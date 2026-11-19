import random
from process.base64 import padded_image_to_b64
from process.metadata import prepare_metadata
from process.process_vibes import identify_vibe_images
from signaling.debug_signal import debug_info
from windows.error import Error
from data.datahub import wildcard_cache
from data.character_labels import label_values
from data.paths import ASSOCIATIONS_DIR, SUBSTITUTIONS_DIR, CHARACTERS_DIR, LABEL_ASSOCIATIONS_FILE
from data.label_associations import LABEL_MATCH_NONE, label_association_matches, load_label_associations
from data.mutators import effective_labels, is_active, tag_scope_matches
import random
import re
import json
import math
from pathlib import Path


_MAX_LOGGED_VALUE_LENGTH = 400


def _format_logged_value(value):
    text = str(value).strip()
    if len(text) > _MAX_LOGGED_VALUE_LENGTH:
        text = f"{text[:_MAX_LOGGED_VALUE_LENGTH]}..."
    return text or "(empty)"


def _format_logged_tags(tags):
    formatted = [_format_logged_value(tag) for tag in tags]
    return " | ".join(formatted) if formatted else "(empty)"


def _log_prompt(scope, message):
    if not scope:
        return
    debug_info(f"Prompt/{scope}", message)


def _log_prompt_input(scope, label, value):
    if not scope:
        return
    if isinstance(value, (list, tuple)):
        if not value:
            return
        rendered = _format_logged_tags(value)
    else:
        if value is None or str(value).strip() == "":
            return
        rendered = _format_logged_value(value)
    _log_prompt(scope, f"input [{label}]: {rendered}")


def _log_tag_added(scope, tag, reason):
    _log_prompt(scope, f"+ '{_format_logged_value(tag)}' ({reason})")


def _log_tag_removed(scope, tag, reason):
    _log_prompt(scope, f"- '{_format_logged_value(tag)}' ({reason})")


def _log_tag_changed(scope, before, after, reason):
    _log_prompt(
        scope,
        f"~ '{_format_logged_value(before)}' -> '{_format_logged_value(after)}' ({reason})",
    )



def _log_final_prompt(scope, prompt_text):
    _log_prompt(scope, f"final output: {_format_logged_value(prompt_text)}")


def _state_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


_RANDOM_WEIGHT_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_RANDOM_WEIGHT_PATTERN = re.compile(
    rf"!(?P<tag>[^!\r\n]+)!\s*(?P<lower>{_RANDOM_WEIGHT_NUMBER})\s*!"
    rf"\s*(?P<upper>{_RANDOM_WEIGHT_NUMBER})\s*!"
)
_RANDOM_WEIGHT_CANDIDATE = re.compile(
    r"(?<!\w)!(?P<tag>[^!,\r\n]*)!(?P<lower>[^!,\r\n]*)!(?P<upper>[^!,\r\n]*)!"
)


def _resolve_random_weights(prompt, scope):
    def replace(match):
        tag = match.group("tag").strip()
        lower = float(match.group("lower"))
        upper = float(match.group("upper"))
        if not tag or not math.isfinite(lower) or not math.isfinite(upper):
            raise ValueError(f"{scope}: invalid random weight syntax: {match.group(0)}")
        sampled = random.uniform(min(lower, upper), max(lower, upper))
        if not math.isfinite(sampled):
            raise ValueError(f"{scope}: invalid random weight range: {match.group(0)}")
        weight = round(sampled, 1)
        if weight == 0:
            weight = 0.0
        return f"{weight:.1f}::{tag}::"

    resolved = _RANDOM_WEIGHT_PATTERN.sub(replace, prompt)
    for match in _RANDOM_WEIGHT_CANDIDATE.finditer(resolved):
        lower = match.group("lower").strip()
        upper = match.group("upper").strip()
        if re.fullmatch(_RANDOM_WEIGHT_NUMBER, lower) or re.fullmatch(_RANDOM_WEIGHT_NUMBER, upper):
            raise ValueError(f"{scope}: invalid random weight syntax: {match.group(0)}")
    return resolved


def _resolve_payload_random_weights(payload):
    parameters = payload["parameters"]
    positive = _resolve_random_weights(payload["input"], "Base Positive")
    negative = _resolve_random_weights(parameters["negative_prompt"], "Base Negative")
    payload["input"] = positive
    parameters["negative_prompt"] = negative

    for key, base, label in (
        ("v4_prompt", positive, "Positive"),
        ("v4_negative_prompt", negative, "Negative"),
    ):
        if key not in parameters:
            continue
        caption = parameters[key]["caption"]
        caption["base_caption"] = base
        for index, character in enumerate(caption.get("char_captions", []), 1):
            character["char_caption"] = _resolve_random_weights(
                character["char_caption"], f"Character {index} {label}"
            )


def prepare_generate_payload(state):
    # Reset per-character negative-injection scratch space before each payload build.
    character_count = state.get('global_prompt', {}).get('character_number', 0)
    for index in range(1, character_count + 1):
        character_state = state.get(f'character_{index}')
        if isinstance(character_state, dict):
            character_state['_pending_negative_injections'] = []

    version = state['generate']['payload_type']
    _log_prompt("Payload", f"processing prompts for a {version} payload")
    if version == 'v3':
        payload, metadata = prepare_v3_payload(state, version)

    elif version == 'v4':
       payload, metadata = prepare_v4_payload(state, version)
        
    elif version == 'v45':
        payload, metadata = prepare_v45_payload(state, version)

    elif version == 'v5':
        payload, metadata = prepare_v5_payload(state, version)

    _resolve_payload_random_weights(payload)
    _log_prompt("Payload", f"final base positive prompt: {_format_logged_value(payload.get('input'))}")
    _log_prompt(
        "Payload",
        f"final base negative prompt: {_format_logged_value(payload.get('parameters', {}).get('negative_prompt'))}",
    )
    for character_payload in payload.get('parameters', {}).get('v4_prompt', {}).get('caption', {}).get('char_captions', []):
        _log_prompt("Payload", f"final character positive caption: {_format_logged_value(character_payload.get('char_caption'))}")
    for character_payload in payload.get('parameters', {}).get('v4_negative_prompt', {}).get('caption', {}).get('char_captions', []):
        _log_prompt("Payload", f"final character negative caption: {_format_logged_value(character_payload.get('char_caption'))}")

    return payload, metadata


def prepare_v3_payload(state, version):

    positive_prompt = prepare_positive_prompt(state, version)
    negative_prompt = prepare_negative_prompt(state, version)
    brownian = prepare_brownian(state)
    seed = generate_seed(state)
    cfg = prepare_cfg(state)
    payload = {
    "action": "generate",
    "input": positive_prompt, #string
    "model": state['generate']['payload_name'],# string
    "parameters": {
        "add_original_image": True, #bool
        "cfg_rescale": state['generate']['rescale'], #number
        "controlnet_strength": 1,
        "dynamic_thresholding": state['generate']['decrisp'], #bool
        "height": state['generate']['image_height'], #int
        "legacy_v3_extend": state['generate']['legacy_v3'], #bool
        "n_samples": 1,
        "negative_prompt": negative_prompt, #string
        "noise_schedule": state['generate']['schedule'], #string
        "sampler": state['generate']['sampler'], #string
        "scale": state['generate']['scale'], #number
        "seed": seed, #int
        "sm": state['generate']['SMEA'], #bool
        "sm_dyn": state['generate']['DYN'], #bool
        "steps": state['generate']['steps'], #number
        "width": state['generate']['image_width'], #int
        "skip_cfg_above_sigma":cfg, #number
        "deliberate_euler_ancestral_bug": brownian[1],
        "prefer_brownian": brownian[0]
    }
}
    metadata = prepare_metadata(state, payload)
    return payload, metadata

def _coordinate_mode_enabled_for_payload(state):
    character_count = state.get('global_prompt', {}).get('character_number', 0)
    for index in range(1, character_count + 1):
        character_key = f"character_{index}"
        coordinate_mode = str(
            state.get(character_key, {}).get('character_coordinate_mode', 'auto')
        ).lower()
        if coordinate_mode in ('coordinate', 'random'):
            return True
    return False


