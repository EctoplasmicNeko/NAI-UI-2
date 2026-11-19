# windows/import_on_drop.py
from PySide6.QtWidgets import QDialog, QGridLayout, QCheckBox, QPushButton, QLabel, QFrame
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt
from signaling.import_signal import import_signal
from data.datahub import get_character
from windows.character_editor import parse_prompt_text


def _saved_quick_weight_tags(raw_values):
    tags = set()
    for raw_value in raw_values or []:
        for entry in parse_prompt_text(str(raw_value)):
            tag = str(entry.get("tag", "")).strip().lower()
            if tag:
                tags.add(tag)
    return tags


def _character_quick_weight_tags(character_name):
    character = get_character(character_name) or {}
    positive_tags = set()
    negative_tags = set()
    for entry in character.get("quick_weights") or []:
        if not isinstance(entry, dict):
            continue
        tag = str(entry.get("tag", "")).strip().lower()
        if not tag:
            continue
        if entry.get("negative"):
            negative_tags.add(tag)
        else:
            positive_tags.add(tag)
    return positive_tags, negative_tags


def quick_weights_out_of_sync(metadata):
    """True if any character's saved quick weight tags no longer match that character's current quick weights."""
    characters = (metadata or {}).get("characters") or {}
    for slot_data in characters.values():
        if not isinstance(slot_data, dict):
            continue
        character_name = slot_data.get("character")
        if not character_name or character_name == "None":
            continue

        saved_positive = _saved_quick_weight_tags(slot_data.get("character_positive_quick_weights"))
        saved_negative = _saved_quick_weight_tags(slot_data.get("character_negative_quick_weights"))
        if not saved_positive and not saved_negative:
            continue

        current_positive, current_negative = _character_quick_weight_tags(character_name)
        if not saved_positive.issubset(current_positive) or not saved_negative.issubset(current_negative):
            return True

    return False


def has_saved_quick_weight_data(metadata):
    for slot_data in ((metadata or {}).get("characters") or {}).values():
        if isinstance(slot_data, dict) and (
            slot_data.get("character_positive_quick_weights")
            or slot_data.get("character_negative_quick_weights")
        ):
            return True
    return False


def derive_legacy_quick_weights(character_name, caption, negative=False):
    """Extract configured quick-weight tags and their generated strengths from a caption."""
    character = get_character(character_name) or {}
    configured_tags = {
        str(entry.get("tag", "")).strip().casefold()
        for entry in character.get("quick_weights") or []
        if isinstance(entry, dict) and bool(entry.get("negative")) == negative
    }
    configured_tags.discard("")
    if not configured_tags:
        return []

    weights = []
    seen = set()
    for entry in parse_prompt_text(caption or ""):
        tag = str(entry.get("tag", "")).strip()
        normalized_tag = tag.casefold()
        if normalized_tag not in configured_tags or normalized_tag in seen:
            continue
        seen.add(normalized_tag)
        weights.append((tag, float(entry.get("strength", 1.0))))
    return weights


def quick_weight_prompt_entries(raw_values):
    weights = []
    for raw_value in raw_values or []:
        for entry in parse_prompt_text(str(raw_value)):
            tag = str(entry.get("tag", "")).strip()
            if tag:
                weights.append((tag, float(entry.get("strength", 1.0))))
    return weights


def prepend_missing_quick_weights(prompt, weights):
    prompt_weights = {
        str(entry.get("tag", "")).strip().casefold(): float(entry.get("strength", 1.0))
        for entry in parse_prompt_text(prompt or "")
    }
    prefix = [
        f"{strength:.1f}::{tag}::"
        for tag, strength in weights
        if prompt_weights.get(tag.casefold()) != strength
    ]
    if not prefix:
        return prompt or ""
    return ", ".join([*prefix, *([prompt.strip()] if prompt and prompt.strip() else [])])


def prepare_saved_quick_weights_for_import(
    positive_prompt,
    negative_prompt,
    positive_weights,
    negative_weights,
    restore_quick_weights,
):
    if restore_quick_weights:
        return positive_prompt, negative_prompt, positive_weights, negative_weights
    return (
        prepend_missing_quick_weights(
            positive_prompt,
            quick_weight_prompt_entries(positive_weights),
        ),
        prepend_missing_quick_weights(
            negative_prompt,
            quick_weight_prompt_entries(negative_weights),
        ),
        [],
        [],
    )


