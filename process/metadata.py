
import json
import os
from pathlib import Path
import uuid
from PIL import Image, PngImagePlugin


def get_imported_coordinate_mode(slot_data):
    return 'coordinate' if slot_data.get('use_coordinates', False) else 'auto'

def write_custom_metadata(input_path, output_path, key, value):
    """
    Copy a PNG from input_path to output_path, preserving existing text metadata,
    and atomically add or update a custom text key.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.tmp{output_path.suffix}"
    )
    copied_image = None

    try:
        with Image.open(input_path) as source_image:
            if source_image.format != "PNG":
                raise ValueError("Custom metadata can only be embedded in PNG images")
            source_image.load()
            copied_image = source_image.copy()
            source_info = dict(source_image.info)

        pnginfo = PngImagePlugin.PngInfo()
        for metadata_key, metadata_value in source_info.items():
            if isinstance(metadata_value, bytes):
                metadata_value = metadata_value.decode("utf-8", errors="ignore")
            if isinstance(metadata_value, str):
                pnginfo.add_text(metadata_key, metadata_value)

        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)

        pnginfo.add_text(key, value)
        copied_image.save(temporary_path, format="PNG", pnginfo=pnginfo)
        os.replace(temporary_path, output_path)
    finally:
        if copied_image is not None:
            copied_image.close()
        temporary_path.unlink(missing_ok=True)


def prepare_metadata(state, payload):
    character_number = state['global_prompt']['character_number']

    generate = {
        "model": state['generate']['model_name'],
        "sampler": state['generate']['sampler_name'],
        "schedule": state['generate']['schedule_name'],
        "steps": state['generate']['steps'],
        "seed": payload['parameters']['seed'],
        "scale": state['generate']['scale'],
        "rescale": state['generate']['rescale'],
        "cfg": state['generate']['cfg'],
        "legacy_v3": state['generate']['legacy_v3'],
        "legacy_v4": state['generate']['legacy_v4'],
        "SMEA": state['generate']['SMEA'],
        "DYN": state['generate']['DYN'],
        "variety+": state['generate']['variety+'],
        "decrisp": state['generate']['decrisp'],
        "brownian": state['generate']['brownian'],
        "size_name": state['generate']['size_name'],
    }

    global_prompt = {
        "global_positive_prompt": state['global_prompt']['global_positive_prompt'],
        "global_negative_prompt": state['global_prompt']['global_negative_prompt'],
        "global_positive_preset_name": state['global_prompt']['global_positive_preset_name'],
        "global_negative_preset_name": state['global_prompt']['global_negative_preset_name'],
        "global_positive_preset_tags": state['global_prompt']['global_positive_preset_tags'],
        "global_negative_preset_tags": state['global_prompt']['global_negative_preset_tags'],
        "character_number": state['global_prompt']['character_number'],
    }

    # ---- Characters ----
    characters = {}
    for index in range(1, character_number + 1):
        key = f"character_{index}"
        character = {
            "character": state[key]['character'],
            "character_positive_prompt": state[key]['character_positive_prompt'],
            "character_negative_prompt": state[key]['character_negative_prompt'],
            "character_static_positive_prompt": state[key].get('character_static_positive_prompt', ''),
            "character_static_negative_prompt": state[key].get('character_static_negative_prompt', ''),
            "character_disable_associations": state[key].get('character_disable_associations', False),
            "character_randomize_quick_weights": state[key].get('character_randomize_quick_weights', False),
            "character_quick_weights_positive_only": state[key].get('character_quick_weights_positive_only', False),
            "character_positive_quick_weights": state[key]['character_positive_quick_weights'],
            "character_negative_quick_weights": state[key]['character_negative_quick_weights'],
            "character_coordinate_button": state[key]['character_coordinate_button'],
            "character_x_coordinate": state[key]['character_x_coordinate'],
            "character_y_coordinate": state[key]['character_y_coordinate'],
            "use_coordinates": state[key].get('character_coordinate_mode', 'auto') in ('coordinate', 'random'),
            "character_preset_positive": state[key]['character_preset_positive'],
            "character_preset_negative": state[key]['character_preset_negative'],
            "character_preset_global_positive": state[key]['character_preset_global_positive'],
            "character_preset_global_negative": state[key]['character_preset_global_negative'],
            "character_outfit_preset_positive": state[key]['character_outfit_preset_positive'],
            "character_outfit_preset_negative": state[key]['character_outfit_preset_negative'],
            "most_recent_outfit": state[key]['most_recent_outfit'],
        }
        characters[key] = character

    # ---- Optional reference block (v4.5 only, when present) ----
    reference = None
    params = payload.get("parameters", {})
    director_images = params.get("director_reference_images")

    if director_images:
        # pull settings from character_1 in state
        char1 = state.get("character_1", {})
        reference = {
            "referenceb64": director_images,
            "character_reference_style_aware": char1.get("character_reference_style_aware"),
            "character_reference_fidelity": char1.get("character_reference_fidelity"),
            "character_reference_strength": char1.get("character_reference_strength"),
        }

    return {
        "characters": characters,
        "generate": generate,
        "global_prompt": global_prompt,
        "reference": reference,  # None if no director reference
        "post_quickweight_storage_update": True,  # marks metadata as capturing quick weight data
    }
