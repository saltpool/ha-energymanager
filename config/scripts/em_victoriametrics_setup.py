#!/usr/bin/env python3
import json
import os
import ssl
import time
import urllib.error
import urllib.request


MARKER = "/config/.em_victoriametrics_setup_done"
STATE_FILE = "/config/.em_victoriametrics_setup_state.json"

SUPERVISOR = "http://supervisor"
TOKEN = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")

VICTORIA_REPOSITORY = (
    "https://github.com/VictoriaMetrics-Community/"
    "homeassistant-addon-victoriametrics"
)
COMMUNITY_REPOSITORY = "https://github.com/hassio-addons/repository"
VICTORIA_LOCAL_SLUG = "victoria_metrics"
INFLUX_SLUG = "a0d7b954_influxdb"
GRAFANA_SLUG = "a0d7b954_grafana"
GRAFANA_VICTORIA_PLUGIN = "victoriametrics-metrics-datasource"
COMPLETION_SIGNAL = "EM_VICTORIAMETRICS_MIGRATION_COMPLETE"

VICTORIA_OPTIONS = {
    "retention": "60d",
    "additionalArguments": "",
    "enableHTTPAuth": False,
    "username": "",
    "password": "",
    "enablePrometheusScrape": True,
    "prometheusScrapeHTTPS": False,
    "prometheusScrapeInterval": "15s",
    "prometheusScrapeTimeout": "10s",
    "longelivedToken": "",
}
GRAFANA_ENVIRONMENT = {
    "GF_SECURITY_ALLOW_EMBEDDING": "true",
    "GF_PATHS_PROVISIONING": "/share/grafana/provisioning",
}

SSL_CONTEXT = ssl.create_default_context()


def log(message):
    print(f"[EM] {message}", flush=True)


def unwrap(response):
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def request(method, path, payload=None, timeout=20):
    url = path if path.startswith("http") else f"{SUPERVISOR}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            req, context=SSL_CONTEXT, timeout=timeout
        ) as response:
            body = response.read()
            if not body:
                return {}
            if "application/json" in (response.headers.get("Content-Type") or ""):
                return json.loads(body.decode("utf-8"))
            return body
    except urllib.error.HTTPError as error:
        body = (error.read() or b"").decode("utf-8", errors="ignore").strip()
        log(f"HTTP {error.code} {path} -> {body}")
        raise


def get(path, timeout=20):
    return request("GET", path, timeout=timeout)


def post(path, payload=None, timeout=20):
    return request("POST", path, payload if payload is not None else {}, timeout)


def desired_victoria_options():
    core_info = unwrap(get("/core/info", timeout=10))
    if not isinstance(core_info, dict):
        raise RuntimeError("Supervisor returned invalid Home Assistant core info")

    try:
        port = int(core_info.get("port"))
    except (TypeError, ValueError):
        raise RuntimeError("Supervisor did not report a valid Home Assistant port")

    if not 1 <= port <= 65535:
        raise RuntimeError(f"Supervisor reported invalid Home Assistant port {port}")

    options = dict(VICTORIA_OPTIONS)
    options["homeassistantUrl"] = (
        "homeassistant" if port == 80 else f"homeassistant:{port}"
    )
    return options


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_json_atomic(path, value):
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def remove_state():
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass


def store_data():
    value = unwrap(get("/store"))
    return value if isinstance(value, dict) else {}


def find_victoria_slug():
    for addon in store_data().get("addons", []):
        if not isinstance(addon, dict):
            continue
        slug = str(addon.get("slug") or "")
        if slug == VICTORIA_LOCAL_SLUG or slug.endswith(
            f"_{VICTORIA_LOCAL_SLUG}"
        ):
            return slug
    return None


def store_addon_visible(slug):
    for addon in store_data().get("addons", []):
        if isinstance(addon, dict) and addon.get("slug") == slug:
            return True
    return False


def repository_present(repository_url):
    response = unwrap(get("/store/repositories"))
    repositories = response if isinstance(response, list) else []
    wanted = repository_url.rstrip("/").lower()
    for repository in repositories:
        if not isinstance(repository, dict):
            continue
        for key in ("source", "url"):
            actual = str(repository.get(key) or "").rstrip("/").lower()
            if actual == wanted:
                return True
    return False


def add_repository(repository_url, label):
    if repository_present(repository_url):
        return
    log(f"Adding the {label} app repository")
    try:
        post(
            "/store/repositories",
            {"repository": repository_url},
            timeout=20,
        )
    except urllib.error.HTTPError as error:
        if error.code != 400:
            raise


def reload_store():
    log("Reloading the Home Assistant app store")
    post("/store/reload", {}, timeout=20)