def prepare_v4_payload(state, version):
        
    positive_prompt = prepare_positive_prompt(state, version)
    negative_prompt = prepare_negative_prompt(state, version)
    positive_character_captions = prepare_positive_character_prompt(state)
    negative_character_captions = prepare_negative_character_prompt(state)
    seed = generate_seed(state)
    cfg = prepare_cfg(state)
    brownian = prepare_brownian(state)
    coordinate_mode_enabled = _coordinate_mode_enabled_for_payload(state)

    if state['vibe']['vibe_enabled'] and state['vibe']['reference_image_paths'] != []:
        vibe_encodings = identify_vibe_images(state)
        vibe_reference_strength = state['vibe']['reference_strengths']
        vibe_normalize_strength = state['vibe']['normalize_strength']
        
    else:
        vibe_encodings = []
        vibe_reference_strength = []
        vibe_normalize_strength = False

    payload = {
    "action": "generate",
    "input": positive_prompt,
    "model": state['generate']['payload_name'],
    "parameters": {
        "add_original_image": True,
        "cfg_rescale": state['generate']['rescale'],
        "legacy_uc": state['generate']['legacy_v4'],
        "controlnet_strength": 1,
        "deliberate_euler_ancestral_bug": brownian[1],
        "prefer_brownian": brownian[0],
        "dynamic_thresholding": False, #can v4 use this? its in the payload but theres no toggle. Set to false for now. It can, the effect seems minor.
        "height": state['generate']['image_height'],
        "width": state['generate']['image_width'],
        "n_samples": 1,
        "negative_prompt": negative_prompt,
        "noise_schedule": state['generate']['schedule'],
        "sampler": state['generate']['sampler'],
        "scale": state['generate']['scale'],
        "seed": seed,
        "normalize_reference_strength_multiple": vibe_normalize_strength,
        "reference_strength_multiple": vibe_reference_strength,
        "reference_image_multiple": vibe_encodings,
        "skip_cfg_above_sigma": cfg,
        "steps": state['generate']['steps'],
        "use_coords": coordinate_mode_enabled,
        "v4_negative_prompt": {
            "caption": {
                "base_caption": negative_prompt,
                "char_captions": negative_character_captions
            },
            "legacy_uc": state['generate']['legacy_v4'],
            "use_coords": False
        },
        "v4_prompt": {
            "caption": {
                "base_caption": positive_prompt,
                "char_captions": positive_character_captions
            },
            "use_coords": coordinate_mode_enabled,
            "use_order": True # if one of these is true, the negative version will be false. AI choice = coords false, order true. Non AI Choice = Both true.
        },
    }
}
    metadata = prepare_metadata(state, payload)
    return payload, metadata

def prepare_v45_payload(state, version):
        
    positive_prompt = prepare_positive_prompt(state, version)
    negative_prompt = prepare_negative_prompt(state, version)
    positive_character_captions = prepare_positive_character_prompt(state)
    negative_character_captions = prepare_negative_character_prompt(state)
    seed = generate_seed(state)
    cfg = prepare_cfg(state)
    brownian = prepare_brownian(state)

    if state['vibe']['vibe_enabled'] and state['vibe']['reference_image_paths'] != []:
        vibe_encodings = identify_vibe_images(state)
        vibe_reference_strength = state['vibe']['reference_strengths']
        vibe_normalize_strength = state['vibe']['normalize_strength']
        using_vibe = True
        
    else:
        vibe_encodings = []
        vibe_reference_strength = []
        vibe_normalize_strength = False
    

    coordinate_mode_enabled = _coordinate_mode_enabled_for_payload(state)

    if state['character_1']['character_reference_enabled'] and state['character_1']['character_reference_path'] != None:
        if using_vibe:
            Error(None, "Vibe and Character Reference cannot be used together. Generation payload not created.")
            return None, None

        referenceb64 = padded_image_to_b64(state['character_1']['character_reference_path'])
        fidelity = float(state['character_1']['character_reference_fidelity'])
        styleaware = state['character_1']['character_reference_style_aware']
        refstrength = state['character_1']['character_reference_strength']
        
        payload = {
        "action": "generate",
        "input": positive_prompt, 
        "model": state['generate']['payload_name'],
        "parameters": {
            "add_original_image": True,
            "cfg_rescale": state['generate']['rescale'],
            "controlnet_strength": 1,
            "deliberate_euler_ancestral_bug": brownian[1],
            "prefer_brownian": brownian[0],
            "dynamic_thresholding": False, 
            "height": state['generate']['image_height'],
            "width": state['generate']['image_width'],
            "n_samples": 1,
            "negative_prompt": negative_prompt,
            "noise_schedule": state['generate']['schedule'],
            "sampler": state['generate']['sampler'],
            "scale": state['generate']['scale'],
            "seed": seed,
            "skip_cfg_above_sigma": cfg,
            "steps": state['generate']['steps'],
            "normalize_reference_strength_multiple": vibe_normalize_strength,
            "reference_strength_multiple": vibe_reference_strength,
            "reference_image_multiple": vibe_encodings,
            "use_coords": coordinate_mode_enabled,
            "v4_negative_prompt": {
                "caption": {
                    "base_caption": negative_prompt,
                    "char_captions": negative_character_captions
                },
                "use_coords": False
            },
            "v4_prompt": {
                "caption": {
                    "base_caption": positive_prompt,
                    "char_captions": positive_character_captions
                },
                "use_coords": coordinate_mode_enabled,
                "use_order": True # if one of these is true, the negative version will be false. AI choice = coords false, order true. Non AI Choice = Both true.
            },
            
        "director_reference_descriptions": [{
            "caption": {
                "base_caption": styleaware,
                "char_captions": []
            },
            "legacy_uc": False
        }],
        "director_reference_images": [referenceb64],  # raw base64, PNG preferred
        "director_reference_information_extracted": [1], #must be 1 or will return 500 error
        "director_reference_secondary_strength_values": [fidelity], #this value is tied to fidelity, range 0-1 float
        "director_reference_strength_values": [refstrength] #Defraults to 1 on the website, can be any value
            
        }
    }
        
        metadata = prepare_metadata(state, payload)
        return payload, metadata

        
    else:
        payload = {
        "action": "generate",
        "input": positive_prompt, 
        "model": state['generate']['payload_name'],
        "parameters": {
            "add_original_image": True,
            "cfg_rescale": state['generate']['rescale'],
            "controlnet_strength": 1,
            "deliberate_euler_ancestral_bug": brownian[1],
            "prefer_brownian": brownian[0],
            "dynamic_thresholding": False, 
            "height": state['generate']['image_height'],
            "width": state['generate']['image_width'],
            "n_samples": 1,
            "negative_prompt": negative_prompt,
            "noise_schedule": state['generate']['schedule'],
            "sampler": state['generate']['sampler'],
            "scale": state['generate']['scale'],
            "seed": seed,
            "normalize_reference_strength_multiple": vibe_normalize_strength,
            "reference_strength_multiple": vibe_reference_strength,
            "reference_image_multiple": vibe_encodings,
            "skip_cfg_above_sigma": cfg,
            "steps": state['generate']['steps'],
            "use_coords": coordinate_mode_enabled,
            "v4_negative_prompt": {
                "caption": {
                    "base_caption": negative_prompt,
                    "char_captions": negative_character_captions
                },
                "use_coords": False
            },
            "v4_prompt": {
                "caption": {
                    "base_caption": positive_prompt,
                    "char_captions": positive_character_captions
                },
                "use_coords": coordinate_mode_enabled,
                "use_order": True # if one of these is true, the negative version will be false. AI choice = coords false, order true. Non AI Choice = Both true.
            },
        }
    }
        

        metadata = prepare_metadata(state, payload)
        return payload, metadata


