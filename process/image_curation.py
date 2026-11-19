from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
from threading import Event, RLock
from typing import Callable, Iterable

from data.character_slots import MAX_CHARACTER_SLOTS
from data.datahub import resolve_character_id
from data.paths import CURATION_DIR
from process.drop_handling import load_custom_json, load_nai_comment_json


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SORTING_DIRECTORY = "!sorting"
CURATED_DIRECTORY = "curated"
TRASH_DIRECTORY = "trash"


class CurationError(RuntimeError):
    pass


CURATION_BLOCK_SIZE = 100
CURATION_WORKER_COUNT = 8


class CurationProgress:
    """Thread-safe progress shared with the UI: counters are only incremented by curation workers and
    read by the UI, and cancellation is an Event the UI may set at any time."""

    CHECKING = "checking"
    MOVING = "moving"
    TAGGING = "tagging"

    def __init__(self, callback: Callable[[int], bool] | None = None):
        self.callback = callback
        self.stage = self.CHECKING
        self.checked = 0
        self.processed = 0
        self.tagged = 0
        self.tag_total = 0
        self.block = 0
        self.block_count = 0
        self._cancel_event = Event()
        self._lock = RLock()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    def check(self) -> None:
        with self._lock:
            self.checked += 1

    def report(self, count: int = 1) -> None:
        with self._lock:
            self.stage = self.MOVING
            self.processed += count
            processed = self.processed
        if self.callback is not None and not self.callback(processed):
            self.cancel()

    def tag(self) -> None:
        with self._lock:
            self.tagged += 1


def _is_cancelled(progress: CurationProgress | None) -> bool:
    return progress is not None and progress.cancelled


def _load_manifests(images: list[Path], progress: CurationProgress | None, pool: ThreadPoolExecutor) -> dict[Path, dict] | None:
    def load(image_path: Path) -> dict | None:
        if _is_cancelled(progress):
            return None
        manifest = load_curation_manifest(image_path)
        if progress is not None:
            progress.check()
        return manifest

    if progress is not None:
        progress.stage = CurationProgress.CHECKING
    manifests = dict(zip(images, pool.map(load, images)))
    if _is_cancelled(progress) or any(manifest is None for manifest in manifests.values()):
        return None
    return manifests


def _run_in_blocks(
    images: Iterable[Path],
    progress: CurationProgress | None,
    process_block: Callable[[list[Path], dict[Path, dict], ThreadPoolExecutor], list[CurationMoveResult]],
) -> list[CurationMoveResult]:
    """Analyze and process images CURATION_BLOCK_SIZE at a time, using a thread pool within each block,
    so moving starts after the first block instead of after every image has been analyzed."""
    source_images = [Path(image) for image in images]
    block_starts = range(0, len(source_images), CURATION_BLOCK_SIZE)
    if progress is not None:
        progress.block_count = len(block_starts)
    results = []
    with ThreadPoolExecutor(max_workers=CURATION_WORKER_COUNT, thread_name_prefix="curation-block") as pool:
        for block_index, start in enumerate(block_starts, start=1):
            if _is_cancelled(progress):
                break
            if progress is not None:
                progress.block = block_index
            block = source_images[start:start + CURATION_BLOCK_SIZE]
            manifests = _load_manifests(block, progress, pool)
            if manifests is None:
                break
            results.extend(process_block(block, manifests, pool))
    return results


@dataclass(frozen=True)
class CurationMoveResult:
    source: Path
    destination: Path
    sidecar_source: Path | None
    sidecar_destination: Path | None
    manifest_source: Path | None
    manifest_destination: Path | None


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def sidecar_path(image_path: Path) -> Path:
    return Path(f"{image_path}.txt")


def manifest_path(image_path: Path) -> Path:
    return Path(f"{image_path}.json")