def ensure_grafana_visible():
    if store_addon_visible(GRAFANA_SLUG):
        return True

    add_repository(COMMUNITY_REPOSITORY, "Community")
    reload_store()

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if store_addon_visible(GRAFANA_SLUG):
            return True
        time.sleep(2)
    return False


def ensure_victoria_visible():
    slug = find_victoria_slug()
    if slug:
        return slug

    add_repository(VICTORIA_REPOSITORY, "VictoriaMetrics")
    reload_store()

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        slug = find_victoria_slug()
        if slug:
            return slug
        time.sleep(2)
    return None


def addon_info(slug):
    try:
        value = unwrap(get(f"/addons/{slug}/info", timeout=10))
        return value if isinstance(value, dict) else None
    except urllib.error.HTTPError as error:
        if error.code in (400, 404):
            return None
        raise


def addon_installed(slug):
    info = addon_info(slug)
    return bool(info and info.get("version"))


def install_job_pending(state, state_key, label):
    job_id = state.get(state_key)
    if not job_id:
        return False
    try:
        job = unwrap(get(f"/jobs/{job_id}", timeout=10))
    except urllib.error.HTTPError as error:
        if error.code in (400, 404):
            state.pop(state_key, None)
            save_json_atomic(STATE_FILE, state)
            return False
        raise

    if isinstance(job, dict) and not job.get("done", False):
        progress = job.get("progress")
        detail = "" if progress is None else f" ({progress}%)"
        log(f"{label} installation is still running{detail}")
        return True

    state.pop(state_key, None)
    save_json_atomic(STATE_FILE, state)
    return False


def request_install(slug, state, state_key, label):
    log(f"Requesting background installation of {label}")
    response = unwrap(
        post(
            f"/store/addons/{slug}/install",
            {"background": True},
            timeout=20,
        )
    )
    if isinstance(response, dict) and response.get("job_id"):
        state[state_key] = response["job_id"]
        save_json_atomic(STATE_FILE, state)
    log(f"{label} installation requested; a later invocation will continue setup")


def desired_options_present(info, desired_options):
    current = info.get("options") if isinstance(info, dict) else None
    if not isinstance(current, dict):
        return False
    return all(
        current.get(key) == value
        for key, value in desired_options.items()
    )


def configure_victoria(slug, info, desired_options):
    current = info.get("options") if isinstance(info.get("options"), dict) else {}
    options = dict(current)
    options.update(desired_options)

    log(
        "Configuring VictoriaMetrics to scrape Home Assistant at "
        f"{desired_options['homeassistantUrl']}"
    )
    post(
        f"/addons/{slug}/options",
        {
            "boot": "auto",
            "watchdog": True,
            "auto_update": False,
            "options": options,
        },
        timeout=20,
    )


def start_victoria(slug):
    log("Starting VictoriaMetrics")
    post(f"/addons/{slug}/start", {}, timeout=20)


def victoria_healthy(info):
    hostname = str(info.get("hostname") or "").strip()
    if not hostname:
        return False
    try:
        with urllib.request.urlopen(
            f"http://{hostname}:8428/health", timeout=5
        ) as response:
            return response.status == 200
    except Exception:
        return False


def grafana_options(info):
    current = info.get("options")
    if not isinstance(current, dict):
        current = {}

    options = dict(current)
    plugins = current.get("plugins")
    if not isinstance(plugins, list):
        plugins = []
    if GRAFANA_VICTORIA_PLUGIN not in plugins:
        plugins.append(GRAFANA_VICTORIA_PLUGIN)
    options["plugins"] = plugins

    env_vars = current.get("env_vars")
    if not isinstance(env_vars, list):
        env_vars = []
    environment = {
        item.get("name"): item.get("value")
        for item in env_vars
        if isinstance(item, dict) and item.get("name")
    }
    environment.update(GRAFANA_ENVIRONMENT)
    options["env_vars"] = [
        {"name": name, "value": value}
        for name, value in environment.items()
    ]
    return options


def grafana_options_present(info):
    current = info.get("options")
    if not isinstance(current, dict):
        return False
    plugins = current.get("plugins")
    if not isinstance(plugins, list) or GRAFANA_VICTORIA_PLUGIN not in plugins:
        return False
    env_vars = current.get("env_vars")
    if not isinstance(env_vars, list):
        return False
    environment = {
        item.get("name"): item.get("value")
        for item in env_vars
        if isinstance(item, dict) and item.get("name")
    }
    return all(
        environment.get(name) == value
        for name, value in GRAFANA_ENVIRONMENT.items()
    )


