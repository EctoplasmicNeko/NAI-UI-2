import json
from pathlib import Path

from data.paths import CHARACTERS_DIR, UNIVERSAL_QUICK_WEIGHTS_FILE


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _is_valid_quick_weight(item):
    if not isinstance(item, dict):
        return False
    required_keys = {"tag", "value", "min", "max", "negative"}
    return required_keys.issubset(item.keys())


def _normalize_quick_weight(item):
    return {
        "tag": str(item["tag"]).strip(),
        "value": float(item["value"]),
        "min": float(item["min"]),
        "max": float(item["max"]),
        "negative": bool(item["negative"]),
    }


def collect_quick_weights():
    characters_dir = Path(CHARACTERS_DIR)
    if not characters_dir.exists():
        return []

    collected = []
    seen = set()

    for character_path in sorted(characters_dir.glob("*.json")):
        try:
            data = _load_json(character_path)
        except Exception:
            continue

        character = data[0] if isinstance(data, list) and data else data
        if not isinstance(character, dict):
            continue

        quick_weights = character.get("quick_weights") or []
        if not isinstance(quick_weights, list):
            continue

        for item in quick_weights:
            if not _is_valid_quick_weight(item):
                continue
            normalized = _normalize_quick_weight(item)
            key = (
                normalized["tag"],
                normalized["negative"],
                normalized["min"],
                normalized["max"],
            )
            if key not in seen:
                seen.add(key)
                collected.append(normalized)

    return collected


def write_universal_quick_weights(weights):
    UNIVERSAL_QUICK_WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with UNIVERSAL_QUICK_WEIGHTS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(weights, handle, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    weights = collect_quick_weights()
    write_universal_quick_weights(weights)
    print(f"Wrote {len(weights)} universal quick weights to {UNIVERSAL_QUICK_WEIGHTS_FILE}")
