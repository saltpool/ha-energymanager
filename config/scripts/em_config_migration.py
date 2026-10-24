#!/usr/bin/env python3
"""Energy Manager v2 configuration adoption preflight (read-only, stdlib only).

This is a deliberately non-mutating first stage. It inventories the YAML files
that an existing Home Assistant installation uses, identifies conflicts with
Energy Manager's current managed configuration, and produces a JSON report.
It never rewrites, relocates, or validates HA-specific YAML semantics.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT_FILES = (
    'configuration.yaml', 'automations.yaml', 'scripts.yaml',
    'template.yaml', 'group.yaml', 'utility_meter.yaml', 'secrets.yaml',
)
# Include forms must be inspected, not followed blindly: they may represent
# directories, missing files, or paths outside /config.
INCLUDE_RE = re.compile(
    r'!include(?:_dir_(?:list|named|merge_list|merge_named))?\s+([^\s#]+)'
)
TAG_START = re.compile(r'^\s*#\s*===\s*ENERGY_MANAGER_(.+?)_START\s+v[^\s]+\s*===\s*$')
TAG_END = re.compile(r'^\s*#\s*===\s*ENERGY_MANAGER_(.+?)_END\s*===\s*$')
TOP_KEY = re.compile(r'^([A-Za-z_][\w.-]*)(?:\s+[^:]*)?\s*:\s*(?:.*)$')
KEY = re.compile(r'^([A-Za-z_][\w.-]*)\s*:')
DANGEROUS_ROOTS = {'homeassistant', 'automation', 'script', 'template', 'modbus', 'utility_meter', 'group', 'frontend', 'logger'}


def inspect_file(path, root):
    rel = str(path.relative_to(root))
    result = {'file': rel, 'exists': path.is_file(), 'managed_sections': [],
              'top_level_keys': [], 'includes': [], 'issues': []}
    if not path.is_file():
        return result
    try:
        lines = path.read_text(encoding='utf-8-sig').splitlines()
    except (UnicodeError, OSError) as exc:
        result['issues'].append({'severity': 'blocker', 'message': f'Cannot read UTF-8 file: {exc}'})
        return result
    open_tag = None
    section_start = None
    keys = defaultdict(list)
    seen_content = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            seen_content = True
        start = TAG_START.fullmatch(line)
        end = TAG_END.fullmatch(line)
        if start:
            if open_tag is not None:
                result['issues'].append({'severity': 'blocker', 'line': i,
                                         'message': f'Nested Energy Manager tag {start.group(1)}'})
            open_tag = start.group(1)
            section_start = i
        elif end:
            if open_tag != end.group(1):
                result['issues'].append({'severity': 'blocker', 'line': i,
                                         'message': f'Unmatched Energy Manager end tag {end.group(1)}'})
            else:
                result['managed_sections'].append({'name': open_tag, 'start': section_start, 'end': i})
            open_tag = None
            section_start = None
        if not stripped or stripped.startswith('#'):
            continue
        if not line[0].isspace():
            match = TOP_KEY.match(line)
            if match:
                key = match.group(1)
                # This is a heuristic lexical scan; HA YAML can use more
                # complex syntax, so flagged items require review.
                keys[key].append({'line': i, 'managed': open_tag is not None})
        for include in INCLUDE_RE.finditer(line.split('#', 1)[0]):
            target = include.group(1).strip('"\'')
            result['includes'].append({'line': i, 'expression': include.group(0), 'target': target})
    if open_tag is not None:
        result['issues'].append({'severity': 'blocker', 'message': f'Unclosed Energy Manager section {open_tag}'})
    result['top_level_keys'] = [{'name': name, 'occurrences': occurrences}
                                for name, occurrences in sorted(keys.items())]
    for name, occurrences in keys.items():
        if len(occurrences) > 1:
            result['issues'].append({'severity': 'blocker', 'message':
                f'Possible duplicate top-level key {name!r} at lines '
                + ', '.join(str(x['line']) for x in occurrences)})
    result['has_content'] = seen_content
    return result


def scan(root):
    root = root.resolve()
    if not root.is_dir():
        raise RuntimeError(f'Configuration directory does not exist: {root}')
    inspected = {}
    queue = list(ROOT_FILES)
    discovered_includes = []
    while queue:
        rel = queue.pop(0)
        if rel in inspected:
            continue
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            continue
        info = inspect_file(path, root)
        inspected[rel] = info
        for inc in info['includes']:
            target = inc['target']
            candidate = (path.parent / target).resolve()
            inc['within_config'] = candidate.is_relative_to(root)
            inc['exists'] = candidate.exists()
            inc['directory'] = candidate.is_dir()
            discovered_includes.append({'source': rel, **inc})
            if not inc['within_config']:
                info['issues'].append({'severity': 'blocker', 'line': inc['line'],
                                       'message': 'Include points outside /config: ' + target})
                continue
            if candidate.is_file() and candidate.suffix.lower() in ('.yaml', '.yml'):
                queue.append(str(candidate.relative_to(root)))
            elif candidate.is_dir():
                # Only YAML files are relevant; never modify these files.
                for included in sorted(candidate.glob('*.yaml')) + sorted(candidate.glob('*.yml')):
                    queue.append(str(included.resolve().relative_to(root)))
            elif not candidate.exists():
                info['issues'].append({'severity': 'review', 'line': inc['line'],
                                       'message': 'Missing include target: ' + target})
    root_info = inspected['configuration.yaml']
    root_keys = {v['name']: v for v in root_info['top_level_keys']}
    issues = [{'file': rel, **issue}
              for rel, info in inspected.items() for issue in info['issues']]
    if not root_info['exists']:
        issues.append({'file': 'configuration.yaml', 'severity': 'blocker',
                       'message': 'Home Assistant configuration.yaml is missing'})
    for section in root_info['managed_sections']:
        if section['name'] in ('SHELL_COMMANDS', 'SENSORS', 'UPDATE_INPUTS'):
            issues.append({'file': 'configuration.yaml', 'severity': 'review',
                           'message': f'Legacy moved section {section["name"]} can be removed only during a migration'})
    for key in ('homeassistant', 'logger', 'frontend'):
        k = root_keys.get(key)
        if k and k['occurrences']:
            owners = {x['managed'] for x in k['occurrences']}
            if True in owners:
                issues.append({'file': 'configuration.yaml', 'severity': 'review',
                               'message': f'{key}: currently lives inside EM-managed section; move user-specific fields into persistent user-owned configuration before replacing CORE'})
    if not root_info['managed_sections'] and root_info['has_content']:
        issues.append({'file': 'configuration.yaml', 'severity': 'review',
                       'message': 'Populated configuration without EM tags: requires adoption merge, not standard tagged-section replacement'})
    # Report collisions in managed/user namespace without guessing semantics.
    for rel, info in inspected.items():
        for key in info['top_level_keys']:
            if key['name'] in DANGEROUS_ROOTS and len(key['occurrences']) > 1:
                issues.append({'file': rel, 'severity': 'blocker',
                               'message': f'Cannot safely deduplicate {key["name"]!r} without parsing HA YAML'})
    return {
        'schema_version': 1,
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'read-only-preflight', 'config_dir': str(root),
        'files': list(inspected.values()), 'include_references': discovered_includes,
        'issues': issues,
        'counts': {'files_checked': len(inspected),
                   'blockers': sum(x['severity'] == 'blocker' for x in issues),
                   'reviews': sum(x['severity'] == 'review' for x in issues)},
        'next_step': 'Review and design migration actions; no files have been changed.',
    }


def main():
    p = argparse.ArgumentParser(description='Read-only Energy Manager v2 YAML adoption preflight')
    p.add_argument('--config-dir', type=Path, default=Path('/config'))
    p.add_argument('--output', type=Path, default=None,
                   help='Optional path to save machine-readable JSON report')
    p.add_argument('--apply', action='store_true',
                   help='Reserved for the later transactional migrator; currently disabled')
    args = p.parse_args()
    if args.apply:
        p.error('--apply is not implemented: this release is read-only by design')
    report = scan(args.config_dir)
    print('[EM Config] Read-only preflight completed')
    print(f"[EM Config] Checked {report['counts']['files_checked']} files; "
          f"{report['counts']['blockers']} blockers, {report['counts']['reviews']} reviews")
    for issue in report['issues']:
        print(f"[{issue['severity'].upper()}] {issue['file']}: {issue['message']}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'[EM Config] Report written: {args.output}')
    print('[EM Config] No Home Assistant configuration files were changed')
    return 0 if not report['counts']['blockers'] else 2


if __name__ == '__main__':
    sys.exit(main())
