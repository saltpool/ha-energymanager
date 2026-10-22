#!/usr/bin/env python3
"""Configure Energy Manager's credential-free HA integrations after HACS reboot.

Run in Advanced SSH & Web Terminal. Uses Home Assistant's WebSocket config
flows, not .storage edits. No host reboot and no custom credentials needed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, '/config/scripts')
from hacs_manager import HAWebSocket


def log(s):
    print('[EM Integrations] ' + s, flush=True)


def entries(ws):
    return ws.call('config_entries/get')


def existing(ws, domain):
    return [e for e in entries(ws) if e.get('domain') == domain and e.get('source') != 'ignore']


def configure_node_red(ws):
    if existing(ws, 'nodered'):
        log('Node-RED Companion already configured; preserved')
        return
    if not Path('/config/custom_components/nodered/manifest.json').is_file():
        raise RuntimeError('Node-RED Companion integration files missing; run HACS stage first')
    flow = ws.call('config_entries/flow/init', handler='nodered', show_advanced_options=False)
    if flow.get('type') == 'form' and flow.get('step_id') == 'user':
        result = ws.call('config_entries/flow/configure', flow_id=flow['flow_id'], user_input={})
    else:
        result = flow
    if result.get('type') != 'create_entry':
        raise RuntimeError('Node-RED Companion configuration did not complete: ' + json.dumps(result)[:700])
    log('Node-RED Companion integration configured')


def configure_mqtt(ws):
    found = existing(ws, 'mqtt')
    if found:
        log('MQTT integration already configured; preserving broker details')
        return found[0]
    flow = ws.call('config_entries/flow/init', handler='mqtt', show_advanced_options=False)
    # The supported HA OS UI flow presents an add-on menu if Supervisor exists.
    if flow.get('type') == 'menu' and flow.get('step_id') == 'user' and 'addon' in flow.get('menu_options', []):
        flow = ws.call('config_entries/flow/configure', flow_id=flow['flow_id'], user_input={'next_step_id': 'addon'})
    if flow.get('type') == 'form' and flow.get('step_id') == 'hassio_confirm':
        flow = ws.call('config_entries/flow/configure', flow_id=flow['flow_id'], user_input={})
    if flow.get('type') != 'create_entry':
        raise RuntimeError('MQTT broker setup requires attention; flow returned: ' + json.dumps(flow)[:900])
    found = existing(ws, 'mqtt')
    if not found:
        raise RuntimeError('MQTT configuration flow completed but no entry was found')
    log('MQTT broker integration configured')
    return found[0]


def disable_discovery(ws, entry):
    if entry.get('options', {}).get('discovery') is False:
        log('MQTT discovery already disabled; verified')
        return
    # Do not write core.config_entries directly. MQTT uses an options flow;
    # it includes extra settings. Only submit when the form is understood.
    step = ws.call('config_entries/options/flow/init', entry_id=entry['entry_id'], show_advanced_options=False)
    if step.get('type') != 'form' or step.get('step_id') != 'options':
        raise RuntimeError('MQTT discovery is ON and options flow was unexpected: ' + json.dumps(step)[:700])
    # The options schema varies by HA version; require known fields and
    # retain all existing values instead of blindly supplying guessed defaults.
    fields = {f.get('name'): f for f in step.get('data_schema', []) if isinstance(f, dict)}
    required = {'discovery', 'discovery_prefix', 'discovery_qos', 'birth_enable', 'will_enable'}
    if not required.issubset(fields):
        raise RuntimeError('MQTT discovery is ON. Cannot safely automate this HA options form; disable it in MQTT > Configure MQTT Options. Fields: ' + ', '.join(fields))
    values = {}
    for name, field in fields.items():
        if name == 'discovery':
            values[name] = False
        elif 'default' in field:
            values[name] = field['default']
        elif name in entry.get('options', {}):
            values[name] = entry['options'][name]
        elif field.get('required'):
            raise RuntimeError('Missing MQTT setting ' + name + '; refusing to guess')
    result = ws.call('config_entries/options/flow/configure', flow_id=step['flow_id'], user_input=values)
    if result.get('type') != 'create_entry':
        raise RuntimeError('MQTT options were not applied: ' + json.dumps(result)[:800])
    refreshed = existing(ws, 'mqtt')
    if not refreshed or refreshed[0].get('options', {}).get('discovery') is not False:
        raise RuntimeError('MQTT discovery disable was not verified')
    log('MQTT discovery OFF; verified')


def main():
    log('Configuring MQTT and Node-RED Companion through Home Assistant')
    with HAWebSocket() as ws:
        configure_node_red(ws)
        mqtt = configure_mqtt(ws)
        disable_discovery(ws, mqtt)
    log('MQTT and Node-RED Companion configuration complete')
    log('BOM location and Solcast API credentials remain onboarding tasks')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        log('ERROR: ' + str(exc))
        sys.exit(1)
