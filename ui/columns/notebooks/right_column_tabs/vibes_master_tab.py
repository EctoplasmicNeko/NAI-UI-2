from pathlib import Path
import random

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout,
)
from PySide6.QtCore import Qt

from data.paths import USER_DIR
from process.frequency import frequency_matches
from ui.columns.notebooks.right_column_tabs.vibe_reference_entry import VibeReferenceEntry


class VibeReferenceMasterTab(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.vibes_root_dir = USER_DIR / "vibes"
        self.vibes_root_dir.mkdir(parents=True, exist_ok=True)
        self.entries = {}
        self.saved_entry_state = {}
        self.current_model_files = set()
        self.build_vibe_reference_master_tab()
        self.refresh_vibe_pages()

    def build_vibe_reference_master_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(3)

        self.enable_vibes_checkbox = QPushButton("Use Vibes", self)
        self.enable_vibes_checkbox.setCheckable(True)
        self.grid.addWidget(self.enable_vibes_checkbox, 0, 0, 1, 3)

        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)

        self.manual_vibes_button = QPushButton("Manual", self)
        self.manual_vibes_button.setCheckable(True)
        self.manual_vibes_button.setChecked(True)

        self.random_vibes_checkbox = QPushButton("Random", self)
        self.random_vibes_checkbox.setCheckable(True)
        self.random_vibes_checkbox.toggled.connect(self._on_random_vibes_toggled)

        self.advance_vibes_checkbox = QPushButton("Advance", self)
        self.advance_vibes_checkbox.setCheckable(True)
        self.advance_vibes_checkbox.toggled.connect(self._on_advance_vibes_toggled)

        self.mode_button_group.addButton(self.manual_vibes_button, 0)
        self.mode_button_group.addButton(self.random_vibes_checkbox, 1)
        self.mode_button_group.addButton(self.advance_vibes_checkbox, 2)
        self.mode_button_group.idToggled.connect(lambda _button_id, checked: self._apply_vibe_mode() if checked else None)

        self.grid.addWidget(self.manual_vibes_button, 1, 0)
        self.grid.addWidget(self.random_vibes_checkbox, 1, 1)
        self.grid.addWidget(self.advance_vibes_checkbox, 1, 2)

        self.normalize_strength_checkbox = QCheckBox("Normalize Strengths", self)
        self.grid.addWidget(self.normalize_strength_checkbox, 2, 0, 1, 3)

        self.random_tools_frame = QFrame(self)
        self.random_tools_grid = QGridLayout(self.random_tools_frame)
        self.random_tools_grid.setContentsMargins(0, 0, 0, 0)
        self.random_tools_grid.setHorizontalSpacing(3)
        self.random_tools_grid.setVerticalSpacing(3)
        self.random_tools_grid.setColumnStretch(0, 1)
        self.random_tools_grid.setColumnStretch(1, 1)
        self.grid.addWidget(self.random_tools_frame, 3, 0, 4, 3)

        self.randomize_strengths_checkbox = QCheckBox("Randomize Strengths", self)
        self.random_tools_grid.addWidget(self.randomize_strengths_checkbox, 0, 0, 1, 2)

        self.random_vibe_frequency_spinbox = QSpinBox(self)
        self.random_vibe_frequency_spinbox.setRange(1, 1000)
        self.random_vibe_frequency_spinbox.setValue(1)
        self.random_vibe_frequency_spinbox.setPrefix("Random Every: ")
        self.random_vibe_frequency_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_vibe_frequency_spinbox, 1, 0, 1, 2)

        self.advance_vibe_frequency_spinbox = QSpinBox(self)
        self.advance_vibe_frequency_spinbox.setRange(1, 1000)
        self.advance_vibe_frequency_spinbox.setValue(1)
        self.advance_vibe_frequency_spinbox.setPrefix("Advance Every: ")
        self.advance_vibe_frequency_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.grid.addWidget(self.advance_vibe_frequency_spinbox, 3, 0, 1, 3)

        self.random_vibe_minimum_spinbox = QSpinBox(self)
        self.random_vibe_minimum_spinbox.setRange(0, 1000)
        self.random_vibe_minimum_spinbox.setPrefix("Min Vibes: ")
        self.random_vibe_minimum_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_vibe_minimum_spinbox, 2, 0)
        self.random_vibe_maximum_spinbox = QSpinBox(self)
        self.random_vibe_maximum_spinbox.setRange(0, 1000)
        self.random_vibe_maximum_spinbox.setValue(1)
        self.random_vibe_maximum_spinbox.setPrefix("Max Vibes: ")
        self.random_vibe_maximum_spinbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.random_tools_grid.addWidget(self.random_vibe_maximum_spinbox, 2, 1)

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
        self.grid.addWidget(self.clear_selections_button, 7, 0, 1, 3)
        self.subfolder_combobox = QComboBox(self)
        self.subfolder_combobox.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.grid.addWidget(self.subfolder_combobox, 8, 0, 1, 3)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_content = QFrame(self.scroll_area)
        self.scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.scroll_area.setWidget(self.scroll_content)
        self.vibes_layout = QVBoxLayout(self.scroll_content)
        self.vibes_layout.setContentsMargins(4, 4, 4, 4)
        self.vibes_layout.setSpacing(8)
        self.grid.addWidget(self.scroll_area, 9, 0, 1, 3)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 1)
        self.grid.setRowStretch(9, 1)
        self.subfolder_combobox.currentIndexChanged.connect(self.refresh_vibe_pages)
        self._apply_vibe_mode()

    def _on_random_vibes_toggled(self, checked):
        if checked:
            self.advance_vibes_checkbox.setChecked(False)

    def _on_advance_vibes_toggled(self, checked):
        if checked:
            self.random_vibes_checkbox.setChecked(False)

    def _apply_vibe_mode(self):
        random_mode = self.random_vibes_checkbox.isChecked()
        advance_mode = self.advance_vibes_checkbox.isChecked()

        for widget in (
            self.random_tools_frame,
        ):
            widget.setVisible(random_mode)
        self.advance_vibe_frequency_spinbox.setVisible(advance_mode)

    def _clear_entries(self):
        while self.vibes_layout.count():
            item = self.vibes_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _vibe_files_by_folder(self):
        folders = {"__root__": [], "__all__": []}
        image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
        root_files = sorted(path for path in self.vibes_root_dir.iterdir() if path.is_file() and path.suffix.lower() in image_suffixes)
        folders["__root__"].extend(root_files)
        folders["__all__"].extend(root_files)
        for subfolder in sorted(path for path in self.vibes_root_dir.iterdir() if path.is_dir()):
            files = sorted(path for path in subfolder.rglob("*") if path.is_file() and path.suffix.lower() in image_suffixes)
            folders[subfolder.name] = files
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

    def refresh_vibe_pages(self):
        self.saved_entry_state.update(self._entry_state())
        self._clear_entries()
        self.entries = {}
        folders = self._vibe_files_by_folder()
        self.current_model_files = set(folders["__all__"])
        self._refresh_subfolder_options(folders)
        image_paths = folders.get(self.subfolder_combobox.currentData(), [])
        if not image_paths:
            placeholder = QLabel("No vibe images found.", self.scroll_content)
            placeholder.setAlignment(Qt.AlignCenter)
            self.vibes_layout.addWidget(placeholder)
            self.vibes_layout.addStretch(1)
            return
        for image_path in image_paths:
            stored = self.saved_entry_state.get(str(image_path), {})
            entry = VibeReferenceEntry(self.scroll_content, image_path, image_path.name)
            entry.use_vibe_checkbox.setChecked(stored.get("selected", False))
            entry.strength_spinner.setValue(stored.get("strength", 1.0))
            entry.info_extracted_spinner.setValue(stored.get("information_extracted", 1.0))
            self.entries[str(image_path)] = entry
            self.vibes_layout.addWidget(entry)
        self.vibes_layout.addStretch(1)

    def collect_images_from_folder(self, folder_path):
        return sorted(path for path in folder_path.rglob("*") if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})

    def _entry_state(self):
        return {
            file_path: {
                "selected": entry.use_vibe_checkbox.isChecked(),
                "strength": round(entry.strength_spinner.value(), 2),
                "information_extracted": round(entry.info_extracted_spinner.value(), 2),
            }
            for file_path, entry in self.entries.items()
        }

    def _randomize_vibes(self):
        available_files = [Path(file_path) for file_path in self.entries]
        if not available_files:
            return
        minimum, maximum = sorted((self.random_vibe_minimum_spinbox.value(), self.random_vibe_maximum_spinbox.value()))
        selected_files = set(random.sample(available_files, min(random.randint(minimum, maximum), len(available_files))))
        low, high = sorted((self.random_strength_minimum_spinbox.value(), self.random_strength_maximum_spinbox.value()))
        for file_path in self.current_model_files:
            values = self.saved_entry_state.setdefault(str(file_path), {})
            values["selected"] = file_path in selected_files
            if file_path in selected_files and self.randomize_strengths_checkbox.isChecked():
                values["strength"] = round(random.uniform(low, high), 2)
        for file_path, entry in self.entries.items():
            values = self.saved_entry_state[file_path]
            entry.use_vibe_checkbox.setChecked(values["selected"])
            entry.strength_spinner.setValue(values.get("strength", 1.0))

    def _advance_vibes(self):
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
            entry.use_vibe_checkbox.setChecked(values["selected"])
            entry.strength_spinner.setValue(values.get("strength", 1.0))

    def clear_all_selections(self):
        for file_path in self.current_model_files:
            self.saved_entry_state.setdefault(str(file_path), {})["selected"] = False
        for entry in self.entries.values():
            entry.use_vibe_checkbox.setChecked(False)

    def export_state(self, randomize_vibes=False, force_random=False, generation_number=1):
        self.saved_entry_state.update(self._entry_state())
        if randomize_vibes and force_random:
            self._randomize_vibes()
        elif randomize_vibes and self.random_vibes_checkbox.isChecked() and frequency_matches(self.random_vibe_frequency_spinbox.value(), generation_number):
            self._randomize_vibes()
        elif randomize_vibes and self.advance_vibes_checkbox.isChecked() and frequency_matches(self.advance_vibe_frequency_spinbox.value(), generation_number):
            self._advance_vibes()
        active_files = {str(path) for path in self.current_model_files}
        selected = [(path, values) for path, values in self.saved_entry_state.items() if path in active_files and values.get("selected", False)]
        return {
            "reference_image_paths": [path for path, _ in selected],
            "reference_strengths": [values.get("strength", 1.0) for _, values in selected],
            "reference_information_extracted": [values.get("information_extracted", 1.0) for _, values in selected],
            "normalize_strength": self.normalize_strength_checkbox.isChecked(),
            "vibe_enabled": self.enable_vibes_checkbox.isChecked(),
            "entries": self.saved_entry_state,
            "random_vibes": self.random_vibes_checkbox.isChecked(),
            "random_vibe_frequency": self.random_vibe_frequency_spinbox.value(),
            "advance_vibes": self.advance_vibes_checkbox.isChecked(),
            "advance_vibe_frequency": self.advance_vibe_frequency_spinbox.value(),
            "randomize_strengths": self.randomize_strengths_checkbox.isChecked(),
            "random_vibe_minimum": self.random_vibe_minimum_spinbox.value(),
            "random_vibe_maximum": self.random_vibe_maximum_spinbox.value(),
            "random_strength_minimum": self.random_strength_minimum_spinbox.value(),
            "random_strength_maximum": self.random_strength_maximum_spinbox.value(),
        }

    def import_state(self, state):
        self.saved_entry_state.update(state.get("entries", {}))
        old_paths = state.get("reference_image_paths", [])
        old_strengths = state.get("reference_strengths", [])
        old_information = state.get("reference_information_extracted", [])
        for index, file_path in enumerate(old_paths):
            values = self.saved_entry_state.setdefault(file_path, {})
            values["selected"] = True
            if index < len(old_strengths):
                values["strength"] = old_strengths[index]
            if index < len(old_information):
                values["information_extracted"] = old_information[index]
        self.enable_vibes_checkbox.setChecked(state.get("vibe_enabled", False))
        self.normalize_strength_checkbox.setChecked(state.get("normalize_strength", False))
        self.random_vibes_checkbox.setChecked(state.get("random_vibes", False))
        self.random_vibe_frequency_spinbox.setValue(state.get("random_vibe_frequency", 1))
        self.advance_vibes_checkbox.setChecked(state.get("advance_vibes", False))
        self.advance_vibe_frequency_spinbox.setValue(state.get("advance_vibe_frequency", 1))
        if not self.random_vibes_checkbox.isChecked() and not self.advance_vibes_checkbox.isChecked():
            self.manual_vibes_button.setChecked(True)
        self.randomize_strengths_checkbox.setChecked(state.get("randomize_strengths", False))
        self.random_vibe_minimum_spinbox.setValue(state.get("random_vibe_minimum", 0))
        self.random_vibe_maximum_spinbox.setValue(state.get("random_vibe_maximum", 1))
        self.random_strength_minimum_spinbox.setValue(state.get("random_strength_minimum", 1.0))
        self.random_strength_maximum_spinbox.setValue(state.get("random_strength_maximum", 1.0))
        for file_path, values in self.saved_entry_state.items():
            entry = self.entries.get(file_path)
            if entry is None:
                continue
            entry.use_vibe_checkbox.setChecked(values.get("selected", False))
            entry.strength_spinner.setValue(values.get("strength", 1.0))
            entry.info_extracted_spinner.setValue(values.get("information_extracted", 1.0))
        self._apply_vibe_mode()
