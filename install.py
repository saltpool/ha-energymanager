#!/usr/bin/env python3
"""Energy Manager bootstrap installer (development).

Run in Advanced SSH & Web Terminal on dedicated Home Assistant OS.
"""
import argparse
import getpass
import uuid
import shutil
from datetime import datetime
import importlib.util
import io
import zipfile
import json
import re
import urllib.error
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import time
import stat

REPO = os.environ.get('EM_UPDATE_REPOSITORY', 'saltpool/ha-energymanager')
BRANCH = os.environ.get('EM_UPDATE_BRANCH', 'development')
ROOT = Path('/config')
STATE = ROOT / '.energy_manager'
SCRIPTS = ROOT / 'scripts'
REQUIRED = (
    'update_checker.py',
    'file_merger.py',
    'marketplace_manager.py',
    'em_apps_manager.py',
    'em_post_reboot.py',
    'configure_em_integrations.py',
    'perform_energy_manager_update.py',
)
SSH_HOST = 'a0d7b954-ssh.local.hass.io'
SSH_USER = 'hassio'


def log(message):
    print(f'[EM Install] {message}', flush=True)


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def prepare():
    if not (os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')):
        raise RuntimeError('Supervisor token not available; run in Advanced SSH & Web Terminal')
    if not ROOT.is_dir() or not Path('/share').is_dir():
        raise RuntimeError('Home Assistant /config or /share is unavailable')

    STATE.mkdir(parents=True, exist_ok=True)
    SCRIPTS.mkdir(parents=True, exist_ok=True)

    version_file = STATE / 'version.txt'
    if not version_file.exists():
        version_file.write_text('0.0.0\n', encoding='utf-8')
        log('Initialised Energy Manager version tracking')
    else:
        log('Existing version tracking preserved')

    if importlib.util.find_spec('requests') is None:
        log('Installing missing Python requests dependency')
        run([sys.executable, '-m', 'pip', 'install', 'requests'])
    else:
        log('Python requests dependency available')

    base = f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/config/scripts'
    for filename in REQUIRED:
        url = f'{base}/{filename}'
        target = SCRIPTS / filename
        log(f'Downloading {filename}')
        with urllib.request.urlopen(url, timeout=60) as response:
            source = response.read()
        compile(source, str(target), 'exec')
        temp = target.with_name(target.name + '.em-download')
        temp.write_bytes(source)
        os.replace(temp, target)
    log('Bootstrap scripts downloaded and syntax checked')

    private = STATE / 'ssh_key'
    public = STATE / 'ssh_key.pub'
    if private.exists() and public.exists():
        log('Existing SSH keypair preserved')
    elif private.exists() or public.exists():
        raise RuntimeError('Incomplete SSH keypair: refusing to overwrite existing key')
    else:
        log('Generating SSH keypair')
        run(['ssh-keygen', '-t', 'ed25519', '-f', str(private), '-N', '', '-C', 'energy_manager_automation'])
    log('SSH keypair ready')
    log('Preparation complete. SSH authorisation is not required for initial deployment.')



def supervisor_request(method, path, payload=None, timeout=30):
    token = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
    if not token:
        raise RuntimeError('Supervisor token not available')
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        'http://supervisor' + path, data=data, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Supervisor HTTP {exc.code}: {detail}') from exc
    if result.get('result') == 'error':
        raise RuntimeError(result.get('message', 'Supervisor rejected request'))
    return result.get('data', result)



def install_apps():
    manager = SCRIPTS / 'em_apps_manager.py'
    if not manager.is_file():
        raise RuntimeError('App manager missing; run --step prepare first')
    if not (os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')):
        raise RuntimeError('Supervisor token not available')

    manifest_url = f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/manifest/manifest.json'
    log(f'Downloading manifest from {REPO} ({BRANCH})')
    with urllib.request.urlopen(manifest_url, timeout=60) as response:
        manifest = json.load(response)
    apps = manifest.get('apps')
    if not isinstance(apps, list) or not apps:
        raise RuntimeError('Manifest has no valid apps list; refusing to continue')
    if not isinstance(manifest.get('nodered_dependencies', {}), dict):
        raise RuntimeError('Invalid Node-RED dependency manifest')

    manifest_file = STATE / 'install-manifest.json'
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_file.with_name(manifest_file.name + '.download')
    temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    os.replace(temporary, manifest_file)

    log(f'Reconciling {len(apps)} Supervisor Apps and Node-RED dependencies')
    # Run in the foreground: all App manager output stays visible.
    run([sys.executable, '-u', str(manager), '--manifest', str(manifest_file)])
    log('Supervisor App installation and Node-RED dependencies complete')

    nodered_dir = Path('/addon_configs/a0d7b954_nodered')
    if nodered_dir.is_dir():
        log(f'Node-RED configuration directory accessible: {nodered_dir}')
        flow_path = nodered_dir / 'flows.json'
        log(f'Node-RED flows.json exists: {flow_path.is_file()}')
    else:
        log(f'Node-RED configuration directory NOT accessible at {nodered_dir}')
        log('Direct flow deployment cannot be assumed from this environment')
    storage = ROOT / '.storage'
    log(f'Home Assistant .storage accessible: {storage.is_dir()}')
    log('App stage complete; no SSH authentication or SSH App restart requested')



def _download_text(source):
    from update_checker import manifest_source_path
    safe = manifest_source_path(source)
    url = f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/{safe}'
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f'Failed to download {source}: HTTP {exc.code}\n'
            f'URL: {url}'
        ) from exc


def _backup_file(path, label):
    if not path.is_file():
        return
    backup_dir = STATE / 'backups' / ('installer_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / (label + '.bak')
    shutil.copy2(path, backup)
    log(f'Backup: {path} -> {backup}')


def _write_atomic(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.em-install-temp')
    try:
        temp.write_text(contents, encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _install_base_yaml(name, downloaded):
    path = ROOT / name
    original = path.read_text(encoding='utf-8') if path.exists() else ''
    if 'ENERGY_MANAGER_' in original:
        return False  # The existing file merger has already handled it.
    if name == 'configuration.yaml':
        # Avoid silently destroying unrelated YAML from a configured instance.
        vanilla_lines = {
            'default_config:', 'frontend:', 'themes: !include_dir_merge_named themes',
            'automation: !include automations.yaml', 'script: !include scripts.yaml',
            'scene: !include scenes.yaml',
        }
        active = [line.strip() for line in original.splitlines()
                  if line.strip() and not line.lstrip().startswith('#')]
        unexpected = [line for line in active if line not in vanilla_lines]
        if unexpected:
            raise RuntimeError('Existing configuration.yaml contains custom settings and '
                               'no Energy Manager markers; refusing to overwrite: '
                               + ', '.join(unexpected[:5]))
        result = downloaded
    else:
        raise ValueError(name)
    if original == result:
        return True
    _backup_file(path, name)
    _write_atomic(path, result)
    log(f'Initialised /config/{name} with Energy Manager configuration')
    return True


def _ensure_modbus_secrets():
    path = ROOT / 'secrets.yaml'
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    values = (
        ('modbus_host_ip', '"REPLACE_WITH_INVERTER_IP"  # Set to your inverter IP, no default, remove quotes'),
        ('modbus_port', '502  # Default Modbus port'),
        ('modbus_slave', '1  # Default Modbus slave address'),
    )
    additions = [(key, value) for key, value in values
                 if not re.search(r'^\s*' + re.escape(key) + r'\s*:', existing, flags=re.MULTILINE)]
    if not additions:
        log('Existing Modbus secrets preserved; no changes needed')
        return
    _backup_file(path, 'secrets.yaml')
    separator = '' if not existing or existing.endswith('\n') else '\n'
    addition = '\n'.join(f'{key}: {value}' for key, value in additions) + '\n'
    _write_atomic(path, existing + separator + addition)
    log('Added missing Modbus secrets: ' + ', '.join(key for key, _ in additions))
    log('Inverter IP must be configured during onboarding (no IP address assumed)')


def _ensure_prometheus():
    import re
    path = ROOT / 'configuration.yaml'
    content = path.read_text(encoding='utf-8')
    if re.search(r'^prometheus\s*:', content, re.MULTILINE):
        log('Existing Prometheus configuration preserved')
        return
    _backup_file(path, 'configuration-prometheus.yaml')
    separator = '' if not content or content.endswith('\n') else '\n'
    _write_atomic(path, content + separator + '\n# Energy Manager metrics for VictoriaMetrics\nprometheus:\n')
    log('Enabled built-in Home Assistant Prometheus integration')


def _merge_flows(old_content, new_content):
    old = json.loads(old_content)
    new = json.loads(new_content)
    if not isinstance(old, list) or not isinstance(new, list):
        raise ValueError('Node-RED flows must be JSON arrays')
    def tab(node):
        return (isinstance(node, dict) and node.get('type') == 'tab'
                and isinstance(node.get('label'), str) and 'id' in node)
    old_tabs = {n['id'] for n in old if tab(n) and n['label'].startswith('EnergyManager-')}
    new_tabs = {n['id'] for n in new if tab(n) and n['label'].startswith('EnergyManager-')}
    if not new_tabs:
        raise RuntimeError('Downloaded flows contain no EnergyManager- tabs; refusing replacement')
    retained = [n for n in old if not (tab(n) and n['id'] in old_tabs)
                and n.get('z') not in old_tabs]
    incoming = [n for n in new if (tab(n) and n['id'] in new_tabs)
                or n.get('z') in new_tabs]
    subflows = {n['type'].split(':', 1)[1] for n in incoming
                if isinstance(n.get('type'), str) and n['type'].startswith('subflow:')}
    if subflows:
        retained = [n for n in retained if not (n.get('type') == 'subflow'
                    and n.get('id') in subflows)]
        retained += [n for n in new if n.get('type') == 'subflow'
                     and n.get('id') in subflows]
    ids = {n.get('id') for n in retained}
    retained.extend(n for n in incoming if n.get('id') not in ids)

    # Include global configuration nodes referenced by Energy Manager.
    # These include the HA server, entity configs and device configs.
    global_configs = {
        node['id']: node
        for node in new
        if isinstance(node, dict)
        and node.get('id')
        and not node.get('z')
        and node.get('type') != 'tab'
    }

    def referenced_ids(value):
        if isinstance(value, str):
            if value in global_configs:
                yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from referenced_ids(child)
        elif isinstance(value, list):
            for child in value:
                yield from referenced_ids(child)

    required = set()
    pending = list(incoming)

    while pending:
        node = pending.pop()
        for ref in referenced_ids(node):
            if ref not in required:
                required.add(ref)
                pending.append(global_configs[ref])

    existing_ids = {node.get('id') for node in retained}
    added_configs = 0

    for ref in sorted(required):
        if ref not in existing_ids:
            retained.append(global_configs[ref])
            existing_ids.add(ref)
            added_configs += 1

    log(f'Added {added_configs} missing Node-RED configuration nodes')
    log(f'Flow merge: replaced {len(old_tabs)} EM tabs with {len(new_tabs)} EM tabs')
    return json.dumps(retained, separators=(',', ':'))


def deploy():
    if not (SCRIPTS / 'file_merger.py').is_file():
        raise RuntimeError('Bootstrap files missing; run --step prepare')
    if not Path('/addon_configs/a0d7b954_nodered').is_dir():
        raise RuntimeError('Node-RED missing; run --step install-apps')
    sys.path.insert(0, str(SCRIPTS))
    from file_merger import EnergyManagerFileMerger
    from update_checker import safe_repo_path

    manifest_path = STATE / 'install-manifest.json'
    log(f'Downloading current manifest from {REPO} ({BRANCH})')
    url = f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/manifest/manifest.json'
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            manifest = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f'Failed to download manifest: HTTP {exc.code}\n'
            f'URL: {url}'
        ) from exc
    if not isinstance(manifest.get('files'), dict):
        raise RuntimeError('Invalid manifest files map')
    # Download and validate all file content before changing any installed files.
    downloads = {}
    for name, entry in manifest['files'].items():
        path = safe_repo_path(name)
        if not isinstance(entry, dict) or entry.get('action', 'merge') not in ('merge', 'replace', 'create', 'remove'):
            raise ValueError(f'Invalid manifest file entry: {name}')
        if entry.get('action') != 'remove':
            downloads[name] = _download_text(name)
    flow_config = manifest.get('nodered_flows') or {}
    if not flow_config.get('download_url'):
        raise RuntimeError('Manifest lacks Node-RED flows download URL')
    flows = _download_text(flow_config['download_url'])
    fresh_flows = json.loads(flows)
    if not isinstance(fresh_flows, list):
        raise RuntimeError('Downloaded flows are not a JSON array')
    log(f'Validated {len(downloads)} manifest files and Node-RED flows')

    merger = EnergyManagerFileMerger()
    errors = []
    for name, info in manifest['files'].items():
        rel = safe_repo_path(name)
        destination = Path('/') / rel if rel.startswith('share/') else ROOT / rel
        action = info.get('action', 'merge')
        log(f'{action}: {destination}')
        try:
            if action == 'remove':
                if destination.is_file() or destination.is_symlink():
                    destination.unlink()
                    log(f'Removed obsolete file: {destination}')
                else:
                    log(f'Already absent, skipping: {destination}')
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = downloads[name]
            if action == 'replace':
                result = merger.replace_file(str(destination), content, manifest['version'])
            elif action == 'create':
                if name == 'em_initial_states.csv':
                    result = merger.replace_file(
                        str(destination), content, manifest['version']
                    )
                else:
                    result = (
                        True if destination.exists()
                        else merger.replace_file(
                            str(destination), content, manifest['version']
                        )
                    )
            else:
                result = merger.update_file(str(destination), content, info.get('sections', []), manifest['version'])
            if not result:
                raise RuntimeError('File merger returned failure')
        except Exception as exc:
            errors.append(f'{name}: {exc}')
            log(f'ERROR: {errors[-1]}')
    if errors:
        raise RuntimeError('Manifest deployment incomplete: ' + '; '.join(errors))

    for base_name in ('configuration.yaml',):
        if base_name not in downloads:
            raise RuntimeError(f'Manifest missing required {base_name}')
        _install_base_yaml(base_name, downloads[base_name])
    _ensure_modbus_secrets()
    _ensure_prometheus()
    log('Manifest file deployment complete')

    flow_path = Path('/addon_configs/a0d7b954_nodered/flows.json')
    old_flows = flow_path.read_text(encoding='utf-8') if flow_path.exists() else '[]'
    merged_flows = _merge_flows(old_flows, flows)
    if not flow_path.exists() or merged_flows != old_flows:
        _backup_file(flow_path, 'nodered-flows.json')
        _write_atomic(flow_path, merged_flows)
        log('Node-RED flows deployed directly')
        log('Restarting Node-RED through Supervisor to load deployed flows')
        try:
            supervisor_request('POST', '/addons/a0d7b954_nodered/restart', {}, timeout=45)
        except (TimeoutError, urllib.error.URLError) as exc:
            log(f'Node-RED restart request interrupted: {exc}; checking App status')
        status = supervisor_request('GET', '/addons/a0d7b954_nodered/info')
        log(f'Node-RED Supervisor state: {status.get("state", "unknown")}')
    else:
        log('Node-RED flows already current')

    # Register Lovelace resources through Home Assistant's supported API.
    # Do not modify .storage/lovelace_resources directly while Core is running.
    resources = manifest.get('lovelace_resources') or []

    if not isinstance(resources, list):
        raise RuntimeError('Unexpected Lovelace resource manifest format')

    if resources:
        from marketplace_manager import HAWebSocket

        with HAWebSocket() as ws:
            existing_resources = ws.call('lovelace/resources/list')
            if not isinstance(existing_resources, list):
                raise RuntimeError(
                    'Unexpected Lovelace resource registry response'
                )

            existing_by_url = {
                item['url']: item
                for item in existing_resources
                if isinstance(item, dict) and item.get('url')
            }

            for resource in resources:
                url = resource['url']
                resource_type = resource.get('type', 'module')
                existing = existing_by_url.get(url)

                if existing is None:
                    ws.call(
                        'lovelace/resources/create',
                        url=url,
                        res_type=resource_type,
                    )
                    log(f'Added Lovelace resource: {url}')

                elif existing.get('type') != resource_type:
                    ws.call(
                        'lovelace/resources/update',
                        resource_id=existing['id'],
                        res_type=resource_type,
                    )
                    log(f'Updated Lovelace resource: {url}')

                else:
                    log(f'Lovelace resource already correct: {url}')

        log(f'Verified {len(resources)} Lovelace resources')

    log('Deployment stage complete: files, Node-RED flows, Lovelace resources')
    log('Inverter-specific onboarding and Home Assistant reboot follow deployment')


def core_request(method, endpoint, payload=None, timeout=45):
    token = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
    if not token:
        raise RuntimeError('Supervisor token not available')
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'http://supervisor/core/api/' + endpoint.lstrip('/'),
        data=data, method=method,
        headers={'Authorization': 'Bearer ' + token,
                 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read() or b'{}')

def _marketplace_source():
    """Download and compile manager before altering installation."""
    url = f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/config/scripts/marketplace_manager.py'
    request = urllib.request.Request(url, headers={'User-Agent': 'EnergyManagerBootstrap/2.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        source = response.read(1024 * 1024 + 1)
    if len(source) > 1024 * 1024:
        raise RuntimeError('Marketplace manager exceeds size limit')
    compile(source, 'marketplace_manager.py', 'exec')
    return source


def preflight_marketplace(source):
    """Obtain consent prior to deployment or App changes."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='em-marketplace-') as directory:
        target = Path(directory) / 'marketplace_manager.py'
        target.write_bytes(source)
        run([sys.executable, str(target), '--preflight', '--consent', '--github-auth',])
    log('Marketplace consent confirmed')


def install_marketplace():
    """Reconcile Marketplace components in the main installation."""
    from contextlib import redirect_stdout

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, text):
            for stream in self.streams:
                stream.write(text)
                stream.flush()

        def flush(self):
            for stream in self.streams:
                stream.flush()
                
    sys.path.insert(0, str(SCRIPTS))
    from marketplace_manager import sync_marketplace_components
    manifest = json.loads((STATE / 'install-manifest.json').read_text(encoding='utf-8'))
    entries = manifest.get('marketplace_components', [])
    if not entries:
        raise RuntimeError('Manifest is missing marketplace_components')

    log_path = STATE / 'marketplace-install.log'
    log(f'Saving Marketplace installation log to {log_path}')

    with log_path.open('w', encoding='utf-8', buffering=1) as logfile:
        with redirect_stdout(Tee(sys.stdout, logfile)):
            changes = sync_marketplace_components(entries)

    log(f'Marketplace components reconciled: {len(changes)} changes')


def register_post_reboot_hook():
    """Arm SSH App post-reboot configuration before first OS reboot."""
    script = SCRIPTS / 'em_post_reboot.py'
    if not script.is_file():
        raise RuntimeError('Post-reboot script missing: ' + str(script))
    addon = '/addons/a0d7b954_ssh'
    info = supervisor_request('GET', addon + '/info')
    options = dict(info.get('options') or {})
    commands = list(options.get('init_commands') or [])
    hook = ("sh -c 'nohup python3 /config/scripts/em_post_reboot.py "
            "> /config/.energy_manager/post-reboot.log 2>&1 < /dev/null &'")
    if hook not in commands:
        commands.append(hook)
        options['init_commands'] = commands
        supervisor_request('POST', addon + '/options', {'options': options}, timeout=60)
    saved = supervisor_request('GET', addon + '/info')
    if hook not in ((saved.get('options') or {}).get('init_commands') or []):
        raise RuntimeError('Supervisor did not retain post-reboot init command')
    _write_atomic(STATE / 'post-reboot-status.json', json.dumps({
        'status': 'pending', 'kind': 'install',
        'detail': 'Waiting for Home Assistant OS reboot'
    }) + '\n')
    log('Post-reboot MQTT and Node-RED configuration hook registered')



def finalise():
    sys.path.insert(0, str(SCRIPTS))

    if not (ROOT / 'configuration.yaml').is_file():
        raise RuntimeError('Home Assistant configuration missing; run --step deploy first')
    if not (Path('/addon_configs/a0d7b954_nodered') / 'flows.json').is_file():
        raise RuntimeError('Node-RED flows missing; run --step deploy first')

    log('Validating Home Assistant configuration before reboot')
    try:
        result = core_request('POST', 'config/core/check_config', {}, timeout=120)
    except urllib.error.HTTPError as exc:
        reason = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Home Assistant configuration check HTTP {exc.code}: {reason}') from exc
    status = str(result.get('result', '')).lower()
    if status != 'valid':
        log('Home Assistant configuration validation result: ' + json.dumps(result))
        raise RuntimeError('Home Assistant configuration is not valid; OS will NOT be rebooted')
    log('Home Assistant configuration valid')

    STATE.mkdir(parents=True, exist_ok=True)
    marker = STATE / 'install-status.json'
    marker_payload = {
        'status': 'reboot_requested',
        'repository': REPO,
        'branch': BRANCH,
        'requested_at': datetime.now().astimezone().isoformat(),
        'note': 'Installation deployed and configuration validated; post-reboot verification pending.',
    }
    _write_atomic(marker, json.dumps(marker_payload, indent=2) + '\n')

    log('Installation files deployed and Home Assistant configuration validated.')
    log('A full Home Assistant OS reboot will now be requested.')
    log('The SSH terminal will disconnect; this is expected.')
    log('After reboot, complete inverter, BOM, Solcast, electricity provider and Energy Manager account setup as required.')
    log('Reboot request status saved to /config/.energy_manager/install-status.json')

    try:
        supervisor_request('POST', '/host/reboot', {}, timeout=10)
    except urllib.error.HTTPError as exc:
        # An HTTP response means the Supervisor explicitly rejected the request.
        error = exc.read().decode('utf-8', errors='replace')
        marker_payload['status'] = 'reboot_request_failed'
        _write_atomic(marker, json.dumps(marker_payload, indent=2) + '\n')
        raise RuntimeError(f'Host reboot rejected (HTTP {exc.code}): {error}') from exc
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        # The host may go down while the request is in flight. We cannot
        # distinguish that from a network failure here; do not claim success.
        log(f'Reboot connection interrupted: {exc}')
        log('Reboot may be underway. Check whether Home Assistant restarts; if not, reboot it via Settings > System.')
        return
    log('Full Home Assistant OS reboot requested successfully. The terminal may disconnect now.')


def configure_ssh(restart=True):
    public_file = STATE / 'ssh_key.pub'
    private_file = STATE / 'ssh_key'
    if not public_file.is_file() or not private_file.is_file():
        raise RuntimeError('SSH keypair missing; run --step prepare first')
    public_key = public_file.read_text(encoding='utf-8').strip()
    if not public_key.startswith('ssh-ed25519 '):
        raise RuntimeError('Unexpected SSH public key format')

    slug = 'a0d7b954_ssh'
    info = supervisor_request('GET', f'/addons/{slug}/info')
    options = dict(info.get('options') or {})
    ssh = dict(options.get('ssh') or {})
    keys = list(ssh.get('authorized_keys') or [])
    if public_key in keys:
        log('SSH public key already authorised; existing settings preserved')
        return

    keys.append(public_key)
    ssh['authorized_keys'] = keys
    options['ssh'] = ssh
    log('Adding Energy Manager SSH key, preserving existing App credentials and settings')
    supervisor_request('POST', f'/addons/{slug}/options', {'options': options}, timeout=60)
    verified = supervisor_request('GET', f'/addons/{slug}/info')
    saved_keys = ((verified.get('options') or {}).get('ssh') or {}).get('authorized_keys') or []
    if public_key not in saved_keys:
        raise RuntimeError('Supervisor did not retain the Energy Manager SSH key')
    log('SSH public key authorised successfully')
    if not restart:
        log('SSH key will be activated by the final Home Assistant OS reboot')
        return
    log('Restarting Advanced SSH & Web Terminal to activate the new key')
    log('This may disconnect this terminal. Reopen it and run --step check-ssh.')
    try:
        supervisor_request('POST', f'/addons/{slug}/restart', {}, timeout=15)
    except (TimeoutError, urllib.error.URLError) as exc:
        log(f'Restart request interrupted ({exc}); verify SSH after reconnecting')


def check_ssh():
    private = STATE / 'ssh_key'
    if not private.is_file():
        raise RuntimeError('SSH private key missing; run --step prepare first')
    command = [
        'ssh', '-i', str(private), '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=accept-new',
        f'{SSH_USER}@{SSH_HOST}', 'echo EM_SSH_OK',
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=25)
    if result.returncode != 0 or 'EM_SSH_OK' not in result.stdout:
        raise RuntimeError('SSH key authentication failed: ' + (result.stderr.strip() or result.stdout.strip()))
    log('SSH key authentication successful')
    log('Next step: run the existing updater after first-run prerequisites are reviewed.')

def require_supported_home_assistant():
    """Require Home Assistant Core 2026.11+ before installation."""
    result = supervisor_request('GET', '/core/info')
    version = str(result.get('version', ''))

    match = re.match(r'^(\d{4})\.(\d+)(?:\.|b|rc|$)', version)
    if not match:
        raise RuntimeError(
            f'Cannot determine Home Assistant Core version: {version!r}'
        )

    if (int(match.group(1)), int(match.group(2))) < (2026, 11):
        raise RuntimeError(
            f'Energy Manager 2.0.0 requires Home Assistant Core '
            f'2026.11 or newer. Installed version: {version}. '
            'Please update Home Assistant before installing Energy Manager.'
        )

    log(f'Home Assistant Core {version} supported')

def preflight_marketplace_consent():
    """Check Marketplace readiness and obtain explicit installer consent."""
    url = (
        f'https://raw.githubusercontent.com/{REPO}/{BRANCH}/'
        'config/scripts/marketplace_manager.py'
    )

    log('Checking Marketplace readiness and consent')

    with urllib.request.urlopen(url, timeout=60) as response:
        source = response.read()

    compile(source, 'marketplace_manager.py', 'exec')

    import tempfile

    with tempfile.TemporaryDirectory(prefix='em-marketplace-') as directory:
        target = Path(directory) / 'marketplace_manager.py'
        target.write_bytes(source)

        run([
            sys.executable,
            str(target),
            '--preflight',
            '--consent',
            '--github-auth',
        ])

    log('Marketplace consent and GitHub authentication confirmed')

def collect_onboarding_credentials():
    """Collect credentials before changing a fresh HA installation.

    Stored only until the first post-reboot setup succeeds; never log values.
    """
    print(
        'Solcast is mandatory for Energy Manager optimisation. Obtain your '
        'Solcast API key and resource ID(s) from the Solcast website.\n'
        'You can copy them and right-click in the SSH terminal to paste '
        '(or use your terminal\'s paste shortcut).\n'
        'If you do not have the details yet, press Enter to skip Solcast '
        'onboarding but you will need to manually configure after installation.',
        flush=True,
    )
    solcast_key = input('Solcast API key (Enter to skip): ').strip()
    resource_1 = ''
    resource_2 = ''
    if solcast_key:
        resource_1 = input('Solcast resource ID 1 (required when using Solcast): ').strip()
        if not resource_1:
            raise RuntimeError('A Solcast resource ID is required when an API key is supplied')
        resource_2 = input('Solcast resource ID 2 (optional, Enter to skip): ').strip()
        if resource_2 and resource_2 == resource_1:
            raise RuntimeError('Solcast resource IDs must be different')
    else:
        log('Solcast onboarding skipped; configure it manually after installation.')
    print('Energy Manager key is strongly recommended. Without it, automated '
          'energy optimisation will not occur. You can get one from https://energymanager.com.au.', flush=True)
    em_key = input('Energy Manager key (Enter to skip): ').strip()
    if not em_key:
        log('WARNING: No Energy Manager key supplied; optimisation will not operate.')
    secrets = {
        'solcast_key': solcast_key,
        'solcast_array_1': resource_1,
        'solcast_array_2': resource_2,
        'energymanager_key': em_key,
    }
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / 'onboarding-secrets.json'
    if path.exists():
        raise RuntimeError('Onboarding secrets already staged; resolve prior installation before retrying')
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(secrets, handle)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    log('Onboarding credentials staged securely for post-reboot setup')


def main():
    parser = argparse.ArgumentParser(description='Energy Manager bootstrap installer (development)')
    parser.add_argument('--step', choices=['all', 'prepare', 'install-apps', 'deploy', 'install-marketplace', 'finalise', 'configure-ssh', 'check-ssh'], default='all', help='Installation stage (default: all); specific stages for troubleshooting')
    args = parser.parse_args()

    require_supported_home_assistant()
    if args.step in ('all', 'install-marketplace'):
        preflight_marketplace(_marketplace_source())
    
    if args.step == 'all':
        preflight_marketplace_consent()
        collect_onboarding_credentials()
    
    if not all(part and part.replace('-', '').replace('_', '').replace('.', '').isalnum() for part in REPO.split('/')) or len(REPO.split('/')) != 2:
        raise ValueError('Invalid repository name')
    if not BRANCH or '/' in BRANCH or '..' in BRANCH:
        raise ValueError('Invalid branch')
    log(f'Repository: {REPO} ({BRANCH})')
    if args.step == 'all':
        log('Starting full Energy Manager installation')
        log('Stage 1/5: Preparation')
        prepare()
        log('Stage 2/5: Supervisor Apps')
        install_apps()
        log('Stage 3/5: Energy Manager deployment')
        deploy()
        log('Stage 4/5: Marketplace components')
        install_marketplace()
        register_post_reboot_hook()
        log('Authorising Energy Manager SSH key for future updates')
        configure_ssh(restart=False)
        log('Stage 5/5: Configuration validation and full OS reboot')
        log('MQTT and Node-RED Companion configuration will complete after reboot.')
        log('MQTT discovery must remain disabled; this installer does not alter it.')
        finalise()
    elif args.step == 'prepare':
        prepare()
    elif args.step == 'install-apps':
        install_apps()
    elif args.step == 'deploy':
        deploy()
    elif args.step == 'install-marketplace':
        install_marketplace()
    elif args.step == 'finalise':
        finalise()
    elif args.step == 'configure-ssh':
        configure_ssh()
    else:
        check_ssh()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'ERROR: {exc}')
        sys.exit(1)
