from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from data.paths import OUTPUT_DIR
from process.image_curation import CurationError, load_content_tag_groups, load_content_tags, load_curation_other_tags, load_curation_outfits, load_curation_sets, load_pairing_tag_definitions, rename_curation_sets, save_content_tag_definitions, save_curation_other_tags, save_curation_outfits, save_curation_sets, save_pairing_tags
from windows.error import Error


class AssociationTagListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None, tags=None):
        super().__init__(parent)
        self.rows = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        # New tags are typed here and only appended on Add, so existing rows are never touched.
        input_frame = QFrame(self)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)
        self.input_lineedit = QLineEdit(input_frame)
        self.input_lineedit.setPlaceholderText("Add prompt tag (commas add several)")
        self.input_lineedit.returnPressed.connect(self.add_from_input)
        input_layout.addWidget(self.input_lineedit, 1)
        self.add_button = QPushButton("Add", input_frame)
        self.add_button.clicked.connect(self.add_from_input)
        input_layout.addWidget(self.add_button)
        self.layout.addWidget(input_frame)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(4)
        self.layout.addLayout(self.rows_layout)
        for tag in tags or []:
            self.add_row(str(tag), emit_changed=False)

    def add_from_input(self):
        existing_tags = {tag.lower() for tag in self.tags()}
        added = False
        for part in self.input_lineedit.text().split(","):
            tag = part.strip()
            if not tag or tag.lower() in existing_tags:
                continue
            existing_tags.add(tag.lower())
            self.add_row(tag, emit_changed=False)
            added = True
        self.input_lineedit.clear()
        self.input_lineedit.setFocus()
        if added:
            self.changed.emit()

    def add_row(self, tag="", emit_changed=True):
        row = QFrame(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        lineedit = QLineEdit(str(tag), row)
        lineedit.setPlaceholderText("Prompt tag")
        lineedit.textChanged.connect(lambda *_: self.changed.emit())
        row_layout.addWidget(lineedit, 1)
        remove_button = QPushButton("Remove", row)
        remove_button.clicked.connect(lambda: self.remove_row(row))
        row_layout.addWidget(remove_button)
        row.lineedit = lineedit
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        if emit_changed:
            self.changed.emit()

    def remove_row(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self.changed.emit()

    def tags(self):
        return [row.lineedit.text().strip() for row in self.rows if row.lineedit.text().strip()]


class ContentTagDetailEditor(QFrame):
    changed = Signal()
    delete_requested = Signal(object)

    def __init__(self, parent, definition, groups):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)
        self.header_label = QLabel(self)
        self.header_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.header_label)
        form = QFormLayout()
        self.name_lineedit = QLineEdit(str(definition.get("name") or ""), self)
        self.name_lineedit.setPlaceholderText("Content tag name")
        self.name_lineedit.textChanged.connect(self.update_header)
        self.name_lineedit.textChanged.connect(lambda *_: self.changed.emit())
        form.addRow("Name", self.name_lineedit)
        # Not editable: new groups come from "Add Group...", not from typing here.
        self.group_combobox = QComboBox(self)
        self.set_groups(groups, definition.get("category"))
        self.group_combobox.currentTextChanged.connect(lambda *_: self.changed.emit())
        form.addRow("Group", self.group_combobox)
        self.layout.addLayout(form)
        self.layout.addWidget(QLabel("Include when prompt contains", self))
        self.include_editor = AssociationTagListEditor(self, definition.get("include"))
        self.include_editor.changed.connect(self.changed.emit)
        self.layout.addWidget(self.include_editor)
        self.layout.addWidget(QLabel("Exclude when prompt contains", self))
        self.exclude_editor = AssociationTagListEditor(self, definition.get("exclude"))
        self.exclude_editor.changed.connect(self.changed.emit)
        self.layout.addWidget(self.exclude_editor)
        self.delete_button = QPushButton("Delete Content Tag", self)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self))
        self.layout.addWidget(self.delete_button)
        self.layout.addStretch(1)
        self.update_header()

    def update_header(self):
        self.header_label.setText(f"Editing: {self.name_lineedit.text().strip() or 'New Content Tag'}")

    def set_groups(self, groups, selected_group=None):
        selected_group = str(selected_group or self.group_combobox.currentText() or "General").strip() or "General"
        group_names = list(groups)
        if selected_group not in group_names:
            group_names.append(selected_group)
        self.group_combobox.blockSignals(True)
        self.group_combobox.clear()
        self.group_combobox.addItems(group_names)
        self.group_combobox.setCurrentText(selected_group)
        self.group_combobox.blockSignals(False)

    def definition(self):
        return {
            "name": self.name_lineedit.text().strip(),
            "category": self.group_combobox.currentText().strip() or "General",
            "include": self.include_editor.tags(),
            "exclude": self.exclude_editor.tags(),
        }


