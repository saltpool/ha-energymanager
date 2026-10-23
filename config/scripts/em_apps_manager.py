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

    repository_url = REPOSITORIES[prefix]
    repositories = request('GET', '/store/repositories')

    for repo in repositories:
        if repo.get('slug') == prefix or repo.get('source', '').rstrip('/') == repository_url.rstrip('/'):
            return

    print(f'[EM Apps] Adding missing repository: {repository_url}', flush=True)
    request('POST', '/store/repositories', {'repository': repository_url}, timeout=60)
    print(f'[EM Apps] Repository added: {repository_url}', flush=True)

def wait_for(slug, predicate, seconds=360):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        current = info(slug)
        if current and predicate(current):
            return current
        time.sleep(3)
    raise RuntimeError(f'{slug}: timed out waiting for Supervisor')


def ensure_key_for_new_ssh():
    pub = Path(str(KEY) + '.pub')
    if KEY.exists() and pub.exists():
        return pub.read_text(encoding='utf-8').strip()
    if KEY.exists() or pub.exists():
        raise RuntimeError('SSH key pair incomplete: refusing to replace either key')
    KEY.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ssh-keygen', '-t', 'ed25519', '-f', str(KEY), '-N', '',
                    '-C', 'energy_manager_automation'], check=True)
    return pub.read_text(encoding='utf-8').strip()

def reconcile_nodered_dependencies(manifest):
    """Repair required Node-RED npm dependencies without replacing user files."""
    required = manifest.get('nodered_dependencies', {})
    if not required:
        return

    root = Path('/addon_configs/a0d7b954_nodered')
    package_file = root / 'package.json'
    modules = root / 'node_modules'

    if not root.is_dir():
        raise RuntimeError(f'Node-RED configuration directory missing: {root}')

    if package_file.exists():
        package = json.loads(package_file.read_text(encoding='utf-8'))
    else:
        package = {
            'name': 'node-red-project',
            'version': '0.0.1',
            'private': True,
            'dependencies': {}
        }

    dependencies = package.setdefault('dependencies', {})
    declaration_changes = {}
    missing_or_wrong = {}

    for name, version in required.items():
        if not isinstance(version, str) or not version:
            raise ValueError(f'Invalid Node-RED version for {name}')
        if not name.startswith('node-red-contrib-') or '/' in name:
            raise ValueError(f'Invalid Node-RED package name: {name}')

        installed_file = modules / name / 'package.json'
        installed = None

        if installed_file.exists():
            try:
                installed = json.loads(
                    installed_file.read_text(encoding='utf-8')
                ).get('version')
            except (OSError, ValueError):
                pass

        if dependencies.get(name) != version:
            declaration_changes[name] = version
        if installed != version:
            missing_or_wrong[name] = (installed, version)

    if not declaration_changes and not missing_or_wrong:
        print('[EM Apps] Node-RED npm dependencies verified', flush=True)
        return

    if declaration_changes:
        dependencies.update(declaration_changes)

        if package_file.exists():
            backup = root / 'package.json.em-backup'
            backup.write_bytes(package_file.read_bytes())

        temporary = root / 'package.json.em-tmp'
        try:
            temporary.write_text(
                json.dumps(package, indent=2) + '\n',
                encoding='utf-8'
            )
            os.replace(temporary, package_file)
        finally:
            temporary.unlink(missing_ok=True)

        print(
            f'[EM Apps] Node-RED dependency declarations repaired: '
            f'{list(declaration_changes)}',
            flush=True
        )

    print(
        f'[EM Apps] Restarting Node-RED to reconcile npm dependencies: '
        f'{list(missing_or_wrong)}',
        flush=True
    )

    try:
        request(
            'POST', '/addons/a0d7b954_nodered/restart',
            {}, timeout=60
        )
    except urllib.error.HTTPError:
        raise
    except (TimeoutError, urllib.error.URLError) as exc:
        print(
            f'[EM Apps] Node-RED restart request incomplete ({exc}); '
            'checking installed packages...',
            flush=True
        )

    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        remaining = {}
        for name, version in required.items():
            installed_file = modules / name / 'package.json'
            try:
                installed = json.loads(
                    installed_file.read_text(encoding='utf-8')
                ).get('version')
            except (OSError, ValueError):
                installed = None
            if installed != version:
                remaining[name] = installed

        if not remaining:
            wait_for(
                'a0d7b954_nodered',
                lambda state: state.get('state') == 'started',
                seconds=180
            )
            print('[EM Apps] Node-RED npm dependencies repaired', flush=True)
            return

        time.sleep(5)

    raise RuntimeError(
        f'Node-RED npm dependency repair timed out: {remaining}'
    )