def prepare_v5_payload(state, version):
        
    positive_prompt = prepare_positive_prompt(state, version)
    negative_prompt = prepare_negative_prompt(state, version)
    positive_character_captions = prepare_positive_character_prompt(state)
    negative_character_captions = prepare_negative_character_prompt(state)
    seed = generate_seed(state)
    cfg = prepare_cfg(state)
    brownian = prepare_brownian(state)
    coordinate_mode_enabled = _coordinate_mode_enabled_for_payload(state)

    payload = payload = {
            "action": "generate",
            "input": positive_prompt, 
            "model": state['generate']['payload_name'],
            "parameters": {
                "add_original_image": True,
                "cfg_rescale": state['generate']['rescale'],
                "controlnet_strength": 1,
                "deliberate_euler_ancestral_bug": brownian[1],
                "prefer_brownian": brownian[0],
                "dynamic_thresholding": False, 
                "height": state['generate']['image_height'],
                "width": state['generate']['image_width'],
                "n_samples": 1,
                "negative_prompt": negative_prompt,
                "noise_schedule": state['generate']['schedule'],
                "sampler": state['generate']['sampler'],
                "scale": state['generate']['scale'],
                "seed": seed,
                "skip_cfg_above_sigma": cfg,
                "steps": state['generate']['steps'],
                "use_coords": coordinate_mode_enabled,
                "v4_negative_prompt": {
                    "caption": {
                        "base_caption": negative_prompt,
                        "char_captions": negative_character_captions
                    },
                    "use_coords": False
                },
                "v4_prompt": {
                    "caption": {
                        "base_caption": positive_prompt,
                        "char_captions": positive_character_captions
                    },
                    "use_coords": coordinate_mode_enabled,
                    "use_order": True # if one of these is true, the negative version will be false. AI choice = coords false, order true. Non AI Choice = Both true.
                },
            }
        }
    

    metadata = prepare_metadata(state, payload)
    return payload, metadata



def _split_prompt_entries(raw_text) -> list[str]:
    """
    Split prompt text on commas while preserving commas inside inline substitution calls,
    and double-quoted phrases.
    Inline substitution format: $cN$trigger$inject$
    """
    if raw_text is None:
        return []

    normalized_text = str(raw_text).replace('\n', ',').replace('\r', ',')

    entries = []
    current = []
    in_inline_call = False
    inline_dollar_count = 0
    in_double_quotes = False

    def _clean_entry(entry: str) -> str:
        cleaned = entry.strip()
        if cleaned.lower().startswith('text:') and cleaned.endswith(','):
            return cleaned[:-1].rstrip()
        if cleaned.startswith('"') and cleaned.endswith(','):
            return cleaned[:-1].rstrip()
        return cleaned

    for char in normalized_text:
        if char == '$':
            if not in_inline_call:
                in_inline_call = True
                inline_dollar_count = 1
            else:
                inline_dollar_count += 1
                if inline_dollar_count >= 4:
                    in_inline_call = False
                    inline_dollar_count = 0

            current.append(char)
            continue

        if char == '"' and not in_inline_call:
            in_double_quotes = not in_double_quotes
            current.append(char)
            continue

        if char == ',' and not in_inline_call and not in_double_quotes:
            cleaned = _clean_entry(''.join(current))
            if cleaned:
                entries.append(cleaned)
            current = []
            continue

        current.append(char)

    cleaned = _clean_entry(''.join(current))
    if cleaned:
        entries.append(cleaned)

    return entries


def _scramble_prompt_text(raw_text):
    entries = _split_prompt_entries(raw_text)
    first_entries = []
    movable_entries = []
    last_entries = []

    for entry in entries:
        normalized = entry.strip().lower()
        position_tag = normalized.strip("{}[]")
        if position_tag in {"fur_dataset", "fur dataset"}:
            first_entries.append(entry)
        elif normalized.startswith("text:") or (normalized.startswith('"') and normalized.endswith('"')):
            last_entries.append(entry)
        else:
            movable_entries.append(entry)

    random.shuffle(movable_entries)
    return ", ".join(first_entries + movable_entries + last_entries)


def _modifier_enabled(state, key):
    return _state_bool(state.get('modifiers', {}).get(key, False))


def prepare_positive_prompt(state, version):
    scope = "Base Positive"
    prompt = []
    preset = state['global_prompt']['global_positive_preset_tags']
    target = state['global_prompt']['global_positive_preset_target']
    character_count = state['global_prompt']['character_number']

    _log_prompt(scope, f"building base positive prompt ({version}, {character_count} character(s))")

    global_positive_prompt = state['global_prompt']['global_positive_prompt']
    _log_prompt_input(scope, "global positive prompt", global_positive_prompt)
    if global_positive_prompt != "" and global_positive_prompt != None:
        split_global_positive = _split_prompt_entries(global_positive_prompt)
        prompt.extend(split_global_positive)
    else:
        pass

    artist_entries = state.get('artist', {}).get('prompt_entries', [])
    _log_prompt_input(scope, "artist entries", artist_entries)
    prompt.extend(artist_entries)

    if character_count > 0:
        for index in range(1, character_count + 1):
            key = f'character_{index}'
            character_scope = f"{scope}/Character {index}"
            preset_global_positive = state[key]['character_preset_global_positive']
            _log_prompt_input(character_scope, "character global positive preset", preset_global_positive)
            if preset_global_positive != '' and preset_global_positive != None:
                split_preset_global_positive = _split_prompt_entries(preset_global_positive)
                prompt.extend(split_preset_global_positive)
            else:
                pass

            character_tags = []
            if version == 'v3':
                quick_weights = state[f'character_{index}']['character_positive_quick_weights']
                _log_prompt_input(character_scope, "positive quick weights", quick_weights)
                for qw in quick_weights:
                    character_tags.append(qw)

                preset_positive = state[f'character_{index}']['character_preset_positive']
                _log_prompt_input(character_scope, "character positive preset", preset_positive)
                if preset_positive != None and preset_positive != "":
                    split_preset_positive = _split_prompt_entries(preset_positive)
                    character_tags.extend(split_preset_positive)

                prompt_positive = state[f'character_{index}']['character_positive_prompt']
                _log_prompt_input(character_scope, "character positive prompt", prompt_positive)
                if prompt_positive != "" and prompt_positive != None:
                    split_prompt_positive = _split_prompt_entries(prompt_positive)
                    character_tags.extend(split_prompt_positive)

                static_positive = state[key].get('character_static_positive_prompt', '')
                _log_prompt_input(character_scope, "static positive prompt", static_positive)
                if static_positive:
                    character_tags.extend(_split_prompt_entries(static_positive))

                character_tags.extend(_roll_character_chance_tags(state, key, scope=character_scope))

            if version == 'v3':
                key_negative_injections = []
                character_tags = handle_assocations(
                    character_tags,
                    state,
                    key,
                    include_global_associations=_state_bool(state[key].get('character_global_tag_association_enabled', False)),
                    shared_prompt=prompt,
                    negative_sink=key_negative_injections,
                    scope=character_scope,
                )
                state[key].setdefault('_pending_negative_injections', []).extend(key_negative_injections)

            prompt.extend(handle_gender_inversion(character_tags, state, state[key], scope=character_scope))

            if version in {'v4', 'v45', 'v5'}:
                key_negative_injections = []
                handle_assocations(
                    [],
                    state,
                    key,
                    include_global_associations=_state_bool(state[key].get('character_global_tag_association_enabled', False)),
                    shared_prompt=prompt,
                    apply_injections=False,
                    evaluate_absent_triggers=False,
                    negative_sink=key_negative_injections,
                    scope=character_scope,
                )
                state[key].setdefault('_pending_negative_injections', []).extend(key_negative_injections)

    _log_prompt_input(scope, "global positive preset tags", preset)
    if preset != '' and preset != None:
        if target == 'end':
            split_preset = _split_prompt_entries(preset)
            prompt.extend(split_preset)
        elif target == 'start':
            split_preset = _split_prompt_entries(preset)
            for item in reversed(split_preset):
                prompt.insert(0, item)
    else:
        pass
    _log_prompt(scope, f"assembled tags: {_format_logged_tags(prompt)}")
    prompt = [tag.strip() for tag in prompt]
    prompt = resolve_wildcards(prompt, scope=scope)
    prompt = handle_substitutions(prompt, state, scope=scope)
    prompt = handle_gender_inversion(prompt, state, scope=scope)
    prompt = handle_character_name(prompt, state, scope=scope)
    prompt = _unwrap_hash_guard_tags(prompt, scope=scope)
    prompt = text_to_bottom(prompt, scope=scope)
    final_prompt = ", ".join(prompt)
    if _modifier_enabled(state, 'scramble_global_positive'):
        final_prompt = _scramble_prompt_text(final_prompt)
        _log_prompt(scope, "tag order scrambled (scramble global positive modifier is enabled)")
    _log_final_prompt(scope, final_prompt)
    return final_prompt

