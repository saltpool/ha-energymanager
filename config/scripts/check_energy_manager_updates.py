#!/usr/bin/env python3
"""
Check for Energy Manager Updates v1.3.0 - Github branch update checker
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, '/config/scripts')
from em_updater_bootstrap import refresh_updater, resolve_branch

EM_DIR = '/config/.energy_manager'


def write_outputs(status, version, changelog='', branch='main', error='', restart_required=False):
    os.makedirs(EM_DIR, exist_ok=True)
    with open(os.path.join(EM_DIR, 'update_status.txt'), 'w', encoding='utf-8') as file:
        file.write(status)
    with open(os.path.join(EM_DIR, 'update_details.json'), 'w', encoding='utf-8') as file:
        json.dump({'status': status, 'version': version, 'branch': branch,
                   'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'changelog': changelog, 'restart_required': restart_required, 'error': error}, file, indent=2)
    with open(os.path.join(EM_DIR, 'current_version.txt'), 'w', encoding='utf-8') as file:
        file.write(version or '')
    with open(os.path.join(EM_DIR, 'changelog.md'), 'w', encoding='utf-8') as file:
        file.write(changelog)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', choices=('main', 'early', 'test', 'development'), help='Override HA branch selector')
    parser.add_argument('--key', default='', help=argparse.SUPPRESS)  # Legacy shell command compatibility.
    args = parser.parse_args()
    selected_branch = args.branch or 'unknown'
    try:
        selected_branch = resolve_branch(args.branch)
        refresh_updater(selected_branch, mode='check')
        # Import only after refreshing the checker and its dependencies.
        from update_checker import EnergyManagerUpdateChecker

        checker = EnergyManagerUpdateChecker(branch=selected_branch)
        selected_branch = checker.branch
        result = checker.check_for_updates()
        if result['error']:
            raise RuntimeError(result['error'])
        if result['update_available']:
            manifest = result['manifest']
            notes = next((manifest[key] for key in ('changelog', 'release_notes', 'notes', 'description')
        if isinstance(manifest.get(key), str)), '')
            write_outputs(
                'update_available',
                result['remote_version'],
                notes,
                checker.branch,
                restart_required=bool(manifest.get('restart_required', True))
            )
            print(f"Update available on {checker.branch}: {result['current_version']} -> {result['remote_version']}")
            return 1
        else:       
            write_outputs('no_updates', result['current_version'], branch=checker.branch)
            print(f"No updates available on {checker.branch}")
        return 0
    except Exception as exc:
        write_outputs('error', '', branch=selected_branch, error=str(exc))
        print(f'Update check failed: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
