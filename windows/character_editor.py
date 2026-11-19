from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from shutil import copy2
import shutil

from PySide6.QtCore import QSettings, Qt, QSignalBlocker, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data.datahub import get_all_characters
from data.mutators import chance_groups_with_active
from data.character_labels import structured_label, label_category, label_value, label_values
from data.outfits import OUTFIT_SLOT_ORDER, empty_outfit_slots, normalize_outfit
from data.label_groups import (
    MANDATORY_LABEL_CATEGORIES,
    group_names as label_group_names,
    load_character_label_data,
    load_character_label_definitions,
)
from data.paths import ALT_PORTRAITS_DIR, CHARACTER_FLUFF_FIELDS_FILE, CHARACTER_MONTHS_FILE, CHARACTER_LABELS_FILE, CHARACTERS_DIR, PORTRAITS_DIR, REFERENCE_DIR
from signaling.refresh_character_lists import refresh_character_lists_signal
from windows.confirmation import Confirm
from windows.error import Error


NEW_CHARACTER_LABEL = "New Character"
GENDER_OPTIONS = ["none specified", "Male", "Female", "Other"]
SPECIES_ICON_OPTIONS = ["None", "Human", "Cat", "Dog", "Fox", "Rabbit", "Squirrel", "Angel", "Demon"]
EDITOR_LIST_WIDTH = 180


