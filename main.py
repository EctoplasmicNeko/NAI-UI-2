# main.py
from ui.ui_main import run_app
from data import datahub
from data.mutators import migrate_file
from signaling.debug_signal import debug_error
from data.paths import (
    PORTRAITS_DIR,
    ALT_PORTRAITS_DIR,
    OUTPUT_DIR,
    CHARACTERS_DIR,
    REFERENCE_DIR,
    ENCODES_DIR,
    VIBES_DIR,
    SAVED_PROMPTS_DIR,
    ARTISTS_DIR,
    CURATION_DIR,
    ASSOCIATIONS_DIR,
    LABEL_ASSOCIATIONS_FILE,
)
import warnings


def migrate_global_mutators() -> None:
    paths = [(path, ("tag_associations",)) for path in ASSOCIATIONS_DIR.glob("*.json")]
    if LABEL_ASSOCIATIONS_FILE.is_file():
        paths.append((LABEL_ASSOCIATIONS_FILE, ("label_associations",)))
    for path, keys in paths:
        try:
            migrate_file(path, keys)
        except (OSError, ValueError) as exception:
            message = f"Cannot migrate {path}: {exception}"
            debug_error("Mutators", message)
            warnings.warn(message, UserWarning)
# data/paths.py
def ensure_dirs() -> None:
    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    ALT_PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    ENCODES_DIR.mkdir(parents=True, exist_ok=True)
    VIBES_DIR.mkdir(parents=True, exist_ok=True)
    SAVED_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTISTS_DIR.mkdir(parents=True, exist_ok=True)
    CURATION_DIR.mkdir(parents=True, exist_ok=True)


# This check ensures we only run the window when executing directly
if __name__ == "__main__":
    ensure_dirs()
    migrate_global_mutators()
    datahub.load_all()
    datahub.load_characters()
    datahub.load_universal_quick_weights()
    datahub.sync_universal_quick_weights_from_characters()
    datahub.load_wildcards()
    run_app()
