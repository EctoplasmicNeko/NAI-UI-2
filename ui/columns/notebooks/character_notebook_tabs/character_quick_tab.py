import random
from copy import deepcopy

from PySide6.QtWidgets import (
    QGridLayout,
    QFrame,
    QAbstractSpinBox,
    QDoubleSpinBox,
    QLabel,
    QPushButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal, QEvent
from signaling.debug_signal import debug_error


class CharacterQuickTab(QFrame):
    # character_name, quick_weights_data, source_mode
    quickWeightsChanged = Signal(str, list, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("character_quick_tab")
        self.current_character_name = None
        self.current_mode = "character"
        self.character_quick_weights = []
        self.universal_quick_weights = []
        self.quick_weights_data = []
        # (tag_lower, negative) -> locked value. Lives on the tab so locked
        # values and states persist across character switches.
        self.locked_quick_weights = {}
        self.build_character_quick_tab()
        self.setMinimumHeight(70)
        
    def build_character_quick_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 0)
        self.grid.setRowStretch(2, 0)
        self.grid.setRowStretch(3, 1)

        self.quick_tab_label = QLabel("Quick Weights", self)
        self.quick_tab_label.setObjectName("quick_tab_label")
        self.quick_tab_label.setAlignment(Qt.AlignCenter)
        self.grid.addWidget(self.quick_tab_label, 0, 0, 1, 2)

        self.quick_weight_mode_frame = QFrame(self)
        self.quick_weight_mode_grid = QGridLayout(self.quick_weight_mode_frame)
        self.quick_weight_mode_grid.setContentsMargins(4, 4, 4, 4)
        self.quick_weight_mode_grid.setSpacing(4)
        self.quick_weight_mode_grid.setColumnStretch(0, 1)
        self.quick_weight_mode_grid.setColumnStretch(1, 1)
        self.grid.addWidget(self.quick_weight_mode_frame, 1, 0, 1, 2)

        self.character_mode_button = QPushButton("C", self)
        self.character_mode_button.setCheckable(True)
        self.character_mode_button.setChecked(True)
        self.character_mode_button.setToolTip("Use character quick weights")
        self.quick_weight_mode_grid.addWidget(self.character_mode_button, 0, 0)

        self.universal_mode_button = QPushButton("U", self)
        self.universal_mode_button.setCheckable(True)
        self.universal_mode_button.setChecked(False)
        self.universal_mode_button.setToolTip("Use universal quick weights from u_quickweights.json")
        self.quick_weight_mode_grid.addWidget(self.universal_mode_button, 0, 1)

        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)
        self.mode_button_group.addButton(self.character_mode_button)
        self.mode_button_group.addButton(self.universal_mode_button)

        self.character_mode_button.clicked.connect(lambda: self.set_quick_weight_mode("character"))
        self.universal_mode_button.clicked.connect(lambda: self.set_quick_weight_mode("universal"))

        self.spinner_frame = QFrame(self)
        self.spinner_grid = QGridLayout(self.spinner_frame)
        self.spinner_grid.setContentsMargins(4, 4, 4, 4)
        self.spinner_grid.setSpacing(4)
        self.grid.addWidget(self.spinner_frame, 2, 0, 1, 2)

    def set_quick_weight_mode(self, mode: str):
        if mode not in {"character", "universal"}:
            return

        self.current_mode = mode
        self.character_mode_button.setChecked(mode == "character")
        self.universal_mode_button.setChecked(mode == "universal")
        self.display_quick_weights()

    def rebuild_quick_weights(self, character_name, quick_weights_data, universal_quick_weights=None, mode="character"):
        self.current_character_name = character_name
        self.character_quick_weights = deepcopy(quick_weights_data or [])
        self.universal_quick_weights = deepcopy(universal_quick_weights or [])
        self.current_mode = mode if mode in {"character", "universal"} else "character"

        self.character_mode_button.setChecked(self.current_mode == "character")
        self.universal_mode_button.setChecked(self.current_mode == "universal")

        self.display_quick_weights()

    def _filter_universal_quick_weights(self):
        if not self.character_quick_weights or not self.universal_quick_weights:
            return []

        allowed = {
            (entry["tag"], entry["negative"]) for entry in self.character_quick_weights if isinstance(entry, dict)
        }
        filtered = [
            entry for entry in self.universal_quick_weights
            if isinstance(entry, dict) and (entry.get("tag"), entry.get("negative")) in allowed
        ]
        return filtered

    @staticmethod
    def _lock_key(tag, negative):
        return (str(tag or "").strip().lower(), bool(negative))

    def is_quick_weight_locked(self, tag, negative) -> bool:
        return self._lock_key(tag, negative) in self.locked_quick_weights

    def toggle_quick_weight_lock(self, spinner):
        key = self._lock_key(spinner.property("tag"), spinner.property("negative"))
        if key in self.locked_quick_weights:
            self.locked_quick_weights.pop(key, None)
        else:
            self.locked_quick_weights[key] = round(float(spinner.value()), 1)
        self._apply_lock_state(spinner, key in self.locked_quick_weights)

    def _apply_lock_state(self, spinner, locked: bool):
        spinner.setProperty("locked", locked)
        spinner.setReadOnly(locked)
        tag = spinner.property("tag")
        if locked:
            spinner.setPrefix(f"[off] {tag}: ")
            spinner.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spinner.setStyleSheet("QDoubleSpinBox { color: #808080; }")
        else:
            spinner.setPrefix(f"{tag}: ")
            spinner.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
            spinner.setStyleSheet("")

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            spinner = watched.parent()
            if isinstance(spinner, QDoubleSpinBox) and spinner.property("tag") is not None:
                if event.button() == Qt.LeftButton:
                    self.toggle_quick_weight_lock(spinner)
                watched.deselect()
                return True
        elif event_type in (QEvent.MouseMove, QEvent.MouseButtonRelease):
            spinner = watched.parent()
            if isinstance(spinner, QDoubleSpinBox) and spinner.property("tag") is not None:
                # Block drag/double-click text selection in the read-only line edit.
                return True
        return super().eventFilter(watched, event)

    def randomize_quick_weights(self, positive_only: bool = False) -> None:
        for index, entry in enumerate(self.quick_weights_data):
            spinner = self.spinner_grid.itemAt(index).widget()
            if not isinstance(spinner, QDoubleSpinBox):
                continue
            if self.is_quick_weight_locked(entry.get("tag"), entry.get("negative")):
                continue
            minimum = max(0.0, spinner.minimum()) if positive_only else spinner.minimum()
            maximum = spinner.maximum()
            if minimum > maximum:
                debug_error(
                    "Quick Weights",
                    f"Cannot randomize '{entry['tag']}' with Positive Only: "
                    "its configured maximum is negative. Set its maximum to at least zero.",
                )
                continue

            value = random.randint(round(minimum * 10), round(maximum * 10)) / 10
            previous = spinner.blockSignals(True)
            spinner.setValue(value)
            spinner.blockSignals(previous)
            entry["value"] = value

    def apply_saved_values(self, positive_lookup, negative_lookup):
        """Restore per-generation quick weight values (e.g. from imported metadata) without persisting them.

        positive_lookup/negative_lookup map lowercased tag -> (original_tag, strength). Entries with no
        matching spinner or a value outside its current range are returned for prompt-text fallback.
        """
        remaining_positive = dict(positive_lookup or {})
        remaining_negative = dict(negative_lookup or {})

        for widget in self.findChildren(QDoubleSpinBox):
            if bool(widget.property('locked')):
                # Locked quick weights keep their value; matching imported
                # values fall back to prompt text instead.
                continue
            is_negative = bool(widget.property('negative'))
            tag = str(widget.property('tag') or '').strip().lower()
            remaining = remaining_negative if is_negative else remaining_positive
            match = remaining.pop(tag, None)
            if match and not widget.minimum() <= match[1] <= widget.maximum():
                remaining[tag] = match
                match = None
            value = round(match[1], 1) if match else 0.0

            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)

            for entry in self.quick_weights_data:
                if (
                    str(entry.get('tag', '')).strip().lower() == tag
                    and bool(entry.get('negative')) == is_negative
                ):
                    entry['value'] = value
                    break

        return remaining_positive, remaining_negative

    def display_quick_weights(self):
        if self.current_mode == "universal":
            self.quick_weights_data = self._filter_universal_quick_weights()
        else:
            self.quick_weights_data = self.character_quick_weights

        while self.spinner_grid.count():
            item = self.spinner_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        placeholder_text = "Character has no assigned quick weights"
        if self.current_mode == "universal":
            placeholder_text = "Universal quick weights are not defined in u_quickweights.json or do not match the character"

        if not self.quick_weights_data:
            placeholder_label = QLabel(placeholder_text, self.spinner_frame)
            placeholder_label.setAlignment(Qt.AlignCenter)
            self.spinner_grid.addWidget(placeholder_label, 0, 0, 2, 2)
            return

        row = 0
        column = 0

        for quick_weight in self.quick_weights_data:
            spinner = QDoubleSpinBox(self.spinner_frame)
            spinner.setPrefix(f"{quick_weight['tag']}: ")
            spinner.setProperty("tag", quick_weight['tag'])
            spinner.setProperty("negative", quick_weight['negative'])
            spinner.setProperty("min", quick_weight['min'])
            spinner.setProperty("max", quick_weight['max'])
            spinner.setRange(quick_weight['min'], quick_weight['max'])
            spinner.setDecimals(1)
            spinner.setSingleStep(0.1)
            spinner.lineEdit().setReadOnly(True)
            spinner.lineEdit().setFocusPolicy(Qt.NoFocus)
            spinner.lineEdit().setContextMenuPolicy(Qt.NoContextMenu)
            spinner.lineEdit().installEventFilter(self)
            spinner.setToolTip("Click the value to disable/enable this quick weight")

            initial_value = round(float(quick_weight['value']), 1)
            spinner.setValue(initial_value)

            lock_key = self._lock_key(quick_weight['tag'], quick_weight['negative'])
            if lock_key in self.locked_quick_weights:
                spinner.setValue(round(float(self.locked_quick_weights[lock_key]), 1))
                quick_weight['value'] = spinner.value()
            self._apply_lock_state(spinner, lock_key in self.locked_quick_weights)

            spinner.valueChanged.connect(self.save_quick_weight)
            self.spinner_grid.addWidget(spinner, row, column)

            column += 1
            if column == 2:
                column = 0
                row += 1

    def save_quick_weight(self):
        spinner = self.sender()
        if spinner is None:
            return

        tag = spinner.property("tag")
        negative = spinner.property("negative")
        min_value = float(spinner.property("min"))
        max_value = float(spinner.property("max"))
        raw_value = float(spinner.value())
        new_value = round(raw_value, 1)

        spinner.blockSignals(True)
        spinner.setValue(new_value)
        spinner.blockSignals(False)

        for entry in self.quick_weights_data:
            if (
                entry["tag"] == tag
                and entry["negative"] == negative
                and float(entry.get("min", 0.0)) == min_value
                and float(entry.get("max", 0.0)) == max_value
            ):
                entry["value"] = new_value
                break

        if self.current_mode == "universal":
            self.universal_quick_weights = self.quick_weights_data
        else:
            self.character_quick_weights = self.quick_weights_data

        self.quickWeightsChanged.emit(self.current_character_name or "", self.quick_weights_data, self.current_mode)
