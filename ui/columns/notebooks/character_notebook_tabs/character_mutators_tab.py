import json
from functools import partial

from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout

from data.datahub import get_character, get_character_source_path, resolve_character_id
from data.label_associations import label_association_matches, normalize_label_association
from data.mutators import (
    document_objects, effective_labels, entries_from_document, is_active,
    migrate_file, normalize_label, set_entry_active, tag_scope_matches,
)
from data.paths import ASSOCIATIONS_DIR, LABEL_ASSOCIATIONS_FILE
from signaling.debug_signal import debug_error
from signaling.refresh_character_lists import refresh_character_lists_signal


class CharacterMutatorsTab(QFrame):
    personal_data_loaded = Signal(dict)

    def __init__(self, parent):
        super().__init__(parent)
        self.modifiers = parent
        self.character_id = None
        self.labels = []
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QFrame(self.scroll)
        self.rows_layout = QVBoxLayout(self.content)
        self.rows_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.reload)
        layout.addWidget(self.refresh_button)

    def set_character(self, character_id, labels):
        self.character_id = resolve_character_id(character_id)
        self.labels = labels
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.reload()

    def reload(self):
        self.refresh()
        if self.character_id:
            refresh_character_lists_signal.mutators_changed.emit("")

    def _error(self, path, exception):
        message = f"Cannot update mutators in {path}: {exception}"
        self.status_label.setText(message)
        debug_error("Mutators", message)

    def _entries(self, path, keys):
        try:
            return migrate_file(path, keys)
        except (OSError, ValueError) as exception:
            self._error(path, exception)
            return None

    def refresh(self):
        self.rows.clear()
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.status_label.setText("")
        if not self.character_id:
            self.status_label.setText("Select a character to view its mutators.")
            return

        groups = {
            "Personal Tag Associations": [],
            "Global Tag Associations": [],
            "Global Label Associations": [],
            "Chance Tags": [],
        }
        path = get_character_source_path(self.character_id)
        payload = self._entries(path, ("tag_associations", "chance_tag"))
        if payload is not None:
            # Character loading uses the first document in legacy list files.
            character = payload[0] if isinstance(payload, list) and payload else payload
            if isinstance(character, dict):
                cached = get_character(self.character_id)
                if cached is not None:
                    for key in ("tag_associations", "chance_tag", "labels"):
                        if key in character:
                            cached[key] = character[key]
                self.labels = effective_labels(character.get("labels") or [])
                self.personal_data_loaded.emit(character)
                prefix = (0,) if isinstance(payload, list) else ()
                for key, kind in (("tag_associations", "Personal Tag Associations"), ("chance_tag", "Chance Tags")):
                    groups[kind] = [
                        entry for entry in entries_from_document(path, payload, key, kind, self.character_id)
                        if entry.location[:-2] == prefix
                    ]

        modifiers = self.modifiers
        forced = None
        if modifiers.boys_to_girls_button.isChecked():
            forced = "female"
        elif modifiers.girls_to_boys_button.isChecked():
            forced = "male"

        for path in sorted(ASSOCIATIONS_DIR.glob("*.json")):
            payload = self._entries(path, ("tag_associations",))
            if payload is None:
                continue
            for prefix, document in document_objects(payload):
                targets = document.get("target_label") or []
                if not tag_scope_matches(targets, self.labels, forced):
                    continue
                scope = ", ".join(str(label) for label in targets) if isinstance(targets, list) else str(targets)
                scope = scope or "All characters"
                groups["Global Tag Associations"].extend(
                    entry for entry in entries_from_document(
                        path, payload, "tag_associations", "Global Tag Associations", scope,
                    ) if entry.location[:-2] == prefix
                )

        if LABEL_ASSOCIATIONS_FILE.is_file():
            path = LABEL_ASSOCIATIONS_FILE
            payload = self._entries(path, ("label_associations",))
            if payload is not None:
                groups["Global Label Associations"] = [
                    entry for entry in entries_from_document(
                        path, payload, "label_associations", "Global Label Associations", "All characters",
                    )
                    if label_association_matches(
                        normalize_label_association(entry.value),
                        effective_labels(self.labels, forced), normalize_label,
                    )
                ]

        for kind, entries in groups.items():
            if not entries:
                continue
            heading = QLabel(kind, self.content)
            heading.setStyleSheet("font-weight: bold;")
            self.rows_layout.addWidget(heading)
            for index, entry in enumerate(entries, 1):
                name = entry.value.get("name") or f"{'Chance' if kind == 'Chance Tags' else 'Association'} {index}"
                checkbox = QCheckBox(str(name), self.content)
                checkbox.setChecked(is_active(entry.value))
                global_entry = kind.startswith("Global")
                source = f"{entry.scope} - {entry.path.name}"
                checkbox.setToolTip(
                    source + ("\nChanges affect every character." if global_entry else "\nChanges affect every slot using this character.")
                    + "\n\n" + json.dumps(entry.value, indent=2, ensure_ascii=False)
                )
                checkbox.toggled.connect(partial(self._toggle, entry, checkbox))
                self.rows.append((entry, checkbox))
                self.rows_layout.addWidget(checkbox)
                if global_entry:
                    source_label = QLabel(source, self.content)
                    source_label.setWordWrap(True)
                    self.rows_layout.addWidget(source_label)
        if not self.rows and not self.status_label.text():
            self.status_label.setText("No mutators apply to this character.")
        self.rows_layout.addStretch(1)

    def _toggle(self, entry, checkbox, active):
        try:
            payload = set_entry_active(entry, active)
        except (OSError, ValueError) as exception:
            blocker = QSignalBlocker(checkbox)
            checkbox.setChecked(is_active(entry.value))
            del blocker
            self._error(entry.path, exception)
            return

        personal = entry.kind in {"Personal Tag Associations", "Chance Tags"}
        if personal:
            document = payload[0] if isinstance(payload, list) else payload
            character = get_character(self.character_id)
            if character is not None:
                for key in ("tag_associations", "chance_tag"):
                    character[key] = document.get(key, [])
        entry.value["active"] = bool(active)
        self.status_label.setText("")
        refresh_character_lists_signal.mutators_changed.emit(self.character_id if personal else "")
