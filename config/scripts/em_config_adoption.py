#!/usr/bin/env python3
"""Energy Manager v2 adoption planner for existing Home Assistant YAML.

Produces reviewable, non-mutating file previews. This stage intentionally does
not apply changes or trigger Home Assistant restarts. The proposed CORE block
must match config/configuration.yaml in the v2 repository before activation.
"""
import argparse
import difflib
import json
import re
from pathlib import Path

CORE = '''# === ENERGY_MANAGER_CORE_START v2.0.0 ===
default_config:

frontend: !include frontend_config.yaml

automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml
modbus: !include_dir_merge_list modbus/
utility_meter: !include utility_meter.yaml
template: !include template.yaml
group: !include group.yaml

homeassistant: !include homeassistant_config.yaml
logger: !include logger_config.yaml
# === ENERGY_MANAGER_CORE_END ===
'''

# Existing top-level definitions that conflict with CORE and currently need
# manual reconciliation instead of an unsafe automatic merge.
UNSUPPORTED = {'modbus', 'utility_meter', 'template', 'group'}
SIMPLE_INCLUDES = {
    'automation': '!include automations.yaml',
    'script': '!include scripts.yaml',
    'scene': '!include scenes.yaml',
}
TOP = re.compile(r'^([A-Za-z_][\w.-]*)\s*:\s*(.*)$')
CHILD = re.compile(r'^  ([A-Za-z_][\w.-]*)\s*:\s*(.*)$')
TAG = re.compile(r'^\s*#\s*===\s*ENERGY_MANAGER_')


def get_blocks(contents):
    lines = contents.splitlines(keepends=True)
    heads = [(i, m.group(1), m.group(2).strip()) for i, line in enumerate(lines)
             if (m := TOP.match(line.rstrip('\r\n')))]
    return {name: (value, ''.join(lines[i:(heads[pos + 1][0] if pos + 1 < len(heads) else len(lines))]))
            for pos, (i, name, value) in enumerate(heads)}


def children(block):
    found = {}
    for line in block.splitlines()[1:]:
        match = CHILD.match(line)
        if match:
            name = match.group(1)
            if name in found:
                raise ValueError(f'Duplicate nested key {name}')
            found[name] = match.group(2).strip()
    return found


def child_content(block):
    return ''.join(block.splitlines(keepends=True)[1:]).rstrip('\n')


def compose_shared(old_block, key, required_key, required_value):
    if old_block is None:
        return f'{required_key}: {required_value}\n'
    value, block = old_block
    if value:
        raise ValueError(f'{key}: inline value or !include requires manual review')
    options = children(block)
    if required_key in options and options[required_key] != required_value:
        raise ValueError(f'{key}.{required_key} already set to {options[required_key]!r}; manual merge required')
    current = child_content(block)
    if required_key not in options:
        current = f'  {required_key}: {required_value}\n' + (current + '\n' if current else '')
    # Remove the top-level wrapper while retaining the contents and comments.
    return ''.join(line[2:] if line.startswith('  ') else line
                   for line in current.splitlines(keepends=True)).rstrip('\n') + '\n'


