from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from data.character_slots import CHARACTER_SLOTS_PER_ROW, MAX_CHARACTER_SLOTS
from data.datahub import get_all_characters, resolve_character_id
from data.paths import CURATION_DIR
from process.image_curation import CurationError, calculate_character_matches, calculate_content_matches, calculate_pairing_matches, get_pairing_labels, load_content_tag_groups, load_content_tags, load_curation_other_tags, load_curation_outfits, load_curation_sets, load_pairing_tags
from windows.add_character_outfit import AddCharacterOutfitDialog, delete_character_outfit
from windows.confirmation import Confirm
from windows.content_tag_editor import ContentTagEditor
from windows.error import Error


class CurationMetadataTab(QFrame):
    values_changed = Signal(dict)
    auto_calculate_all_requested = Signal(str)
    CHARACTER_SLOT_RESERVED_ROWS = 3

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(
            "QComboBox {"
            " selection-background-color: transparent;"
            " selection-color: palette(text);"
            " }"
        )
        self.current_image_path = None
        self.build_curation_metadata_tab()

    def build_curation_metadata_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(5, 5, 5, 5)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(8)
        self.character_slot_comboboxes = []
        self.character_names = []
        self.content_checkboxes = {}

        self.title_label = QLabel("Hydrus Curation", self)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.grid.addWidget(self.title_label, 0, 0)

        self.dimensions_label = QLabel("", self)
        self.dimensions_label.setAlignment(Qt.AlignCenter)
        self.grid.addWidget(self.dimensions_label, 1, 0)

        self.grid.addWidget(QLabel("Status", self), 2, 0)
        self.status_button_frame = QFrame(self)
        self.status_button_layout = QGridLayout(self.status_button_frame)
        self.status_button_layout.setContentsMargins(0, 0, 0, 0)
        self.status_button_layout.setSpacing(3)
        self.status_button_group = QButtonGroup(self)
        self.status_button_group.setExclusive(True)
        self.status_buttons = self._create_choice_buttons(
            self.status_button_layout,
            self.status_button_group,
            ["Keep", "Trash", "Uncurated"],
            columns=3,
        )
        self.status_buttons["Uncurated"].setChecked(True)
        self.grid.addWidget(self.status_button_frame, 3, 0)

        self.grid.addWidget(QLabel("Character", self), 4, 0)
        self.character_slots_frame = QFrame(self)
        self.character_slots_layout = QVBoxLayout(self.character_slots_frame)
        self.character_slots_layout.setContentsMargins(0, 0, 0, 0)
        self.character_slots_layout.setSpacing(3)
        self.character_slots_layout.setAlignment(Qt.AlignTop)
        self._reserve_character_slot_height()
        self.grid.addWidget(self.character_slots_frame, 5, 0)
        self.character_button_frame = QFrame(self)
        self.character_button_layout = QGridLayout(self.character_button_frame)
        self.character_button_layout.setContentsMargins(0, 0, 0, 0)
        self.character_button_layout.setSpacing(3)
        self.add_character_button = QPushButton("Add Character", self.character_button_frame)
        self.add_character_button.clicked.connect(self.add_character_slot)
        self.character_button_layout.addWidget(self.add_character_button, 0, 0)
        self.remove_character_button = QPushButton("Remove Character", self.character_button_frame)
        self.remove_character_button.clicked.connect(self.remove_character_slot)
        self.character_button_layout.addWidget(self.remove_character_button, 0, 1)
        self.auto_calculate_characters_button = QPushButton("Auto-Calculate Characters", self.character_button_frame)
        self.auto_calculate_characters_button.clicked.connect(self.auto_calculate_characters)
        self.character_button_layout.addWidget(self.auto_calculate_characters_button, 1, 0, 1, 2)
        self.grid.addWidget(self.character_button_frame, 6, 0)
        self.character_outfit_button_frame = QFrame(self)
        self.character_outfit_button_layout = QHBoxLayout(self.character_outfit_button_frame)
        self.character_outfit_button_layout.setContentsMargins(0, 0, 0, 0)
        self.character_outfit_button_layout.setSpacing(3)
        self.add_character_outfit_button = QPushButton("Add Character Outfit", self.character_outfit_button_frame)
        self.add_character_outfit_button.clicked.connect(self.add_character_outfit)
        self.character_outfit_button_layout.addWidget(self.add_character_outfit_button)
        self.delete_character_outfit_button = QPushButton("Delete Character Outfit", self.character_outfit_button_frame)
        self.delete_character_outfit_button.clicked.connect(self.delete_character_outfit)
        self.character_outfit_button_layout.addWidget(self.delete_character_outfit_button)
        self.grid.addWidget(self.character_outfit_button_frame, 7, 0)

        self.grid.addWidget(QLabel("Outfit", self), 8, 0)
        self.outfit_button_frame = QFrame(self)
        self.outfit_button_layout = QGridLayout(self.outfit_button_frame)
        self.outfit_button_layout.setContentsMargins(0, 0, 0, 0)
        self.outfit_button_layout.setSpacing(3)
        self.outfit_combobox = QComboBox(self.outfit_button_frame)
        self.outfit_button_layout.addWidget(self.outfit_combobox, 0, 0)
        self.grid.addWidget(self.outfit_button_frame, 9, 0)

        self.grid.addWidget(QLabel("Set", self), 10, 0)
        self.set_button_frame = QFrame(self)
        self.set_button_layout = QGridLayout(self.set_button_frame)
        self.set_button_layout.setContentsMargins(0, 0, 0, 0)
        self.set_button_layout.setSpacing(3)
        self.sets_path = CURATION_DIR / "sets.json"
        self.outfits_path = CURATION_DIR / "outfits.json"
        self.pairing_tags_path = CURATION_DIR / "pairing_tags.json"
        self.content_tags_path = CURATION_DIR / "content_tags.json"
        self.other_tags_path = CURATION_DIR / "other_tags.json"
        self.set_combobox = QComboBox(self.set_button_frame)
        self.set_button_layout.addWidget(self.set_combobox, 0, 0)
        self.grid.addWidget(self.set_button_frame, 11, 0)
        self.refresh_set_choices()

        self.grid.addWidget(QLabel("Rating", self), 12, 0)
        self.rating_button_frame = QFrame(self)
        self.rating_button_layout = QGridLayout(self.rating_button_frame)
        self.rating_button_layout.setContentsMargins(0, 0, 0, 0)
        self.rating_button_layout.setSpacing(3)
        self.rating_button_group = QButtonGroup(self)
        self.rating_button_group.setExclusive(True)
        self.rating_buttons = self._create_choice_buttons(
            self.rating_button_layout,
            self.rating_button_group,
            ["SFW", "Questionable", "Cute NSFW", "NSFW", "Explicit"],
            columns=5,
        )
        self.rating_buttons["SFW"].setChecked(True)
        self.grid.addWidget(self.rating_button_frame, 13, 0)

        self.grid.addWidget(QLabel("Pairing", self), 14, 0)
        self.pairing_frame = QFrame(self)
        self.pairing_layout = QGridLayout(self.pairing_frame)
        self.pairing_layout.setContentsMargins(0, 0, 0, 0)
        self.pairing_layout.setSpacing(3)
        self.pairing_options = []
        self.pairing_comboboxes = []
        for index in range(MAX_CHARACTER_SLOTS):
            row = index // CHARACTER_SLOTS_PER_ROW
            row_index = index % CHARACTER_SLOTS_PER_ROW
            column = row_index * 2
            if row_index > 0:
                separator_label = QLabel("X", self.pairing_frame)
                separator_label.setAlignment(Qt.AlignCenter)
                self.pairing_layout.addWidget(separator_label, row, column - 1)
            pairing_combobox = QComboBox(self.pairing_frame)
            pairing_combobox.currentTextChanged.connect(self._emit_values_changed)
            self.pairing_comboboxes.append(pairing_combobox)
            self.pairing_layout.addWidget(pairing_combobox, row, column)
        self.grid.addWidget(self.pairing_frame, 15, 0)
        self.refresh_pairing_choices()

        self.auto_calculate_pairing_button = QPushButton("Auto-Calculate Pairing", self)
        self.auto_calculate_pairing_button.clicked.connect(self.auto_calculate_pairing)
        self.grid.addWidget(self.auto_calculate_pairing_button, 16, 0)

        self.grid.addWidget(QLabel("Content", self), 17, 0)
        self.content_category_combobox = QComboBox(self)
        self.grid.addWidget(self.content_category_combobox, 18, 0)
        self.content_frame = QFrame(self)
        self.content_layout = QGridLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(3)
        self._load_content_checkboxes()
        self.grid.addWidget(self.content_frame, 19, 0)

        self.auto_calculate_content_button = QPushButton("Auto-Calculate Content", self)
        self.auto_calculate_content_button.clicked.connect(self.auto_calculate_content)
        self.grid.addWidget(self.auto_calculate_content_button, 20, 0)

        self.grid.addWidget(QLabel("Other Tags", self), 21, 0)
        self.other_tags_frame = QFrame(self)
        self.other_tags_layout = QGridLayout(self.other_tags_frame)
        self.other_tags_layout.setContentsMargins(0, 0, 0, 0)
        self.other_tags_layout.setSpacing(3)
        self.other_tag_checkboxes = {}
        self.unlisted_other_tags = []
        self._load_other_tag_checkboxes()
        self.grid.addWidget(self.other_tags_frame, 22, 0)
        self.copy_previous_button = QPushButton("Copy Previous", self)
        self.copy_previous_button.setCheckable(True)
        self.grid.addWidget(self.copy_previous_button, 23, 0)

        self.copy_previous_fields_frame = QFrame(self)
        self.copy_previous_fields_layout = QGridLayout(self.copy_previous_fields_frame)
        self.copy_previous_fields_layout.setContentsMargins(12, 0, 0, 0)
        self.copy_previous_fields_layout.setHorizontalSpacing(8)
        self.copy_previous_fields_layout.setVerticalSpacing(2)
        self.copy_status_checkbox = QCheckBox("Copy Status", self.copy_previous_fields_frame)
        self.copy_status_checkbox.setChecked(True)
        self.copy_characters_checkbox = QCheckBox("Copy Characters", self.copy_previous_fields_frame)
        self.copy_characters_checkbox.setChecked(True)
        self.copy_outfit_checkbox = QCheckBox("Copy Outfit", self.copy_previous_fields_frame)
        self.copy_outfit_checkbox.setChecked(True)
        self.copy_content_checkbox = QCheckBox("Copy Content", self.copy_previous_fields_frame)
        self.copy_content_checkbox.setChecked(True)
        self.copy_set_checkbox = QCheckBox("Copy Set", self.copy_previous_fields_frame)
        self.copy_set_checkbox.setChecked(True)
        self.copy_rating_checkbox = QCheckBox("Copy Rating", self.copy_previous_fields_frame)
        self.copy_rating_checkbox.setChecked(True)
        self.copy_pairing_checkbox = QCheckBox("Copy Pairing", self.copy_previous_fields_frame)
        self.copy_pairing_checkbox.setChecked(True)
        copy_field_checkboxes = [
            self.copy_status_checkbox,
            self.copy_characters_checkbox,
            self.copy_outfit_checkbox,
            self.copy_content_checkbox,
            self.copy_set_checkbox,
            self.copy_rating_checkbox,
            self.copy_pairing_checkbox,
        ]
        for index, checkbox in enumerate(copy_field_checkboxes):
            self.copy_previous_fields_layout.addWidget(checkbox, index // 2, index % 2)
        self.grid.addWidget(self.copy_previous_fields_frame, 24, 0)
        self.curate_settings_button = QPushButton("Curate Settings", self)
        self.curate_settings_button.clicked.connect(self.edit_content_tags)
        self.grid.addWidget(self.curate_settings_button, 25, 0)
        self.auto_calculate_all_pairings_button = QPushButton("Auto-Calculate All Pairings", self)
        self.auto_calculate_all_pairings_button.clicked.connect(lambda: self.auto_calculate_all_requested.emit("pairing"))
        self.grid.addWidget(self.auto_calculate_all_pairings_button, 26, 0)
        self.auto_calculate_all_characters_button = QPushButton("Auto-Calculate All Characters", self)
        self.auto_calculate_all_characters_button.clicked.connect(lambda: self.auto_calculate_all_requested.emit("characters"))
        self.grid.addWidget(self.auto_calculate_all_characters_button, 27, 0)
        self.set_bulk_actions_enabled(False)
        self.grid.setRowStretch(28, 1)

        self.set_combobox.currentTextChanged.connect(self._emit_values_changed)
        self.outfit_combobox.currentTextChanged.connect(self._emit_values_changed)
        self.content_category_combobox.currentTextChanged.connect(self._apply_content_category_filter)
        self.status_button_group.buttonToggled.connect(lambda button, checked: checked and self._emit_values_changed())
        self.rating_button_group.buttonToggled.connect(lambda button, checked: checked and self._emit_values_changed())

    def set_bulk_actions_enabled(self, enabled):
        self.auto_calculate_all_pairings_button.setEnabled(enabled)
        self.auto_calculate_all_characters_button.setEnabled(enabled)

    def _load_content_checkboxes(self):
        self.content_definitions = load_content_tags(self.content_tags_path)
        checked_tags = {name for name, checkbox in self.content_checkboxes.items() if checkbox.isChecked()}
        for checkbox in self.content_checkboxes.values():
            self.content_layout.removeWidget(checkbox)
            checkbox.hide()
            checkbox.deleteLater()
        self.content_checkboxes = {}
        self.content_categories = {}
        categories = load_content_tag_groups(self.content_tags_path)
        for index, entry in enumerate(self.content_definitions):
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            category = str(entry.get("category") or "General").strip() or "General"
            if category not in categories:
                categories.append(category)
            checkbox = QCheckBox(name, self.content_frame)
            checkbox.setChecked(name in checked_tags)
            checkbox.toggled.connect(self._emit_values_changed)
            self.content_checkboxes[name] = checkbox
            self.content_categories[name] = category
            self.content_layout.addWidget(checkbox, index // 2, index % 2)
        self.content_category_combobox.blockSignals(True)
        self.content_category_combobox.clear()
        self.content_category_combobox.addItem("All")
        self.content_category_combobox.addItems(categories)
        self.content_category_combobox.setCurrentIndex(0)
        self.content_category_combobox.blockSignals(False)
        self._apply_content_category_filter()

    def _load_other_tag_checkboxes(self):
        checked_tags = [name for name, checkbox in self.other_tag_checkboxes.items() if checkbox.isChecked()]
        checked_tags += [tag for tag in self.unlisted_other_tags if tag not in checked_tags]
        for checkbox in self.other_tag_checkboxes.values():
            self.other_tags_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self.other_tag_checkboxes = {}
        for index, name in enumerate(load_curation_other_tags(self.other_tags_path)):
            checkbox = QCheckBox(name, self.other_tags_frame)
            checkbox.setChecked(name in checked_tags)
            checkbox.toggled.connect(self._emit_values_changed)
            self.other_tag_checkboxes[name] = checkbox
            self.other_tags_layout.addWidget(checkbox, index // 2, index % 2)
        self.unlisted_other_tags = [tag for tag in checked_tags if tag not in self.other_tag_checkboxes]

    def edit_content_tags(self):
        dialog = ContentTagEditor(
            self,
            self.content_tags_path,
            self.pairing_tags_path,
            self.outfits_path,
            self.sets_path,
            self.other_tags_path,
        )
        if dialog.exec():
            self._load_content_checkboxes()
            self._load_other_tag_checkboxes()
            self.refresh_pairing_choices()
            self._refresh_outfit_choices()
            current_set = self.set_combobox.currentText()
            self.refresh_set_choices(dialog.set_renames.get(current_set, current_set))
            self._emit_values_changed()

    def refresh_pairing_choices(self):
        self.pairing_options = ["", *get_pairing_labels(self.pairing_tags_path)]
        for pairing_combobox in self.pairing_comboboxes:
            selected_value = pairing_combobox.currentText()
            pairing_combobox.blockSignals(True)
            pairing_combobox.clear()
            pairing_combobox.addItems(self.pairing_options)
            if selected_value and pairing_combobox.findText(selected_value) < 0:
                pairing_combobox.addItem(selected_value)
            pairing_combobox.setCurrentText(selected_value)
            pairing_combobox.blockSignals(False)

    def _apply_content_category_filter(self):
        selected_category = self.content_category_combobox.currentText()
        visible_checkboxes = []
        for name, checkbox in self.content_checkboxes.items():
            self.content_layout.removeWidget(checkbox)
            is_visible = selected_category in {"", "All"} or self.content_categories.get(name) == selected_category
            checkbox.setVisible(is_visible)
            if is_visible:
                visible_checkboxes.append(checkbox)
        for index, checkbox in enumerate(visible_checkboxes):
            self.content_layout.addWidget(checkbox, index // 2, index % 2)

    def _create_choice_buttons(self, layout, button_group, labels, columns):
        buttons = {}
        for index, label in enumerate(labels):
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setMinimumHeight(36)
            button_group.addButton(button)
            buttons[label] = button
            layout.addWidget(button, index // columns, index % columns)
        return buttons

    def set_curation_manifest(self, manifest):
        controls = [
            *self.status_buttons.values(),
            self.set_combobox,
            self.outfit_combobox,
            *self.rating_buttons.values(),
            *self.pairing_comboboxes,
            *self.content_checkboxes.values(),
            *self.other_tag_checkboxes.values(),
            self.status_button_group,
            self.rating_button_group,
        ]
        for control in controls:
            control.blockSignals(True)
        self.status_buttons.get(manifest["status"], self.status_buttons["Uncurated"]).setChecked(True)
        self._set_character_slots(manifest.get("characters", []))
        self._refresh_outfit_choices(manifest.get("outfits", []))
        self.refresh_set_choices(manifest.get("set_name", ""))
        self.rating_buttons.get(manifest["rating"], self.rating_buttons["SFW"]).setChecked(True)
        other_tag_values = list(manifest.get("other_tags") or [])
        for name, checkbox in self.other_tag_checkboxes.items():
            checkbox.setChecked(name in other_tag_values)
        # Tags later removed from the Other Tags list stay on the image instead of being silently dropped.
        self.unlisted_other_tags = [tag for tag in other_tag_values if tag not in self.other_tag_checkboxes]
        pairing_values = manifest.get("pairing") or []
        for index, pairing_combobox in enumerate(self.pairing_comboboxes):
            pairing_value = pairing_values[index] if index < len(pairing_values) else ""
            if pairing_combobox.findText(pairing_value) < 0:
                pairing_value = ""
            pairing_combobox.setCurrentText(pairing_value)
        content_values = set(manifest.get("content") or [])
        for name, checkbox in self.content_checkboxes.items():
            checkbox.setChecked(name in content_values)
        for control in controls:
            control.blockSignals(False)

    def refresh_set_choices(self, selected_set=None):
        if selected_set is None:
            selected_set = self.set_combobox.currentText()
        self.set_combobox.blockSignals(True)
        self.set_combobox.clear()
        self.set_combobox.addItem("")
        self.set_combobox.addItems(load_curation_sets(self.sets_path))
        if selected_set and self.set_combobox.findText(selected_set) < 0:
            self.set_combobox.addItem(selected_set)
        self.set_combobox.setCurrentText(selected_set or "")
        self.set_combobox.blockSignals(False)

    def _set_character_slots(self, characters):
        while self.character_slots_layout.count():
            item = self.character_slots_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.character_slot_comboboxes = []

        slot_values = list(characters) or ["None"]
        for index, character_name in enumerate(slot_values):
            character_name = resolve_character_id(character_name) or character_name
            character_combobox = QComboBox(self)
            character_combobox.addItem("None")
            character_combobox.addItems(self.character_names)
            if character_combobox.findText(character_name) < 0:
                character_combobox.addItem(character_name)
            character_combobox.setCurrentText(character_name)
            self.character_slot_comboboxes.append(character_combobox)
            self.character_slots_layout.addWidget(character_combobox)
            character_combobox.currentTextChanged.connect(self._on_character_changed)
        self._reserve_character_slot_height()
        self.remove_character_button.setEnabled(len(self.character_slot_comboboxes) > 1)

    def _reserve_character_slot_height(self):
        if self.character_slot_comboboxes:
            row_height = self.character_slot_comboboxes[0].sizeHint().height()
        else:
            probe_combobox = QComboBox(self.character_slots_frame)
            row_height = probe_combobox.sizeHint().height()
            probe_combobox.deleteLater()
        spacing = self.character_slots_layout.spacing()
        self.character_slots_frame.setMinimumHeight(
            (row_height * self.CHARACTER_SLOT_RESERVED_ROWS)
            + (spacing * (self.CHARACTER_SLOT_RESERVED_ROWS - 1))
        )

    def add_character_slot(self):
        slot_values = [
            character_combobox.currentText()
            for character_combobox in self.character_slot_comboboxes
        ]
        self._set_character_slots([*slot_values, "None"])
        self._refresh_outfit_choices()
        self._emit_values_changed()

    def remove_character_slot(self):
        if len(self.character_slot_comboboxes) <= 1:
            return
        slot_values = [
            character_combobox.currentText()
            for character_combobox in self.character_slot_comboboxes[:-1]
        ]
        self._set_character_slots(slot_values)
        self._refresh_outfit_choices()
        self._emit_values_changed()

    def add_character_outfit(self):
        dialog = AddCharacterOutfitDialog(self, self.character_names, self.current_image_path)
        if dialog.exec():
            self._refresh_outfit_choices()

    def delete_character_outfit(self):
        selected_character = next(
            (character_combobox.currentText() for character_combobox in self.character_slot_comboboxes if character_combobox.currentText() != "None"),
            None,
        )
        outfit_name = self.outfit_combobox.currentText()
        if selected_character is None:
            Error(self, "Select a character before deleting a character outfit.")
            return
        confirmation = Confirm(
            self,
            "Delete Character Outfit",
            f"Delete '{outfit_name}' from {selected_character}?",
            "Delete",
            "Cancel",
        )
        if not confirmation.exec():
            return
        try:
            delete_character_outfit(selected_character, outfit_name)
        except ValueError as exc:
            Error(self, str(exc))
            return
        self._refresh_outfit_choices(["None"])
        self._emit_values_changed()

    def _outfit_names_for_selected_characters(self):
        characters_by_name = {
            str(character.get("nameID", "")).strip(): character
            for character in get_all_characters()
            if character.get("nameID")
        }
        outfit_names = []
        for character_combobox in self.character_slot_comboboxes:
            character = characters_by_name.get(character_combobox.currentText())
            if character is None:
                continue
            for outfit in character.get("outfits", []):
                outfit_name = str(outfit.get("name", "")).strip() if isinstance(outfit, dict) else ""
                if outfit_name and outfit_name not in outfit_names:
                    outfit_names.append(outfit_name)
        for outfit_name in load_curation_outfits(self.outfits_path):
            if outfit_name not in outfit_names:
                outfit_names.append(outfit_name)
        return outfit_names

    def _refresh_outfit_choices(self, selected_outfits=None):
        if selected_outfits is None:
            selected_outfits = [self.outfit_combobox.currentText()]
        selected_outfit = (selected_outfits[0] if selected_outfits else "") or "None"
        self.outfit_combobox.blockSignals(True)
        self.outfit_combobox.clear()
        self.outfit_combobox.addItem("None")
        self.outfit_combobox.addItems(self._outfit_names_for_selected_characters())
        if selected_outfit != "None" and self.outfit_combobox.findText(selected_outfit) < 0:
            self.outfit_combobox.addItem(selected_outfit)
        self.outfit_combobox.setCurrentText(selected_outfit)
        self.outfit_combobox.blockSignals(False)

    def _on_character_changed(self):
        self._refresh_outfit_choices()
        self._emit_values_changed()

    def set_character_choices(self, character_names):
        self.character_names = list(character_names)
        if self.character_slot_comboboxes:
            selected_characters = [
                character_combobox.currentText()
                for character_combobox in self.character_slot_comboboxes
            ]
            self._set_character_slots(selected_characters)
            self._refresh_outfit_choices()

    def _emit_values_changed(self):
        self.values_changed.emit(self.curation_values())

    def auto_calculate_characters(self):
        if not self.current_image_path:
            Error(self, "Select an image before auto-calculating characters.")
            return
        characters = calculate_character_matches(self.current_image_path)
        if characters is None:
            return
        self._set_character_slots(characters)
        self._emit_values_changed()

    def auto_calculate_pairing(self):
        if not self.current_image_path:
            Error(self, "Select an image before auto-calculating pairing.")
            return
        pairing_tags = load_pairing_tags(self.pairing_tags_path)
        pairing_matches = calculate_pairing_matches(self.current_image_path, pairing_tags)
        if pairing_matches is None:
            return
        for pairing_combobox, pairing_match in zip(self.pairing_comboboxes, pairing_matches):
            pairing_combobox.blockSignals(True)
            pairing_combobox.setCurrentText(pairing_match)
            pairing_combobox.blockSignals(False)
        self._emit_values_changed()

    def auto_calculate_content(self):
        if not self.current_image_path:
            Error(self, "Select an image before auto-calculating content.")
            return
        content_matches = set(calculate_content_matches(self.current_image_path, self.content_definitions))
        for name, checkbox in self.content_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(name in content_matches)
            checkbox.blockSignals(False)
        self._emit_values_changed()

    def copy_previous_enabled(self):
        return self.copy_previous_button.isChecked()

    def copy_previous_fields(self):
        return {
            "status": self.copy_status_checkbox.isChecked(),
            "characters": self.copy_characters_checkbox.isChecked(),
            "outfits": self.copy_outfit_checkbox.isChecked(),
            "content": self.copy_content_checkbox.isChecked(),
            "set_name": self.copy_set_checkbox.isChecked(),
            "rating": self.copy_rating_checkbox.isChecked(),
            "pairing": self.copy_pairing_checkbox.isChecked(),
        }

    def set_current_image_path(self, image_path):
        self.current_image_path = image_path
        self.dimensions_label.setText(self._format_dimensions(image_path))

    def _format_dimensions(self, image_path):
        if not image_path:
            return ""
        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except (OSError, UnidentifiedImageError):
            return ""
        return f"{width} x {height}"

    def curation_values(self):
        status_button = self.status_button_group.checkedButton()
        rating_button = self.rating_button_group.checkedButton()
        return {
            "status": status_button.text() if status_button is not None else "Uncurated",
            "characters": [
                character_combobox.currentText()
                for character_combobox in self.character_slot_comboboxes
            ],
            "outfits": [] if self.outfit_combobox.currentText() == "None" else [self.outfit_combobox.currentText()],
            "content": [
                name
                for name, checkbox in self.content_checkboxes.items()
                if checkbox.isChecked()
            ],
            "set_name": self.set_combobox.currentText(),
            "rating": rating_button.text() if rating_button is not None else "SFW",
            "other_tags": [
                name
                for name, checkbox in self.other_tag_checkboxes.items()
                if checkbox.isChecked()
            ] + [tag for tag in self.unlisted_other_tags if tag not in self.other_tag_checkboxes],
            "pairing": [pairing_combobox.currentText() for pairing_combobox in self.pairing_comboboxes],
        }