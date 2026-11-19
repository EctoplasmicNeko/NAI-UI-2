from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from data.paths import ASSOCIATIONS_DIR
from data.mutators import add_active_fields, write_document
from windows.character_editor import TagAssociationListEditor
from windows.confirmation import Confirm
from signaling.refresh_character_lists import refresh_character_lists_signal

UNIVERSAL_ASSOCIATIONS_FILE = ASSOCIATIONS_DIR / "universal.json"
UNIVERSAL_SCOPE = "universal.json"


def load_universal_associations() -> list[dict]:
    if not UNIVERSAL_ASSOCIATIONS_FILE.exists():
        return []
    try:
        payload = json.loads(UNIVERSAL_ASSOCIATIONS_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        associations = payload.get("tag_associations")
        return associations if isinstance(associations, list) else []
    return []


def save_universal_associations(associations: list[dict]) -> None:
    ASSOCIATIONS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_label": [],
        "tag_associations": associations,
    }
    add_active_fields(payload, ("tag_associations",))
    write_document(UNIVERSAL_ASSOCIATIONS_FILE, payload)


def _clean_target_labels(raw) -> list[str]:
    if not isinstance(raw, list):
        raw = [raw]
    labels = []
    for label in raw:
        text = str(label or "").strip()
        if text and text.casefold() not in {existing.casefold() for existing in labels}:
            labels.append(text)
    return labels


def load_scoped_associations(directory: Path | None = None) -> dict[str, dict]:
    """Load every association file, keyed by file name.

    Each value is ``{"target_label": [...], "tag_associations": [...]}``. An empty
    ``target_label`` means the file applies to every character.
    """
    directory = Path(directory or ASSOCIATIONS_DIR)
    scopes: dict[str, dict] = {UNIVERSAL_SCOPE: {"target_label": [], "tag_associations": []}}
    if not directory.is_dir():
        return scopes
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        associations = payload.get("tag_associations")
        scopes[path.name] = {
            "target_label": _clean_target_labels(payload.get("target_label") or []),
            "tag_associations": associations if isinstance(associations, list) else [],
        }
    return scopes


def save_scoped_associations(scopes: dict[str, dict], directory: Path | None = None, removed: list[str] | None = None) -> None:
    directory = Path(directory or ASSOCIATIONS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    for file_name in removed or []:
        if file_name == UNIVERSAL_SCOPE or file_name in scopes:
            continue
        path = directory / file_name
        if path.is_file():
            path.unlink()
    for file_name, scope in scopes.items():
        payload = {
            "target_label": _clean_target_labels(scope.get("target_label") or []),
            "tag_associations": list(scope.get("tag_associations") or []),
        }
        add_active_fields(payload, ("tag_associations",))
        write_document(directory / file_name, payload)


def scope_file_name_for_label(label: str, existing: set[str]) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(label).strip()).strip(" .") or "label"
    lowered = {name.casefold() for name in existing}
    candidate = f"{stem}.json"
    suffix = 2
    while candidate.casefold() in lowered:
        candidate = f"{stem} ({suffix}).json"
        suffix += 1
    return candidate


def scope_display_name(file_name: str, scope: dict) -> str:
    labels = scope.get("target_label") or []
    if labels:
        return "Label: " + ", ".join(labels)
    if file_name == UNIVERSAL_SCOPE:
        return "All characters"
    return f"All characters ({file_name})"


