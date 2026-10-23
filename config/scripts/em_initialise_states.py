#!/usr/bin/env python3
"""Set initial Energy Manager helper values once, after Home Assistant starts.

Run during first-install post-HACS onboarding only. Never call from routine
updates or Force Reinstall. Calculated sensors are intentionally excluded.
"""
import csv
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

CSV_FILE = Path('/config/em_initial_states.csv')
MARKER = Path('/config/.energy_manager/initial-states-complete.json')
TOKEN = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
ROOT = 'http://supervisor/core/api/'
SUPPORTED = {'input_boolean', 'input_datetime', 'input_number', 'input_select', 'input_text'}


def log(message):
    print('[EM Initial States] ' + message, flush=True)


def call(method, endpoint, data=None):
    body = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(ROOT + endpoint, data=body, method=method,
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        content = response.read()
    return json.loads(content) if content else None


def main():
    if MARKER.is_file():
        log('Initial states already applied; no changes made')
        return
    if not TOKEN:
        raise RuntimeError('Supervisor token missing')
    if not CSV_FILE.is_file():
        raise RuntimeError('Missing initial state file: ' + str(CSV_FILE))

    current = {item['entity_id']: item for item in call('GET', 'states')}
    applied = 0
    missing = []
    errors = []
    seen = set()
    with CSV_FILE.open(newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            entity_id = row['entity_id'].strip()
            value = row['state'].strip()
            if entity_id in seen:
                errors.append(f'{entity_id}: duplicate CSV entry')
                continue
            seen.add(entity_id)
            if '.' not in entity_id or entity_id.split('.', 1)[0] not in SUPPORTED:
                continue
            if not value or value.lower() in ('unavailable', 'unknown'):
                continue
            if entity_id not in current:
                missing.append(entity_id)
                continue
            domain = entity_id.split('.', 1)[0]
            try:
                if domain == 'input_boolean':
                    if value not in ('on', 'off'):
                        raise ValueError('expected on/off')
                    service, data = ('turn_on' if value == 'on' else 'turn_off'), {'entity_id': entity_id}
                elif domain == 'input_number':
                    number = float(value)
                    attributes = current[entity_id].get('attributes', {})
                    minimum, maximum = attributes.get('min'), attributes.get('max')
                    if (minimum is not None and number < float(minimum)) or (maximum is not None and number > float(maximum)):
                        raise ValueError(f'{number} outside helper range [{minimum}, {maximum}]')
                    service, data = 'set_value', {'entity_id': entity_id, 'value': number}
                elif domain == 'input_select':
                    options = current[entity_id].get('attributes', {}).get('options', [])
                    if value not in options:
                        raise ValueError(f'option not available: {value!r}')
                    service, data = 'select_option', {'entity_id': entity_id, 'option': value}
                elif domain == 'input_datetime':
                    field = 'datetime' if ' ' in value else ('date' if '-' in value else 'time')
                    service, data = 'set_datetime', {'entity_id': entity_id, field: value}
                else:
                    service, data = 'set_value', {'entity_id': entity_id, 'value': value}
                call('POST', 'services/' + domain + '/' + service, data)
                applied += 1
            except (ValueError, TypeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
                errors.append(f'{entity_id}: {exc}')

    log(f'Initialised {applied} editable helpers; {len(missing)} absent; {len(errors)} errors')
    for item in missing:
        log('Not present: ' + item)
    for item in errors:
        log('ERROR: ' + item)
    if errors:
        raise RuntimeError(f'{len(errors)} helper initialisation errors; see log')
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    temp = MARKER.with_suffix('.tmp')
    temp.write_text(json.dumps({'status': 'complete', 'applied': applied,
                                'absent': missing}, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, MARKER)
    log('One-time initialisation complete; future runs will preserve states')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('ERROR: ' + str(exc))
        sys.exit(1)
