#!/usr/bin/env python3
"""Configure Energy Manager MQTT and Node-RED Companion via HA's HTTP config-flow API.

Run after installing HACS components and rebooting Home Assistant OS.
Does not change .storage, alter broker credentials, or enable MQTT discovery.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = 'http://supervisor/core/api/config/config_entries'
TOKEN = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')


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
    if not flow.get('flow_id'):
        raise RuntimeError('Home Assistant returned a flow without flow_id: ' + repr(flow)[:700])
    return request('POST', '/flow/' + flow['flow_id'], data)


def configure_node_red():
    if entries('nodered'):
        log('Node-RED Companion already configured; leaving existing entry unchanged')
        return
    if not Path('/config/custom_components/nodered/manifest.json').is_file():
        raise RuntimeError('Node-RED Companion files absent; run HACS component installer first')
    flow = start_flow('nodered')
    log('Node-RED flow initial response: ' + str(flow.get('type')) + ' / ' + str(flow.get('step_id')))
    if flow.get('type') == 'form' and flow.get('step_id') == 'user':
        flow = submit_flow(flow, {})
    if flow.get('type') != 'create_entry' or not entries('nodered'):
        raise RuntimeError('Node-RED Companion setup unsuccessful: ' + json.dumps(flow)[:900])
    log('Node-RED Companion configuration entry created')


def configure_mqtt():
    configured = entries('mqtt')
    if configured:
        log('MQTT already configured; keeping existing broker credentials')
        return configured[0]
    flow = start_flow('mqtt')
    log('MQTT flow initial response: ' + str(flow.get('type')) + ' / ' + str(flow.get('step_id')))
    if flow.get('type') == 'menu' and 'addon' in flow.get('menu_options', []):
        flow = submit_flow(flow, {'next_step_id': 'addon'})
    if flow.get('type') == 'form' and flow.get('step_id') == 'hassio_confirm':
        flow = submit_flow(flow, {})
    if flow.get('type') != 'create_entry':
        raise RuntimeError('MQTT broker setup needs attention: ' + json.dumps(flow)[:900])
    configured = entries('mqtt')
    if not configured:
        raise RuntimeError('MQTT flow returned create_entry but MQTT entry is absent')
    log('MQTT configured using installed broker')
    return configured[0]


def disable_mqtt_discovery(entry):
    if entry.get('options', {}).get('discovery') is False:
        log('MQTT discovery OFF, verified')
        return
    step = request('POST', '/options/flow', {'handler': entry['entry_id']})
    if step.get('type') != 'form' or step.get('step_id') != 'options':
        raise RuntimeError('Unexpected MQTT options form: ' + json.dumps(step)[:900])
    fields = {f.get('name'): f for f in step.get('data_schema', []) if isinstance(f, dict)}
    required = {'discovery', 'discovery_prefix', 'discovery_qos', 'birth_enable', 'will_enable'}
    if not required.issubset(fields):
        raise RuntimeError('Cannot safely disable MQTT discovery automatically with this form; '
                           'disable in MQTT > Configure MQTT options. Fields: ' + ', '.join(fields))
    values = {}
    for name, field in fields.items():
        if name == 'discovery':
            values[name] = False
        elif 'default' in field:
            values[name] = field['default']
        elif name in entry.get('options', {}):
            values[name] = entry['options'][name]
        elif field.get('required'):
            raise RuntimeError('Required MQTT option lacks a safe value: ' + name)
    result = request('POST', '/options/flow/' + step['flow_id'], values)
    if result.get('type') != 'create_entry':
        raise RuntimeError('MQTT options update failed: ' + json.dumps(result)[:900])
    configured = entries('mqtt')
    if not configured or configured[0].get('options', {}).get('discovery') is not False:
        raise RuntimeError('MQTT discovery OFF could not be verified after update')
    log('MQTT discovery OFF, verified')


def main():
    log('Configuring Node-RED Companion and MQTT through Home Assistant HTTP API')
    configure_node_red()
    entry = configure_mqtt()
    disable_mqtt_discovery(entry)
    log('Required integration entries configured; BOM and Solcast still need onboarding')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('ERROR: ' + str(exc))
        sys.exit(1)
