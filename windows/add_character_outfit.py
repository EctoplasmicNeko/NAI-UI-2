import json
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QDialog, QGridLayout, QLineEdit, QLabel, QPushButton, QTextEdit

from data.paths import CHARACTERS_DIR
from data.outfits import normalize_outfit
from process.image_curation import get_image_prompt_slots
from signaling.refresh_character_lists import refresh_character_lists_signal
from windows.error import Error


class AddCharacterOutfitDialog(QDialog):
    FIELD_LABELS = [
        ("name", "Outfit Name"),
        ("role", "Role"),
        ("modifier", "Modifiers"),
        ("upper_garment", "Upper Garment"),
        ("lower_garment", "Lower Garment"),
        ("shoes", "Shoes"),
        ("socks", "Socks"),
        ("head", "Head"),
        ("arms", "Arms"),
        ("other", "Other"),
        ("description", "Description"),
    ]

    def __init__(self, parent, character_names, image_path=None):
        super().__init__(parent)
        self.character_names = list(character_names)
        self.image_path = Path(image_path) if image_path else None
        self.fields = {}
        self.setWindowTitle("Add Character Outfit")
        self.build_dialog()

    def build_dialog(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(5)

        self.grid.addWidget(QLabel("Add Outfit To", self), 0, 0)
        self.character_combobox = QComboBox(self)
        self.character_combobox.addItem("Select character")
        self.character_combobox.addItems(self.character_names)
        self.grid.addWidget(self.character_combobox, 0, 1)

        self.prompt_slots = get_image_prompt_slots(self.image_path)
        self.grid.addWidget(QLabel("Image Metadata Slot", self), 1, 0)
        self.prompt_slot_combobox = QComboBox(self)
        self.prompt_slot_combobox.addItems([slot["label"] for slot in self.prompt_slots])
        self.prompt_slot_combobox.currentIndexChanged.connect(self.load_prompt_slot)
        self.grid.addWidget(self.prompt_slot_combobox, 1, 1)

        self.grid.addWidget(QLabel("Positive Prompt", self), 2, 0)
        self.positive_prompt_view = QTextEdit(self)
        self.positive_prompt_view.setReadOnly(True)
        self.positive_prompt_view.setMinimumHeight(56)
        self.grid.addWidget(self.positive_prompt_view, 2, 1)
        self.grid.addWidget(QLabel("Negative Prompt", self), 3, 0)
        self.negative_prompt_view = QTextEdit(self)
        self.negative_prompt_view.setReadOnly(True)
        self.negative_prompt_view.setMinimumHeight(56)
        self.grid.addWidget(self.negative_prompt_view, 3, 1)
        self.load_prompt_slot(0)

        field_start_row = 4
        for index, (key, label) in enumerate(self.FIELD_LABELS):
            row = field_start_row + index
            self.grid.addWidget(QLabel(label, self), row, 0)
            field = QLineEdit(self)
            self.fields[key] = field
            self.grid.addWidget(field, row, 1)

        self.save_button = QPushButton("Add Outfit", self)
        self.save_button.clicked.connect(self.save_outfit)
        self.grid.addWidget(self.save_button, field_start_row + len(self.FIELD_LABELS), 0)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        self.grid.addWidget(self.cancel_button, field_start_row + len(self.FIELD_LABELS), 1)

    def load_prompt_slot(self, slot_index):
        prompt_slot = self.prompt_slots[slot_index] if 0 <= slot_index < len(self.prompt_slots) else {}
        self.positive_prompt_view.setPlainText(prompt_slot.get("positive_prompt", ""))
        self.negative_prompt_view.setPlainText(prompt_slot.get("negative_prompt", ""))

    def outfit_data(self):
        outfit = {key: field.text().strip() for key, field in self.fields.items()}
        outfit["modifier"] = [item.strip() for item in outfit["modifier"].split(",") if item.strip()]
        return normalize_outfit(outfit)

    def save_outfit(self):
        outfit = self.outfit_data()
        if not outfit["name"]:
            Error(self, "Outfit name cannot be empty.")
            return

        character_name = self.character_combobox.currentText()
        if character_name == "Select character":
            Error(self, "Select the character that should receive this outfit.")
            return

        character_path = CHARACTERS_DIR / f"{character_name}.json"
        try:
            character = json.loads(character_path.read_text(encoding="utf-8"))
            if isinstance(character, list):
                character = character[0] if character else {}
        except (OSError, json.JSONDecodeError):
            Error(self, f"Unable to load character '{character_name}'.")
            return

        if not isinstance(character, dict):
            Error(self, f"Unable to load character '{character_name}'.")
            return

        outfits = character.setdefault("outfits", [])
        if any(isinstance(existing, dict) and existing.get("name") == outfit["name"] for existing in outfits):
            Error(self, "That character already has an outfit with this name.")
            return

        outfits.append(outfit)
        try:
            character_path.write_text(json.dumps(character, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as exc:
            Error(self, f"Unable to save outfit: {exc}")
            return

        refresh_character_lists_signal.reload_character_data.emit()
        refresh_character_lists_signal.refresh_lists.emit()
        self.accept()


def delete_character_outfit(character_name, outfit_name):
    if not character_name or character_name == "None":
        raise ValueError("Select a character before deleting a character outfit.")
    if not outfit_name or outfit_name == "None":
        raise ValueError("Select a character outfit to delete.")

    character_path = CHARACTERS_DIR / f"{character_name}.json"
    try:
        character = json.loads(character_path.read_text(encoding="utf-8"))
        if isinstance(character, list):
            character = character[0] if character else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load character '{character_name}'.") from exc

    if not isinstance(character, dict):
        raise ValueError(f"Unable to load character '{character_name}'.")

    outfits = character.get("outfits", [])
    remaining_outfits = [
        outfit
        for outfit in outfits
        if not (isinstance(outfit, dict) and outfit.get("name") == outfit_name)
    ]
    if len(remaining_outfits) == len(outfits):
        raise ValueError("That outfit does not belong to the selected character.")

    character["outfits"] = remaining_outfits
    try:
        character_path.write_text(json.dumps(character, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to save character outfit changes: {exc}") from exc

    refresh_character_lists_signal.reload_character_data.emit()
    refresh_character_lists_signal.refresh_lists.emit()