def get_sidecar_tags(image_path: Path) -> list[str]:
    companion_path = sidecar_path(image_path)
    if not companion_path.is_file():
        return []

    return [line.strip() for line in companion_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get_image_metadata_tags(image_path: Path) -> tuple[list[str], list[str]]:
    if image_path.suffix.lower() != ".png":
        return [], []

    try:
        metadata = load_custom_json(image_path)
    except (OSError, ValueError):
        return [], []
    if not isinstance(metadata, dict):
        return [], []

    characters = []
    outfits = []
    for character_data in metadata.get("characters", {}).values():
        if not isinstance(character_data, dict):
            continue
        character_name = str(character_data.get("character") or "").strip()
        outfit_name = str(character_data.get("most_recent_outfit") or "").strip()
        if character_name and character_name != "None" and character_name not in characters:
            characters.append(character_name)
        if outfit_name and outfit_name != "None" and outfit_name not in outfits:
            outfits.append(outfit_name)
    return characters, outfits


def get_image_prompt_slots(image_path: Path) -> list[dict]:
    if image_path is None or image_path.suffix.lower() != ".png":
        return []

    try:
        metadata = load_nai_comment_json(image_path)
    except (OSError, ValueError):
        return []
    if not isinstance(metadata, dict):
        return []

    try:
        custom_metadata = load_custom_json(image_path)
    except (OSError, ValueError):
        custom_metadata = {}
    character_names = [
        str(character_data.get("character") or "").strip()
        for character_data in custom_metadata.get("characters", {}).values()
        if isinstance(character_data, dict)
    ] if isinstance(custom_metadata, dict) else []

    positive_caption = metadata.get("v4_prompt", {}).get("caption", {})
    negative_caption = metadata.get("v4_negative_prompt", {}).get("caption", {})
    base_positive_prompt = str(positive_caption.get("base_caption") or metadata.get("prompt") or "")
    base_negative_prompt = str(
        negative_caption.get("base_caption") or metadata.get("negative_prompt") or metadata.get("uc") or ""
    )
    positive_slots = positive_caption.get("char_captions", [])
    negative_slots = negative_caption.get("char_captions", [])
    slot_count = max(len(positive_slots), len(negative_slots))
    prompt_slots = [
        {
            "label": "Global Prompt",
            "positive_prompt": base_positive_prompt,
            "negative_prompt": base_negative_prompt,
        }
    ]
    for index in range(slot_count):
        positive_slot = positive_slots[index] if index < len(positive_slots) else {}
        negative_slot = negative_slots[index] if index < len(negative_slots) else {}
        positive_character_prompt = str(positive_slot.get("char_caption") or "") if isinstance(positive_slot, dict) else ""
        negative_character_prompt = str(negative_slot.get("char_caption") or "") if isinstance(negative_slot, dict) else ""
        character_name = character_names[index] if index < len(character_names) else ""
        label = f"Character {index + 1}"
        if character_name and character_name != "None":
            label = f"{label}: {character_name}"
        prompt_slots.append(
            {
                "label": label,
                "positive_prompt": positive_character_prompt,
                "negative_prompt": negative_character_prompt,
            }
        )
    return prompt_slots


DEFAULT_OTHER_TAGS = ["Favorite", "Best of Set"]
# Manifests written before Other Tags existed stored these as separate true/false flags.
LEGACY_OTHER_TAG_FLAGS = {"favorite": "Favorite", "best_of_set": "Best of Set"}


def create_curation_manifest(image_path: Path) -> dict:
    characters, outfits = get_image_metadata_tags(image_path)
    return {
        "status": "Uncurated",
        "characters": characters,
        "outfits": outfits,
        "content": [],
        "set_name": "",
        "rating": "SFW",
        "other_tags": [],
        "pairing": ["", "", "", "", ""],
    }


def _migrate_legacy_other_tags(manifest: dict) -> dict:
    legacy_tags = [tag for flag, tag in LEGACY_OTHER_TAG_FLAGS.items() if manifest.get(flag)]
    if "other_tags" not in manifest:
        manifest["other_tags"] = legacy_tags
    for flag in LEGACY_OTHER_TAG_FLAGS:
        manifest.pop(flag, None)
    return manifest


_manifest_cache: dict[Path, tuple[float, dict]] = {}
# Curation mode creates default manifests on a background thread while the UI saves edits.
# Every read-modify-write holds this lock so a default can never land on top of an edit.
_manifest_lock = RLock()


def load_curation_manifest(image_path: Path) -> dict:
    path = manifest_path(image_path)
    with _manifest_lock:
        if path.is_file():
            cached = _manifest_cache.get(image_path)
            if cached is not None and cached[0] == path.stat().st_mtime:
                return dict(cached[1])

    # Reading PNG metadata is the slow part, so it runs outside the lock to let curation
    # blocks analyze images in parallel; the manifest file is re-checked under the lock below.
    defaults = create_curation_manifest(image_path)
    with _manifest_lock:
        if path.is_file():
            mtime = path.stat().st_mtime
            cached = _manifest_cache.get(image_path)
            if cached is not None and cached[0] == mtime:
                return dict(cached[1])
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None
            if isinstance(manifest, dict):
                merged = defaults | _migrate_legacy_other_tags(manifest)
                _manifest_cache[image_path] = (mtime, merged)
                return dict(merged)

        write_curation_manifest(image_path, defaults)
        return dict(defaults)


def write_curation_manifest(image_path: Path, manifest: dict) -> None:
    with _manifest_lock:
        path = manifest_path(image_path)
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Every write refreshes the cache so cached reads never go stale.
        _manifest_cache[image_path] = (path.stat().st_mtime, dict(manifest))


def update_curation_manifest(image_path: Path, values: dict) -> dict:
    with _manifest_lock:
        manifest = load_curation_manifest(image_path)
        manifest.update({key: value for key, value in values.items() if key in {"status", "characters", "outfits", "content", "set_name", "rating", "other_tags", "pairing"}})
        write_curation_manifest(image_path, manifest)
        return manifest


def initialize_curation_manifests(output_dir: Path) -> None:
    # Best effort in the background: images can be moved (Apply Curation) or folders
    # deleted while this runs, so a vanished path is skipped rather than crashing the thread.
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        image_paths = [image_path for image_path in output_dir.rglob("*") if is_image_file(image_path)]
    except OSError:
        return
    for image_path in image_paths:
        try:
            load_curation_manifest(image_path)
        except OSError:
            continue


def build_hydrus_tags(manifest: dict, pairing_priorities: dict[str, int] | None = None) -> list[str]:
    status = str(manifest["status"]).strip().lower()
    set_name = str(manifest.get("set_name") or "").strip()
    rating = str(manifest["rating"]).strip().lower()
    tags = [f"status: {status}"]
    tags.extend(
        f"character: {name}"
        for name in manifest.get("characters", [])
        if str(name).strip() and str(name) != "None"
    )
    tags.extend(f"outfit: {name}" for name in manifest.get("outfits", []) if str(name).strip())
    tags.extend(f"content: {name}" for name in manifest.get("content", []) if str(name).strip())
    if set_name:
        tags.append(f"set: {set_name}")
    tags.append(f"rating: {rating}")
    # Lowercased so the former Favorite / Best of Set flags keep exporting as "favorite" / "best of set".
    tags.extend(str(tag).strip().lower() for tag in manifest.get("other_tags", []) if str(tag).strip())
    pairing_values = [str(value).strip() for value in manifest.get("pairing", []) if str(value).strip()]
    if pairing_values:
        pairing_priorities = pairing_priorities or {}
        pairing_values.sort(key=lambda value: (pairing_priorities.get(value, 9999), value))
        tags.append(f"pairing: {' x '.join(pairing_values)}")
    return tags


def write_hydrus_tags(image_path: Path, tags: Iterable[str]) -> None:
    sidecar_path(image_path).write_text("\n".join(tags) + "\n", encoding="utf-8")


def load_curation_sets(sets_path: Path) -> list[str]:
    if not sets_path.is_file():
        return []
    try:
        sets = json.loads(sets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(sets, list):
        return []
    return sorted({str(set_name).strip() for set_name in sets if str(set_name).strip()}, key=str.lower)


def save_curation_sets(sets_path: Path, sets: Iterable[str]) -> list[str]:
    normalized_sets = sorted({str(set_name).strip() for set_name in sets if str(set_name).strip()}, key=str.lower)
    sets_path.parent.mkdir(parents=True, exist_ok=True)
    sets_path.write_text(json.dumps(normalized_sets, indent=2) + "\n", encoding="utf-8")
    return normalized_sets


def add_curation_set(sets_path: Path, set_name: str) -> list[str]:
    normalized_name = set_name.strip()
    if not normalized_name:
        raise CurationError("Set name cannot be empty.")
    current_sets = load_curation_sets(sets_path)
    if normalized_name in current_sets:
        raise CurationError("That set already exists.")
    return save_curation_sets(sets_path, [*current_sets, normalized_name])


def rename_curation_sets(output_dir: Path, renames: dict[str, str]) -> int:
    """Move every image under output_dir from an old set name to its new one. Returns how many images changed."""
    renames = {
        str(old_name).strip(): str(new_name).strip()
        for old_name, new_name in renames.items()
        if str(old_name).strip() and str(new_name).strip() and str(old_name).strip() != str(new_name).strip()
    }
    if not renames or not Path(output_dir).is_dir():
        return 0
    # Cheap text check first so thousands of unrelated manifests are never parsed.
    encoded_names = [json.dumps(old_name) for old_name in renames]
    updated_count = 0
    for current_root, _, file_names in os.walk(output_dir):
        for file_name in file_names:
            if not file_name.endswith(".json"):
                continue
            image_path = Path(current_root) / file_name[: -len(".json")]
            if image_path.suffix.lower() not in IMAGE_SUFFIXES or not image_path.is_file():
                continue
            try:
                manifest_text = (Path(current_root) / file_name).read_text(encoding="utf-8")
            except OSError:
                continue
            if not any(encoded_name in manifest_text for encoded_name in encoded_names):
                continue
            with _manifest_lock:
                manifest = load_curation_manifest(image_path)
                new_name = renames.get(str(manifest.get("set_name") or "").strip())
                if new_name is None:
                    continue
                manifest["set_name"] = new_name
                write_curation_manifest(image_path, manifest)
            updated_count += 1
    return updated_count


def delete_curation_set(sets_path: Path, set_name: str) -> list[str]:
    current_sets = load_curation_sets(sets_path)
    if set_name not in current_sets:
        raise CurationError("Select a saved set to delete.")
    return save_curation_sets(sets_path, [name for name in current_sets if name != set_name])


def load_curation_other_tags(other_tags_path: Path) -> list[str]:
    if not other_tags_path.is_file():
        return list(DEFAULT_OTHER_TAGS)
    try:
        other_tags = json.loads(other_tags_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(DEFAULT_OTHER_TAGS)
    if not isinstance(other_tags, list):
        return list(DEFAULT_OTHER_TAGS)
    return _unique_in_order(other_tags)


def save_curation_other_tags(other_tags_path: Path, other_tags: Iterable[str]) -> list[str]:
    # Kept in the order entered; no sorting or grouping.
    normalized_tags = _unique_in_order(other_tags)
    other_tags_path.parent.mkdir(parents=True, exist_ok=True)
    other_tags_path.write_text(json.dumps(normalized_tags, indent=2) + "\n", encoding="utf-8")
    return normalized_tags


def _unique_in_order(values: Iterable) -> list[str]:
    unique_values = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in unique_values:
            unique_values.append(cleaned)
    return unique_values


def load_curation_outfits(outfits_path: Path) -> list[str]:
    if not outfits_path.is_file():
        return []
    try:
        outfits = json.loads(outfits_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(outfits, list):
        return []
    return [str(outfit_name).strip() for outfit_name in outfits if str(outfit_name).strip()]


def save_curation_outfits(outfits_path: Path, outfits: Iterable[str]) -> list[str]:
    normalized_outfits = sorted({str(outfit_name).strip() for outfit_name in outfits if str(outfit_name).strip()}, key=str.lower)
    outfits_path.parent.mkdir(parents=True, exist_ok=True)
    outfits_path.write_text(json.dumps(normalized_outfits, indent=2) + "\n", encoding="utf-8")
    return normalized_outfits


def add_curation_outfit(outfits_path: Path, outfit_name: str) -> list[str]:
    normalized_name = outfit_name.strip()
    if not normalized_name:
        raise CurationError("Outfit name cannot be empty.")
    current_outfits = load_curation_outfits(outfits_path)
    if normalized_name in current_outfits:
        raise CurationError("That generic outfit already exists.")
    return save_curation_outfits(outfits_path, [*current_outfits, normalized_name])


def delete_curation_outfit(outfits_path: Path, outfit_name: str) -> list[str]:
    current_outfits = load_curation_outfits(outfits_path)
    if outfit_name not in current_outfits:
        raise CurationError("Select a generic outfit to delete.")
    return save_curation_outfits(outfits_path, [name for name in current_outfits if name != outfit_name])


DEFAULT_PAIRING_PRIORITY = 100


def _normalize_caption_tag(tag: str) -> str:
    normalized = tag.strip().lower()
    normalized = re.sub(r"^[\d.]+::", "", normalized)
    normalized = normalized.rstrip(":")
    return normalized.strip("{}[]()").strip()


def load_pairing_tag_definitions(pairing_tags_path: Path) -> dict[str, dict[str, object]]:
    if not pairing_tags_path.is_file():
        return {}
    try:
        pairing_tags = json.loads(pairing_tags_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(pairing_tags, dict):
        return {}

    raw_definitions = pairing_tags.get("labels", pairing_tags)
    if not isinstance(raw_definitions, dict):
        return {}
    definitions = {}
    for index, (label, value) in enumerate(raw_definitions.items()):
        normalized_label = str(label).strip()
        if not normalized_label:
            continue
        if isinstance(value, dict):
            tags = _normalize_tag_list(value.get("tags"))
            priority = value.get("priority", DEFAULT_PAIRING_PRIORITY + index)
        else:
            tags = _normalize_tag_list(value)
            priority = DEFAULT_PAIRING_PRIORITY + index
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = DEFAULT_PAIRING_PRIORITY + index
        definitions[normalized_label] = {"tags": tags, "priority": priority}
    return definitions


def get_pairing_labels(pairing_tags_path: Path) -> list[str]:
    return list(load_pairing_tag_definitions(pairing_tags_path))


def load_pairing_tags(pairing_tags_path: Path) -> dict[str, list[str]]:
    return {
        label: list(definition["tags"])
        for label, definition in load_pairing_tag_definitions(pairing_tags_path).items()
    }


def load_pairing_priorities(pairing_tags_path: Path) -> dict[str, int]:
    return {
        label: int(definition["priority"])
        for label, definition in load_pairing_tag_definitions(pairing_tags_path).items()
    }


def save_pairing_tags(pairing_tags_path: Path, pairing_tags: dict[str, list[str]], priorities: dict[str, int] | None = None) -> None:
    existing_definitions = load_pairing_tag_definitions(pairing_tags_path)
    labels = [str(label).strip() for label in pairing_tags if str(label).strip()]
    normalized_tags = {
        label: {
            "tags": _normalize_tag_list(pairing_tags.get(label, [])),
            "priority": int((priorities or {}).get(label, existing_definitions.get(label, {}).get("priority", DEFAULT_PAIRING_PRIORITY))),
        }
        for label in labels
    }
    pairing_tags_path.parent.mkdir(parents=True, exist_ok=True)
    pairing_tags_path.write_text(json.dumps({"labels": normalized_tags}, indent=2) + "\n", encoding="utf-8")


def _normalize_tag_list(tags) -> list[str]:
    if not isinstance(tags, list):
        return []
    return [_normalize_caption_tag(str(tag)) for tag in tags if str(tag).strip()]


def _load_content_tag_entries(content_tags_path: Path) -> list[dict]:
    if not content_tags_path.is_file():
        return []
    try:
        content_tags = json.loads(content_tags_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurationError("Content tags could not be read.") from exc
    if isinstance(content_tags, dict):
        return [
            {"name": name, **rules}
            for name, rules in content_tags.items()
            if isinstance(rules, dict)
        ]
    if not isinstance(content_tags, list):
        raise CurationError("Content tags must be a list or object.")
    return [entry for entry in content_tags if isinstance(entry, dict)]


def load_content_tag_groups(content_tags_path: Path) -> list[str]:
    groups = []
    for entry in _load_content_tag_entries(content_tags_path):
        if str(entry.get("type") or "").strip().lower() == "group":
            group_name = str(entry.get("name") or "").strip()
        else:
            group_name = str(entry.get("category") or entry.get("catagory") or "General").strip() or "General"
        if group_name and group_name not in groups:
            groups.append(group_name)
    return groups


def _save_content_tag_entries(content_tags_path: Path, entries: list[dict]) -> None:
    content_tags_path.parent.mkdir(parents=True, exist_ok=True)
    content_tags_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")


def add_content_tag(content_tags_path: Path, tag_name: str, category: str) -> None:
    normalized_name = tag_name.strip()
    normalized_category = category.strip() or "General"
    if not normalized_name:
        raise CurationError("Content tag name cannot be empty.")
    entries = _load_content_tag_entries(content_tags_path)
    if any(str(entry.get("name") or "").strip() == normalized_name for entry in entries):
        raise CurationError("That content tag already exists.")
    entries.append(
        {"name": normalized_name, "category": normalized_category, "include": [], "exclude": []}
    )
    _save_content_tag_entries(content_tags_path, entries)


def add_content_tag_group(content_tags_path: Path, group_name: str) -> None:
    normalized_name = group_name.strip()
    if not normalized_name:
        raise CurationError("Content tag group name cannot be empty.")
    entries = _load_content_tag_entries(content_tags_path)
    if normalized_name in load_content_tag_groups(content_tags_path):
        raise CurationError("That content tag group already exists.")
    entries.append({"type": "group", "name": normalized_name})
    _save_content_tag_entries(content_tags_path, entries)


def save_content_tag_definitions(content_tags_path: Path, groups: Iterable[str], tags: Iterable[dict]) -> None:
    normalized_groups = []
    for group in groups:
        group_name = str(group).strip()
        if group_name and group_name not in normalized_groups:
            normalized_groups.append(group_name)

    entries = [{"type": "group", "name": group_name} for group_name in normalized_groups]
    tag_names = set()
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        name = str(tag.get("name") or "").strip()
        if not name:
            raise CurationError("Content tag name cannot be empty.")
        if name in tag_names:
            raise CurationError(f"Content tag names must be unique: {name}")
        tag_names.add(name)
        category = str(tag.get("category") or "General").strip() or "General"
        if category not in normalized_groups:
            normalized_groups.append(category)
            entries.append({"type": "group", "name": category})
        entries.append(
            {
                "name": name,
                "category": category,
                "include": _normalize_tag_list(tag.get("include")),
                "exclude": _normalize_tag_list(tag.get("exclude")),
            }
        )
    _save_content_tag_entries(content_tags_path, entries)


def load_content_tags(content_tags_path: Path) -> list[dict[str, object]]:
    try:
        content_tags = _load_content_tag_entries(content_tags_path)
    except CurationError:
        return []

    entries = []
    seen_names = set()
    for entry in content_tags:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type") or "").strip().lower() == "group":
            continue
        name = str(entry.get("name") or entry.get("label") or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        category = str(entry.get("category") or entry.get("catagory") or "General").strip() or "General"
        entries.append(
            {
                "name": name,
                "category": category,
                "include": _normalize_tag_list(entry.get("include")),
                "exclude": _normalize_tag_list(entry.get("exclude")),
            }
        )
    return entries


def calculate_content_matches(image_path: Path, content_tags: list[dict[str, object]]) -> list[str]:
    caption_tags = {
        _normalize_caption_tag(tag)
        for slot in get_image_prompt_slots(image_path)
        for tag in str(slot.get("positive_prompt") or "").split(",")
        if tag.strip()
    }
    caption_tags.discard("")
    print(
        f"Content auto-calculate for {image_path.name}: prompt tags: "
        f"{', '.join(sorted(caption_tags)) or '(none)'}"
    )
    results = []
    for entry in content_tags:
        name = str(entry.get("name") or "").strip()
        include_tags = set(_normalize_tag_list(entry.get("include")))
        exclude_tags = set(_normalize_tag_list(entry.get("exclude")))
        include_matches = sorted(include_tags & caption_tags)
        exclude_matches = sorted(exclude_tags & caption_tags)
        if not name:
            print("Content auto-calculate: skipped unnamed content tag definition")
            continue
        if include_matches and not exclude_matches:
            print(
                f"Content auto-calculate {name}: matched "
                f"include [{', '.join(include_matches)}]; exclude [none]"
            )
            results.append(name)
        elif exclude_matches:
            print(
                f"Content auto-calculate {name}: excluded by "
                f"[{', '.join(exclude_matches)}]; include [{', '.join(include_matches) or 'none'}]"
            )
        else:
            print(
                f"Content auto-calculate {name}: no include match; "
                f"configured include [{', '.join(sorted(include_tags)) or 'none'}]"
            )
    return results


def calculate_character_matches(image_path: Path) -> list[str] | None:
    if image_path.suffix.lower() != ".png":
        print(f"Character auto-calculate skipped {image_path.name}: no supported character metadata.")
        return None
    try:
        metadata = load_custom_json(image_path)
    except (OSError, ValueError) as exc:
        print(f"Character auto-calculate skipped {image_path.name}: unable to read metadata: {exc}")
        return None
    if not isinstance(metadata, dict) or not isinstance(metadata.get("characters"), dict):
        print(f"Character auto-calculate skipped {image_path.name}: no character metadata.")
        return None

    characters = []
    for slot in metadata["characters"].values():
        if not isinstance(slot, dict) or "character" not in slot:
            print(f"Character auto-calculate skipped {image_path.name}: invalid character slot metadata.")
            return None
        character_name = str(slot.get("character") or "").strip()
        if character_name and character_name not in {"None", "Loaded"}:
            characters.append(resolve_character_id(character_name) or character_name)
    print(f"Character auto-calculate for {image_path.name}: {', '.join(characters) or '(none)'}")
    return characters


def calculate_pairing_matches(image_path: Path, pairing_tags: dict[str, list[str]]) -> list[str] | None:
    prompt_slots = get_image_prompt_slots(image_path)
    if not prompt_slots:
        print(f"Pairing auto-calculate skipped {image_path.name}: no prompt metadata.")
        return None
    character_slots = prompt_slots[1:MAX_CHARACTER_SLOTS + 1]
    results = []
    for slot_index, slot in enumerate(character_slots):
        slot_name = slot.get("label") or f"Character {slot_index + 1}"
        caption_tags = {
            _normalize_caption_tag(tag)
            for tag in str(slot.get("positive_prompt") or "").split(",")
            if tag.strip()
        }
        caption_tags.discard("")
        best_label = ""
        best_count = 0
        best_matched_tags = []
        tied_labels = []
        for label in pairing_tags:
            matched_tags = caption_tags & set(pairing_tags.get(label, []))
            match_count = len(matched_tags)
            if match_count > best_count:
                best_label, best_count, best_matched_tags = label, match_count, sorted(matched_tags)
                tied_labels = [label]
            elif match_count == best_count and match_count > 0:
                tied_labels.append(label)
        if best_count > 0 and len(tied_labels) > 1:
            print(f"Pairing auto-calculate tie for slot {slot_index + 1} ({slot_name}): {', '.join(tied_labels)} ({best_count} matching tags)")
            best_label = ""
        elif best_label:
            print(f"Pairing auto-calculate for slot {slot_index + 1} ({slot_name}): {best_label} (matched tags: {', '.join(best_matched_tags)})")
        else:
            print(f"Pairing auto-calculate for slot {slot_index + 1} ({slot_name}): no match")
        results.append(best_label)
    results.extend([""] * (MAX_CHARACTER_SLOTS - len(results)))
    return results


def output_folders(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    nested_folders = (
        Path(current_root) / folder_name
        for current_root, folder_names, _ in os.walk(output_dir)
        for folder_name in folder_names
    )
    return [output_dir, *sorted(nested_folders)]


def images_in_folder(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    # os.scandir() reuses the file-type info returned by the directory read
    # itself, avoiding a separate stat() syscall per entry. Path.iterdir()
    # combined with Path.is_file() forces one stat() call per file, which is
    # extremely slow (minutes) for output folders containing tens of
    # thousands of images.
    with os.scandir(folder) as entries:
        return sorted(
            Path(entry.path)
            for entry in entries
            if entry.is_file() and Path(entry.name).suffix.lower() in IMAGE_SUFFIXES
        )


def is_managed_folder(folder: Path, output_dir: Path) -> bool:
    try:
        relative_parts = folder.resolve().relative_to(output_dir.resolve()).parts
    except ValueError:
        return False

    return relative_parts[:2] == (SORTING_DIRECTORY, CURATED_DIRECTORY) or relative_parts[:2] == (
        SORTING_DIRECTORY,
        TRASH_DIRECTORY,
    )


def curated_directory(output_dir: Path) -> Path:
    return output_dir / SORTING_DIRECTORY / CURATED_DIRECTORY


def trash_directory(output_dir: Path) -> Path:
    return output_dir / SORTING_DIRECTORY / TRASH_DIRECTORY


def _is_managed_resolved(resolved_folder: Path, resolved_output_dir: Path) -> bool:
    try:
        relative_parts = resolved_folder.relative_to(resolved_output_dir).parts
    except ValueError:
        return False
    return relative_parts[:2] in {(SORTING_DIRECTORY, CURATED_DIRECTORY), (SORTING_DIRECTORY, TRASH_DIRECTORY)}


def _check_movable(image_path: Path, resolved_output_dir: Path) -> str | None:
    if not is_image_file(image_path):
        return f"Not an available image file: {image_path}"
    if _is_managed_resolved(image_path.parent.resolve(), resolved_output_dir):
        return f"Images in managed folders cannot be moved: {image_path}"
    return None


def _plan_move(image_path: Path, destination: Path) -> tuple[Path | None, Path | None, Path | None]:
    companion_path = sidecar_path(image_path) if sidecar_path(image_path).is_file() else None
    source_manifest_path = manifest_path(image_path) if manifest_path(image_path).is_file() else None
    # Same-named destination files get overwritten; only non-file entries (such as folders) block the move.
    obstruction = next(
        (path for path in (destination, sidecar_path(destination), manifest_path(destination)) if path.exists() and not path.is_file()),
        None,
    )
    return companion_path, source_manifest_path, obstruction


def move_images(
    images: Iterable[Path],
    destination_dir: Path,
    output_dir: Path,
    progress: CurationProgress | None = None,
    pool: ThreadPoolExecutor | None = None,
) -> list[CurationMoveResult]:
    source_images = [Path(image) for image in images]
    if not source_images or _is_cancelled(progress):
        return []
    if pool is None:
        with ThreadPoolExecutor(max_workers=CURATION_WORKER_COUNT, thread_name_prefix="curation-move") as own_pool:
            return move_images(source_images, destination_dir, output_dir, progress, own_pool)

    destination_dir = Path(destination_dir)
    output_dir = Path(output_dir)
    resolved_output_dir = output_dir.resolve()

    for error in pool.map(lambda image_path: _check_movable(image_path, resolved_output_dir), source_images):
        if error is not None:
            raise CurationError(error)

    # Images already in the destination folder stay in place instead of overwriting themselves.
    resolved_destination_dir = destination_dir.resolve()
    resolved_parents = list(pool.map(lambda image_path: image_path.parent.resolve(), source_images))
    in_place_count = sum(1 for parent in resolved_parents if parent == resolved_destination_dir)
    if in_place_count:
        source_images = [image_path for image_path, parent in zip(source_images, resolved_parents) if parent != resolved_destination_dir]
        if progress is not None:
            progress.report(in_place_count)
        if not source_images:
            return []

    planned_destinations = [destination_dir / image_path.name for image_path in source_images]
    if len(set(planned_destinations)) != len(planned_destinations):
        raise CurationError("Selected images have conflicting destination names.")

    plans = list(pool.map(_plan_move, source_images, planned_destinations))
    obstructions = [obstruction for _, _, obstruction in plans if obstruction is not None]
    if obstructions:
        raise CurationError(f"Destination cannot be overwritten: {obstructions[0].name}")

    destination_dir.mkdir(parents=True, exist_ok=True)

    # Moves run one at a time: parallel renames into one folder contend heavily on Windows
    # (measured ~30x slower with 4-8 threads), while analysis above parallelizes well.
    results = []
    for image_path, destination, plan in zip(source_images, planned_destinations, plans):
        if _is_cancelled(progress):
            break
        companion_path, source_manifest_path, _ = plan
        # Same-named files already at the destination (including stale sidecars and
        # manifests from a previously overwritten image) are replaced by the new image.
        for stale_path in (destination, sidecar_path(destination), manifest_path(destination)):
            stale_path.unlink(missing_ok=True)
        # Each image moves together with its sidecar and manifest, so cancellation never splits them.
        shutil.move(str(image_path), str(destination))
        companion_destination = sidecar_path(destination) if companion_path is not None else None
        if companion_path is not None:
            shutil.move(str(companion_path), str(companion_destination))
        destination_manifest_path = manifest_path(destination) if source_manifest_path is not None else None
        if source_manifest_path is not None:
            shutil.move(str(source_manifest_path), str(destination_manifest_path))
        with _manifest_lock:
            _manifest_cache.pop(image_path, None)
            _manifest_cache.pop(destination, None)
        results.append(CurationMoveResult(image_path, destination, companion_path, companion_destination, source_manifest_path, destination_manifest_path))
        if progress is not None:
            progress.report()
    return results


def _manifest_status(manifest: dict) -> str:
    return str(manifest["status"]).strip().lower()


def apply_curation(images: Iterable[Path], output_dir: Path, progress: CurationProgress | None = None) -> list[CurationMoveResult]:
    pairing_priorities: dict[str, int] | None = None

    def process_block(block: list[Path], manifests: dict[Path, dict], pool: ThreadPoolExecutor) -> list[CurationMoveResult]:
        nonlocal pairing_priorities
        images_by_status: dict[str, list[Path]] = {"keep": [], "trash": [], "uncurated": []}
        for image_path, manifest in manifests.items():
            normalized_status = _manifest_status(manifest)
            if normalized_status not in images_by_status:
                raise CurationError(f"Unsupported curation status: {normalized_status}")
            images_by_status[normalized_status].append(image_path)

        if progress is not None and images_by_status["uncurated"]:
            progress.report(len(images_by_status["uncurated"]))
        kept_results = move_images(images_by_status["keep"], curated_directory(output_dir), output_dir, progress, pool)
        results = list(kept_results)
        results.extend(move_images(images_by_status["trash"], trash_directory(output_dir), output_dir, progress, pool))
        results.extend(
            CurationMoveResult(image_path, image_path, None, None, manifest_path(image_path), manifest_path(image_path))
            for image_path in images_by_status["uncurated"]
        )

        if kept_results:
            if pairing_priorities is None:
                pairing_priorities = load_pairing_priorities(CURATION_DIR / "pairing_tags.json")
            if progress is not None:
                progress.tag_total += len(kept_results)
                progress.stage = CurationProgress.TAGGING

            # Tags are written even after cancellation so every moved Keep image gets its sidecar.
            def tag(result: CurationMoveResult) -> None:
                write_hydrus_tags(result.destination, build_hydrus_tags(manifests[result.source], pairing_priorities))
                if progress is not None:
                    progress.tag()

            list(pool.map(tag, kept_results))
        return results

    return _run_in_blocks(images, progress, process_block)


def apply_trash_curation(images: Iterable[Path], output_dir: Path, progress: CurationProgress | None = None) -> list[CurationMoveResult]:
    def process_block(block: list[Path], manifests: dict[Path, dict], pool: ThreadPoolExecutor) -> list[CurationMoveResult]:
        trash_images = [image_path for image_path in block if _manifest_status(manifests[image_path]) == "trash"]
        if progress is not None and len(block) > len(trash_images):
            progress.report(len(block) - len(trash_images))
        return move_images(trash_images, trash_directory(output_dir), output_dir, progress, pool)

    return _run_in_blocks(images, progress, process_block)


def _move_grouped(
    images_by_folder: dict[str, list[Path]],
    skipped_count: int,
    output_dir: Path,
    progress: CurationProgress | None,
    pool: ThreadPoolExecutor,
) -> list[CurationMoveResult]:
    if progress is not None and skipped_count:
        progress.report(skipped_count)
    results = []
    for folder_name, folder_images in images_by_folder.items():
        results.extend(move_images(folder_images, Path(output_dir) / folder_name, output_dir, progress, pool))
    return results


def sort_by_set_curation(images: Iterable[Path], output_dir: Path, progress: CurationProgress | None = None) -> list[CurationMoveResult]:
    def process_block(block: list[Path], manifests: dict[Path, dict], pool: ThreadPoolExecutor) -> list[CurationMoveResult]:
        images_by_set: dict[str, list[Path]] = {}
        skipped_count = 0
        for image_path in block:
            set_name = str(manifests[image_path].get("set_name") or "").strip()
            if not set_name:
                skipped_count += 1
                continue
            if set_name in {".", "..", SORTING_DIRECTORY} or any(character in set_name for character in '<>:"/\\|?*'):
                raise CurationError(f"Set name cannot be used as an output folder: {set_name}")
            images_by_set.setdefault(set_name, []).append(image_path)
        return _move_grouped(images_by_set, skipped_count, output_dir, progress, pool)

    return _run_in_blocks(images, progress, process_block)


def _character_folder_name(manifest: dict) -> str:
    characters = {
        str(character).strip()
        for character in manifest.get("characters", [])
        if character is not None and str(character).strip() not in {"", "None"}
    }
    folder_name = " x ".join(sorted(characters, key=lambda name: (name.casefold(), name))) or "Unknown Characters"
    if (
        folder_name in {".", "..", SORTING_DIRECTORY}
        or any(character in folder_name for character in '<>:"/\\|?*')
        or any(ord(character) < 32 for character in folder_name)
        or folder_name.endswith((".", " "))
        or re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?", folder_name, re.IGNORECASE)
    ):
        raise CurationError(f"Character names cannot be used as an output folder: {folder_name}")
    return folder_name


def sort_by_character_curation(images: Iterable[Path], output_dir: Path, progress: CurationProgress | None = None) -> list[CurationMoveResult]:
    resolved_output_dir = Path(output_dir).resolve()

    def process_block(block: list[Path], manifests: dict[Path, dict], pool: ThreadPoolExecutor) -> list[CurationMoveResult]:
        images_by_characters: dict[str, list[Path]] = {}
        resolved_destinations: dict[str, Path] = {}
        skipped_count = 0
        for image_path in block:
            folder_name = _character_folder_name(manifests[image_path])
            resolved_parent = image_path.parent.resolve()
            if _is_managed_resolved(resolved_parent, resolved_output_dir):
                raise CurationError(f"Images in managed folders cannot be moved: {image_path}")
            if folder_name not in resolved_destinations:
                resolved_destinations[folder_name] = (Path(output_dir) / folder_name).resolve()
            if resolved_parent == resolved_destinations[folder_name]:
                skipped_count += 1
                continue
            images_by_characters.setdefault(folder_name, []).append(image_path)
        return _move_grouped(images_by_characters, skipped_count, output_dir, progress, pool)

    return _run_in_blocks(images, progress, process_block)