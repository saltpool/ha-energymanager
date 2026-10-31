#!/usr/bin/env python3
"""Refresh Energy Manager updater code before any local updater imports."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request

REPOSITORY = os.environ.get('EM_UPDATE_REPOSITORY', 'saltpool/ha-energymanager')
BRANCHES = ('main', 'early', 'test', 'development')
SCRIPTS_DIR = Path('/config/scripts')

# Files required by the check and update entry points.
# All are retrieved from the same pinned commit.
CHECK_FILES = ('update_checker.py', 'marketplace_manager.py',
               'check_energy_manager_updates.py', 'em_updater_bootstrap.py')
UPDATE_FILES = CHECK_FILES + ('perform_energy_manager_update.py',
                              'file_merger.py', 'em_update_launcher.py')


def _read(url):
    req = urllib.request.Request(
        url, headers={'User-Agent': 'EnergyManager-Bootstrap'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def resolve_branch(branch=None):
    if branch is None:
        token = os.environ.get('SUPERVISOR_TOKEN', '')
        if not token:
            raise RuntimeError('SUPERVISOR_TOKEN unavailable; specify --branch')
        req = urllib.request.Request(
            'http://supervisor/core/api/states/input_select.em_update_branch',
            headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req, timeout=30) as response:
            branch = json.load(response).get('state')
    branch = str(branch or '').strip().lower()
    if branch not in BRANCHES:
        raise ValueError(f'Invalid update branch: {branch!r}')
    return branch


def refresh_updater(branch, mode='check'):
    branch = resolve_branch(branch)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', REPOSITORY):
        raise ValueError('Invalid updater repository')

    info = json.loads(_read(
        f'https://api.github.com/repos/{REPOSITORY}/commits/{branch}'))
    sha = info.get('sha', '')
    if not re.fullmatch(r'[a-fA-F0-9]{40}', sha):
        raise ValueError('Invalid GitHub commit SHA')

    names = CHECK_FILES if mode == 'check' else UPDATE_FILES
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    staged = {}
    try:
        for name in names:
            url = (f'https://raw.githubusercontent.com/{REPOSITORY}/{sha}/'
                   f'config/scripts/{urllib.parse.quote(name)}')
            payload = _read(url)
            if not payload:
                raise ValueError(f'Empty updater script: {name}')

            # Refuse syntax-invalid downloads.
            compile(payload, name, 'exec')
            fd, path = tempfile.mkstemp(
                prefix='.em-bootstrap-', dir=str(SCRIPTS_DIR))
            staged[name] = path
            with os.fdopen(fd, 'wb') as handle:
                handle.write(payload)
            os.chmod(path, 0o644)

        # Only modify installed files after every download was verified.
        for name, path in staged.items():
            os.replace(path, SCRIPTS_DIR / name)

        print(
            f'Updater scripts refreshed from {branch} ({sha[:12]})',
            flush=True)
    finally:
        for path in staged.values():
            if os.path.exists(path):
                os.unlink(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', required=True, choices=BRANCHES)
    parser.add_argument('--mode', choices=('check', 'update'), default='check')
    options = parser.parse_args()
    refresh_updater(options.branch, options.mode)
