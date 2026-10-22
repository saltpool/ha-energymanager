#!/usr/bin/env python3
"""Energy Manager bootstrap installer (development).

Run in Advanced SSH & Web Terminal on dedicated Home Assistant OS.
"""
import argparse
import importlib.util
import json
import urllib.error
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

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
    parser.add_argument('--step', choices=['prepare', 'configure-ssh', 'check-ssh'], default='prepare')
    args = parser.parse_args()
    if not all(part and part.replace('-', '').replace('_', '').replace('.', '').isalnum() for part in REPO.split('/')) or len(REPO.split('/')) != 2:
        raise ValueError('Invalid repository name')
    if not BRANCH or '/' in BRANCH or '..' in BRANCH:
        raise ValueError('Invalid branch')
    log(f'Repository: {REPO} ({BRANCH})')
    if args.step == 'prepare':
        prepare()
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
