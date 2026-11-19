from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMessageBox,
)
from PySide6.QtCore import Qt

import json
from pathlib import Path

from data.datahub import get_all_characters
from data.paths import CHARACTERS_DIR
from signaling.refresh_character_lists import refresh_character_lists_signal


class CharacterOrderWindow(QDialog):
    def __init__(self, parent=None, image_cache=None):
        super().__init__(parent)
        self.image_cache = image_cache
        self.setWindowTitle("Reorder Characters")
        self.resize(360, 440)
        self.characters = get_all_characters()
        self.build_window()
        self.populate_character_list()

    def build_window(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info_label = QLabel("Drag the list into the order you want to use for Custom sorting.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.character_list_widget = QListWidget(self)
        self.character_list_widget.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.character_list_widget)

        button_row = QHBoxLayout()
        button_row.setSpacing(6)

        self.move_up_button = QPushButton("Move Up", self)
        self.move_up_button.clicked.connect(lambda: self.move_selected_character(-1))
        button_row.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("Move Down", self)
        self.move_down_button.clicked.connect(lambda: self.move_selected_character(1))
        button_row.addWidget(self.move_down_button)

        button_row.addStretch(1)

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_order)
        button_row.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        layout.addLayout(button_row)

    def populate_character_list(self):
        sorted_characters = sorted(
            self.characters,
            key=lambda character: (
                int(character.get("sort_position", 10**9)),
                str(character.get("nameID", "")).lower(),
            ),
        )

        self.character_list_widget.clear()
        for character in sorted_characters:
            name_id = character.get("nameID", "")
            if not name_id:
                continue
            item = QListWidgetItem(name_id)
            item.setData(Qt.UserRole, name_id)
            self.character_list_widget.addItem(item)

        if self.character_list_widget.count():
            self.character_list_widget.setCurrentRow(0)

    def move_selected_character(self, offset: int):
        current_row = self.character_list_widget.currentRow()
        if current_row < 0:
            return

        target_row = current_row + offset
        if target_row < 0 or target_row >= self.character_list_widget.count():
            return

        current_item = self.character_list_widget.takeItem(current_row)
        self.character_list_widget.insertItem(target_row, current_item)
        self.character_list_widget.setCurrentRow(target_row)

    def save_order(self):
        ordered_names = []
        for index in range(self.character_list_widget.count()):
            item = self.character_list_widget.item(index)
            name_id = item.data(Qt.UserRole)
            if name_id:
                ordered_names.append(name_id)

        if not ordered_names:
            QMessageBox.warning(self, "No characters", "There are no characters to save.")
            return

        for position, name_id in enumerate(ordered_names, start=1):
            for character in self.characters:
                if character.get("nameID") == name_id:
                    character["sort_position"] = position
                    break

        characters_dir = Path(CHARACTERS_DIR)
        characters_dir.mkdir(parents=True, exist_ok=True)

        for character in self.characters:
            name_id = str(character.get("nameID", "")).strip()
            if not name_id:
                continue

            character_file_path = characters_dir / f"{name_id}.json"
            try:
                with character_file_path.open("w", encoding="utf-8") as file_handle:
                    json.dump(character, file_handle, indent=2, ensure_ascii=False)
                    file_handle.write("\n")
            except OSError:
                pass

        refresh_character_lists_signal.reload_character_data.emit()
        refresh_character_lists_signal.refresh_lists.emit()
        self.accept()
