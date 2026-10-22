#!/usr/bin/env python3
"""
Perform Energy Manager Update v1.3.0 - Github branch updater
"""
import sys
import os
import shutil
import json
import time
import subprocess
import tarfile
import uuid
import glob
from datetime import datetime, timedelta
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description='Energy Manager Update Script')
    parser.add_argument('--force-reinstall', action='store_true', help='Force reinstall of current version')
    parser.add_argument('--branch', choices=('main', 'early', 'test', 'development'), help='Override HA branch selector')
    parser.add_argument('--key', default='', help=argparse.SUPPRESS)
    return parser.parse_args()

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠ requests module not available - some features may not work")

sys.path.append('/config/scripts')

from update_checker import EnergyManagerUpdateChecker, version_tuple
from file_merger import EnergyManagerFileMerger
from hacs_manager import sync_hacs_components_via_ssh

def cleanup_old_backups():
    try:
        backup_dir = '/config/.energy_manager/backups'
        if not os.path.exists(backup_dir):
            return
        
        cutoff_date = datetime.now() - timedelta(days=60)
        recent_cutoff = datetime.now() - timedelta(days=7)
        
        for item in os.listdir(backup_dir):
            item_path = os.path.join(backup_dir, item)
            if os.path.isdir(item_path):
                try:
                    date_part = item.split('_')[0] + '_' + item.split('_')[1]
                    backup_date = datetime.strptime(date_part, '%Y-%m-%d_%H')
                    
                    if backup_date < cutoff_date:
                        shutil.rmtree(item_path)
                        print(f"🗑️ Deleted old backup: {item}")
                    elif backup_date < recent_cutoff and not os.path.exists(f"{item_path}.tar.gz"):
                        with tarfile.open(f"{item_path}.tar.gz", 'w:gz') as tar:
                            tar.add(item_path, arcname=item)
                        shutil.rmtree(item_path)
                        print(f"📦 Compressed backup: {item}")
                        
                except (ValueError, IndexError):
                    continue
                    
    except Exception as e:
        print(f"⚠ Backup cleanup error: {e}")

def supervisor_api_call(endpoint, method='GET', data=None):
    if not REQUESTS_AVAILABLE:
        print("❌ Cannot make API calls - requests module not available")
        return False, {}

    token = os.environ.get('SUPERVISOR_TOKEN', '')
    if not token:
        return False, {}

    url = f"http://supervisor/core/api/{endpoint}"
    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json'
    }
    
    try:
        if method == 'POST':
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return True, response.json() if response.text else {}
        else:
            return False, {}
            
    except Exception as e:
        return False, {}