class ClickablePortraitLabel(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def normalize_prompt_entry(entry) -> dict[str, object] | None:
    if isinstance(entry, dict):
        tag_text = str(entry.get("tag", "")).strip()
        if not tag_text:
            return None
        try:
            strength_value = float(entry.get("strength", 1.0))
        except (TypeError, ValueError):
            strength_value = 1.0
        return {"tag": tag_text, "strength": strength_value}
    tag_text = str(entry).strip()
    if tag_text:
        return {"tag": tag_text, "strength": 1.0}
    return None


def normalize_prompt_list(prompt_list) -> list[dict[str, object]]:
    if not isinstance(prompt_list, list):
        return []
    normalized_prompts = []
    for entry in prompt_list:
        normalized_entry = normalize_prompt_entry(entry)
        if normalized_entry is not None:
            normalized_prompts.append(normalized_entry)
    return normalized_prompts


class PromptEntryRow(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, prompt=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.tag_lineedit = QLineEdit(self)
        self.tag_lineedit.setPlaceholderText("Tag")
        self.layout.addWidget(self.tag_lineedit, 1)
        self.strength_spinbox = QDoubleSpinBox(self)
        self.strength_spinbox.setDecimals(2)
        self.strength_spinbox.setSingleStep(0.05)
        self.strength_spinbox.setRange(-10.0, 10.0)
        self.strength_spinbox.setValue(1.0)
        self.strength_spinbox.setPrefix("Strength: ")
        self.layout.addWidget(self.strength_spinbox)
        self.remove_button = QPushButton("Remove", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.layout.addWidget(self.remove_button)
        self.tag_lineedit.textChanged.connect(self.changed)
        self.strength_spinbox.valueChanged.connect(self.changed)
        self.set_prompt(prompt or {"tag": "", "strength": 1.0})

    def set_prompt(self, prompt):
        normalized_prompt = normalize_prompt_entry(prompt) or {"tag": "", "strength": 1.0}
        blockers = [QSignalBlocker(self.tag_lineedit), QSignalBlocker(self.strength_spinbox)]
        self.tag_lineedit.setText(str(normalized_prompt.get("tag", "")))
        self.strength_spinbox.setValue(float(normalized_prompt.get("strength", 1.0)))
        del blockers

    def prompt(self) -> dict[str, object] | None:
        tag_text = self.tag_lineedit.text().strip()
        if not tag_text:
            return None
        return {"tag": tag_text, "strength": self.strength_spinbox.value()}


class PromptListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget(self.scroll_area)
        self.rows_layout = QVBoxLayout(self.scroll_content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.rows_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area, 1)
        self.add_button = QPushButton("Add Tag", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)

    def add_empty_row(self):
        self.add_row()
        self._emit_changed()

    def add_row(self, prompt=None):
        row = PromptEntryRow(self.scroll_content, prompt)
        row.changed.connect(self._emit_changed)
        row.remove_requested.connect(self.remove_row)
        self.rows.append(row)
        self.rows_layout.insertWidget(max(0, self.rows_layout.count() - 1), row)
        return row

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._emit_changed()

    def clear_rows(self):
        for row in list(self.rows):
            self.rows.remove(row)
            self.rows_layout.removeWidget(row)
            row.deleteLater()

    def set_prompts(self, prompts):
        self.loading = True
        self.clear_rows()
        for prompt in normalize_prompt_list(prompts):
            self.add_row(prompt)
        if not self.rows:
            self.add_row()
        self.loading = False

    def prompts(self) -> list[dict[str, object]]:
        return [prompt for row in self.rows if (prompt := row.prompt()) is not None]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class ChanceAlternativeEditor(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, alternative=None, is_default_none=False):
        super().__init__(parent)
        self.setObjectName("chanceAlternativeCard")
        self.loading = False
        self.rows = []
        self.is_default_none = is_default_none
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("Chance", self))
        self.chance_spinbox = QDoubleSpinBox(self)
        self.chance_spinbox.setDecimals(2)
        self.chance_spinbox.setRange(0.0, 1000000.0)
        self.chance_spinbox.setValue(1.0)
        self.chance_spinbox.valueChanged.connect(self._emit_changed)
        header_layout.addWidget(self.chance_spinbox)
        header_layout.addStretch(1)
        self.remove_button = QPushButton("Remove Alternative", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.remove_button.setVisible(not self.is_default_none)
        header_layout.addWidget(self.remove_button)
        self.layout.addLayout(header_layout)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(12)
        self.layout.addLayout(self.rows_layout)
        self.layout.addStretch(1)
        self.add_button = QPushButton("Add Tag", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.add_button.setVisible(not self.is_default_none)
        self.layout.addWidget(self.add_button)
        self.set_alternative(alternative)

    def _create_row(self, prompt, removable=True):
        row = PromptEntryRow(self, prompt)
        row.changed.connect(self._emit_changed)
        row.remove_requested.connect(self.remove_row)
        row.remove_button.setEnabled(removable)
        if not removable:
            row.tag_lineedit.setReadOnly(True)
            row.strength_spinbox.setEnabled(False)
            row.remove_button.setVisible(False)
            row.setMaximumHeight(28)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        return row

    def add_empty_row(self):
        if self.is_default_none or not self.add_button.isEnabled():
            return
        self._create_row({"tag": "", "strength": 1.0})
        self._emit_changed()

    def _update_add_button(self):
        self.add_button.setEnabled(not self.is_default_none)

    def remove_row(self, row):
        if row not in self.rows or self.is_default_none:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._update_add_button()
        self._emit_changed()

    def clear_rows(self):
        for row in list(self.rows):
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()

    def set_alternative(self, alternative):
        self.loading = True
        self.clear_rows()
        alternative = alternative or {}
        self.chance_spinbox.setValue(float(alternative.get("chance", 1.0)))
        tags = alternative.get("tags", [])
        if self.is_default_none:
            self._create_row({"tag": "none", "strength": 1.0}, removable=False)
        elif isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, dict) and str(tag.get("tag", "")).strip().lower() != "none":
                    self._create_row(tag)
        if not self.rows:
            self._create_row({"tag": "", "strength": 1.0})
        self._update_add_button()
        self.loading = False

    def alternative(self):
        if self.is_default_none:
            return {
                "chance": self.chance_spinbox.value(),
                "tags": [{"tag": "none", "strength": 1.0}],
            }
        tags = [
            tag
            for row in self.rows
            if (tag := row.prompt()) is not None
            and str(tag.get("tag", "")).strip().lower() != "none"
        ]
        return {"chance": self.chance_spinbox.value(), "tags": tags}

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class ChanceGroupEditor(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, group=None):
        super().__init__(parent)
        self.loading = False
        self.alternatives = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel("Group Name", self))
        self.name_lineedit = QLineEdit(self)
        self.name_lineedit.textChanged.connect(self._emit_changed)
        header_layout.addWidget(self.name_lineedit, 1)
        self.remove_button = QPushButton("Remove Group", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        header_layout.addWidget(self.remove_button)
        self.layout.addLayout(header_layout)

        self.alternatives_layout = QVBoxLayout()
        self.alternatives_layout.setContentsMargins(0, 0, 0, 0)
        self.alternatives_layout.setSpacing(4)
        self.layout.addLayout(self.alternatives_layout)
        self.add_button = QPushButton("Add Alternative", self)
        self.add_button.clicked.connect(self.add_empty_alternative)
        self.layout.addWidget(self.add_button)
        self.layout.addStretch(1)
        self.set_group(group or {})

    def add_empty_alternative(self):
        self.add_alternative()
        self._emit_changed()

    def add_alternative(self, alternative=None, is_default_none=False):
        editor = ChanceAlternativeEditor(self, alternative or {}, is_default_none=is_default_none)
        editor.changed.connect(self._emit_changed)
        editor.remove_requested.connect(self.remove_alternative)
        self.alternatives.append(editor)
        self.alternatives_layout.addWidget(editor)
        return editor

    def remove_alternative(self, editor):
        if editor not in self.alternatives or editor.is_default_none or len(self.alternatives) <= 1:
            return
        self.alternatives.remove(editor)
        self.alternatives_layout.removeWidget(editor)
        editor.deleteLater()
        self._emit_changed()

    def clear_alternatives(self):
        for editor in list(self.alternatives):
            self.alternatives_layout.removeWidget(editor)
            editor.deleteLater()
        self.alternatives.clear()

    @staticmethod
    def _is_none_alternative(alternative):
        if not isinstance(alternative, dict):
            return False
        tags = alternative.get("tags")
        return bool(tags) and isinstance(tags, list) and all(
            isinstance(tag, dict)
            and str(tag.get("tag", "")).strip().lower() == "none"
            for tag in tags
        )

    def set_group(self, group):
        self.loading = True
        self.active = group.get("active", True)
        self.clear_alternatives()
        self.name_lineedit.setText(str(group.get("name", "")))
        alternatives = group.get("alternatives", [])
        alternatives = alternatives if isinstance(alternatives, list) else []
        default_alternative = next(
            (
                alternative
                for alternative in alternatives
                if self._is_none_alternative(alternative)
            ),
            {"chance": 1.0, "tags": [{"tag": "none", "strength": 1.0}]},
        )
        self.add_alternative(default_alternative, is_default_none=True)
        for alternative in alternatives:
            if not isinstance(alternative, dict) or alternative is default_alternative:
                continue
            tags = alternative.get("tags", [])
            if self._is_none_alternative(alternative):
                continue
            cleaned_alternative = dict(alternative)
            cleaned_alternative["tags"] = [
                tag
                for tag in tags
                if isinstance(tag, dict)
                and str(tag.get("tag", "")).strip().lower() != "none"
            ] if isinstance(tags, list) else []
            self.add_alternative(cleaned_alternative)
        self.loading = False

    def group(self):
        return {
            "name": self.name_lineedit.text().strip(),
            "active": self.active,
            "alternatives": [editor.alternative() for editor in self.alternatives],
        }

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class ChanceTagListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.groups = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.group_list = QListWidget(self)
        self.group_list.setFixedWidth(EDITOR_LIST_WIDTH)
        self.group_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 3px 10px;
            }
            """
        )
        self.group_list.currentRowChanged.connect(self.select_group)
        self.content_layout.addWidget(self.group_list)
        self.group_stack = QStackedWidget(self)
        self.content_layout.addWidget(self.group_stack, 1)
        self.layout.addLayout(self.content_layout, 1)
        self.add_button = QPushButton("Add Chance Group", self)
        self.add_button.clicked.connect(self.add_empty_group)
        self.layout.addWidget(self.add_button)

    def add_empty_group(self):
        editor = self.add_group({"name": "", "alternatives": []})
        self.group_list.setCurrentRow(self.groups.index(editor))
        self._emit_changed()

    def add_group(self, group):
        editor = ChanceGroupEditor(self.group_stack, group)
        editor.changed.connect(self._emit_changed)
        editor.name_lineedit.textChanged.connect(self.refresh_group_names)
        editor.remove_requested.connect(self.remove_group)
        self.groups.append(editor)
        self.group_stack.addWidget(editor)
        self.group_list.addItem(str(group.get("name", "") or f"Chance {len(self.groups)}"))
        return editor

    def select_group(self, index):
        if 0 <= index < len(self.groups):
            self.group_stack.setCurrentIndex(index)

    def refresh_group_names(self):
        for index, editor in enumerate(self.groups):
            name = editor.name_lineedit.text().strip() or f"Chance {index + 1}"
            self.group_list.item(index).setText(name)

    def remove_group(self, editor):
        if editor not in self.groups:
            return
        index = self.groups.index(editor)
        self.groups.pop(index)
        self.group_list.takeItem(index)
        self.group_stack.removeWidget(editor)
        editor.deleteLater()
        if self.groups:
            self.group_list.setCurrentRow(min(index, len(self.groups) - 1))
        self._emit_changed()

    def clear_groups(self):
        for editor in list(self.groups):
            self.group_stack.removeWidget(editor)
            editor.deleteLater()
        self.groups.clear()
        self.group_list.clear()

    def set_groups(self, groups):
        self.loading = True
        self.clear_groups()
        for group in chance_groups_with_active(groups) or []:
            if isinstance(group, dict):
                self.add_group(group)
        self.loading = False
        if self.groups:
            self.group_list.setCurrentRow(0)
        self.refresh_group_names()

    def groups_payload(self):
        names = set()
        payload = []
        for index, editor in enumerate(self.groups, 1):
            group = editor.group()
            name = group["name"] or f"Chance {index}"
            base_name = name
            suffix = 2
            while name in names:
                name = f"{base_name} ({suffix})"
                suffix += 1
            names.add(name)
            group["name"] = name
            payload.append(group)
        return payload

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


def _association_text_list(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


class PlainTagListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, tags=None):
        super().__init__(parent)
        self.rows = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.layout.addLayout(self.rows_layout)
        self.layout.addStretch(1)
        self.add_button = QPushButton("Add Tag", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)
        self.set_tags(tags or [])

    def add_empty_row(self):
        self.add_row()
        self._emit_changed()

    def add_row(self, tag=""):
        row = QFrame(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        lineedit = QLineEdit(row)
        lineedit.setPlaceholderText("Tag")
        lineedit.setText(str(tag))
        lineedit.textChanged.connect(self._emit_changed)
        row_layout.addWidget(lineedit, 1)
        remove_button = QPushButton("Remove", row)
        remove_button.clicked.connect(lambda: self.remove_row(row))
        row_layout.addWidget(remove_button)
        row.tag_lineedit = lineedit
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        return row

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._emit_changed()

    def clear_rows(self):
        for row in list(self.rows):
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()

    def set_tags(self, tags):
        self.loading = True
        self.clear_rows()
        for tag in _association_text_list(tags):
            self.add_row(tag)
        self.loading = False

    def tags(self):
        return [row.tag_lineedit.text().strip() for row in self.rows if row.tag_lineedit.text().strip()]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class TriggerGroupEditor(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, tags=None):
        super().__init__(parent)
        self.setObjectName("triggerGroupCard")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(4)
        self.tag_editor = PlainTagListEditor(self, tags)
        self.tag_editor.changed.connect(self.changed.emit)
        self.layout.addWidget(self.tag_editor)
        self.remove_button = QPushButton("Remove Trigger Group", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.layout.addWidget(self.remove_button)

    def tags(self):
        return self.tag_editor.tags()


class GroupedTriggerEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, groups=None):
        super().__init__(parent)
        self.groups = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.group_list = QListWidget(self)
        self.group_list.setFixedWidth(EDITOR_LIST_WIDTH)
        self.group_list.currentRowChanged.connect(self.select_group)
        self.content_layout.addWidget(self.group_list)
        self.group_stack = QStackedWidget(self)
        self.content_layout.addWidget(self.group_stack, 1)
        self.layout.addLayout(self.content_layout, 1)
        self.add_button = QPushButton("Add Trigger Group", self)
        self.add_button.clicked.connect(self.add_empty_group)
        self.layout.addWidget(self.add_button)
        self.set_groups(groups or [])

    def add_empty_group(self):
        editor = self.add_group([])
        self.group_list.setCurrentRow(self.groups.index(editor))
        self._emit_changed()

    def add_group(self, tags):
        editor = TriggerGroupEditor(self.group_stack, tags)
        editor.changed.connect(self._emit_changed)
        editor.remove_requested.connect(self.remove_group)
        self.groups.append(editor)
        self.group_stack.addWidget(editor)
        self.group_list.addItem(f"Group {len(self.groups)}")
        return editor

    def select_group(self, index):
        if 0 <= index < len(self.groups):
            self.group_stack.setCurrentIndex(index)

    def remove_group(self, editor):
        if editor not in self.groups:
            return
        index = self.groups.index(editor)
        self.groups.pop(index)
        self.group_list.takeItem(index)
        self.group_stack.removeWidget(editor)
        editor.deleteLater()
        for group_index in range(self.group_list.count()):
            self.group_list.item(group_index).setText(f"Group {group_index + 1}")
        if self.groups:
            self.group_list.setCurrentRow(min(index, len(self.groups) - 1))
        self._emit_changed()

    def clear_groups(self):
        for editor in list(self.groups):
            self.group_stack.removeWidget(editor)
            editor.deleteLater()
        self.groups.clear()
        self.group_list.clear()

    def set_groups(self, groups):
        self.loading = True
        self.clear_groups()
        if isinstance(groups, list):
            for group in groups:
                if isinstance(group, list):
                    self.add_group(group)
        self.loading = False
        if self.groups:
            self.group_list.setCurrentRow(0)

    def trigger_groups(self):
        return [tags for editor in self.groups if (tags := editor.tags())]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class QuoteListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget(self.scroll_area)
        self.rows_layout = QVBoxLayout(self.scroll_content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.rows_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area, 1)
        self.add_button = QPushButton("Add Quote", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)

    def add_empty_row(self):
        self.add_row()
        self._emit_changed()

    def add_row(self, quote=""):
        row = QFrame(self.scroll_content)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        lineedit = QLineEdit(row)
        lineedit.setPlaceholderText("Quote")
        lineedit.setText(str(quote))
        lineedit.textChanged.connect(self._emit_changed)
        row_layout.addWidget(lineedit, 1)
        remove_button = QPushButton("Remove", row)
        remove_button.clicked.connect(lambda: self.remove_row(row))
        row_layout.addWidget(remove_button)
        row.quote_lineedit = lineedit
        self.rows.append(row)
        self.rows_layout.insertWidget(max(0, self.rows_layout.count() - 1), row)
        return row

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._emit_changed()

    def clear_rows(self):
        for row in list(self.rows):
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()

    def set_quotes(self, quotes):
        self.loading = True
        self.clear_rows()
        for quote in quotes or []:
            if str(quote).strip():
                self.add_row(quote)
        self.loading = False

    def quotes(self):
        return [row.quote_lineedit.text().strip() for row in self.rows if row.quote_lineedit.text().strip()]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


def load_character_fluff_fields(fields_path: Path) -> list[dict[str, object]]:
    if not fields_path.is_file():
        return []
    try:
        fields = json.loads(fields_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(fields, list):
        return []
    normalized_fields = []
    seen_keys = set()
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key", "")).strip()
        label = str(field.get("label", key)).strip() or key
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        normalized_fields.append({
            "key": key,
            "label": label,
            "multiline": bool(field.get("multiline", False)),
            "type": str(field.get("type", "text")),
        })
    return normalized_fields


def load_character_months(months_path: Path) -> list[str]:
    if not months_path.is_file():
        return []
    try:
        months = json.loads(months_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(months, list):
        return []
    return [str(month).strip() for month in months if str(month).strip()]


class CharacterPoolEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, characters=None, image_cache=None):
        super().__init__(parent)
        self.setObjectName("characterPoolEditor")
        self.setFrameShape(QFrame.NoFrame)
        self.characters = sorted(characters or [], key=lambda character: str(character.get("nameID", "")).lower())
        self.image_cache = image_cache or {}
        self.rows = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("characterPoolScrollArea")
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setFixedHeight(190)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(
            """
            QScrollArea#characterPoolScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 10px;
                background: transparent;
                margin: 0 4px 2px 4px;
            }
            QScrollBar::handle:horizontal {
                min-width: 24px;
                border-radius: 4px;
                background: rgba(159, 168, 218, 0.5);
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(159, 168, 218, 0.8);
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: none;
            }
            """
        )
        self.scroll_content = QWidget(self.scroll_area)
        self.scroll_content.setObjectName("characterPoolScrollContent")
        self.rows_layout = QHBoxLayout(self.scroll_content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(12)
        self.rows_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)
        self.add_button = QPushButton("Add Character", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)

    def _character_ids(self):
        return [str(character.get("nameID", "")) for character in self.characters if character.get("nameID")]

    def _portrait_path(self, character_id):
        key = str(character_id).lower()
        cached_path = self.image_cache.get("portraits", {}).get(key)
        if cached_path and Path(cached_path).is_file():
            return Path(cached_path)
        try:
            return next((path for path in PORTRAITS_DIR.glob(f"{key}.*") if path.is_file()), None)
        except OSError:
            return None

    def add_empty_row(self):
        self.add_row("")
        self._emit_changed()

    def add_row(self, character_id):
        row = QFrame(self)
        row.setObjectName("relationshipCard")
        row.setFrameShape(QFrame.NoFrame)
        row.setFixedWidth(120)
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        relationship_lineedit = QLineEdit(row)
        relationship_lineedit.setPlaceholderText("Relationship")
        relationship_lineedit.textChanged.connect(self._emit_changed)
        row_layout.addWidget(relationship_lineedit)
        combo = QComboBox(row)
        combo.addItem("None", "")
        for character_id_option in self._character_ids():
            combo.addItem(character_id_option, character_id_option)
        combo.setCurrentText(str(character_id or ""))
        combo.currentIndexChanged.connect(lambda: self._update_portrait(row))
        combo.currentIndexChanged.connect(self._emit_changed)
        portrait = QLabel(row)
        portrait.setAlignment(Qt.AlignCenter)
        portrait.setFixedSize(96, 96)
        row_layout.addWidget(portrait, 0, Qt.AlignCenter)
        row_layout.addWidget(combo)
        remove_button = QPushButton("Remove", row)
        remove_button.clicked.connect(lambda: self.remove_row(row))
        row_layout.addWidget(remove_button)
        row.combo = combo
        row.portrait = portrait
        row.relationship_lineedit = relationship_lineedit
        self.rows.append(row)
        self.rows_layout.insertWidget(max(0, self.rows_layout.count() - 1), row)
        self._update_scroll_content_size()
        self._update_portrait(row)
        return row

    def _update_scroll_content_size(self):
        card_width = 120
        spacing = 12
        content_width = max(1, len(self.rows) * card_width + max(0, len(self.rows) - 1) * spacing)
        self.scroll_content.setFixedSize(content_width, 178)

    def _update_portrait(self, row):
        path = self._portrait_path(row.combo.currentData())
        placeholder = self.image_cache.get("images", {}).get("character_portraits", {}).get("fluff_placeholder", "")
        pixmap = QPixmap(str(path or placeholder)) if (path or placeholder) else QPixmap()
        if pixmap.isNull():
            row.portrait.clear()
            row.portrait.setText("No Image")
            return
        row.portrait.setPixmap(pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._update_scroll_content_size()
        self._emit_changed()

    def clear_rows(self):
        for row in list(self.rows):
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()
        self._update_scroll_content_size()

    def set_values(self, values):
        self.loading = True
        self.clear_rows()
        for value in values or []:
            if isinstance(value, dict):
                character_id = value.get("character", value.get("nameID", ""))
                relationship = value.get("relationship", "")
            else:
                character_id = value
                relationship = ""
            if str(character_id).strip():
                row = self.add_row(character_id)
                row.relationship_lineedit.setText(str(relationship or ""))
        self.loading = False

    def values(self):
        return [
            {
                "character": row.combo.currentData(),
                "relationship": row.relationship_lineedit.text().strip(),
            }
            for row in self.rows
            if row.combo.currentData()
        ]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


def normalize_lore_entries(value) -> list[dict[str, str]]:
    entries = []
    for entry in value if isinstance(value, list) else []:
        if isinstance(entry, dict):
            entries.append({"title": str(entry.get("title") or "").strip(), "text": str(entry.get("text") or "")})
        elif str(entry).strip():
            entries.append({"title": "", "text": str(entry)})
    return entries


class LoreEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []
        self.current_index = None
        self.loading = False
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(8)

        # Left: the list of entries and the add/delete buttons, matching the other editors.
        list_layout = QVBoxLayout()
        list_layout.setSpacing(6)
        self.entry_list = QListWidget(self)
        self.entry_list.setFixedWidth(EDITOR_LIST_WIDTH)
        self.entry_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 3px 6px;
                margin: 1px 4px;
            }
            """
        )
        self.entry_list.currentRowChanged.connect(self.on_entry_selected)
        list_layout.addWidget(self.entry_list, 1)
        self.add_entry_button = QPushButton("Add Entry", self)
        self.add_entry_button.clicked.connect(self.add_entry)
        list_layout.addWidget(self.add_entry_button)
        self.delete_entry_button = QPushButton("Delete Entry", self)
        self.delete_entry_button.clicked.connect(self.delete_current_entry)
        list_layout.addWidget(self.delete_entry_button)
        self.layout.addLayout(list_layout)

        # Right: the selected entry's title and a large free-text area.
        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        self.title_lineedit = QLineEdit(self)
        self.title_lineedit.setPlaceholderText("Entry title")
        self.title_lineedit.textChanged.connect(self.store_current_entry)
        text_layout.addWidget(self.title_lineedit)
        self.text_edit = QTextEdit(self)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.textChanged.connect(self.store_current_entry)
        text_layout.addWidget(self.text_edit, 1)
        self.layout.addLayout(text_layout, 1)
        self.select_entry(None)

    def set_entries(self, entries):
        self.loading = True
        self.entries = normalize_lore_entries(entries)
        self.refresh_entry_list()
        self.loading = False
        self.select_entry(0 if self.entries else None)

    def values(self) -> list[dict[str, str]]:
        return normalize_lore_entries(self.entries)

    def refresh_entry_list(self):
        blocker = QSignalBlocker(self.entry_list)
        self.entry_list.clear()
        for entry in self.entries:
            self.entry_list.addItem(entry["title"] or "Untitled Entry")
        del blocker

    def on_entry_selected(self, row):
        if self.loading:
            return
        self.select_entry(row if row >= 0 else None)

    def select_entry(self, index):
        self.current_index = index if index is not None and 0 <= index < len(self.entries) else None
        has_entry = self.current_index is not None
        self.loading = True
        blockers = [QSignalBlocker(self.title_lineedit), QSignalBlocker(self.text_edit)]
        if has_entry:
            entry = self.entries[self.current_index]
            self.title_lineedit.setText(entry["title"])
            self.text_edit.setPlainText(entry["text"])
            self.entry_list.setCurrentRow(self.current_index)
            self.text_edit.setPlaceholderText("")
        else:
            self.title_lineedit.clear()
            self.text_edit.clear()
            self.text_edit.setPlaceholderText("Add a lore entry to start writing.")
        del blockers
        self.title_lineedit.setEnabled(has_entry)
        self.text_edit.setReadOnly(not has_entry)
        self.delete_entry_button.setEnabled(has_entry)
        self.loading = False

    def store_current_entry(self):
        if self.loading or self.current_index is None:
            return
        entry = {"title": self.title_lineedit.text().strip(), "text": self.text_edit.toPlainText()}
        self.entries[self.current_index] = entry
        item = self.entry_list.item(self.current_index)
        if item is not None:
            item.setText(entry["title"] or "Untitled Entry")
        self.changed.emit()

    def add_entry(self):
        self.entries.append({"title": "New Entry", "text": ""})
        self.refresh_entry_list()
        self.select_entry(len(self.entries) - 1)
        # Ready to type the new entry's name straight away.
        self.title_lineedit.setFocus()
        self.title_lineedit.selectAll()
        self.changed.emit()

    def delete_current_entry(self):
        if self.current_index is None:
            return
        entry = self.entries[self.current_index]
        if entry["text"].strip():
            confirmation = Confirm(self, "Delete Lore Entry", f"Delete '{entry['title'] or 'Untitled Entry'}' and its text?", "Delete", "Cancel")
            if not confirmation.exec():
                return
        deleted_index = self.current_index
        del self.entries[deleted_index]
        self.refresh_entry_list()
        self.select_entry(min(deleted_index, len(self.entries) - 1) if self.entries else None)
        self.changed.emit()


class CharacterFluffEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, fields=None, characters=None, image_cache=None, month_names=None):
        super().__init__(parent)
        self.fields = fields or []
        self.widgets = {}
        self.field_frames = {}
        self.characters = characters or []
        self.image_cache = image_cache or {}
        self.month_names = month_names or []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(8)
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("fluffSubtabs")
        self.tabs.setUsesScrollButtons(False)
        self.tabs.setStyleSheet(
            """
            QTabWidget#fluffSubtabs::pane {
                border: none;
            }
            """
        )
        self.relationships_tab = QScrollArea(self.tabs)
        self.relationships_tab.setWidgetResizable(True)
        self.relationships_tab.setFrameShape(QFrame.NoFrame)
        self.relationships_content = QWidget(self.relationships_tab)
        self.relationships_layout = QVBoxLayout(self.relationships_content)
        self.relationships_layout.setContentsMargins(4, 4, 4, 4)
        self.relationships_layout.setSpacing(8)
        self.relationships_tab.setWidget(self.relationships_content)
        self.other_tab = QScrollArea(self.tabs)
        self.other_tab.setWidgetResizable(True)
        self.other_tab.setFrameShape(QFrame.NoFrame)
        self.other_content = QWidget(self.other_tab)
        self.other_layout = QVBoxLayout(self.other_content)
        self.other_layout.setContentsMargins(4, 4, 4, 4)
        self.other_layout.setSpacing(8)
        self.other_tab.setWidget(self.other_content)
        self.tabs.addTab(self.relationships_tab, "Relationships")
        self.tabs.addTab(self.other_tab, "Other")
        self.lore_editor = LoreEditor(self.tabs)
        self.lore_editor.changed.connect(self._emit_changed)
        self.tabs.addTab(self.lore_editor, "Lore")
        self.layout.addWidget(self.tabs)
        for field in self.fields:
            key = field["key"]
            field_type = field.get("type", "text")
            field_tab = self.relationships_content if field_type == "character_pool" else self.other_content
            field_layout_container = self.relationships_layout if field_type == "character_pool" else self.other_layout
            field_frame = QFrame(field_tab)
            field_frame.setObjectName("fluffFieldFrame")
            field_frame.setStyleSheet(
                """
                QFrame#fluffFieldFrame {
                    background: #21222C;
                    border: 1px solid #444;
                }
                QFrame#characterPoolEditor,
                QFrame#relationshipCard {
                    background: transparent;
                    border: none;
                }
                QLabel {
                    background: transparent;
                    border: none;
                }
                """
            )
            field_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            field_layout = QVBoxLayout(field_frame)
            field_layout.setContentsMargins(4, 4, 4, 4)
            field_layout.setSpacing(4)
            field_layout.addWidget(QLabel(field["label"], field_frame))
            if field_type == "birthday":
                widget = self._build_birthday_widget(field_frame)
            elif field_type == "character_pool":
                widget = CharacterPoolEditor(field_frame, self.characters, self.image_cache)
                widget.changed.connect(self._emit_changed)
            elif field.get("multiline"):
                widget = QTextEdit(field_frame)
                widget.setFixedHeight(80)
                widget.textChanged.connect(self._emit_changed)
            else:
                widget = QLineEdit(field_frame)
                widget.textChanged.connect(self._emit_changed)
            self.widgets[key] = widget
            self.field_frames[key] = field_frame
            field_layout.addWidget(widget)
            field_layout_container.addWidget(field_frame)
        self.relationships_layout.addStretch(1)
        self.other_layout.addStretch(1)

    def _build_birthday_widget(self, parent):
        widget = QWidget(parent)
        birthday_layout = QHBoxLayout(widget)
        birthday_layout.setContentsMargins(0, 0, 0, 0)
        birthday_layout.setSpacing(6)
        for label in ["Day", "Year"]:
            birthday_layout.addWidget(QLabel(label, widget))
            spinbox = QSpinBox(widget)
            spinbox.setRange(0, 2147483647)
            spinbox.setFixedWidth(82)
            spinbox.valueChanged.connect(self._emit_changed)
            birthday_layout.addWidget(spinbox)
            setattr(widget, f"{label.lower()}_spinbox", spinbox)
        birthday_layout.insertWidget(2, QLabel("Month", widget))
        widget.month_combobox = QComboBox(widget)
        widget.month_combobox.addItem("None", 0)
        for index, month_name in enumerate(self.month_names, 1):
            widget.month_combobox.addItem(month_name, index)
        widget.month_combobox.currentIndexChanged.connect(self._emit_changed)
        birthday_layout.insertWidget(3, widget.month_combobox)
        birthday_layout.addWidget(QLabel("Era", widget))
        widget.era_lineedit = QLineEdit(widget)
        widget.era_lineedit.setPlaceholderText("Era")
        widget.era_lineedit.textChanged.connect(self._emit_changed)
        birthday_layout.addWidget(widget.era_lineedit)
        birthday_layout.addStretch(1)
        return widget

    def set_values(self, character):
        self.loading = True
        for field in self.fields:
            widget = self.widgets[field["key"]]
            value = character.get(field["key"], "")
            if field.get("type") == "birthday":
                birthday = value if isinstance(value, dict) else {}
                widget.era_lineedit.setText(str(birthday.get("era", "") or ""))
                month_value = birthday.get("month", 0) or 0
                if isinstance(month_value, str) and not month_value.isdigit():
                    month_value = next((index for index, name in enumerate(self.month_names, 1) if name.lower() == month_value.lower()), 0)
                widget.month_combobox.setCurrentIndex(widget.month_combobox.findData(int(month_value)))
                widget.day_spinbox.setValue(int(birthday.get("day", 0) or 0))
                widget.year_spinbox.setValue(int(birthday.get("year", 0) or 0))
            elif field.get("type") == "character_pool":
                widget.set_values(value if isinstance(value, list) else [])
            elif isinstance(widget, QTextEdit):
                value = str(value or "")
                widget.setPlainText(value)
            else:
                widget.setText(value)
        self.lore_editor.set_entries(character.get("lore"))
        self.loading = False

    def values(self):
        result = {"lore": self.lore_editor.values()}
        for field in self.fields:
            widget = self.widgets[field["key"]]
            if field.get("type") == "birthday":
                result[field["key"]] = {
                    "day": widget.day_spinbox.value(),
                    "month": widget.month_combobox.currentData(),
                    "year": widget.year_spinbox.value(),
                    "era": widget.era_lineedit.text().strip(),
                }
            elif field.get("type") == "character_pool":
                result[field["key"]] = widget.values()
            else:
                result[field["key"]] = widget.toPlainText() if isinstance(widget, QTextEdit) else widget.text()
        return result

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class TagAssociationEditor(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, association=None):
        super().__init__(parent)
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)

        self.name_lineedit = QLineEdit(self)
        self.name_lineedit.setPlaceholderText("Association name")
        self.name_lineedit.textChanged.connect(self._emit_changed)
        self.layout.addWidget(QLabel("Name", self))
        self.layout.addWidget(self.name_lineedit)
        self.trigger_editor = GroupedTriggerEditor(self)
        self.trigger_absent_checkbox = QCheckBox("Trigger when groups are not satisfied", self)
        self.trigger_absent_checkbox.setToolTip(
            "Activate unless every non-empty trigger group has at least one matching positive tag. "
            "With one trigger tag, activate only when that tag is absent."
        )
        self.trigger_absent_checkbox.toggled.connect(self._emit_changed)
        self.blacklist_editor = PlainTagListEditor(self)
        self.remove_editor = PlainTagListEditor(self)
        for label, widget in [
            ("Triggers", self.trigger_editor),
            ("Blacklist", self.blacklist_editor),
            ("Remove", self.remove_editor),
        ]:
            self.layout.addWidget(QLabel(label, self))
            self.layout.addWidget(widget)
            widget.changed.connect(self._emit_changed)
            if widget is self.trigger_editor:
                self.layout.addWidget(self.trigger_absent_checkbox)

        self.layout.addWidget(QLabel("Inject", self))
        self.inject_editor = PromptListEditor(self)
        self.layout.addWidget(self.inject_editor, 1)
        self.remove_triggers_checkbox = QCheckBox("Remove triggering tags", self)
        self.remove_triggers_checkbox.setToolTip(
            "Remove trigger tags for presence-based rules. Has no effect when trigger groups are not satisfied."
        )
        self.remove_triggers_checkbox.toggled.connect(self._emit_changed)
        self.layout.addWidget(self.remove_triggers_checkbox)
        self.negative_injection_checkbox = QCheckBox("Negative Injections", self)
        self.negative_injection_checkbox.setToolTip("Inject into the negative prompt instead of the positive prompt when triggered.")
        self.negative_injection_checkbox.toggled.connect(self._emit_changed)
        self.layout.addWidget(self.negative_injection_checkbox)
        self.remove_button = QPushButton("Remove Association", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.layout.addWidget(self.remove_button)
        self.set_association(association or {})

    def set_association(self, association):
        self.loading = True
        self.active = association.get("active", True)
        self.name_lineedit.setText(str(association.get("name", "")))
        self.trigger_editor.set_groups(association.get("trigger", []))
        self.trigger_absent_checkbox.setChecked(bool(association.get("trigger_absent", False)))
        self.blacklist_editor.set_tags(association.get("blacklist", []))
        self.remove_editor.set_tags(association.get("remove", []))
        self.inject_editor.set_prompts(association.get("inject", []))
        self.remove_triggers_checkbox.setChecked(bool(association.get("remove_triggers", association.get("remove_trigger", False))))
        self.negative_injection_checkbox.setChecked(bool(association.get("negative_injection", False)))
        self.loading = False

    def association(self):
        return {
            "name": self.name_lineedit.text().strip(),
            "active": self.active,
            "trigger": self.trigger_editor.trigger_groups(),
            "trigger_absent": self.trigger_absent_checkbox.isChecked(),
            "inject": self.inject_editor.prompts(),
            "blacklist": self.blacklist_editor.tags(),
            "remove": self.remove_editor.tags(),
            "remove_triggers": self.remove_triggers_checkbox.isChecked(),
            "negative_injection": self.negative_injection_checkbox.isChecked(),
        }

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class TagAssociationListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.editors = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.content_layout = QHBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.association_list = QListWidget(self)
        self.association_list.setFixedWidth(EDITOR_LIST_WIDTH)
        self.association_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 3px 8px;
                margin: 2px 4px;
            }
            """
        )
        self.association_list.currentRowChanged.connect(self.select_association)
        self.content_layout.addWidget(self.association_list)
        self.association_stack = QStackedWidget(self)
        self.content_layout.addWidget(self.association_stack, 1)
        self.layout.addLayout(self.content_layout, 1)
        self.add_button = QPushButton("Add Association", self)
        self.add_button.clicked.connect(self.add_empty_association)
        self.layout.addWidget(self.add_button)

    def add_empty_association(self):
        editor = self.add_association({"name": "", "trigger": [], "inject": [], "blacklist": [], "remove": []})
        self.association_list.setCurrentRow(self.editors.index(editor))
        self._emit_changed()

    def add_association(self, association):
        editor = TagAssociationEditor(self.association_stack, association)
        editor.changed.connect(self._emit_changed)
        editor.name_lineedit.textChanged.connect(self.refresh_association_names)
        editor.remove_requested.connect(self.remove_association)
        self.editors.append(editor)
        self.association_stack.addWidget(editor)
        self.association_list.addItem(self._association_label(association))
        return editor

    def _association_label(self, association):
        return str(association.get("name", "")).strip() or "New Association"

    def refresh_association_names(self):
        for index, editor in enumerate(self.editors):
            name = editor.name_lineedit.text().strip() or f"Association {index + 1}"
            self.association_list.item(index).setText(name)

    def select_association(self, index):
        if 0 <= index < len(self.editors):
            self.association_stack.setCurrentIndex(index)

    def remove_association(self, editor):
        if editor not in self.editors:
            return
        index = self.editors.index(editor)
        self.editors.pop(index)
        self.association_list.takeItem(index)
        self.association_stack.removeWidget(editor)
        editor.deleteLater()
        if self.editors:
            self.association_list.setCurrentRow(min(index, len(self.editors) - 1))
        self._emit_changed()

    def clear_associations(self):
        for editor in list(self.editors):
            self.association_stack.removeWidget(editor)
            editor.deleteLater()
        self.editors.clear()
        self.association_list.clear()

    def set_associations(self, associations):
        self.loading = True
        self.clear_associations()
        for association in associations or []:
            if isinstance(association, dict):
                self.add_association(association)
        self.loading = False
        if self.editors:
            self.association_list.setCurrentRow(0)

    def associations_payload(self):
        payload = []
        for index, editor in enumerate(self.editors):
            association = editor.association()
            if not association["trigger"]:
                continue
            name = association["name"] or f"Association {index + 1}"
            base_name = name
            suffix = 2
            existing_names = {entry.get("name") for entry in payload}
            while name in existing_names:
                name = f"{base_name} ({suffix})"
                suffix += 1
            association["name"] = name
            self.association_list.item(index).setText(self._association_label(association))
            payload.append(association)
        return payload

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


def normalize_quick_weight_entry(entry) -> dict[str, object] | None:
    if isinstance(entry, dict):
        tag_text = str(entry.get("tag", "")).strip()
        if not tag_text:
            return None
        try:
            value = float(entry.get("value", 0))
        except (TypeError, ValueError):
            value = 0.0
        try:
            minimum = float(entry.get("min", -3))
        except (TypeError, ValueError):
            minimum = -3.0
        try:
            maximum = float(entry.get("max", 3))
        except (TypeError, ValueError):
            maximum = 3.0
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        value = max(minimum, min(maximum, value))
        return {
            "max": maximum,
            "min": minimum,
            "negative": bool(entry.get("negative", False)),
            "tag": tag_text,
            "value": value,
        }
    tag_text = str(entry).strip()
    if not tag_text:
        return None
    return {"max": 3, "min": -3, "negative": False, "tag": tag_text, "value": 0}


def normalize_quick_weight_list(quick_weights) -> list[dict[str, object]]:
    if not isinstance(quick_weights, list):
        return []
    normalized_weights = []
    for entry in quick_weights:
        normalized_entry = normalize_quick_weight_entry(entry)
        if normalized_entry is not None:
            normalized_weights.append(normalized_entry)
    return normalized_weights


class LabelGroupSelector(QFrame):
    """Multi-select control listing every label of one group for a character."""

    changed = Signal()
    remove_requested = Signal(str)

    LABEL_COLUMNS = 3

    def __init__(self, parent=None, category="", labels=None, removable=True, exclusive=False):
        super().__init__(parent)
        self.category = str(category or "")
        self.exclusive = exclusive
        self.loading = False
        self.label_checkboxes = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.label_frame = QFrame(self)
        self.label_layout = QGridLayout(self.label_frame)
        self.label_layout.setContentsMargins(0, 0, 0, 0)
        self.label_layout.setSpacing(4)
        layout.addWidget(self.label_frame, 1)
        self.remove_button = QPushButton("Remove Group", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self.category))
        self.remove_button.setVisible(removable)
        layout.addWidget(self.remove_button, 0, Qt.AlignTop)
        self.set_available_labels(labels or [])

    def set_available_labels(self, labels):
        selected = set(self.selected_labels())
        self.loading = True
        while self.label_layout.count():
            item = self.label_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.label_checkboxes = {}
        sort_priority_order = {"main": 0, "supporting": 1, "minor": 2}
        if self.category.casefold() == "sort priority":
            sort_key = lambda label: (
                sort_priority_order.get(str(label).casefold(), len(sort_priority_order)),
                str(label).casefold(),
            )
        else:
            sort_key = lambda label: str(label).casefold()
        for index, label in enumerate(sorted(labels, key=sort_key)):
            checkbox = QCheckBox(label, self.label_frame)
            checkbox.setChecked(label in selected)
            checkbox.toggled.connect(self._on_label_toggled)
            self.label_checkboxes[label] = checkbox
            self.label_layout.addWidget(checkbox, index // self.LABEL_COLUMNS, index % self.LABEL_COLUMNS)
        for column in range(self.LABEL_COLUMNS):
            self.label_layout.setColumnStretch(column, 1)
        self.loading = False

    def set_selected_labels(self, labels):
        selected = {str(label) for label in labels or []}
        self.loading = True
        for label, checkbox in self.label_checkboxes.items():
            checkbox.setChecked(label in selected)
        self.loading = False

    def selected_labels(self) -> list[str]:
        return [label for label, checkbox in self.label_checkboxes.items() if checkbox.isChecked()]

    def _on_label_toggled(self, _checked):
        if self.exclusive and not self.loading:
            sender = self.sender()
            self.loading = True
            for checkbox in self.label_checkboxes.values():
                if checkbox is not sender:
                    checkbox.setChecked(False)
            self.loading = False
        if not self.loading:
            self.changed.emit()


class CharacterLabelEditor(QFrame):
    """Per character label selection.

    Label groups themselves are managed in the All Character Settings window, so
    this editor only chooses which of the existing labels apply to a character and
    which groups are shown for it.
    """

    changed = Signal()

    def __init__(self, parent=None, label_definitions=None, labels_path=None, group_settings=None):
        super().__init__(parent)
        self.loading = False
        self.label_definitions = label_definitions or []
        self.labels_path = Path(labels_path) if labels_path else None
        self.group_settings = dict(group_settings or {})
        self.category_selectors = {}
        self.group_selectors = {}
        self.active_categories = []
        self._refresh_known_labels()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        self.add_group_frame = QFrame(self)
        add_group_layout = QHBoxLayout(self.add_group_frame)
        add_group_layout.setContentsMargins(0, 0, 0, 0)
        add_group_layout.setSpacing(4)
        self.add_group_combobox = QComboBox(self.add_group_frame)
        add_group_layout.addWidget(self.add_group_combobox, 1)
        self.add_group_button = QPushButton("Add Group To Character", self.add_group_frame)
        self.add_group_button.clicked.connect(self.add_selected_group)
        add_group_layout.addWidget(self.add_group_button)
        self.layout.addWidget(self.add_group_frame)

        self.category_scroll_area = QScrollArea(self)
        self.category_scroll_area.setWidgetResizable(True)
        self.category_scroll_area.setFrameShape(QFrame.NoFrame)
        self.category_frame = QFrame(self.category_scroll_area)
        self.category_layout = QGridLayout(self.category_frame)
        self.category_layout.setContentsMargins(8, 0, 8, 0)
        self.category_layout.setHorizontalSpacing(6)
        self.category_layout.setVerticalSpacing(10)
        self.category_layout.setColumnMinimumWidth(0, 110)
        self.category_layout.setRowStretch(999, 1)
        self.category_scroll_area.setWidget(self.category_frame)
        self.layout.addWidget(self.category_scroll_area, 2)
        # Keep the backing widget hidden so existing Additional labels are not
        # discarded when characters are edited after this field is removed.
        self.additional_labels_textedit = QTextEdit(self)
        self.additional_labels_textedit.setVisible(False)
        self.additional_labels_textedit.textChanged.connect(self._emit_changed)
        self._build_category_controls()

    def set_label_definitions(self, label_definitions, group_settings=None):
        selected_labels = self.labels()
        active_categories = list(self.active_categories)
        self.label_definitions = label_definitions or []
        if group_settings is not None:
            self.group_settings = dict(group_settings)
        self._rebuild_category_controls(selected_labels, active_categories)

    def reload_label_definitions(self):
        if self.labels_path is None:
            return
        definitions, group_settings = load_character_label_data(self.labels_path)
        self.set_label_definitions(definitions, group_settings)

    def _refresh_known_labels(self):
        self.known_labels = {definition["label"] for definition in self.label_definitions}
        self.labels_by_category = {}
        for definition in self.label_definitions:
            self.labels_by_category.setdefault(definition["category"], []).append(definition["label"])
        self.all_categories = label_group_names(self.label_definitions, self.group_settings)

    def _clear_category_controls(self):
        while self.category_layout.count():
            item = self.category_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.category_selectors = {}
        self.group_selectors = {}

    def _rebuild_category_controls(self, selected_labels=None, active_categories=None):
        if selected_labels is None:
            selected_labels = self.labels()
        if active_categories is None:
            active_categories = list(self.active_categories)
        self._clear_category_controls()
        self._refresh_known_labels()
        self._build_category_controls()
        self.set_labels(selected_labels, active_categories)

    def _build_category_controls(self):
        row = 0
        has_group = False

        def add_group_divider():
            nonlocal row, has_group
            if not has_group:
                return
            divider = QFrame(self.category_frame)
            divider.setFrameShape(QFrame.HLine)
            divider.setFrameShadow(QFrame.Sunken)
            divider.setFixedHeight(2)
            divider.setStyleSheet("QFrame { color: #555; background: #555; border: none; }")
            self.category_layout.addWidget(divider, row, 0, 1, 2)
            row += 1

        for category in self.all_categories:
            if category not in MANDATORY_LABEL_CATEGORIES:
                continue
            add_group_divider()
            category_label = QLabel(
                f'{category} <span style="color: #e53935;">*</span>',
                self.category_frame,
            )
            category_label.setTextFormat(Qt.RichText)
            self.category_layout.addWidget(category_label, row, 0)
            selector = LabelGroupSelector(
                self.category_frame,
                category,
                self.labels_by_category.get(category, []),
                removable=False,
                exclusive=True,
            )
            selector.changed.connect(self._emit_changed)
            self.category_selectors[category] = selector
            self.category_layout.addWidget(selector, row, 1)
            row += 1
            has_group = True
        for category in self.active_categories:
            if category in MANDATORY_LABEL_CATEGORIES or category not in self.all_categories:
                continue
            add_group_divider()
            self.category_layout.addWidget(QLabel(category, self.category_frame), row, 0, Qt.AlignTop)
            selector = LabelGroupSelector(self.category_frame, category, self.labels_by_category.get(category, []))
            selector.changed.connect(self._emit_changed)
            selector.remove_requested.connect(self.remove_group_from_character)
            self.group_selectors[category] = selector
            self.category_layout.addWidget(selector, row, 1)
            row += 1
            has_group = True
        self.category_layout.setColumnStretch(1, 1)
        self._refresh_add_group_combobox()

    def _refresh_add_group_combobox(self):
        available = [
            category
            for category in self.all_categories
            if category not in MANDATORY_LABEL_CATEGORIES and category not in self.active_categories
        ]
        blocker = QSignalBlocker(self.add_group_combobox)
        self.add_group_combobox.clear()
        self.add_group_combobox.addItems(available)
        del blocker
        self.add_group_frame.setEnabled(bool(available))

    def available_groups(self) -> list[str]:
        return [self.add_group_combobox.itemText(index) for index in range(self.add_group_combobox.count())]

    def add_selected_group(self):
        category = self.add_group_combobox.currentText().strip()
        if not category:
            return
        self.add_group_to_character(category)

    def add_group_to_character(self, category):
        category = str(category or "").strip()
        if not category:
            Error(self, "Label group name cannot be empty.")
            return
        if category in MANDATORY_LABEL_CATEGORIES:
            return
        if category not in self.all_categories:
            Error(self, "That label group does not exist.")
            return
        if category in self.active_categories:
            return
        selected_labels = self.labels()
        self.active_categories.append(category)
        self._rebuild_category_controls(selected_labels, list(self.active_categories))
        self._emit_changed()

    def remove_group_from_character(self, category):
        category = str(category or "").strip()
        if category not in self.active_categories:
            return
        selected_labels = [entry for entry in self.labels() if label_category(entry) != category]
        self.active_categories = [name for name in self.active_categories if name != category]
        self._rebuild_category_controls(selected_labels, list(self.active_categories))
        self._emit_changed()

    def set_labels(self, labels, active_groups=None):
        raw_labels = [label for label in labels if isinstance(label, dict)] if isinstance(labels, list) else []
        labelled_categories = []
        for label_entry in raw_labels:
            category = label_category(label_entry, "")
            if (
                category
                and category not in MANDATORY_LABEL_CATEGORIES
                and category in self.all_categories
                and category not in labelled_categories
            ):
                labelled_categories.append(category)
        requested_groups = []
        if isinstance(active_groups, list):
            for category in active_groups:
                category = str(category or "").strip()
                if (
                    category
                    and category not in MANDATORY_LABEL_CATEGORIES
                    and category in self.all_categories
                    and category not in requested_groups
                ):
                    requested_groups.append(category)
        active_categories = requested_groups + [
            category for category in labelled_categories if category not in requested_groups
        ]
        if active_categories != self.active_categories:
            self.active_categories = active_categories
            self._clear_category_controls()
            self._refresh_known_labels()
            self._build_category_controls()

        self.loading = True
        selected_labels = set()
        for category, selector in self.category_selectors.items():
            group_labels = [
                label_value(label_entry)
                for label_entry in raw_labels
                if label_category(label_entry, "") == category and label_value(label_entry)
            ]
            if not group_labels and selector.label_checkboxes:
                group_labels = [next(iter(selector.label_checkboxes))]
            selector.set_selected_labels(group_labels)
            selected_labels.update(group_labels)
        for category, selector in self.group_selectors.items():
            group_labels = [
                label_value(label_entry)
                for label_entry in raw_labels
                if label_category(label_entry, "") == category and label_value(label_entry)
            ]
            selector.set_selected_labels(group_labels)
            selected_labels.update(group_labels)
        additional_labels = []
        for label_entry in raw_labels:
            value = label_value(label_entry)
            category = label_category(label_entry, "Additional")
            if not value or value in selected_labels:
                continue
            if value not in self.known_labels or category == "Additional":
                additional_labels.append(value)
        self.additional_labels_textedit.setPlainText(", ".join(additional_labels))
        self.loading = False
        self._refresh_add_group_combobox()

    def labels(self) -> list[dict[str, str]]:
        labels = []
        seen = set()
        for category, selector in self.category_selectors.items():
            for label in selector.selected_labels():
                key = (category, label)
                if key in seen:
                    continue
                structured = structured_label(category, label)
                if structured is not None:
                    labels.append(structured)
                    seen.add(key)
        for category, selector in self.group_selectors.items():
            for label in selector.selected_labels():
                key = (category, label)
                if key in seen:
                    continue
                structured = structured_label(category, label)
                if structured is not None:
                    labels.append(structured)
                    seen.add(key)
        for label in parse_tag_text(self.additional_labels_textedit.toPlainText()):
            key = ("Additional", label)
            if key not in seen:
                structured = structured_label("Additional", label)
                if structured is not None:
                    labels.append(structured)
                    seen.add(key)
        return labels

    def active_groups(self) -> list[str]:
        return list(self.active_categories)

    def label_values(self) -> list[str]:
        return label_values(self.labels())

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class QuickWeightEntryRow(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, quick_weight=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.tag_lineedit = QLineEdit(self)
        self.tag_lineedit.setPlaceholderText("Tag")
        self.layout.addWidget(self.tag_lineedit, 1)
        self.value_spinbox = QDoubleSpinBox(self)
        self.value_spinbox.setDecimals(1)
        self.value_spinbox.setSingleStep(0.1)
        self.value_spinbox.setRange(-10.0, 10.0)
        self.value_spinbox.setPrefix("Value: ")
        self.layout.addWidget(self.value_spinbox)
        self.min_spinbox = QDoubleSpinBox(self)
        self.min_spinbox.setDecimals(1)
        self.min_spinbox.setSingleStep(0.1)
        self.min_spinbox.setRange(-10.0, 10.0)
        self.min_spinbox.setPrefix("Min: ")
        self.layout.addWidget(self.min_spinbox)
        self.max_spinbox = QDoubleSpinBox(self)
        self.max_spinbox.setDecimals(1)
        self.max_spinbox.setSingleStep(0.1)
        self.max_spinbox.setRange(-10.0, 10.0)
        self.max_spinbox.setPrefix("Max: ")
        self.layout.addWidget(self.max_spinbox)
        self.negative_checkbox = QCheckBox("Negative", self)
        self.layout.addWidget(self.negative_checkbox)
        self.remove_button = QPushButton("Remove", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.layout.addWidget(self.remove_button)
        self.tag_lineedit.textChanged.connect(self.changed)
        self.value_spinbox.valueChanged.connect(self.changed)
        self.min_spinbox.valueChanged.connect(self.changed)
        self.max_spinbox.valueChanged.connect(self.changed)
        self.negative_checkbox.toggled.connect(self.changed)
        self.set_quick_weight(quick_weight or {"tag": "", "value": 0, "min": -3, "max": 3, "negative": False})

    def set_quick_weight(self, quick_weight):
        normalized_weight = normalize_quick_weight_entry(quick_weight) or {"tag": "", "value": 0, "min": -3, "max": 3, "negative": False}
        controls = [self.tag_lineedit, self.value_spinbox, self.min_spinbox, self.max_spinbox, self.negative_checkbox]
        blockers = [QSignalBlocker(control) for control in controls]
        self.tag_lineedit.setText(str(normalized_weight.get("tag", "")))
        self.min_spinbox.setValue(float(normalized_weight.get("min", -3)))
        self.max_spinbox.setValue(float(normalized_weight.get("max", 3)))
        self.value_spinbox.setValue(float(normalized_weight.get("value", 0)))
        self.negative_checkbox.setChecked(bool(normalized_weight.get("negative", False)))
        del blockers

    def quick_weight(self) -> dict[str, object] | None:
        tag_text = self.tag_lineedit.text().strip()
        if not tag_text:
            return None
        minimum = self.min_spinbox.value()
        maximum = self.max_spinbox.value()
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        value = max(minimum, min(maximum, self.value_spinbox.value()))
        return {
            "max": maximum,
            "min": minimum,
            "negative": self.negative_checkbox.isChecked(),
            "tag": tag_text,
            "value": value,
        }


class QuickWeightListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.loading = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget(self.scroll_area)
        self.rows_layout = QVBoxLayout(self.scroll_content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.rows_layout.addStretch(1)
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area, 1)
        self.add_button = QPushButton("Add Quick Weight", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)

    def add_empty_row(self):
        self.add_row()
        self._emit_changed()

    def add_row(self, quick_weight=None):
        row = QuickWeightEntryRow(self.scroll_content, quick_weight)
        row.changed.connect(self._emit_changed)
        row.remove_requested.connect(self.remove_row)
        self.rows.append(row)
        self.rows_layout.insertWidget(max(0, self.rows_layout.count() - 1), row)
        return row

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._emit_changed()

    def clear_rows(self):
        for row in list(self.rows):
            self.rows.remove(row)
            self.rows_layout.removeWidget(row)
            row.deleteLater()

    def set_quick_weights(self, quick_weights):
        self.loading = True
        self.clear_rows()
        for quick_weight in normalize_quick_weight_list(quick_weights):
            self.add_row(quick_weight)
        if not self.rows:
            self.add_row()
        self.loading = False

    def quick_weights(self) -> list[dict[str, object]]:
        return [quick_weight for row in self.rows if (quick_weight := row.quick_weight()) is not None]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class CopyOutfitDialog(QDialog):
    CHARACTER_MODE = "character"
    LABEL_MODE = "label"

    def __init__(self, parent, outfit_name, character_ids, character_labels=None, source_character_id=None):
        """character_labels maps character id -> list of (category, label) pairs, for the bulk "copy to label" mode."""
        super().__init__(parent)
        self.setWindowTitle("Copy Outfit To")
        self.character_labels = character_labels or {}
        self.source_character_id = source_character_id
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)

        self.grid.addWidget(QLabel(f"Copy '{outfit_name}' to:", self), 0, 0, 1, 2)
        self.character_mode_button = QPushButton("One Character", self)
        self.label_mode_button = QPushButton("Everyone With Label", self)
        self.mode_button_group = QButtonGroup(self)
        for column, button in enumerate([self.character_mode_button, self.label_mode_button]):
            button.setCheckable(True)
            self.mode_button_group.addButton(button)
            self.grid.addWidget(button, 1, column)
        self.character_mode_button.setChecked(True)
        self.mode_button_group.buttonToggled.connect(lambda *_: self.update_mode())

        self.character_combobox = QComboBox(self)
        self.character_combobox.addItems(list(character_ids))
        self.grid.addWidget(self.character_combobox, 2, 0, 1, 2)

        self.label_combobox = QComboBox(self)
        all_labels = sorted({pair for pairs in self.character_labels.values() for pair in pairs}, key=lambda pair: (pair[0].lower(), pair[1].lower()))
        for category, label in all_labels:
            self.label_combobox.addItem(f"{category}: {label}", (category, label))
        self.label_combobox.currentIndexChanged.connect(lambda *_: self.update_label_matches())
        self.grid.addWidget(self.label_combobox, 3, 0, 1, 2)
        self.label_match_label = QLabel(self)
        self.grid.addWidget(self.label_match_label, 4, 0, 1, 2)
        # A scrolling list rather than a wrapped label, so broad labels matching dozens of characters still fit.
        self.label_match_list = QListWidget(self)
        self.label_match_list.setFixedHeight(150)
        self.label_match_list.setSelectionMode(QListWidget.NoSelection)
        self.label_match_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 1px 6px;
                margin: 0px 4px;
            }
            """
        )
        self.grid.addWidget(self.label_match_list, 5, 0, 1, 2)
        self.label_mode_button.setEnabled(bool(all_labels))

        self.ok_button = QPushButton("Ok", self)
        self.ok_button.clicked.connect(self.accept)
        self.grid.addWidget(self.ok_button, 6, 0)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.reject)
        self.grid.addWidget(self.cancel_button, 6, 1)
        self.setMinimumWidth(320)
        self.update_mode()

    def copy_mode(self) -> str:
        return self.LABEL_MODE if self.label_mode_button.isChecked() else self.CHARACTER_MODE

    def update_mode(self):
        label_mode = self.copy_mode() == self.LABEL_MODE
        self.character_combobox.setVisible(not label_mode)
        self.label_combobox.setVisible(label_mode)
        self.label_match_label.setVisible(label_mode)
        self.label_match_list.setVisible(label_mode)
        self.update_label_matches()
        # Shrink back to the compact single-character layout, or grow to fit the label list.
        self.adjustSize()

    def update_label_matches(self):
        target_ids = self.label_target_ids()
        self.label_match_list.clear()
        self.label_match_list.addItems(target_ids)
        if self.copy_mode() == self.LABEL_MODE:
            self.ok_button.setEnabled(bool(target_ids))
            self.label_match_label.setText(
                f"Copies to {len(target_ids)} character(s):"
                if target_ids
                else "No other characters have this label."
            )
        else:
            self.ok_button.setEnabled(self.character_combobox.count() > 0)

    def selected_character_id(self) -> str:
        return self.character_combobox.currentText()

    def selected_label(self):
        return self.label_combobox.currentData()

    def label_target_ids(self) -> list[str]:
        selected_label = self.selected_label()
        if selected_label is None:
            return []
        # The source character already has the outfit, so it is never a bulk target.
        return [
            character_id
            for character_id, pairs in self.character_labels.items()
            if character_id != self.source_character_id and tuple(selected_label) in pairs
        ]


