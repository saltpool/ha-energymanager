#!/usr/bin/env python3
"""
Energy Manager File Merger v2.0.0
"""

import re
import os
import json
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import hashlib
import shutil

class EnergyManagerFileMerger:
    def __init__(self, config_dir: str = "/config"):
        self.config_dir = config_dir
        self.backup_dir = os.path.join(config_dir, ".energy_manager", "backups")
        self.managed_sections_file = os.path.join(config_dir, ".energy_manager", "managed-sections.json")
        
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.managed_sections_file), exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(config_dir, '.energy_manager', 'update.log')),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def get_file_checksum(self, filepath: str) -> str:
        hash_md5 = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except FileNotFoundError:
            return ""

    def load_managed_sections(self) -> Dict:
        if os.path.exists(self.managed_sections_file):
            with open(self.managed_sections_file, 'r') as f:
                return json.load(f)
        return {}

    def save_managed_sections(self, sections: Dict):
        with open(self.managed_sections_file, 'w') as f:
            json.dump(sections, f, indent=2)

    def create_backup(self, filepath: str, version: str, timestamp: str = None) -> str:
        if timestamp is None:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        backup_name = f"{timestamp}_{version}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        os.makedirs(backup_path, exist_ok=True)
        
        filename = os.path.basename(filepath)
        backup_filepath = os.path.join(backup_path, f"{filename}.bak")
        
        if os.path.exists(filepath):
            shutil.copy2(filepath, backup_filepath)
            self.logger.info(f"Backed up {filepath} to {backup_filepath}")
        
        return backup_filepath

    def find_managed_sections(self, content: str) -> List[Tuple[str, str, int, int]]:
        sections = []
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            start_match = re.match(r'#\s*===\s*ENERGY_MANAGER_(.+?)_START\s+v([\d.]+)\s*===', line)
            if start_match:
                section_name = start_match.group(1)
                version = start_match.group(2)
                start_line = i
                
                j = i + 1
                while j < len(lines):
                    end_line = lines[j].strip()
                    end_match = re.match(r'#\s*===\s*ENERGY_MANAGER_(.+?)_END\s*===', end_line)
                    if end_match and end_match.group(1) == section_name:
                        sections.append((section_name, version, start_line, j))
                        break
                    j += 1
                
                i = j
            else:
                i += 1
        
        return sections

    def extract_section_content(self, content: str, section_name: str) -> Optional[str]:
        lines = content.split('\n')
        start_pattern = re.compile(r'#\s*===\s*ENERGY_MANAGER_' + re.escape(section_name) + r'_START\s+v[\d.]+\s*===')
        end_pattern = re.compile(r'#\s*===\s*ENERGY_MANAGER_' + re.escape(section_name) + r'_END\s*===')
        
        start_idx = None
        for i, line in enumerate(lines):
            if start_pattern.match(line.strip()):
                start_idx = i
                break
        
        if start_idx is None:
            return None
        
        end_idx = None
        for i in range(start_idx + 1, len(lines)):
            if end_pattern.match(lines[i].strip()):
                end_idx = i
                break
        
        if end_idx is None:
            return None
        
        return '\n'.join(lines[start_idx:end_idx + 1])

    def merge_sections(self, local_filepath: str, remote_content: str, sections_to_update: List[str]) -> str:
        if os.path.exists(local_filepath):
            with open(local_filepath, 'r', encoding='utf-8') as f:
                local_content = f.read()
        else:
            local_content = ""
        
        if not local_content.strip():
            return remote_content
        
        local_lines = local_content.split('\n')
        result_lines = []
        i = 0
        
        while i < len(local_lines):
            line = local_lines[i].strip()
            
            start_match = re.match(r'#\s*===\s*ENERGY_MANAGER_(.+?)_START\s+v[\d.]+\s*===', line)
            if start_match:
                section_name = start_match.group(1)
                
                if section_name in sections_to_update:
                    with open('/config/debug_merge.txt', 'a') as f:
                        f.write(f"[{datetime.now()}] Attempting to extract section {section_name}\n")
                    
                    new_section = self.extract_section_content(remote_content, section_name)
                    
                    with open('/config/debug_merge.txt', 'a') as f:
                        f.write(f"[{datetime.now()}] extract_section_content returned: {new_section is not None}\n")
                        if new_section is None:
                            f.write(f"[{datetime.now()}] Section not found in remote content\n")
                        else:
                            f.write(f"[{datetime.now()}] Found section, length: {len(new_section)} chars\n")
                    
                    if new_section:
                        result_lines.extend(new_section.split('\n'))
                        with open('/config/debug_merge.txt', 'a') as f:
                            f.write(f"[{datetime.now()}] SUCCESS: Updated section {section_name}\n")
                        self.logger.info(f"Updated section: {section_name}")
                    else:
                        result_lines.append(local_lines[i])
                        with open('/config/debug_merge.txt', 'a') as f:
                            f.write(f"[{datetime.now()}] FAILED: Keeping original section {section_name}\n")
                        self.logger.warning(f"New version of section {section_name} not found, keeping original")
                    
                    j = i + 1
                    while j < len(local_lines):
                        end_line = local_lines[j].strip()
                        end_match = re.match(r'#\s*===\s*ENERGY_MANAGER_(.+?)_END\s*===', end_line)
                        if end_match and end_match.group(1) == section_name:
                            break
                        j += 1
                    i = j + 1
                else:
                    result_lines.append(local_lines[i])
                    i += 1
            else:
                result_lines.append(local_lines[i])
                i += 1
        
        return '\n'.join(result_lines)

    def replace_file(self, filepath: str, new_content: str, version: str, timestamp: str = None) -> bool:
        try:
            self.create_backup(filepath, version, timestamp)
            
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            self.logger.info(f"Replaced {filepath} with new version")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to replace {filepath}: {e}")
            return False

    def update_file(self, filepath: str, remote_content: str, sections_to_update: List[str], current_version: str, timestamp: str = None) -> bool:
        try:
            self.create_backup(filepath, current_version, timestamp)
            
            merged_content = self.merge_sections(filepath, remote_content, sections_to_update)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(merged_content)
            
            managed_sections = self.load_managed_sections()
            if filepath not in managed_sections:
                managed_sections[filepath] = {}
            
            for section in sections_to_update:
                managed_sections[filepath][section] = {
                    'version': current_version,
                    'updated': datetime.now().isoformat()
                }
            
            self.save_managed_sections(managed_sections)
            
            self.logger.info(f"Successfully updated {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update {filepath}: {str(e)}")
            return False

    def validate_yaml_syntax(self, filepath: str) -> bool:
        try:
            import yaml
            with open(filepath, 'r') as f:
                yaml.safe_load(f)
            return True
        except Exception as e:
            self.logger.error(f"YAML validation failed for {filepath}: {str(e)}")
            return False

    def rollback_file(self, filepath: str, backup_version: str) -> bool:
        try:
            backup_path = None
            for backup_dir in os.listdir(self.backup_dir):
                if backup_version in backup_dir:
                    filename = os.path.basename(filepath)
                    potential_backup = os.path.join(self.backup_dir, backup_dir, f"{filename}.bak")
                    if os.path.exists(potential_backup):
                        backup_path = potential_backup
                        break
            
            if not backup_path:
                self.logger.error(f"Backup not found for {filepath} version {backup_version}")
                return False
            
            shutil.copy2(backup_path, filepath)
            self.logger.info(f"Rolled back {filepath} to version {backup_version}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to rollback {filepath}: {str(e)}")
            return False
