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

    # Run through the SSH App login shell to obtain its Supervisor token.
    # Execute as root so the updater can manage /config, /share and Apps.
    # Keep the detached process alive after the SSH connection closes.
    log = '/config/.energy_manager/update-run.log'

    privileged_command = (
        f'nohup {invocation} > {shlex.quote(log)} '
        '2>&1 < /dev/null &'
    )

    remote_script = (
        'set -e; '
        'TOKEN="${SUPERVISOR_TOKEN:-${HASSIO_TOKEN:-}}"; '
        'test -n "$TOKEN" || { echo MISSING_SUPERVISOR_TOKEN >&2; exit 1; }; '
        f'test -f {shlex.quote(updater)} || '
        '{ echo MISSING_UPDATER >&2; exit 1; }; '
        'sudo -n env SUPERVISOR_TOKEN="$TOKEN" '
        f'bash -c {shlex.quote(privileged_command)}; '
        f'sudo -n test -f {shlex.quote(log)} || '
        '{ echo UPDATE_LOG_NOT_CREATED >&2; exit 1; }; '
        'echo EM_UPDATE_LAUNCHED'  
    )
    remote = 'bash -lc ' + shlex.quote(remote_script)
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