def prepare_negative_prompt(state, version):
    scope = "Base Negative"
    prompt = []
    preset = state['global_prompt']['global_negative_preset_tags']
    character_count = state['global_prompt']['character_number']

    _log_prompt(scope, f"building base negative prompt ({version}, {character_count} character(s))")

    global_negative_prompt = state['global_prompt']['global_negative_prompt']
    _log_prompt_input(scope, "global negative prompt", global_negative_prompt)
    if global_negative_prompt != "" and global_negative_prompt != None:
        split_global_negative = _split_prompt_entries(global_negative_prompt)
        prompt.extend(split_global_negative)
    
    if character_count > 0:
        for index in range(1, character_count + 1):
            key = f'character_{index}'
            character_scope = f"{scope}/Character {index}"
            preset_global_negative = state[key]['character_preset_global_negative']
            _log_prompt_input(character_scope, "character global negative preset", preset_global_negative)
            if preset_global_negative != None and preset_global_negative != '':
                split_preset_global_negative = _split_prompt_entries(preset_global_negative)
                prompt.extend(split_preset_global_negative)

            character_tags = []
            if version == 'v3':
                    
                    quick_weights = state[f'character_{index}']['character_negative_quick_weights']
                    _log_prompt_input(character_scope, "negative quick weights", quick_weights)
                    for qw in quick_weights:
                        character_tags.append(qw)

                    preset_negative = state[f'character_{index}']['character_preset_negative']
                    _log_prompt_input(character_scope, "character negative preset", preset_negative)
                    if preset_negative != None and preset_negative != "":
                        split_preset_negative = _split_prompt_entries(preset_negative)
                        character_tags.extend(split_preset_negative)

                    prompt_negative = state[f'character_{index}']['character_negative_prompt']
                    _log_prompt_input(character_scope, "character negative prompt", prompt_negative)
                    if prompt_negative != "" and prompt_negative != None:
                        split_prompt_negative = _split_prompt_entries(prompt_negative)
                        character_tags.extend(split_prompt_negative)

                    static_negative = state[key].get('character_static_negative_prompt', '')
                    _log_prompt_input(character_scope, "static negative prompt", static_negative)
                    if static_negative:
                        character_tags.extend(_split_prompt_entries(static_negative))

                    # Associations are not re-checked against negative tags; only
                    # positive-triggered negative injections are applied here.
                    pending_negative_injections = state[key].get('_pending_negative_injections') or []
                    for injected_tag in pending_negative_injections:
                        _log_tag_added(character_scope, injected_tag, "negative injection queued by a positive association")
                    character_tags.extend(pending_negative_injections)

            prompt.extend(handle_gender_inversion(character_tags, state, state[key], scope=character_scope))
    
    _log_prompt_input(scope, "global negative preset tags", preset)
    if preset != None and preset != '':
        prompt.append(preset)

    _log_prompt(scope, f"assembled tags: {_format_logged_tags(prompt)}")
    prompt = [tag.strip() for tag in prompt]
    prompt = resolve_wildcards(prompt, scope=scope)
    prompt = handle_substitutions(prompt, state, scope=scope)
    prompt = handle_gender_inversion(prompt, state, scope=scope)
    prompt = _unwrap_hash_guard_tags(prompt, scope=scope)
    final_prompt = ", ".join(prompt)
    if _modifier_enabled(state, 'scramble_global_negative'):
        final_prompt = _scramble_prompt_text(final_prompt)
        _log_prompt(scope, "tag order scrambled (scramble global negative modifier is enabled)")
    _log_final_prompt(scope, final_prompt)
    return final_prompt

def prepare_positive_character_prompt(state):
    character_captions = []
    character_count = state['global_prompt']['character_number']

    for id in range(1, character_count + 1):
        if id <= character_count:
            key = f"character_{id}"
            scope = f"Character {id} Positive"

            caption = []

            quick_weights = state[key]['character_positive_quick_weights']
            _log_prompt_input(scope, "positive quick weights", quick_weights)
            for weight in quick_weights:
                caption.append(weight)

            preset_positive = state[key]['character_preset_positive']
            _log_prompt_input(scope, "character positive preset", preset_positive)
            if preset_positive != None and preset_positive != "":
                split_preset_positive = _split_prompt_entries(preset_positive)
                caption.extend(split_preset_positive)
                
            caption.extend(_roll_character_chance_tags(state, key, scope=scope))

            outfit_positive = state[key]['character_outfit_preset_positive']
            _log_prompt_input(scope, "outfit positive preset", outfit_positive)
            if outfit_positive != None and outfit_positive != "":
                split_outfit_positive = _split_prompt_entries(outfit_positive)
                caption.extend(split_outfit_positive)

            prompt_positive = state[key]['character_positive_prompt']
            _log_prompt_input(scope, "character positive prompt", prompt_positive)
            if prompt_positive != None and prompt_positive != "":
                split_prompt_positive = _split_prompt_entries(prompt_positive)
                caption.extend(split_prompt_positive)

            static_positive = state[key].get('character_static_positive_prompt', '')
            _log_prompt_input(scope, "static positive prompt", static_positive)
            if static_positive:
                caption.extend(_split_prompt_entries(static_positive))

            _log_prompt(scope, f"assembled tags: {_format_logged_tags(caption)}")

            

            # Handle default expression if enabled
            if state[key].get('use_default_expression', False):
                default_expression = state[key].get('character_default_expression', [])
                for tag in default_expression:
                    cleaned_tag = tag['tag'].strip()
                    if tag['strength'] == 1.0:
                        caption.append(tag['tag'])
                    else:
                        caption.append(f"{tag['strength']:.1f}::{cleaned_tag}::")
                    _log_tag_added(scope, caption[-1], "default expression is enabled for this character")
                
            key_negative_injections = []
            caption = handle_assocations(
                caption,
                state,
                key,
                include_global_associations=_state_bool(state[key].get('character_global_tag_association_enabled', False)),
                negative_sink=key_negative_injections,
                scope=scope,
            )
            state[key].setdefault('_pending_negative_injections', []).extend(key_negative_injections)
            caption = _apply_outfit_removals(caption, state, key, scope=scope)
            caption = handle_substitutions (caption, state, scope=scope)
            caption = resolve_wildcards(caption, scope=scope)
            caption = handle_gender_inversion(caption, state, state[key], scope=scope)
            caption = _unwrap_hash_guard_tags(caption, scope=scope)
            caption = text_to_bottom(caption, scope=scope)
            joined_caption = ", ".join(caption)
            if _modifier_enabled(state, 'scramble_character_positive') and _state_bool(state[key].get('character_can_scramble', False)):
                joined_caption = _scramble_prompt_text(joined_caption)
                _log_prompt(scope, "tag order scrambled (scramble character positive modifier is enabled)")

            _log_final_prompt(scope, joined_caption)


            payload = {
                "centers": [
                    {
                        "x": state[key]['character_x_coordinate'],
                        "y": state[key]['character_y_coordinate']
                    }
                ],
                "char_caption": joined_caption
            }
            character_captions.append(payload)
    return character_captions

