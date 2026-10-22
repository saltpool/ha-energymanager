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
import urllib.error
from datetime import datetime
from pathlib import Path

REPOSITORY = os.environ.get('EM_UPDATE_REPOSITORY', 'saltpool/ha-energymanager')
BRANCH = os.environ.get('EM_UPDATE_BRANCH', 'development')
SCRIPTS = Path('/config/scripts')


def log(message):
    print(f'[EM HACS] {message}', flush=True)


# Verify the actual integration directories, not only HACS metadata.
# These paths are defined by the upstream integration repositories.
REQUIRED_INTEGRATIONS = {
    'zachowj/hass-node-red': 'nodered',
    'bremor/bureau_of_meteorology': 'bureau_of_meteorology',
    'BJReplay/ha-solcast-solar': 'solcast_solar',
}


def repair_missing_integrations(entries, ws_class):
    """Ask HACS to download again if its metadata says installed but files are absent."""
    wanted = {entry['repository'].lower() for entry in entries
              if entry.get('action') == 'install'}
    required = {repo: domain for repo, domain in REQUIRED_INTEGRATIONS.items()
                if repo.lower() in wanted}
    missing = {
        repo: domain for repo, domain in required.items()
        if not (Path('/config/custom_components') / domain / 'manifest.json').is_file()
    }
    if missing:
        log('Missing integration files: ' + ', '.join(missing.values()))
        with ws_class() as ws:
            info = ws.call('hacs/info')
            if info.get('stage') != 'running':
                raise RuntimeError('HACS is not running; complete GitHub authorisation first')
            repos = ws.call('hacs/repositories/list')
            lookup = {str(item.get('full_name', '')).lower(): item for item in repos}
            for repo, domain in missing.items():
                item = lookup.get(repo.lower())
                if not item:
                    raise RuntimeError(f'HACS does not list {repo}; cannot download {domain}')
                if item.get('category') != 'integration':
                    raise RuntimeError(f'Unexpected HACS category for {repo}')
                log(f'Re-downloading {repo} because custom_components/{domain} is missing')
                ws.call('hacs/repository/download', repository=str(item['id']))

    still_missing = [
        f'{repo} -> /config/custom_components/{domain}/manifest.json'
        for repo, domain in required.items()
        if not (Path('/config/custom_components') / domain / 'manifest.json').is_file()
    ]
    if still_missing:
        raise RuntimeError('HACS download did not install required files: ' + '; '.join(still_missing))
    for repo, domain in required.items():
        log(f'Verified on disk: {repo} -> custom_components/{domain}')


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
    from hacs_manager import HAWebSocket, sync_hacs_components, validate_components

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
    # HACS can report a repository as installed even when its component directory
    # is absent. Never accept that as a successful fresh installation.
    repair_missing_integrations(entries, HAWebSocket)

    for change in changes:
        log(f"{change['action']}: {change['repository']} ({change.get('version') or 'n/a'})")
    log(f'Completed: {len(changes)} changes. Manifest contains {len(entries)} entries.')
    log('All HACS component operations completed successfully.')
    log('The full Home Assistant OS will now reboot to load custom integrations.')
    log('The terminal will disconnect; this is expected. Finish integration setup after reboot.')
    token = os.environ['SUPERVISOR_TOKEN']
    request = urllib.request.Request(
        'http://supervisor/host/reboot',
        data=b'{}', method='POST',
        headers={'Authorization': 'Bearer ' + token,
                 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.load(response)
            if payload.get('result') == 'error':
                raise RuntimeError('Supervisor rejected host reboot: ' + str(payload.get('message')))
    except urllib.error.HTTPError as exc:
        raise RuntimeError('Supervisor refused host reboot: HTTP ' + str(exc.code)) from exc
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        log('Reboot request connection interrupted; Home Assistant may already be rebooting: ' + str(exc))
        return
    log('Home Assistant OS reboot requested successfully.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log(f'ERROR: {exc}')
        sys.exit(1)
