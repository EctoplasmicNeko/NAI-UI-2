from __future__ import annotations

OUTFIT_SLOT_ORDER = ("upper_garment", "lower_garment", "shoes", "socks", "head", "arms", "other")


def normalize_prompt_entry(entry) -> dict[str, object] | None:
    if isinstance(entry, dict):
        tag_text = str(entry.get("tag", "")).strip()
        if not tag_text:
            return None
        try:
            strength_value = float(entry.get("strength", 1.0))
        except (TypeError, ValueError):
            strength_value = 1.0
        return {"tag": tag_text, "strength": strength_value}
    tag_text = str(entry).strip()
    if tag_text:
        return {"tag": tag_text, "strength": 1.0}
    return None


def normalize_prompt_entries(value) -> list[dict[str, object]]:
    if isinstance(value, str):
        entries = []
        for raw_entry in value.split(","):
            entry = raw_entry.strip()
            if not entry:
                continue
            if "::" in entry:
                parts = [part.strip() for part in entry.split("::")]
                try:
                    strength = float(parts[0])
                except (IndexError, ValueError):
                    continue
                for tag_part in parts[1:]:
                    if tag_part:
                        entries.append({"tag": tag_part, "strength": strength})
                continue
            entries.append({"tag": entry, "strength": 1.0})
        return entries
    elif isinstance(value, list):
        raw_entries = value
    else:
        raw_entries = []

    entries = []
    for entry in raw_entries:
        normalized = normalize_prompt_entry(entry)
        if normalized is not None:
            entries.append(normalized)
    return entries


def format_prompt_entries(entries) -> str:
    formatted = []
    for entry in normalize_prompt_entries(entries):
        tag_text = str(entry.get("tag", "")).strip()
        if not tag_text:
            continue
        strength = float(entry.get("strength", 1.0))
        if strength == 1.0:
            formatted.append(tag_text)
        else:
            formatted.append(f"{strength:.1f}::{tag_text}::")
    return ", ".join(formatted)


def empty_outfit_slots() -> dict[str, dict[str, list[dict[str, object]]]]:
    return {slot: {"positive": [], "negative": []} for slot in OUTFIT_SLOT_ORDER}


def normalize_outfit(outfit: dict) -> dict:
    if not isinstance(outfit, dict):
        outfit = {}

    normalized = {
        "name": str(outfit.get("name", "")).strip(),
        "role": str(outfit.get("role") or outfit.get("Role") or "").strip(),
        "modifier": [str(item).strip() for item in outfit.get("modifier", []) if str(item).strip()] if isinstance(outfit.get("modifier", []), list) else [],
        "description": str(outfit.get("description", "")),
        "slots": empty_outfit_slots(),
        "remove": list(outfit.get("remove") or []) if isinstance(outfit.get("remove") or [], list) else [],
    }

    source_slots = outfit.get("slots") if isinstance(outfit.get("slots"), dict) else {}
    for slot in OUTFIT_SLOT_ORDER:
        slot_payload = source_slots.get(slot, {}) if isinstance(source_slots.get(slot, {}), dict) else {}
        old_positive_value = outfit.get(slot, "")
        normalized["slots"][slot] = {
            "positive": normalize_prompt_entries(slot_payload.get("positive", old_positive_value)),
            "negative": normalize_prompt_entries(slot_payload.get("negative", [])),
        }

    return normalized


def compile_outfit_prompt(outfit: dict, polarity: str, suppressed_slots=None) -> str:
    normalized = normalize_outfit(outfit)
    suppressed = set(suppressed_slots or [])
    entries = []
    for slot in OUTFIT_SLOT_ORDER:
        if slot in suppressed:
            continue
        entries.extend(normalized["slots"][slot].get(polarity, []))
    return format_prompt_entries(entries)