def prepare_negative_character_prompt(state):
    character_captions = []
    character_count = state['global_prompt']['character_number']

    for id in range(1, character_count + 1):
        if id <= character_count:
            key = f"character_{id}"
            scope = f"Character {id} Negative"

            caption = []

            quick_weights = state[key]['character_negative_quick_weights']
            _log_prompt_input(scope, "negative quick weights", quick_weights)
            for weight in quick_weights:
                caption.append(weight)

            preset_negative = state[key]['character_preset_negative']
            _log_prompt_input(scope, "character negative preset", preset_negative)
            if preset_negative != None and preset_negative != "":
                split_preset_negative = _split_prompt_entries(preset_negative)
                caption.extend(split_preset_negative)

            outfit_negative = state[key]['character_outfit_preset_negative']
            _log_prompt_input(scope, "outfit negative preset", outfit_negative)
            if outfit_negative != None and outfit_negative != "":
                split_outfit_negative = _split_prompt_entries(outfit_negative)
                caption.extend(split_outfit_negative)

            prompt_negative = state[key]['character_negative_prompt']
            _log_prompt_input(scope, "character negative prompt", prompt_negative)
            if prompt_negative != "" and prompt_negative != None:
                split_prompt_negative = _split_prompt_entries(prompt_negative)
                caption.extend(split_prompt_negative)   

            static_negative = state[key].get('character_static_negative_prompt', '')
            _log_prompt_input(scope, "static negative prompt", static_negative)
            if static_negative:
                caption.extend(_split_prompt_entries(static_negative))

            caption = [tag.strip() for tag in caption]
            _log_prompt(scope, f"assembled tags: {_format_logged_tags(caption)}")

            # Associations are not re-checked against negative tags; only
            # positive-triggered negative injections are applied here.
            pending_negative_injections = state[key].get('_pending_negative_injections') or []
            for injected_tag in pending_negative_injections:
                _log_tag_added(scope, injected_tag, "negative injection queued by a positive association")
            caption.extend(pending_negative_injections)
            caption = _apply_outfit_removals(caption, state, key, scope=scope)

            caption = handle_substitutions(caption, state, scope=scope)
            caption = resolve_wildcards(caption, scope=scope)
            caption = handle_gender_inversion(caption, state, state[key], scope=scope)
            caption = _unwrap_hash_guard_tags(caption, scope=scope)
            joined_caption = ", ".join(caption)
            if _modifier_enabled(state, 'scramble_character_negative') and _state_bool(state[key].get('character_can_scramble', False)):
                joined_caption = _scramble_prompt_text(joined_caption)
                _log_prompt(scope, "tag order scrambled (scramble character negative modifier is enabled)")

            _log_final_prompt(scope, joined_caption)
            
            payload = {
                "centers": [
                    {
                        "x": state[key]['character_x_coordinate'],
                        "y": state[key]['character_y_coordinate']
                    }
                ],
                "char_caption": joined_caption
            }
            character_captions.append(payload)
    return character_captions

def generate_seed(state):
    state_seed = state['generate']['seed']
    if state_seed > 0:
        return state_seed
    else:
        random_seed = random.randint(1, 4294967295)
        return random_seed
    
def prepare_cfg(state):
    if state['generate']['variety+']:
        return state['generate']['variety+_value']
    else:
        state_cfg = state['generate']['cfg']
        if state_cfg >= 0:
            return state_cfg
        else:
            return None
        
def prepare_brownian(state):
    if state['generate']['brownian']:
        return (True, False)
    else:
        return (False, True)
    

def resolve_wildcards(tags: list[str], scope=None) -> list[str]:
    """
    Resolves wildcard tokens (*wildcard_name*) in a list of tags.
    Each tag is repeatedly scanned until no wildcards remain or none can be resolved.
    """
    resolved_tags = []

    for tag in tags:
        resolved = _resolve_tag_wildcards(tag)
        if scope and str(resolved) != str(tag):
            _log_tag_changed(scope, tag, resolved, "wildcard resolved")
        resolved_tags.append(resolved)

    return resolved_tags


def _resolve_tag_wildcards(tag: str) -> str:
    return _resolve_wildcard_text(str(tag), (), 0)


def _resolve_wildcard_text(text: str, active_keys: tuple[str, ...], depth: int) -> str:
    if depth >= 64:
        return text

    matches = list(re.finditer(r'\*([^*]+)\*', text))
    if not matches:
        return text

    resolved_parts = []
    cursor = 0
    for match in matches:
        wildcard_key = match.group(1)
        resolved_parts.append(text[cursor:match.start()])
        if wildcard_key in active_keys:
            replacement = match.group(0)
        else:
            sampled = _sample_wildcard(wildcard_key)
            replacement = (
                match.group(0)
                if sampled is None
                else _resolve_wildcard_text(sampled, active_keys + (wildcard_key,), depth + 1)
            )
        resolved_parts.append(replacement)
        cursor = match.end()

    resolved_parts.append(text[cursor:])
    return "".join(resolved_parts)


def _sample_wildcard(key: str) -> str | None:
    wildcard = wildcard_cache.get(key)
    if wildcard is None:
        return None

    values = wildcard.get("values", [])
    if not values:
        return None

    population = [entry["text"] for entry in values]
    weights = [entry.get("weight", 1) for entry in values]

    result = random.choices(population, weights=weights, k=1)[0]
    return result

