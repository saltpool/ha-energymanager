#!/usr/bin/env python3
"""
Entity Manager for Energy Manager Update System v2.0.0
Handles non-YAML entity updates via Home Assistant API
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import logging
from typing import Dict, List, Optional

class EntityManager:
    def __init__(self, ha_url: str = "http://localhost:8123", ha_token: str = None):
        self.ha_url = ha_url.rstrip('/')
        self.ha_token = ha_token
        self.headers = {
            'Authorization': f'Bearer {ha_token}' if ha_token else '',
            'Content-Type': 'application/json'
        }
        self.logger = logging.getLogger(__name__)

    def _make_request(self, url: str, method: str = 'GET', data: Dict = None) -> Optional[Dict]:
        try:
            req = urllib.request.Request(url)
            
            for key, value in self.headers.items():
                if value:
                    req.add_header(key, value)
            
            if data and method == 'POST':
                req.data = json.dumps(data).encode('utf-8')
                req.get_method = lambda: 'POST'
            
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')
                return {
                    'success': True,
                    'status_code': response.status,
                    'data': json.loads(content) if content else {}
                }
                    
        except urllib.error.HTTPError as e:
            self.logger.error(f"HTTP Error {e.code}: {e.reason}")
            return {'success': False, 'status_code': e.code}
        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_entity_state(self, entity_id: str) -> Optional[Dict]:
        try:
            result = self._make_request(f"{self.ha_url}/api/states/{entity_id}")
            if result and result.get('success'):
                return result.get('data')
            return None
        except Exception as e:
            self.logger.error(f"Failed to get state for {entity_id}: {e}")
            return None

    def update_input_select(self, entity_id: str, options: List[str], preserve_selection: bool = True) -> bool:
        try:
            current_value = None
            if preserve_selection:
                current_state = self.get_entity_state(entity_id)
                if current_state:
                    current_value = current_state.get('state')

            config_name = entity_id.replace('input_select.', '')
            payload = {'options': options}
            
            result = self._make_request(
                f"{self.ha_url}/api/config/input_select/{config_name}",
                method='POST',
                data=payload
            )
            
            if result and result.get('success'):
                if current_value and current_value in options:
                    self.set_input_select_value(entity_id, current_value)
                
                self.logger.info(f"Updated {entity_id} with options: {options}")
                return True
            else:
                self.logger.error(f"Failed to update {entity_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to update input_select {entity_id}: {e}")
            return False

    def set_input_select_value(self, entity_id: str, value: str) -> bool:
        try:
            payload = {
                'entity_id': entity_id,
                'option': value
            }
            
            result = self._make_request(
                f"{self.ha_url}/api/services/input_select/select_option",
                method='POST',
                data=payload
            )
            
            return result and result.get('success')
            
        except Exception as e:
            self.logger.error(f"Failed to set {entity_id} to {value}: {e}")
            return False

    def trigger_automation(self, automation_id: str) -> bool:
        try:
            payload = {'entity_id': automation_id}
            
            result = self._make_request(
                f"{self.ha_url}/api/services/automation/trigger",
                method='POST',
                data=payload
            )
            
            if result and result.get('success'):
                self.logger.info(f"Triggered automation: {automation_id}")
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to trigger automation {automation_id}: {e}")
            return False

    def create_persistent_notification(self, title: str, message: str, notification_id: str = "energy_manager"):
        try:
            payload = {
                "title": title,
                "message": message,
                "notification_id": notification_id
            }
            
            result = self._make_request(
                f"{self.ha_url}/api/services/persistent_notification/create",
                method='POST',
                data=payload
            )
            
            return result and result.get('success')
            
        except Exception as e:
            self.logger.error(f"Failed to create notification: {e}")
            return False

