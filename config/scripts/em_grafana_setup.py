#!/usr/bin/env python3
import os, json, time, ssl, urllib.request, urllib.error, urllib.parse

MARKER = "/config/.em_grafana_setup_done"
if os.path.exists(MARKER):
    raise SystemExit(0)

SUP = "http://supervisor"
TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
if not TOKEN:
    print("[EM] Missing SUPERVISOR_TOKEN/HASSIO_TOKEN")
    raise SystemExit(2)

HDR = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
CTX = ssl.create_default_context()

GRAFANA_SLUG = "a0d7b954_grafana"
GRAFANA_HOST = "a0d7b954-grafana"
INFLUX_SLUG  = "a0d7b954_influxdb"
INFLUX_HOST  = "a0d7b954-influxdb"
COMMUNITY_REPO = "https://github.com/hassio-addons/repository"

def _req(method, url, payload=None, timeout=30):
    data = None if payload is None else (json.dumps(payload).encode() if not isinstance(payload, (bytes, bytearray)) else payload)
    req = urllib.request.Request(url, data=data, headers=HDR, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=timeout) as r:
            body = r.read()
            if "application/json" in (r.headers.get("Content-Type") or ""):
                return json.loads(body.decode() or "{}")
            return body
    except urllib.error.HTTPError as e:
        msg = (e.read() or b"").decode(errors="ignore")
        print(f"[EM] HTTP {e.code} {url} -> {msg.strip()}")
        raise
    except Exception as e:
        print(f"[EM] {method} {url} failed: {e}")
        raise

def GET(u, timeout=30):           return _req("GET",  u, None, timeout)
def POST(u, p, timeout=30):       return _req("POST", u, p, timeout)

def ensure_dirs():
    for p in [
        "/config/dashboards", "/config/scripts", "/config/www",
        "/share/grafana/dashboards",
        "/share/grafana/provisioning/dashboards",
        "/share/grafana/provisioning/datasources",
        "/share/grafana/secrets",
    ]:
        os.makedirs(p, exist_ok=True)

def write(path, content, only_if_missing=False):
    if only_if_missing and os.path.exists(path): return
    with open(path, "w", encoding="utf-8") as f: f.write(content)

