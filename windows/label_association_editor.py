from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from data.label_associations import (
    LABEL_MATCH_ALL,
    LABEL_MATCH_NONE,
    normalize_label_association,
)
from windows.character_editor import EDITOR_LIST_WIDTH, PlainTagListEditor, PromptListEditor


class LabelBlacklistEditor(QFrame):
    """Edit blacklist tags and whether each matching tag should be removed."""

    changed = Signal()

    def __init__(self, parent=None):
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
        self.add_button = QPushButton("Add Tag", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)

    def add_empty_row(self):
        self.add_row()
        self._emit_changed()

    def add_row(self, tag="", remove=False):
        row = QFrame(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        lineedit = QLineEdit(row)
        lineedit.setPlaceholderText("Tag")
        lineedit.setText(str(tag))
        lineedit.textChanged.connect(self._emit_changed)
        row_layout.addWidget(lineedit, 1)
        remove_checkbox = QCheckBox("Remove", row)
        remove_checkbox.setChecked(bool(remove))
        remove_checkbox.setToolTip("Remove this tag from the prompt when it blocks the association.")
        remove_checkbox.toggled.connect(self._emit_changed)
        row_layout.addWidget(remove_checkbox)
        remove_button = QPushButton("Remove Row", row)
        remove_button.clicked.connect(lambda: self.remove_row(row))
        row_layout.addWidget(remove_button)
        row.tag_lineedit = lineedit
        row.remove_checkbox = remove_checkbox
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

    def set_tags(self, tags, remove_tags=None):
        self.loading = True
        for row in self.rows:
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()
        remove_tags = {str(tag).casefold() for tag in remove_tags or []}
        for tag in tags or []:
            text = str(tag or "").strip()
            if text:
                self.add_row(text, text.casefold() in remove_tags)
        self.loading = False

    def tags(self):
        return [row.tag_lineedit.text().strip() for row in self.rows if row.tag_lineedit.text().strip()]

    def remove_tags(self):
        return [
            row.tag_lineedit.text().strip()
            for row in self.rows
            if row.tag_lineedit.text().strip() and row.remove_checkbox.isChecked()
        ]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


def _label_options(definitions) -> list[tuple[str, str]]:
    """Return ``(display text, label)`` pairs for every defined label."""
    options = []
    seen = set()
    for definition in definitions or []:
        if not isinstance(definition, dict):
            continue
        label = str(definition.get("label") or "").strip()
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        category = str(definition.get("category") or "").strip()
        options.append((f"{category}: {label}" if category else label, label))
    return options


class LabelPickerListEditor(QFrame):
    """A list of labels chosen from the defined character labels."""

    changed = Signal()

    def __init__(self, parent=None, labels=None, options=None):
        super().__init__(parent)
        self.rows = []
        self.loading = False
        self.options = list(options or [])
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.layout.addLayout(self.rows_layout)
        self.add_button = QPushButton("Add Label", self)
        self.add_button.clicked.connect(self.add_empty_row)
        self.layout.addWidget(self.add_button)
        self.set_labels(labels or [])

    def _populate_combo(self, combo, selected=""):
        blocker = QSignalBlocker(combo)
        combo.clear()
        known = set()
        for text, label in self.options:
            combo.addItem(text, label)
            known.add(label.casefold())
        if selected and selected.casefold() not in known:
            combo.addItem(f"{selected} (undefined)", selected)
        index = combo.findData(selected) if selected else -1
        if index < 0 and selected:
            index = next(
                (i for i in range(combo.count()) if str(combo.itemData(i)).casefold() == selected.casefold()),
                -1,
            )
        combo.setCurrentIndex(index if index >= 0 else (0 if combo.count() else -1))
        del blocker

    def add_empty_row(self):
        self.add_row()
        self._emit_changed()

    def add_row(self, label=""):
        row = QFrame(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        combo = QComboBox(row)
        self._populate_combo(combo, str(label or "").strip())
        combo.currentIndexChanged.connect(self._emit_changed)
        row_layout.addWidget(combo, 1)
        remove_button = QPushButton("Remove", row)
        remove_button.clicked.connect(lambda: self.remove_row(row))
        row_layout.addWidget(remove_button)
        row.label_combo = combo
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

    def set_labels(self, labels):
        self.loading = True
        self.clear_rows()
        for label in labels or []:
            if str(label or "").strip():
                self.add_row(label)
        self.loading = False

    def set_options(self, options):
        self.options = list(options or [])
        for row in self.rows:
            self._populate_combo(row.label_combo, str(row.label_combo.currentData() or ""))

    def labels(self):
        labels = []
        for row in self.rows:
            label = str(row.label_combo.currentData() or "").strip()
            if label and label not in labels:
                labels.append(label)
        return labels

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class LabelTriggerGroupEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, groups=None, options=None):
        super().__init__(parent)
        self.groups = []
        self.loading = False
        self.options = list(options or [])
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        self.group_list = QListWidget(self)
        self.group_list.setFixedWidth(EDITOR_LIST_WIDTH)
        self.group_list.currentRowChanged.connect(self.select_group)
        content_layout.addWidget(self.group_list)
        self.group_stack = QStackedWidget(self)
        content_layout.addWidget(self.group_stack, 1)
        self.layout.addLayout(content_layout, 1)
        self.add_button = QPushButton("Add Label Group", self)
        self.add_button.clicked.connect(self.add_empty_group)
        self.layout.addWidget(self.add_button)
        self.set_groups(groups or [])

    def add_empty_group(self):
        editor = self.add_group([])
        editor.add_row()
        self.group_list.setCurrentRow(self.groups.index(editor))
        self._emit_changed()

    def add_group(self, labels):
        card = QFrame(self.group_stack)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(4)
        editor = LabelPickerListEditor(card, labels, self.options)
        editor.changed.connect(self._emit_changed)
        card_layout.addWidget(editor)
        remove_button = QPushButton("Remove Label Group", card)
        remove_button.clicked.connect(lambda: self.remove_group(editor))
        card_layout.addWidget(remove_button)
        card_layout.addStretch(1)
        editor.card = card
        self.groups.append(editor)
        self.group_stack.addWidget(card)
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
        self.group_stack.removeWidget(editor.card)
        editor.card.deleteLater()
        for group_index in range(self.group_list.count()):
            self.group_list.item(group_index).setText(f"Group {group_index + 1}")
        if self.groups:
            self.group_list.setCurrentRow(min(index, len(self.groups) - 1))
        self._emit_changed()

    def clear_groups(self):
        for editor in list(self.groups):
            self.group_stack.removeWidget(editor.card)
            editor.card.deleteLater()
        self.groups.clear()
        self.group_list.clear()

    def set_groups(self, groups):
        self.loading = True
        self.clear_groups()
        for group in groups or []:
            if isinstance(group, list):
                self.add_group(group)
        self.loading = False
        if self.groups:
            self.group_list.setCurrentRow(0)

    def set_options(self, options):
        self.options = list(options or [])
        for editor in self.groups:
            editor.set_options(self.options)

    def label_groups(self):
        return [labels for editor in self.groups if (labels := editor.labels())]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class LabelAssociationEditor(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, association=None, options=None):
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

        self.layout.addWidget(QLabel("Label Triggers", self))
        self.trigger_editor = LabelTriggerGroupEditor(self, options=options)
        self.trigger_editor.changed.connect(self._emit_changed)
        self.layout.addWidget(self.trigger_editor)

        match_row = QFrame(self)
        match_layout = QHBoxLayout(match_row)
        match_layout.setContentsMargins(0, 0, 0, 0)
        match_layout.addWidget(QLabel("Apply when the character has", match_row))
        self.match_combo = QComboBox(match_row)
        self.match_combo.addItem("All label groups", LABEL_MATCH_ALL)
        self.match_combo.addItem("None of the labels", LABEL_MATCH_NONE)
        self.match_combo.setToolTip(
            "All: every label group must contain at least one of the character's labels.\n"
            "None: the character must have none of the labels listed in any group."
        )
        self.match_combo.currentIndexChanged.connect(self._emit_changed)
        match_layout.addWidget(self.match_combo, 1)
        self.layout.addWidget(match_row)

        self.blacklist_editor = LabelBlacklistEditor(self)
        self.blacklist_editor.changed.connect(self._emit_changed)
        self.remove_editor = PlainTagListEditor(self)
        self.layout.addWidget(QLabel("Blacklist", self))
        self.layout.addWidget(self.blacklist_editor)
        for label, widget in [("Remove", self.remove_editor)]:
            self.layout.addWidget(QLabel(label, self))
            self.layout.addWidget(widget)
            widget.changed.connect(self._emit_changed)

        self.layout.addWidget(QLabel("Inject", self))
        self.inject_editor = PromptListEditor(self)
        self.inject_editor.changed.connect(self._emit_changed)
        self.layout.addWidget(self.inject_editor, 1)
        self.negative_injection_checkbox = QCheckBox("Negative Injections", self)
        self.negative_injection_checkbox.setToolTip("Inject into the negative prompt instead of the positive prompt when triggered.")
        self.negative_injection_checkbox.toggled.connect(self._emit_changed)
        self.layout.addWidget(self.negative_injection_checkbox)
        self.remove_button = QPushButton("Remove Association", self)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        self.layout.addWidget(self.remove_button)
        self.set_association(association or {})

    def set_association(self, association):
        association = normalize_label_association(association or {}) or {}
        self.loading = True
        self.active = association.get("active", True)
        self.name_lineedit.setText(association.get("name", ""))
        self.trigger_editor.set_groups(association.get("label_triggers", []))
        index = self.match_combo.findData(association.get("match", LABEL_MATCH_ALL))
        self.match_combo.setCurrentIndex(max(0, index))
        self.blacklist_editor.set_tags(
            association.get("blacklist", []),
            association.get("remove_blacklist", []),
        )
        self.remove_editor.set_tags(association.get("remove", []))
        self.inject_editor.set_prompts(association.get("inject", []))
        self.negative_injection_checkbox.setChecked(bool(association.get("negative_injection", False)))
        self.loading = False

    def set_label_options(self, options):
        self.trigger_editor.set_options(options)

    def association(self):
        return {
            "name": self.name_lineedit.text().strip(),
            "active": self.active,
            "label_triggers": self.trigger_editor.label_groups(),
            "match": self.match_combo.currentData() or LABEL_MATCH_ALL,
            "inject": self.inject_editor.prompts(),
            "blacklist": self.blacklist_editor.tags(),
            "remove_blacklist": self.blacklist_editor.remove_tags(),
            "remove": self.remove_editor.tags(),
            "negative_injection": self.negative_injection_checkbox.isChecked(),
        }

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()


class LabelAssociationListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, label_definitions=None):
        super().__init__(parent)
        self.editors = []
        self.loading = False
        self.options = _label_options(label_definitions)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
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
        content_layout.addWidget(self.association_list)
        self.association_stack = QStackedWidget(self)
        content_layout.addWidget(self.association_stack, 1)
        self.layout.addLayout(content_layout, 1)
        self.add_button = QPushButton("Add Label Association", self)
        self.add_button.clicked.connect(self.add_empty_association)
        self.layout.addWidget(self.add_button)

    def set_label_definitions(self, label_definitions):
        self.options = _label_options(label_definitions)
        for editor in self.editors:
            editor.set_label_options(self.options)

    def add_empty_association(self):
        editor = self.add_association({})
        self.association_list.setCurrentRow(self.editors.index(editor))
        self._emit_changed()

    def add_association(self, association):
        editor = LabelAssociationEditor(self.association_stack, association, self.options)
        editor.changed.connect(self._emit_changed)
        editor.name_lineedit.textChanged.connect(self.refresh_association_names)
        editor.remove_requested.connect(self.remove_association)
        self.editors.append(editor)
        self.association_stack.addWidget(editor)
        self.association_list.addItem(str(association.get("name") or "").strip() or "New Label Association")
        return editor

    def refresh_association_names(self):
        for index, editor in enumerate(self.editors):
            name = editor.name_lineedit.text().strip() or f"Label Association {index + 1}"
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
        return [
            association
            for editor in self.editors
            if (association := editor.association())["label_triggers"]
        ]

    def _emit_changed(self):
        if not self.loading:
            self.changed.emit()
