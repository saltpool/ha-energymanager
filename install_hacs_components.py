#!/usr/bin/env python3
"""Energy Manager second-stage installer, after HACS onboarding.

Run from Advanced SSH & Web Terminal after HACS has been added as a Home
Assistant integration and authenticated with GitHub.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPOSITORY = os.environ.get('EM_UPDATE_REPOSITORY', 'saltpool/ha-energymanager')
BRANCH = os.environ.get('EM_UPDATE_BRANCH', 'development')
SCRIPTS = Path('/config/scripts')


def log(message):
    print(f'[EM HACS] {message}', flush=True)


def main():
    parser = argparse.ArgumentParser(description='Install Energy Manager HACS components after GitHub authorisation')
    parser.add_argument('--repository', default=REPOSITORY)
    parser.add_argument('--branch', default=BRANCH)
    args = parser.parse_args()

    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        raise RuntimeError('Invalid GitHub repository')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.branch):
        raise RuntimeError('Invalid GitHub branch')
    if not (os.environ.get('SUPERVISOR_TOKEN')):
        raise RuntimeError('Run this from Advanced SSH & Web Terminal with Supervisor access')
    if not Path('/config/custom_components/hacs/manifest.json').is_file():
        raise RuntimeError('HACS files are missing. Run install.py --step install-hacs first.')
    if not (SCRIPTS / 'hacs_manager.py').is_file():
        raise RuntimeError('Energy Manager HACS manager is missing. Run install.py --step prepare first.')

    sys.path.insert(0, str(SCRIPTS))
    from hacs_manager import sync_hacs_components, validate_components

    url = f'https://raw.githubusercontent.com/{args.repository}/{args.branch}/manifest/manifest.json'
    log(f'Reading manifest: {args.repository} ({args.branch})')
    with urllib.request.urlopen(url, timeout=60) as response:
        manifest = json.load(response)
    entries = validate_components(manifest.get('hacs_components', []))
    if not entries:
        log('No HACS components requested in the manifest')
        return

    log(f'Checking HACS authorisation and {len(entries)} component entries')
    try:
        changes = sync_hacs_components(entries)
    except Exception as exc:
        details = str(exc)
        if any(marker in details.lower() for marker in ('hacs is not running', 'hacs/info', 'unknown_command', 'not_found', 'websocket auth')):
            raise RuntimeError('HACS does not appear to be fully set up. In Home Assistant, add the HACS integration and complete GitHub authorisation, then rerun this script. Details: ' + details) from exc
        raise
    for change in changes:
        log(f"{change['action']}: {change['repository']} ({change.get('version') or 'n/a'})")
    log(f'Completed: {len(changes)} changes. Manifest contains {len(entries)} entries.')
    log('Restart Home Assistant Core after component installation to load new custom integrations.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'ERROR: {exc}')
        sys.exit(1)
