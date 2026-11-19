# data/paths.py
from pathlib import Path
import sys

def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]

PROJECT_ROOT = get_project_root()

DATA_DIR       = PROJECT_ROOT / "data"
CONFIG_DIR     = DATA_DIR / "config"
IMAGES_DIR     = PROJECT_ROOT / "images"
THEMES_DIR     = PROJECT_ROOT / "themes"
OUTPUT_DIR = PROJECT_ROOT / "output"

USER_DIR      = PROJECT_ROOT / 'user_config'
REFERENCE_DIR = USER_DIR / 'character_reference'
CHARACTERS_DIR = USER_DIR / "characters"
CHARACTER_LABELS_FILE = USER_DIR / "character_labels.json"
LABEL_ASSOCIATIONS_FILE = USER_DIR / "label_associations.json"
CHARACTER_FLUFF_FIELDS_FILE = USER_DIR / "character_fluff_fields.json"
CHARACTER_MONTHS_FILE = USER_DIR / "character_months.json"
PORTRAITS_DIR  = USER_DIR / "character_portraits"
ALT_PORTRAITS_DIR = USER_DIR / "alt character portraits"
ASSOCIATIONS_DIR = USER_DIR / "associations"
SUBSTITUTIONS_DIR = USER_DIR / "substitutions"
PRESETS_DIR    = USER_DIR / "preset"
SAVE_DIR = USER_DIR / "save"
ENCODES_DIR    = USER_DIR / "vibe_encodes"
VIBES_DIR     = USER_DIR / "vibes"
SAVED_PROMPTS_DIR = USER_DIR / "saved_prompts"
ARTISTS_DIR   = USER_DIR / "artists"
WILDCARDS_DIR = USER_DIR / "wildcards"
CURATION_DIR = USER_DIR / "curation"
UNIVERSAL_QUICK_WEIGHTS_FILE = PROJECT_ROOT / "u_quickweights.json"