def get_entity_state(entity_id):
    
    try:
        success, response = supervisor_api_call(f"states/{entity_id}")
        if success:
            return response
    except Exception as e:
        pass
    
    try:
        storage_path = '/config/.storage/core.config_entries'
        if os.path.exists(storage_path):
            with open(storage_path, 'r') as f:
                config_data = json.load(f)
            
            for entry in config_data.get('data', {}).get('entries', []):
                if entry.get('domain') == 'input_select':
                    pass
                
    except Exception as e:
        pass
    
    try:
        entity_registry_path = '/config/.storage/core.entity_registry'
        if os.path.exists(entity_registry_path):
            with open(entity_registry_path, 'r') as f:
                registry_data = json.load(f)
                
    except Exception as e:
        pass
    
    try:
        result = subprocess.run(['ha', 'core', 'info'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            entity_result = subprocess.run(['ha', 'core', 'state', 'get', entity_id], 
                                         capture_output=True, text=True, timeout=10)
            if entity_result.returncode == 0 and entity_result.stdout:
                output_lines = entity_result.stdout.strip().split('\n')
                for line in output_lines:
                    if 'state:' in line.lower():
                        state_value = line.split(':', 1)[1].strip()
                        return {'state': state_value}
    except Exception as e:
        pass
       
    try:
        state_file = '/config/.storage/core.restore_state'
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                state_data = json.load(f)
            
            for item in state_data.get('data', []):
                if item.get('state', {}).get('entity_id') == entity_id:
                    state_value = item.get('state', {}).get('state')
                    return {'state': state_value}
                    
    except Exception as e:
        pass
    
    try:
        import socket
        sock_path = '/var/run/homeassistant/homeassistant.sock'
        if os.path.exists(sock_path):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(sock_path)
            
            request = f"GET /api/states/{entity_id} HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}\r\n\r\n"
            sock.send(request.encode())
            response = sock.recv(4096).decode()
            sock.close()
            
            if '200 OK' in response and '{' in response:
                json_start = response.find('{')
                json_data = response[json_start:]
                data = json.loads(json_data)
                return data
                
    except Exception as e:
        pass
    
    try:
        url = f"http://127.0.0.1:8123/api/states/{entity_id}"
        headers = {'Content-Type': 'application/json'}

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return data

    except Exception as e:
        pass

    try:
        config_file = '/config/configuration.yaml'
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_content = f.read()
            
            if 'input_select:' in config_content:
                lines = config_content.split('\n')
                in_input_select = False
                in_inverter_brand = False
                
                for line in lines:
                    if line.strip().startswith('input_select:'):
                        in_input_select = True
                        continue
                    
                    if in_input_select:
                        if line.strip().startswith('inverter_brand:'):
                            in_inverter_brand = True
                            continue
                        
                        if in_inverter_brand and 'initial:' in line:
                            initial_value = line.split('initial:')[1].strip().strip('"\'')
                            return {'state': initial_value}
                        
                        if line.strip() and not line.startswith('  ') and not line.startswith('\t'):
                            in_input_select = False
                            in_inverter_brand = False
                            
    except Exception as e:
        pass
    
    return None

def handle_special_files(manifest):
    try:
        modbus_files = ['alphaess_modbus.yaml.disabled', 'fronius_modbus.yaml.disabled', 
                        'sigenergy_modbus.yaml.disabled', 'sungrow_modbus.yaml.disabled',
                        'goodwe_modbus.yaml.disabled', 'solaredge_modbus.yaml.disaled']
        
        updated_modbus_files = [f for f in modbus_files if f in manifest.get('files', {})]
        
        if updated_modbus_files:
            print("Checking modbus configuration...")
            
            brand_state = get_entity_state('input_select.inverter_brand')
            
            if brand_state:
                current_brand = brand_state.get('state')
                brand_to_modbus_disabled = {
                    'sungrow':   'sungrow_modbus.yaml.disabled',
                    'sigenergy': 'sigenergy_modbus.yaml.disabled',
                    'alphaess':  'alphaess_modbus.yaml.disabled',
                    'fronius':   'fronius_modbus.yaml.disabled',
                    'goodwe':    'goodwe_modbus.yaml.disabled',
                    'goodwe_et': 'goodwe_modbus.yaml.disabled',
                    'goodwe_int': 'goodwe_modbus.yaml.disabled',
                    'solaredge': 'solaredge_modbus.yaml.disabled',
                }

                if current_brand in brand_to_modbus_disabled:
                    disabled_file = os.path.join('/config', brand_to_modbus_disabled[current_brand])
                    active_file = os.path.join('/config/modbus', "modbus.yaml")
                    
                    if os.path.exists(disabled_file):
                        if os.path.exists(active_file):
                            timestamp = datetime.now().strftime('%Y%m%d_%H')
                            backup_dir = f"/config/.energy_manager/backups/{timestamp}_modbus_switch"
                            os.makedirs(backup_dir, exist_ok=True)
                            shutil.copy2(active_file, os.path.join(backup_dir, "modbus.yaml.bak"))
                            print(f"✅ Backed up current modbus.yaml")
                        
                        shutil.copy2(disabled_file, active_file)
                        print(f"✅ Activated {current_brand} modbus configuration")
                        
                        return True
                    else:
                        print(f"❌ CRITICAL: Disabled file for {current_brand} not found: {disabled_file}")
                        return False
                else:
                    print(f"❌ CRITICAL: Unknown or unsupported inverter brand: {current_brand}")
                    return False
            else:
                print("❌ CRITICAL: Could not get inverter brand selection - API authentication failed")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ CRITICAL: Failed to handle special files: {e}")
        return False

def update_dashboard_status(message, status="info"):
    try:
        status_file = '/config/.energy_manager/dashboard_status.txt'
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        if status == "ssh_required":
            content = f"""## 🔑 SSH Setup Required

**Last Updated:** {timestamp}

{message}

**Status:** Waiting for SSH configuration
"""
        elif status == "error":
            content = f"""## ❌ Update Error

**Last Updated:** {timestamp}

{message}

**Status:** Failed
"""
        elif status == "success":
            content = f"""## ✅ Update Complete

**Last Updated:** {timestamp}

{message}

**Status:** Success
"""
        elif status == "self_update":
            content = f"""## 🔄 Self-Update Complete

**Last Updated:** {timestamp}

{message}

**Status:** Ready for Next Update
"""
        else:
            content = f"""## ℹ️ Update Status

**Last Updated:** {timestamp}

{message}

**Status:** In Progress
"""
        
        with open(status_file, 'w') as f:
            f.write(content)
        
        print(f"✅ Dashboard status updated: {status}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update dashboard: {e}")
        return False

def test_ssh_key_authentication():
    
    ssh_key_path = '/config/.energy_manager/ssh_key'
    ssh_target = 'a0d7b954-ssh.local.hass.io'
    ssh_username = 'hassio'
    
    if not os.path.exists(ssh_key_path):
        print("❌ SSH key not found")
        update_dashboard_status("SSH key not configured. Please use the dashboard to generate an SSH key first, then add it to the SSH addon configuration.", "ssh_required")
        return False
    
    print(f"Testing SSH key authentication to {ssh_username}@{ssh_target}...")
    
    try:
        ssh_test_cmd = [
            'ssh', '-i', ssh_key_path,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ConnectTimeout=10',
            '-o', 'BatchMode=yes',
            '-o', 'PasswordAuthentication=no',
            f'{ssh_username}@{ssh_target}',
            'echo', 'SSH_KEY_TEST_SUCCESS'
        ]
        
        result = subprocess.run(ssh_test_cmd, capture_output=True, text=True, timeout=20)
        
        if result.returncode == 0 and 'SSH_KEY_TEST_SUCCESS' in result.stdout:
            print("✅ SSH key authentication successful!")
            return True
        else:
            error_msg = f"SSH key authentication failed: {result.stderr}"
            print(f"❌ {error_msg}")
            update_dashboard_status("SSH authentication failed. Please verify the SSH key has been added to the SSH addon configuration and the addon has been restarted.", "ssh_required")
            return False
            
    except Exception as e:
        error_msg = f"SSH key test error: {e}"
        print(f"❌ {error_msg}")
        update_dashboard_status(error_msg, "error")
        return False

def _read_remote_text_via_ssh(remote_path):
    """Read remote text file via SSH. Returns text or None."""
    ssh_key_path = '/config/.energy_manager/ssh_key'
    ssh_target = 'a0d7b954-ssh.local.hass.io'
    ssh_username = 'hassio'
    if not os.path.exists(ssh_key_path):
        return None
    try:
        cmd = [
            'ssh','-i',ssh_key_path,
            '-o','StrictHostKeyChecking=no',
            '-o','BatchMode=yes',
            f'{ssh_username}@{ssh_target}',
            f'sudo cat {remote_path}'
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode == 0 and res.stdout:
            return res.stdout
        return None
    except Exception:
        return None

def _merge_energy_manager_tabs(current_flows_str, new_flows_str, prefix='EnergyManager-'):
    """Replace only tabs whose label starts with prefix (and their nodes), plus any referenced subflow definitions."""
    try:
        cur = json.loads(current_flows_str)
        new = json.loads(new_flows_str)
        if not isinstance(cur, list) or not isinstance(new, list):
            return None
        def is_tab(n):
            return n.get('type') == 'tab' and isinstance(n.get('label'), str) and 'id' in n
        cur_tabs = {n['id']: n for n in cur if is_tab(n)}
        new_tabs = {n['id']: n for n in new if is_tab(n)}
        cur_em_tab_ids = {tid for tid, tab in cur_tabs.items() if tab.get('label','').startswith(prefix)}
        new_em_tab_ids = {tid for tid, tab in new_tabs.items() if tab.get('label','').startswith(prefix)}
        merged = [n for n in cur if not (is_tab(n) and n['id'] in cur_em_tab_ids) and n.get('z') not in cur_em_tab_ids]
        to_add = [n for n in new if (is_tab(n) and n['id'] in new_em_tab_ids) or (n.get('z') in new_em_tab_ids)]
        used_subflow_ids = set()
        for n in to_add:
            t = n.get('type','')
            if isinstance(t,str) and t.startswith('subflow:'):
                used_subflow_ids.add(t.split(':',1)[1])
        if used_subflow_ids:
            merged = [n for n in merged if not (n.get('type')=='subflow' and n.get('id') in used_subflow_ids)]
            for d in new:
                if d.get('type') == 'subflow' and d.get('id') in used_subflow_ids:
                    merged.append(d)
        existing_ids = {n.get('id') for n in merged}
        merged.extend([n for n in to_add if n.get('id') not in existing_ids])
        try:
            print(f"EM-merge: removed {len(cur_em_tab_ids)} tabs; added {len(new_em_tab_ids)} tabs; result nodes={len(merged)}")
        except Exception:
            pass
        return json.dumps(merged, separators=(',', ':'))
    except Exception:
        return None

def update_flows_via_ssh(flows_content, manifest_version):
    
    print("=== Updating Flows via SSH ===")
    
    ssh_key_path = '/config/.energy_manager/ssh_key'
    ssh_target = 'a0d7b954-ssh.local.hass.io'
    ssh_username = 'hassio'
    
    if not test_ssh_key_authentication():
        print("❌ SSH authentication failed")
        return False
    
    local_flows_file = '/config/.energy_manager/new_flows.json'
    try:
        with open(local_flows_file, 'w') as f:
            flows_to_write = flows_content
            try:
                remote_str = _read_remote_text_via_ssh('/addon_configs/a0d7b954_nodered/flows.json')
                if remote_str:
                    merged_str = _merge_energy_manager_tabs(remote_str, flows_content, prefix='EnergyManager-')
                    if merged_str:
                        flows_to_write = merged_str
                        print('Using selective EnergyManager- tab merge for flows.json')
            except Exception:
                pass
            f.write(flows_to_write)
        
        source_size = os.path.getsize(local_flows_file)
        print(f"Source flows file: {source_size} bytes")
            
    except Exception as e:
        error_msg = f"Failed to write flows file: {e}"
        print(f"❌ {error_msg}")
        update_dashboard_status(error_msg, "error")
        return False
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_cmd = [
        'ssh', '-i', ssh_key_path,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        f'{ssh_username}@{ssh_target}',
        f'sudo cp /addon_configs/a0d7b954_nodered/flows.json /addon_configs/a0d7b954_nodered/flows.json.backup.{timestamp}'
    ]
    
    try:
        result = subprocess.run(backup_cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print(f"✅ Backup created: flows.json.backup.{timestamp}")
        else:
            print(f"⚠ Backup failed: {result.stderr}")
    except Exception as e:
        print(f"⚠ Backup error: {e}")
    
    print("Copying flows to temp directory...")
    
    copy_to_temp_cmd = [
        'ssh', '-i', ssh_key_path,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        f'{ssh_username}@{ssh_target}',
        'cat > /tmp/flows.json'
    ]
    
    try:
        with open(local_flows_file, 'r') as f:
            flows_data = f.read()
        
        result = subprocess.run(copy_to_temp_cmd, input=flows_data, text=True, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            error_msg = f"Failed to copy flows to temp: {result.stderr}"
            print(f"❌ {error_msg}")
            update_dashboard_status(error_msg, "error")
            return False
            
        print("✅ Flows copied to temp directory")
        
    except Exception as e:
        error_msg = f"Copy to temp error: {e}"
        print(f"❌ {error_msg}")
        update_dashboard_status(error_msg, "error")
        return False
    
    print("Moving flows to Node-RED directory...")
    
    move_cmd = [
        'ssh', '-i', ssh_key_path,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        f'{ssh_username}@{ssh_target}',
        'sudo cp /tmp/flows.json /addon_configs/a0d7b954_nodered/flows.json'
    ]
    
    try:
        result = subprocess.run(move_cmd, capture_output=True, text=True, timeout=15)
        
        if result.returncode != 0:
            error_msg = f"Failed to move flows to Node-RED: {result.stderr}"
            print(f"❌ {error_msg}")
            update_dashboard_status(error_msg, "error")
            return False
            
        print("✅ Flows moved to Node-RED directory")
        
    except Exception as e:
        error_msg = f"Move to Node-RED error: {e}"
        print(f"❌ {error_msg}")
        update_dashboard_status(error_msg, "error")
        return False
    
    print("Verifying flows update...")
    
    verify_cmd = [
        'ssh', '-i', ssh_key_path,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        f'{ssh_username}@{ssh_target}',
        'ls -la /addon_configs/a0d7b954_nodered/flows.json'
    ]
    
    try:
        result = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print(f"✅ Verification: {result.stdout.strip()}")
        else:
            print(f"⚠ Verification failed: {result.stderr}")
            
    except Exception as e:
        print(f"⚠ Verification error: {e}")
    
    cleanup_cmd = [
        'ssh', '-i', ssh_key_path,
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'BatchMode=yes',
        f'{ssh_username}@{ssh_target}',
        'rm -f /tmp/flows.json'
    ]
    
    try:
        subprocess.run(cleanup_cmd, capture_output=True, text=True, timeout=10)
        print("✅ Temp file cleaned up")
    except Exception as e:
        print(f"⚠ Cleanup error: {e}")
    
    if os.path.exists(local_flows_file):
        os.remove(local_flows_file)
    
    print("=== SSH Flows Update Complete ===")
    return True

def _restart_nodered_via_ssh():
    ssh_key_path = '/config/.energy_manager/ssh_key'
    ssh_target = 'a0d7b954-ssh.local.hass.io'
    ssh_username = 'hassio'
    try:
        print("Restarting Node-RED to pick up changes (SSH fallback)...")
        subprocess.run([
            'ssh','-i',ssh_key_path,
            '-o','StrictHostKeyChecking=no',
            '-o','BatchMode=yes',
            f'{ssh_username}@{ssh_target}',
            'ha addons restart a0d7b954_nodered'
        ], capture_output=True, text=True, timeout=60)
        print("✅ Node-RED restart initiated (SSH fallback)")
    except Exception as e:
        print(f"⚠ Node-RED restart via SSH fallback failed: {e}")
def get_nodered_status():
    success, info = supervisor_api_call('addons/a0d7b954_nodered/info')
    if success:
        state = info.get('data', {}).get('state', 'unknown')
        return state
    else:
        return 'unknown'

def validate_flows_json(file_path):
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        return True
    except json.JSONDecodeError as e:
        return False
    except Exception as e:
        return False

def update_status_success(version):
    message = f"""**Energy Manager successfully updated to version {version}**

✅ All files updated
✅ Node-RED flows updated via SSH 
✅ System ready

Last update completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    update_dashboard_status(message, "success")

def update_status_self_update_success(version):
    message = f"""**Update script successfully updated to version {version}**

🔄 Update script has been updated
✅ All other components updated
✅ System ready for future updates

Last update completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

The update system is now ready to handle future updates with the latest improvements."""
    
    update_dashboard_status(message, "self_update")

def update_status_failed(error):
    message = f"""**Energy Manager update failed**

❌ Error: {error}

Please check the logs and try again."""
    
    update_dashboard_status(message, "error")

def create_or_update_entity(entity_id, entity_config):
    try:
        entity_type = entity_config.get('entity_type')
        payload = entity_config.get('payload', {})
        preserve_current = entity_config.get('preserve_current_value', False)
        description = entity_config.get('description', '')
        
        print(f"Processing entity: {entity_id} ({entity_type})")
        
        current_value = None
        if preserve_current:
            current_state = get_entity_state(entity_id)
            if current_state:
                current_value = current_state.get('state')
                print(f"Current value of {entity_id}: {current_value}")
        
        api_payload = {}
        
        if entity_type == 'input_select':
            api_payload = {
                'name': entity_id.split('.')[1].replace('_', ' ').title(),
                'options': payload.get('options', []),
                'icon': payload.get('icon', 'mdi:form-select')
            }
            
            if preserve_current and current_value and current_value in payload.get('options', []):
                api_payload['initial'] = current_value
            elif 'initial' in payload:
                api_payload['initial'] = payload['initial']
            elif payload.get('options'):
                api_payload['initial'] = payload['options'][0]
                
        elif entity_type == 'input_number':
            api_payload = {
                'name': entity_id.split('.')[1].replace('_', ' ').title(),
                'min': float(payload.get('min', 0)),
                'max': float(payload.get('max', 100)),
                'step': float(payload.get('step', 1)),
                'mode': payload.get('mode', 'slider'),
                'icon': payload.get('icon', 'mdi:numeric'),
                'unit_of_measurement': payload.get('unit_of_measurement', '')
            }
            
            if preserve_current and current_value:
                try:
                    current_float = float(current_value)
                    if api_payload['min'] <= current_float <= api_payload['max']:
                        api_payload['initial'] = current_float
                    else:
                        print(f"⚠ Current value {current_float} is outside new bounds [{api_payload['min']}, {api_payload['max']}], using default")
                        api_payload['initial'] = payload.get('initial', api_payload['min'])
                except (ValueError, TypeError):
                    print(f"⚠ Could not parse current value '{current_value}' as number, using default")
                    api_payload['initial'] = payload.get('initial', api_payload['min'])
            elif 'initial' in payload:
                api_payload['initial'] = float(payload['initial'])
            else:
                api_payload['initial'] = api_payload['min']
                
        elif entity_type == 'input_boolean':
            api_payload = {
                'name': entity_id.split('.')[1].replace('_', ' ').title(),
                'icon': payload.get('icon', 'mdi:toggle-switch')
            }
            
            if preserve_current and current_value:
                api_payload['initial'] = current_value.lower() in ['true', 'on', '1', 'yes']
            elif 'initial' in payload:
                api_payload['initial'] = payload['initial']
            else:
                api_payload['initial'] = False
                
        elif entity_type == 'input_text':
            api_payload = {
                'name': entity_id.split('.')[1].replace('_', ' ').title(),
                'min': int(payload.get('min', 0)),
                'max': int(payload.get('max', 100)),
                'pattern': payload.get('pattern', ''),
                'mode': payload.get('mode', 'text'),
                'icon': payload.get('icon', 'mdi:form-textbox')
            }
            
            if preserve_current and current_value:
                api_payload['initial'] = current_value
            elif 'initial' in payload:
                api_payload['initial'] = payload['initial']
            else:
                api_payload['initial'] = ''
                
        else:
            print(f"❌ Unsupported entity type: {entity_type}")
            return False
        
        success = False
        
        if not success and REQUESTS_AVAILABLE:
            try:
                service_name = f"{entity_type}_set_value" if preserve_current and current_value else f"{entity_type}_create"
                
                url = f"http://homeassistant:8123/api/config/config_entries"
                headers = {
                    'Authorization': 'Bearer ' + os.environ.get('SUPERVISOR_TOKEN', ''),
                    'Content-Type': 'application/json'
                }
                
                state_success, state_response = supervisor_api_call(f"states/{entity_id}")
                entity_exists = state_success and state_response
                
                if entity_exists:
                    print(f"Entity {entity_id} already exists, updating configuration...")
                    config_update_success = update_entity_configuration(entity_id, api_payload, entity_type)
                    success = config_update_success
                else:
                    print(f"Creating new entity {entity_id}...")
                    config_create_success = add_entity_to_configuration(entity_id, api_payload, entity_type)
                    success = config_create_success
                
            except Exception as e:
                print(f"API method failed: {e}")
                success = False
        
        if not success:
            print(f"Updating configuration.yaml for {entity_id}...")
            success = add_entity_to_configuration(entity_id, api_payload, entity_type)
        
        if success:
            print(f"✅ Successfully processed entity: {entity_id}")
            return True
        else:
            print(f"❌ Failed to process entity: {entity_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error processing entity {entity_id}: {e}")
        return False

def update_entity_configuration(entity_id, config, entity_type):
    try:
        config_file = '/config/configuration.yaml'
        
        if not os.path.exists(config_file):
            print(f"❌ Configuration file not found: {config_file}")
            return False
        
        with open(config_file, 'r') as f:
            content = f.read()
        
        lines = content.split('\n')
        updated_lines = []
        in_entity_section = False
        in_target_entity = False
        entity_section = entity_type + ':'
        entity_name = entity_id.split('.')[1]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.strip() == entity_section:
                in_entity_section = True
                updated_lines.append(line)
                i += 1
                continue
            
            if in_entity_section and line.strip().startswith(f"{entity_name}:"):
                in_target_entity = True
                updated_lines.append(line)
                
                i += 1
                while i < len(lines) and (lines[i].startswith('  ') or lines[i].strip() == ''):
                    i += 1
                
                for key, value in config.items():
                    if isinstance(value, list):
                        updated_lines.append(f"  {key}:")
                        for item in value:
                            updated_lines.append(f"    - {item}")
                    else:
                        updated_lines.append(f"  {key}: {value}")
                
                in_target_entity = False
                continue
            
            if in_entity_section and line.strip() and not line.startswith(' ') and line.strip() != entity_section:
                in_entity_section = False
            
            updated_lines.append(line)
            i += 1
        
        with open(config_file, 'w') as f:
            f.write('\n'.join(updated_lines))
        
        print(f"✅ Updated configuration for {entity_id}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating configuration for {entity_id}: {e}")
        return False

def add_entity_to_configuration(entity_id, config, entity_type):
    try:
        config_file = '/config/configuration.yaml'
        entity_name = entity_id.split('.')[1]
        
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                content = f.read()
        else:
            content = ""
        
        lines = content.split('\n') if content else []
        
        entity_section = entity_type + ':'
        section_exists = False
        section_line = -1
        
        for i, line in enumerate(lines):
            if line.strip() == entity_section:
                section_exists = True
                section_line = i
                break
        
        if section_exists:
            insert_point = section_line + 1
            while insert_point < len(lines) and (lines[insert_point].startswith('  ') or lines[insert_point].strip() == ''):
                insert_point += 1
        else:
            if lines and lines[-1].strip() != '':
                lines.append('')
            lines.append(entity_section)
            insert_point = len(lines)
        
        entity_config = [f"  {entity_name}:"]
        for key, value in config.items():
            if isinstance(value, list):
                entity_config.append(f"    {key}:")
                for item in value:
                    entity_config.append(f"      - {item}")
            else:
                entity_config.append(f"    {key}: {value}")
        
        for i, config_line in enumerate(entity_config):
            lines.insert(insert_point + i, config_line)
        
        with open(config_file, 'w') as f:
            f.write('\n'.join(lines))
        
        print(f"✅ Added {entity_id} to configuration.yaml")
        return True
        
    except Exception as e:
        print(f"❌ Error adding {entity_id} to configuration: {e}")
        return False

def handle_entities_update(manifest):
    try:
        entities = manifest.get('entities', {})
        if not entities:
            print("No entities to update")
            return True
        
        print(f"Processing {len(entities)} entities...")
        success = True
        
        for entity_id, entity_config in entities.items():
            action = entity_config.get('action')
            
            if action == 'entity_api_update':
                entity_success = create_or_update_entity(entity_id, entity_config)
                success &= entity_success
            else:
                print(f"❌ Unsupported entity action: {action} for {entity_id}")
                success = False
        
        if success:
            print("✅ All entities processed successfully")
            
            print("Requesting Home Assistant configuration reload...")
            reload_success = reload_home_assistant_config()
            if reload_success:
                print("✅ Home Assistant configuration reload requested")
            else:
                print("⚠ Could not request configuration reload - please restart Home Assistant manually")
                
        else:
            print("❌ Some entities failed to process")
        
        return success
        
    except Exception as e:
        print(f"❌ Error processing entities: {e}")
        return False

def reload_home_assistant_config():
    try:
        if REQUESTS_AVAILABLE:
            success, response = supervisor_api_call('services/homeassistant/reload_config_entry', 'POST', {})
            if success:
                return True
            
            success, response = supervisor_api_call('services/homeassistant/restart', 'POST', {})
            if success:
                print("⚠ Full restart initiated instead of config reload")
                return True
        
        return False
        
    except Exception as e:
        print(f"Config reload error: {e}")
        return False

def update_lovelace_resources(manifest):
    print("=== Updating Lovelace Resources via SSH ===")

    resources_config = manifest.get('lovelace_resources')

    if not resources_config:
        print("No Lovelace resources to update")
        return True

    if isinstance(resources_config, list):
        resources = resources_config
    elif isinstance(resources_config, dict):
        values = list(resources_config.values())
        if values and all(isinstance(v, dict) and 'url' in v for v in values):
            resources = values
        else:
            resources = [resources_config]
    else:
        print(f"ERROR: lovelace_resources unexpected type {type(resources_config)}")
        return False

    try:
        resources_file = '/config/.storage/lovelace_resources'
        
        existing_items = []
        
        read_cmd = [
            'ssh', '-i', '/config/.energy_manager/ssh_key',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            f'hassio@a0d7b954-ssh.local.hass.io',
            f'sudo cat {resources_file}'
        ]
        
        try:
            result = subprocess.run(read_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                resources_data = json.loads(result.stdout)
                existing_items = resources_data.get('data', {}).get('items', [])
            else:
                print(f"Warning: Failed to read existing resources via SSH: {result.stderr}")
                resources_data = {
                    "version": 1,
                    "minor_version": 1,
                    "key": "lovelace_resources",
                    "data": {
                        "items": []
                    }
                }
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Could not retrieve existing Lovelace resources: {e}")
            resources_data = {
                "version": 1,
                "minor_version": 1,
                "key": "lovelace_resources",
                "data": {
                    "items": []
                }
            }

        
        for i, resource in enumerate(resources):
            if not isinstance(resource, dict):
                print(f"ERROR: Resource {i} is not a dict, got {type(resource)}: {resource}")
                continue
            
            url = resource.get('url')
            resource_type = resource.get('type', 'module')
            
            if not url:
                print("ERROR: Resource missing URL")
                continue
            
            existing = next((item for item in existing_items if item.get('url') == url), None)
            
            if existing:
                print(f"Resource {url} already exists, updating...")
                existing['type'] = resource_type
            else:
                print(f"Adding new resource: {url}")
                new_resource = {
                    "id": str(uuid.uuid4()).replace('-', ''),
                    "url": url,
                    "type": resource_type
                }
                existing_items.append(new_resource)
        
        resources_data['version'] = 1
        resources_data['minor_version'] = 1

        local_temp_file = '/config/.energy_manager/lovelace_resources_temp.json'
        with open(local_temp_file, 'w') as f:
            json.dump(resources_data, f, indent=2)

        print("Copying Lovelace resources to temp directory via SSH...")
        copy_to_temp_cmd = [
            'ssh', '-i', '/config/.energy_manager/ssh_key',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            f'hassio@a0d7b954-ssh.local.hass.io',
            'cat > /tmp/lovelace_resources.json'
        ]
        
        with open(local_temp_file, 'r') as f:
            result = subprocess.run(copy_to_temp_cmd, input=f.read(), text=True, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            error_msg = f"Failed to copy resources to temp: {result.stderr}"
            print(f"❌ {error_msg}")
            update_dashboard_status(error_msg, "error")
            return False
            
        print("✅ Lovelace resources copied to temp directory")

        print("Moving Lovelace resources to .storage directory...")
        move_cmd = [
            'ssh', '-i', '/config/.energy_manager/ssh_key',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            f'hassio@a0d7b954-ssh.local.hass.io',
            f'sudo mv /tmp/lovelace_resources.json {resources_file}'
        ]
        
        result = subprocess.run(move_cmd, capture_output=True, text=True, timeout=15)
        
        if result.returncode != 0:
            error_msg = f"Failed to move resources to final location: {result.stderr}"
            print(f"❌ {error_msg}")
            update_dashboard_status(error_msg, "error")
            return False
        
        print(f"✅ Updated Lovelace resources with {len(resources)} items")
        
        if os.path.exists(local_temp_file):
            os.remove(local_temp_file)
            print("✅ Local temp file cleaned up")
            
        return True
    
    except Exception as e:
        print(f"❌ Error updating Lovelace resources via SSH: {e}")
        return False

try:
    cleanup_old_backups()
    
    args = parse_arguments()
    
    if args.force_reinstall:
        update_dashboard_status("Force reinstalling current version...", "info")
        print("Force reinstall requested - bypassing version check")
    else:
        update_dashboard_status("Checking for Energy Manager updates...", "info")
    
    update_checker = EnergyManagerUpdateChecker(branch=args.branch)
    file_merger = EnergyManagerFileMerger()
    os.makedirs('/config/.energy_manager', exist_ok=True)
    result = update_checker.check_for_updates(force=args.force_reinstall)
    if result.get('error'):
        raise RuntimeError(result['error'])
    should_update = result['update_available']
    installed_version = version_tuple(result['current_version'])

    if not should_update:
        print("No new Energy Manager version; no changes made")
        update_dashboard_status(
            "No updates available. System is up to date.",
            "success"
        )
        with open('/config/.energy_manager/update_result.txt', 'w') as f:
            f.write("no_updates")
        sys.exit(0)
    
    manifest = result.get('manifest')
    if not manifest:
        error_msg = "Failed to download update manifest"
        print(error_msg)
        update_status_failed(error_msg)
        with open('/config/.energy_manager/update_result.txt', 'w') as f:
            f.write("error:Failed to download manifest")
        sys.exit(1)
    
    if args.force_reinstall:
        print(f"Force reinstalling version {manifest['version']}...")
    else:
        print(f"Starting update to version {manifest['version']}...")
    
    update_dashboard_status(f"Updating to version {manifest['version']}...", "info")
    success = True
    selected_files = {}
    for filepath, file_info in manifest['files'].items():
        selected_files[filepath] = file_info
    selected_manifest = dict(manifest, files=selected_files)
    for filepath, file_info in selected_files.items():
        local_path = filepath if filepath.startswith('/share/') else os.path.join('/config', filepath)
        print(f"Processing {filepath}...")
        update_dashboard_status(f"Updating file: {filepath}...", "info")
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        temp_path = f"{local_path}.temp"
        if not update_checker.download_file(filepath, temp_path):
            success = False
            continue
        try:
            with open(temp_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            action = file_info.get('action', 'merge')
            if action == 'replace':
                file_success = file_merger.replace_file(local_path, new_content, manifest['version'])
            elif action == 'merge':
                file_success = file_merger.update_file(local_path, new_content,
                                                       file_info.get('sections', []), manifest['version'])
            elif action == 'create':
                file_success = (True if os.path.exists(local_path) else
                                file_merger.replace_file(local_path, new_content, manifest['version']))
            else:
                raise ValueError(f'Unknown action: {action}')
            success &= bool(file_success)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    if success and manifest.get('apps'):
        print("Reconciling Supervisor Apps...")
        update_dashboard_status("Reconciling Supervisor Apps...", "info")
        try:
            from em_apps_manager import reconcile
            reconcile(manifest, repair=True)
        except Exception as e:
            print(f"❌ App reconciliation failed: {e}")
            success = False

    if not success:
        raise RuntimeError(
            "Required files or Supervisor App reconciliation failed"
        )

   
    print("Processing special file operations...")
    update_dashboard_status("Processing special file operations...", "info")
    special_files_success = handle_special_files(selected_manifest)
    success &= special_files_success

    print("Processing entity updates...")
    update_dashboard_status("Processing entity updates...", "info")
    entities_success = handle_entities_update(selected_manifest)
    success &= entities_success

    print("Processing Lovelace resource updates...")
    update_dashboard_status("Processing Lovelace resource updates...", "info")
    lovelace_success = update_lovelace_resources(dict(manifest, lovelace_resources=[
        resource for resource in manifest.get('lovelace_resources', [])
        ]))
    success &= lovelace_success
    
    update_flows = ('nodered_flows' in manifest and True)
    if update_flows:
        flows_info = manifest['nodered_flows']
        download_url = flows_info.get('download_url')
        
        if download_url:
            print("Processing Node-RED flows...")
            update_dashboard_status("Updating Node-RED flows via SSH...", "info")
            
            flows_temp_path = '/config/.energy_manager/downloaded_flows.json'
            
            if update_checker.download_file(download_url, flows_temp_path):
                if validate_flows_json(flows_temp_path):
                    with open(flows_temp_path, 'r') as f:
                        new_flows_content = f.read()
                    
                    print("Updating Node-RED flows via SSH...")
                    ssh_result = update_flows_via_ssh(new_flows_content, manifest['version'])
                    
                    if ssh_result:
                        print("✓ Node-RED flows updated via SSH")
                        if not REQUESTS_AVAILABLE:
                            _restart_nodered_via_ssh()
                    else:
                        print("✗ SSH flows update failed")
                        success = False
                    
                else:
                    print("✗ Downloaded Node-RED flows file is invalid JSON")
                    update_dashboard_status("Downloaded Node-RED flows file is invalid JSON", "error")
                    success = False
                
                if os.path.exists(flows_temp_path):
                    os.remove(flows_temp_path)
            else:
                print("✗ Failed to download Node-RED flows")
                update_dashboard_status("Failed to download Node-RED flows", "error")
                success = False
        else:
            print("✗ No download URL specified for Node-RED flows")
            update_dashboard_status("No download URL specified for Node-RED flows", "error")
            success = False
    
    if success and update_flows:
        print("Restarting Node-RED to pick up changes...")
        update_dashboard_status("Restarting Node-RED...", "info")
        
        try:
            if REQUESTS_AVAILABLE:
                url = "http://supervisor/addons/a0d7b954_nodered/restart"
                headers = {
                    'Authorization': 'Bearer ' + os.environ.get('SUPERVISOR_TOKEN', ''),
                    'Content-Type': 'application/json'
                }
                
                response = requests.post(url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    print("✅ Node-RED restart initiated")
                else:
                    print(f"❌ Node-RED restart failed: {response.status_code}")
                    print("Please restart Node-RED manually")
                    
            else:
                print("⚠ Please restart Node-RED manually - requests not available")
                
        except Exception as e:
            print(f"❌ Node-RED restart error: {e}")
            print("Please restart Node-RED manually")
  
    if success:
        print("Processing HACS dependencies...")
        update_dashboard_status(
            "Processing HACS dependencies...",
            "info"
        )
        try:
            hacs_changes = sync_hacs_components_via_ssh(
                manifest.get('hacs_components', [])
            )
            print(
                f"✅ HACS dependencies reconciled: "
                f"{len(hacs_changes)} changes"
            )

            # This file is deployed from the manifest earlier in the
            # update. Only normal updates and Force Reinstall reach here.
            integration_script = (
                '/config/scripts/configure_em_integrations.py'
            )

            if not os.path.isfile(integration_script):
                raise RuntimeError(
                    'Required integration configuration script missing: '
                    + integration_script
                )

            print("Reconciling MQTT and Node-RED Companion...")
            subprocess.run(
                [sys.executable, '-u', integration_script],
                check=True
            )

            print("✅ Required Home Assistant integrations reconciled")
        except Exception as e:
            print(f"❌ Dependency reconciliation failed: {e}")
            update_dashboard_status(
                f"HACS dependency update failed: {e}",
                "error"
            )
            success = False

    if success:
        update_checker.set_current_version(manifest['version'])
        with open('/config/.energy_manager/installed_branch.txt', 'w', encoding='utf-8') as f:
            f.write(update_checker.branch + '\n')
        print(f"✅ Update successful: {manifest['version']}")
        update_status_success(manifest['version'])
        
        with open('/config/.energy_manager/update_result.txt', 'w') as f:
            f.write(f"success:{manifest['version']}")
        sys.exit(0)
    else:
        print("❌ Update failed")
        update_status_failed("One or more update steps failed")
        with open('/config/.energy_manager/update_result.txt', 'w') as f:
            f.write("failed")
        sys.exit(1)

except Exception as e:
    print(f"Update process failed: {e}")
    update_status_failed(str(e))
    with open('/config/.energy_manager/update_result.txt', 'w') as f:
        f.write(f"error:{str(e)}")
    sys.exit(1)