class ImportDialog(QDialog):
    def __init__(self, parent, path, dict_type, metadata, import_settings_state, import_prompt_state, import_seed_state, import_characters_state, has_metadata, reference_width=None, reference_height=None):
        super().__init__(parent)
        self.path = path
        self.dict_type = dict_type
        self.metadata = metadata
        self.import_settings_state = import_settings_state
        self.import_prompt_state = import_prompt_state
        self.import_seed_state = import_seed_state
        self.import_characters_state = import_characters_state
        self.reference_width = reference_width
        self.reference_height = reference_height

        self.setWindowTitle("Import")
        self.build_import_window()
        self.set_allowed_options(has_metadata)
        self.update_quick_weight_warning()


    def build_import_window(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.prompt_checkbox = QCheckBox("Import Prompt", self)
        self.prompt_checkbox.setChecked(self.import_prompt_state)
        self.grid.addWidget(self.prompt_checkbox, 0, 0)

        self.import_characters_checkbox = QCheckBox("Import Characters", self)
        self.import_characters_checkbox.setChecked(self.import_characters_state)
        self.grid.addWidget(self.import_characters_checkbox, 1, 0)

        self.import_settings_checkbox = QCheckBox("Import Settings", self)
        self.import_settings_checkbox.setChecked(self.import_settings_state)
        self.grid.addWidget(self.import_settings_checkbox, 2, 0)

        self.import_seed_checkbox = QCheckBox("Import Seed", self)
        self.import_seed_checkbox.setChecked(self.import_seed_state)
        self.grid.addWidget(self.import_seed_checkbox, 3, 0)

        self.quick_weights_option_frame = QFrame(self)
        self.quick_weights_option_layout = QGridLayout(self.quick_weights_option_frame)
        self.quick_weights_option_layout.setContentsMargins(3, 3, 3, 3)
        self.quick_weights_option_layout.setSpacing(0)
        self.quick_weights_to_prompt_checkbox = QCheckBox("Restore Quick Weights", self.quick_weights_option_frame)
        self.quick_weights_to_prompt_checkbox.setChecked(True)
        self.quick_weights_to_prompt_checkbox.setToolTip(
            "Restore saved values to character quick-weight controls. Uncheck to add the weighted tags to prompts."
        )
        self.quick_weights_option_layout.addWidget(self.quick_weights_to_prompt_checkbox, 0, 0)
        self.no_quick_weight_data_label = QLabel("No Quick Weight Data", self.quick_weights_option_frame)
        self.no_quick_weight_data_label.setAlignment(Qt.AlignCenter)
        self.no_quick_weight_data_label.setStyleSheet(
            "color: #e0a030; background-color: transparent;"
        )
        self.quick_weights_option_layout.addWidget(self.no_quick_weight_data_label, 0, 0)
        self.grid.addWidget(self.quick_weights_option_frame, 4, 0)

        self.disable_associations_checkbox = QCheckBox("Disable Associations for All Characters", self)
        self.disable_associations_checkbox.setToolTip(
            "Enable Disable Associations for every imported character, skipping tag and label associations."
        )
        self.disable_associations_checkbox.setEnabled(self.import_characters_checkbox.isChecked())
        self.import_characters_checkbox.toggled.connect(self.disable_associations_checkbox.setEnabled)
        self.grid.addWidget(self.disable_associations_checkbox, 5, 0)

        self.import_button = QPushButton("Import", self)
        self.import_button.clicked.connect(self.on_import_clicked)
        self.grid.addWidget(self.import_button, 6, 0)

        self.import_image_button = QPushButton("Import Image Assets", self)
        self.import_image_button.clicked.connect(self.on_import_image_clicked)
        self.grid.addWidget(self.import_image_button, 7, 0)

        self.import_reference_button = QPushButton("Import Reference", self)
        self.import_reference_button.clicked.connect(self.on_import_reference_clicked)
        self.grid.addWidget(self.import_reference_button, 8, 0)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.close)
        self.grid.addWidget(self.cancel_button, 9, 0)

        self.quick_weight_warning_label = QLabel("", self)
        self.quick_weight_warning_label.setWordWrap(True)
        self.quick_weight_warning_label.setStyleSheet("color: #e0a030;")
        self.quick_weight_warning_label.hide()
        self.grid.addWidget(self.quick_weight_warning_label, 10, 0)
        self.quick_weights_available = (
            self.dict_type == "custom" and has_saved_quick_weight_data(self.metadata)
        )
        self.quick_weights_option_frame.setVisible(self.dict_type == "custom")
        self.quick_weights_to_prompt_checkbox.setVisible(self.quick_weights_available)
        self.no_quick_weight_data_label.setVisible(
            self.dict_type == "custom" and not self.quick_weights_available
        )

    def update_quick_weight_warning(self):
        warning = ""
        if self.dict_type == "custom" and self.metadata:
            if self.quick_weights_available and quick_weights_out_of_sync(self.metadata):
                warning = (
                    "Quick weights have changed since this image was generated; unmatched saved weights "
                    "will be kept in prompt text."
                )

        self.quick_weight_warning_label.setText(warning)
        self.quick_weight_warning_label.setVisible(bool(warning))

    def on_import_clicked(self):
        import_signal.import_signal.emit(
            self.dict_type,
            self.metadata,
            self.import_settings_checkbox.isChecked(),
            self.prompt_checkbox.isChecked(),
            self.import_seed_checkbox.isChecked(),
            self.import_characters_checkbox.isChecked(),
            self.quick_weights_to_prompt_checkbox.isChecked(),
            self.import_characters_checkbox.isChecked() and self.disable_associations_checkbox.isChecked(),
        )
        self.close()

    def set_allowed_options(self, has_metadata: bool):
        if not has_metadata:
            self.prompt_checkbox.setEnabled(False)
            self.import_characters_checkbox.setEnabled(False)
            self.disable_associations_checkbox.setEnabled(False)
            self.import_settings_checkbox.setEnabled(False)
            self.import_seed_checkbox.setEnabled(False)
            self.import_button.setEnabled(False)

    def on_import_image_clicked(self, path):
        image = QImage(self.path)
        width = image.width()
        height = image.height()
        import_signal.import_image_signal.emit(self.path, width, height)
        self.close()

    def on_import_reference_clicked(self, checked=False):
        if self.reference_width is None or self.reference_height is None:
            return
        import_signal.import_reference_signal.emit(
            self.path,
            self.reference_width,
            self.reference_height,
        )
        self.close()
