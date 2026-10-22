#!/usr/bin/env python3
"""Energy Manager bootstrap installer (development).

Run in Advanced SSH & Web Terminal on dedicated Home Assistant OS.
"""
import argparse
import importlib.util
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
    log('SSH public key (add to Advanced SSH & Web Terminal authorized_keys):')
    print(public.read_text(encoding='utf-8').strip())
    log('Preparation complete. Next: configure SSH authorized_keys, then run --step check-ssh.')


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
    parser.add_argument('--step', choices=['prepare', 'check-ssh'], default='prepare')
    args = parser.parse_args()
    if not all(part and part.replace('-', '').replace('_', '').replace('.', '').isalnum() for part in REPO.split('/')) or len(REPO.split('/')) != 2:
        raise ValueError('Invalid repository name')
    if not BRANCH or '/' in BRANCH or '..' in BRANCH:
        raise ValueError('Invalid branch')
    log(f'Repository: {REPO} ({BRANCH})')
    if args.step == 'prepare':
        prepare()
    else:
        check_ssh()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'ERROR: {exc}')
        sys.exit(1)
