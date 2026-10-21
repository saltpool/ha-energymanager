#!/usr/bin/env python3
"""
Fix duplicated Home Assistant utility_meter/template sensors that appear as *_2
by removing the original base entity_id entries from the entity registry,
then restarting Home Assistant.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REGISTRY_PATH = Path("/config/.storage/core.entity_registry")

BASE_ENTITY_IDS = [
    "sensor.electricity_export_profit_daily",
    "sensor.electricity_export_profit_hourly",
    "sensor.electricity_export_profit_monthly",
    "sensor.electricity_import_cost_daily",
    "sensor.electricity_import_cost_hourly",
    "sensor.electricity_import_cost_monthly",
]

DUP_SUFFIX = "_2"

def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def parse_args():
    p = argparse.ArgumentParser(description="Fix duplicated HA utility meter entities")
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Proceed even if *_2 entities are not present in core.entity_registry. "
            "Use this when duplicates exist in the UI but not in the registry."
        ),
    )
    return p.parse_args()


def load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die(f"Registry file not found: {path}")
    except json.JSONDecodeError as e:
        die(f"Registry file is not valid JSON: {e}")

def atomic_write_json(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)

def backup_file(path: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(path.name + f".bak-{ts}")
    shutil.copy2(path, backup_path)
    return backup_path

def get_registry_entities(registry: dict) -> list[dict]:
    entities = registry.get("data", {}).get("entities")
    if not isinstance(entities, list):
        die("Unexpected registry format: registry['data']['entities'] is not a list")
    return [e for e in entities if isinstance(e, dict)]


def entity_id_set(entities: list[dict]) -> set[str]:
    return {
        e["entity_id"]
        for e in entities
        if isinstance(e.get("entity_id"), str)
    }

def should_proceed(entity_ids: set[str], force: bool):
    bases_present = [b for b in BASE_ENTITY_IDS if b in entity_ids]
    dups_present = [f"{b}{DUP_SUFFIX}" for b in BASE_ENTITY_IDS if f"{b}{DUP_SUFFIX}" in entity_ids]

    if not bases_present:
        return False, bases_present, dups_present, (
            "None of the target base entities exist in the entity registry."
        )

    if dups_present:
        return True, bases_present, dups_present, (
            "Detected base + *_2 entity pairs in the entity registry."
        )

    if force:
        return True, bases_present, dups_present, (
            "Force mode enabled: base entities exist in the registry but *_2 entities "
            "are not registered (likely runtime-only)."
        )

    return False, bases_present, dups_present, (
        "Base entities exist in the registry, but no *_2 entities were found there.\n"
        "If duplicates exist in the UI, re-run with --force."
    )

def remove_base_entities(registry: dict, to_remove: set[str]) -> int:
    entities = registry["data"]["entities"]
    kept = []
    removed = 0

    for ent in entities:
        eid = ent.get("entity_id") if isinstance(ent, dict) else None
        if eid in to_remove:
            removed += 1
            continue
        kept.append(ent)

    registry["data"]["entities"] = kept
    return removed

def restart_home_assistant() -> bool:
    ha_cli = shutil.which("ha")
    if ha_cli:
        try:
            subprocess.run([ha_cli, "core", "restart"], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"WARNING: ha core restart failed: {e}", file=sys.stderr)
    return False

def main():
    args = parse_args()

    print(f"Reading registry: {REGISTRY_PATH}")
    registry = load_json(REGISTRY_PATH)
    entities = get_registry_entities(registry)
    entity_ids = entity_id_set(entities)

    proceed, bases_present, dups_present, reason = should_proceed(entity_ids, args.force)

    if not proceed:
        print("Not proceeding.")
        print(reason)
        sys.exit(0)

    print(reason)

    print("\nBase entities present in registry:")
    for b in bases_present:
        print(f"  - {b}")

    if dups_present:
        print("Duplicate *_2 entities present in registry:")
        for d in dups_present:
            print(f"  - {d}")
    else:
        print("No *_2 entities present in registry (may be runtime-only).")

    print("\nPre-flight warning:")
    print("  - The FIRST restart after fixing the entity registry may take several minutes.")
    print('    You may see: "Home Assistant is starting. Not everything will be available..."')
    print("  - This is typically a ONE-OFF while HA reconciles entities and statistics.")
    print("  - Subsequent restarts should return to normal speed.\n")

    to_remove = set(bases_present)

    print("The following entity registry entries WILL be removed:")
    for r in sorted(to_remove):
        print(f"  - {r}")

    backup_path = backup_file(REGISTRY_PATH)
    print(f"\nBackup created: {backup_path}")

    removed = remove_base_entities(registry, to_remove)
    atomic_write_json(REGISTRY_PATH, registry)

    print(f"Updated registry written. Removed {removed} entr{'y' if removed == 1 else 'ies'}.")

    print("\nAttempting Home Assistant restart...")
    if restart_home_assistant():
        print("Restart command issued.")
    else:
        print("Automatic restart unavailable.")
        print("Please restart Home Assistant manually (Settings → System → Restart).")

if __name__ == "__main__":
    main()