def make_plan(root):
    root = root.resolve()
    original = root.joinpath('configuration.yaml').read_text(encoding='utf-8')
    if TAG.search(original) or 'ENERGY_MANAGER_' in original:
        raise ValueError('Existing Energy Manager tags found: use the separate EM v2 migration path')
    blocks = get_blocks(original)
    # Refuse duplicate keys rather than let dict conversion hide them.
    found = [m.group(1) for line in original.splitlines() if (m := TOP.match(line))]
    if len(found) != len(set(found)):
        raise ValueError('Duplicate top-level YAML keys detected')
    conflicts = UNSUPPORTED.intersection(blocks)
    if conflicts:
        raise ValueError('Existing definitions need manual merge: ' + ', '.join(sorted(conflicts)))
    for key, expected in SIMPLE_INCLUDES.items():
        if key in blocks and blocks[key][0] != expected:
            raise ValueError(f'{key}: nonstandard definition; preserve UI editing by reviewing manually')
    if 'default_config' in blocks and blocks['default_config'][0] not in ('', 'null', '~'):
        raise ValueError('default_config has a nonempty value')

    # Keep all unrelated original configuration blocks at the root, untouched.
    # Remove all keys that are represented exactly once in v2 CORE.
    owned = {'default_config', 'frontend', 'homeassistant', 'logger', *SIMPLE_INCLUDES}
    lines = original.splitlines(keepends=True)
    indexes = [(i, m.group(1)) for i, line in enumerate(lines)
               if (m := TOP.match(line.rstrip('\r\n')))]
    remove = set()
    for pos, (start, name) in enumerate(indexes):
        if name in owned:
            end = indexes[pos + 1][0] if pos + 1 < len(indexes) else len(lines)
            remove.update(range(start, end))
    preserved = ''.join(line for i, line in enumerate(lines) if i not in remove).strip()
    result = '# Home Assistant configuration (Energy Manager v2)\n' + CORE
    if preserved:
        result += '\n# Existing Home Assistant configuration (not managed by EM)\n' + preserved + '\n'

    planned = {
        'configuration.yaml': result,
        'homeassistant_config.yaml': compose_shared(
            blocks.get('homeassistant'), 'homeassistant',
            'packages', '!include_dir_named integrations'),
        'frontend_config.yaml': compose_shared(
            blocks.get('frontend'), 'frontend',
            'themes', '!include_dir_merge_named themes'),
        'logger_config.yaml': compose_shared(
            blocks.get('logger'), 'logger',
            'default', 'warning') if 'logger' in blocks else
            'default: warning\nlogs:\n  py.warnings: error\n',
    }
    # Only create missing references; preserve existing Home Assistant UI files.
    defaults = {
        'automations.yaml': '[]\n', 'scripts.yaml': '{}\n',
        'scenes.yaml': '[]\n', 'utility_meter.yaml': '{}\n',
        'template.yaml': '[]\n', 'group.yaml': '{}\n',
    }
    for path, default in defaults.items():
        if not (root / path).exists():
            planned[path] = default
    if (root / 'homeassistant_config.yaml').exists() or (root / 'frontend_config.yaml').exists() or (root / 'logger_config.yaml').exists():
        raise ValueError('One or more destination user-owned include files already exist; manual review required')
    return planned


def main():
    parser = argparse.ArgumentParser(description='Energy Manager v2 non-destructive adoption preview')
    parser.add_argument('--config-dir', type=Path, default=Path('/config'))
    parser.add_argument('--output-dir', type=Path, default=Path('/config/.energy_manager/adoption-preview'))
    args = parser.parse_args()
    try:
        planned = make_plan(args.config_dir)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'[EM Adoption] Cannot safely generate preview: {exc}\n')
    directory = args.output_dir.resolve()
    if directory == args.config_dir.resolve() or not directory.is_relative_to(args.config_dir.resolve()):
        parser.error('Output directory must be a separate folder under --config-dir')
    directory.mkdir(parents=True, exist_ok=True)
    for rel, text in planned.items():
        dest = directory / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
        original = args.config_dir / rel
        old = original.read_text(encoding='utf-8').splitlines(keepends=True) if original.exists() else []
        diff = ''.join(difflib.unified_diff(old, text.splitlines(keepends=True),
                       fromfile='current/' + rel, tofile='preview/' + rel))
        (directory / (rel + '.diff')).write_text(diff, encoding='utf-8')
        print(f'[EM Adoption] Preview: {rel} ({"modified" if original.exists() else "new"})')
    manifest = {'stage': 'preview-only', 'files': list(planned),
                'note': 'Do not copy previews over configuration.yaml. The v2 updater must be migrated first.'}
    (directory / 'plan.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('[EM Adoption] No live Home Assistant configuration was changed.')


if __name__ == '__main__':
    main()
