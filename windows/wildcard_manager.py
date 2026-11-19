import json
import re
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSettings, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data import datahub
from data.paths import WILDCARDS_DIR
from windows.confirmation import Confirm
from windows.error import Error


WILDCARD_REFERENCE_PATTERN = re.compile(r"\*([^*]+)\*")
WILDCARD_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9 _-]*")
NEW_WILDCARD_LABEL = "New Wildcard"
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def normalize_wildcard_id(wildcard_id: str) -> str:
    return str(wildcard_id or "").strip().lower()


def validate_wildcard_id(
    wildcard_id: str,
    existing_ids: set[str],
    previous_id: str | None = None,
) -> str | None:
    normalized_id = normalize_wildcard_id(wildcard_id)
    normalized_previous_id = normalize_wildcard_id(previous_id)
    normalized_existing_ids = {normalize_wildcard_id(item) for item in existing_ids}

    if not normalized_id:
        return "Wildcard ID cannot be empty."
    if not WILDCARD_ID_PATTERN.fullmatch(normalized_id):
        return "Wildcard ID may only contain letters, numbers, spaces, underscores, and hyphens."
    if normalized_id in WINDOWS_RESERVED_NAMES:
        return "Wildcard ID is reserved by Windows."
    if normalized_id != normalized_previous_id and normalized_id in normalized_existing_ids:
        return "Wildcard ID must be unique."
    return None


def normalize_wildcard_references(text: str) -> str:
    def replace_reference(match):
        return f"*{normalize_wildcard_id(match.group(1))}*"

    return WILDCARD_REFERENCE_PATTERN.sub(replace_reference, str(text or "").strip())


def normalize_wildcard_document(wildcard_id: str, document) -> dict:
    normalized_id = normalize_wildcard_id(wildcard_id)
    values = document.get("values", []) if isinstance(document, dict) else []
    normalized_values = []

    if isinstance(values, list):
        for entry in values:
            if not isinstance(entry, dict):
                continue
            text = normalize_wildcard_references(entry.get("text", ""))
            if not text:
                continue
            raw_weight = entry.get("weight", 1)
            if isinstance(raw_weight, bool):
                continue
            try:
                numeric_weight = float(raw_weight)
            except (TypeError, ValueError):
                continue
            weight = int(numeric_weight)
            if numeric_weight != weight or weight <= 0:
                continue
            normalized_values.append({"text": text, "weight": weight})

    return {
        "trigger": normalized_id,
        "values": normalized_values,
    }


