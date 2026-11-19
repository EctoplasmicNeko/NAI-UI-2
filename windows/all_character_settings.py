from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from data.paths import CHARACTER_LABELS_FILE, LABEL_ASSOCIATIONS_FILE
from data.label_associations import load_label_associations, save_label_associations
from data.label_groups import (
    MANDATORY_LABEL_CATEGORIES,
    group_names,
    load_character_label_data,
    save_character_label_data,
)
from windows.label_association_editor import LabelAssociationListEditor
from windows.confirmation import Confirm
from windows.error import Error
from windows.universal_tag_associations import ScopedTagAssociationEditor
from signaling.refresh_character_lists import refresh_character_lists_signal


class LabelGroupManager(QFrame):
    """Create, delete and configure the label groups shared by every character."""

    changed = Signal()

    def __init__(self, parent=None, labels_path=None):
        super().__init__(parent)
        self.labels_path = labels_path or CHARACTER_LABELS_FILE
        self.label_definitions, self.group_settings = load_character_label_data(self.labels_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        layout.addLayout(content_layout, 1)

        group_frame = QFrame(self)
        group_layout = QVBoxLayout(group_frame)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(4)
        group_layout.addWidget(QLabel("Label Groups", group_frame))
        self.group_list = QListWidget(group_frame)
        self.group_list.setFixedWidth(200)
        self.group_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 3px 10px;
            }
            """
        )
        self.group_list.currentTextChanged.connect(self.select_group)
        group_layout.addWidget(self.group_list, 1)

        add_group_frame = QFrame(group_frame)
        add_group_layout = QHBoxLayout(add_group_frame)
        add_group_layout.setContentsMargins(0, 0, 0, 0)
        add_group_layout.setSpacing(4)
        self.new_group_lineedit = QLineEdit(add_group_frame)
        self.new_group_lineedit.setPlaceholderText("Label group name")
        self.new_group_lineedit.returnPressed.connect(self.add_group)
        add_group_layout.addWidget(self.new_group_lineedit, 1)
        self.add_group_button = QPushButton("Add Group", add_group_frame)
        self.add_group_button.clicked.connect(lambda: self.add_group())
        add_group_layout.addWidget(self.add_group_button)
        group_layout.addWidget(add_group_frame)

        self.delete_group_button = QPushButton("Delete Group", group_frame)
        self.delete_group_button.clicked.connect(lambda: self.delete_group())
        group_layout.addWidget(self.delete_group_button)
        content_layout.addWidget(group_frame)

        label_frame = QFrame(self)
        label_layout = QVBoxLayout(label_frame)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(4)
        self.group_label = QLabel("Labels", label_frame)
        label_layout.addWidget(self.group_label)
        self.include_in_filters_checkbox = QCheckBox("Include in filters", label_frame)
        self.include_in_filters_checkbox.setToolTip(
            "Show this group's labels in the workflow and auto advance label filters."
        )
        self.include_in_filters_checkbox.toggled.connect(self.set_include_in_filters)
        label_layout.addWidget(self.include_in_filters_checkbox)
        self.label_list = QListWidget(label_frame)
        self.label_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 3px 10px;
            }
            """
        )
        label_layout.addWidget(self.label_list, 1)

        label_action_frame = QFrame(label_frame)
        label_action_layout = QHBoxLayout(label_action_frame)
        label_action_layout.setContentsMargins(0, 0, 0, 0)
        label_action_layout.setSpacing(4)
        self.add_label_button = QPushButton("Add Label", label_action_frame)
        self.add_label_button.clicked.connect(lambda: self.add_label())
        label_action_layout.addWidget(self.add_label_button)
        self.delete_label_button = QPushButton("Delete Label", label_action_frame)
        self.delete_label_button.clicked.connect(lambda: self.delete_label())
        label_action_layout.addWidget(self.delete_label_button)
        label_layout.addWidget(label_action_frame)
        content_layout.addWidget(label_frame, 1)

        self.refresh_groups()

    @property
    def current_group(self) -> str:
        item = self.group_list.currentItem()
        return item.text() if item is not None else ""

    def group_names(self) -> list[str]:
        return group_names(self.label_definitions, self.group_settings)

    def refresh_groups(self, selected_group=None):
        selected_group = selected_group or self.current_group
        names = self.group_names()
        self.group_list.blockSignals(True)
        self.group_list.clear()
        self.group_list.addItems(names)
        self.group_list.blockSignals(False)
        if names:
            row = names.index(selected_group) if selected_group in names else 0
            self.group_list.setCurrentRow(row)
        self.select_group(self.current_group)

    def select_group(self, group_name):
        group_name = str(group_name or "")
        self.group_label.setText(f"Labels in {group_name}" if group_name else "Labels")
        self.include_in_filters_checkbox.blockSignals(True)
        self.include_in_filters_checkbox.setChecked(bool(self.group_settings.get(group_name, True)))
        self.include_in_filters_checkbox.blockSignals(False)
        self.include_in_filters_checkbox.setEnabled(bool(group_name))
        self.label_list.clear()
        self.label_list.addItems(
            [definition["label"] for definition in self.label_definitions if definition["category"] == group_name]
        )
        self.label_list.doItemsLayout()
        if self.label_list.count():
            self.label_list.setCurrentRow(0)
        is_mandatory = group_name in MANDATORY_LABEL_CATEGORIES
        self.delete_group_button.setEnabled(bool(group_name) and not is_mandatory)
        self.add_label_button.setEnabled(bool(group_name))
        self.delete_label_button.setEnabled(bool(group_name))

    def set_include_in_filters(self, checked):
        group_name = self.current_group
        if not group_name:
            return
        self.group_settings[group_name] = bool(checked)
        self.changed.emit()

    def add_group(self, name=None):
        name = str(name or self.new_group_lineedit.text()).strip()
        if not name:
            Error(self, "Label group name cannot be empty.")
            return
        if name in self.group_names():
            Error(self, "That label group already exists.")
            return
        self.group_settings[name] = True
        self.new_group_lineedit.clear()
        self.refresh_groups(name)
        self.changed.emit()

    def delete_group(self, name=None):
        name = str(name or self.current_group).strip()
        if not name:
            return
        if name in MANDATORY_LABEL_CATEGORIES:
            Error(self, "Mandatory label groups cannot be deleted.")
            return
        if not Confirm(
            self,
            "Delete Label Group",
            f"Delete the label group '{name}' and all of its labels?",
            "Delete",
            "Cancel",
        ).exec():
            return
        self.label_definitions = [
            definition for definition in self.label_definitions if definition["category"] != name
        ]
        self.group_settings.pop(name, None)
        self.refresh_groups()
        self.changed.emit()

    def add_label(self, label=None):
        group_name = self.current_group
        if not group_name:
            Error(self, "Select a label group first.")
            return
        if label is None:
            label, accepted = QInputDialog.getText(self, "Add Label", f"New label for {group_name}:")
            if not accepted:
                return
        label = str(label or "").strip()
        if not label:
            Error(self, "Label cannot be empty.")
            return
        if any(
            definition["category"] == group_name and definition["label"] == label
            for definition in self.label_definitions
        ):
            Error(self, "That label already exists in this group.")
            return
        self.label_definitions.append({"category": group_name, "label": label})
        self.refresh_groups(group_name)
        matches = self.label_list.findItems(label, Qt.MatchExactly)
        if matches:
            self.label_list.setCurrentItem(matches[0])
        self.changed.emit()

    def delete_label(self, label=None):
        group_name = self.current_group
        if not group_name:
            return
        if label is None:
            item = self.label_list.currentItem()
            label = item.text() if item is not None else ""
        label = str(label or "").strip()
        if not label:
            return
        group_labels = [
            definition for definition in self.label_definitions if definition["category"] == group_name
        ]
        if group_name in MANDATORY_LABEL_CATEGORIES and len(group_labels) <= 1:
            Error(self, "Mandatory label groups must keep at least one label.")
            return
        self.label_definitions = [
            definition
            for definition in self.label_definitions
            if not (definition["category"] == group_name and definition["label"] == label)
        ]
        self.refresh_groups(group_name)
        self.changed.emit()

    def save(self):
        save_character_label_data(self.labels_path, self.label_definitions, self.group_settings)


