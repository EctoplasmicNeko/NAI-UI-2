from PySide6.QtWidgets import QGridLayout, QFrame, QLabel, QLineEdit, QMenu, QPushButton
from PySide6.QtCore import Signal
from widget import decorated_combobox
from data.themes import available_themes
from signaling.speciesbaronoff import species_bar_on_off
from signaling.minimal_character_tab import minimal_character_tab
from windows.confirmation import Confirm
from windows.manage_character_order import CharacterOrderWindow
from windows.special_syntax import SpecialSyntaxDialog
from PySide6.QtWidgets import QDialog



class ProgramSettingsTab(QFrame):
    reset_ui_requested = Signal()

    def __init__(self, parent, image_cache):
        super().__init__(parent,)
        self.image_cache = image_cache
        self.special_syntax_dialog = None
        self.available_themes = self.load_available_themes()
        self.build_program_settings_tab()

    def build_program_settings_tab(self):

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
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
        self.grid.setRowStretch(10, 1)

        self.password_label = QLabel('NAI API Key')
        self.grid.addWidget(self.password_label, 0, 0)

        self.API_entry = QLineEdit(self)
        self.grid.addWidget(self.API_entry, 0, 1)

        self.manage_characters_button = QPushButton('Manage Characters', self)
        self.grid.addWidget(self.manage_characters_button, 1, 0)
        
        self.manage_presets_button = QPushButton('Manage Presets', self)
        self.manage_presets_menu = QMenu(self.manage_presets_button)
        self.manage_sizes_action = self.manage_presets_menu.addAction('Sizes')
        self.manage_presets_button.setMenu(self.manage_presets_menu)
        self.grid.addWidget(self.manage_presets_button, 2, 0)

        self.manage_wildcard_button = QPushButton('Manage Wildcards', self)
        self.grid.addWidget(self.manage_wildcard_button, 3, 0)

        self.manage_assistants_button = QPushButton('Manage Assistants', self)
        self.grid.addWidget(self.manage_assistants_button, 4, 0)

        self.generate_button = QPushButton('Generate')
        self.grid.addWidget(self.generate_button, 5, 0)

        self.test_button = QPushButton('Test')
        self.grid.addWidget(self.test_button, 6, 0)

        self.theme_combo = decorated_combobox.DecoratedComboBox(self)
        self.theme_combo.setPrefix("Theme: ")
        self.theme_combo.addItems(self.available_themes)
        self.grid.addWidget(self.theme_combo, 8, 0) 

        self.enable_species_bar_checkbox = QPushButton('Enable Species Bar', self)
        self.enable_species_bar_checkbox.toggled.connect(self.hide_species_bar)
        self.enable_species_bar_checkbox.setCheckable(True)
        self.grid.addWidget(self.enable_species_bar_checkbox, 1, 1)

        self.enable_character_fluff_tab_checkbox = QPushButton('Enable Character Fluff Tab', self)
        self.enable_character_fluff_tab_checkbox.toggled.connect(self.hide_character_fluff_tab)
        self.enable_character_fluff_tab_checkbox.setCheckable(True)
        self.grid.addWidget(self.enable_character_fluff_tab_checkbox, 2, 1)

        self.enable_reference_image_b64_capture_checkbox = QPushButton('Embed References', self)
        self.enable_reference_image_b64_capture_checkbox.toggled.connect(self.enable_b64_capture)
        self.enable_reference_image_b64_capture_checkbox.setCheckable(True)
        self.grid.addWidget(self.enable_reference_image_b64_capture_checkbox, 3, 1)

        self.use_alt_character_portraits_checkbox = QPushButton('Use Alt Character Portraits', self)
        self.use_alt_character_portraits_checkbox.toggled.connect(self.toggle_alt_character_portraits)
        self.use_alt_character_portraits_checkbox.setCheckable(True)
        self.grid.addWidget(self.use_alt_character_portraits_checkbox, 4, 1)

        self.character_sorting_combo = decorated_combobox.DecoratedComboBox(self)
        self.character_sorting_combo.setPrefix("Character Sorting: ")
        self.character_sorting_combo.addItems(["Status", "Alphabetical", "Youngest", "Oldest", "Custom"])
        self.grid.addWidget(self.character_sorting_combo, 5, 1)

        self.all_character_settings_button = QPushButton('All Character Settings', self)
        self.grid.addWidget(self.all_character_settings_button, 7, 0)

        self.reorder_characters_button = QPushButton('Reorder Custom Sort', self)
        self.reorder_characters_button.clicked.connect(self.open_character_order_window)
        self.grid.addWidget(self.reorder_characters_button, 6, 1)

        self.write_hydrus_sidecar_checkbox = QPushButton('Write Hydrus Sidecar Files', self)
        self.write_hydrus_sidecar_checkbox.setCheckable(True)
        self.grid.addWidget(self.write_hydrus_sidecar_checkbox, 7, 1)

        self.reset_ui_button = QPushButton('Reset UI', self)
        self.reset_ui_button.setObjectName('reset_ui_button')
        self.reset_ui_button.setToolTip('Clear prompts, characters, references, selections, and automation.')
        self.reset_ui_button.clicked.connect(self.confirm_reset_ui)
        self.grid.addWidget(self.reset_ui_button, 8, 1)

        self.special_syntax_button = QPushButton('Special Syntax', self)
        self.special_syntax_button.clicked.connect(self.open_special_syntax_window)
        self.grid.addWidget(self.special_syntax_button, 9, 0)

        self.show_account_usage_bars_button = QPushButton('Show Account Usage Bars', self)
        self.show_account_usage_bars_button.setCheckable(True)
        self.show_account_usage_bars_button.setChecked(True)
        self.show_account_usage_bars_button.setToolTip('Show or hide the Anlas and V5 usage bars beside Loops and Sets.')
        self.grid.addWidget(self.show_account_usage_bars_button, 9, 1)

    def confirm_reset_ui(self):
        confirmation = Confirm(
            self,
            "Reset UI",
            "Clear all prompts, characters, references, selections, and automation?",
            "Reset",
            "Cancel",
        )
        if confirmation.exec() == QDialog.Accepted:
            self.reset_ui_requested.emit()


    def export_state(self):
        return{
            'API_key': self.API_entry.text(),
            'selected_theme': self.theme_combo.currentText(),
            'enable_species_bar': self.enable_species_bar_checkbox.isChecked(),
            'enable_character_fluff_tab': self.enable_character_fluff_tab_checkbox.isChecked(),
            'enable_reference_image_b64_capture': self.enable_reference_image_b64_capture_checkbox.isChecked(),
            'use_alt_character_portraits': self.use_alt_character_portraits_checkbox.isChecked(),
            'enable_hydrus_sidecar': self.write_hydrus_sidecar_checkbox.isChecked(),
            'character_sorting': self.character_sorting_combo.currentText(),
            'show_account_usage_bars': self.show_account_usage_bars_button.isChecked(),
        }

    def open_character_order_window(self):
        dialog = CharacterOrderWindow(self, self.image_cache)
        dialog.exec()

    def open_special_syntax_window(self):
        # Non-modal so prompts can still be edited while the reference is open.
        if self.special_syntax_dialog is None:
            self.special_syntax_dialog = SpecialSyntaxDialog(self)
        self.special_syntax_dialog.show()
        self.special_syntax_dialog.raise_()
        self.special_syntax_dialog.activateWindow()

    def import_state(self, loaded):
        self.show_account_usage_bars_button.setChecked(loaded.get('show_account_usage_bars', True))
        self.API_entry.setText(loaded['API_key'])
        self.theme_combo.setCurrentText(loaded['selected_theme'])   
        self.enable_species_bar_checkbox.setChecked(loaded.get('enable_species_bar', False))
        self.hide_species_bar()

        self.enable_character_fluff_tab_checkbox.setChecked(loaded.get('enable_character_fluff_tab', False))
        self.hide_character_fluff_tab()

        self.enable_reference_image_b64_capture_checkbox.blockSignals(True)
        self.enable_reference_image_b64_capture_checkbox.setChecked(loaded.get('enable_reference_image_b64_capture', False))
        self.enable_reference_image_b64_capture_checkbox.blockSignals(False)
        self.enable_b64_capture(loaded.get('enable_reference_image_b64_capture', False), startup=True)

        self.use_alt_character_portraits_checkbox.blockSignals(True)
        self.use_alt_character_portraits_checkbox.setChecked(loaded.get('use_alt_character_portraits', False))
        self.use_alt_character_portraits_checkbox.blockSignals(False)
        self.toggle_alt_character_portraits(loaded.get('use_alt_character_portraits', False), startup=True)
        
        self.write_hydrus_sidecar_checkbox.setChecked(loaded.get('enable_hydrus_sidecar', False))

        self.character_sorting_combo.setCurrentText(loaded.get('character_sorting', 'Status'))

    def load_available_themes(self):
            return available_themes()
    
    def hide_species_bar(self):
        checked = self.enable_species_bar_checkbox.isChecked()
        species_bar_on_off.on_signal.emit(checked)
        if checked:
            self.enable_species_bar_checkbox.setText('Species Bar (On)')
        else:
            self.enable_species_bar_checkbox.setText('Species Bar (Off)')

    def hide_character_fluff_tab(self):
        checked = self.enable_character_fluff_tab_checkbox.isChecked()
        minimal_character_tab.on_signal.emit(checked)
        if checked:
            self.enable_character_fluff_tab_checkbox.setText('Character Fluff Tab (On)')
        else:
            self.enable_character_fluff_tab_checkbox.setText('Character Fluff Tab (Off)')



    def enable_b64_capture(self, checked: bool, startup: bool = False):
        if not startup:
            if checked:
                dialog = Confirm(
                    self,
                    "Enable B64 Capture",
                    "Enabling B64 capture will increase metadata size significantly. "
                    "Are you sure you want to enable this feature?",
                    "Enable",
                    "Cancel"
                )
                if dialog.exec() == QDialog.Accepted:
                    # Already checked at this point
                    self.enable_reference_image_b64_capture_checkbox.setText("Embed References (On)")
                else:
                    # User cancelled – revert checkbox without re-triggering the slot
                    cb = self.enable_reference_image_b64_capture_checkbox
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
                    cb.setText("Embed References (Off)")
            else:
                # Just turned off normally
                self.enable_reference_image_b64_capture_checkbox.setText("Embed References (Off)")
        else:
            # Startup case
            if checked:
                self.enable_reference_image_b64_capture_checkbox.setText("Embed References (On)")
            else:
                self.enable_reference_image_b64_capture_checkbox.setText("Embed References (Off)")

    def toggle_alt_character_portraits(self, checked: bool, startup: bool = False):
        if checked:
            self.use_alt_character_portraits_checkbox.setText("Use Alt Character Portraits (On)")
        else:
            self.use_alt_character_portraits_checkbox.setText("Use Alt Character Portraits (Off)")
