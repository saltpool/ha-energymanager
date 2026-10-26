#!/usr/bin/env python3
"""Set up MQTT and Node-RED Companion following the HACS component reboot.

Uses Home Assistant's HTTP config flows. Never edits .storage directly.
BOM and Solcast deliberately remain manual onboarding steps.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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
        raise RuntimeError('Node-RED Companion files absent; run HACS component installer and reboot first')
    flow = start_flow('nodered')
    log('Node-RED flow: ' + str(flow.get('type')) + ' / ' + str(flow.get('step_id')))
    if flow.get('type') == 'form' and flow.get('step_id') == 'user':
        flow = submit_flow(flow, {})
    if flow.get('type') != 'create_entry' or not entries('nodered'):
        raise RuntimeError('Node-RED Companion configuration unsuccessful: ' + json.dumps(flow)[:900])
    log('Node-RED Companion configuration entry created')

def correct_nodered_entity_ids():
    """Assign Energy Manager entity IDs using Home Assistant's registry API."""
    from hacs_manager import HAWebSocket

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
    # /config/config_entries/entry may omit options. Read the actual options form.
    # The form defaults reflect the current MQTT options, as seen in the HA UI.
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
    # A new flow reads back persisted MQTT options; entry listing may omit options.
    _, verified_fields = _discovery_form(entry['entry_id'])
    if verified_fields['discovery'].get('default') is not False:
        raise RuntimeError('MQTT discovery OFF could not be verified in refreshed options form')
    log('MQTT discovery OFF, verified from refreshed options form')


def dismiss_stale_mqtt_repair():
    """Dismiss the expected MQTT setup warning after successful configuration."""
    from hacs_manager import HAWebSocket

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


def main():
    log('Configuring Node-RED Companion and MQTT')
    configure_node_red()
    entry = configure_mqtt()
    ensure_mqtt_discovery_off(entry)
    dismiss_stale_mqtt_repair()
    correct_nodered_entity_ids()
    log('MQTT and Node-RED Companion configured successfully')
    log('Bureau of Meteorology and Solcast PV Forecast require manual onboarding')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('ERROR: ' + str(exc))
        sys.exit(1)
