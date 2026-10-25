#!/usr/bin/env python3
"""One-shot post-reboot Energy Manager integration configuration.

Started by Advanced SSH & Web Terminal init_commands after HACS reboot.
Only runs when explicitly armed by install_hacs_components.py.
"""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

STATE = Path('/config/.energy_manager')
STATUS = STATE / 'post-hacs-status.json'
LOCK = STATE / 'post-hacs.lock'
SCRIPT = Path('/config/scripts/configure_em_integrations.py')
INITIALISE_SCRIPT = Path('/config/scripts/em_initialise_states.py')

def write_status(status, detail=''):
    previous = {}
    if STATUS.is_file():
        try:
            previous = json.loads(STATUS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    payload = {'status': status, 'detail': detail,
               'updated_at': datetime.now(timezone.utc).isoformat()}
    if previous.get('kind'):
        payload['kind'] = previous['kind']

    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, STATUS)


def notify_update_complete(token):
    """Notify Home Assistant after successful post-update checks."""
    import re

    result_file = STATE / 'update_result.txt'
    if not result_file.is_file():
        raise RuntimeError('Missing update result; cannot confirm completed version')

    result = result_file.read_text(encoding='utf-8').strip()
    if not result.startswith('success:'):
        raise RuntimeError(
            'Update result does not indicate success: ' + result
        )

    version = result.split(':', 1)[1]
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('Invalid completed update version: ' + repr(version))

    dismiss_request = urllib.request.Request(
        'http://supervisor/core/api/services/persistent_notification/dismiss',
        data=json.dumps({
            'notification_id': 'em_updating'
        }).encode('utf-8'),
        method='POST',
        headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        }
    )

    try:
        with urllib.request.urlopen(dismiss_request, timeout=20):
            pass
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(
            f'[EM Post-HACS] Could not dismiss progress notification: {exc}',
            flush=True
        )

       'title': '✅ Energy Manager Update Complete',
        'message': (
            f'Energy Manager has successfully updated to version {version}. '
            'Home Assistant has restarted and the post-update '
           'integration checks have completed successfully.'
        ),
       'notification_id': 'em_update_complete'
    }

    request = urllib.request.Request(
        'http://supervisor/core/api/services/persistent_notification/create',
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        }
    )

    for attempt in range(1, 7):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status not in (200, 201):
                    raise RuntimeError(
                        f'Notification service returned HTTP {response.status}'
                    )
            print(
                f'[EM Post-HACS] Update completion notification sent: {version}',
                flush=True
            )
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == 6:
                raise RuntimeError(
                    f'Unable to send completion notification: {exc}'
                ) from exc
            time.sleep(10)


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        if not STATUS.is_file():
            return
        try:
            current = json.loads(STATUS.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if current.get('status') not in ('pending', 'running'):
            return
        update_mode = current.get('kind') == 'update'
        if not SCRIPT.is_file():
            write_status('failed', 'Missing /config/scripts/configure_em_integrations.py')
            return
        token = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
        if not token:
            write_status('failed', 'Supervisor token unavailable in SSH App startup')
            return
        print('[EM Post-HACS] Waiting for Home Assistant Core to become available', flush=True)
        write_status('running', 'Waiting for Core')
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            req = urllib.request.Request('http://supervisor/core/api/',
                headers={'Authorization': 'Bearer ' + token})
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(10)
        else:
            write_status('failed', 'Home Assistant Core did not become available within 10 minutes')
            return
        print('[EM Post-HACS] Configuring MQTT and Node-RED Companion', flush=True)
        for attempt in range(1, 4):
            proc = subprocess.run([sys.executable, '-u', str(SCRIPT)],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, timeout=180)
            print(proc.stdout, flush=True)
            if proc.returncode == 0:
                if update_mode:
                    print(
                        '[EM Post-HACS] Post-update checks passed; '
                        'sending completion notification',
                        flush=True
                    )
                    notify_update_complete(token)
                    write_status(
                        'complete',
                        'Post-update integration reconciliation complete; '
                        'completion notification sent'
                    )
                    print(
                        '[EM Post-HACS] Post-update checks completed successfully',
                        flush=True
                    )
                    return

                if not INITIALISE_SCRIPT.is_file():
                    write_status(
                        'failed',
                        'Missing /config/scripts/em_initialise_states.py'
                    )
                    return

                print(
                    '[EM Post-HACS] Applying initial Energy Manager helper states',
                    flush=True
                )
                initialisation = subprocess.run(
                    [sys.executable, '-u', str(INITIALISE_SCRIPT)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=300
                )
                print(initialisation.stdout, flush=True)
                if initialisation.returncode != 0:
                    write_status(
                        'failed',
                        'Initial helper configuration failed; see post-hacs.log'
                    )
                    return

                write_status('complete', 'MQTT discovery OFF; Node-RED Companion configured')
                print('[EM Post-HACS] Completed successfully', flush=True)
                return
            if attempt < 3:
                print(f'[EM Post-HACS] Attempt {attempt} failed; retrying', flush=True)
                time.sleep(20)
        write_status('failed', 'Integration configuration failed after 3 attempts; see post-hacs.log')
        print('[EM Post-HACS] Failed; see /config/.energy_manager/post-hacs.log', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        write_status('failed', str(exc))
        print(f'[EM Post-HACS] ERROR: {exc}', flush=True)
        sys.exit(1)
