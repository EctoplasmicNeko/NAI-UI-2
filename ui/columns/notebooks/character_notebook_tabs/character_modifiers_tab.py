from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QFrame, QHBoxLayout, QCheckBox, QSpinBox, QLabel, QPushButton, QStackedWidget
from data.character_slots import MAX_CHARACTER_SLOTS
from data.datahub import get_all_characters
from data.paths import CHARACTER_LABELS_FILE
from data.label_groups import filterable_label_values, load_label_group_settings
from widget.decorated_combobox import DecoratedComboBox
from ui.columns.notebooks.character_notebook_tabs.character_mutators_tab import CharacterMutatorsTab


def _coerce_bool(value, default=False):
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


class CharacterModifiersTab(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.build_character_modifiers_tab()

    def build_character_modifiers_tab(self):
        outer_grid = QGridLayout(self)
        outer_grid.setContentsMargins(0, 5, 0, 0)
        outer_grid.setSpacing(5)
        self.mode_button_frame = QFrame(self)
        self.mode_button_layout = QHBoxLayout(self.mode_button_frame)
        self.mode_button_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_button_layout.setSpacing(0)
        self.settings_button = QPushButton("Settings", self.mode_button_frame)
        self.settings_button.setCheckable(True)
        self.settings_button.setChecked(True)
        self.mutators_button = QPushButton("Mutators", self.mode_button_frame)
        self.mutators_button.setCheckable(True)
        self.mode_button_layout.addWidget(self.settings_button)
        self.mode_button_layout.addWidget(self.mutators_button)
        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)
        self.mode_button_group.addButton(self.settings_button, 0)
        self.mode_button_group.addButton(self.mutators_button, 1)
        outer_grid.addWidget(self.mode_button_frame, 0, 0)

        self.stack = QStackedWidget(self)
        outer_grid.addWidget(self.stack, 1, 0)
        outer_grid.setRowStretch(1, 1)
        self.settings_page = QFrame(self.stack)
        self.stack.addWidget(self.settings_page)
        self.grid = QGridLayout(self.settings_page)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.label1_mode = "include"
        self.label2_mode = "include"
        self.label3_mode = "include"

        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 0)
        self.grid.setRowStretch(2, 0)
        self.grid.setRowStretch(3, 0)
        self.grid.setRowStretch(4, 0)
        self.grid.setRowStretch(5, 0)
        self.grid.setRowStretch(6, 0)
        self.grid.setRowStretch(7, 0)
        self.grid.setRowStretch(8, 0)
        self.grid.setRowStretch(9, 0)
        self.grid.setRowStretch(10, 0)
        self.grid.setRowStretch(11, 0)
        self.grid.setRowStretch(12, 0)
        self.grid.setRowStretch(13, 0)
        self.grid.setRowStretch(14, 1)

        self.auto_change_characters_label = QLabel("Auto-Change Characters Settings", self)
        self.auto_change_characters_label.setObjectName("character_modifiers_section_label")
        self.auto_change_characters_label.setAlignment(Qt.AlignCenter)
        self.auto_change_characters_label.setStyleSheet("border: none; font-weight: bold; padding-bottom: 3px;")
        self.grid.addWidget(self.auto_change_characters_label, 0, 0, 1, 2)
        self.auto_advance_characters_checkbox = QCheckBox("Auto-Advance Characters", self)
        self.auto_advance_characters_checkbox.setToolTip("Automatically advance to the next character after each generation.")
        self.grid.addWidget(self.auto_advance_characters_checkbox, 1, 0) 
        self.auto_advance_characters_checkbox.stateChanged.connect(lambda: self.exclusive_checkboxes(self.auto_advance_characters_checkbox)) 

        self.auto_random_characters_checkbox = QCheckBox("Auto-Random Characters", self)
        self.grid.addWidget(self.auto_random_characters_checkbox, 1, 1)
        self.auto_random_characters_checkbox.setToolTip("Automatically select a random character after each generation.")
        self.auto_random_characters_checkbox.stateChanged.connect(lambda: self.exclusive_checkboxes(self.auto_random_characters_checkbox))

        self.auto_advance_character_frequency_spinbox = QSpinBox(self)
        self.auto_advance_character_frequency_spinbox.setToolTip("Set how many generations to wait before auto-advancing to the next character.")
        self.auto_advance_character_frequency_spinbox.setMinimum(0)  
        self.auto_advance_character_frequency_spinbox.setValue(1)  
        self.auto_advance_character_frequency_spinbox.setSpecialValueText("Frequency: On Set")
        self.grid.addWidget(self.auto_advance_character_frequency_spinbox, 2, 0, 1, 2)
        self.auto_advance_character_frequency_spinbox.setPrefix("Frequency: ")

        self.auto_advance_character_label1_combo = DecoratedComboBox(self)
        self.auto_advance_character_label1_combo.addItems(["None"] + list(self.load_labels()))
        self.auto_advance_character_label1_combo.setPrefix("Filter: ")
        self.grid.addWidget(self.auto_advance_character_label1_combo, 3, 0)
        self.auto_advance_character_label1_combo.setToolTip( "Select the label that determines character pool for auto-advancing.")

        self.auto_advance_character_label2_combo = DecoratedComboBox(self)
        self.auto_advance_character_label2_combo.addItems(["None"] + list(self.load_labels()))
        self.grid.addWidget(self.auto_advance_character_label2_combo, 4, 0)
        self.auto_advance_character_label2_combo.setPrefix("Filter: ")
        self.auto_advance_character_label2_combo.setToolTip( "Select the label that determines character pool for auto-advancing.")

        self.auto_advance_character_label3_combo = DecoratedComboBox(self)
        self.auto_advance_character_label3_combo.addItems(["None"] + list(self.load_labels()))
        self.auto_advance_character_label3_combo.setPrefix("Filter: ")
        self.grid.addWidget(self.auto_advance_character_label3_combo, 5, 0)
        self.auto_advance_character_label3_combo.setToolTip( "Select the label that determines character pool for auto-advancing.")

        self.label1_button = QPushButton("Include")
        self.label1_button.clicked.connect(self.toggle_label1_mode)
        self.grid.addWidget(self.label1_button, 3, 1)

        self.label2_button = QPushButton("Include")
        self.label2_button.clicked.connect(self.toggle_label2_mode)
        self.grid.addWidget(self.label2_button, 4, 1)

        self.label3_button = QPushButton("Include")
        self.label3_button.clicked.connect(self.toggle_label3_mode)
        self.grid.addWidget(self.label3_button, 5, 1)

        self.other_settings_label = QLabel("Other Settings", self)
        self.other_settings_label.setObjectName("character_modifiers_section_label")
        self.other_settings_label.setAlignment(Qt.AlignCenter)
        self.other_settings_label.setStyleSheet("border: none; font-weight: bold; padding-top: 3px; padding-bottom: 3px;")
        self.grid.addWidget(self.other_settings_label, 6, 0, 1, 2)

        self.global_tag_association_button = QPushButton("Enable Global Tag Association")
        self.global_tag_association_button.setCheckable(True)
        self.global_tag_association_button.setChecked(False)
        self.global_tag_association_button.setToolTip("Enable or disable global tag association for character modifiers.")
        self.global_tag_association_button.toggled.connect(self.toggle_global_tag_association)
        self.grid.addWidget(self.global_tag_association_button, 7, 0, 1, 2)

        self.disable_associations_button = QPushButton("Disable Associations", self)
        self.disable_associations_button.setCheckable(True)
        self.disable_associations_button.setToolTip(
            "Skip all character, universal, label-scoped tag, and label associations for this character."
        )
        self.grid.addWidget(self.disable_associations_button, 8, 0, 1, 2)
        
        self.gender_swap_frame = QFrame(self)
        self.gender_swap_layout = QGridLayout(self.gender_swap_frame)
        self.gender_swap_layout.setContentsMargins(0, 0, 0, 0)
        self.gender_swap_layout.setSpacing(0)
        self.grid.addWidget(self.gender_swap_frame, 9, 0, 1, 2)
        
        self.boys_to_girls_button = QPushButton("Boys to Girls", self)
        self.boys_to_girls_button.setCheckable(True)
        self.boys_to_girls_button.clicked.connect(lambda: self.girls_to_boys_button.setChecked(False))  # Uncheck the other button when this one is checked
        self.gender_swap_layout.addWidget(self.boys_to_girls_button, 0, 0)
        self.boys_to_girls_button.setToolTip("Swap all male characters to female characters.")
        
        self.girls_to_boys_button = QPushButton("Girls to Boys", self)
        self.girls_to_boys_button.setCheckable(True)
        self.girls_to_boys_button.clicked.connect(lambda: self.boys_to_girls_button.setChecked(False))  # Uncheck the other button when this one is checked
        self.gender_swap_layout.addWidget(self.girls_to_boys_button, 0, 1)
        self.girls_to_boys_button.setToolTip("Swap all female characters to male characters.")

        self.use_default_expression_button = QPushButton("Use Default Expression", self)
        self.use_default_expression_button.setCheckable(True)
        self.use_default_expression_button.setChecked(False)
        self.use_default_expression_button.setToolTip("Append the character's default expression tags to the positive prompt during generation.")
        self.grid.addWidget(self.use_default_expression_button, 10, 0, 1, 2)

        self.can_scramble_button = QPushButton("Can Scramble", self)
        self.can_scramble_button.setCheckable(True)
        self.can_scramble_button.setChecked(False)
        self.can_scramble_button.setToolTip("Allow this character's prompts to be scrambled by prompt modifiers.")
        self.grid.addWidget(self.can_scramble_button, 11, 0, 1, 2)

        self.randomize_quick_weights_button = QPushButton("Randomize Quick Weights", self)
        self.randomize_quick_weights_button.setCheckable(True)
        self.randomize_quick_weights_button.setToolTip(
            "Randomize this slot's active quick weights within their configured limits before each generation."
        )
        self.grid.addWidget(self.randomize_quick_weights_button, 12, 0)

        self.quick_weights_positive_only_button = QPushButton("Positive Only", self)
        self.quick_weights_positive_only_button.setCheckable(True)
        self.quick_weights_positive_only_button.setToolTip(
            "When randomizing quick weights, use only non-negative values up to each weight's maximum."
        )
        self.grid.addWidget(self.quick_weights_positive_only_button, 12, 1)

        self.copy_quick_weights_button = QPushButton("Copy Quick Weights to Other Characters", self)
        self.copy_quick_weights_button.setToolTip(
            "Copy displayed quick-weight values to other saved characters with matching tags "
            "and positive/negative prompt types. Skip values outside the target's limits. "
            "Updates saved character defaults, not universal defaults or other slots' displayed values."
        )
        self.grid.addWidget(self.copy_quick_weights_button, 13, 0, 1, 2)

        self.mutators_page = CharacterMutatorsTab(self)
        self.stack.addWidget(self.mutators_page)
        self.mode_button_group.idToggled.connect(lambda button_id, checked: self.stack.setCurrentIndex(button_id) if checked else None)
        self.boys_to_girls_button.toggled.connect(self.mutators_page.refresh)
        self.girls_to_boys_button.toggled.connect(self.mutators_page.refresh)

    def load_labels(self):
        self.characters = get_all_characters()
        group_settings = load_label_group_settings(CHARACTER_LABELS_FILE)
        label_list = []
        for character in self.characters:
            for label in filterable_label_values(character.get("labels", []), group_settings):
                if label not in label_list:
                    label_list.append(label)
            
        return sorted(label_list)
    
    def reload_labels(self):
        current_label1 = self.auto_advance_character_label1_combo.currentText()
        current_label2 = self.auto_advance_character_label2_combo.currentText()
        current_label3 = self.auto_advance_character_label3_combo.currentText()
        self.auto_advance_character_label1_combo.clear()
        self.auto_advance_character_label2_combo.clear()
        self.auto_advance_character_label3_combo.clear()
        label_list = self.load_labels()
        self.auto_advance_character_label1_combo.addItems(["None"] + label_list)
        self.auto_advance_character_label2_combo.addItems(["None"] + label_list)
        self.auto_advance_character_label3_combo.addItems(["None"] + label_list)
        if current_label1 in label_list:
            self.auto_advance_character_label1_combo.setCurrentText(current_label1)
        else:
            self.auto_advance_character_label1_combo.setCurrentText("None")

        if current_label2 in label_list:
            self.auto_advance_character_label2_combo.setCurrentText(current_label2)
        else:
            self.auto_advance_character_label2_combo.setCurrentText("None")

        if current_label3 in label_list:
            self.auto_advance_character_label3_combo.setCurrentText(current_label3)
        else:
            self.auto_advance_character_label3_combo.setCurrentText("None")
    
    def toggle_label1_mode(self):
        if self.label1_mode == "include":
            self.label1_mode = "exclude"
            self.label1_button.setText("Exclude")
        else:
            self.label1_mode = "include"
            self.label1_button.setText("Include")

    def toggle_label2_mode(self):
        if self.label2_mode == "include":
            self.label2_mode = "exclude"
            self.label2_button.setText("Exclude")
        else:
            self.label2_mode = "include"
            self.label2_button.setText("Include")

    def toggle_label3_mode(self):
        if self.label3_mode == "include":
            self.label3_mode = "exclude"
            self.label3_button.setText("Exclude")
        else:
            self.label3_mode = "include"
            self.label3_button.setText("Include")

    def _find_character_lower_notebook(self):
        current_parent = self.parent()
        while current_parent is not None:
            if all(
                hasattr(current_parent, f"character_tab_{slot_id}")
                for slot_id in range(1, MAX_CHARACTER_SLOTS + 1)
            ):
                return current_parent
            current_parent = current_parent.parent()
        return None

    def toggle_global_tag_association(self, enabled=None):
        # Keep a stable label; toggle state is conveyed by the checked style/state.
        if enabled is None:
            enabled = self.global_tag_association_button.isChecked()

        # Keep this truly global: sync the checkbox state across all character tabs.
        lower_notebook = self._find_character_lower_notebook()
        if lower_notebook is None:
            return

        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            lower_tab = getattr(lower_notebook, f"character_tab_{slot_id}", None)
            if lower_tab is None:
                continue

            sub_notebook = getattr(lower_tab, "sub_notebook", None)
            if sub_notebook is None:
                continue

            modifiers_tab = getattr(sub_notebook, "character_sub_tab_4", None)
            if modifiers_tab is None or modifiers_tab is self:
                continue

            peer_button = modifiers_tab.global_tag_association_button
            if peer_button.isChecked() == enabled:
                continue

            peer_button.blockSignals(True)
            peer_button.setChecked(enabled)
            peer_button.blockSignals(False)

    def export_state(self):
        return {
            'character_global_tag_association_enabled': self.global_tag_association_button.isChecked(),
            'character_disable_associations': self.disable_associations_button.isChecked(),
            'character_randomize_quick_weights': self.randomize_quick_weights_button.isChecked(),
            'character_quick_weights_positive_only': self.quick_weights_positive_only_button.isChecked(),
            'boys_to_girls': self.boys_to_girls_button.isChecked(),
            'girls_to_boys': self.girls_to_boys_button.isChecked(),
            'use_default_expression': self.use_default_expression_button.isChecked(),
            'character_can_scramble': self.can_scramble_button.isChecked(),
            'auto_advance_character_label1': self.auto_advance_character_label1_combo.currentText(),
            'label1_mode': self.label1_mode,
            'auto_advance_character_label2': self.auto_advance_character_label2_combo.currentText(),
            'label2_mode': self.label2_mode,
            'auto_advance_character_label3': self.auto_advance_character_label3_combo.currentText(),
            'label3_mode': self.label3_mode,
        }

    def import_state(self, loaded, import_filters=True):
        self.auto_advance_characters_checkbox.setChecked(
            _coerce_bool(loaded.get('auto_advance_characters', False))
        )
        self.auto_random_characters_checkbox.setChecked(
            _coerce_bool(loaded.get('auto_random_characters', False))
        )
        self.auto_advance_character_frequency_spinbox.setValue(
            loaded.get('auto_advance_character_frequency', 1)
        )

        enabled = _coerce_bool(loaded.get('character_global_tag_association_enabled', False))
        self.global_tag_association_button.setChecked(enabled)
        self.disable_associations_button.setChecked(
            _coerce_bool(loaded.get('character_disable_associations', False))
        )
        self.randomize_quick_weights_button.setChecked(
            _coerce_bool(loaded.get('character_randomize_quick_weights', False))
        )
        self.quick_weights_positive_only_button.setChecked(
            _coerce_bool(loaded.get('character_quick_weights_positive_only', False))
        )

        boys_to_girls = _coerce_bool(loaded.get('boys_to_girls', False))
        girls_to_boys = _coerce_bool(loaded.get('girls_to_boys', False))
        self.boys_to_girls_button.setChecked(boys_to_girls)
        self.girls_to_boys_button.setChecked(girls_to_boys)

        use_default_expression = _coerce_bool(loaded.get('use_default_expression', False))
        self.use_default_expression_button.setChecked(use_default_expression)

        can_scramble = _coerce_bool(loaded.get('character_can_scramble', False))
        self.can_scramble_button.setChecked(can_scramble)

        if import_filters:
            # Restore filter labels
            label1 = loaded.get('auto_advance_character_label1', 'None')
            if self.auto_advance_character_label1_combo.findText(label1) != -1:
                self.auto_advance_character_label1_combo.setCurrentText(label1)
            
            label2 = loaded.get('auto_advance_character_label2', 'None')
            if self.auto_advance_character_label2_combo.findText(label2) != -1:
                self.auto_advance_character_label2_combo.setCurrentText(label2)
            
            label3 = loaded.get('auto_advance_character_label3', 'None')
            if self.auto_advance_character_label3_combo.findText(label3) != -1:
                self.auto_advance_character_label3_combo.setCurrentText(label3)

            # Restore filter modes
            self.label1_mode = loaded.get('label1_mode', 'include')
            self.label1_button.setText("Exclude" if self.label1_mode == "exclude" else "Include")
            
            self.label2_mode = loaded.get('label2_mode', 'include')
            self.label2_button.setText("Exclude" if self.label2_mode == "exclude" else "Include")
            
            self.label3_mode = loaded.get('label3_mode', 'include')
            self.label3_button.setText("Exclude" if self.label3_mode == "exclude" else "Include")

    def exclusive_checkboxes(self, checked_checkbox):
        if checked_checkbox == self.auto_advance_characters_checkbox and checked_checkbox.isChecked():
            self.auto_random_characters_checkbox.setChecked(False)
        elif checked_checkbox == self.auto_random_characters_checkbox and checked_checkbox.isChecked():
            self.auto_advance_characters_checkbox.setChecked(False)