#!/usr/bin/env python3
"""Energy Manager bootstrap installer (development).

Run in Advanced SSH & Web Terminal on dedicated Home Assistant OS.
Rerunnable: never overwrites existing SSH key material or version tracking.
"""
import argparse
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

REPO = os.environ.get('EM_UPDATE_REPOSITORY', 'saltpool/ha-energymanager')
BRANCH = os.environ.get('EM_UPDATE_BRANCH', 'development')
ROOT = Path('/config')
STATE = ROOT / '.energy_manager'
SCRIPTS = ROOT / 'scripts'
REQUIRED = (
    'update_checker.py',
    'file_merger.py',
    'hacs_manager.py',
    'em_apps_manager.py',
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
    log('Preparation complete. Next: run --step configure-ssh.')



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
    """Install/configure required Apps from the fork manifest, without SSH."""
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
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read().decode('utf-8')


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
    """Initialise HA's pre-existing files that have no Energy Manager markers.

    Normal managed-section upgrades still use EnergyManagerFileMerger; this
    fallback is only for first-time installation on an unmodified HA instance.
    """
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
    elif name == 'automations.yaml':
        # HA's default empty list is often [] or an empty file.
        active = [line.strip() for line in original.splitlines()
                  if line.strip() and not line.lstrip().startswith('#')]
        if active and active != ['[]']:
            # Existing user automations should not be silently discarded.
            if not all(line.startswith('- ') or line.startswith(' ') for line in
                       original.splitlines() if line.strip() and not line.lstrip().startswith('#')):
                raise RuntimeError('Existing automations.yaml cannot be safely merged on first install')
            result = downloaded.rstrip() + '\n\n' + original.strip() + '\n'
        else:
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
    """Append missing Modbus values only, keeping all existing secrets intact."""
    path = ROOT / 'secrets.yaml'
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    values = (
        ('modbus_host_ip', '"REPLACE_WITH_INVERTER_IP"  # Set during inverter onboarding; no default'),
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


def _merge_flows(old_content, new_content):
    # Same EnergyManager- tab selection and referenced-subflow semantics
    # as _merge_energy_manager_tabs in perform_energy_manager_update.py.
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
    log(f'Flow merge: replaced {len(old_tabs)} EM tabs with {len(new_tabs)} EM tabs')
    return json.dumps(retained, separators=(',', ':'))


def deploy():
    """Use existing manifest and file merger; no SSH or SSH App restarts."""
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
    with urllib.request.urlopen(url, timeout=60) as response:
        manifest = json.load(response)
    if not isinstance(manifest.get('files'), dict):
        raise RuntimeError('Invalid manifest files map')
    # Download and validate all file content before changing any installed files.
    downloads = {}
    for name, entry in manifest['files'].items():
        path = safe_repo_path(name)
        if not isinstance(entry, dict) or entry.get('action', 'merge') not in ('merge', 'replace', 'create'):
            raise ValueError(f'Invalid manifest file entry: {name}')
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
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = downloads[name]
            if action == 'replace':
                result = merger.replace_file(str(destination), content, manifest['version'])
            elif action == 'create':
                result = True if destination.exists() else merger.replace_file(str(destination), content, manifest['version'])
            else:
                result = merger.update_file(str(destination), content, info.get('sections', []), manifest['version'])
            if not result:
                raise RuntimeError('File merger returned failure')
        except Exception as exc:
            errors.append(f'{name}: {exc}')
            log(f'ERROR: {errors[-1]}')
    if errors:
        raise RuntimeError('Manifest deployment incomplete: ' + '; '.join(errors))
    # Vanilla Home Assistant already contains these files but no EM markers.
    # The normal merger only replaces existing marked sections, so initialise
    # them explicitly on first install and leave subsequent upgrades unchanged.
    for base_name in ('configuration.yaml', 'automations.yaml'):
        if base_name not in downloads:
            raise RuntimeError(f'Manifest missing required {base_name}')
        _install_base_yaml(base_name, downloads[base_name])
    _ensure_modbus_secrets()
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

    # Resource entries follow the existing updater's structure and matching-by-URL.
    resources = manifest.get('lovelace_resources') or []
    if resources:
        if not isinstance(resources, list):
            raise RuntimeError('Unexpected Lovelace resource manifest format')
        resource_path = ROOT / '.storage/lovelace_resources'
        if resource_path.is_file():
            data = json.loads(resource_path.read_text(encoding='utf-8'))
        else:
            data = {'version': 1, 'minor_version': 1,
                    'key': 'lovelace_resources', 'data': {'items': []}}
        items = data.setdefault('data', {}).setdefault('items', [])
        changed = False
        for entry in resources:
            resource_url = entry['url']
            resource_type = entry.get('type', 'module')
            existing = next((item for item in items if item.get('url') == resource_url), None)
            if existing is None:
                items.append({'id': uuid.uuid4().hex, 'url': resource_url,
                              'type': resource_type})
                changed = True
                log(f'Added Lovelace resource: {resource_url}')
            elif existing.get('type') != resource_type:
                existing['type'] = resource_type
                changed = True
                log(f'Updated Lovelace resource: {resource_url}')
        if changed:
            _backup_file(resource_path, 'lovelace_resources.json')
            _write_atomic(resource_path, json.dumps(data, indent=2))
            log('Lovelace resources registered locally (Home Assistant may need a restart to reload them)')
        else:
            log('Lovelace resources already registered')

    log('Deployment stage complete: files, Node-RED flows, Lovelace resources')
    log('Inverter-specific configuration, HACS and Home Assistant reload remain separate installation stages')



def core_request(method, endpoint, payload=None, timeout=45):
    """Call Home Assistant's authenticated REST API through Supervisor."""
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


def install_hacs():
    """Install HACS files; GitHub authorisation is completed after reboot."""
    destination = ROOT / 'custom_components' / 'hacs'
    manifest_file = destination / 'manifest.json'
    if manifest_file.is_file():
        try:
            metadata = json.loads(manifest_file.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f'Existing HACS installation needs attention: {exc}') from exc
        if metadata.get('domain') != 'hacs':
            raise RuntimeError('Existing custom_components/hacs is not a valid HACS integration')
        log('HACS files already installed; leaving the existing installation unchanged')
        log('GitHub authorisation will be completed through Home Assistant after reboot')
        return
    if destination.exists():
        raise RuntimeError('HACS destination exists but is incomplete; refusing to overwrite it')

    # Download the official release, not a fork or a copy bundled with Energy Manager.
    url = 'https://github.com/hacs/integration/releases/latest/download/hacs.zip'
    log('Downloading official HACS release')
    request = urllib.request.Request(url, headers={'User-Agent': 'EnergyManagerBootstrap/1.0'})
    with urllib.request.urlopen(request, timeout=120) as response:
        archive = response.read(50 * 1024 * 1024 + 1)
    if len(archive) > 50 * 1024 * 1024:
        raise RuntimeError('HACS download exceeds expected size limit')

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    staged = parent / ('.hacs-em-install-' + uuid.uuid4().hex)
    staged.mkdir()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for member in z.infolist():
                # Reject absolute paths, traversal and symlinks in third-party archives.
                name = member.filename
                parts = Path(name).parts
                mode = (member.external_attr >> 16) & 0o170000
                if not name or name.startswith('/') or '..' in parts or mode == 0o120000:
                    raise RuntimeError(f'Unsafe HACS archive member: {name!r}')
                resolved = (staged / name).resolve()
                if not resolved.is_relative_to(staged.resolve()):
                    raise RuntimeError(f'Unsafe HACS archive path: {name!r}')
            z.extractall(staged)
        candidate = staged / 'manifest.json'
        if not candidate.is_file() or json.loads(candidate.read_text(encoding='utf-8')).get('domain') != 'hacs':
            raise RuntimeError('Downloaded archive is not a valid HACS integration')
        if destination.exists():
            raise RuntimeError('HACS was installed concurrently; refusing to replace it')
        staged.rename(destination)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    log('HACS integration files installed successfully')
    log('After the final reboot: Settings > Devices & services > Add integration > HACS')
    log('Complete GitHub authorisation during onboarding; no GitHub credentials are required here')


def finalise():
    """Validate Home Assistant and request a full Home Assistant OS reboot."""
    if not (ROOT / 'configuration.yaml').is_file():
        raise RuntimeError('Home Assistant configuration missing; run --step deploy first')
    if not (Path('/addon_configs/a0d7b954_nodered') / 'flows.json').is_file():
        raise RuntimeError('Node-RED flows missing; run --step deploy first')

    if not (ROOT / 'custom_components/hacs/manifest.json').is_file():
        raise RuntimeError('HACS integration files missing; run --step install-hacs first')

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

    # Write a durable status *before* rebooting, since this Python process
    # and its terminal are expected to be terminated by the host reboot.
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
    log('After Home Assistant is back, continue onboarding: HACS, inverter, Solcast, electricity provider and Energy Manager keys.')
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


def configure_ssh():
    """Authorise the existing key, retaining all SSH App options and credentials."""
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


def main():
    parser = argparse.ArgumentParser(description='Energy Manager bootstrap installer (development)')
    parser.add_argument('--step', choices=['prepare', 'install-apps', 'deploy', 'install-hacs', 'finalise', 'configure-ssh', 'check-ssh'], default='prepare')
    args = parser.parse_args()
    if not all(part and part.replace('-', '').replace('_', '').replace('.', '').isalnum() for part in REPO.split('/')) or len(REPO.split('/')) != 2:
        raise ValueError('Invalid repository name')
    if not BRANCH or '/' in BRANCH or '..' in BRANCH:
        raise ValueError('Invalid branch')
    log(f'Repository: {REPO} ({BRANCH})')
    if args.step == 'prepare':
        prepare()
    elif args.step == 'install-apps':
        install_apps()
    elif args.step == 'deploy':
        deploy()
    elif args.step == 'install-hacs':
        install_hacs()
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