def download(url, dest):
    if os.path.exists(dest): return
    try:
        with urllib.request.urlopen(url, context=CTX, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        print(f"[EM] Downloaded {url} -> {dest}")
    except Exception as e:
        print(f"[EM] Download failed: {url} -> {e}")

def store_addon_visible(slug):
    try:
        resp = GET(f"{SUP}/store/addons/{slug}"); return isinstance(resp, dict) and bool(resp)
    except urllib.error.HTTPError as e:
        return False if e.code in (400, 404) else (_ for _ in ()).throw(e)
    except Exception:
        return False

def reload_store():
    print("[EM] Reloading store…"); POST(f"{SUP}/store/reload", {})

def ensure_addons_visible():
    need_g = not store_addon_visible(GRAFANA_SLUG)
    need_i = not store_addon_visible(INFLUX_SLUG)
    if not (need_g or need_i):
        print("[EM] Add-ons already visible in store."); return
    print("[EM] Ensuring Community repo…")
    try:
        POST(f"{SUP}/store/repositories", {"repository": COMMUNITY_REPO})
        print("[EM] Community repo added.")
    except urllib.error.HTTPError as e:
        body = (e.read() or b"").decode(errors="ignore")
        if e.code == 400 and "already in the store" in body.lower():
            print("[EM] Community repo already present.")
        else:
            raise
    reload_store()
    print("[EM] Waiting for add-ons to appear…")
    t0 = time.time()
    while time.time() - t0 < 180:
        if store_addon_visible(GRAFANA_SLUG) and store_addon_visible(INFLUX_SLUG): return
        time.sleep(2)
    raise RuntimeError("Store did not expose Grafana/InfluxDB in time")

def addon_installed(slug):
    try:
        info = GET(f"{SUP}/addons/{slug}/info")
        return bool(info.get("data", {}).get("version"))
    except Exception:
        return False

def install_addon(slug):
    print(f"[EM] Installing add-on: {slug}")
    try:
        POST(f"{SUP}/store/addons/{slug}/install", {}, timeout=5)
    except Exception as e:
        print(f"[EM] install call returned {e.__class__.__name__}: {e} — continuing to poll")

def wait_addon_installed(slug, max_s, label):
    t0 = time.time(); last = 0
    while time.time() - t0 < max_s:
        if addon_installed(slug):
            print(f"[EM] {label} installed."); return True
        if int(time.time() - t0)//10 > last:
            last = int(time.time() - t0)//10
            print(f"[EM] Waiting for {label} to install… {int(time.time() - t0)}s")
        time.sleep(2)
    return False

def start_addon(slug):
    print(f"[EM] Starting add-on: {slug}")
    try:
        POST(f"{SUP}/addons/{slug}/start", {}, timeout=10)
    except Exception as e:
        print(f"[EM] start call returned {e.__class__.__name__}: {e} — will check status")

def restart_addon_async(slug):
    print(f"[EM] Restarting add-on: {slug}")
    try:
        POST(f"{SUP}/addons/{slug}/restart", {}, timeout=5)
    except Exception as e:
        print(f"[EM] restart call returned {e.__class__.__name__}: {e} — continuing to poll")

def ensure_boot_watchdog(slug):
    try:
        POST(f"{SUP}/addons/{slug}/options", {"boot": "auto", "watchdog": True, "auto_update": False})
        print(f"[EM] Ensured boot=auto, watchdog=true for {slug}")
    except Exception as e:
        print(f"[EM] WARN: couldn't set boot/watchdog for {slug}: {e}")

def grafana_up(timeout=3):
    try:
        with urllib.request.urlopen(f"http://{GRAFANA_HOST}:3000/api/health", timeout=timeout) as r: return r.status == 200
    except Exception: return False

def wait_grafana_down(max_s=90):
    t0 = time.time()
    while time.time() - t0 < max_s:
        if not grafana_up(2): return True
        time.sleep(2)
    return False

def wait_grafana_up(max_s=300):
    t0 = time.time()
    while time.time() - t0 < max_s:
        if grafana_up(3): return True
        time.sleep(2)
    return False

def restart_grafana_and_wait():
    restart_addon_async(GRAFANA_SLUG)
    wait_grafana_down(90)
    if not wait_grafana_up(300):
        print("[EM] WARN: Grafana health not reachable after restart; proceeding.")

def influx_up(timeout=3):
    try:
        with urllib.request.urlopen(f"http://{INFLUX_HOST}:8086/ping", timeout=timeout) as r: return r.status in (200,204)
    except Exception: return False

def wait_influx_up(max_s=180):
    t0 = time.time()
    while time.time() - t0 < max_s:
        if influx_up(3): return True
        time.sleep(2)
    return False

def init_influx_v1(db_name="home_assistant"):
    url = f"http://{INFLUX_HOST}:8086/query"
    def q(stmt):
        data = urllib.parse.urlencode({"q": stmt}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/x-www-form-urlencoded"})
        urllib.request.urlopen(req, timeout=10).read()
    try:
        q(f"CREATE DATABASE {db_name}")
        q(f'CREATE RETENTION POLICY "autogen" ON "{db_name}" DURATION 0 REPLICATION 1 DEFAULT')
        print(f"[EM] InfluxDB database ensured: {db_name}")
    except Exception as e:
        print(f"[EM] WARN: DB init may have partially failed (likely already exists): {e}")

def set_grafana_env_minimal():
    info = GET(f"{SUP}/addons/{GRAFANA_SLUG}/info")
    opts = info.get("data", {}).get("options", {}) or {}
    opts["env_vars"] = [
        {"name": "GF_SECURITY_ALLOW_EMBEDDING", "value": "true"},
        {"name": "GF_PATHS_PROVISIONING", "value": "/share/grafana/provisioning"},
    ]
    POST(f"{SUP}/addons/{GRAFANA_SLUG}/options", {"options": opts})
    print("[EM] Grafana env set to minimal (embedding + provisioning).")

def merge_influx_envvars(kv):
    info = GET(f"{SUP}/addons/{INFLUX_SLUG}/info")
    opts = info.get("data", {}).get("options", {}) or {}
    envs = opts.get("envvars", [])
    mp = {e.get("name"): e.get("value") for e in envs if isinstance(e, dict)}
    mp.update(kv)
    opts["envvars"] = [{"name": k, "value": v} for k, v in mp.items()]
    POST(f"{SUP}/addons/{INFLUX_SLUG}/options", {"options": opts})

def main():
    ensure_dirs()

    ensure_addons_visible()
    if not addon_installed(INFLUX_SLUG):  install_addon(INFLUX_SLUG)
    if not addon_installed(GRAFANA_SLUG): install_addon(GRAFANA_SLUG)

    if not addon_installed(GRAFANA_SLUG):
        if not wait_addon_installed(GRAFANA_SLUG, 1800, "Grafana"):
            raise RuntimeError("Timed out waiting for Grafana to install")
    if not addon_installed(INFLUX_SLUG):
        if not wait_addon_installed(INFLUX_SLUG, 1800, "InfluxDB"):
            raise RuntimeError("Timed out waiting for InfluxDB to install")

    merge_influx_envvars({"INFLUXDB_HTTP_AUTH_ENABLED": "false"})
    start_addon(INFLUX_SLUG)
    if wait_influx_up(300):
        init_influx_v1("home_assistant")
    else:
        print("[EM] WARN: InfluxDB HTTP not reachable; continuing.")

    set_grafana_env_minimal()
    restart_grafana_and_wait()

    ensure_boot_watchdog(INFLUX_SLUG)
    ensure_boot_watchdog(GRAFANA_SLUG)

    with open(MARKER, "w") as f: f.write("ok\n")
    print("[EM] Energy Manager setup complete.")

if __name__ == "__main__":
    main()


