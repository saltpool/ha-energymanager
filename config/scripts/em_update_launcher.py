#!/usr/bin/env python3
"""Launch Energy Manager updates inside Advanced SSH & Web Terminal.

Home Assistant shell_command must not wait for the update or OS reboot.
The updater itself writes update_result.txt and handles the reboot.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys

STATE = Path('/config/.energy_manager')
KEY = STATE / 'ssh_key'
RESULT = STATE / 'update_result.txt'
TARGET = 'hassio@a0d7b954-ssh.local.hass.io'
BRANCHES = ('main', 'early', 'test', 'development')


def set_result(value):
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = RESULT.with_name('update_result.txt.launching')
    tmp.write_text(value + '\n', encoding='utf-8')
    os.replace(tmp, RESULT)


def main():
    parser = argparse.ArgumentParser(description='Launch Energy Manager updater in SSH App')
    parser.add_argument('--branch', required=True, choices=BRANCHES)
    parser.add_argument('--force-reinstall', action='store_true')
    args = parser.parse_args()
    if not KEY.is_file():
        raise RuntimeError('Missing Energy Manager SSH key; cannot launch updater')

    updater = '/config/scripts/perform_energy_manager_update.py'
    invocation = f'python3 -u {shlex.quote(updater)} --branch {shlex.quote(args.branch)}'
    if args.force_reinstall:
        invocation += ' --force-reinstall'

    # nohup, redirected standard streams and background execution let the SSH
    # call return before the update finishes or restarts Home Assistant OS.
    log = '/config/.energy_manager/update-run.log'
    remote = (
        f'if test -f {shlex.quote(updater)}; then '
        f'nohup {invocation} > {shlex.quote(log)} 2>&1 < /dev/null & '
        'echo EM_UPDATE_LAUNCHED; else echo MISSING_UPDATER >&2; exit 1; fi'
    )
    command = [
        'ssh', '-n', '-i', str(KEY),
        '-o', 'BatchMode=yes',
        '-o', 'ConnectTimeout=10',
        '-o', 'StrictHostKeyChecking=accept-new',
        TARGET, remote,
    ]
    set_result('running')
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=25)
        if result.returncode != 0 or 'EM_UPDATE_LAUNCHED' not in result.stdout:
            raise RuntimeError('SSH launch failed: ' + (result.stderr.strip() or result.stdout.strip() or f'exit {result.returncode}'))
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        set_result('error:Failed to launch updater through SSH App: ' + str(exc))
        raise
    print('Energy Manager updater launched in SSH App; awaiting result or OS reboot', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('[EM Update Launcher] ERROR: ' + str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
