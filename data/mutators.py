"""Persistent enable switches shared by character and global prompt mutators."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile


def is_active(entry: dict) -> bool:
    value = entry.get("active", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off", ""}
    return True if value is None else bool(value)


def chance_groups_with_active(groups):
    if not isinstance(groups, list) or not groups:
        return groups
    if all(isinstance(entry, dict) and "alternatives" not in entry for entry in groups):
        groups = [groups]
    result = []
    for index, group in enumerate(groups, 1):
        if isinstance(group, list):
            group = {"name": f"Chance {index}", "alternatives": group}
        if isinstance(group, dict) and "alternatives" in group:
            group = dict(group)
            group.setdefault("active", True)
        result.append(group)
    return result


def document_objects(payload) -> list[tuple[tuple[int, ...], dict]]:
    if isinstance(payload, dict):
        return [((), payload)]
    if isinstance(payload, list):
        return [((index,), value) for index, value in enumerate(payload) if isinstance(value, dict)]
    raise ValueError("Expected a JSON object or list of objects.")


def add_active_fields(payload, keys: tuple[str, ...]) -> bool:
    changed = False
    for _, document in document_objects(payload):
        for key in keys:
            entries = document.get(key)
            if key == "chance_tag":
                normalized = chance_groups_with_active(entries)
                if normalized != entries:
                    document[key] = entries = normalized
                    changed = True
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict) and "active" not in entry:
                        entry["active"] = True
                        changed = True
    return changed


def read_document(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_document(path: Path, payload) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def migrate_file(path: Path, keys: tuple[str, ...]):
    payload = read_document(path)
    if add_active_fields(payload, keys):
        write_document(path, payload)
    return payload


@dataclass(frozen=True)
class MutatorEntry:
    path: Path
    location: tuple[str | int, ...]
    value: dict
    kind: str
    scope: str


def entries_from_document(path: Path, payload, key: str, kind: str, scope: str) -> list[MutatorEntry]:
    result = []
    for prefix, document in document_objects(payload):
        entries = document.get(key)
        if isinstance(entries, list):
            for index, entry in enumerate(entries):
                if isinstance(entry, dict):
                    result.append(MutatorEntry(
                        path, (*prefix, key, index), deepcopy(entry), kind, scope,
                    ))
    return result


def set_entry_active(entry: MutatorEntry, active: bool):
    payload = read_document(entry.path)
    current = payload
    try:
        for part in entry.location:
            current = current[part]
    except (KeyError, IndexError, TypeError) as exception:
        raise ValueError("This mutator has changed or been removed. Refresh and try again.") from exception
    if current != entry.value:
        raise ValueError("This mutator has changed. Refresh and try again.")
    current["active"] = bool(active)
    write_document(entry.path, payload)
    return payload


def normalize_label(value) -> str:
    return str(value or "").strip().lower()


def effective_labels(labels, forced_target_label=None) -> list[str]:
    if not isinstance(labels, list):
        labels = [labels]
    result = [
        str((entry.get("label", "") if isinstance(entry, dict) else entry) or "").strip()
        for entry in labels
    ]
    result = [label for label in result if label]
    if forced_target_label:
        result = [label for label in result if normalize_label(label) not in {"male", "female"}]
        result.append(forced_target_label)
    return result


def tag_scope_matches(targets, labels, forced_target_label=None) -> bool:
    if not isinstance(targets, list):
        targets = [targets]
    targets = {normalize_label(label) for label in targets if normalize_label(label)}
    if not targets:
        return True
    if forced_target_label:
        return normalize_label(forced_target_label) in targets
    return not targets.isdisjoint(normalize_label(label) for label in labels)