def load_wildcard_documents(directory: Path) -> dict[str, dict]:
    directory = Path(directory)
    documents = {}
    if not directory.exists():
        return documents

    for json_path in sorted(directory.glob("*.json"), key=lambda path: path.name.lower()):
        try:
            document = json.loads(json_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        wildcard_id = normalize_wildcard_id(json_path.stem)
        if not wildcard_id:
            continue
        documents[wildcard_id] = normalize_wildcard_document(wildcard_id, document)
    return documents


def extract_wildcard_references(text: str) -> set[str]:
    return {
        normalize_wildcard_id(match.group(1))
        for match in WILDCARD_REFERENCE_PATTERN.finditer(str(text or ""))
        if normalize_wildcard_id(match.group(1))
    }


def _wildcard_reference_graph(wildcards: dict[str, dict]) -> dict[str, set[str]]:
    wildcard_ids = {normalize_wildcard_id(wildcard_id) for wildcard_id in wildcards}
    graph = {}
    for wildcard_id, document in wildcards.items():
        normalized_id = normalize_wildcard_id(wildcard_id)
        references = set()
        for entry in document.get("values", []) if isinstance(document, dict) else []:
            if isinstance(entry, dict):
                references.update(extract_wildcard_references(entry.get("text", "")))
        graph[normalized_id] = references.intersection(wildcard_ids)
    return graph


def find_missing_wildcard_references(wildcards: dict[str, dict]) -> dict[str, list[str]]:
    wildcard_ids = {normalize_wildcard_id(wildcard_id) for wildcard_id in wildcards}
    missing_by_wildcard = {}

    for wildcard_id, document in wildcards.items():
        missing = set()
        for entry in document.get("values", []) if isinstance(document, dict) else []:
            if isinstance(entry, dict):
                missing.update(extract_wildcard_references(entry.get("text", "")) - wildcard_ids)
        if missing:
            missing_by_wildcard[normalize_wildcard_id(wildcard_id)] = sorted(missing)

    return missing_by_wildcard


def find_wildcard_cycles(wildcards: dict[str, dict]) -> list[list[str]]:
    graph = _wildcard_reference_graph(wildcards)
    visited = set()
    active = []
    active_set = set()
    cycle_keys = set()
    cycles = []

    def record_cycle(cycle):
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        canonical_body = min(rotations)
        if canonical_body in cycle_keys:
            return
        cycle_keys.add(canonical_body)
        cycles.append(list(canonical_body) + [canonical_body[0]])

    def visit(wildcard_id):
        if wildcard_id in active_set:
            cycle_start = active.index(wildcard_id)
            record_cycle(active[cycle_start:] + [wildcard_id])
            return
        if wildcard_id in visited:
            return

        active.append(wildcard_id)
        active_set.add(wildcard_id)
        for referenced_id in sorted(graph.get(wildcard_id, set())):
            visit(referenced_id)
        active.pop()
        active_set.remove(wildcard_id)
        visited.add(wildcard_id)

    for wildcard_id in sorted(graph):
        visit(wildcard_id)

    return sorted(cycles)


class WildcardValueRow(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, parent=None, value=None):
        super().__init__(parent)
        self.setObjectName("wildcardValueRow")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)

        self.text_edit = QTextEdit(self)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("Replacement text; nested wildcards use *name*")
        self.text_edit.setMinimumHeight(72)
        self.layout.addWidget(self.text_edit, 1)

        controls = QFrame(self)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)
        self.weight_spinbox = QSpinBox(controls)
        self.weight_spinbox.setRange(1, 999999)
        self.weight_spinbox.setPrefix("Weight: ")
        controls_layout.addWidget(self.weight_spinbox)
        self.remove_button = QPushButton("Remove", controls)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        controls_layout.addWidget(self.remove_button)
        controls_layout.addStretch(1)
        self.layout.addWidget(controls)

        self.text_edit.textChanged.connect(self.changed.emit)
        self.weight_spinbox.valueChanged.connect(lambda _value: self.changed.emit())
        self.set_value(value or {"text": "", "weight": 1})

    def set_value(self, value):
        text_blocker = QSignalBlocker(self.text_edit)
        weight_blocker = QSignalBlocker(self.weight_spinbox)
        self.text_edit.setPlainText(str(value.get("text", "")))
        try:
            weight = int(value.get("weight", 1))
        except (TypeError, ValueError):
            weight = 1
        self.weight_spinbox.setValue(max(1, weight))
        del text_blocker
        del weight_blocker

    def value(self):
        return {
            "text": normalize_wildcard_references(self.text_edit.toPlainText()),
            "weight": self.weight_spinbox.value(),
        }


class WildcardValueListEditor(QFrame):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.rows_widget = QWidget(self.scroll_area)
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(6)
        self.rows_layout.addStretch(1)
        self.scroll_area.setWidget(self.rows_widget)
        self.layout.addWidget(self.scroll_area, 1)

        self.add_value_button = QPushButton("Add Value", self)
        self.add_value_button.clicked.connect(lambda: self.add_row())
        self.layout.addWidget(self.add_value_button)
        self.set_values([])

    def clear_rows(self):
        for row in self.rows:
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.rows.clear()

    def add_row(self, value=None, emit_changed=True):
        row = WildcardValueRow(self.rows_widget, value)
        row.changed.connect(self.changed.emit)
        row.remove_requested.connect(self.remove_row)
        self.rows.append(row)
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        if emit_changed:
            self.changed.emit()
        return row

    def remove_row(self, row):
        if row not in self.rows:
            return
        if len(self.rows) == 1:
            row.set_value({"text": "", "weight": 1})
        else:
            self.rows.remove(row)
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self.changed.emit()

    def set_values(self, values):
        blocker = QSignalBlocker(self)
        self.clear_rows()
        for value in values or []:
            if isinstance(value, dict):
                self.add_row(value, emit_changed=False)
        if not self.rows:
            self.add_row(emit_changed=False)
        del blocker

    def values(self):
        return [value for row in self.rows if (value := row.value())["text"]]


