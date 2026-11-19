import json
import math
import os
import sys
import warnings
from copy import deepcopy
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtCore import QObject, Signal

from data.paths import CONFIG_DIR, IMAGES_DIR, CHARACTERS_DIR, PRESETS_DIR, PORTRAITS_DIR, ALT_PORTRAITS_DIR, REFERENCE_DIR, WILDCARDS_DIR, UNIVERSAL_QUICK_WEIGHTS_FILE
from signaling.refresh_character_lists import refresh_character_lists_signal
from signaling.debug_signal import debug_error, debug_info, debug_warning
from data.mutators import migrate_file, read_document, write_document

VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

data_cache: dict = {}
character_cache: dict = {}
character_source_paths: dict[str, Path] = {}
wildcard_cache: dict = {}
universal_quick_weights_cache: list = []

def packaged_path(relative_path: str) -> Path:
    """
    Returns a path to a bundled resource.
    - In PyInstaller builds: uses sys._MEIPASS
    - In dev: falls back to project-ish root (parents[1] from this file)
    """
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_dir / relative_path

def _load_json_from_file(json_path: Path) -> dict:
    # Use utf-8-sig to transparently handle UTF-8 files with or without BOM.
    with open(json_path, "r", encoding="utf-8-sig") as file_handle:
        return json.load(file_handle)


def _warn_invalid_json(json_path: Path, exception: Exception) -> None:
    warnings.warn(f"Invalid JSON in {json_path.name}: {exception}", UserWarning)


def _load_all_json_in_dir(source_dir: Path, target_cache: dict, label: str) -> None:
    if not source_dir.exists():
        return
    for filename in os.listdir(source_dir):
        if not filename.endswith(".json"):
            continue
        key = os.path.splitext(filename)[0]
        json_path = source_dir / filename
        try:
            target_cache[key] = _load_json_from_file(json_path)
        except Exception as exception:
            _warn_invalid_json(json_path, exception)

def load_all() -> dict:
    """
    Load order:
      1) Bundled defaults from data/config (inside build, or dev fallback)
      2) Disk overrides from CONFIG_DIR
      3) Disk overrides from PRESETS_DIR
    """
    data_cache.clear()

    # 1) Built-in defaults bundled into the app build
    bundled_config_dir = packaged_path("data/config")
    _load_all_json_in_dir(bundled_config_dir, data_cache, "defaults")

    # 2) User / disk config overrides (wherever CONFIG_DIR points)
    _load_all_json_in_dir(Path(CONFIG_DIR), data_cache, "config")

    # 3) Presets overrides (wherever PRESETS_DIR points)
    _load_all_json_in_dir(Path(PRESETS_DIR), data_cache, "presets")

    return data_cache

def load_characters() -> dict:
    character_cache.clear()
    character_source_paths.clear()

    characters_dir = Path(CHARACTERS_DIR)
    if not characters_dir.exists():
        return character_cache

    for filename in os.listdir(characters_dir):
        if not filename.endswith(".json"):
            continue

        file_path = characters_dir / filename
        try:
            loaded = migrate_file(file_path, ("tag_associations", "chance_tag"))
        except Exception as exception:
            _warn_invalid_json(file_path, exception)
            continue

        character = loaded[0] if isinstance(loaded, list) and loaded else loaded
        if not isinstance(character, dict):
            warnings.warn(f"Skipping non-object JSON payload in {file_path.name}.", UserWarning)
            continue

        character_id = character.get("nameID") or os.path.splitext(filename)[0]
        character_cache[character_id] = character
        character_source_paths[character_id] = file_path

    return character_cache


def get_character_source_path(character_id: str) -> Path:
    resolved_id = resolve_character_id(character_id) or character_id
    return character_source_paths.get(resolved_id, Path(CHARACTERS_DIR) / f"{resolved_id}.json")

