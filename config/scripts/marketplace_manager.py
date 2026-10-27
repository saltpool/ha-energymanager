#!/usr/bin/env python3
"""Energy Manager Marketplace component management for HA Core 2026.11+.

Runs from the Advanced SSH & Web Terminal App, with SUPERVISOR_TOKEN.
Accepts the Marketplace warning only after explicit terminal consent.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import urllib.request

CORE_MINIMUM = (2026, 11)
INTEGRATIONS = {
    'zachowj/hass-node-red': 'nodered',
    'bremor/bureau_of_meteorology': 'bureau_of_meteorology',
    'bjreplay/ha-solcast-solar': 'solcast_solar',
}
CATEGORIES = {'integration', 'plugin', 'theme', 'template'}

def log_github_rate_limit(stage):
    """Record unauthenticated GitHub API quota during Marketplace operations."""
    try:
        req = urllib.request.Request(
            'https://api.github.com/rate_limit',
            headers={
                'User-Agent': 'EnergyManager-Marketplace-Diagnostic',
                'Accept': 'application/vnd.github+json',
            },
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.load(response)

        core = data['resources']['core']

        print(
            f'[EM GitHub API] {stage}: '
            f'{core["remaining"]}/{core["limit"]} remaining, '
            f'{core["used"]} used, '
            f'reset={core["reset"]}',
            flush=True,
        )
    except Exception as exc:
        print(
            f'[EM GitHub API] {stage}: quota check unavailable: {exc}',
            flush=True,
        )

def require_marketplace():
    """Fail before any installation changes on older Home Assistant Core."""
    token = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
    if not token:
        raise RuntimeError('Supervisor token unavailable; run from Advanced SSH & Web Terminal')
    req = urllib.request.Request('http://supervisor/core/info',
                                 headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.load(response)
    version = str(payload.get('data', {}).get('version', ''))
    match = re.match(r'^(\d{4})\.(\d+)(?:\.|b|rc|$)', version)
    if not match:
        raise RuntimeError('Cannot determine Home Assistant Core version: ' + repr(version))
    current = (int(match.group(1)), int(match.group(2)))
    if current < CORE_MINIMUM:
        raise RuntimeError(
            f'Energy Manager 2.0.0 requires Home Assistant Core 2026.11 or newer '
            f'(installed: {version}). Update Home Assistant first, then rerun Energy Manager.'
        )
    print('[EM Marketplace] Home Assistant Core ' + version + ' meets minimum version', flush=True)
    return version


class HAWebSocket:
    """Minimal authenticated Home Assistant WebSocket client, no third-party deps."""
    def __init__(self):
        token = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
        if not token:
            raise RuntimeError('Supervisor token missing')
        self.sock = socket.create_connection(('supervisor', 80), timeout=20)
        self.sock.settimeout(180)
        try:
            key = base64.b64encode(secrets.token_bytes(16)).decode()
            handshake = ('GET /core/websocket HTTP/1.1\r\nHost: supervisor\r\n'
                         'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                         'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n') % key
            self.sock.sendall(handshake.encode())
            response = bytearray()
            while b'\r\n\r\n' not in response:
                part = self.sock.recv(1)
                if not part or len(response) > 16384:
                    raise ConnectionError('Invalid WebSocket handshake')
                response.extend(part)
            headers = response.decode('latin-1')
            expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if ' 101 ' not in headers.split('\r\n')[0] or ('sec-websocket-accept: ' + expected).lower() not in headers.lower():
                raise ConnectionError('WebSocket upgrade rejected')
            if self.receive().get('type') != 'auth_required':
                raise RuntimeError('Unexpected Home Assistant auth greeting')
            self.send({'type': 'auth', 'access_token': token})
            result = self.receive()
            if result.get('type') != 'auth_ok':
                raise RuntimeError('Home Assistant WebSocket authentication failed: ' + repr(result))
            self.counter = 0
        except Exception:
            self.sock.close()
            raise

    def read(self, count):
        data = bytearray()
        while len(data) < count:
            part = self.sock.recv(count - len(data))
            if not part:
                raise ConnectionError('WebSocket closed')
            data.extend(part)
        return bytes(data)

    def frame(self, opcode, payload):
        mask = secrets.token_bytes(4)
        size = len(payload)
        header = bytes([128 | opcode])
        if size < 126:
            header += bytes([128 | size])
        elif size < 65536:
            header += bytes([254]) + struct.pack('!H', size)
        else:
            header += bytes([255]) + struct.pack('!Q', size)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, value):
        self.frame(1, json.dumps(value).encode())

    def receive(self):
        data = bytearray()
        while True:
            first, second = self.read(2)
            opcode = first & 15
            length = second & 127
            if length == 126:
                length = struct.unpack('!H', self.read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.read(8))[0]
            if length > 16 * 1024 * 1024:
                raise ValueError('Oversized WebSocket response')
            mask = self.read(4) if second & 128 else None
            payload = self.read(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 9:
                self.frame(10, payload)
                continue
            if opcode == 8:
                raise ConnectionError('WebSocket closed by server')
            if opcode not in (0, 1):
                continue
            data.extend(payload)
            if first & 128:
                return json.loads(data.decode())

    def call(self, command, **fields):
        self.counter += 1
        request_id = self.counter
        self.send(dict(type=command, id=request_id, **fields))
        while True:
            message = self.receive()
            if message.get('type') == 'result' and message.get('id') == request_id:
                if not message.get('success'):
                    raise RuntimeError('%s: %s' % (command, message.get('error')))
                return message.get('result')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.sock.close()


def validate_components(entries):
    if not isinstance(entries, list):
        raise ValueError('marketplace_components must be a list')
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError('Invalid Marketplace component entry')
        repo = item.get('repository')
        if not isinstance(repo, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            raise ValueError('Invalid Marketplace repository: ' + repr(repo))
        if repo.lower() in seen:
            raise ValueError('Duplicate Marketplace repository: ' + repo)
        seen.add(repo.lower())
        if item.get('type') not in CATEGORIES or item.get('action') not in ('install', 'remove'):
            raise ValueError('Invalid component category/action: ' + repo)
        if item['action'] == 'install':
            version = item.get('version', 'latest')
            if not isinstance(version, str) or not version or len(version) > 128 or any(c.isspace() for c in version):
                raise ValueError('Invalid Marketplace version: ' + repo)
    return entries


def _remove_legacy_directory(relative_path):
    """Only remove a known legacy HACS resource path when Marketplace lacks it."""
    if not isinstance(relative_path, str):
        raise ValueError('Missing legacy removal path')
    path = Path(relative_path)
    parts = path.parts
    if path.is_absolute() or '..' in parts or len(parts) != 3 or parts[:2] != ('www', 'community'):
        raise ValueError('Unsafe legacy removal path: ' + relative_path)
    target = Path('/config') / path
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError('Unsafe legacy component type: ' + relative_path)
    if target.exists():
        shutil.rmtree(target)
        print('[EM Marketplace] Removed legacy resource directory: ' + relative_path, flush=True)


def check_marketplace(ws, ask_consent=False):
    """Only acknowledge the warning after explicit approval on this session."""
    info = ws.call('marketplace/info')
    if info.get('stage') != 'running':
        raise RuntimeError('Marketplace is not ready (stage: %s)' % info.get('stage'))
    if info.get('warning_accepted'):
        return info

    if not ask_consent:
        raise RuntimeError(
            'Marketplace warning has not been acknowledged for this connection. '
            'Run the interactive installer or marketplace_manager.py --preflight --consent. '
            'Review the actual Marketplace warning at Settings > Marketplace first.'
        )

    print('\n[EM Marketplace] CONSENT REQUIRED', flush=True)
    print('Marketplace installs third-party community software, which is not reviewed or'
          ' supported by Home Assistant. Review the full warning in'
          ' Home Assistant > Settings > Marketplace before continuing.', flush=True)
    print('Your confirmation below will acknowledge the Marketplace warning for the'
          ' identity used by the Energy Manager installer.', flush=True)
    try:
        answer = input('After reviewing the warning, type YES to accept and continue: ')
    except (EOFError, KeyboardInterrupt) as exc:
        raise RuntimeError('Marketplace warning not accepted; installation cancelled') from exc
    if answer != 'YES':
        raise RuntimeError('Marketplace warning not accepted; installation cancelled')

    ws.call('marketplace/warning/accept')
    info = ws.call('marketplace/info')
    if not info.get('warning_accepted'):
        raise RuntimeError('Marketplace did not confirm the acknowledgement; installation stopped')
    print('[EM Marketplace] Warning acknowledgement verified', flush=True)
    return info


def sync_marketplace_components(entries, dry_run=False, repair=False):
    """Reconcile required versions; repair also reinstalls matching versions."""
    validate_components(entries)
    require_marketplace()
    changes = []
    with HAWebSocket() as ws:
        check_marketplace(ws)
        log_github_rate_limit('BEFORE Marketplace repository listing')
        repos = ws.call('marketplace/repositories/list')
        log_github_rate_limit('AFTER Marketplace repository listing')
        lookup = {str(repo.get('full_name', '')).lower(): repo for repo in repos}
        for item in entries:
            name = item['repository']
            category = item['type']
            action = item['action']
            repo = lookup.get(name.lower())
            if repo is None:
                if action == 'remove' and item.get('local_path'):
                    changes.append({'repository': name, 'action': 'remove', 'version': None})
                    if not dry_run:
                        _remove_legacy_directory(item['local_path'])
                    continue
                raise RuntimeError('Marketplace repository not listed: ' + name + '. Check Marketplace catalog or add the custom repository in its UI.')
            if repo.get('category') != category:
                raise RuntimeError('Marketplace category mismatch for %s: found %s' % (name, repo.get('category')))
            identifier = str(repo['id'])
            installed = bool(repo.get('installed'))
            version = item.get('version', 'latest')
            available = repo.get('available_version')
            target = available if version == 'latest' else version
            domain = INTEGRATIONS.get(name.lower())
            files_missing = bool(domain and not (Path('/config/custom_components') / domain / 'manifest.json').is_file())
            if action == 'remove':
                needed = installed
            else:
                # Normal updates correct version drift. Force reinstall additionally
                # repairs components whose installed version already matches.
                needed = (repair or not installed or files_missing or
                          bool(target and repo.get('installed_version') != target))
            if not needed:
                continue
            changes.append({'repository': name, 'action': action, 'version': target})
            if dry_run:
                continue
            log_github_rate_limit(f'BEFORE {action}: {name}')
            if action == 'remove':
                ws.call('marketplace/repository/uninstall', repository=identifier)
            else:
                kwargs = {
                    'repository': identifier,
                    'confirm_replace_built_in': item.get(
                        'confirm_replace_built_in', False
                    ),
                }
                # Use the catalog installation path when the required version
                # matches the catalog's available version. Explicit version
                # selection can require additional GitHub API requests.
                if version != 'latest' and version != available:
                    details = ws.call('marketplace/repository/info', repository_id=identifier)
                    releases = details.get('releases', [])
                    if version not in releases:
                        raise RuntimeError('Marketplace version %s not listed for %s' % (version, name))
                    kwargs['version'] = version
                ws.call('marketplace/repository/install', **kwargs)
            verified = ws.call('marketplace/repository/info', repository_id=identifier)
            log_github_rate_limit(f'AFTER {action}: {name}')
            if action == 'remove' and verified.get('installed'):
                raise RuntimeError('Marketplace removal could not be verified: ' + name)
            if action == 'install':
                if not verified.get('installed'):
                    raise RuntimeError('Marketplace install could not be verified: ' + name)
                if version != 'latest' and verified.get('installed_version') != version:
                    raise RuntimeError('Marketplace installed wrong version: ' + name)
                if domain and not (Path('/config/custom_components') / domain / 'manifest.json').is_file():
                    raise RuntimeError('Marketplace integration files missing: ' + name)
            print('[EM Marketplace] %s: %s' % (action, name), flush=True)
        log_github_rate_limit('AFTER all Marketplace operations')
    return changes

def sync_marketplace_components_via_ssh(entries, dry_run=False, repair=False):
    """Run Marketplace operations in the Advanced SSH App with Supervisor token."""
    import shlex
    import subprocess
    validate_components(entries)
    if not entries:
        return []
    key = '/config/.energy_manager/ssh_key'
    if not os.path.isfile(key):
        raise RuntimeError('Energy Manager SSH key is missing')
    encoded = base64.b64encode(json.dumps({
        'entries': entries, 'dry_run': dry_run, 'repair': repair
    }).encode()).decode()
    program = (
        "import sys,json,base64;sys.path.insert(0,'/config/scripts');"
        "from marketplace_manager import sync_marketplace_components;"
        "data=json.loads(base64.b64decode(sys.argv[1]));"
        "print('__EM_MARKETPLACE_RESULT__'+json.dumps(sync_marketplace_components("
        "data['entries'],dry_run=data['dry_run'],repair=data['repair'])))"
    )
    command = 'bash -lc ' + shlex.quote('python3 -c ' + shlex.quote(program) + ' ' + shlex.quote(encoded))
    result = subprocess.run([
        'ssh', '-i', key, '-o', 'StrictHostKeyChecking=no',
        '-o', 'ConnectTimeout=10', '-o', 'BatchMode=yes',
        '-o', 'PasswordAuthentication=no',
        'hassio@a0d7b954-ssh.local.hass.io', command
    ], capture_output=True, text=True, timeout=600)
    if result.stdout:
        print(result.stdout, end='', flush=True)
    if result.returncode:
        raise RuntimeError('Marketplace SSH reconciliation failed: ' + (
            result.stderr.strip() or result.stdout.strip() or str(result.returncode)))
    marker = '__EM_MARKETPLACE_RESULT__'
    if marker not in result.stdout:
        raise RuntimeError('Marketplace SSH reconciliation returned no result')
    return json.loads(result.stdout.rsplit(marker, 1)[1].splitlines()[0])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--consent', action='store_true',
                        help='Interactively request consent if Marketplace needs acknowledgement')
    parser.add_argument('--manifest')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    require_marketplace()
    with HAWebSocket() as ws:
        info = check_marketplace(ws, ask_consent=args.consent)
        print('[EM Marketplace] Ready; GitHub connected: %s' % info.get('github_connected'), flush=True)
    if args.manifest and not args.preflight:
        with open(args.manifest, encoding='utf-8') as handle:
            manifest = json.load(handle)
        components = manifest.get('marketplace_components', manifest.get('hacs_components', []))
        print(json.dumps(sync_marketplace_components(components, dry_run=args.dry_run), indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('[EM Marketplace] ERROR: ' + str(exc), flush=True)
        raise SystemExit(1)
