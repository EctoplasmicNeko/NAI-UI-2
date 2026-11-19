"""Universal label associations: prompt mutators applied based on a character's labels."""

from __future__ import annotations

import json
from pathlib import Path
from data.mutators import is_active, write_document

LABEL_MATCH_ALL = "all"
LABEL_MATCH_NONE = "none"
LABEL_MATCH_MODES = (LABEL_MATCH_ALL, LABEL_MATCH_NONE)


def _clean_strings(values) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def normalize_label_triggers(groups) -> list[list[str]]:
    if not isinstance(groups, list):
        return []
    normalized = []
    for group in groups:
        labels = _clean_strings(group if isinstance(group, list) else [group])
        if labels:
            normalized.append(labels)
    return normalized


def _normalize_inject(entries) -> list[dict]:
    if not isinstance(entries, list):
        return []
    normalized = []
    for entry in entries:
        if isinstance(entry, dict):
            tag = str(entry.get("tag") or "").strip()
            if not tag:
                continue
            try:
                strength = float(entry.get("strength", 1.0))
            except (TypeError, ValueError):
                strength = 1.0
            normalized.append({"tag": tag, "strength": strength})
        else:
            tag = str(entry or "").strip()
            if tag:
                normalized.append({"tag": tag, "strength": 1.0})
    return normalized


def normalize_label_association(association) -> dict | None:
    if not isinstance(association, dict):
        return None
    match = str(association.get("match") or LABEL_MATCH_ALL).strip().lower()
    if match not in LABEL_MATCH_MODES:
        match = LABEL_MATCH_ALL
    blacklist = _clean_strings(association.get("blacklist"))
    remove_blacklist = association.get("remove_blacklist", [])
    if isinstance(remove_blacklist, bool):
        remove_blacklist = blacklist if remove_blacklist else []
    return {
        "name": str(association.get("name") or "").strip(),
        "active": is_active(association),
        "label_triggers": normalize_label_triggers(association.get("label_triggers")),
        "match": match,
        "inject": _normalize_inject(association.get("inject")),
        "blacklist": blacklist,
        "remove_blacklist": _clean_strings(remove_blacklist),
        "remove": _clean_strings(association.get("remove")),
        "negative_injection": bool(association.get("negative_injection", False)),
    }


def load_label_associations(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = payload.get("label_associations") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    return [normalized for normalized in map(normalize_label_association, entries) if normalized]


def save_label_associations(path: Path, associations) -> None:
    path = Path(path)
    normalized = [
        entry
        for entry in map(normalize_label_association, associations or [])
        if entry and entry["label_triggers"]
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    write_document(path, {"label_associations": normalized})


def label_association_matches(association, labels, normalize=None) -> bool:
    """Return whether ``labels`` satisfy the association's label trigger groups.

    ``all``: every group shares at least one label with ``labels``.
    ``none``: ``labels`` contains none of the labels listed in any group.
    Associations without any trigger labels never match.
    """
    normalize = normalize or (lambda value: str(value or "").strip().casefold())
    groups = [
        {normalize(label) for label in group if normalize(label)}
        for group in normalize_label_triggers(association.get("label_triggers"))
    ]
    groups = [group for group in groups if group]
    if not groups:
        return False
    character_labels = {normalize(label) for label in labels or [] if normalize(label)}
    if association.get("match") == LABEL_MATCH_NONE:
        return all(character_labels.isdisjoint(group) for group in groups)
    return all(not character_labels.isdisjoint(group) for group in groups)
