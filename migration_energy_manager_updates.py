#!/usr/bin/env python3
"""Manually install the GitHub updater scripts."""
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPOSITORY = 'ha-energymanager/ha-energymanager'
BRANCH = 'main'
FILES = (
    'scripts/update_checker.py',
    'scripts/check_energy_manager_updates.py',
    'scripts/perform_energy_manager_update.py',
)
CONFIG = Path('/config')
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')


def request_bytes(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'EnergyManager-Migration'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def repository_bytes(sha, path):
    url = (f'https://raw.githubusercontent.com/{REPOSITORY}/' + sha + '/' +
           urllib.parse.quote(path, safe='/'))
    data = request_bytes(url)
    if not data:
        raise ValueError(f'Empty GitHub file: {path}')
    return data


def get_release():
    data = json.loads(request_bytes(f'https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}'))
    sha = data.get('sha', '')
    if not re.fullmatch(r'[a-fA-F0-9]{40}', sha):
        raise ValueError('Invalid GitHub commit SHA')
    latest = repository_bytes(sha, 'latest.txt').decode('utf-8').strip()
    manifest = json.loads(repository_bytes(sha, 'manifest/manifest.json'))
    if not VERSION_RE.fullmatch(latest) or tuple(map(int, latest.split('.'))) < (1, 3, 0):
        raise ValueError('GitHub 1.3.0 release is not ready')
    if manifest.get('version') != latest:
        raise ValueError('GitHub manifest does not match latest.txt')
    for path in FILES:
        if path not in manifest.get('files', {}):
            raise ValueError(f'GitHub manifest does not include {path}')
    return sha


def migrate():
    sha = get_release()
    em_dir = CONFIG / '.energy_manager'
    scripts_dir = CONFIG / 'scripts'
    scripts_dir.mkdir(parents=True, exist_ok=True)
    version_file = em_dir / 'version.txt'
    current_version = version_file.read_text(encoding='utf-8').strip()
    if not VERSION_RE.fullmatch(current_version):
        raise ValueError('Installed version.txt is missing or invalid')

    # Download and validate everything before touching installed scripts.
    payloads = {}
    for path in FILES:
        content = repository_bytes(sha, 'config/' + path)
        compile(content.decode('utf-8'), path, 'exec')
        payloads[path] = content

    backup = em_dir / 'backups' / ('github_updater_migration_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    backup.mkdir(parents=True, exist_ok=False)
    previous = {}
    prepared = {}
    try:
        for path, content in payloads.items():
            target = scripts_dir / Path(path).name
            previous[target] = target.exists()
            if target.exists():
                shutil.copy2(target, backup / target.name)
            fd, temp_name = tempfile.mkstemp(prefix='.em-migrate-', dir=scripts_dir)
            with os.fdopen(fd, 'wb') as file:
                file.write(content)
            os.chmod(temp_name, 0o755)
            prepared[target] = Path(temp_name)
        if version_file.exists():
            shutil.copy2(version_file, backup / 'version.txt')
        for target, temp in prepared.items():
            os.replace(temp, target)
        print(f'GitHub updater installed from {REPOSITORY}@{sha[:12]}.')
        print(f'Installed version: {version_file.read_text(encoding="utf-8").strip()}.')
        print(f'Next update check will query GitHub; backup: {backup}.')
    except Exception:
        for target, existed in previous.items():
            saved = backup / target.name
            if existed and saved.exists():
                shutil.copy2(saved, target)
            elif not existed and target.exists():
                target.unlink()
        saved_version = backup / 'version.txt'
        if saved_version.exists():
            shutil.copy2(saved_version, version_file)
        raise
    finally:
        for temp in prepared.values():
            if temp.exists():
                temp.unlink()


def main():
    if len(sys.argv) != 1:
        print('Usage: python3 migrate_energy_manager_updates.py', file=sys.stderr)
        return 2
    try:
        migrate()
    except Exception as error:
        print(f'Update migration failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