class ScopedTagAssociationEditor(QFrame):
    """Edit universal and label-scoped tag association files from one place."""

    changed = Signal()

    def __init__(self, parent=None, directory: Path | None = None, label_definitions=None):
        super().__init__(parent)
        self.directory = Path(directory or ASSOCIATIONS_DIR)
        self.label_definitions = list(label_definitions or [])
        self.scopes = load_scoped_associations(self.directory)
        self.removed_scopes: list[str] = []
        self.current_scope: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        scope_row = QFrame(self)
        scope_layout = QHBoxLayout(scope_row)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(4)
        scope_layout.addWidget(QLabel("Applies to:", scope_row))
        self.scope_combo = QComboBox(scope_row)
        self.scope_combo.currentIndexChanged.connect(self._switch_scope)
        scope_layout.addWidget(self.scope_combo, 1)
        self.add_scope_button = QPushButton("Add Label Scope", scope_row)
        self.add_scope_button.clicked.connect(self.prompt_add_scope)
        scope_layout.addWidget(self.add_scope_button)
        self.remove_scope_button = QPushButton("Remove Scope", scope_row)
        self.remove_scope_button.clicked.connect(self.prompt_remove_scope)
        scope_layout.addWidget(self.remove_scope_button)
        layout.addWidget(scope_row)

        self.association_editor = TagAssociationListEditor(self)
        self.association_editor.changed.connect(self.changed.emit)
        layout.addWidget(self.association_editor, 1)

        self._refresh_scope_combo(UNIVERSAL_SCOPE)

    def set_label_definitions(self, label_definitions):
        self.label_definitions = list(label_definitions or [])

    def _refresh_scope_combo(self, select: str | None = None):
        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        ordered = [UNIVERSAL_SCOPE] + sorted(
            (name for name in self.scopes if name != UNIVERSAL_SCOPE),
            key=lambda name: (bool(self.scopes[name]["target_label"]) is False, scope_display_name(name, self.scopes[name]).casefold()),
        )
        for file_name in ordered:
            self.scope_combo.addItem(scope_display_name(file_name, self.scopes[file_name]), file_name)
        self.scope_combo.blockSignals(False)
        index = self.scope_combo.findData(select) if select else 0
        self.scope_combo.setCurrentIndex(max(0, index))
        self._switch_scope()

    def _store_current(self):
        if self.current_scope in self.scopes:
            self.scopes[self.current_scope]["tag_associations"] = self.association_editor.associations_payload()

    def _switch_scope(self, *_):
        file_name = self.scope_combo.currentData()
        if file_name == self.current_scope or file_name is None:
            return
        self._store_current()
        self.current_scope = file_name
        self.association_editor.set_associations(self.scopes[file_name]["tag_associations"])
        self.remove_scope_button.setEnabled(file_name != UNIVERSAL_SCOPE)

    def available_labels(self) -> list[str]:
        scoped = {
            label.casefold()
            for scope in self.scopes.values()
            for label in scope["target_label"]
        }
        labels = []
        for definition in self.label_definitions:
            label = str(definition.get("label") or "").strip() if isinstance(definition, dict) else ""
            if label and label.casefold() not in scoped and label.casefold() not in {item.casefold() for item in labels}:
                labels.append(label)
        return sorted(labels, key=str.casefold)

    def add_scope(self, label: str) -> str | None:
        label = str(label or "").strip()
        if not label:
            return None
        for file_name, scope in self.scopes.items():
            if [item.casefold() for item in scope["target_label"]] == [label.casefold()]:
                self._refresh_scope_combo(file_name)
                return file_name
        self._store_current()
        file_name = scope_file_name_for_label(label, set(self.scopes) | set(self.removed_scopes))
        self.scopes[file_name] = {"target_label": [label], "tag_associations": []}
        self._refresh_scope_combo(file_name)
        self.changed.emit()
        return file_name

    def remove_scope(self, file_name: str) -> None:
        if file_name == UNIVERSAL_SCOPE or file_name not in self.scopes:
            return
        self.scopes.pop(file_name)
        self.removed_scopes.append(file_name)
        self.current_scope = None
        self._refresh_scope_combo(UNIVERSAL_SCOPE)
        self.changed.emit()

    def prompt_add_scope(self):
        labels = self.available_labels()
        if not labels:
            label, accepted = QInputDialog.getText(
                self, "Add Label Scope", "Every defined label already has a scope. Enter a label:"
            )
        else:
            label, accepted = QInputDialog.getItem(
                self, "Add Label Scope", "Apply associations to characters with label:", labels, 0, False
            )
        if accepted:
            self.add_scope(label)

    def prompt_remove_scope(self):
        file_name = self.current_scope
        if not file_name or file_name == UNIVERSAL_SCOPE:
            return
        name = scope_display_name(file_name, self.scopes[file_name])
        if Confirm(self, "Remove Scope", f"Remove '{name}' and all of its associations?").exec():
            self.remove_scope(file_name)

    def save(self):
        self._store_current()
        save_scoped_associations(self.scopes, self.directory, self.removed_scopes)
        self.removed_scopes = []
        refresh_character_lists_signal.mutators_changed.emit("")


class UniversalTagAssociationsWindow(QDialog):
    """Editor for tag associations that apply to every character regardless of their labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Universal Tag Associations")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.association_editor = TagAssociationListEditor(self)
        self.association_editor.set_associations(load_universal_associations())
        layout.addWidget(self.association_editor, 1)

        action_frame = QFrame(self)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.addStretch(1)

        self.save_button = QPushButton("Save", action_frame)
        self.save_button.clicked.connect(self.save_and_close)
        action_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel", action_frame)
        self.cancel_button.clicked.connect(self.reject)
        action_layout.addWidget(self.cancel_button)

        layout.addWidget(action_frame)

    def save_and_close(self):
        save_universal_associations(self.association_editor.associations_payload())
        refresh_character_lists_signal.mutators_changed.emit("")
        self.accept()