def resolve_character_id(character_id: str) -> str | None:
    if character_id in character_cache:
        return character_id
    if not character_id or character_id in ("None", "Loaded"):
        return None

    alias_id = character_id.strip().casefold()
    matches = [
        current_id
        for current_id, character in character_cache.items()
        if alias_id in [
            alias.strip().casefold()
            for alias in character.get("Alias_ID", "").split(",")
            if alias.strip()
        ]
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        debug_warning(
            "Characters",
            f"Alias_ID '{character_id}' matches multiple characters: {', '.join(matches)}. "
            "The character has been left unresolved.",
        )
    return None


def get_character(character_id, default=None):
    resolved_id = resolve_character_id(character_id)
    return character_cache.get(resolved_id, default)

def get_all_characters():
    return list(character_cache.values())

def copy_character_quick_weight_values(
    character_id: str, values: dict[tuple[str, bool], float]
) -> None:
    source_id = resolve_character_id(character_id)
    if source_id is None or not values:
        debug_warning("Quick Weights", "Select a saved character with quick weights to copy.")
        return
    if any(not tag or not math.isfinite(value) for (tag, _), value in values.items()):
        debug_error("Quick Weights", "Cannot copy invalid quick-weight tags or values.")
        return

    updated_characters = updated_weights = skipped = failed = 0
    for target_id, cached in character_cache.items():
        if target_id == source_id:
            continue
        path = get_character_source_path(target_id)
        try:
            payload = read_document(path)
            target = payload[0] if isinstance(payload, list) and payload else payload
            if not isinstance(target, dict):
                raise ValueError("Expected a character object.")
            weights = target.get("quick_weights", [])
            if not isinstance(weights, list):
                raise ValueError("Expected a quick_weights list.")
            changed = 0
            for entry in weights:
                if not isinstance(entry, dict):
                    raise ValueError("Expected a quick-weight object.")
                tag = str(entry.get("tag") or "").strip().lower()
                key = (tag, bool(entry.get("negative", False)))
                if key not in values:
                    continue
                value = values[key]
                minimum = float(entry["min"])
                maximum = float(entry["max"])
                if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
                    raise ValueError(f"Invalid limits for '{tag}'.")
                if not minimum <= value <= maximum:
                    skipped += 1
                    debug_warning(
                        "Quick Weights",
                        f"Skipped {target_id}: '{tag}' ({'negative' if key[1] else 'positive'}) "
                        f"does not support {value:.1f} (limits {minimum:g} to {maximum:g}).",
                    )
                    continue
                if entry.get("value") != value:
                    entry["value"] = value
                    changed += 1
            if changed:
                write_document(path, payload)
                cached["quick_weights"] = deepcopy(weights)
                updated_characters += 1
                updated_weights += changed
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exception:
            failed += 1
            debug_error("Quick Weights", f"Cannot update {path}: {exception}")

    debug_info(
        "Quick Weights",
        f"Copied values from {source_id}: updated {updated_weights} quick weights in "
        f"{updated_characters} other characters; skipped {skipped} unsupported values; "
        f"{failed} character files failed.",
    )

def get_data(key, default=None):
    return data_cache.get(key, default)

def load_image_tree(use_alt_portraits: bool = False) -> dict:
    image_tree: dict = {}

    def pick_root(disk_path: Path, packaged_relative: str) -> Path:
        if disk_path.exists():
            return disk_path
        bundled = packaged_path(packaged_relative)
        return bundled if bundled.exists() else disk_path

    portrait_root = Path(PORTRAITS_DIR)
    if use_alt_portraits:
        alt_portrait_root = pick_root(Path(ALT_PORTRAITS_DIR), "images/character_portraits")
        if alt_portrait_root.exists():
            portrait_root = alt_portrait_root

    root_definitions = [
        ("images", pick_root(Path(IMAGES_DIR), "images")),
        ("references", pick_root(Path(REFERENCE_DIR), "references")),
        ("portraits", pick_root(portrait_root, "images/character_portraits")),
    ]

    def add_root_to_tree(root_name: str, root_path: Path) -> None:
        if not root_path.exists():
            return

        root_level = image_tree.setdefault(root_name, {})

        for file_path in root_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in VALID_IMAGE_EXTENSIONS:
                continue

            relative_path = file_path.relative_to(root_path)
            path_parts = relative_path.parts
            name_without_extension = file_path.stem
            normalized_name = name_without_extension.lower()

            current_level = root_level
            for folder_name in path_parts[:-1]:
                current_level = current_level.setdefault(folder_name, {})

            current_level[normalized_name] = str(file_path)
            if name_without_extension != normalized_name:
                current_level[name_without_extension] = str(file_path)

    for root_name, root_path in root_definitions:
        add_root_to_tree(root_name, root_path)

    return image_tree

def load_wildcards() -> dict:
    wildcard_cache.clear()
    _load_all_json_in_dir(Path(WILDCARDS_DIR), wildcard_cache, "wildcards")
    return wildcard_cache

def get_wildcard(wildcard_id, default=None):
    return wildcard_cache.get(wildcard_id, default)

def get_all_wildcards():
    return list(wildcard_cache.values())


def get_wildcard_map(default=None):
    if not wildcard_cache:
        return {} if default is None else default
    return deepcopy(wildcard_cache)


def load_universal_quick_weights() -> list:
    universal_quick_weights_cache.clear()
    if not UNIVERSAL_QUICK_WEIGHTS_FILE.exists():
        return universal_quick_weights_cache

    try:
        with UNIVERSAL_QUICK_WEIGHTS_FILE.open("r", encoding="utf-8") as file_handle:
            loaded = json.load(file_handle)
    except Exception:
        return universal_quick_weights_cache

    if isinstance(loaded, list):
        for item in loaded:
            if isinstance(item, dict):
                universal_quick_weights_cache.append(item)
    return universal_quick_weights_cache


def get_universal_quick_weights(default=None):
    if default is None:
        default = []
    return [dict(weight) for weight in universal_quick_weights_cache] if universal_quick_weights_cache else default


def save_universal_quick_weights(quick_weights_data: list) -> None:
    if not isinstance(quick_weights_data, list):
        return

    def weight_key(weight: dict):
        return (
            weight.get("tag"),
            bool(weight.get("negative", False)),
            float(weight.get("min", 0.0)),
            float(weight.get("max", 0.0)),
        )

    existing_weights = [dict(item) for item in universal_quick_weights_cache if isinstance(item, dict)]
    incoming_weights = [dict(item) for item in quick_weights_data if isinstance(item, dict)]

    incoming_by_key = {weight_key(item): item for item in incoming_weights}
    merged_weights = []
    replaced_keys = set()

    # Keep every existing universal entry unless an incoming update matches it.
    for existing in existing_weights:
        key = weight_key(existing)
        incoming = incoming_by_key.get(key)
        if incoming is not None:
            merged_weights.append(incoming)
            replaced_keys.add(key)
        else:
            merged_weights.append(existing)

    # Allow brand-new entries to be appended.
    for key, incoming in incoming_by_key.items():
        if key not in replaced_keys:
            merged_weights.append(incoming)

    universal_quick_weights_cache.clear()
    universal_quick_weights_cache.extend(merged_weights)

    try:
        with UNIVERSAL_QUICK_WEIGHTS_FILE.open("w", encoding="utf-8") as file_handle:
            json.dump(universal_quick_weights_cache, file_handle, indent=2, ensure_ascii=False)
    except Exception:
        pass


def sync_universal_quick_weights_from_characters() -> bool:
    """
    Ensure universal quick weights include every quick weight found in character data.
    Returns True when universal quick weights were updated.
    """
    def weight_key(weight: dict):
        return (
            str(weight.get("tag", "")).strip(),
            bool(weight.get("negative", False)),
            float(weight.get("min", 0.0)),
            float(weight.get("max", 0.0)),
        )

    def normalize(weight: dict):
        return {
            "tag": str(weight.get("tag", "")).strip(),
            "value": float(weight.get("value", 0.0)),
            "min": float(weight.get("min", 0.0)),
            "max": float(weight.get("max", 0.0)),
            "negative": bool(weight.get("negative", False)),
        }

    existing = [dict(item) for item in universal_quick_weights_cache if isinstance(item, dict)]
    existing_keys = {
        weight_key(item)
        for item in existing
        if str(item.get("tag", "")).strip()
    }

    additions = []
    for character in character_cache.values():
        if not isinstance(character, dict):
            continue

        quick_weights = character.get("quick_weights") or []
        if not isinstance(quick_weights, list):
            continue

        for item in quick_weights:
            if not isinstance(item, dict):
                continue

            normalized = normalize(item)
            if not normalized["tag"]:
                continue

            key = weight_key(normalized)
            if key in existing_keys:
                continue

            existing_keys.add(key)
            additions.append(normalized)

    if not additions:
        return False

    save_universal_quick_weights(existing + additions)
    return True


# Hook your reload signal to character reload
refresh_character_lists_signal.reload_character_data.connect(lambda: load_characters())