def unique_outfit_name(name: str, outfits) -> str:
    existing_names = {str(outfit.get("name", "")).strip() for outfit in outfits or [] if isinstance(outfit, dict)}
    while name in existing_names:
        name = f"{name}_copy"
    return name


class OutfitEditor(QFrame):
    changed = Signal()
    copy_to_requested = Signal()

    SLOT_LABELS = {
        "upper_garment": "Upper",
        "lower_garment": "Lower",
        "shoes": "Shoes",
        "socks": "Socks",
        "head": "Head",
        "arms": "Arms",
        "other": "Other",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.outfits = []
        self.current_outfit_index = None
        self.loading = False
        self.slot_editors = {}
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)

        self.outfit_list = QListWidget(self)
        self.outfit_list.setFixedWidth(EDITOR_LIST_WIDTH)
        self.outfit_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 3px 6px;
                margin: 1px 4px;
            }
            """
        )
        self.outfit_list.currentRowChanged.connect(self.on_outfit_selected)
        self.layout.addWidget(self.outfit_list, 0, 0, 4, 1)

        self.add_outfit_button = QPushButton("Add Outfit", self)
        self.add_outfit_button.clicked.connect(self.add_outfit)
        self.layout.addWidget(self.add_outfit_button, 4, 0)
        self.delete_outfit_button = QPushButton("Delete Outfit", self)
        self.delete_outfit_button.clicked.connect(self.delete_current_outfit)
        self.layout.addWidget(self.delete_outfit_button, 5, 0)
        self.copy_to_button = QPushButton("Copy Outfit", self)
        self.copy_to_button.clicked.connect(self.copy_to_requested.emit)
        self.layout.addWidget(self.copy_to_button, 6, 0)

        self.detail_frame = QFrame(self)
        self.detail_layout = QGridLayout(self.detail_frame)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_layout.setSpacing(6)
        self.name_lineedit = QLineEdit(self.detail_frame)
        self.role_lineedit = QLineEdit(self.detail_frame)
        self.modifier_lineedit = QLineEdit(self.detail_frame)
        self.description_textedit = QTextEdit(self.detail_frame)
        self.description_textedit.setMaximumHeight(80)
        self.description_textedit.setFixedHeight(72)
        detail_rows = [
            ("Name", self.name_lineedit),
            ("Role", self.role_lineedit),
            ("Modifiers", self.modifier_lineedit),
            ("Description", self.description_textedit),
        ]
        for row, (label, widget) in enumerate(detail_rows):
            self.detail_layout.addWidget(QLabel(label, self.detail_frame), row, 0)
            self.detail_layout.addWidget(widget, row, 1)
        self.detail_layout.setColumnStretch(1, 1)
        self.layout.addWidget(self.detail_frame, 0, 1)

        self.slot_tabs = QTabWidget(self)
        self.slot_tabs.setObjectName("outfitSlotTabs")
        self.slot_tabs.setStyleSheet(
            """
            QTabWidget#outfitSlotTabs::pane {
                border: none;
            }
            """
        )
        for slot in OUTFIT_SLOT_ORDER:
            slot_tab = QWidget(self.slot_tabs)
            slot_layout = QGridLayout(slot_tab)
            slot_layout.setContentsMargins(8, 8, 8, 8)
            slot_layout.setSpacing(6)

            slot_prompt_tabs = QTabWidget(slot_tab)
            slot_prompt_tabs.setObjectName("outfitPromptTabs")
            slot_prompt_tabs.setUsesScrollButtons(False)
            slot_prompt_tabs.setStyleSheet(
                """
                QTabWidget#outfitPromptTabs::pane {
                    border: none;
                }
                """
            )
            positive_editor = PromptListEditor(slot_prompt_tabs)
            negative_editor = PromptListEditor(slot_prompt_tabs)
            slot_prompt_tabs.addTab(positive_editor, "Positive")
            slot_prompt_tabs.addTab(negative_editor, "Negative")

            slot_layout.addWidget(slot_prompt_tabs, 0, 0, 1, 2)
            slot_layout.setColumnStretch(0, 1)
            slot_layout.setColumnStretch(1, 1)
            self.slot_tabs.addTab(slot_tab, self.SLOT_LABELS.get(slot, slot))
            self.slot_editors[slot] = {"positive": positive_editor, "negative": negative_editor}
            positive_editor.changed.connect(self.store_current_outfit)
            negative_editor.changed.connect(self.store_current_outfit)
        self.layout.addWidget(self.slot_tabs, 1, 1, 6, 1)
        self.layout.setColumnStretch(1, 1)
        self.layout.setRowStretch(3, 1)

        self.name_lineedit.textChanged.connect(self.store_current_outfit)
        self.role_lineedit.textChanged.connect(self.store_current_outfit)
        self.modifier_lineedit.textChanged.connect(self.store_current_outfit)
        self.description_textedit.textChanged.connect(self.store_current_outfit)

    def set_outfits(self, outfits):
        self.loading = True
        self.outfits = [normalize_outfit(outfit) for outfit in outfits or [] if isinstance(outfit, dict)]
        self.refresh_outfit_list()
        self.loading = False
        self.select_outfit(0 if self.outfits else None)

    def outfits_payload(self) -> list[dict]:
        self._store_current_outfit(emit_changed=False)
        return [normalize_outfit(outfit) for outfit in self.outfits]

    def current_outfit_payload(self) -> dict | None:
        if self.current_outfit_index is None:
            return None
        self._store_current_outfit(emit_changed=False)
        return normalize_outfit(deepcopy(self.outfits[self.current_outfit_index]))

    def refresh_outfit_list(self):
        blocker = QSignalBlocker(self.outfit_list)
        self.outfit_list.clear()
        for outfit in self.outfits:
            self.outfit_list.addItem(str(outfit.get("name") or "Unnamed Outfit"))
        del blocker

    def on_outfit_selected(self, row):
        if self.loading:
            return
        self.store_current_outfit()
        self.select_outfit(row if row >= 0 else None)

    def select_outfit(self, index):
        self.current_outfit_index = index if index is not None and 0 <= index < len(self.outfits) else None
        self.loading = True
        if self.current_outfit_index is None:
            self.clear_detail_form()
            self.delete_outfit_button.setEnabled(False)
            self.copy_to_button.setEnabled(False)
        else:
            outfit = normalize_outfit(self.outfits[self.current_outfit_index])
            self.load_outfit(outfit)
            self.outfit_list.setCurrentRow(self.current_outfit_index)
            self.delete_outfit_button.setEnabled(True)
            self.copy_to_button.setEnabled(True)
        self.loading = False

    def clear_detail_form(self):
        self.name_lineedit.clear()
        self.role_lineedit.clear()
        self.modifier_lineedit.clear()
        self.description_textedit.clear()
        for editors in self.slot_editors.values():
            editors["positive"].set_prompts([])
            editors["negative"].set_prompts([])

    def load_outfit(self, outfit):
        blockers = [
            QSignalBlocker(self.name_lineedit),
            QSignalBlocker(self.role_lineedit),
            QSignalBlocker(self.modifier_lineedit),
            QSignalBlocker(self.description_textedit),
        ]
        self.name_lineedit.setText(str(outfit.get("name", "")))
        self.role_lineedit.setText(str(outfit.get("role", "")))
        self.modifier_lineedit.setText(", ".join(str(item).strip() for item in outfit.get("modifier", []) if str(item).strip()))
        self.description_textedit.setPlainText(str(outfit.get("description", "")))
        del blockers
        slots = outfit.get("slots", empty_outfit_slots())
        for slot, editors in self.slot_editors.items():
            slot_payload = slots.get(slot, {}) if isinstance(slots.get(slot, {}), dict) else {}
            editors["positive"].set_prompts(slot_payload.get("positive", []))
            editors["negative"].set_prompts(slot_payload.get("negative", []))

    def form_outfit(self) -> dict:
        slots = empty_outfit_slots()
        for slot, editors in self.slot_editors.items():
            slots[slot] = {
                "positive": editors["positive"].prompts(),
                "negative": editors["negative"].prompts(),
            }
        return {
            "name": self.name_lineedit.text().strip(),
            "role": self.role_lineedit.text().strip(),
            "modifier": parse_tag_text(self.modifier_lineedit.text()),
            "description": self.description_textedit.toPlainText(),
            "slots": slots,
            "remove": normalize_outfit(self.outfits[self.current_outfit_index]).get("remove", []) if self.current_outfit_index is not None else [],
        }

    def store_current_outfit(self):
        self._store_current_outfit(emit_changed=True)

    def _store_current_outfit(self, emit_changed=True):
        if self.loading or self.current_outfit_index is None:
            return
        self.outfits[self.current_outfit_index] = self.form_outfit()
        item = self.outfit_list.item(self.current_outfit_index)
        if item is not None:
            item.setText(self.outfits[self.current_outfit_index].get("name") or "Unnamed Outfit")
        if emit_changed:
            self._emit_changed()

    def add_outfit(self, outfit=None):
        self.store_current_outfit()
        if not isinstance(outfit, dict):
            outfit = {"name": "New Outfit", "role": "", "modifier": [], "description": "", "slots": empty_outfit_slots(), "remove": []}
        self.outfits.append(outfit)
        self.refresh_outfit_list()
        self.select_outfit(len(self.outfits) - 1)
        self._emit_changed()

    def delete_current_outfit(self):
        if self.current_outfit_index is None:
            return
        del self.outfits[self.current_outfit_index]
        self.refresh_outfit_list()
        self.select_outfit(min(self.current_outfit_index, len(self.outfits) - 1) if self.outfits else None)
        self._emit_changed()

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


def character_path(character_id: str) -> Path:
    return CHARACTERS_DIR / f"{character_id}.json"


def parse_prompt_text(raw_text: str) -> list[dict[str, object]]:
    parsed_prompt = []
    for raw_chunk in raw_text.split(","):
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        if "::" in chunk:
            parts = [part.strip() for part in chunk.split("::")]
            try:
                strength_value = float(parts[0])
            except (IndexError, ValueError):
                continue
            for tag_part in parts[1:]:
                if tag_part:
                    parsed_prompt.append({"tag": tag_part, "strength": strength_value})
        else:
            parsed_prompt.append({"tag": chunk, "strength": 1.0})
    return parsed_prompt


def format_prompt_list(prompt_list) -> str:
    if not prompt_list:
        return ""
    formatted_chunks = []
    for item in prompt_list:
        if not isinstance(item, dict):
            continue
        tag_text = str(item.get("tag", "")).strip()
        if not tag_text:
            continue
        try:
            strength_value = float(item.get("strength", 1.0))
        except (TypeError, ValueError):
            strength_value = 1.0
        if strength_value != 1.0:
            formatted_chunks.append(f"{strength_value}::{tag_text}::")
        else:
            formatted_chunks.append(tag_text)
    return ", ".join(formatted_chunks)


def parse_tag_text(raw_text: str) -> list[str]:
    return [chunk.strip() for chunk in raw_text.split(",") if chunk.strip()]


def parse_quick_weight_text(raw_text: str) -> list[dict[str, object]]:
    return [
        {
            "max": 3,
            "min": -3,
            "negative": False,
            "tag": tag,
            "value": 0,
        }
        for tag in parse_tag_text(raw_text)
    ]


def format_quick_weights(quick_weights) -> str:
    tags = []
    for item in quick_weights or []:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag", "")).strip()
        if tag:
            tags.append(tag)
    return ", ".join(tags)


def default_character() -> dict:
    return {
        "nameID": "",
        "Alias_ID": "",
        "exclude_from_character_list": False,
        "full_name": "",
        "c_positive": [],
        "c_negative": [],
        "g_positive": [],
        "g_negative": [],
        "chance_tag": [],
        "age": "",
        "gender": "none specified",
        "species": "",
        "subspecies": "",
        "species icon": "None",
        "labels": [],
        "label_groups": [],
        "quick_weights": [],
        "quotes": [],
        "default_expression": [],
        "outfits": [],
        "most_recent_outfit": "None",
        "tag_associations": [],
        "lore": [],
    }


def validate_character_id(character_id: str, existing_ids: set[str], previous_id: str | None = None) -> str | None:
    normalized_id = character_id.strip()
    if not normalized_id:
        return "Character ID cannot be empty."
    if normalized_id != previous_id and normalized_id in existing_ids:
        return "Character ID must be unique."
    return None


def character_order_key(character):
    try:
        sort_position = int(float(character.get("sort_position", 10**9)))
    except (TypeError, ValueError):
        sort_position = 10**9
    return sort_position, str(character.get("nameID", "")).lower()


def character_sort_key(character, sort_mode):
    name = str(character.get("nameID", "")).lower()
    if sort_mode == "Alphabetical":
        return 0, name
    if sort_mode == "Custom":
        return character_order_key(character)
    if sort_mode == "Status":
        labels = label_values(character.get("labels", []))
        score = 3 if "Main" in labels else 2 if "Supporting" in labels else 1 if "Minor" in labels else 0
        return -score, name
    try:
        age = int(character.get("age", 10**9))
    except (TypeError, ValueError):
        age = 10**9
    return (age if sort_mode == "Youngest" else -age), name


def load_saved_character_order(character_id: str, character: dict) -> dict:
    path = character_path(character_id)
    try:
        saved_character = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return character
    if isinstance(saved_character, dict) and "sort_position" in saved_character:
        character["sort_position"] = saved_character["sort_position"]
    return character


class ManageCharacterWindow(QDialog):
    LAST_CHARACTER_SETTING = "character_manager/last_character_id"

    def __init__(self, parent, image_cache):
        super().__init__(parent)
        self.setObjectName("characterManager")
        self.setStyleSheet(
            """
            QDialog#characterManager QFrame {
                background: transparent;
                border: none;
            }
            QDialog#characterManager QLabel {
                background: transparent;
                border: none;
            }
            QDialog#characterManager QScrollArea,
            QDialog#characterManager QStackedWidget {
                background: transparent;
                border: none;
            }
            QDialog#characterManager QFrame#characterManagerSidebar {
                background: #272833;
                border: 1px solid #444;
            }
            QDialog#characterManager QFrame#fluffFieldFrame,
            QDialog#characterManager QFrame#chanceAlternativeCard,
            QDialog#characterManager QFrame#triggerGroupCard {
                background: #21222C;
                border: 1px solid #444;
            }
            QDialog#characterManager QComboBox QFrame,
            QDialog#characterManager QComboBox QAbstractItemView {
                background: #272833;
                border: 1px solid #444;
            }
            """
        )
        self.setWindowTitle("Manage Characters")
        self.resize(840, 870)
        self.image_cache = image_cache
        self.characters_file_path = CHARACTERS_DIR
        self.portraits_dir = PORTRAITS_DIR
        self.alt_portraits_dir = ALT_PORTRAITS_DIR
        self.character_labels_path = CHARACTER_LABELS_FILE
        self.character_fluff_fields_path = CHARACTER_FLUFF_FIELDS_FILE
        self.character_fluff_fields = load_character_fluff_fields(self.character_fluff_fields_path)
        self.character_month_names = load_character_months(CHARACTER_MONTHS_FILE)
        self.characters = {
            str(character.get("nameID", "")): load_saved_character_order(
                str(character.get("nameID", "")), deepcopy(character)
            )
            for character in get_all_characters()
            if character.get("nameID")
        }
        self.original_character_ids = set(self.characters)
        self.deleted_character_ids = set()
        self.current_character_id = None
        self.new_character = default_character()
        self.new_character_active = False
        self.draft_previous_character_id = None
        self.pending_portraits = {}
        self.pending_portrait_deletes = set()
        self.loading_character = False
        self.character_lists_refresh_emitted = False
        self.build_manage_character_window()
        self.refresh_character_selector()
        ordered_ids = self.ordered_characters()
        last_character_id = str(
            QSettings("NAI_UI_2", "NAI_UI_2").value(self.LAST_CHARACTER_SETTING, "")
        ).strip()
        initial_character_id = (
            last_character_id
            if last_character_id in self.characters
            else ordered_ids[0].get("nameID")
            if ordered_ids
            else None
        )
        self.select_character(initial_character_id)

    def character_sort_mode(self):
        parent = self.parent()
        while parent is not None:
            left_column = getattr(parent, "left_column_widget", None)
            page4 = getattr(getattr(left_column, "upper_frame", None), "page4", None)
            sorting_combo = getattr(page4, "character_sorting_combo", None)
            if sorting_combo is not None:
                return sorting_combo.currentText()
            parent = parent.parent()
        return "Custom"

    def ordered_characters(self):
        return sorted(
            self.characters.values(),
            key=lambda character: character_sort_key(character, self.character_sort_mode()),
        )

    def build_manage_character_window(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("characterManagerSidebar")
        self.sidebar.setFixedWidth(110)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(6)
        self.grid.addWidget(self.sidebar, 0, 0)

        self.sidebar_layout.addWidget(QLabel("Character", self.sidebar))
        self.character_select_combobox = QComboBox(self.sidebar)
        self.character_select_combobox.currentIndexChanged.connect(self.on_character_change)
        self.sidebar_layout.addWidget(self.character_select_combobox)

        self.new_character_button = QPushButton("New", self.sidebar)
        self.new_character_button.clicked.connect(self.new_character_draft)
        self.sidebar_layout.addWidget(self.new_character_button)
        self.copy_character_button = QPushButton("Copy", self.sidebar)
        self.copy_character_button.clicked.connect(self.copy_character)
        self.sidebar_layout.addWidget(self.copy_character_button)
        self.delete_character_button = QPushButton("Delete", self.sidebar)
        self.delete_character_button.clicked.connect(self.delete_character)
        self.sidebar_layout.addWidget(self.delete_character_button)
        self.sidebar_layout.addStretch(1)

        action_frame = QFrame(self.sidebar)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.save_button = QPushButton("Save", action_frame)
        self.save_button.clicked.connect(self.save_and_close)
        action_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel", action_frame)
        self.cancel_button.clicked.connect(self.reject)
        action_layout.addWidget(self.cancel_button)
        self.sidebar_layout.addWidget(action_frame)
        self.update_draft_buttons()

        self.tabs = QTabWidget(self)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #555;
                background: #21222C;
            }
            QTabBar::tab {
                background: #21222C;
                color: #DDDDDD;
                border: 1px solid #555;
                border-bottom: none;
                min-width: 0;
                max-width: 200px;
                padding: 4px 8px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3949ab;
                color: #FFFFFF;
                border: 1px solid #9fa8da;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background: #3c3d50;
            }
            QLineEdit,
            QTextEdit {
                border: 1px solid #555;
            }
            """
        )
        self.grid.addWidget(self.tabs, 0, 1)
        self.grid.setColumnStretch(1, 1)

        self.build_overview_tab()
        self.build_fluff_tab()
        self.build_prompts_tab()
        self.build_labels_tab()
        self.build_quick_weights_tab()
        self.build_chance_tags_tab()
        self.build_tag_associations_tab()
        self.build_outfits_tab()
        self.build_quotes_tab()

    def build_overview_tab(self):
        tab = QWidget(self.tabs)
        layout = QGridLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        form_frame = QFrame(tab)
        form_layout = QGridLayout(form_frame)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(6)

        self.character_id_lineedit = QLineEdit(form_frame)
        self.character_id_lineedit.setProperty("lockedCharacterId", False)
        self.character_id_lineedit.setStyleSheet(
            'QLineEdit[lockedCharacterId="true"] { color: #888888; }'
        )
        self.exclude_from_character_list_checkbox = QCheckBox("Exclude from character list", form_frame)
        self.character_alias_id_lineedit = QLineEdit(form_frame)
        self.character_alias_id_lineedit.setPlaceholderText("Previous ID, another previous ID")
        self.character_alias_id_lineedit.setToolTip(
            "Comma-separated previous character IDs or names. Used only when the loaded ID is not found."
        )
        self.character_fullname_lineedit = QLineEdit(form_frame)
        self.character_age_lineedit = QLineEdit(form_frame)
        self.character_gender_combobox = QComboBox(form_frame)
        self.character_gender_combobox.addItems(GENDER_OPTIONS)
        self.character_species_lineedit = QLineEdit(form_frame)
        self.character_subspecies_lineedit = QLineEdit(form_frame)
        self.character_species_icon_combobox = QComboBox(form_frame)
        self.character_species_icon_combobox.addItems(SPECIES_ICON_OPTIONS)

        rows = [
            ("Character ID", self.character_id_lineedit),
            ("Alias_ID", self.character_alias_id_lineedit),
            ("Full Name", self.character_fullname_lineedit),
            ("Age", self.character_age_lineedit),
            ("Gender", self.character_gender_combobox),
            ("Species", self.character_species_lineedit),
            ("Subspecies", self.character_subspecies_lineedit),
            ("Species Icon", self.character_species_icon_combobox),
        ]
        for row, (label, widget) in enumerate(rows):
            label_widget = QLabel(label, form_frame)
            if label == "Character ID":
                label_widget.setText('Character ID <span style="color: #e53935;">*</span>')
            form_layout.addWidget(label_widget, row, 0)
            form_layout.addWidget(widget, row, 1, 1, 1 if label == "Character ID" else 2)
        form_layout.setColumnStretch(1, 1)
        form_layout.setColumnStretch(2, 0)
        form_layout.setRowStretch(len(rows), 1)
        layout.addWidget(form_frame, 0, 0, 1, 2)
        form_layout.addWidget(self.exclude_from_character_list_checkbox, 0, 2)
        portrait_frame = QFrame(tab)
        portrait_layout = QHBoxLayout(portrait_frame)
        portrait_layout.setContentsMargins(0, 0, 0, 0)
        portrait_layout.setSpacing(6)
        self.portrait_column = QFrame(portrait_frame)
        portrait_column_layout = QVBoxLayout(self.portrait_column)
        portrait_column_layout.setContentsMargins(0, 0, 0, 0)
        portrait_column_layout.setSpacing(6)
        self.portrait_label = ClickablePortraitLabel(self.portrait_column)
        self.portrait_label.setAlignment(Qt.AlignCenter)
        self.portrait_label.setFixedSize(180, 180)
        portrait_title_label = QLabel("Portrait", self.portrait_column)
        portrait_title_label.setAlignment(Qt.AlignCenter)
        portrait_title_label.setMaximumHeight(18)
        portrait_column_layout.addWidget(portrait_title_label)
        portrait_column_layout.addWidget(self.portrait_label, 0, Qt.AlignCenter)
        self.portrait_label.clicked.connect(lambda: self.browse_for_portrait("portrait"))
        self.delete_portrait_button = QPushButton("Delete Portrait", self.portrait_column)
        self.delete_portrait_button.clicked.connect(lambda: self.stage_portrait_delete("portrait"))
        portrait_column_layout.addWidget(self.delete_portrait_button)
        portrait_layout.addWidget(self.portrait_column, 0, Qt.AlignTop)

        self.alt_portrait_column = QFrame(portrait_frame)
        alt_portrait_column_layout = QVBoxLayout(self.alt_portrait_column)
        alt_portrait_column_layout.setContentsMargins(0, 0, 0, 0)
        alt_portrait_column_layout.setSpacing(6)
        self.alt_portrait_label = ClickablePortraitLabel(self.alt_portrait_column)
        self.alt_portrait_label.setAlignment(Qt.AlignCenter)
        self.alt_portrait_label.setFixedSize(180, 180)
        alt_portrait_title_label = QLabel("Alt Portrait", self.alt_portrait_column)
        alt_portrait_title_label.setAlignment(Qt.AlignCenter)
        alt_portrait_title_label.setMaximumHeight(18)
        alt_portrait_column_layout.addWidget(alt_portrait_title_label)
        alt_portrait_column_layout.addWidget(self.alt_portrait_label, 0, Qt.AlignCenter)
        self.alt_portrait_label.clicked.connect(lambda: self.browse_for_portrait("alt_portrait"))
        self.delete_alt_portrait_button = QPushButton("Delete Alt Portrait", self.alt_portrait_column)
        self.delete_alt_portrait_button.clicked.connect(lambda: self.stage_portrait_delete("alt_portrait"))
        alt_portrait_column_layout.addWidget(self.delete_alt_portrait_button)
        portrait_layout.addWidget(self.alt_portrait_column, 0, Qt.AlignTop)
        portrait_layout.addStretch(1)
        layout.addWidget(portrait_frame, 1, 0, 1, 2)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(2, 1)
        self.tabs.addTab(tab, "Overview")

        for line_edit in [self.character_id_lineedit, self.character_alias_id_lineedit, self.character_fullname_lineedit, self.character_age_lineedit, self.character_species_lineedit, self.character_subspecies_lineedit]:
            line_edit.textChanged.connect(self.store_current_character_from_form)
        self.character_gender_combobox.currentTextChanged.connect(self.store_current_character_from_form)
        self.character_species_icon_combobox.currentTextChanged.connect(self.store_current_character_from_form)
        self.exclude_from_character_list_checkbox.toggled.connect(self.store_current_character_from_form)

    def build_fluff_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.fluff_editor = CharacterFluffEditor(
            tab,
            self.character_fluff_fields,
            list(self.characters.values()),
            self.image_cache,
            self.character_month_names,
        )
        layout.addWidget(self.fluff_editor)
        self.tabs.addTab(tab, "Fluff")
        self.fluff_editor.changed.connect(self.store_current_character_from_form)

    def build_prompts_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.prompt_tabs = QTabWidget(tab)
        self.prompt_tabs.setObjectName("characterPromptTabs")
        self.prompt_tabs.setUsesScrollButtons(False)
        self.prompt_tabs.setStyleSheet(
            """
            QTabWidget#characterPromptTabs::pane {
                border: none;
                background: #21222C;
            }
            QTabBar::tab {
                background: #21222C;
                color: #DDDDDD;
                border: 1px solid #555;
                border-bottom: none;
                min-width: 0;
                max-width: 200px;
                padding: 4px 8px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3949ab;
                color: #FFFFFF;
                border: 1px solid #9fa8da;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background: #3c3d50;
            }
            """
        )
        self.character_c_positive_editor = PromptListEditor(self.prompt_tabs)
        self.character_c_negative_editor = PromptListEditor(self.prompt_tabs)
        self.character_g_positive_editor = PromptListEditor(self.prompt_tabs)
        self.character_g_negative_editor = PromptListEditor(self.prompt_tabs)
        self.character_default_expression_editor = PromptListEditor(self.prompt_tabs)
        self.prompt_tabs.addTab(self.character_c_positive_editor, "Character +")
        self.prompt_tabs.addTab(self.character_c_negative_editor, "Character -")
        self.prompt_tabs.addTab(self.character_g_positive_editor, "Global +")
        self.prompt_tabs.addTab(self.character_g_negative_editor, "Global -")
        self.prompt_tabs.addTab(self.character_default_expression_editor, "Default Expression")
        layout.addWidget(self.prompt_tabs)
        self.tabs.addTab(tab, "Prompts")

        for prompt_editor in [self.character_c_positive_editor, self.character_c_negative_editor, self.character_g_positive_editor, self.character_g_negative_editor]:
            prompt_editor.changed.connect(self.store_current_character_from_form)

    def _character_label_data(self):
        definitions, group_settings = load_character_label_data(self.character_labels_path)
        return definitions, self.character_labels_path, group_settings

    def build_labels_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.character_labels_editor = CharacterLabelEditor(tab, *self._character_label_data())
        layout.addWidget(self.character_labels_editor, 1)
        self.tabs.addTab(tab, "Labels")

        self.character_labels_editor.changed.connect(self.store_current_character_from_form)

    def build_quick_weights_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.quick_weight_editor = QuickWeightListEditor(tab)
        layout.addWidget(self.quick_weight_editor)
        self.tabs.addTab(tab, "Quick Weights")
        self.quick_weight_editor.changed.connect(self.store_current_character_from_form)

    def build_chance_tags_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.chance_tag_editor = ChanceTagListEditor(tab)
        layout.addWidget(self.chance_tag_editor)
        self.tabs.addTab(tab, "Chance Tags")
        self.chance_tag_editor.changed.connect(self.store_current_character_from_form)

    def build_tag_associations_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.tag_association_editor = TagAssociationListEditor(tab)
        layout.addWidget(self.tag_association_editor)
        self.tabs.addTab(tab, "Tag Associations")
        self.tag_association_editor.changed.connect(self.store_current_character_from_form)

    def build_outfits_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.outfit_editor = OutfitEditor(tab)
        layout.addWidget(self.outfit_editor)
        self.tabs.addTab(tab, "Outfits")
        self.outfit_editor.changed.connect(self.store_current_character_from_form)
        self.outfit_editor.copy_to_requested.connect(self.copy_current_outfit_to_character)

    def copy_current_outfit_to_character(self):
        outfit = self.outfit_editor.current_outfit_payload()
        if outfit is None:
            return
        # Make sure the open character's latest label edits count when matching by label.
        self.store_current_character_from_form()
        ordered_characters = [character for character in self.ordered_characters() if character.get("nameID")]
        target_ids = [str(character.get("nameID")) for character in ordered_characters]
        if not target_ids:
            Error(self, "There are no characters to copy this outfit to.")
            return
        character_labels = {
            str(character.get("nameID")): [
                (label_category(label_entry), label_value(label_entry))
                for label_entry in character.get("labels") or []
                if label_value(label_entry)
            ]
            for character in ordered_characters
        }
        dialog = CopyOutfitDialog(
            self,
            outfit.get("name") or "Unnamed Outfit",
            target_ids,
            character_labels,
            source_character_id=self.current_character_id,
        )
        if self.current_character_id in target_ids:
            dialog.character_combobox.setCurrentText(self.current_character_id)
        if not dialog.exec():
            return
        if dialog.copy_mode() == CopyOutfitDialog.LABEL_MODE:
            for target_id in dialog.label_target_ids():
                self.copy_outfit_to_stored_character(target_id, deepcopy(outfit))
            return
        target_id = dialog.selected_character_id()
        if target_id == self.current_character_id:
            # The open character's outfits live in the editor, so duplicate there and select the copy.
            outfit["name"] = unique_outfit_name(outfit["name"], self.outfit_editor.outfits)
            self.outfit_editor.add_outfit(outfit)
            return
        self.copy_outfit_to_stored_character(target_id, outfit)

    def copy_outfit_to_stored_character(self, target_id, outfit):
        target_character = self.characters.get(target_id)
        if target_character is None:
            return
        target_outfits = target_character.setdefault("outfits", [])
        outfit["name"] = unique_outfit_name(outfit["name"], target_outfits)
        target_outfits.append(outfit)

    def build_quotes_tab(self):
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.quote_editor = QuoteListEditor(tab)
        layout.addWidget(self.quote_editor)
        self.tabs.addTab(tab, "Quotes")
        self.quote_editor.changed.connect(self.store_current_character_from_form)

    def refresh_character_selector(self):
        current_id = self.current_character_id
        blocker = QSignalBlocker(self.character_select_combobox)
        self.character_select_combobox.clear()
        if self.new_character_active:
            self.character_select_combobox.addItem(NEW_CHARACTER_LABEL, None)
        ordered_characters = self.ordered_characters()
        for character in ordered_characters:
            character_id = character.get("nameID")
            self.character_select_combobox.addItem(character_id, character_id)
        index = self.character_select_combobox.findData(current_id)
        self.character_select_combobox.setCurrentIndex(index if index >= 0 else (0 if self.character_select_combobox.count() else -1))
        del blocker

    def on_character_change(self):
        if self.loading_character:
            return
        self.store_current_character_from_form()
        self.select_character(self.character_select_combobox.currentData())

    def new_character_draft(self):
        if self.new_character_active:
            self.save_character_draft()
            return
        self.store_current_character_from_form()
        self.draft_previous_character_id = self.current_character_id
        self.new_character = default_character()
        self.new_character_active = True
        self.current_character_id = None
        self.character_select_combobox.setEnabled(False)
        self.refresh_character_selector()
        self.select_character(None)
        self.update_draft_buttons()

    def select_character(self, character_id):
        self.current_character_id = character_id
        # Keep the selector in step with the loaded character (e.g. the restored last character on open).
        index = self.character_select_combobox.findData(character_id)
        if index >= 0 and index != self.character_select_combobox.currentIndex():
            blocker = QSignalBlocker(self.character_select_combobox)
            self.character_select_combobox.setCurrentIndex(index)
            del blocker
        character = self.characters.get(character_id, default_character()) if character_id else self.new_character
        self.load_character_into_form(character)
        is_existing = character_id is not None
        self.character_id_lineedit.setReadOnly(is_existing)
        self.character_id_lineedit.setProperty("lockedCharacterId", is_existing)
        self.character_id_lineedit.style().unpolish(self.character_id_lineedit)
        self.character_id_lineedit.style().polish(self.character_id_lineedit)
        self.copy_character_button.setEnabled(is_existing)
        self.delete_character_button.setEnabled(is_existing)

    def update_draft_buttons(self):
        if self.new_character_active:
            self.new_character_button.setText("Save Character")
            self.copy_character_button.setText("Cancel Character")
            self.copy_character_button.setEnabled(True)
            self.delete_character_button.setVisible(False)
        else:
            self.new_character_button.setText("New")
            self.copy_character_button.setText("Copy")
            self.delete_character_button.setVisible(True)

    def save_character_draft(self):
        self.store_current_character_from_form()
        existing_ids = set(self.characters)
        new_id = str(self.new_character.get("nameID", "")).strip()
        validation_error = validate_character_id(new_id, existing_ids)
        if validation_error:
            Error(self, validation_error)
            return False
        self.characters[new_id] = deepcopy(self.new_character)
        for portrait_kind in ["portrait", "alt_portrait"]:
            pending_key = (portrait_kind, None)
            if pending_key in self.pending_portraits:
                self.pending_portraits[(portrait_kind, new_id)] = self.pending_portraits.pop(pending_key)
        self.new_character = default_character()
        self.new_character_active = False
        self.draft_previous_character_id = None
        self.current_character_id = new_id
        self.character_select_combobox.setEnabled(True)
        self.refresh_character_selector()
        self.select_character(new_id)
        self.update_draft_buttons()
        return True

    def cancel_character_draft(self):
        if not self.new_character_active:
            return
        self.new_character = default_character()
        self.new_character_active = False
        character_id = self.draft_previous_character_id
        self.draft_previous_character_id = None
        self.current_character_id = character_id
        self.character_select_combobox.setEnabled(True)
        self.refresh_character_selector()
        self.select_character(character_id)
        self.update_draft_buttons()

    def load_character_into_form(self, character):
        self.loading_character = True
        controls = [
            self.character_id_lineedit,
            self.character_alias_id_lineedit,
            self.character_fullname_lineedit,
            self.character_age_lineedit,
            self.character_species_lineedit,
            self.character_subspecies_lineedit,
            self.character_gender_combobox,
            self.character_species_icon_combobox,
            self.character_c_positive_editor,
            self.character_c_negative_editor,
            self.character_g_positive_editor,
            self.character_g_negative_editor,
            self.character_default_expression_editor,
            self.character_labels_editor,
            self.quick_weight_editor,
            self.tag_association_editor,
            self.outfit_editor,
            self.quote_editor,
            self.fluff_editor,
        ]
        blockers = [QSignalBlocker(control) for control in controls]
        self.character_id_lineedit.setText(str(character.get("nameID", "")))
        self.character_alias_id_lineedit.setText(character.get("Alias_ID", ""))
        self.exclude_from_character_list_checkbox.setChecked(bool(character.get("exclude_from_character_list", False)))
        self.character_fullname_lineedit.setText(str(character.get("full_name", "")))
        self.character_age_lineedit.setText(str(character.get("age", "")))
        self.character_species_lineedit.setText(str(character.get("species", "")))
        self.character_subspecies_lineedit.setText(str(character.get("subspecies", "")))
        self.character_gender_combobox.setCurrentText(str(character.get("gender", "none specified")))
        self.character_species_icon_combobox.setCurrentText(str(character.get("species icon", "None")))
        self.fluff_editor.set_values(character)
        self.character_c_positive_editor.set_prompts(character.get("c_positive", []))
        self.character_c_negative_editor.set_prompts(character.get("c_negative", []))
        self.character_g_positive_editor.set_prompts(character.get("g_positive", []))
        self.character_g_negative_editor.set_prompts(character.get("g_negative", []))
        self.character_default_expression_editor.set_prompts(character.get("default_expression", []))
        self.character_labels_editor.set_labels(character.get("labels", []), character.get("label_groups"))
        self.quick_weight_editor.set_quick_weights(character.get("quick_weights", []))
        self.chance_tag_editor.set_groups(character.get("chance_tag", []))
        self.tag_association_editor.set_associations(character.get("tag_associations", []))
        self.outfit_editor.set_outfits(character.get("outfits", []))
        self.quote_editor.set_quotes(character.get("quotes", []))
        del blockers
        self.update_portrait("portrait", self.portrait_path_for_character("portrait", character.get("nameID", "")))
        self.update_portrait("alt_portrait", self.portrait_path_for_character("alt_portrait", character.get("nameID", "")))
        self.loading_character = False

    def form_character(self) -> dict:
        base = deepcopy(self.characters.get(self.current_character_id, self.new_character if self.current_character_id is None else default_character()))
        base["nameID"] = self.character_id_lineedit.text().strip()
        base["Alias_ID"] = ", ".join(
            alias.strip()
            for alias in self.character_alias_id_lineedit.text().split(",")
            if alias.strip()
        )
        base["exclude_from_character_list"] = self.exclude_from_character_list_checkbox.isChecked()
        base["full_name"] = self.character_fullname_lineedit.text()
        base["age"] = self.character_age_lineedit.text()
        base["gender"] = self.character_gender_combobox.currentText()
        base["species"] = self.character_species_lineedit.text()
        base["subspecies"] = self.character_subspecies_lineedit.text()
        base["species icon"] = self.character_species_icon_combobox.currentText()
        base.update(self.fluff_editor.values())
        base["c_positive"] = self.character_c_positive_editor.prompts()
        base["c_negative"] = self.character_c_negative_editor.prompts()
        base["g_positive"] = self.character_g_positive_editor.prompts()
        base["g_negative"] = self.character_g_negative_editor.prompts()
        base["default_expression"] = self.character_default_expression_editor.prompts()
        base["labels"] = self.character_labels_editor.labels()
        base["label_groups"] = self.character_labels_editor.active_groups()
        base["quick_weights"] = self.quick_weight_editor.quick_weights()
        base["chance_tag"] = self.chance_tag_editor.groups_payload()
        base["tag_associations"] = self.tag_association_editor.associations_payload()
        base["outfits"] = self.outfit_editor.outfits_payload()
        base["quotes"] = self.quote_editor.quotes()
        for key, value in default_character().items():
            base.setdefault(key, deepcopy(value))
        return base

    def store_current_character_from_form(self):
        if self.loading_character:
            return
        character = self.form_character()
        if self.current_character_id is None:
            self.new_character = character
        elif self.current_character_id in self.characters:
            self.characters[self.current_character_id] = character

    def copy_character(self):
        if self.new_character_active:
            self.cancel_character_draft()
            return
        if self.current_character_id is None:
            return
        self.store_current_character_from_form()
        character = deepcopy(self.characters.get(self.current_character_id, default_character()))
        character["nameID"] = f"{character.get('nameID', '')}_copy"
        character["Alias_ID"] = ""
        self.draft_previous_character_id = self.current_character_id
        self.new_character = character
        self.new_character_active = True
        self.current_character_id = None
        self.character_select_combobox.setEnabled(False)
        self.refresh_character_selector()
        self.select_character(None)
        self.update_draft_buttons()

    def delete_character(self):
        if self.current_character_id is None:
            return
        confirmation = Confirm(self, "Delete Character", f"Delete '{self.current_character_id}' when changes are saved?", "Delete", "Cancel")
        if not confirmation.exec():
            return
        character_id = self.current_character_id
        self.deleted_character_ids.add(character_id)
        self.characters.pop(character_id, None)
        for portrait_kind in ["portrait", "alt_portrait"]:
            self.pending_portraits.pop((portrait_kind, character_id), None)
            self.pending_portrait_deletes.add((portrait_kind, character_id))
        self.current_character_id = None
        self.refresh_character_selector()
        self.select_character(None)

    def browse_for_portrait(self, portrait_kind="portrait"):
        file_path, selected_filter = QFileDialog.getOpenFileName(
            self,
            "Select portrait image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)",
        )
        if not file_path:
            return
        key = (portrait_kind, self.current_character_id)
        if self.current_character_id is None:
            self.pending_portraits[(portrait_kind, None)] = file_path
        else:
            self.pending_portraits[key] = file_path
            self.pending_portrait_deletes.discard(key)
        self.update_portrait(portrait_kind, file_path)

    def stage_portrait_delete(self, portrait_kind="portrait"):
        key = (portrait_kind, self.current_character_id)
        if self.current_character_id is None:
            self.pending_portraits.pop((portrait_kind, None), None)
        else:
            self.pending_portraits.pop(key, None)
            self.pending_portrait_deletes.add(key)
        self.update_portrait(portrait_kind, "")

    def portrait_path_for_character(self, portrait_kind: str, character_id: str) -> str:
        current_key = (portrait_kind, self.current_character_id)
        if current_key in self.pending_portraits:
            return self.pending_portraits[current_key]
        if current_key in self.pending_portrait_deletes:
            return ""
        if not character_id:
            return self.pending_portraits.get((portrait_kind, None), "")
        return str(self.existing_portrait_path(portrait_kind, character_id) or "")

    def update_portrait(self, portrait_kind: str, path: str):
        label = self.alt_portrait_label if portrait_kind == "alt_portrait" else self.portrait_label
        pix_path = path or self.image_cache.get("images", {}).get("character_portraits", {}).get("fluff_placeholder", "")
        pixmap = QPixmap(str(pix_path)) if pix_path else QPixmap()
        if pixmap.isNull():
            label.clear()
            label.setText("No Portrait")
            return
        scaled_pixmap = pixmap.scaled(180, 180, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        label.setText("")
        label.setPixmap(scaled_pixmap)

    def portrait_directory(self, portrait_kind: str) -> Path:
        return self.alt_portraits_dir if portrait_kind == "alt_portrait" else self.portraits_dir

    def existing_portrait_path(self, portrait_kind: str, character_id: str) -> Path | None:
        if not character_id:
            return None
        key = str(character_id).lower()
        if portrait_kind == "portrait":
            cached_path = self.image_cache.setdefault("portraits", {}).get(key)
            if cached_path and Path(cached_path).is_file():
                return Path(cached_path)
        try:
            return next((path for path in self.portrait_directory(portrait_kind).glob(f"{key}.*") if path.is_file()), None)
        except OSError:
            return None

    def save_and_close(self):
        self.store_current_character_from_form()
        if self.new_character_active and not self.save_character_draft():
            return

        for character_id, character in list(self.characters.items()):
            validation_error = validate_character_id(str(character.get("nameID", "")), set(self.characters) - {character_id}, character_id)
            if validation_error:
                Error(self, f"{character_id}: {validation_error}")
                return

        CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        for character_id in self.deleted_character_ids:
            self.delete_character_files(character_id)
        for character_id, character in self.characters.items():
            character_path(character_id).write_text(json.dumps(character, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (REFERENCE_DIR / character_id.lower()).mkdir(parents=True, exist_ok=True)
        for portrait_kind, character_id in self.pending_portrait_deletes:
            if character_id is not None:
                self.delete_portrait_for_character(character_id, portrait_kind)
        for (portrait_kind, character_id), source_path in self.pending_portraits.items():
            if character_id is not None:
                self.save_current_portrait_for_character(character_id, source_path, portrait_kind)

        self.emit_character_lists_refresh()
        self.save_last_character_id()
        self.accept()

    def save_last_character_id(self):
        if self.current_character_id is not None:
            QSettings("NAI_UI_2", "NAI_UI_2").setValue(
                self.LAST_CHARACTER_SETTING,
                self.current_character_id,
            )

    def emit_character_lists_refresh(self):
        if self.character_lists_refresh_emitted:
            return
        self.character_lists_refresh_emitted = True
        refresh_character_lists_signal.reload_character_data.emit()
        refresh_character_lists_signal.refresh_lists.emit()

    def delete_character_files(self, character_id: str):
        self.delete_portrait_for_character(character_id, "portrait")
        self.delete_portrait_for_character(character_id, "alt_portrait")
        reference_path = REFERENCE_DIR / character_id.lower()
        if reference_path.is_dir():
            shutil.rmtree(reference_path, ignore_errors=True)
        path = character_path(character_id)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass

    def save_current_portrait_for_character(self, character_id: str, source_path: str, portrait_kind="portrait"):
        source = Path(source_path)
        if not source.is_file():
            return
        placeholder_path = self.image_cache.get("images", {}).get("character_portraits", {}).get("fluff_placeholder", "")
        if placeholder_path and source == Path(placeholder_path):
            return
        key = character_id.lower()
        portrait_dir = self.portrait_directory(portrait_kind)
        portrait_dir.mkdir(parents=True, exist_ok=True)
        for existing_portrait_file in portrait_dir.glob(f"{key}.*"):
            if existing_portrait_file.is_file():
                try:
                    existing_portrait_file.unlink()
                except OSError:
                    pass
        target_path = portrait_dir / f"{key}{source.suffix.lower() or '.png'}"
        try:
            copy2(source, target_path)
        except OSError:
            return
        if portrait_kind == "portrait":
            self.image_cache.setdefault("portraits", {})[key] = str(target_path)

    def delete_portrait_for_character(self, character_id: str, portrait_kind="portrait"):
        key = character_id.lower()
        placeholder_path = self.image_cache.get("images", {}).get("character_portraits", {}).get("fluff_placeholder", "")
        for portrait_file in self.portrait_directory(portrait_kind).glob(f"{key}.*"):
            if placeholder_path and str(portrait_file) == str(Path(placeholder_path)):
                continue
            if portrait_file.is_file():
                try:
                    portrait_file.unlink()
                except OSError:
                    pass
        if portrait_kind == "portrait":
            self.image_cache.setdefault("portraits", {}).pop(key, None)

    def closeEvent(self, event):
        self.emit_character_lists_refresh()
        self.save_last_character_id()
        event.accept()

    def reject(self):
        self.save_last_character_id()
        self.cancel_character_draft()
        self.new_character = default_character()
        self.new_character_active = False
        ordered_characters = self.ordered_characters()
        first_character_id = ordered_characters[0].get("nameID") if ordered_characters else None
        self.current_character_id = first_character_id
        self.character_select_combobox.setEnabled(True)
        self.update_draft_buttons()
        self.refresh_character_selector()
        self.select_character(first_character_id)
        super().reject()

    def parse_prompt_text(self, raw_text: str):
        return parse_prompt_text(raw_text)

    def format_prompt_list(self, prompt_list):
        return format_prompt_list(prompt_list)