class AllCharacterSettingsWindow(QDialog):
    """Settings that apply to every character: label groups and universal associations."""

    def __init__(self, parent=None, labels_path=None, label_associations_path=None, associations_dir=None):
        super().__init__(parent)
        self.setWindowTitle("All Character Settings")
        self.resize(820, 620)

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        sidebar = QFrame(self)
        sidebar.setFixedWidth(130)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)
        sidebar_layout.addWidget(QLabel("Settings", sidebar))
        sidebar_layout.addStretch(1)

        action_frame = QFrame(sidebar)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.save_button = QPushButton("Save", action_frame)
        self.save_button.setMinimumWidth(0)
        self.save_button.clicked.connect(self.save_and_close)
        action_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel", action_frame)
        self.cancel_button.setMinimumWidth(0)
        self.cancel_button.clicked.connect(self.reject)
        action_layout.addWidget(self.cancel_button)
        sidebar_layout.addWidget(action_frame)
        layout.addWidget(sidebar, 0, 0)

        self.tabs = QTabWidget(self)
        self.tabs.setUsesScrollButtons(False)
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
            """
        )
        layout.addWidget(self.tabs, 0, 1)
        layout.setColumnStretch(1, 1)

        self.label_group_manager = LabelGroupManager(self.tabs, labels_path)
        self.tabs.addTab(self.label_group_manager, "Label Groups")

        self.association_editor = ScopedTagAssociationEditor(
            self.tabs, associations_dir, self.label_group_manager.label_definitions
        )
        self.tabs.addTab(self.association_editor, "Universal Tag Associations")

        self.label_associations_path = label_associations_path or LABEL_ASSOCIATIONS_FILE
        self.label_association_editor = LabelAssociationListEditor(
            self.tabs, self.label_group_manager.label_definitions
        )
        self.label_association_editor.set_associations(load_label_associations(self.label_associations_path))
        self.tabs.addTab(self.label_association_editor, "Universal Label Associations")
        self.label_group_manager.changed.connect(self._refresh_label_definitions)

    def _refresh_label_definitions(self):
        definitions = self.label_group_manager.label_definitions
        self.association_editor.set_label_definitions(definitions)
        self.label_association_editor.set_label_definitions(definitions)

    def save_and_close(self):
        self.label_group_manager.save()
        self.association_editor.save()
        save_label_associations(self.label_associations_path, self.label_association_editor.associations_payload())
        refresh_character_lists_signal.mutators_changed.emit("")
        self.accept()