def ensure_grafana_ready(state):
    info = addon_info(GRAFANA_SLUG)
    if not info:
        raise RuntimeError("Grafana is not installed")

    if not grafana_options_present(info):
        log("Configuring Grafana and the VictoriaMetrics data-source plugin")
        post(
            f"/addons/{GRAFANA_SLUG}/options",
            {
                "boot": "auto",
                "watchdog": True,
                "auto_update": False,
                "options": grafana_options(info),
            },
            timeout=20,
        )
        state["grafana_plugin_restart_requested"] = True
        save_json_atomic(STATE_FILE, state)
        if info.get("state") == "started":
            log("Restarting Grafana to install the VictoriaMetrics plugin")
            post(f"/addons/{GRAFANA_SLUG}/restart", {}, timeout=20)
        else:
            log("Starting Grafana to install the VictoriaMetrics plugin")
            post(f"/addons/{GRAFANA_SLUG}/start", {}, timeout=20)
        return False

    if state.get("grafana_plugin_restart_requested"):
        if info.get("state") != "started":
            log("Grafana is still starting or installing the plugin")
            return False
        state.pop("grafana_plugin_restart_requested", None)
        save_json_atomic(STATE_FILE, state)

    if info.get("state") != "started":
        state["grafana_plugin_restart_requested"] = True
        save_json_atomic(STATE_FILE, state)
        log("Starting Grafana")
        post(f"/addons/{GRAFANA_SLUG}/start", {}, timeout=20)
        return False

    return True


def uninstall_influxdb():
    if not addon_installed(INFLUX_SLUG):
        return True

    log("Permanently uninstalling InfluxDB and deleting its app configuration")
    try:
        post(
            f"/addons/{INFLUX_SLUG}/uninstall",
            {"remove_config": True},
            timeout=20,
        )
    except (TimeoutError, urllib.error.URLError):
        log("InfluxDB removal is still being processed; will check again")
        return False

    return not addon_installed(INFLUX_SLUG)


def write_completion_marker(slug):
    temporary = f"{MARKER}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(f"ok\nslug={slug}\n")
    os.replace(temporary, MARKER)
    remove_state()


def adopt_preinstalled_victoria(slug):
    log(
        "VictoriaMetrics is already installed and InfluxDB is absent; "
        "recording setup as complete without making changes"
    )
    write_completion_marker(slug)


def finish_migration(slug):
    write_completion_marker(slug)
    log(
        "VictoriaMetrics setup complete; Grafana plugin installed; "
        "InfluxDB removed"
    )
    log(COMPLETION_SIGNAL)


def main():
    if os.path.exists(MARKER):
        return 0

    if not TOKEN:
        log("Missing SUPERVISOR_TOKEN/HASSIO_TOKEN")
        return 2

    state = load_state()

    existing_slug = find_victoria_slug()
    if (
        not state
        and existing_slug
        and addon_installed(existing_slug)
        and addon_installed(GRAFANA_SLUG)
        and not addon_installed(INFLUX_SLUG)
    ):
        adopt_preinstalled_victoria(existing_slug)
        return 0

    if not state.get("migration_started"):
        state["migration_started"] = True
        save_json_atomic(STATE_FILE, state)

    if not ensure_grafana_visible():
        log("Grafana is not visible yet; will retry later")
        return 0

    if not addon_installed(GRAFANA_SLUG):
        if install_job_pending(
            state,
            "grafana_install_job_id",
            "Grafana",
        ):
            return 0
        if addon_installed(GRAFANA_SLUG):
            return 0
        request_install(
            GRAFANA_SLUG,
            state,
            "grafana_install_job_id",
            "Grafana",
        )
        return 0

    if state.get("grafana_install_job_id"):
        state.pop("grafana_install_job_id", None)
        save_json_atomic(STATE_FILE, state)

    slug = ensure_victoria_visible()
    if not slug:
        log("VictoriaMetrics is not visible yet; will retry later")
        return 0

    if not addon_installed(slug):
        if install_job_pending(
            state,
            "victoria_install_job_id",
            "VictoriaMetrics",
        ):
            return 0
        if addon_installed(slug):
            return 0
        request_install(
            slug,
            state,
            "victoria_install_job_id",
            "VictoriaMetrics",
        )
        return 0

    if state.get("victoria_install_job_id"):
        state.pop("victoria_install_job_id", None)
        save_json_atomic(STATE_FILE, state)

    info = addon_info(slug) or {}
    desired_options = desired_victoria_options()
    if not desired_options_present(info, desired_options):
        configure_victoria(slug, info, desired_options)
        log("VictoriaMetrics configured; a later invocation will start it")
        return 0

    if info.get("state") != "started":
        start_victoria(slug)
        log("VictoriaMetrics start requested; will check health later")
        return 0

    if not victoria_healthy(info):
        log("VictoriaMetrics is starting but is not healthy yet; will retry")
        return 0

    if not ensure_grafana_ready(state):
        return 0

    if not uninstall_influxdb():
        return 0

    finish_migration(slug)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        log(f"Setup failed: {error.__class__.__name__}: {error}")
        raise