def reconcile(manifest, repair=False):
    errors = []
    for app in manifest.get('apps', []):
        slug = app['slug']
        try:
            target_version = str(app.get('version', 'latest')).strip()
            if not target_version:
                raise ValueError('App version must not be empty')
            current = info(slug)
            newly_installed = not current or not current.get('version')
            if newly_installed:
                print(f'[EM Apps] Installing missing {slug}', flush=True)
                prefix = slug.split('_', 1)[0]
                ensure_repository(prefix)
                
                if target_version != 'latest':
                    available = request('GET', f'/store/addons/{slug}')
                    available_version = (
                        available.get('version')
                        or available.get('version_latest')
                    )
                    if available_version != target_version:
                        raise RuntimeError(
                            f'Requires version {target_version}, but '
                            f'Supervisor offers {available_version or "unknown"}. '
                            f'Exact-version installation is not supported.'
                        )
               
                try:
                    request('POST', f'/store/addons/{slug}/install', {}, timeout=15)              
                except TimeoutError:
                    pass
                current = wait_for(slug, lambda state: bool(state.get('version')))

            installed_version = current.get('version')

            if target_version != 'latest':
                if installed_version != target_version:
                    raise RuntimeError(
                        f'Version mismatch: installed {installed_version}, '
                        f'required {target_version}. Supervisor does not '
                        f'support installing arbitrary historical versions.'
                    )
                print(
                    f'[EM Apps] {slug}: pinned version '
                    f'{target_version} verified',
                    flush=True
                )
            else:
                latest_version = current.get('version_latest')
                if latest_version and installed_version != latest_version:
                    print(
                        f'[EM Apps] {slug}: updating '
                        f'{installed_version} -> {latest_version}',
                        flush=True
                    )
                    try:
                        request(
                            'POST',
                            f'/store/addons/{slug}/update',
                            {},
                            timeout=60
                        )
                    except (TimeoutError, urllib.error.URLError):
                        print(
                            f'[EM Apps] {slug}: update request did not '
                            f'complete; verifying version...',
                            flush=True
                        )
                    current = wait_for(
                        slug,
                        lambda state: state.get('version') == latest_version,
                        seconds=360
                    )
                    print(
                        f'[EM Apps] {slug}: updated to {latest_version}',
                        flush=True
                    )          

            existing_options = dict(current.get('options') or {})
            desired = dict(app.get('options') or {})

            if slug == 'a0d7b954_ssh':
                desired.pop('ssh', None)
                if newly_installed and not current.get('options', {}).get('ssh', {}).get('authorized_keys'):
                    ssh = dict(existing_options.get('ssh') or {})
                    pub = ensure_key_for_new_ssh()
                    ssh['authorized_keys'] = [pub]
                    desired['ssh'] = ssh

            changed_options = {key: value for key, value in desired.items()
                               if existing_options.get(key) != value}
            settings = {'boot': app.get('boot', 'auto'),
                        'watchdog': app.get('watchdog', True),
                        'auto_update': app.get('auto_update', False)}
.
            if 'ingress_panel' in app:
                if not isinstance(app['ingress_panel'], bool):
                    raise ValueError(
                        f'{slug}: ingress_panel must be true or false'
                    )
                if app['ingress_panel'] and not current.get('ingress'):
                    raise ValueError(
                        f'{slug}: cannot enable sidebar for an App without ingress'
                    )
                settings['ingress_panel'] = app['ingress_panel']

            changed_settings = {key: value for key, value in settings.items()
                                if current.get(key) != value}

            if (newly_installed or repair) and (changed_options or changed_settings):
                print(f'[EM Apps] Configuring {slug}: '
                      f'{list(changed_options)} + {list(changed_settings)}', flush=True)
            payload = dict(changed_settings)
            
            if changed_options:
                payload['options'] = {**existing_options, **changed_options}
            
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
                try:
                    request('POST', f'/addons/{slug}/start', {}, timeout=60)
                except (TimeoutError, urllib.error.URLError) as exc:
                    print(
                        f'[EM Apps] {slug}: startup request did not complete '
                        f'({exc}); verifying startup...',
                        flush=True
                    )
            if newly_installed or repair:
                wait_for(slug, lambda state: state.get('state') == 'started', seconds=180)
            print(f'[EM Apps] {slug}: checked', flush=True)
        except Exception as exc:
            errors.append(f'{slug}: {exc}')
            print(f'[EM Apps] ERROR {errors[-1]}', flush=True)

    if not any(
        error.startswith('a0d7b954_nodered:')
        for error in errors
    ):
        try:
            reconcile_nodered_dependencies(manifest)
        except Exception as exc:
            errors.append(f'Node-RED npm dependencies: {exc}')
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
