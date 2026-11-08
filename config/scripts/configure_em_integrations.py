#!/usr/bin/env python3
"""Set up MQTT, Node-RED Companion, BOM and Solcast following the Marketplace reboot.

Fresh-install Solcast configuration: API limit 10; automatic updates OFF.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SECRETS_FILE = Path('/config/.energy_manager/onboarding-secrets.json')
API = 'http://supervisor/core/api/config/config_entries'
TOKEN = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')

NODERED_ENTITY_IDS = {
    'sensor.electricity_provider_buy_price': 'sensor.nodered_buyprice',
    'sensor.electricity_provider_demand_interval': 'sensor.demand_interval',
    'sensor.electricity_provider_em_last_updated': 'sensor.em_last_updated',
    'sensor.electricity_provider_end_time': 'sensor.end_time',
    'sensor.electricity_provider_forecast': 'sensor.nodered_forecast',
    'sensor.electricity_provider_last_updated': 'sensor.nodered_energyproviderupdate',
    'sensor.electricity_provider_sell_price': 'sensor.nodered_sellprice',
    'sensor.electricity_provider_solcast_last_updated': 'sensor.solcast_last_updated',
    'sensor.electricity_provider_start_time': 'sensor.start_time',
}

def log(message):
    print('[EM Integrations] ' + message, flush=True)


def request(method, path, data=None):
    if not TOKEN:
        raise RuntimeError('Supervisor token missing; use Advanced SSH & Web Terminal')
    body = None if data is None else json.dumps(data).encode('utf-8')
    req = urllib.request.Request(
        API + path, data=body, method=method,
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'Home Assistant HTTP {exc.code} {path}: {detail[:600]}') from exc


def entries(domain):
    result = request('GET', '/entry')
    if not isinstance(result, list):
        raise RuntimeError('Unexpected config entry listing')
    return [item for item in result if item.get('domain') == domain
            and item.get('source') != 'ignore']


def start_flow(domain):
    return request('POST', '/flow', {'handler': domain})


def submit_flow(flow, data):
    flow_id = flow.get('flow_id')
    if not flow_id:
        raise RuntimeError('Home Assistant returned a flow without flow_id: ' + repr(flow)[:700])
    return request('POST', '/flow/' + flow_id, data)


def configure_node_red():
    if entries('nodered'):
        log('Node-RED Companion already configured; existing entry preserved')
        return
    if not Path('/config/custom_components/nodered/manifest.json').is_file():
        raise RuntimeError('Node-RED Companion files absent; run Marketplace component installer and reboot first')
    flow = start_flow('nodered')
    log('Node-RED flow: ' + str(flow.get('type')) + ' / ' + str(flow.get('step_id')))
    if flow.get('type') == 'form' and flow.get('step_id') == 'user':
        flow = submit_flow(flow, {})
    if flow.get('type') != 'create_entry' or not entries('nodered'):
        raise RuntimeError('Node-RED Companion configuration unsuccessful: ' + json.dumps(flow)[:900])
    log('Node-RED Companion configuration entry created')

def correct_nodered_entity_ids():
    from marketplace_manager import HAWebSocket

    entry_ids = {
        entry['entry_id']
        for entry in entries('nodered')
        if entry.get('entry_id')
    }
    if not entry_ids:
        raise RuntimeError('Node-RED Companion has no configuration entry')

    remaining = dict(NODERED_ENTITY_IDS)
    renamed = 0

    for attempt in range(12):
        with HAWebSocket() as ws:
            registry = ws.call('config/entity_registry/list')
            by_id = {
                entity['entity_id']: entity
                for entity in registry
            }

            for old_id, new_id in list(remaining.items()):
                old = by_id.get(old_id)
                new = by_id.get(new_id)

                if old is None:
                    if new is not None:
                        if new.get('config_entry_id') not in entry_ids:
                            raise RuntimeError(
                                f'Entity ID conflict: {new_id} belongs '
                                'to another integration'
                            )
                        log(f'Entity already correct: {new_id}')
                        del remaining[old_id]
                        continue
                
                    candidates = [
                        entity for entity in registry
                        if entity.get('config_entry_id') in entry_ids
                        and re.fullmatch(
                            re.escape(new_id) + r'_[0-9]+',
                            entity.get('entity_id', '')
                        )
                    ]
                
                    if len(candidates) > 1:
                        raise RuntimeError(
                            f'Multiple possible Node-RED entities for {new_id}: '
                            + ', '.join(e['entity_id'] for e in candidates)
                        )
                
                    if len(candidates) == 1:
                        renamed_id = candidates[0]['entity_id']
                
                        ws.call(
                            'config/entity_registry/update',
                            entity_id=renamed_id,
                            new_entity_id=new_id
                        )
                
                        log(f'Repaired Node-RED entity: {renamed_id} -> {new_id}')
                        renamed += 1
                        del remaining[old_id]
                
                    continue

                if old.get('config_entry_id') not in entry_ids:
                    raise RuntimeError(
                        f'Refusing to rename non-Node-RED entity: {old_id}'
                    )

                if new is not None:
                    raise RuntimeError(
                        f'Cannot rename {old_id}: {new_id} already exists'
                    )

                ws.call(
                    'config/entity_registry/update',
                    entity_id=old_id,
                    new_entity_id=new_id
                )
                log(f'Renamed entity: {old_id} -> {new_id}')
                renamed += 1
                del remaining[old_id]

            if not remaining:
                break

        if attempt < 11:
            time.sleep(10)

    if remaining:
        log(
            'WARNING: Node-RED entities not yet registered: '
            + ', '.join(remaining)
        )

    log(
        f'Node-RED entity tidy-up complete: '
        f'{renamed} renamed, '
        f'{len(NODERED_ENTITY_IDS) - renamed - len(remaining)} already correct, '
        f'{len(remaining)} not found'
    )

def configure_mqtt():
    configured = entries('mqtt')
    if configured:
        log('MQTT already configured; existing broker credentials preserved')
        return configured[0]
    flow = start_flow('mqtt')
    log('MQTT flow: ' + str(flow.get('type')) + ' / ' + str(flow.get('step_id')))
    if flow.get('type') == 'menu' and 'addon' in flow.get('menu_options', []):
        flow = submit_flow(flow, {'next_step_id': 'addon'})
    if flow.get('type') == 'form' and flow.get('step_id') == 'hassio_confirm':
        flow = submit_flow(flow, {})
    if flow.get('type') != 'create_entry':
        raise RuntimeError('MQTT broker setup needs attention: ' + json.dumps(flow)[:900])
    configured = entries('mqtt')
    if not configured:
        raise RuntimeError('MQTT flow completed but no MQTT entry exists')
    log('MQTT configured using installed Mosquitto broker')
    return configured[0]


def _option_fields(flow):
    return {f.get('name'): f for f in flow.get('data_schema', [])
            if isinstance(f, dict) and isinstance(f.get('name'), str)}


def _discovery_form(entry_id):
    flow = request('POST', '/options/flow', {'handler': entry_id})
    if flow.get('type') != 'form' or flow.get('step_id') != 'options':
        raise RuntimeError('Unexpected MQTT options form: ' + json.dumps(flow)[:800])
    fields = _option_fields(flow)
    if 'discovery' not in fields:
        raise RuntimeError('MQTT options form has no discovery switch')
    return flow, fields


def ensure_mqtt_discovery_off(entry):
    flow, fields = _discovery_form(entry['entry_id'])
    if fields['discovery'].get('default') is False:
        log('MQTT discovery OFF, verified from current options form')
        return
    required = {'discovery', 'discovery_prefix', 'discovery_qos', 'birth_enable', 'will_enable'}
    if not required.issubset(fields):
        raise RuntimeError('Cannot safely set MQTT discovery on this HA version; fields: '
                           + ', '.join(fields))
    values = {}
    for name, field in fields.items():
        if name == 'discovery':
            values[name] = False
        elif 'default' in field:
            values[name] = field['default']
        elif name in entry.get('options', {}):
            values[name] = entry['options'][name]
        elif field.get('required'):
            raise RuntimeError('Required MQTT option lacks existing value: ' + name)
    result = request('POST', '/options/flow/' + flow['flow_id'], values)
    if result.get('type') != 'create_entry':
        raise RuntimeError('MQTT options update failed: ' + json.dumps(result)[:900])
    _, verified_fields = _discovery_form(entry['entry_id'])
    if verified_fields['discovery'].get('default') is not False:
        raise RuntimeError('MQTT discovery OFF could not be verified in refreshed options form')
    log('MQTT discovery OFF, verified from refreshed options form')


def dismiss_stale_mqtt_repair():
    from marketplace_manager import HAWebSocket

    with HAWebSocket() as ws:
        issues = ws.call('repairs/list_issues').get('issues', [])

        issue = next((
            item for item in issues
            if item.get('domain') == 'mqtt'
            and item.get('issue_id') == 'yaml_setup_without_active_setup'
        ), None)

        if issue is None:
            log('No stale MQTT setup repair present')
            return

        if issue.get('ignored'):
            log('MQTT setup repair already dismissed')
            return

        ws.call(
            'repairs/ignore_issue',
            domain='mqtt',
            issue_id='yaml_setup_without_active_setup',
            ignore=True
        )
        log('Stale MQTT setup repair dismissed')

def _home_coordinates():
    if not TOKEN:
        raise RuntimeError('Supervisor token missing')
    req = urllib.request.Request(
        'http://supervisor/core/api/config',
        headers={'Authorization': 'Bearer ' + TOKEN},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        config = json.load(response)
    latitude = config.get('latitude')
    longitude = config.get('longitude')
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise RuntimeError('Home Assistant latitude/longitude not configured')
    return float(latitude), float(longitude)


def _all_form_choices(flow, field_name):
    field = _option_fields(flow).get(field_name)
    if not field:
        raise RuntimeError(f'BOM form has no {field_name}: {json.dumps(flow)[:900]}')
    options = field.get('options')
    if isinstance(options, dict):
        choices = list(options)
    elif isinstance(options, list):
        choices = [
            option['value'] if isinstance(option, dict) else option
            for option in options
        ]
    else:
        raise RuntimeError(f'BOM form has no selectable options for {field_name}')
    if not choices or not all(isinstance(choice, str) for choice in choices):
        raise RuntimeError(f'Invalid or empty BOM options for {field_name}')
    return choices


def _bom_step(flow, expected_step, values, options=False):
    if flow.get('type') != 'form' or flow.get('step_id') != expected_step:
        raise RuntimeError(
            f'Unexpected BOM step (expected {expected_step}): '
            + json.dumps(flow)[:900]
        )
    if options:
        result = request(
            'POST',
            '/options/flow/' + flow['flow_id'],
            values
        )
    else:
        result = submit_flow(flow, values)
    if result.get('type') == 'form' and result.get('errors'):
        raise RuntimeError('BOM rejected setup values: ' + json.dumps(result)[:900])
    return result


def _bom_weather_registry():
    from marketplace_manager import HAWebSocket

    with HAWebSocket() as ws:
        return [
            entity for entity in ws.call('config/entity_registry/list')
            if entity.get('entity_id', '').startswith('weather.')
        ]


def _bom_home_entry(existing):
    by_id = {entry['entry_id']: entry for entry in existing}
    home = next((e for e in _bom_weather_registry()
                 if e.get('entity_id') == 'weather.home'), None)
    if home is None:
        return None
    owner = by_id.get(home.get('config_entry_id'))
    if owner is None or home.get('platform') != 'bureau_of_meteorology':
        log('WARNING: weather.home registry owner does not match a listed '
            'BOM entry (platform=%s, entry_id=%s); no ownership assumed' % (
                home.get('platform'), home.get('config_entry_id')))
        return None
    if home.get('disabled_by'):
        from marketplace_manager import HAWebSocket

        log('BOM weather.home is disabled by %s; enabling it' % home['disabled_by'])
        with HAWebSocket() as ws:
            ws.call('config/entity_registry/update',
                    entity_id='weather.home', disabled_by=None)
        payload = json.dumps({'entry_id': owner['entry_id']}).encode('utf-8')
        reload_request = urllib.request.Request(
            'http://supervisor/core/api/services/homeassistant/reload_config_entry',
            data=payload, method='POST',
            headers={'Authorization': 'Bearer ' + TOKEN,
                     'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(reload_request, timeout=60):
            pass
        for attempt in range(10):
            current = next((entity for entity in _bom_weather_registry()
                            if entity.get('entity_id') == 'weather.home'), None)
            if current and not current.get('disabled_by'):
                break
            time.sleep(2)
        else:
            raise RuntimeError('Unable to enable BOM weather.home; '
                               'the required weather entity remains disabled')
        log('BOM weather.home enabled; existing configuration preserved')
    return owner


def _restore_existing_bom_home(entry):
    from marketplace_manager import HAWebSocket

    with HAWebSocket() as ws:
        candidates = [
            entity for entity in ws.call('config/entity_registry/list')
            if entity.get('config_entry_id') == entry['entry_id']
            and entity.get('platform') == 'bureau_of_meteorology'
            and re.fullmatch(r'weather\.home_[0-9]+', entity.get('entity_id', ''))
        ]
        if len(candidates) > 1:
            raise RuntimeError('Several suffixed BOM weather entities exist; '
                               'refusing to guess which one is weather.home')
        if not candidates:
            return False
        entity = candidates[0]
        if entity.get('disabled_by'):
            raise RuntimeError('Existing BOM weather entity is disabled: '
                               + entity['entity_id'])
        ws.call('config/entity_registry/update',
                entity_id=entity['entity_id'], new_entity_id='weather.home')
        log(f"Restored BOM entity ID: {entity['entity_id']} -> weather.home")
    return True


def _australian_location(latitude, longitude):
    return -44 <= latitude <= -9 and 112 <= longitude <= 154


def repair_bom_config(entry, force=False):

    def step(flow, expected_step, values):
       return _bom_step(flow, expected_step, values, options=True)
       
    current = {**(entry.get('data') or {}), **(entry.get('options') or {})}
    fixed = {
        'weather_name': 'home',
        'observations_basename': 'home',
        'forecasts_basename': 'home',
        'warnings_basename': 'home',
        'observations_create': True,
        'forecasts_create': True,
        'warnings_create': True,
        'forecasts_days': 7,
    }

    if not force and all(current.get(k) == v for k, v in fixed.items()):
        log('BOM required names, enabled groups and seven-day limit verified')
        return

    latitude = current.get('latitude')
    longitude = current.get('longitude')
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise RuntimeError('Cannot safely repair BOM: its existing coordinates '
                           'are not exposed by the config entry')

    flow = request('POST', '/options/flow', {'handler': entry['entry_id']})
    flow = step(flow, 'init', {
        'latitude': latitude, 'longitude': longitude,
    })
    flow = step(flow, 'weather_name', {'weather_name': 'home'})
    flow = step(flow, 'sensors_create', {
        'observations_create': True,
        'forecasts_create': True,
        'warnings_create': True,
    })
    observations = _all_form_choices(flow, 'observations_monitored')
    flow = step(flow, 'observations_monitored', {
        'observations_basename': 'home',
        'observations_monitored': observations,
    })
    forecasts = _all_form_choices(flow, 'forecasts_monitored')
    flow = step(flow, 'forecasts_monitored', {
        'forecasts_basename': 'home',
        'forecasts_monitored': forecasts,
        'forecasts_days': 7,
    })
    flow = step(flow, 'warnings_basename', {'warnings_basename': 'home'})
    if flow.get('type') != 'create_entry':
        raise RuntimeError('BOM options repair did not complete')
    log('BOM configuration repaired using its existing entry')


def _bom_entry_coordinates(entry):
    current = {**(entry.get('data') or {}), **(entry.get('options') or {})}
    latitude, longitude = current.get('latitude'), current.get('longitude')
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise RuntimeError('BOM original coordinates unavailable; refusing to replace its location')
    return float(latitude), float(longitude)


def _reload_bom(entry):
    payload = json.dumps({'entry_id': entry['entry_id']}).encode('utf-8')
    req = urllib.request.Request(
        'http://supervisor/core/api/services/homeassistant/reload_config_entry',
        data=payload, method='POST',
        headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=90):
        pass


def _wait_for_bom_home():
    for _ in range(15):
        owner = _bom_home_entry(entries('bureau_of_meteorology'))
        if owner:
            return owner
        time.sleep(2)
    return None


def _create_bom_at(latitude, longitude):
    domain = 'bureau_of_meteorology'
    if not Path(f'/config/custom_components/{domain}/manifest.json').is_file():
        raise RuntimeError('BOM integration files missing; Marketplace install must run first')

    if not _australian_location(latitude, longitude):
        raise RuntimeError('BOM coordinates are outside Australia; configure the Home Assistant location')
    log(f'Configuring BOM at coordinates: {latitude}, {longitude}')
    flow = start_flow(domain)
    flow = _bom_step(flow, 'user', {
        'latitude': latitude,
        'longitude': longitude,
    })
    flow = _bom_step(flow, 'weather_name', {'weather_name': 'home'})
    flow = _bom_step(flow, 'sensors_create', {
        'observations_create': True,
        'forecasts_create': True,
        'warnings_create': True,
    })
    observations = _all_form_choices(flow, 'observations_monitored')
    flow = _bom_step(flow, 'observations_monitored', {
        'observations_basename': 'home',
        'observations_monitored': observations,
    })
    forecasts = _all_form_choices(flow, 'forecasts_monitored')
    flow = _bom_step(flow, 'forecasts_monitored', {
        'forecasts_basename': 'home',
        'forecasts_monitored': forecasts,
        'forecasts_days': 7,
    })
    flow = _bom_step(flow, 'warnings_basename', {'warnings_basename': 'home'})
    if flow.get('type') != 'create_entry':
        raise RuntimeError('BOM configuration did not complete: ' + json.dumps(flow)[:900])
    if not entries('bureau_of_meteorology'):
        raise RuntimeError('BOM config flow completed but no configuration entry exists')
    if _bom_home_entry(entries(domain)) is None:
        raise RuntimeError('BOM setup completed but weather.home was not registered')
    for attempt in range(10):
        if _bom_home_entry(entries('bureau_of_meteorology')) is not None:
            break
        time.sleep(2)
    else:
        raise RuntimeError('BOM setup created a config entry but weather.home '
                           'is not registered; retry will reuse that entry')
    log(
        f'BOM configured: all {len(observations)} observations, '
        f'all {len(forecasts)} forecast sensor types, warnings, '
        '7 forecast days; all basenames home'
    )

def configure_bom(repair=False):
    domain = 'bureau_of_meteorology'
    existing = entries(domain)
    owner = _bom_home_entry(existing)
    if owner:
        log(f"BOM weather.home verified in {owner['entry_id']}; "
            f"preserving {len(existing)} existing BOM configuration(s)")
        return

    home = next((e for e in _bom_weather_registry()
                 if e.get('entity_id') == 'weather.home'), None)
    if home is not None:
        raise RuntimeError('weather.home exists, but is not owned by a listed '
                           'BOM entry (platform=%s, entry_id=%s)' % (
                               home.get('platform'), home.get('config_entry_id')))

    if not existing:
        latitude, longitude = _home_coordinates()
        _create_bom_at(latitude, longitude)
        if not _wait_for_bom_home():
            raise RuntimeError('BOM setup did not create an enabled weather.home')
        return

    for entry in existing:
        if _restore_existing_bom_home(entry):
            if not _wait_for_bom_home():
                raise RuntimeError('BOM weather.home rename failed verification')
            return

    for entry in existing:
        _reload_bom(entry)
        if _wait_for_bom_home():
            log('BOM weather.home recovered by reloading existing entry')
            return

    coords = [_bom_entry_coordinates(entry) for entry in existing]
    latitude, longitude = coords[0]
    if any(abs(lat - latitude) > 0.00001 or abs(lon - longitude) > 0.00001
           for lat, lon in coords[1:]):
        raise RuntimeError('BOM entries have differing coordinates; refusing '
                           'to silently change any existing location')
    if not _australian_location(latitude, longitude):
        raise RuntimeError('Existing BOM coordinates are outside Australia; '
                           'refusing to rebuild with an incorrect location')

    try:
        repair_bom_config(existing[0], force=True)
        _reload_bom(existing[0])
        if _wait_for_bom_home():
            log('BOM weather.home created through existing configuration')
            return
    except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        log(f'BOM in-place repair unsuccessful: {exc}; rebuilding original entries')

    log(f'BOM weather.home still absent; rebuilding {len(existing)} broken '
        'configuration entry/entries at their original coordinates')
    for entry in existing:
        request('DELETE', '/entry/' + entry['entry_id'])
    if entries(domain):
        raise RuntimeError('BOM removal incomplete; not creating another entry')
    _create_bom_at(latitude, longitude)
    if not _wait_for_bom_home():
        raise RuntimeError('BOM recreation failed to create enabled weather.home')
    log('BOM weather.home recreated successfully')

def enable_solcast_daily_forecasts(entry_id):
    from marketplace_manager import HAWebSocket

    required = {
        f'sensor.solcast_pv_forecast_forecast_day_{day}'
        for day in range(3, 8)
    }

    for attempt in range(30):
        with HAWebSocket() as ws:
            registry = ws.call('config/entity_registry/list')

        found = {
            entity['entity_id']: entity
            for entity in registry
            if entity.get('entity_id') in required
            and entity.get('config_entry_id') == entry_id
            and entity.get('platform') == 'solcast_solar'
        }

        if required.issubset(found):
            break

        time.sleep(2)
    else:
        missing = sorted(required - found.keys())
        raise RuntimeError(
            'Solcast daily forecast entities not registered: '
            + ', '.join(missing)
        )

    disabled = [
        entity_id for entity_id, entity in found.items()
        if entity.get('disabled_by') is not None
    ]

    if disabled:
        with HAWebSocket() as ws:
            for entity_id in sorted(disabled):
                ws.call(
                    'config/entity_registry/update',
                    entity_id=entity_id,
                    disabled_by=None,
                )
                log(f'Enabled Solcast entity: {entity_id}')

        payload = json.dumps({'entry_id': entry_id}).encode('utf-8')
        reload_request = urllib.request.Request(
            'http://supervisor/core/api/services/homeassistant/reload_config_entry',
            data=payload,
            method='POST',
            headers={
                'Authorization': 'Bearer ' + TOKEN,
                'Content-Type': 'application/json',
            },
        )
        with urllib.request.urlopen(reload_request, timeout=60):
            pass

    with HAWebSocket() as ws:
        registry = ws.call('config/entity_registry/list')

    enabled = {
        entity['entity_id']
        for entity in registry
        if entity.get('entity_id') in required
        and entity.get('config_entry_id') == entry_id
        and entity.get('platform') == 'solcast_solar'
        and entity.get('disabled_by') is None
    }

    if enabled != required:
        raise RuntimeError(
            'Solcast forecast entities remain missing or disabled: '
            + ', '.join(sorted(required - enabled))
        )

    log('Solcast daily forecast entities Day 3-7 enabled successfully')


def configure_solcast():
    domain = 'solcast_solar'
    if not SECRETS_FILE.is_file():
        log('No staged onboarding credentials; Solcast setup skipped')
        return
    credentials = json.loads(SECRETS_FILE.read_text(encoding='utf-8'))
    api_key = credentials.get('solcast_key', '')
    if not api_key:
        log('Solcast onboarding skipped by installer; configure manually later')
        return
    if entries(domain):
        raise RuntimeError('Solcast is already configured; fresh-install onboarding refuses to overwrite it')
    if not Path('/config/custom_components/solcast_solar/manifest.json').is_file():
        raise RuntimeError('Solcast files missing; Marketplace must install them before reboot')

    flow = start_flow(domain)
    if flow.get('type') != 'form' or flow.get('step_id') != 'user':
        raise RuntimeError('Unexpected Solcast config flow: ' + repr(flow.get('step_id')))
    result = submit_flow(flow, {
        'api_key': api_key,
        'api_limit': '10',
        'auto_update': '0',
    })
    if result.get('type') != 'create_entry':
        raise RuntimeError('Solcast onboarding failed; check integration flow errors in Home Assistant')
    configured = entries(domain)
    if not configured:
        raise RuntimeError('Solcast config entry was not created')
    enable_solcast_daily_forecasts(configured[0]['entry_id'])
    log('Solcast configured: daily API limit 10, automatic updates DISABLED')

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('install', 'update'), required=True)
    args = parser.parse_args()
    log('Reconciling Node-RED Companion, MQTT and BOM (' + args.mode + ')')
    configure_node_red()
    entry = configure_mqtt()
    ensure_mqtt_discovery_off(entry)
    dismiss_stale_mqtt_repair()
    correct_nodered_entity_ids()
    configure_bom(repair=args.mode == 'update')
    if args.mode == 'install':
        configure_solcast()
    else:
        log('Solcast onboarding skipped on update; credentials and settings preserved')
    log('Integration reconciliation completed successfully')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('ERROR: ' + str(exc))
        sys.exit(1)