class ContentTagEditor(QDialog):
    def __init__(self, parent, content_tags_path, pairing_tags_path=None, outfits_path=None, sets_path=None, other_tags_path=None, output_dir=None):
        super().__init__(parent)
        self.output_dir = output_dir or OUTPUT_DIR
        # Original set name -> new name. Only applied to image manifests when the dialog is saved.
        self.set_renames = {}
        self.content_tags_path = content_tags_path
        self.pairing_tags_path = pairing_tags_path or content_tags_path.with_name("pairing_tags.json")
        self.outfits_path = outfits_path or content_tags_path.with_name("outfits.json")
        self.sets_path = sets_path or content_tags_path.with_name("sets.json")
        self.other_tags_path = other_tags_path or content_tags_path.with_name("other_tags.json")
        self.groups = load_content_tag_groups(content_tags_path)
        self.editors = []
        self.filtered_editors = []
        self.pairing_editors = {}
        self.setWindowTitle("Edit Content Tags")
        self.setMinimumSize(640, 520)
        self.build_editor()
        self.load_definitions()

    def build_editor(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)
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
        self.content_tab = QFrame(self.tabs)
        self.content_layout = QVBoxLayout(self.content_tab)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)
        self.tabs.addTab(self.content_tab, "Content Tags")
        self.pairing_tab = QFrame(self.tabs)
        self.pairing_layout = QVBoxLayout(self.pairing_tab)
        self.pairing_layout.setContentsMargins(0, 0, 0, 0)
        self.pairing_layout.setSpacing(6)
        self.tabs.addTab(self.pairing_tab, "Pairing Tags")
        self.outfits_tab = QFrame(self.tabs)
        self.tabs.addTab(self.outfits_tab, "Generic Outfits")
        self.sets_tab = QFrame(self.tabs)
        self.tabs.addTab(self.sets_tab, "Sets")
        self.other_tags_tab = QFrame(self.tabs)
        self.tabs.addTab(self.other_tags_tab, "Other Tags")
        self.layout.addWidget(self.tabs, 1)

        content_layout = QHBoxLayout()

        # Left column: find existing tags (top) and add new ones (bottom).
        left_frame = QFrame(self.content_tab)
        left_frame.setFixedWidth(210)
        tag_list_layout = QVBoxLayout(left_frame)
        tag_list_layout.setContentsMargins(0, 0, 0, 0)
        tag_list_layout.setSpacing(4)
        tag_list_layout.addWidget(QLabel("Content Tags", left_frame))
        self.group_filter_combobox = QComboBox(left_frame)
        self.group_filter_combobox.currentTextChanged.connect(self.on_group_filter_changed)
        tag_list_layout.addWidget(self.group_filter_combobox)
        self.tag_list = QListWidget(left_frame)
        self.tag_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 5px 8px;
                margin: 2px 4px;
            }
            """
        )
        self.tag_list.currentRowChanged.connect(self.select_tag)
        tag_list_layout.addWidget(self.tag_list, 1)

        self.new_tag_frame = QFrame(left_frame)
        self.new_tag_frame.setObjectName("newContentTagFrame")
        self.new_tag_frame.setStyleSheet("QFrame#newContentTagFrame { border: 1px solid #555; }")
        new_tag_layout = QVBoxLayout(self.new_tag_frame)
        new_tag_layout.setContentsMargins(6, 6, 6, 6)
        new_tag_layout.setSpacing(4)
        new_tag_layout.addWidget(QLabel("New Content Tag", self.new_tag_frame))
        new_tag_form = QFormLayout()
        self.new_tag_name_lineedit = QLineEdit(self.new_tag_frame)
        self.new_tag_name_lineedit.setPlaceholderText("New tag name")
        self.new_tag_name_lineedit.returnPressed.connect(self.add_tag)
        new_tag_form.addRow("Name", self.new_tag_name_lineedit)
        self.new_tag_group_combobox = QComboBox(self.new_tag_frame)
        new_tag_form.addRow("Group", self.new_tag_group_combobox)
        new_tag_layout.addLayout(new_tag_form)
        self.add_tag_button = QPushButton("Add Content Tag", self.new_tag_frame)
        self.add_tag_button.clicked.connect(self.add_tag)
        new_tag_layout.addWidget(self.add_tag_button)
        self.add_group_button = QPushButton("Add Group...", self.new_tag_frame)
        self.add_group_button.clicked.connect(self.add_group)
        new_tag_layout.addWidget(self.add_group_button)
        tag_list_layout.addWidget(self.new_tag_frame)
        content_layout.addWidget(left_frame)

        # Right column: edits the selected tag only.
        self.tag_stack = QStackedWidget(self)
        self.empty_page = QLabel("Select a content tag to edit, or add one on the left.", self.tag_stack)
        self.empty_page.setAlignment(Qt.AlignCenter)
        self.tag_stack.addWidget(self.empty_page)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.tag_stack)
        content_layout.addWidget(scroll_area, 1)
        self.content_layout.addLayout(content_layout, 1)
        self.build_pairing_editor()
        self.build_named_list_editor(self.outfits_tab, "Add Generic Outfit", load_curation_outfits(self.outfits_path), "outfit")
        self.outfits_list = self.named_list
        self.build_named_list_editor(self.sets_tab, "Add Set", load_curation_sets(self.sets_path), "set")
        self.sets_list = self.named_list
        self.rename_set_button = QPushButton("Rename Set", self.sets_tab)
        self.rename_set_button.clicked.connect(self.rename_set)
        self.named_list_button_layout.insertWidget(1, self.rename_set_button)
        self.build_named_list_editor(self.other_tags_tab, "Add Other Tag", load_curation_other_tags(self.other_tags_path), "other tag")
        self.other_tags_list = self.named_list

        footer_frame = QFrame(self)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch(1)
        self.save_button = QPushButton("Save", footer_frame)
        self.save_button.clicked.connect(self.save)
        footer_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel", footer_frame)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_button)
        self.layout.addWidget(footer_frame)

    def build_named_list_editor(self, tab, add_button_text, values, item_name):
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        named_list = QListWidget(tab)
        for value in values:
            item = QListWidgetItem(value)
            item.setSizeHint(QSize(0, 36))
            named_list.addItem(item)
        layout.addWidget(named_list, 1)
        button_frame = QFrame(tab)
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        add_button = QPushButton(add_button_text, button_frame)
        add_button.clicked.connect(lambda: self.add_named_list_item(named_list, item_name))
        button_layout.addWidget(add_button)
        delete_button = QPushButton(f"Delete {item_name.title()}", button_frame)
        delete_button.clicked.connect(lambda: self.delete_named_list_item(named_list))
        button_layout.addWidget(delete_button)
        layout.addWidget(button_frame)
        self.named_list = named_list
        self.named_list_button_layout = button_layout

    def add_named_list_item(self, named_list, item_name):
        value, accepted = QInputDialog.getText(self, f"Add {item_name.title()}", f"{item_name.title()} name:")
        value = value.strip()
        if not accepted or not value:
            return
        if any(named_list.item(index).text() == value for index in range(named_list.count())):
            Error(self, f"That {item_name} already exists.")
            return
        item = QListWidgetItem(value)
        item.setSizeHint(QSize(0, 36))
        named_list.addItem(item)
        named_list.setCurrentItem(item)

    def rename_set(self):
        item = self.sets_list.currentItem()
        if item is None:
            Error(self, "Select a set to rename.")
            return
        current_name = item.text()
        new_name, accepted = QInputDialog.getText(self, "Rename Set", "New set name:", text=current_name)
        new_name = new_name.strip()
        if not accepted or not new_name or new_name == current_name:
            return
        if any(self.sets_list.item(index).text() == new_name for index in range(self.sets_list.count())):
            Error(self, "That set already exists.")
            return
        item.setText(new_name)
        # Renaming twice before saving still maps the name images use today to the final name.
        original_name = next((old for old, renamed in self.set_renames.items() if renamed == current_name), current_name)
        if original_name == new_name:
            self.set_renames.pop(original_name, None)
        else:
            self.set_renames[original_name] = new_name

    def delete_named_list_item(self, named_list):
        selected_index = named_list.currentRow()
        if selected_index >= 0:
            named_list.takeItem(selected_index)

    def build_pairing_editor(self):
        pairing_content_layout = QHBoxLayout()
        pairing_button_frame = QFrame(self.pairing_tab)
        pairing_button_layout = QHBoxLayout(pairing_button_frame)
        pairing_button_layout.setContentsMargins(0, 0, 0, 0)
        add_pairing_label_button = QPushButton("Add Pairing Tag", pairing_button_frame)
        add_pairing_label_button.clicked.connect(self.add_pairing_label)
        pairing_button_layout.addWidget(add_pairing_label_button)
        delete_pairing_label_button = QPushButton("Delete Pairing Tag", pairing_button_frame)
        delete_pairing_label_button.clicked.connect(self.delete_pairing_label)
        pairing_button_layout.addWidget(delete_pairing_label_button)
        self.pairing_list = QListWidget(self.pairing_tab)
        self.pairing_list.setFixedWidth(150)
        self.pairing_list.setStyleSheet(
            """
            QListWidget::item {
                padding: 5px 8px;
                margin: 2px 4px;
            }
            """
        )
        self.pairing_list.currentRowChanged.connect(self.select_pairing_label)
        pairing_content_layout.addWidget(self.pairing_list)
        self.pairing_stack = QStackedWidget(self.pairing_tab)
        pairing_scroll_area = QScrollArea(self.pairing_tab)
        pairing_scroll_area.setWidgetResizable(True)
        pairing_scroll_area.setWidget(self.pairing_stack)
        pairing_content_layout.addWidget(pairing_scroll_area, 1)
        self.pairing_layout.addLayout(pairing_content_layout, 1)
        self.pairing_layout.addWidget(pairing_button_frame)

        pairing_definitions = load_pairing_tag_definitions(self.pairing_tags_path)
        for label, definition in pairing_definitions.items():
            self.add_pairing_definition(label, definition)
        self.pairing_list.setCurrentRow(0)

    def add_pairing_definition(self, label, definition):
        tag_editor = AssociationTagListEditor(self.pairing_stack, definition["tags"])
        tag_frame = QFrame(self.pairing_stack)
        tag_layout = QVBoxLayout(tag_frame)
        tag_layout.setContentsMargins(6, 6, 6, 6)
        tag_layout.setSpacing(6)
        tag_layout.addWidget(QLabel(f"Recognize {label} when prompt contains", tag_frame))
        priority_frame = QFrame(tag_frame)
        priority_layout = QHBoxLayout(priority_frame)
        priority_layout.setContentsMargins(0, 0, 0, 0)
        priority_layout.addWidget(QLabel("Export Priority", priority_frame))
        priority_spinbox = QSpinBox(priority_frame)
        priority_spinbox.setRange(0, 9999)
        priority_spinbox.setValue(int(definition["priority"]))
        priority_layout.addWidget(priority_spinbox)
        tag_layout.addWidget(priority_frame)
        tag_layout.addWidget(tag_editor)
        tag_layout.addStretch(1)
        self.pairing_editors[label] = (tag_editor, priority_spinbox)
        self.pairing_stack.addWidget(tag_frame)
        item = QListWidgetItem(label)
        item.setSizeHint(QSize(0, 36))
        self.pairing_list.addItem(item)

    def add_pairing_label(self):
        label, accepted = QInputDialog.getText(self, "Add Pairing Tag", "Pairing tag name:")
        label = label.strip()
        if not accepted or not label:
            return
        if label in self.pairing_editors:
            Error(self, "That pairing tag already exists.")
            return
        self.add_pairing_definition(label, {"tags": [], "priority": 100})
        self.pairing_list.setCurrentRow(self.pairing_list.count() - 1)

    def delete_pairing_label(self):
        selected_index = self.pairing_list.currentRow()
        if not 0 <= selected_index < self.pairing_list.count():
            return
        label = self.pairing_list.item(selected_index).text()
        tag_editor, _ = self.pairing_editors.pop(label)
        tag_frame = tag_editor.parent()
        self.pairing_stack.removeWidget(tag_frame)
        tag_frame.deleteLater()
        self.pairing_list.takeItem(selected_index)
        if self.pairing_list.count():
            self.pairing_list.setCurrentRow(min(selected_index, self.pairing_list.count() - 1))

    def keyPressEvent(self, event):
        # Enter is used by the add inputs; never let it trigger the dialog's default button.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            return
        super().keyPressEvent(event)

    def load_definitions(self):
        for definition in load_content_tags(self.content_tags_path):
            self.add_definition(definition)
        self.refresh_groups()
        self.refresh_group_filter()

    def add_group(self):
        group_name, accepted = QInputDialog.getText(self, "Add Content Tag Group", "Content tag group name:")
        if not accepted or not group_name.strip():
            return
        group_name = group_name.strip()
        if group_name in self.groups:
            Error(self, "That content tag group already exists.")
            return
        self.groups.append(group_name)
        self.refresh_groups()
        self.new_tag_group_combobox.setCurrentText(group_name)
        self.refresh_group_filter()

    def add_tag(self):
        name = self.new_tag_name_lineedit.text().strip()
        if not name:
            Error(self, "Enter a name for the new content tag.")
            return
        if any(editor.name_lineedit.text().strip() == name for editor in self.editors):
            Error(self, "That content tag already exists.")
            return
        group_name = self.new_tag_group_combobox.currentText().strip() or "General"
        if group_name not in self.groups:
            self.groups.append(group_name)
            self.refresh_groups()

        editor = self.add_definition({"name": name, "category": group_name, "include": [], "exclude": []})
        # Always show the new tag: keep the filter only if it already includes the new tag's group.
        filter_group = self.group_filter_combobox.currentText()
        self.tag_stack.setCurrentWidget(editor)
        self.refresh_group_filter(filter_group if filter_group in {"", "All Groups", group_name} else group_name)
        self.new_tag_name_lineedit.clear()
        editor.include_editor.input_lineedit.setFocus()

    def add_definition(self, definition):
        editor = ContentTagDetailEditor(self.tag_stack, definition, self.groups)
        editor.changed.connect(self.refresh_tag_list)
        editor.delete_requested.connect(self.delete_tag)
        self.editors.append(editor)
        self.tag_stack.addWidget(editor)
        self.refresh_tag_list()
        return editor

    def refresh_groups(self):
        for editor in self.editors:
            editor.set_groups(self.groups)
        selected_group = self.new_tag_group_combobox.currentText()
        self.new_tag_group_combobox.blockSignals(True)
        self.new_tag_group_combobox.clear()
        self.new_tag_group_combobox.addItems(self.groups)
        if selected_group in self.groups:
            self.new_tag_group_combobox.setCurrentText(selected_group)
        self.new_tag_group_combobox.blockSignals(False)

    def on_group_filter_changed(self, group_name):
        # New tags default to the group being browsed.
        if group_name in self.groups:
            self.new_tag_group_combobox.setCurrentText(group_name)
        self.filter_tags()

    def refresh_group_filter(self, selected_group=None):
        if selected_group is None:
            selected_group = self.group_filter_combobox.currentText()
        groups = list(self.groups)
        for editor in self.editors:
            group_name = editor.group_combobox.currentText().strip()
            if group_name and group_name not in groups:
                groups.append(group_name)
        self.group_filter_combobox.blockSignals(True)
        self.group_filter_combobox.clear()
        self.group_filter_combobox.addItem("All Groups")
        self.group_filter_combobox.addItems(groups)
        self.group_filter_combobox.setCurrentText(selected_group if selected_group in groups else "All Groups")
        self.group_filter_combobox.blockSignals(False)
        self.filter_tags()

    def refresh_tag_list(self):
        selected_editor = self.tag_stack.currentWidget()
        filter_group = self.group_filter_combobox.currentText()
        if selected_editor in self.editors and filter_group not in {"", "All Groups"}:
            editor_group = selected_editor.group_combobox.currentText().strip()
            if editor_group != filter_group:
                # The selected tag was moved to another group: follow it instead of jumping to a different tag.
                self.refresh_group_filter(editor_group)
                return
        self.refresh_group_filter()

    def filter_tags(self):
        selected_editor = self.tag_stack.currentWidget()
        selected_group = self.group_filter_combobox.currentText()
        self.filtered_editors = [
            editor
            for editor in self.editors
            if selected_group in {"", "All Groups"} or editor.group_combobox.currentText().strip() == selected_group
        ]
        if selected_editor in self.filtered_editors:
            selected_row = self.filtered_editors.index(selected_editor)
        else:
            selected_row = 0 if self.filtered_editors else -1
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for editor in self.filtered_editors:
            item = QListWidgetItem(editor.name_lineedit.text().strip() or "New Content Tag")
            item.setSizeHint(QSize(0, 36))
            self.tag_list.addItem(item)
        self.tag_list.setCurrentRow(selected_row)
        self.tag_list.blockSignals(False)
        self.select_tag(selected_row)

    def select_tag(self, index):
        if 0 <= index < len(self.filtered_editors):
            self.tag_stack.setCurrentWidget(self.filtered_editors[index])
        else:
            self.tag_stack.setCurrentWidget(self.empty_page)

    def select_pairing_label(self, index):
        if 0 <= index < self.pairing_stack.count():
            self.pairing_stack.setCurrentIndex(index)

    def delete_tag(self, editor):
        if editor not in self.editors:
            return
        # Move the selection to a neighbouring visible tag before removing this one.
        if editor in self.filtered_editors:
            remaining_editors = [other for other in self.filtered_editors if other is not editor]
            index = self.filtered_editors.index(editor)
            if remaining_editors:
                self.tag_stack.setCurrentWidget(remaining_editors[min(index, len(remaining_editors) - 1)])
            else:
                self.tag_stack.setCurrentWidget(self.empty_page)
        self.editors.remove(editor)
        self.tag_stack.removeWidget(editor)
        editor.deleteLater()
        self.refresh_group_filter()

    def save(self):
        try:
            save_content_tag_definitions(self.content_tags_path, self.groups, [editor.definition() for editor in self.editors])
            save_pairing_tags(
                self.pairing_tags_path,
                {label: editor.tags() for label, (editor, _) in self.pairing_editors.items()},
                {label: priority.value() for label, (_, priority) in self.pairing_editors.items()},
            )
            save_curation_outfits(
                self.outfits_path,
                [self.outfits_list.item(index).text() for index in range(self.outfits_list.count())],
            )
            save_curation_sets(
                self.sets_path,
                [self.sets_list.item(index).text() for index in range(self.sets_list.count())],
            )
            rename_curation_sets(self.output_dir, self.set_renames)
            save_curation_other_tags(
                self.other_tags_path,
                [self.other_tags_list.item(index).text() for index in range(self.other_tags_list.count())],
            )
        except CurationError as exc:
            Error(self, str(exc))
            return
        self.accept()