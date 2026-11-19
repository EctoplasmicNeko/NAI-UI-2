"""Loading and saving of the global character label group definitions.

The definitions file stores per group settings alongside the label entries as
``{"groups": [...], "labels": [{"category", "label"}, ...]}``.
"""

from __future__ import annotations

import json
from pathlib import Path

from data.character_labels import label_category, label_value

MANDATORY_LABEL_CATEGORIES = {"Gender", "Sort Priority"}
ADDITIONAL_LABEL_CATEGORY = "Additional"


def _normalize_definitions(entries) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        return []
    definitions = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        category = str(entry.get("category") or "General").strip() or "General"
        key = (category, label)
        if not label or key in seen:
            continue
        seen.add(key)
        definitions.append({"category": category, "label": label})
    return definitions


def _normalize_group_settings(groups, definitions) -> dict[str, bool]:
    settings: dict[str, bool] = {}
    if isinstance(groups, list):
        for entry in groups:
            if isinstance(entry, dict):
                name = str(entry.get("name") or entry.get("category") or "").strip()
                include = entry.get("include_in_filters", True)
            else:
                name = str(entry or "").strip()
                include = True
            if name:
                settings[name] = bool(include)
    elif isinstance(groups, dict):
        for name, include in groups.items():
            name = str(name or "").strip()
            if name:
                settings[name] = bool(include)
    for definition in definitions:
        settings.setdefault(definition["category"], True)
    return settings


def _read_payload(labels_path: Path):
    path = Path(labels_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def load_character_label_data(labels_path: Path) -> tuple[list[dict[str, str]], dict[str, bool]]:
    """Return the label definitions and the per group settings for ``labels_path``."""
    payload = _read_payload(labels_path)
    if not isinstance(payload, dict):
        payload = {}
    definitions = _normalize_definitions(payload.get("labels"))
    group_settings = _normalize_group_settings(payload.get("groups"), definitions)
    return definitions, group_settings


def load_character_label_definitions(labels_path: Path) -> list[dict[str, str]]:
    return load_character_label_data(labels_path)[0]


def load_label_group_settings(labels_path: Path) -> dict[str, bool]:
    return load_character_label_data(labels_path)[1]


def group_names(definitions, group_settings=None) -> list[str]:
    """Return all group names in case-insensitive alphabetical order."""
    names = []
    for definition in definitions or []:
        category = definition.get("category") if isinstance(definition, dict) else None
        if category and category not in names:
            names.append(category)
    for name in (group_settings or {}):
        if name and name not in names:
            names.append(name)
    return sorted(names, key=str.casefold)


def save_character_label_data(labels_path: Path, definitions, group_settings=None) -> None:
    path = Path(labels_path)
    normalized_definitions = _normalize_definitions(definitions)
    settings = _normalize_group_settings(group_settings, normalized_definitions)
    payload = {
        "groups": [
            {"name": name, "include_in_filters": bool(settings.get(name, True))}
            for name in group_names(normalized_definitions, settings)
        ],
        "labels": normalized_definitions,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def group_is_filterable(category: str, group_settings=None) -> bool:
    """Groups default to being filterable unless explicitly turned off."""
    if not group_settings:
        return True
    return bool(group_settings.get(str(category or "").strip(), True))


def filterable_label_values(labels, group_settings=None) -> list[str]:
    """Label values of ``labels`` limited to groups that opted into label filters."""
    if not isinstance(labels, list):
        return []
    values = []
    for label_entry in labels:
        value = label_value(label_entry)
        if not value or value in values:
            continue
        if not group_is_filterable(label_category(label_entry), group_settings):
            continue
        values.append(value)
    return values
