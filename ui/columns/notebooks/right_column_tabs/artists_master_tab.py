from pathlib import Path
import re
import random

from PySide6.QtWidgets import QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout
from PySide6.QtCore import Qt

from data.paths import USER_DIR
from process.frequency import frequency_matches
from ui.columns.notebooks.right_column_tabs.artist_entry import ArtistEntry


class ArtistsMasterTab(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.artists_root_dir = USER_DIR / "artists"
        self.artists_root_dir.mkdir(parents=True, exist_ok=True)
        self.entries = {}
        self.saved_entry_state = {}
        self.current_model_files = set()
        self.build_artists_tab()
        self.refresh_artists()

        model_combo = self.window().findChild(QComboBox, "model_select_combobox")
        if model_combo is not None:
            model_combo.currentIndexChanged.connect(self.refresh_artists)

    def build_artists_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(3)

        self.enable_artists_checkbox = QPushButton("Use Artists", self)
        self.enable_artists_checkbox.setCheckable(True)
        self.grid.addWidget(self.enable_artists_checkbox, 0, 0, 1, 3)

        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)

        self.manual_artists_button = QPushButton("Manual", self)
        self.manual_artists_button.setCheckable(True)
        self.manual_artists_button.setChecked(True)

        self.random_artists_checkbox = QPushButton("Random", self)
        self.random_artists_checkbox.setCheckable(True)
        self.random_artists_checkbox.toggled.connect(self._on_random_artists_toggled)

        self.advance_artists_checkbox = QPushButton("Advance", self)
        self.advance_artists_checkbox.setCheckable(True)
        self.advance_artists_checkbox.toggled.connect(self._on_advance_artists_toggled)

        self.mode_button_group.addButton(self.manual_artists_button, 0)
        self.mode_button_group.addButton(self.random_artists_checkbox, 1)
        self.mode_button_group.addButton(self.advance_artists_checkbox, 2)
        self.mode_button_group.idToggled.connect(lambda _button_id, checked: self._apply_artist_mode() if checked else None)

        self.grid.addWidget(self.manual_artists_button, 1, 0)
        self.grid.addWidget(self.random_artists_checkbox, 1, 1)
        self.grid.addWidget(self.advance_artists_checkbox, 1, 2)

        self.random_tools_frame = QFrame(self)
        self.random_tools_grid = QGridLayout(self.random_tools_frame)
        self.random_tools_grid.setContentsMargins(0, 0, 0, 0)
        self.random_tools_grid.setHorizontalSpacing(3)
        self.random_tools_grid.setVerticalSpacing(3)
        self.random_tools_grid.setColumnStretch(0, 1)
        self.random_tools_grid.setColumnStretch(1, 1)
        self.grid.addWidget(self.random_tools_frame, 2, 0, 4, 3)

        self.randomize_strengths_checkbox = QCheckBox("Randomize Strengths", self)
        self.random_tools_grid.addWidget(self.randomize_strengths_checkbox, 0, 0, 1, 2)

        self.random_artist_frequency_spinbox = QSpinBox(self)
        self.random_artist_frequency_spinbox.setRange(1, 1000)
        self.random_artist_frequency_spinbox.setValue(1)
        self.random_artist_frequency_spinbox.setPrefix("Random Every: ")
        self.random_artist_frequency_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_artist_frequency_spinbox, 1, 0, 1, 2)

        self.advance_artist_frequency_spinbox = QSpinBox(self)
        self.advance_artist_frequency_spinbox.setRange(1, 1000)
        self.advance_artist_frequency_spinbox.setValue(1)
        self.advance_artist_frequency_spinbox.setPrefix("Advance Every: ")
        self.advance_artist_frequency_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.grid.addWidget(self.advance_artist_frequency_spinbox, 2, 0, 1, 3)

        self.random_artist_minimum_spinbox = QSpinBox(self)
        self.random_artist_minimum_spinbox.setRange(0, 1000)
        self.random_artist_minimum_spinbox.setPrefix("Min Artists: ")
        self.random_artist_minimum_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_artist_minimum_spinbox, 2, 0)

        self.random_artist_maximum_spinbox = QSpinBox(self)
        self.random_artist_maximum_spinbox.setRange(0, 1000)
        self.random_artist_maximum_spinbox.setValue(1)
        self.random_artist_maximum_spinbox.setPrefix("Max Artists: ")
        self.random_artist_maximum_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_artist_maximum_spinbox, 2, 1)

        self.random_strength_minimum_spinbox = QDoubleSpinBox(self)
        self.random_strength_minimum_spinbox.setRange(0.0, 10.0)
        self.random_strength_minimum_spinbox.setDecimals(2)
        self.random_strength_minimum_spinbox.setSingleStep(0.05)
        self.random_strength_minimum_spinbox.setValue(1.0)
        self.random_strength_minimum_spinbox.setPrefix("Min Strength: ")
        self.random_strength_minimum_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_strength_minimum_spinbox, 3, 0)

        self.random_strength_maximum_spinbox = QDoubleSpinBox(self)
        self.random_strength_maximum_spinbox.setRange(0.0, 10.0)
        self.random_strength_maximum_spinbox.setDecimals(2)
        self.random_strength_maximum_spinbox.setSingleStep(0.05)
        self.random_strength_maximum_spinbox.setValue(1.0)
        self.random_strength_maximum_spinbox.setPrefix("Max Strength: ")
        self.random_strength_maximum_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_strength_maximum_spinbox, 3, 1)

        self.clear_selections_button = QPushButton("Clear All Selections", self)
        self.clear_selections_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.clear_selections_button.clicked.connect(self.clear_all_selections)
        self.grid.addWidget(self.clear_selections_button, 6, 0, 1, 3)

        self.subfolder_combobox = QComboBox(self)
        self.subfolder_combobox.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.grid.addWidget(self.subfolder_combobox, 7, 0, 1, 3)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_content = QFrame(self.scroll_area)
        self.scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.scroll_area.setWidget(self.scroll_content)
        self.artists_layout = QVBoxLayout(self.scroll_content)
        self.artists_layout.setContentsMargins(4, 4, 4, 4)
        self.artists_layout.setSpacing(8)
        self.grid.addWidget(self.scroll_area, 8, 0, 1, 3)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 1)
        self.grid.setRowStretch(8, 1)
        self.subfolder_combobox.currentIndexChanged.connect(self.refresh_artists)
        self._apply_artist_mode()

    def _on_random_artists_toggled(self, checked):
        if checked:
            self.advance_artists_checkbox.setChecked(False)

    def _on_advance_artists_toggled(self, checked):
        if checked:
            self.random_artists_checkbox.setChecked(False)

    def _apply_artist_mode(self):
        random_mode = self.random_artists_checkbox.isChecked()
        advance_mode = self.advance_artists_checkbox.isChecked()

        for widget in (
            self.random_tools_frame,
        ):
            widget.setVisible(random_mode)
        self.advance_artist_frequency_spinbox.setVisible(advance_mode)

    def _current_model_folder_names(self):
        model_combo = self.window().findChild(QComboBox, "model_select_combobox")
        if model_combo is None:
            return set()
        names = {model_combo.currentText()}
        payload_name = model_combo.property("payload_name")
        if payload_name:
            names.add(str(payload_name))
        model_key = model_combo.property("model_key")
        if model_key:
            model_key = str(model_key)
            names.add(model_key.lower())
            names.add(re.sub(r"(?<=[0-9])(?=[A-Z])", "_", model_key).lower())
        return names

    def _clear_entries(self):
        while self.artists_layout.count():
            item = self.artists_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _model_directories(self):
        return [
            path for path in self.artists_root_dir.iterdir()
            if path.is_dir() and path.name in self._current_model_folder_names()
        ]

    def _artist_files_by_folder(self):
        folders = {"__root__": [], "__all__": []}
        for model_dir in self._model_directories():
            root_files = sorted(path for path in model_dir.iterdir() if path.is_file())
            folders["__root__"].extend(root_files)
            folders["__all__"].extend(root_files)

            for subfolder in sorted(path for path in model_dir.iterdir() if path.is_dir()):
                files = sorted(path for path in subfolder.rglob("*") if path.is_file())
                folders.setdefault(subfolder.name, []).extend(files)
                folders["__all__"].extend(files)

        for folder_name in folders:
            folders[folder_name] = sorted(set(folders[folder_name]))
        return folders

    def _refresh_subfolder_options(self, folders):
        selected_value = self.subfolder_combobox.currentData()
        self.subfolder_combobox.blockSignals(True)
        self.subfolder_combobox.clear()
        self.subfolder_combobox.addItem("All", "__all__")
        self.subfolder_combobox.addItem("Root", "__root__")
        for folder_name in sorted(name for name in folders if name not in {"__all__", "__root__"}):
            self.subfolder_combobox.addItem(folder_name, folder_name)
        selected_index = self.subfolder_combobox.findData(selected_value)
        self.subfolder_combobox.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.subfolder_combobox.blockSignals(False)

    def refresh_artists(self):
        self.saved_entry_state.update(self._entry_state())
        self._clear_entries()
        self.entries = {}

        folders = self._artist_files_by_folder()
        self.current_model_files = set(folders["__all__"])
        self._refresh_subfolder_options(folders)
        artist_files = folders.get(self.subfolder_combobox.currentData(), [])

        if not artist_files:
            placeholder = QLabel("No artists found for the current model.", self.scroll_content)
            placeholder.setAlignment(Qt.AlignCenter)
            self.artists_layout.addWidget(placeholder)
            self.artists_layout.addStretch(1)
            return

        for file_path in artist_files:
            stored = self.saved_entry_state.get(str(file_path), {})
            entry = ArtistEntry(self.scroll_content, file_path, stored.get("strength", 1.0))
            entry.use_artist_checkbox.setChecked(stored.get("selected", False))
            self.entries[str(file_path)] = entry
            self.artists_layout.addWidget(entry)

        self.artists_layout.addStretch(1)

    def _randomize_artists(self):
        available_files = [Path(file_path) for file_path in self.entries]
        if not available_files:
            return
        minimum = self.random_artist_minimum_spinbox.value()
        maximum = self.random_artist_maximum_spinbox.value()
        minimum, maximum = sorted((minimum, maximum))
        count = random.randint(minimum, maximum)
        count = min(count, len(available_files))
        selected_files = set(random.sample(available_files, count))

        minimum_strength = self.random_strength_minimum_spinbox.value()
        maximum_strength = self.random_strength_maximum_spinbox.value()
        minimum_strength, maximum_strength = sorted((minimum_strength, maximum_strength))

        for file_path in self.current_model_files:
            values = self.saved_entry_state.setdefault(str(file_path), {})
            values["selected"] = file_path in selected_files
            if file_path in selected_files and self.randomize_strengths_checkbox.isChecked():
                values["strength"] = round(random.uniform(minimum_strength, maximum_strength), 2)

        for file_path, entry in self.entries.items():
            values = self.saved_entry_state[file_path]
            entry.use_artist_checkbox.setChecked(values["selected"])
            entry.strength_spinner.setValue(values.get("strength", 1.0))

    def _advance_artists(self):
        available_files = [Path(file_path) for file_path in self.entries]
        if not available_files:
            return

        selected_indexes = [
            index for index, file_path in enumerate(available_files)
            if self.saved_entry_state.get(str(file_path), {}).get("selected", False)
        ]
        if not selected_indexes:
            selected_indexes = [-1]
        selected_files = {available_files[(index + 1) % len(available_files)] for index in selected_indexes}

        for file_path in self.current_model_files:
            values = self.saved_entry_state.setdefault(str(file_path), {})
            values["selected"] = file_path in selected_files

        for file_path, entry in self.entries.items():
            values = self.saved_entry_state[file_path]
            entry.use_artist_checkbox.setChecked(values["selected"])
            entry.strength_spinner.setValue(values.get("strength", 1.0))

    def clear_all_selections(self):
        for file_path in self.current_model_files:
            values = self.saved_entry_state.setdefault(str(file_path), {})
            values["selected"] = False

        for entry in self.entries.values():
            entry.use_artist_checkbox.setChecked(False)

    def export_state(self, randomize_artists=False, force_random=False, generation_number=1):
        self.saved_entry_state.update(self._entry_state())
        if randomize_artists and force_random:
            self._randomize_artists()
        elif randomize_artists and self.random_artists_checkbox.isChecked() and frequency_matches(self.random_artist_frequency_spinbox.value(), generation_number):
            self._randomize_artists()
        elif randomize_artists and self.advance_artists_checkbox.isChecked() and frequency_matches(self.advance_artist_frequency_spinbox.value(), generation_number):
            self._advance_artists()
        entries = {}
        for file_path, values in self.saved_entry_state.items():
            entries[file_path] = values
        return {
            "entries": entries,
            "prompt_entries": self.export_prompt_entries(),
            "artists_enabled": self.enable_artists_checkbox.isChecked(),
            "random_artists": self.random_artists_checkbox.isChecked(),
            "random_artist_frequency": self.random_artist_frequency_spinbox.value(),
            "advance_artists": self.advance_artists_checkbox.isChecked(),
            "advance_artist_frequency": self.advance_artist_frequency_spinbox.value(),
            "randomize_strengths": self.randomize_strengths_checkbox.isChecked(),
            "random_artist_minimum": self.random_artist_minimum_spinbox.value(),
            "random_artist_maximum": self.random_artist_maximum_spinbox.value(),
            "random_strength_minimum": self.random_strength_minimum_spinbox.value(),
            "random_strength_maximum": self.random_strength_maximum_spinbox.value(),
        }

    def _entry_state(self):
        state = {}
        for file_path, entry in self.entries.items():
            state[file_path] = {
                "selected": entry.use_artist_checkbox.isChecked(),
                "strength": round(entry.strength_spinner.value(), 2),
            }
        return state

    def import_state(self, state):
        self.saved_entry_state.update(state.get("entries", {}))
        self.enable_artists_checkbox.setChecked(state.get("artists_enabled", False))
        self.random_artists_checkbox.setChecked(state.get("random_artists", False))
        self.random_artist_frequency_spinbox.setValue(state.get("random_artist_frequency", 1))
        self.advance_artists_checkbox.setChecked(state.get("advance_artists", False))
        self.advance_artist_frequency_spinbox.setValue(state.get("advance_artist_frequency", 1))
        if not self.random_artists_checkbox.isChecked() and not self.advance_artists_checkbox.isChecked():
            self.manual_artists_button.setChecked(True)
        self.randomize_strengths_checkbox.setChecked(state.get("randomize_strengths", False))
        self.random_artist_minimum_spinbox.setValue(state.get("random_artist_minimum", 0))
        self.random_artist_maximum_spinbox.setValue(state.get("random_artist_maximum", 1))
        self.random_strength_minimum_spinbox.setValue(state.get("random_strength_minimum", 1.0))
        self.random_strength_maximum_spinbox.setValue(state.get("random_strength_maximum", 1.0))
        for file_path, values in self.saved_entry_state.items():
            entry = self.entries.get(file_path)
            if entry is None:
                continue
            entry.use_artist_checkbox.setChecked(values.get("selected", False))
            entry.strength_spinner.setValue(values.get("strength", 1.0))
        self._apply_artist_mode()

    def export_prompt_entries(self):
        if not self.enable_artists_checkbox.isChecked():
            return []
        prompt_entries = []
        for file_path, values in self.saved_entry_state.items():
            if file_path not in {str(path) for path in self.current_model_files}:
                continue
            if not values.get("selected", False):
                continue
            strength = values.get("strength", 1.0)
            artist_name = f"Artist:{Path(file_path).stem}"
            if strength == 1.0:
                prompt_entries.append(f"{artist_name}::")
            else:
                prompt_entries.append(f"{strength:g}::{artist_name}::")
        return prompt_entries