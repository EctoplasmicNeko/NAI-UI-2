
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QFrame, QPushButton, QButtonGroup, QLabel
from widget import decorated_combobox
from signaling.outfit_changed import outfit_changed_signal


class CharacterPresetTab(QFrame):
    outfit_role_toggled = Signal(str, bool, int)
    outfit_modifier_toggled = Signal(str, bool, int)

    OUTFIT_ROLE_BUTTONS = [
        "None",
        "School Uniform",
        "Underwear",
        "Swimwear",
        "Warm Weather",
        "Cold Weather",
        "Pajamas",
    ]

    OUTFIT_MODIFIER_BUTTONS = [
        "Canonical",
    ]
    
    def __init__(self, parent, ID):
        super().__init__(parent)
        self.ID = ID
        self.build_character_preset_tab()
        

    def build_character_preset_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.outfit_combo = decorated_combobox.DecoratedComboBox(self)
        self.grid.addWidget(self.outfit_combo, 0, 0, 1, 1) 
        self.outfit_combo.currentTextChanged.connect(self.on_outfit_changed)

        # Add a small visual gap between the combobox and the role controls.
        self.grid.setRowMinimumHeight(1, 6)

        self.outfit_role_label = QLabel("Outfit Auto-Picker", self)
        self.grid.addWidget(self.outfit_role_label, 2, 0, 1, 1)

        self.outfit_role_button_group = QButtonGroup(self)
        self.outfit_role_button_group.setExclusive(False)
        self.outfit_role_button_group.buttonToggled.connect(self.on_role_button_toggled)

        # Stack role filters vertically beneath the outfit combo.
        for row, label in enumerate(self.OUTFIT_ROLE_BUTTONS, start=3):
            button = QPushButton(label)
            button.setCheckable(True)
            self.outfit_role_button_group.addButton(button)
            self.grid.addWidget(button, row, 0, 1, 1)
            self.grid.setRowStretch(row, 0)

        # Leave role filters off by default so users can opt in explicitly.
        self.clear_selected_outfit_role()

        modifier_label_row = len(self.OUTFIT_ROLE_BUTTONS) + 3
        self.outfit_modifier_label = QLabel("Modifiers", self)
        self.grid.addWidget(self.outfit_modifier_label, modifier_label_row, 0, 1, 1)

        self.outfit_modifier_button_group = QButtonGroup(self)
        self.outfit_modifier_button_group.setExclusive(False)
        self.outfit_modifier_button_group.buttonToggled.connect(self.on_modifier_button_toggled)

        for row, label in enumerate(self.OUTFIT_MODIFIER_BUTTONS, start=modifier_label_row + 1):
            button = QPushButton(label)
            button.setCheckable(True)
            self.outfit_modifier_button_group.addButton(button)
            self.grid.addWidget(button, row, 0, 1, 1)
            self.grid.setRowStretch(row, 0)

        self.clear_selected_outfit_modifier()

        # Push remaining free space to the bottom, keeping controls consolidated at top.
        spacer_row = len(self.OUTFIT_ROLE_BUTTONS) + len(self.OUTFIT_MODIFIER_BUTTONS) + 5
        self.grid.setRowStretch(spacer_row, 1)

        self.grid.setColumnStretch(0, 1)

    def on_outfit_changed(self, new_outfit_name):
        outfit_changed_signal.outfit_changed.emit(new_outfit_name, self.ID)

    def get_selected_outfit_role(self):
        checked_button = self.outfit_role_button_group.checkedButton()
        if checked_button is None:
            return ""
        return checked_button.text()

    def clear_selected_outfit_role(self):
        for button in self.outfit_role_button_group.buttons():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)

    def on_role_button_toggled(self, toggled_button, checked):
        if checked:
            for button in self.outfit_role_button_group.buttons():
                if button is toggled_button:
                    continue
                if button.isChecked():
                    button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(False)

        self.outfit_role_toggled.emit(toggled_button.text(), checked, self.ID)

    def set_selected_outfit_role(self, role_name):
        if role_name is None:
            target_role = "None"
        else:
            target_role = str(role_name).strip()

        if not target_role:
            self.clear_selected_outfit_role()
            return

        for button in self.outfit_role_button_group.buttons():
            if button.text().strip().lower() == target_role.lower():
                button.setChecked(True)
                return

        # Fallback for unknown/legacy values.
        for button in self.outfit_role_button_group.buttons():
            if button.text() == "None":
                button.setChecked(True)
                return

    def get_selected_outfit_modifier(self):
        selected_modifiers = self.get_selected_outfit_modifiers()
        if not selected_modifiers:
            return ""
        return selected_modifiers[0]

    def get_selected_outfit_modifiers(self):
        return [
            button.text()
            for button in self.outfit_modifier_button_group.buttons()
            if button.isChecked()
        ]

    def clear_selected_outfit_modifier(self):
        for button in self.outfit_modifier_button_group.buttons():
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)

    def on_modifier_button_toggled(self, toggled_button, checked):
        # Modifiers are intentionally multi-select.
        self.outfit_modifier_toggled.emit(toggled_button.text(), checked, self.ID)

    def set_selected_outfit_modifier(self, modifier_name):
        target_modifiers = []
        if isinstance(modifier_name, list):
            target_modifiers = [str(item).strip().lower() for item in modifier_name if str(item).strip()]
        elif modifier_name is not None:
            cleaned_value = str(modifier_name).strip()
            if cleaned_value:
                target_modifiers = [cleaned_value.lower()]

        if not target_modifiers:
            self.clear_selected_outfit_modifier()
            return

        target_modifier_set = set(target_modifiers)
        for button in self.outfit_modifier_button_group.buttons():
            should_check = button.text().strip().lower() in target_modifier_set
            button.blockSignals(True)
            button.setChecked(should_check)
            button.blockSignals(False)



        