def _normalize_association_tag(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _format_association_injection(entry) -> str:
    if isinstance(entry, dict):
        tag = str(entry.get("tag", "")).strip()
        try:
            strength = float(entry.get("strength", 1.0))
        except (TypeError, ValueError):
            strength = 1.0
        if not tag:
            return ""
        return tag if strength == 1.0 else f"{strength}::{tag}::"
    return str(entry).strip()

def _apply_outfit_removals(caption, state, key, scope=None):
    """Strip any tags the currently selected outfit declares in its 'remove' list."""
    removal_tags = state[key].get('character_outfit_removals') or []
    if not removal_tags:
        return caption

    normalized_removals = {
        _normalize_association_tag(_strip_weighted_prompt_tag(str(tag)))
        for tag in removal_tags
        if str(tag).strip()
    }
    if not normalized_removals:
        return caption

    kept_entries = []
    for entry in caption:
        if _normalize_association_tag(_strip_weighted_prompt_tag(str(entry))) in normalized_removals:
            _log_tag_removed(scope, entry, "listed in the selected outfit's removal list")
            continue
        kept_entries.append(entry)

    return kept_entries

def _strip_weighted_prompt_tag(tag):
    if not isinstance(tag, str):
        return ""

    cleaned = tag.strip()
    weighted_match = re.fullmatch(r'(?P<strength>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*::\s*(?P<tag>.*?)\s*::\s*', cleaned)
    if weighted_match:
        return weighted_match.group('tag').strip()

    return cleaned

def _extract_slot_substitution_payload(payload: str):
    cleaned = str(payload or "").strip()
    if not cleaned:
        return None, ""

    weighted_match = re.fullmatch(r'(?P<strength>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*::\s*(?P<tag>.*?)\s*::\s*', cleaned)
    if weighted_match:
        strength = weighted_match.group('strength').strip()
        target_tag = weighted_match.group('tag').strip()
        if target_tag:
            return strength, target_tag
        return None, ""

    inner_weighted_match = re.fullmatch(r'::\s*(?P<tag>.*?)\s*::\s*', cleaned)
    if inner_weighted_match:
        target_tag = inner_weighted_match.group('tag').strip()
        return None, target_tag

    target_tag = cleaned
    return None, target_tag

def _format_substitution_value(strength, tag_value):
    cleaned_tag = str(tag_value or "").strip()
    if not cleaned_tag:
        return ""

    if strength is None or str(strength).strip() == "":
        return cleaned_tag

    return f"{str(strength).strip()}::{cleaned_tag}::"

def _unwrap_hash_guard_tags(tags: list[str], scope=None) -> list[str]:
    unwrapped_tags = []

    for tag in tags:
        if not isinstance(tag, str):
            unwrapped_tags.append(tag)
            continue

        cleaned_tag = tag.strip()
        if len(cleaned_tag) >= 2 and cleaned_tag.startswith('#') and cleaned_tag.endswith('#'):
            cleaned_tag = cleaned_tag[1:-1]

        cleaned_tag = cleaned_tag.strip()
        if cleaned_tag:
            if scope and cleaned_tag != tag.strip():
                _log_tag_changed(scope, tag, cleaned_tag, "hash guard markers stripped")
            unwrapped_tags.append(cleaned_tag)
        elif scope:
            _log_tag_removed(scope, tag, "empty after hash guard markers were stripped")

    return unwrapped_tags

def _json_lookup_case_insensitive(data, *keys):
    if not isinstance(data, dict):
        return None

    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = lowered.get(str(key).lower())
        if value is not None:
            return value

    return None

def _coerce_to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def _clean_string_list(values):
    cleaned_values = []
    for value in _coerce_to_list(values):
        cleaned = str(value).strip()
        if cleaned:
            cleaned_values.append(cleaned)
    return cleaned_values

def _load_user_substitution_files() -> dict[str, list[dict]]:
    substitutions_by_target = {}
    substitutions_dir = Path(SUBSTITUTIONS_DIR)

    if not substitutions_dir.exists():
        return substitutions_by_target

    for json_path in substitutions_dir.glob("*.json"):
        try:
            with json_path.open("r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
        except Exception:
            continue

        files_to_parse = payload if isinstance(payload, list) else [payload]
        for file_payload in files_to_parse:
            if not isinstance(file_payload, dict):
                continue

            raw_targets = _json_lookup_case_insensitive(file_payload, "target_tag", "target_tags")
            target_tags = _clean_string_list(raw_targets)

            raw_substitutions = _json_lookup_case_insensitive(file_payload, "substitutions", "tag_substitutions")
            if not isinstance(raw_substitutions, list):
                continue

            if not target_tags:
                continue

            for substitution in raw_substitutions:
                if not isinstance(substitution, dict):
                    continue

                raw_triggers = _json_lookup_case_insensitive(substitution, "trigger", "triggers")
                triggers = _clean_string_list(raw_triggers)
                if not triggers:
                    continue

                raw_substitute = _json_lookup_case_insensitive(substitution, "substitute", "inject")
                substitutes = _clean_string_list(raw_substitute)
                substitute_value = substitutes[0] if substitutes else ""
                if not substitute_value:
                    continue

                normalized_triggers = {_normalize_association_tag(trigger) for trigger in triggers if _normalize_association_tag(trigger)}
                if not normalized_triggers:
                    continue

                rule_payload = {
                    "triggers": normalized_triggers,
                    "substitute": substitute_value,
                }

                for target_tag in target_tags:
                    normalized_target = _normalize_association_tag(target_tag)
                    if not normalized_target:
                        continue

                    if normalized_target not in substitutions_by_target:
                        substitutions_by_target[normalized_target] = []
                    substitutions_by_target[normalized_target].append(rule_payload)

    return substitutions_by_target

def _resolve_character_slot_substitution(slot_index: int, strength, target_tag: str, state, substitutions_by_target: dict[str, list[dict]]) -> str:
    default_output = _format_substitution_value(strength, target_tag)
    if slot_index <= 0:
        return default_output

    slot_key = f"character_{slot_index}"
    character_state = state.get(slot_key)
    if not isinstance(character_state, dict):
        return default_output

    character_labels = _clean_string_list(character_state.get('character_labels') or [])
    normalized_character_labels = {_normalize_association_tag(_strip_weighted_prompt_tag(tag)) for tag in character_labels}
    normalized_character_labels = {tag for tag in normalized_character_labels if tag}

    if not normalized_character_labels:
        return default_output

    normalized_target = _normalize_association_tag(target_tag)
    if not normalized_target:
        return default_output

    candidate_rules = substitutions_by_target.get(normalized_target, [])
    for rule in candidate_rules:
        triggers = rule.get("triggers") or set()
        if normalized_character_labels.intersection(triggers):
            substitute_value = rule.get("substitute")
            return _format_substitution_value(strength, substitute_value)

    return default_output

def _resolve_inline_slot_substitution(slot_token: str, trigger_tag: str, inject_value: str, state) -> str:
    cleaned_slot = str(slot_token or "").strip().lower()
    slot_match = re.fullmatch(r'c(?P<slot>\d+)', cleaned_slot)
    if not slot_match:
        return ""

    slot_index = int(slot_match.group('slot'))
    if slot_index <= 0:
        return ""

    slot_key = f"character_{slot_index}"
    character_state = state.get(slot_key)
    if not isinstance(character_state, dict):
        return ""

    normalized_trigger = _normalize_association_tag(trigger_tag)
    cleaned_inject = str(inject_value or "").strip()
    if not normalized_trigger or not cleaned_inject:
        return ""

    character_labels = _clean_string_list(character_state.get('character_labels') or [])
    normalized_character_labels = {
        _normalize_association_tag(_strip_weighted_prompt_tag(tag))
        for tag in character_labels
    }
    normalized_character_labels = {tag for tag in normalized_character_labels if tag}

    if normalized_trigger in normalized_character_labels:
        return cleaned_inject

    return ""

def _load_character_data_by_name(character_name: str):
    if not character_name or character_name == 'None':
        return None

    character_path = Path(CHARACTERS_DIR) / f"{character_name}.json"
    if not character_path.exists():
        return None

    try:
        with character_path.open("r", encoding="utf-8-sig") as file_handle:
            loaded = json.load(file_handle)
    except Exception:
        return None

    if isinstance(loaded, list):
        if loaded and isinstance(loaded[0], dict):
            return loaded[0]
        return None

    if isinstance(loaded, dict):
        return loaded

    return None

def _normalize_chance_groups(raw_chance_groups):
    # Normalize named groups containing weighted, complete prompt-entry alternatives.
    if not raw_chance_groups:
        return []

    if isinstance(raw_chance_groups, list) and raw_chance_groups and all(isinstance(entry, dict) for entry in raw_chance_groups):
        if all('alternatives' not in entry for entry in raw_chance_groups):
            raw_chance_groups = [raw_chance_groups]

    normalized_groups = []
    if isinstance(raw_chance_groups, list):
        for group_index, group in enumerate(raw_chance_groups, 1):
            group_name = f"Chance {group_index}"
            active = True
            if isinstance(group, dict) and 'alternatives' in group:
                group_name = str(group.get('name') or group_name).strip()
                active = is_active(group)
                group = group.get('alternatives')
            if isinstance(group, list):
                alternatives = []
                for alternative in group:
                    if isinstance(alternative, dict):
                        if 'tags' in alternative:
                            raw_entries = alternative.get('tags')
                            chance_value = alternative.get('chance', 1.0)
                        else:
                            raw_entries = [alternative]
                            chance_value = alternative.get('chance', 1.0)
                    elif isinstance(alternative, list):
                        raw_entries = alternative
                        chance_value = 1.0
                    else:
                        continue
                    try:
                        chance_value = float(chance_value)
                    except (TypeError, ValueError):
                        continue
                    if chance_value <= 0 or not isinstance(raw_entries, list):
                        continue
                    normalized_entries = []
                    for entry in raw_entries:
                        if not isinstance(entry, dict):
                            continue
                        tag_value = str(entry.get('tag', '')).strip()
                        if not tag_value:
                            continue
                        try:
                            strength_value = float(entry.get('strength', 1.0))
                        except (TypeError, ValueError):
                            continue
                        normalized_entries.append({'tag': tag_value, 'strength': strength_value})
                    if normalized_entries:
                        alternatives.append({'chance': chance_value, 'tags': normalized_entries})
                if alternatives:
                    normalized_groups.append({'name': group_name, 'active': active, 'alternatives': alternatives})

    return normalized_groups

def _extract_character_chance_groups(state, key):
    character_state = state.get(key, {}) if isinstance(state, dict) else {}

    raw_groups = character_state.get('chance_tag')
    normalized = _normalize_chance_groups(raw_groups)
    if normalized or (isinstance(raw_groups, list) and raw_groups):
        return normalized

    character_name = character_state.get('character')
    loaded_character = _load_character_data_by_name(character_name)
    if not isinstance(loaded_character, dict):
        return []

    raw_groups = loaded_character.get('chance_tag')
    return _normalize_chance_groups(raw_groups)

def _roll_single_chance_group(group):
    if isinstance(group, dict) and not is_active(group):
        return []
    alternatives = group.get('alternatives', []) if isinstance(group, dict) else group
    if not alternatives:
        return None

    weighted_pool = []
    for alternative in alternatives:
        weighted_pool.extend([alternative] * int(alternative['chance']))
    if not weighted_pool:
        return None

    selected_alternative = random.choice(weighted_pool)
    selected_entries = selected_alternative['tags']
    if not selected_entries or all(entry['tag'].lower() == 'none' for entry in selected_entries):
        return []

    return [
        tag_value if entry['strength'] == 1.0 else f"{entry['strength']}::{tag_value}::"
        for entry in selected_entries
        if (tag_value := entry['tag'].strip()) and tag_value.lower() != 'none'
    ]

def _roll_character_chance_tags(state, key, scope=None):
    chance_groups = _extract_character_chance_groups(state, key)
    if not chance_groups:
        return []

    selected_tags = []
    for group in chance_groups:
        if not is_active(group):
            continue
        selected = _roll_single_chance_group(group)
        group_name = group.get('name', 'Chance') if isinstance(group, dict) else 'Chance'
        if selected:
            for tag in selected:
                _log_tag_added(scope, tag, f"chance group '{group_name}' rolled this alternative")
            selected_tags.extend(selected)
        else:
            _log_prompt(scope, f"chance group '{group_name}' rolled no tags")

    return selected_tags

def _load_user_tag_association_files() -> list[dict]:
    loaded_associations = []
    associations_dir = Path(ASSOCIATIONS_DIR)

    if not associations_dir.exists():
        return loaded_associations

    for json_path in associations_dir.glob("*.json"):
        try:
            with json_path.open("r", encoding="utf-8-sig") as file_handle:
                payload = json.load(file_handle)
        except Exception:
            continue

        files_to_parse = payload if isinstance(payload, list) else [payload]
        for file_payload in files_to_parse:
            if not isinstance(file_payload, dict):
                continue

            target_labels = file_payload.get("target_label") or []
            if not isinstance(target_labels, list):
                target_labels = [target_labels]

            normalized_targets = []
            for target_label in target_labels:
                normalized = _normalize_association_tag(target_label)
                if normalized:
                    normalized_targets.append(normalized)

            file_associations = file_payload.get("tag_associations") or []
            if not isinstance(file_associations, list) or not file_associations:
                continue

            loaded_associations.append({
                "target_labels": normalized_targets,
                "tag_associations": file_associations,
            })

    return loaded_associations

def _get_user_associations_for_character_labels(character_labels: list[str], forced_target_label: str | None = None) -> list[dict]:
    matched_associations = []
    for association_file in _load_user_tag_association_files():
        target_labels = association_file.get("target_labels", [])
        if not tag_scope_matches(target_labels, character_labels, forced_target_label):
            continue

        file_associations = association_file.get("tag_associations") or []
        matched_associations.extend(file_associations)

    return matched_associations

def _effective_character_labels(character_labels, forced_target_label=None) -> list[str]:
    return effective_labels(character_labels, forced_target_label)


def _load_universal_label_associations() -> list[dict]:
    return load_label_associations(LABEL_ASSOCIATIONS_FILE)


def _matched_label_associations(character_labels: list[str]) -> list[dict]:
    matched = []
    for index, association in enumerate(_load_universal_label_associations(), start=1):
        if not is_active(association):
            continue
        if not label_association_matches(association, character_labels, _normalize_association_tag):
            continue
        name = association.get('name') or f"#{index}"
        groups = association.get('label_triggers') or []
        group_text = " and ".join("/".join(group) for group in groups)
        if association.get('match') == LABEL_MATCH_NONE:
            reason = f"label association '{name}' triggered because the character has none of the labels {group_text}"
        else:
            reason = f"label association '{name}' triggered by character labels {group_text}"
        matched.append({
            '_label_activation_reason': reason,
            'inject': association.get('inject', []),
            'blacklist': association.get('blacklist', []),
            'remove_blacklist': association.get('remove_blacklist', False),
            'remove': association.get('remove', []),
            'negative_injection': association.get('negative_injection', False),
        })
    return matched


def handle_assocations(caption, state, key, include_global_associations=True, shared_prompt=None, apply_injections=True, negative_sink=None, scope=None, evaluate_absent_triggers=True):
    if _state_bool(state[key].get('character_disable_associations', False)):
        _log_prompt(scope, "tag and label associations skipped (Disable Associations is enabled)")
        return caption[:]

    def _strip_weighted_tag(tag):
        if not isinstance(tag, str):
            return ''
        cleaned = tag.strip()
        parts = cleaned.split('::')
        if len(parts) == 3 and parts[0] and parts[2] == '':
            return parts[1].strip()
        return cleaned

    def _normalized_tag(tag):
        return _normalize_association_tag(_strip_weighted_tag(tag))

    def _caption_contains_tag(caption_list, tag):
        normalized_target = _normalized_tag(tag)
        if not normalized_target:
            return False
        return any(_normalized_tag(entry) == normalized_target for entry in caption_list)

    def _remove_tag_from_caption(caption_list, tag):
        normalized_target = _normalized_tag(tag)
        if not normalized_target:
            return caption_list[:]
        return [entry for entry in caption_list if _normalized_tag(entry) != normalized_target]

    def _global_prompt_context_tags(prompt_state):
        if not isinstance(prompt_state, dict):
            return []

        context_tags = []
        raw_prompt = prompt_state.get('global_positive_prompt')
        if raw_prompt:
            context_tags.extend(_split_prompt_entries(raw_prompt))

        return [str(tag).strip() for tag in context_tags if str(tag).strip()]

    caption = [str(tag).strip() for tag in caption]

    # Use list to preserve order
    final_caption = caption[:]
    trigger_context = final_caption[:]
    if include_global_associations:
        trigger_context.extend(_global_prompt_context_tags(state.get('global_prompt', {})))
    
    associations_to_add = []
    associations_to_remove = []
    removal_reasons = {}

    associations_positive = state[key].get('character_tag_associations') or []

    character_labels = state[key].get('character_labels') or []
    if not isinstance(character_labels, list):
        character_labels = [character_labels]

    forced_target_label = None
    if state[key].get('boys_to_girls'):
        forced_target_label = 'female'
    elif state[key].get('girls_to_boys'):
        forced_target_label = 'male'

    # Universal (user_config/associations/*.json) associations always apply,
    # independent of the global tag association toggle.
    user_associations = _get_user_associations_for_character_labels(character_labels, forced_target_label)
    if user_associations:
        associations_positive = list(associations_positive) + user_associations

    # Label associations need the character's own labels, so skip the V4+ shared base pass.
    if evaluate_absent_triggers:
        label_associations = _matched_label_associations(
            _effective_character_labels(character_labels, forced_target_label)
        )
        if label_associations:
            associations_positive = list(associations_positive) + label_associations

    for association in associations_positive:
        if not is_active(association):
            continue

        label_activation_reason = association.get('_label_activation_reason')
        trigger_absent = _state_bool(association.get('trigger_absent', False))
        # The V4+ base pass has no character traits; defer absence checks.
        if trigger_absent and not evaluate_absent_triggers:
            continue

        blacklist = association.get('blacklist')
        matched_blacklist_tags = [
            blacklist_tag
            for blacklist_tag in blacklist or []
            if _caption_contains_tag(trigger_context, blacklist_tag)
        ]
        if matched_blacklist_tags:
            remove_blacklist = association.get('remove_blacklist') or []
            for blacklisted_by in matched_blacklist_tags:
                if any(_caption_contains_tag([blacklisted_by], tag) for tag in remove_blacklist):
                    associations_to_remove.append(blacklisted_by)
                    removal_reasons.setdefault(
                        blacklisted_by,
                        "association skipped because its blacklist tag was present",
                    )
            _log_prompt(
                scope,
                f"association skipped: blacklist tag '{_format_logged_value(matched_blacklist_tags[0])}' is present",
            )
            continue

        trigger_groups = []
        raw_triggers = association.get('trigger', []) if label_activation_reason is None else []

        if isinstance(raw_triggers, list):
            for raw_group in raw_triggers:
                if not isinstance(raw_group, list):
                    continue
                trigger_group = []
                for raw_trigger in raw_group:
                    trigger = str(raw_trigger).strip()
                    if trigger:
                        trigger_group.append(trigger)
                if trigger_group:
                    trigger_groups.append(trigger_group)

        if label_activation_reason is not None:
            activation_reason = label_activation_reason
        elif not trigger_groups:
            continue
        else:
            matched_triggers = []
            for trigger_group in trigger_groups:
                matched_trigger = next(
                    (
                        trigger_tag
                        for trigger_tag in trigger_group
                        if _caption_contains_tag(trigger_context, trigger_tag)
                    ),
                    None,
                )
                if matched_trigger is None:
                    break
                matched_triggers.append(matched_trigger)
            triggers_match = len(matched_triggers) == len(trigger_groups)
            if triggers_match == trigger_absent:
                continue

            if trigger_absent:
                activation_reason = "association triggered because its trigger groups are not all satisfied"
            else:
                matched_trigger_text = "' and '".join(matched_triggers)
                activation_reason = f"association triggered by '{matched_trigger_text}'"

        cleaned_inject_tags = []
        raw_inject_tags = association.get('inject', [])

        for raw_tag in raw_inject_tags:
            tag = _format_association_injection(raw_tag)
            if tag:
                cleaned_inject_tags.append(tag)

        if association.get('negative_injection'):
            if isinstance(negative_sink, list):
                for inject_tag in cleaned_inject_tags:
                    if inject_tag not in negative_sink:
                        negative_sink.append(inject_tag)
                        _log_tag_added(
                            scope,
                            inject_tag,
                            f"{activation_reason} queued it for the negative prompt",
                        )
        else:
            for inject_tag in cleaned_inject_tags:
                if not _caption_contains_tag(final_caption, inject_tag) and inject_tag not in associations_to_add:
                    associations_to_add.append(inject_tag)
                    if apply_injections:
                        _log_tag_added(scope, inject_tag, activation_reason)

        cleaned_remove_tags = []
        raw_remove_tags = association.get('remove', [])
        for raw_tag in raw_remove_tags:
            tag = str(raw_tag).strip()
            if tag:
                cleaned_remove_tags.append(tag)

        for remove_tag in cleaned_remove_tags:
            associations_to_remove.append(remove_tag)
            removal_reasons.setdefault(
                remove_tag,
                f"{activation_reason} removes it",
            )

        remove_triggers = association.get('remove_triggers')
        if remove_triggers is None:
            remove_triggers = association.get('remove_trigger')
        if remove_triggers and not trigger_absent and label_activation_reason is None:
            for trigger_group in trigger_groups:
                for trigger_tag in trigger_group:
                    if trigger_tag not in associations_to_remove:
                        associations_to_remove.append(trigger_tag)
                        removal_reasons.setdefault(
                            trigger_tag,
                            f"{activation_reason} removes its own trigger tags",
                        )

    # Remove tags
    for remove_tag in associations_to_remove:
        reason = removal_reasons.get(remove_tag, "association removal")
        updated_caption = _remove_tag_from_caption(final_caption, remove_tag)
        if scope and len(updated_caption) != len(final_caption):
            for entry in final_caption:
                if entry not in updated_caption:
                    _log_tag_removed(scope, entry, reason)
        final_caption = updated_caption
        if isinstance(shared_prompt, list):
            updated_shared = _remove_tag_from_caption(shared_prompt, remove_tag)
            if scope and len(updated_shared) != len(shared_prompt):
                for entry in shared_prompt:
                    if entry not in updated_shared:
                        _log_tag_removed(scope, entry, f"{reason} (from the shared global prompt)")
            shared_prompt[:] = updated_shared

    if apply_injections:
        for add_tag in associations_to_add:
            final_caption.append(add_tag)

    return final_caption

def _swap_gender_tag(tag, boys_to_girls, girls_to_boys):
    if not isinstance(tag, str):
        return tag

    cleaned_tag = tag.strip()
    if not cleaned_tag:
        return cleaned_tag

    weighted_match = re.fullmatch(r'(?P<strength>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*::\s*(?P<tag>.*?)\s*::\s*', cleaned_tag)
    if weighted_match:
        strength = weighted_match.group('strength')
        inner_tag = weighted_match.group('tag').strip()
        if boys_to_girls and inner_tag.lower() == 'boy':
            return f"{strength}::girl::"
        if boys_to_girls and inner_tag.lower() == 'shota':
            return f"{strength}::loli::"
        if boys_to_girls and inner_tag.lower() == 'male':
            return f"{strength}::female::"
        if girls_to_boys and inner_tag.lower() == 'girl':
            return f"{strength}::boy::"
        if girls_to_boys and inner_tag.lower() == 'loli':
            return f"{strength}::shota::"
        if girls_to_boys and inner_tag.lower() == 'female':
            return f"{strength}::male::"
        
        return cleaned_tag

    if boys_to_girls and cleaned_tag.lower() == 'boy':
        return 'girl'
    if boys_to_girls and cleaned_tag.lower() == 'shota':
        return 'loli'
    if boys_to_girls and cleaned_tag.lower() == 'male':
        return 'female'
    if girls_to_boys and cleaned_tag.lower() == 'girl':
        return 'boy'
    if girls_to_boys and cleaned_tag.lower() == 'loli':
        return 'shota'
    if girls_to_boys and cleaned_tag.lower() == 'female':
        return 'male'
    return cleaned_tag


def handle_gender_inversion(caption, state, character_state=None, scope=None):
    if character_state is None:
        character_state = state.get('global_prompt', {})

    boys_to_girls = character_state.get('boys_to_girls', False)
    girls_to_boys = character_state.get('girls_to_boys', False)

    if not boys_to_girls and not girls_to_boys:
        return caption

    direction = "boys to girls" if boys_to_girls else "girls to boys"
    swapped_caption = []
    for tag in caption:
        swapped = _swap_gender_tag(tag, boys_to_girls, girls_to_boys)
        if scope and str(swapped) != str(tag).strip():
            _log_tag_changed(scope, tag, swapped, f"gender inversion ({direction}) is enabled")
        swapped_caption.append(swapped)

    return swapped_caption

def handle_character_name(caption, state, scope=None):
    new_caption = []
    for tag in caption:
        if tag.count("&") == 2:
            parts = tag.split("&")
            char_num = parts[1].lower()
            if char_num in ['c1', 'c2', 'c3', 'c4', 'c5']:
                index = int(char_num[1])
                character_name = state[f'character_{index}']['character']
                new_tag = parts[0] + character_name + parts[2]
                _log_tag_changed(scope, tag, new_tag, f"&{char_num}& replaced with character {index}'s name")
                new_caption.append(new_tag)
            else:
                new_caption.append(tag)
        else:
            new_caption.append(tag)
    return new_caption

def handle_substitutions(caption, state, character_state=None, scope=None):
    if caption is None:
        return []

    slot_pattern = re.compile(r'\?c(?P<slot>\d+)\?(?P<payload>.*?)\?', re.IGNORECASE)
    inline_slot_pattern = re.compile(r'\$(?P<slot>c\d+)\$(?P<trigger>[^$]*)\$(?P<inject>[^$]*)\$', re.IGNORECASE)
    substitutions_by_target = _load_user_substitution_files()

    resolved_caption = []
    for tag in caption:
        if not isinstance(tag, str):
            resolved_caption.append(tag)
            continue

        def _replace_slot_call(match):
            slot_index = int(match.group('slot'))
            payload = match.group('payload')
            strength, target_tag = _extract_slot_substitution_payload(payload)
            if not target_tag:
                return ""

            return _resolve_character_slot_substitution(
                slot_index=slot_index,
                strength=strength,
                target_tag=target_tag,
                state=state,
                substitutions_by_target=substitutions_by_target,
            )

        def _replace_inline_slot_call(match):
            return _resolve_inline_slot_substitution(
                slot_token=match.group('slot'),
                trigger_tag=match.group('trigger'),
                inject_value=match.group('inject'),
                state=state,
            )

        replaced_tag = slot_pattern.sub(_replace_slot_call, tag)
        replaced_tag = inline_slot_pattern.sub(_replace_inline_slot_call, replaced_tag)
        cleaned_tag = replaced_tag.strip()
        if cleaned_tag:
            if scope and cleaned_tag != tag.strip():
                _log_tag_changed(scope, tag, cleaned_tag, "substitution resolved")
            resolved_caption.append(cleaned_tag)
        elif scope:
            _log_tag_removed(scope, tag, "substitution resolved to nothing")

    return resolved_caption

def text_to_bottom(prompt, scope=None):
    text_tags = []
    kept_tags = []
    seen_text_tags = set()

    for raw_tag in prompt:
        tag = str(raw_tag).strip()
        normalized = tag.lower()
        is_prefixed_text_tag = normalized.startswith("text:")
        if is_prefixed_text_tag:
            prefix, separator, text_value = tag.partition(':')
            stripped_value = text_value.strip()
            if len(stripped_value) >= 2 and stripped_value.startswith('"') and stripped_value.endswith('"'):
                tag = f"{prefix}{separator} {stripped_value[1:-1].strip()}"
                normalized = tag.lower()
        is_text_tag = is_prefixed_text_tag or (normalized.startswith('"') and normalized.endswith('"'))

        if is_text_tag:
            normalized_key = normalized
            if normalized_key not in seen_text_tags:
                text_tags.append(tag)
                seen_text_tags.add(normalized_key)
            else:
                _log_tag_removed(scope, tag, "duplicate text tag")
        else:
            kept_tags.append(tag)

    if scope and text_tags:
        _log_prompt(scope, f"moved text tags to the end: {_format_logged_tags(text_tags)}")

    return kept_tags + text_tags
            
