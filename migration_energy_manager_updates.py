#!/usr/bin/env python3
"""Install the GitHub updater and migrate the 35 historical UI helpers to YAML."""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPOSITORY = 'saltpool/ha-energymanager'
BRANCH = 'development'
FILES = (
    'scripts/update_checker.py',
    'scripts/check_energy_manager_updates.py',
    'scripts/perform_energy_manager_update.py',
    'scripts/hacs_manager.py',
    'scripts/em_apps_manager.py',
    'integrations/em_helpers.yaml',
)
CONFIG = Path('/config')
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')
STANDARD = {
    'input_select': ('inverter_brand', 'electricity_provider'),
    'input_text': ('amber_api_key', 'amber_site', 'localvolts_key',
                   'localvolts_partner_id', 'nmi', 'energymanager_key',
                   'em_api_version', 'timezone', 'solcast_key',
                   'solcast_array_1', 'solcast_array_2'),
    'input_number': ('inverter_import_limit', 'solar_array_size',
                     'inverter_export_limit', 'bad_weather_rain_today',
                     'bad_weather_rain_tomorrow'),
    'input_boolean': ('demand_period_enabled', 'enable_exclusion_period',
                      'high_sell_price_toggle'),
    'input_datetime': ('battery_install_date', 'demand_start', 'demand_end',
                       'exclusion_start_time', 'exclusion_end_time'),
}
STANDARD_IDS = {f'{domain}.{key}' for domain, keys in STANDARD.items() for key in keys}
TEMPLATE_IDS = {f'number.battery_{n}a' for n in range(2, 7)} | {
    'number.battery_high_sell_mode_usable', 'sensor.grid_buy_price',
    'sensor.grid_sell_price', 'sensor.bom_last_updated',
}


