from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import QSettings, QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from data import datahub
from data.paths import PRESETS_DIR
from windows.confirmation import Confirm
from windows.error import Error


DEFAULT_SIZE = {
    "name": "New Size",
    "image_height": 1024,
    "image_width": 1024,
}


def normalize_size_preset(preset) -> dict[str, object] | None:
    if not isinstance(preset, dict):
        return None

    name = str(preset.get("name", "")).strip()
    try:
        height = int(preset.get("image_height"))
        width = int(preset.get("image_width"))
    except (TypeError, ValueError):
        return None

    if not name or height <= 0 or width <= 0:
        return None
    return {
        "name": name,
        "image_height": height,
        "image_width": width,
    }


def load_size_presets(sizes_path: Path) -> list[dict[str, object]]:
    try:
        loaded = json.loads(Path(sizes_path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(loaded, list):
        return []
    return [
        normalized
        for preset in loaded
        if (normalized := normalize_size_preset(preset)) is not None
    ]


def save_size_presets(sizes_path: Path, sizes: list[dict[str, object]]) -> None:
    sizes_path = Path(sizes_path)
    sizes_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [normalize_size_preset(size) for size in sizes]
    payload = [size for size in payload if size is not None]
    temporary_path = sizes_path.with_suffix(f"{sizes_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(sizes_path)


def validate_size_preset(
    name: str,
    height: int,
    width: int,
    existing_names: set[str],
) -> str | None:
    normalized_name = str(name).strip()
    if not normalized_name:
        return "Size name cannot be empty."
    if normalized_name.casefold() in {item.casefold() for item in existing_names}:
        return "Size name must be unique."
    if int(height) <= 0 or int(width) <= 0:
        return "Height and width must be greater than zero."
    return None


class ManageSizesWindow(QDialog):
    LAST_SIZE_SETTING = "sizes_manager/last_size_name"

    def __init__(
        self,
        parent=None,
        sizes_path=None,
        reload_callback=None,
        settings=None,
    ):
        super().__init__(parent)
        self.setObjectName("sizesManager")
        self.setWindowTitle("Manage Sizes")
        self.resize(520, 300)
        self.setStyleSheet(
            """
            QDialog#sizesManager QFrame,
            QDialog#sizesManager QLabel {
                background: transparent;
                border: none;
            }
            QDialog#sizesManager QFrame#sizesManagerSidebar {
                background: #272833;
                border: 1px solid #444;
            }
            QDialog#sizesManager QFrame#sizesManagerEditor {
                background: #21222C;
                border: 1px solid #555;
            }
            """
        )

        self.sizes_path = Path(sizes_path) if sizes_path is not None else PRESETS_DIR / "sizes.json"
        self.reload_callback = reload_callback if reload_callback is not None else datahub.load_all
        self.settings = settings if settings is not None else QSettings("NAI_UI_2", "NAI_UI_2")
        self.sizes = load_size_presets(self.sizes_path)
        if not self.sizes and sizes_path is None:
            self.sizes = [
                normalized
                for preset in datahub.get_data("sizes", [])
                if (normalized := normalize_size_preset(preset)) is not None
            ]
        self.original_sizes = deepcopy(self.sizes)
        self.current_index = -1
        self.loading_size = False

        self.build_window()
        self.refresh_selector()
        self.select_initial_size()

    def build_window(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("sizesManagerSidebar")
        self.sidebar.setFixedWidth(120)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)
        self.grid.addWidget(self.sidebar, 0, 0)

        sidebar_layout.addWidget(QLabel("Size", self.sidebar))
        self.size_select_combobox = QComboBox(self.sidebar)
        self.size_select_combobox.currentIndexChanged.connect(self.on_size_change)
        sidebar_layout.addWidget(self.size_select_combobox)

        self.new_size_button = QPushButton("New", self.sidebar)
        self.new_size_button.clicked.connect(self.add_size)
        sidebar_layout.addWidget(self.new_size_button)
        self.copy_size_button = QPushButton("Copy", self.sidebar)
        self.copy_size_button.clicked.connect(self.copy_size)
        sidebar_layout.addWidget(self.copy_size_button)
        self.delete_size_button = QPushButton("Delete", self.sidebar)
        self.delete_size_button.clicked.connect(self.delete_size)
        sidebar_layout.addWidget(self.delete_size_button)
        sidebar_layout.addStretch(1)

        action_frame = QFrame(self.sidebar)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.save_button = QPushButton("Save", action_frame)
        self.save_button.clicked.connect(self.save_and_close)
        action_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel", action_frame)
        self.cancel_button.clicked.connect(self.reject)
        action_layout.addWidget(self.cancel_button)
        sidebar_layout.addWidget(action_frame)

        self.editor = QFrame(self)
        self.editor.setObjectName("sizesManagerEditor")
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(12, 12, 12, 12)
        editor_layout.setSpacing(12)
        title_label = QLabel("Size Preset", self.editor)
        editor_layout.addWidget(title_label)

        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        self.name_lineedit = QLineEdit(self.editor)
        self.name_lineedit.setPlaceholderText("Preset name")
        form_layout.addRow("Name", self.name_lineedit)
        self.height_spinbox = QSpinBox(self.editor)
        self.height_spinbox.setRange(1, 16384)
        self.height_spinbox.setSingleStep(64)
        self.height_spinbox.setSuffix(" px")
        form_layout.addRow("Height", self.height_spinbox)
        self.width_spinbox = QSpinBox(self.editor)
        self.width_spinbox.setRange(1, 16384)
        self.width_spinbox.setSingleStep(64)
        self.width_spinbox.setSuffix(" px")
        form_layout.addRow("Width", self.width_spinbox)
        editor_layout.addLayout(form_layout)
        editor_layout.addStretch(1)
        self.grid.addWidget(self.editor, 0, 1)
        self.grid.setColumnStretch(1, 1)

        self.name_lineedit.textChanged.connect(self.store_current_size)
        self.height_spinbox.valueChanged.connect(self.store_current_size)
        self.width_spinbox.valueChanged.connect(self.store_current_size)

    def unique_name(self, base_name: str) -> str:
        existing_names = {str(size["name"]).casefold() for size in self.sizes}
        candidate = base_name
        suffix = 2
        while candidate.casefold() in existing_names:
            candidate = f"{base_name} {suffix}"
            suffix += 1
        return candidate

    def refresh_selector(self, selected_index: int | None = None):
        blocker = QSignalBlocker(self.size_select_combobox)
        self.size_select_combobox.clear()
        self.size_select_combobox.addItems([str(size["name"]) for size in self.sizes])
        if self.sizes:
            target_index = self.current_index if selected_index is None else selected_index
            target_index = min(max(target_index, 0), len(self.sizes) - 1)
            self.size_select_combobox.setCurrentIndex(target_index)
        del blocker

    def select_initial_size(self):
        last_size_name = str(self.settings.value(self.LAST_SIZE_SETTING, "")).strip()
        initial_index = next(
            (
                index
                for index, size in enumerate(self.sizes)
                if str(size["name"]) == last_size_name
            ),
            0 if self.sizes else -1,
        )
        self.select_size(initial_index)

    def on_size_change(self, index: int):
        if self.loading_size:
            return
        self.store_current_size()
        self.select_size(index)

    def select_size(self, index: int):
        self.current_index = index if 0 <= index < len(self.sizes) else -1
        self.loading_size = True
        if self.current_index >= 0:
            size = self.sizes[self.current_index]
            self.name_lineedit.setText(str(size["name"]))
            self.height_spinbox.setValue(int(size["image_height"]))
            self.width_spinbox.setValue(int(size["image_width"]))
            self.size_select_combobox.setCurrentIndex(self.current_index)
        else:
            self.name_lineedit.clear()
            self.height_spinbox.setValue(int(DEFAULT_SIZE["image_height"]))
            self.width_spinbox.setValue(int(DEFAULT_SIZE["image_width"]))
        self.loading_size = False
        has_selection = self.current_index >= 0
        self.editor.setEnabled(has_selection)
        self.copy_size_button.setEnabled(has_selection)
        self.delete_size_button.setEnabled(has_selection)

    def store_current_size(self):
        if self.loading_size or not 0 <= self.current_index < len(self.sizes):
            return
        self.sizes[self.current_index] = {
            "name": self.name_lineedit.text().strip(),
            "image_height": self.height_spinbox.value(),
            "image_width": self.width_spinbox.value(),
        }
        blocker = QSignalBlocker(self.size_select_combobox)
        self.size_select_combobox.setItemText(
            self.current_index,
            self.name_lineedit.text().strip() or "Unnamed Size",
        )
        del blocker

    def add_size(self):
        self.store_current_size()
        size = deepcopy(DEFAULT_SIZE)
        size["name"] = self.unique_name(str(size["name"]))
        self.sizes.append(size)
        self.current_index = len(self.sizes) - 1
        self.refresh_selector(self.current_index)
        self.select_size(self.current_index)
        self.name_lineedit.selectAll()
        self.name_lineedit.setFocus()

    def copy_size(self):
        if not 0 <= self.current_index < len(self.sizes):
            return
        self.store_current_size()
        size = deepcopy(self.sizes[self.current_index])
        size["name"] = self.unique_name(f'{size["name"]} Copy')
        self.sizes.append(size)
        self.current_index = len(self.sizes) - 1
        self.refresh_selector(self.current_index)
        self.select_size(self.current_index)
        self.name_lineedit.selectAll()
        self.name_lineedit.setFocus()

    def delete_size(self):
        if not 0 <= self.current_index < len(self.sizes):
            return
        size_name = str(self.sizes[self.current_index]["name"])
        confirmation = Confirm(
            self,
            "Delete Size",
            f"Delete '{size_name}' when changes are saved?",
            "Delete",
            "Cancel",
        )
        if not confirmation.exec():
            return
        deleted_index = self.current_index
        self.sizes.pop(deleted_index)
        self.current_index = min(deleted_index, len(self.sizes) - 1)
        self.refresh_selector(self.current_index)
        self.select_size(self.current_index)

    def save_and_close(self):
        self.store_current_size()
        existing_names = set()
        for index, size in enumerate(self.sizes):
            validation_error = validate_size_preset(
                str(size.get("name", "")),
                int(size.get("image_height", 0)),
                int(size.get("image_width", 0)),
                existing_names,
            )
            if validation_error:
                self.refresh_selector(index)
                self.select_size(index)
                Error(self, validation_error)
                return
            existing_names.add(str(size["name"]))

        try:
            save_size_presets(self.sizes_path, self.sizes)
            self.reload_callback()
        except OSError as exception:
            Error(self, f"Could not save size presets: {exception}")
            return

        if 0 <= self.current_index < len(self.sizes):
            self.settings.setValue(
                self.LAST_SIZE_SETTING,
                str(self.sizes[self.current_index]["name"]),
            )
        self.accept()