class ManageWildcardWindow(QDialog):
    LAST_WILDCARD_SETTING = "wildcard_manager/last_wildcard_id"

    def __init__(
        self,
        parent=None,
        wildcards_dir=None,
        reload_callback=None,
        settings=None,
    ):
        super().__init__(parent)
        self.setObjectName("wildcardManager")
        self.setWindowTitle("Manage Wildcards")
        self.resize(780, 650)
        self.setStyleSheet(
            """
            QDialog#wildcardManager QFrame {
                background: transparent;
                border: none;
            }
            QDialog#wildcardManager QLabel {
                background: transparent;
                border: none;
            }
            QDialog#wildcardManager QFrame#wildcardManagerSidebar {
                background: #272833;
                border: 1px solid #444;
            }
            QDialog#wildcardManager QFrame#wildcardValueRow {
                background: #21222C;
                border: 1px solid #444;
            }
            QDialog#wildcardManager QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

        self.wildcards_dir = Path(wildcards_dir) if wildcards_dir is not None else Path(WILDCARDS_DIR)
        self.reload_callback = reload_callback if reload_callback is not None else datahub.load_wildcards
        self.settings = settings if settings is not None else QSettings("NAI_UI_2", "NAI_UI_2")
        if wildcards_dir is None:
            datahub.load_wildcards()
            loaded_wildcards = datahub.get_wildcard_map()
            self.wildcards = {
                normalize_wildcard_id(wildcard_id): normalize_wildcard_document(wildcard_id, document)
                for wildcard_id, document in loaded_wildcards.items()
            }
        else:
            self.wildcards = load_wildcard_documents(self.wildcards_dir)

        self.original_paths = {
            normalize_wildcard_id(path.stem): path
            for path in self.wildcards_dir.glob("*.json")
            if normalize_wildcard_id(path.stem)
        } if self.wildcards_dir.exists() else {}
        self.deleted_wildcard_ids = set()
        self.current_wildcard_id = None
        self.new_wildcard = normalize_wildcard_document("", {})
        self.new_wildcard_active = False
        self.draft_previous_wildcard_id = None
        self.loading_wildcard = False

        self.build_manager()
        self.refresh_wildcard_selector()
        last_wildcard_id = normalize_wildcard_id(
            self.settings.value(self.LAST_WILDCARD_SETTING, "")
        )
        initial_id = (
            last_wildcard_id
            if last_wildcard_id in self.wildcards
            else next(iter(sorted(self.wildcards)), None)
        )
        self.select_wildcard(initial_id)

    def build_manager(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(8)

        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("wildcardManagerSidebar")
        self.sidebar.setFixedWidth(150)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(6, 6, 6, 6)
        self.sidebar_layout.setSpacing(6)
        self.grid.addWidget(self.sidebar, 0, 0)

        self.sidebar_layout.addWidget(QLabel("Wildcard", self.sidebar))
        self.wildcard_select_combobox = QComboBox(self.sidebar)
        self.wildcard_select_combobox.currentIndexChanged.connect(self.on_wildcard_change)
        self.sidebar_layout.addWidget(self.wildcard_select_combobox)

        self.new_wildcard_button = QPushButton("New", self.sidebar)
        self.new_wildcard_button.clicked.connect(self.new_wildcard_draft)
        self.sidebar_layout.addWidget(self.new_wildcard_button)
        self.copy_wildcard_button = QPushButton("Copy", self.sidebar)
        self.copy_wildcard_button.clicked.connect(self.copy_wildcard)
        self.sidebar_layout.addWidget(self.copy_wildcard_button)
        self.delete_wildcard_button = QPushButton("Delete", self.sidebar)
        self.delete_wildcard_button.clicked.connect(self.delete_wildcard)
        self.sidebar_layout.addWidget(self.delete_wildcard_button)
        self.sidebar_layout.addStretch(1)

        action_frame = QFrame(self.sidebar)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)
        self.save_button = QPushButton("Save", action_frame)
        self.save_button.clicked.connect(self.save_and_close)
        action_layout.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel", action_frame)
        self.cancel_button.clicked.connect(self.reject)
        action_layout.addWidget(self.cancel_button)
        self.sidebar_layout.addWidget(action_frame)

        detail_frame = QFrame(self)
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(8, 8, 8, 8)
        detail_layout.setSpacing(6)
        self.grid.addWidget(detail_frame, 0, 1)
        self.grid.setColumnStretch(1, 1)

        id_frame = QFrame(detail_frame)
        id_layout = QGridLayout(id_frame)
        id_layout.setContentsMargins(0, 0, 0, 0)
        id_layout.setSpacing(6)
        id_label = QLabel('Wildcard ID <span style="color: #e53935;">*</span>', id_frame)
        id_layout.addWidget(id_label, 0, 0)
        self.wildcard_id_lineedit = QLineEdit(id_frame)
        self.wildcard_id_lineedit.setPlaceholderText("Lowercase wildcard ID")
        self.wildcard_id_lineedit.setProperty("lockedWildcardId", False)
        self.wildcard_id_lineedit.setStyleSheet(
            'QLineEdit[lockedWildcardId="true"] { color: #888888; }'
        )
        id_layout.addWidget(self.wildcard_id_lineedit, 0, 1)
        id_layout.addWidget(QLabel("Token", id_frame), 1, 0)
        self.token_preview_label = QLabel("**", id_frame)
        self.token_preview_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        id_layout.addWidget(self.token_preview_label, 1, 1)
        id_layout.setColumnStretch(1, 1)
        detail_layout.addWidget(id_frame)

        self.missing_reference_label = QLabel("", detail_frame)
        self.missing_reference_label.setWordWrap(True)
        self.missing_reference_label.setStyleSheet("color: #e0a030;")
        detail_layout.addWidget(self.missing_reference_label)

        values_label = QLabel("Weighted Values", detail_frame)
        values_label.setStyleSheet("font-weight: bold;")
        detail_layout.addWidget(values_label)
        self.value_editor = WildcardValueListEditor(detail_frame)
        self.value_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        detail_layout.addWidget(self.value_editor, 1)

        self.wildcard_id_lineedit.textChanged.connect(self.on_form_changed)
        self.value_editor.changed.connect(self.on_form_changed)
        self.update_draft_buttons()

    def refresh_wildcard_selector(self):
        blocker = QSignalBlocker(self.wildcard_select_combobox)
        self.wildcard_select_combobox.clear()
        if self.new_wildcard_active:
            self.wildcard_select_combobox.addItem(NEW_WILDCARD_LABEL, None)
        for wildcard_id in sorted(self.wildcards):
            self.wildcard_select_combobox.addItem(wildcard_id, wildcard_id)
        index = self.wildcard_select_combobox.findData(self.current_wildcard_id)
        self.wildcard_select_combobox.setCurrentIndex(
            index if index >= 0 else (0 if self.wildcard_select_combobox.count() else -1)
        )
        del blocker

    def on_wildcard_change(self):
        if self.loading_wildcard:
            return
        self.store_current_wildcard_from_form()
        self.select_wildcard(self.wildcard_select_combobox.currentData())

    def select_wildcard(self, wildcard_id):
        self.current_wildcard_id = wildcard_id
        index = self.wildcard_select_combobox.findData(wildcard_id)
        if index >= 0 and index != self.wildcard_select_combobox.currentIndex():
            blocker = QSignalBlocker(self.wildcard_select_combobox)
            self.wildcard_select_combobox.setCurrentIndex(index)
            del blocker
        document = (
            self.wildcards.get(wildcard_id, normalize_wildcard_document("", {}))
            if wildcard_id is not None
            else self.new_wildcard
        )
        self.load_wildcard_into_form(document)
        is_existing = wildcard_id is not None
        self.wildcard_id_lineedit.setReadOnly(is_existing)
        self.wildcard_id_lineedit.setProperty("lockedWildcardId", is_existing)
        self.wildcard_id_lineedit.style().unpolish(self.wildcard_id_lineedit)
        self.wildcard_id_lineedit.style().polish(self.wildcard_id_lineedit)
        self.copy_wildcard_button.setEnabled(is_existing or self.new_wildcard_active)
        self.delete_wildcard_button.setEnabled(is_existing)
        self.refresh_missing_reference_warning()

    def load_wildcard_into_form(self, document):
        self.loading_wildcard = True
        id_blocker = QSignalBlocker(self.wildcard_id_lineedit)
        editor_blocker = QSignalBlocker(self.value_editor)
        self.wildcard_id_lineedit.setText(str(document.get("trigger", "")))
        self.value_editor.set_values(document.get("values", []))
        del id_blocker
        del editor_blocker
        self.loading_wildcard = False
        self.update_token_preview()

    def form_wildcard(self):
        wildcard_id = normalize_wildcard_id(self.wildcard_id_lineedit.text())
        return normalize_wildcard_document(
            wildcard_id,
            {"values": self.value_editor.values()},
        )

    def store_current_wildcard_from_form(self):
        if self.loading_wildcard:
            return
        document = self.form_wildcard()
        if self.current_wildcard_id is None:
            self.new_wildcard = document
        elif self.current_wildcard_id in self.wildcards:
            self.wildcards[self.current_wildcard_id] = document

    def on_form_changed(self):
        if self.loading_wildcard:
            return
        self.update_token_preview()
        self.store_current_wildcard_from_form()
        self.refresh_missing_reference_warning()

    def update_token_preview(self):
        wildcard_id = normalize_wildcard_id(self.wildcard_id_lineedit.text())
        self.token_preview_label.setText(f"*{wildcard_id}*" if wildcard_id else "**")

    def documents_with_draft(self):
        documents = deepcopy(self.wildcards)
        if self.new_wildcard_active:
            wildcard_id = normalize_wildcard_id(self.new_wildcard.get("trigger", ""))
            if wildcard_id:
                documents[wildcard_id] = deepcopy(self.new_wildcard)
        return documents

    def refresh_missing_reference_warning(self):
        missing = find_missing_wildcard_references(self.documents_with_draft())
        if not missing:
            self.missing_reference_label.clear()
            return
        details = "; ".join(
            f"{wildcard_id}: {', '.join(references)}"
            for wildcard_id, references in sorted(missing.items())
        )
        self.missing_reference_label.setText(f"Missing wildcard references: {details}")

    def new_wildcard_draft(self):
        if self.new_wildcard_active:
            self.save_wildcard_draft()
            return
        self.store_current_wildcard_from_form()
        self.draft_previous_wildcard_id = self.current_wildcard_id
        self.new_wildcard = normalize_wildcard_document("", {})
        self.new_wildcard_active = True
        self.current_wildcard_id = None
        self.wildcard_select_combobox.setEnabled(False)
        self.refresh_wildcard_selector()
        self.select_wildcard(None)
        self.update_draft_buttons()

    def save_wildcard_draft(self):
        self.store_current_wildcard_from_form()
        wildcard_id = normalize_wildcard_id(self.new_wildcard.get("trigger", ""))
        validation_error = validate_wildcard_id(wildcard_id, set(self.wildcards))
        if validation_error:
            Error(self, validation_error)
            return False
        if not self.new_wildcard.get("values"):
            Error(self, "Wildcard must contain at least one nonempty value.")
            return False

        self.new_wildcard["trigger"] = wildcard_id
        self.wildcards[wildcard_id] = deepcopy(self.new_wildcard)
        self.new_wildcard = normalize_wildcard_document("", {})
        self.new_wildcard_active = False
        self.draft_previous_wildcard_id = None
        self.current_wildcard_id = wildcard_id
        self.wildcard_select_combobox.setEnabled(True)
        self.refresh_wildcard_selector()
        self.select_wildcard(wildcard_id)
        self.update_draft_buttons()
        return True

    def cancel_wildcard_draft(self):
        if not self.new_wildcard_active:
            return
        previous_id = self.draft_previous_wildcard_id
        self.new_wildcard = normalize_wildcard_document("", {})
        self.new_wildcard_active = False
        self.draft_previous_wildcard_id = None
        self.current_wildcard_id = previous_id if previous_id in self.wildcards else next(iter(sorted(self.wildcards)), None)
        self.wildcard_select_combobox.setEnabled(True)
        self.refresh_wildcard_selector()
        self.select_wildcard(self.current_wildcard_id)
        self.update_draft_buttons()

    def update_draft_buttons(self):
        if self.new_wildcard_active:
            self.new_wildcard_button.setText("Save Wildcard")
            self.copy_wildcard_button.setText("Cancel Wildcard")
            self.copy_wildcard_button.setEnabled(True)
            self.delete_wildcard_button.setVisible(False)
        else:
            self.new_wildcard_button.setText("New")
            self.copy_wildcard_button.setText("Copy")
            self.delete_wildcard_button.setVisible(True)

    def copy_wildcard(self):
        if self.new_wildcard_active:
            self.cancel_wildcard_draft()
            return
        if self.current_wildcard_id is None:
            return
        self.store_current_wildcard_from_form()
        copied = deepcopy(self.wildcards[self.current_wildcard_id])
        base_id = f"{self.current_wildcard_id}_copy"
        copied_id = base_id
        suffix = 2
        while copied_id in self.wildcards:
            copied_id = f"{base_id}_{suffix}"
            suffix += 1
        copied["trigger"] = copied_id
        self.draft_previous_wildcard_id = self.current_wildcard_id
        self.new_wildcard = copied
        self.new_wildcard_active = True
        self.current_wildcard_id = None
        self.wildcard_select_combobox.setEnabled(False)
        self.refresh_wildcard_selector()
        self.select_wildcard(None)
        self.update_draft_buttons()

    def delete_wildcard(self):
        if self.current_wildcard_id is None:
            return
        wildcard_id = self.current_wildcard_id
        confirmation = Confirm(
            self,
            "Delete Wildcard",
            f"Delete '{wildcard_id}' when changes are saved?",
            "Delete",
            "Cancel",
        )
        if confirmation.exec() != QDialog.Accepted:
            return
        self.deleted_wildcard_ids.add(wildcard_id)
        self.wildcards.pop(wildcard_id, None)
        self.current_wildcard_id = next(iter(sorted(self.wildcards)), None)
        self.refresh_wildcard_selector()
        self.select_wildcard(self.current_wildcard_id)

    def validate_documents(self):
        wildcard_ids = set(self.wildcards)
        for wildcard_id, document in self.wildcards.items():
            validation_error = validate_wildcard_id(
                wildcard_id,
                wildcard_ids - {wildcard_id},
                previous_id=wildcard_id,
            )
            if validation_error:
                return f"{wildcard_id}: {validation_error}"
            if not document.get("values"):
                return f"{wildcard_id}: Wildcard must contain at least one nonempty value."
        cycles = find_wildcard_cycles(self.wildcards)
        if cycles:
            rendered_cycles = "; ".join(" -> ".join(cycle) for cycle in cycles)
            return f"Wildcard reference cycle detected: {rendered_cycles}"
        return None

    def save_and_close(self):
        self.store_current_wildcard_from_form()
        if self.new_wildcard_active and not self.save_wildcard_draft():
            return

        validation_error = self.validate_documents()
        if validation_error:
            Error(self, validation_error)
            return

        self.wildcards_dir.mkdir(parents=True, exist_ok=True)
        temporary_files = []
        try:
            for wildcard_id, document in self.wildcards.items():
                normalized = normalize_wildcard_document(wildcard_id, document)
                target_path = self.wildcards_dir / f"{wildcard_id}.json"
                temporary_path = self.wildcards_dir / f".{wildcard_id}.json.tmp"
                temporary_path.write_text(
                    json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                temporary_files.append((temporary_path, target_path))

            for temporary_path, target_path in temporary_files:
                temporary_path.replace(target_path)

            for wildcard_id, original_path in self.original_paths.items():
                canonical_path = self.wildcards_dir / f"{wildcard_id}.json"
                if original_path != canonical_path and original_path.exists():
                    original_path.unlink()

            for wildcard_id in self.deleted_wildcard_ids:
                original_path = self.original_paths.get(
                    wildcard_id,
                    self.wildcards_dir / f"{wildcard_id}.json",
                )
                if original_path.exists():
                    original_path.unlink()
        except OSError as exception:
            for temporary_path, _target_path in temporary_files:
                temporary_path.unlink(missing_ok=True)
            Error(self, f"Could not save wildcards: {exception}")
            return

        self.reload_callback()
        self.save_last_wildcard_id()
        self.accept()

    def save_last_wildcard_id(self):
        if self.current_wildcard_id is not None:
            self.settings.setValue(self.LAST_WILDCARD_SETTING, self.current_wildcard_id)

    def reject(self):
        self.save_last_wildcard_id()
        self.cancel_wildcard_draft()
        super().reject()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            return
        super().keyPressEvent(event)