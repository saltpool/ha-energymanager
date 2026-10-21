#!/usr/bin/env python3
"""Reconcile Energy Manager Supervisor Apps. No application data or credentials replaced."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

SUPERVISOR = 'http://supervisor'
TOKEN = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
KEY = Path('/config/.energy_manager/ssh_key')
REPOSITORIES = {
    'a0d7b954': 'https://github.com/hassio-addons/repository',
    '1bd4a9fb': 'https://github.com/VictoriaMetrics-Community/homeassistant-addon-victoriametrics',
}


def request(method, path, data=None, timeout=30):
    if not TOKEN:
        raise RuntimeError('SUPERVISOR_TOKEN/HASSIO_TOKEN not available')
    body = None if data is None else json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        SUPERVISOR + path, data=body, method=method,
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read()
        result = json.loads(content) if content else {}
        if isinstance(result, dict) and result.get('result') == 'error':
            raise RuntimeError(f'{path}: {result.get("message", "Supervisor error")}')
        return result.get('data', result) if isinstance(result, dict) else result


def info(slug):
    try:
        return request('GET', f'/addons/{slug}/info')
    except urllib.error.HTTPError as error:
        if error.code in (400, 404):
            return None
        raise


def ensure_repository(prefix):
    if prefix not in REPOSITORIES:
        return
    try:
        request('POST', '/store/repositories', {'repository': REPOSITORIES[prefix]})
    except urllib.error.HTTPError as error:
        if error.code != 400:
            raise
    request('POST', '/store/reload', {})


def wait_for(slug, predicate, seconds=360):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = info(slug)
        if current and predicate(current):
            return current
        time.sleep(3)
    raise RuntimeError(f'{slug}: timed out waiting for Supervisor')


def ensure_key_for_new_ssh():
    """Only generate on an installation with no private/public key."""
    pub = Path(str(KEY) + '.pub')
    if KEY.exists() and pub.exists():
        return pub.read_text(encoding='utf-8').strip()
    if KEY.exists() or pub.exists():
        raise RuntimeError('SSH key pair incomplete: refusing to replace either key')
    KEY.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ssh-keygen', '-t', 'ed25519', '-f', str(KEY), '-N', '',
                    '-C', 'energy_manager_automation'], check=True)
    return pub.read_text(encoding='utf-8').strip()


def reconcile(manifest, repair=False):
    errors = []
    for app in manifest.get('apps', []):
        slug = app['slug']
        try:
            current = info(slug)
            newly_installed = not current or not current.get('version')
            if newly_installed:
                print(f'[EM Apps] Installing missing {slug}', flush=True)
                prefix = slug.split('_', 1)[0]
                ensure_repository(prefix)
        try:
            request('POST', f'/store/addons/{slug}/install', {}, timeout=15)
        
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            print(
                f'[EM Apps] Install failed: HTTP {e.code}\n'
                f'[EM Apps] Supervisor response: {body}',
                flush=True
            )
            raise
        
        except TimeoutError:
            pass
                current = wait_for(slug, lambda state: bool(state.get('version')))

            existing_options = dict(current.get('options') or {})
            desired = dict(app.get('options') or {})

            if slug == 'a0d7b954_ssh':
                desired.pop('ssh', None)
                if newly_installed and not current.get('options', {}).get('ssh', {}).get('authorized_keys'):
                    ssh = dict(existing_options.get('ssh') or {})
                    pub = ensure_key_for_new_ssh()
                    ssh['authorized_keys'] = [pub]
                    # Retain the App's existing username/password and all other SSH settings.
                    desired['ssh'] = ssh

            changed_options = {key: value for key, value in desired.items()
                               if existing_options.get(key) != value}
            settings = {'boot': app.get('boot', 'auto'),
                        'watchdog': app.get('watchdog', True),
                        'auto_update': app.get('auto_update', False)}

            changed_settings = {key: value for key, value in settings.items()
                                if current.get(key) != value}

            if (newly_installed or repair) and (changed_options or changed_settings):
                print(f'[EM Apps] Configuring {slug}: '
                      f'{list(changed_options)} + {list(changed_settings)}', flush=True)
            payload = {**changed_options, **changed_settings}
            
            try:
                request(
                    'POST',
                    f'/addons/{slug}/options',
                    payload,
                    timeout=60
                )
            except (TimeoutError, urllib.error.URLError) as exc:
                print(
                    f'[EM Apps] {slug}: configuration request timed out '
                    f'or failed ({exc}); checking actual state...',
                    flush=True
                )
            
            def settings_applied(state):
                actual_options = state.get('options') or {}
            
                return (
                    all(
                        actual_options.get(key) == value
                        for key, value in changed_options.items()
                    )
                    and all(
                        state.get(key) == value
                        for key, value in changed_settings.items()
                    )
                )
            
            wait_for(slug, settings_applied, seconds=90)
            
            print(
                f'[EM Apps] {slug}: configuration verified',
                flush=True
            )
            
            if changed_options and current.get('state') == 'started':
                request('POST', f'/addons/{slug}/restart', {}, timeout=15)
            elif repair:
                print(f'[EM Apps] {slug}: configured correctly', flush=True)

            current = info(slug)
            if (newly_installed or repair) and current and current.get('state') != 'started':
                request('POST', f'/addons/{slug}/start', {}, timeout=15)
            if newly_installed or repair:
                wait_for(slug, lambda state: state.get('state') == 'started', seconds=180)
            print(f'[EM Apps] {slug}: checked', flush=True)
        except Exception as exc:
            errors.append(f'{slug}: {exc}')
            print(f'[EM Apps] ERROR {errors[-1]}', flush=True)
    if errors:
        raise RuntimeError('; '.join(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    with open(args.manifest, encoding='utf-8') as handle:
        reconcile(json.load(handle), repair=args.repair)


if __name__ == '__main__':
    main()