def request_bytes(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'EnergyManager-Migration'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def repository_bytes(sha, path):
    url = (f'https://raw.githubusercontent.com/{REPOSITORY}/{sha}/' +
           urllib.parse.quote(path, safe='/'))
    data = request_bytes(url)
    if not data:
        raise ValueError(f'Empty GitHub file: {path}')
    return data


def get_release():
    data = json.loads(request_bytes(
        f'https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}'))
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


def cli(*args):
    result = subprocess.run(['ha', *args], capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f'HA command failed: ha {" ".join(args)}; check HA/Supervisor logs')
    return result.stdout


def ensure_stopped():
    cli('core', 'stop')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.em-migrate-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def validate_helpers(content):
    text = content.decode('utf-8')
    for domain, keys in STANDARD.items():
        matches = list(re.finditer(r'^' + re.escape(domain) + r':\s*$', text, re.M))
        if len(matches) != 1:
            raise ValueError(f'Expanded helpers must contain one {domain} section')
        start = matches[0].end()
        end = re.search(r'^\S[^\n]*:', text[start:], re.M)
        section = text[start:start + end.start()] if end else text[start:]
        for key in keys:
            match = re.search(r'^  ' + re.escape(key) + r':\s*$', section, re.M)
            if not match:
                raise ValueError(f'Expanded GitHub helpers missing {domain}.{key}; upload new YAML first')
            tail = section[match.end():]
            next_key = re.search(r'^  [^ #\n][^\n]*:', tail, re.M)
            block = tail[:next_key.start()] if next_key else tail
            if re.search(r'^    initial:', block, re.M):
                raise ValueError(f'{domain}.{key} must not have initial: (it would override saved state)')
    for entity_id in TEMPLATE_IDS:
        if not re.search(r'^\s+default_entity_id:\s*[\'\"]?' + re.escape(entity_id) +
                         r'[\'\"]?\s*$', text, re.M):
            raise ValueError(f'Expanded GitHub helpers missing {entity_id}')


def plan_storage(storage):
    registry_path = storage / 'core.entity_registry'
    registry = read_json(registry_path)
    entities = registry['data']['entities']
    if not isinstance(entities, list):
        raise ValueError('Unrecognised entity registry format')
    edits = {}
    removed = set()
    migrated = set()
    for domain, keys in STANDARD.items():
        path = storage / domain
        if not path.exists():
            continue
        document = read_json(path)
        items = document['data']['items']
        if not isinstance(items, list):
            raise ValueError(f'Unrecognised {domain} storage format')
        ids = {f'{domain}.{key}' for key in keys}
        entries = [e for e in entities if e['entity_id'] in ids and e.get('platform') == domain]
        for entry in entries:
            item_matches = [item for item in items if item.get('id') == entry.get('unique_id')]
            if len(item_matches) > 1:
                raise ValueError(f'Ambiguous stored helper: {entry["entity_id"]}')
            if item_matches:
                if entry.get('config_entry_id'):
                    raise ValueError(f'Unexpected config entry for {entry["entity_id"]}')
                items.remove(item_matches[0])
                removed.add(entry['entity_id'])
                migrated.add(entry['entity_id'])
        for key in keys:
            leftovers = [item for item in items if item.get('id') == key]
            if leftovers:
                raise ValueError(f'Unmapped UI helper {domain}.{key}; inspect registry before retrying')
        if any(e['entity_id'] in removed for e in entries):
            edits[path] = document

    config_path = storage / 'core.config_entries'
    configs = read_json(config_path) if config_path.exists() else None
    template_entries = [e for e in entities if e['entity_id'] in TEMPLATE_IDS
                        and e.get('platform') == 'template' and e.get('config_entry_id')]
    remove_config_ids = {e['config_entry_id'] for e in template_entries}
    for entry_id in remove_config_ids:
        linked = [e for e in entities if e.get('config_entry_id') == entry_id]
        if any(e['entity_id'] not in TEMPLATE_IDS for e in linked):
            raise ValueError('A historical template config entry also owns unrelated entities; refusing removal')
        matches = [e for e in configs['data']['entries'] if e['entry_id'] == entry_id] if configs else []
        if len(matches) != 1 or matches[0]['domain'] != 'template':
            raise ValueError('Unrecognised historical template config entry')
        configs['data']['entries'].remove(matches[0])
        removed.update(e['entity_id'] for e in linked)
        migrated.update(e['entity_id'] for e in linked)
    if remove_config_ids:
        edits[config_path] = configs

    registry['data']['entities'] = [e for e in entities if e['entity_id'] not in removed]
    if 'deleted_entities' in registry['data']:
        registry['data']['deleted_entities'] = [e for e in registry['data']['deleted_entities']
            if e.get('entity_id') not in removed and e.get('config_entry_id') not in remove_config_ids]
    if removed:
        edits[registry_path] = registry

    restore_path = storage / 'core.restore_state'
    restored = read_json(restore_path) if restore_path.exists() else None
    saved_states = {}
    if restored is not None:
        if not isinstance(restored.get('data'), list):
            raise ValueError('Unrecognised restore state format')
        for item in restored['data']:
            entity_id = item.get('state', {}).get('entity_id')
            if entity_id in STANDARD_IDS:
                saved_states[entity_id] = copy.deepcopy(item)
            if entity_id in removed:
                item['entity_registry_id'] = None
        for entity_id in migrated & STANDARD_IDS:
            state = saved_states.get(entity_id, {}).get('state', {}).get('state')
            if state is None or state in ('unknown', 'unavailable'):
                raise ValueError(f'No valid saved state for {entity_id}; no migration has been written')
        if removed:
            edits[restore_path] = restored
    elif migrated & STANDARD_IDS:
        raise ValueError('Missing restore state file; refusing to lose helper values')
    return edits, migrated, saved_states


def restore_backup(backup):
    journal = read_json(backup / 'transaction.json')
    for item in journal['files']:
        target = CONFIG / item['relative']
        if CONFIG.resolve() not in target.resolve().parents:
            raise ValueError('Invalid rollback path')
        if item['existed']:
            atomic_write(target, (backup / item['relative']).read_bytes(), item['mode'])
        elif target.exists():
            target.unlink()


def migrate():
    if not shutil.which('ha'):
        raise RuntimeError('Run this from the HA OS SSH add-on; the ha CLI is required')
    em_dir = CONFIG / '.energy_manager'
    pending = em_dir / 'helper_migration_pending.json'
    if pending.exists():
        backup = read_json(pending)['backup']
        raise RuntimeError(f'Interrupted migration: run python3 {Path(__file__).name} --rollback {backup}')
    current_version = (em_dir / 'version.txt').read_text(encoding='utf-8').strip()
    if not VERSION_RE.fullmatch(current_version):
        raise ValueError('Installed version.txt is missing or invalid')
    config_text = (CONFIG / 'configuration.yaml').read_text(encoding='utf-8')
    if not re.search(r'packages:\s*!include_dir_named\s+[\'\"]?integrations/?[\'\"]?(?:\s|$)', config_text):
        raise ValueError('Expected homeassistant packages: !include_dir_named integrations in configuration.yaml')
    sha = get_release()
    payloads = {path: repository_bytes(sha, 'config/' + path) for path in FILES}
    for path, content in payloads.items():
        if path.endswith('.py'):
            compile(content.decode('utf-8'), path, 'exec')
    validate_helpers(payloads['integrations/em_helpers.yaml'])
    cli('core', 'check')
    print(f'Downloads validated from {BRANCH}@{sha[:12]}. Stopping Home Assistant Core...', flush=True)
    was_started = True
    stopped = False
    backup = None
    written = False
    try:
        ensure_stopped()
        stopped = True
        edits, migrated, saved_states = plan_storage(CONFIG / '.storage')
        contents = {CONFIG / path: content for path, content in payloads.items()}
        contents.update({path: encode_json(document) for path, document in edits.items()})
        backup = em_dir / 'backups' / ('github_updater_migration_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        backup.mkdir(parents=True, mode=0o700)
        os.chmod(backup, 0o700)
        journal = {'branch': BRANCH, 'sha': sha, 'files': []}
        for target in contents:
            relative = str(target.relative_to(CONFIG))
            existed = target.exists()
            mode = (target.stat().st_mode & 0o777) if existed else (0o755 if target.suffix == '.py' else 0o600)
            journal['files'].append({'relative': relative, 'existed': existed, 'mode': mode})
            if existed:
                saved = backup / relative
                saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                saved.write_bytes(target.read_bytes())
                os.chmod(saved, 0o600)
        for relative in ('configuration.yaml', '.energy_manager/version.txt'):
            target = CONFIG / relative
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            saved.write_bytes(target.read_bytes())
            os.chmod(saved, 0o600)
        atomic_write(backup / 'helper_states.json', encode_json(saved_states))
        atomic_write(backup / 'transaction.json', encode_json(journal))
        atomic_write(pending, encode_json({'backup': str(backup)}))
        written = True
        for item in journal['files']:
            target = CONFIG / item['relative']
            mode = 0o755 if target.suffix == '.py' else item['mode']
            if target.name in ('em_helpers.yaml', 'core.restore_state'):
                mode = 0o600
            atomic_write(target, contents[target], mode)
        cli('core', 'check')
        print(f'Migrated {len(migrated)} UI helpers to YAML. Configuration check passed. Starting Core...', flush=True)
        cli('core', 'start')
        stopped = False
        pending.unlink()
        atomic_write(backup / 'completed.json', encode_json({'migrated': sorted(migrated)}))
        print(f'GitHub updater and expanded helpers installed from {REPOSITORY}@{sha[:12]}.')
        print(f'Installed version remains at {current_version}; please perform a normal update to check for a new version.')
        print(f'Backup location: {backup}')
        print('Verify helper IDs/values and dashboards after Core has finished starting.')
    except BaseException:
        if written:
            try:
                ensure_stopped()
                restore_backup(backup)
                if was_started:
                    cli('core', 'start')
                pending.unlink(missing_ok=True)
                print('Migration rolled back to its original files.', file=sys.stderr)
            except BaseException:
                print(f'Automatic rollback incomplete. Recovery: python3 {Path(__file__).name} --rollback {backup}', file=sys.stderr)
        elif stopped and was_started:
            cli('core', 'start')
        raise


def main():
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--rollback':
            backup = Path(sys.argv[2]).resolve()
            ensure_stopped()
            restore_backup(backup)
            cli('core', 'check')
            cli('core', 'start')
            (CONFIG / '.energy_manager/helper_migration_pending.json').unlink(missing_ok=True)
            print('Backup restored and Home Assistant Core started.')
        elif len(sys.argv) == 1:
            migrate()
        else:
            print(f'Usage: python3 {Path(__file__).name} [--rollback BACKUP_DIRECTORY]', file=sys.stderr)
            return 2
    except (Exception, KeyboardInterrupt) as error:
        print(f'Update migration failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
