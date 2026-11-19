import random

from PySide6.QtWidgets import QGridLayout, QFrame, QDoubleSpinBox, QComboBox, QLabel, QPushButton, QButtonGroup, QSpinBox, QCheckBox
from data.character_slots import MAX_CHARACTER_SLOTS

LEGACY_COORDINATE_VALUES = [0.0, 0.1, 0.3, 0.5, 0.7, 0.9]


class CoordinateSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._step_values = list(LEGACY_COORDINATE_VALUES)

    def set_step_values(self, values, minimum=0.0):
        self._step_values = [float(value) for value in values if float(value) >= minimum]
        if not self._step_values:
            self._step_values = [float(minimum)]
        self.setRange(min(self._step_values), max(self._step_values))

        if len(self._step_values) > 1:
            if self._step_values[0] == 0.0 and self._step_values[-1] == 1.0 and self._step_values == [round(x / 1000, 3) for x in range(0, 1001)]:
                self.setDecimals(3)
                self.setSingleStep(0.001)
            else:
                self.setDecimals(1)
                self.setSingleStep(0.1)

    def stepBy(self, steps):
        if len(self._step_values) <= 1:
            super().stepBy(steps)
            return

        current = self.value()
        try:
            current_index = self._step_values.index(round(current, 3))
        except ValueError:
            current_index = min(range(len(self._step_values)), key=lambda idx: abs(self._step_values[idx] - current))

        target_index = current_index + steps
        target_index = max(0, min(len(self._step_values) - 1, target_index))
        self.setValue(self._step_values[target_index])


def get_coordinate_step_values(model_type: str):
    model_name = str(model_type or "").lower()
    if model_name == "v5":
        return [round(i / 1000, 3) for i in range(0, 1001)]
    return list(LEGACY_COORDINATE_VALUES)


def get_auto_coordinate_value(model_type: str):
    return 0.0 if str(model_type or "").lower() == "v5" else 0.1


def snap_coordinate_value(value, model_type: str):
    if value is None:
        return 0.0

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 0.0

    numeric_value = max(0.0, min(1.0, numeric_value))
    allowed_values = get_coordinate_step_values(model_type)
    return min(allowed_values, key=lambda candidate: abs(candidate - numeric_value))


def _slot_name_is_empty(slot_name):
    return slot_name in (None, "", "None", "Loaded")


def get_eligible_randomize_slots(slot_names, randomizable_slots=None, slot_limit=None):
    if not isinstance(slot_names, dict):
        return []

    try:
        slot_limit = int(slot_limit) if slot_limit is not None else MAX_CHARACTER_SLOTS
    except (TypeError, ValueError):
        slot_limit = MAX_CHARACTER_SLOTS

    randomizable_slots = set(randomizable_slots or [])
    return [
        slot_id
        for slot_id in range(1, min(MAX_CHARACTER_SLOTS, max(1, slot_limit)) + 1)
        if slot_id in randomizable_slots
    ]


def get_randomized_swap_plan(slot_names, randomizable_slots=None, slot_limit=None):
    eligible_slots = get_eligible_randomize_slots(slot_names, randomizable_slots, slot_limit)
    if len(eligible_slots) < 2:
        return []

    randomized_slots = eligible_slots[:]
    random.shuffle(randomized_slots)

    return [
        (randomized_slots[index], randomized_slots[index + 1])
        for index in range(0, len(randomized_slots) - 1, 2)
    ]


SLOT_COORDINATE_STATE_KEYS = (
    "character_coordinate_button",
    "character_coordinate_mode",
    "character_coordinate_markers_visible",
    "character_x_coordinate",
    "character_y_coordinate",
    "character_can_randomize_position",
    "character_swap_prompts",
)

CHARACTER_PROMPT_STATE_KEYS = (
    "character_positive_prompt",
    "character_negative_prompt",
)

CHARACTER_STATIC_PROMPT_STATE_KEYS = (
    "character_static_positive_prompt",
    "character_static_negative_prompt",
)


def preserve_slot_coordinate_state(incoming_state, slot_state):
    preserved_state = dict(incoming_state)
    for key in SLOT_COORDINATE_STATE_KEYS:
        if key in slot_state:
            preserved_state[key] = slot_state[key]
    return preserved_state


def should_swap_slot_prompts(source_state, target_state):
    return bool(
        source_state.get("character_swap_prompts", True)
        and target_state.get("character_swap_prompts", True)
    )


def preserve_slot_prompt_state(incoming_state, slot_state, swap_prompts=None):
    preserved_state = dict(incoming_state)
    for key in CHARACTER_STATIC_PROMPT_STATE_KEYS:
        if key in slot_state:
            preserved_state[key] = slot_state[key]
    if swap_prompts is None:
        swap_prompts = slot_state.get("character_swap_prompts", True)
    if not swap_prompts:
        for key in CHARACTER_PROMPT_STATE_KEYS:
            if key in slot_state:
                preserved_state[key] = slot_state[key]
    return preserved_state


class CharacterCoordinateTab(QFrame):
    def __init__(self, parent, slot_id=1):
        super().__init__(parent)
        self.slot_id = int(slot_id or 1)
        self._model_type = "v4"
        self.build_character_coordinate_tab()
        self._hook_model_selector()
        self.apply_model_type()

    def _hook_model_selector(self):
        model_combo = self.window().findChild(QComboBox, "model_select_combobox") if self.window() else None
        if model_combo is not None:
            model_combo.currentIndexChanged.connect(self.apply_model_type)

    def _resolve_model_type(self):
        from data.datahub import get_data

        model_combo = self.window().findChild(QComboBox, "model_select_combobox") if self.window() else None
        if model_combo is None:
            return self._model_type

        selected_model_name = model_combo.currentText()
        for model_data in get_data("models").values():
            if model_data.get("name") == selected_model_name:
                return str(model_data.get("payload_type") or self._model_type)
        return self._model_type

    def apply_model_type(self):
        self._model_type = self._resolve_model_type()
        step_values = get_coordinate_step_values(self._model_type)

        for spinbox in (self.horizontal_spinbox, self.vertical_spinbox):
            minimum = 0.0 if self._model_type == "v5" else 0.1
            spinbox.set_step_values(step_values, minimum=minimum)
            if self._model_type == "v5":
                spinbox.setDecimals(3)
                spinbox.setRange(0.0, 1.0)
                spinbox.setSingleStep(0.001)
            else:
                spinbox.setDecimals(3)
                spinbox.setRange(0.1, 1.0)
                spinbox.setSingleStep(0.1)

        current_x = self.horizontal_spinbox.value()
        current_y = self.vertical_spinbox.value()
        self.horizontal_spinbox.setValue(snap_coordinate_value(current_x, self._model_type))
        self.vertical_spinbox.setValue(snap_coordinate_value(current_y, self._model_type))

    def get_coordinate_mode(self):
        if self.coordinate_button.isChecked():
            return "coordinate"
        if self.random_button.isChecked():
            return "random"
        return "auto"

    def set_coordinate_mode(self, mode: str):
        mode_name = str(mode or "auto").lower()
        self.auto_button.setChecked(mode_name == "auto")
        self.coordinate_button.setChecked(mode_name == "coordinate")
        self.random_button.setChecked(mode_name == "random")
        self._apply_coordinate_mode()

    def _apply_coordinate_mode(self):
        is_coordinate_mode = self.coordinate_button.isChecked()
        self.horizontal_spinbox.setEnabled(is_coordinate_mode)
        self.vertical_spinbox.setEnabled(is_coordinate_mode)
        self.horizontal_label.setEnabled(is_coordinate_mode)
        self.vertical_label.setEnabled(is_coordinate_mode)

    def build_character_coordinate_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 5, 0, 5)
        self.grid.setSpacing(3)

        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)

        self.auto_button = QPushButton("Auto")
        self.auto_button.setCheckable(True)
        self.auto_button.setChecked(True)
        self.coordinate_button = QPushButton("Coordinate")
        self.coordinate_button.setCheckable(True)
        self.random_button = QPushButton("Random")
        self.random_button.setCheckable(True)
        self.show_markers_button = QPushButton("Show Markers")
        self.show_markers_button.setCheckable(True)
        self.show_markers_button.setChecked(True)

        self.mode_button_group.addButton(self.auto_button, 0)
        self.mode_button_group.addButton(self.coordinate_button, 1)
        self.mode_button_group.addButton(self.random_button, 2)

        self.auto_button.toggled.connect(lambda checked: self._apply_coordinate_mode() if checked else None)
        self.coordinate_button.toggled.connect(lambda checked: self._apply_coordinate_mode() if checked else None)
        self.random_button.toggled.connect(lambda checked: self._apply_coordinate_mode() if checked else None)

        self.grid.addWidget(self.auto_button, 0, 0)
        self.grid.addWidget(self.coordinate_button, 0, 1)
        self.grid.addWidget(self.random_button, 0, 2)
        

        self.horizontal_label = QLabel("Horizontal")
        self.vertical_label = QLabel("Vertical")

        self.horizontal_spinbox = CoordinateSpinBox(self)
        self.horizontal_spinbox.setObjectName("character_horizontal_spinbox")
        self.horizontal_spinbox.setRange(0.0, 1.0)
        self.horizontal_spinbox.setDecimals(3)
        self.horizontal_spinbox.setSingleStep(0.001)
        self.horizontal_spinbox.setMinimumWidth(90)

        self.vertical_spinbox = CoordinateSpinBox(self)
        self.vertical_spinbox.setObjectName("character_vertical_spinbox")
        self.vertical_spinbox.setRange(0.0, 1.0)
        self.vertical_spinbox.setDecimals(3)
        self.vertical_spinbox.setSingleStep(0.001)
        self.vertical_spinbox.setMinimumWidth(90)

        self.grid.addWidget(self.horizontal_label, 1, 0)
        self.grid.addWidget(self.horizontal_spinbox, 1, 1, 1, 2)
        self.grid.addWidget(self.vertical_label, 2, 0)
        self.grid.addWidget(self.vertical_spinbox, 2, 1, 1, 2)

        self.grid.addWidget(self.show_markers_button, 3, 0, 1, 3)
        self.grid.setRowMinimumHeight(4, 8)

        self.position_label = QLabel("Position")
        self.position_spinbox = QSpinBox(self)
        self.position_spinbox.setObjectName("character_position_spinbox")
        self.position_spinbox.setRange(1, MAX_CHARACTER_SLOTS)
        self.position_spinbox.setValue(self.slot_id)

        self.can_randomize_checkbox = QCheckBox("Can Randomize")
        self.can_randomize_checkbox.setChecked(False)
        self.can_randomize_checkbox.setToolTip(
            "Include this slot when Randomize or Auto-Randomize shuffles characters between active slots."
        )

        self.randomize_button = QPushButton("Randomize")
        self.randomize_button.setToolTip(
            "Shuffle characters between active slots marked Can Randomize. Slot coordinates stay in place."
        )
        self.randomize_button.clicked.connect(self.randomize_slots)

        self.swap_prompts_checkbox = QCheckBox("Swap P Prompts")
        self.swap_prompts_checkbox.setChecked(True)
        self.swap_prompts_checkbox.setToolTip(
            "Move positive and negative prompts with characters during slot swaps. This setting applies to all slots."
        )
        self.swap_prompts_checkbox.toggled.connect(self._sync_swap_prompts_controls)

        self.auto_randomize_button = QPushButton("Auto-Randomize")
        self.auto_randomize_button.setCheckable(True)
        self.auto_randomize_button.setToolTip("Randomize eligible slots on the selected frequency.")
        self.auto_randomize_frequency_spinbox = QSpinBox(self)
        self.auto_randomize_frequency_spinbox.setMinimum(0)
        self.auto_randomize_frequency_spinbox.setValue(1)
        self.auto_randomize_frequency_spinbox.setPrefix("Frequency: ")
        self.auto_randomize_frequency_spinbox.setSpecialValueText("Frequency: On Set")
        self.auto_randomize_button.toggled.connect(self._sync_auto_randomize_controls)
        self.auto_randomize_frequency_spinbox.valueChanged.connect(self._sync_auto_randomize_controls)

        self.swap_slot_button = QPushButton("Swap Slot")
        self.swap_slot_button.clicked.connect(self.swap_slot)

        self.grid.addWidget(self.position_label, 5, 0)
        self.grid.addWidget(self.position_spinbox, 5, 1)
        self.grid.addWidget(self.swap_slot_button, 5, 2)
        self.grid.addWidget(self.can_randomize_checkbox, 6, 0, 1, 2)
        self.grid.addWidget(self.randomize_button, 6, 2)
        self.grid.addWidget(self.swap_prompts_checkbox, 7, 0, 1, 3)
        self.grid.addWidget(self.auto_randomize_button, 8, 0)
        self.grid.addWidget(self.auto_randomize_frequency_spinbox, 8, 1, 1, 2)

        self.grid.setRowStretch(9, 1)

        self.coordinate_button_group = None
        self.refresh_position_spinbox_limit()
        self._apply_coordinate_mode()

    def coordinate_to_button_id(self, x: float, y: float) -> int:
        if x == 0.0 and y == 0.0:
            return 0

        legacy_values = get_coordinate_step_values("legacy")
        col = min(range(len(legacy_values)), key=lambda idx: abs(legacy_values[idx] - float(x)))
        row = min(range(len(legacy_values)), key=lambda idx: abs(legacy_values[idx] - float(y)))
        return row * 5 + col + 1

    def button_id_to_coordinates(self, button_id):
        if button_id in (None, 0, -1):
            return 0.0, 0.0

        legacy_values = get_coordinate_step_values("legacy")
        index = int(button_id) - 1
        row = index // 5
        col = index % 5
        return legacy_values[col], legacy_values[row]

    @staticmethod
    def _get_active_slot_limit(left_column):
        character_counter = getattr(getattr(left_column, "upper_frame", None), "page1", None)
        character_counter = getattr(character_counter, "character_number_counter", None)
        if character_counter is None:
            return 1
        return max(1, min(MAX_CHARACTER_SLOTS, character_counter.value()))

    def _sync_auto_randomize_controls(self):
        main_window = self.window()
        left_column = getattr(main_window, "left_column_widget", None) if main_window is not None else None
        if left_column is None:
            return

        enabled = self.auto_randomize_button.isChecked()
        frequency = self.auto_randomize_frequency_spinbox.value()
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            lower_tab = getattr(left_column.lower_frame, f"character_tab_{slot_id}", None)
            if lower_tab is None:
                continue
            coordinate_tab = lower_tab.sub_notebook.character_sub_tab_2
            if coordinate_tab is self:
                continue
            auto_randomize_button = coordinate_tab.auto_randomize_button
            frequency_spinbox = coordinate_tab.auto_randomize_frequency_spinbox
            button_signals_blocked = auto_randomize_button.blockSignals(True)
            spinbox_signals_blocked = frequency_spinbox.blockSignals(True)
            try:
                auto_randomize_button.setChecked(enabled)
                frequency_spinbox.setValue(frequency)
            finally:
                auto_randomize_button.blockSignals(button_signals_blocked)
                frequency_spinbox.blockSignals(spinbox_signals_blocked)

    def _sync_swap_prompts_controls(self, checked):
        main_window = self.window()
        left_column = getattr(main_window, "left_column_widget", None) if main_window is not None else None
        if left_column is None:
            return

        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            lower_tab = getattr(left_column.lower_frame, f"character_tab_{slot_id}", None)
            if lower_tab is None:
                continue
            coordinate_tab = lower_tab.sub_notebook.character_sub_tab_2
            if coordinate_tab is self:
                continue
            checkbox = coordinate_tab.swap_prompts_checkbox
            signals_blocked = checkbox.blockSignals(True)
            try:
                checkbox.setChecked(checked)
            finally:
                checkbox.blockSignals(signals_blocked)

    def refresh_position_spinbox_limit(self):
        main_window = self.window()
        if main_window is None:
            return

        left_column = getattr(main_window, "left_column_widget", None)
        if left_column is None:
            return

        slot_limit = self._get_active_slot_limit(left_column)
        self.position_spinbox.setRange(1, slot_limit)
        if self.position_spinbox.value() > slot_limit:
            self.position_spinbox.setValue(slot_limit)

    def _swap_slot_pair(self, source_slot, target_slot):
        if source_slot == target_slot:
            return

        main_window = self.window()
        if main_window is None:
            return

        left_column = getattr(main_window, "left_column_widget", None)
        if left_column is None:
            return

        source_middle = getattr(left_column.middle_frame, f"character_tab_{source_slot}", None)
        target_middle = getattr(left_column.middle_frame, f"character_tab_{target_slot}", None)
        source_lower = getattr(left_column.lower_frame, f"character_tab_{source_slot}", None)
        target_lower = getattr(left_column.lower_frame, f"character_tab_{target_slot}", None)

        if source_middle is None or target_middle is None or source_lower is None or target_lower is None:
            return

        source_state = source_middle.export_state() | source_lower.export_state(randomize_coordinates=False)
        target_state = target_middle.export_state() | target_lower.export_state(randomize_coordinates=False)
        swap_prompts = should_swap_slot_prompts(source_state, target_state)
        source_import_state = preserve_slot_prompt_state(
            preserve_slot_coordinate_state(target_state, source_state),
            source_state,
            swap_prompts,
        )
        target_import_state = preserve_slot_prompt_state(
            preserve_slot_coordinate_state(source_state, target_state),
            target_state,
            swap_prompts,
        )

        source_character = source_state.get("character", "None")
        target_character = target_state.get("character", "None")

        source_combo = source_middle.fluff_tab.character_select_combobox
        target_combo = target_middle.fluff_tab.character_select_combobox

        source_combo.blockSignals(True)
        target_combo.blockSignals(True)
        try:
            source_combo.setCurrentText(target_character)
            target_combo.setCurrentText(source_character)
        finally:
            source_combo.blockSignals(False)
            target_combo.blockSignals(False)

        source_middle.import_state(source_import_state)
        target_middle.import_state(target_import_state)

        source_middle.on_character_change()
        target_middle.on_character_change()

        source_lower.import_state(source_import_state, import_filters=False)
        target_lower.import_state(target_import_state, import_filters=False)

        source_button = left_column.middle_frame.button_group.button(source_slot - 1)
        target_button = left_column.middle_frame.button_group.button(target_slot - 1)
        if source_button is not None:
            left_column.middle_frame.update_tab_for_character(source_button, source_middle, str(source_slot))
        if target_button is not None:
            left_column.middle_frame.update_tab_for_character(target_button, target_middle, str(target_slot))

    def swap_slot(self):
        self.refresh_position_spinbox_limit()
        target_slot = int(self.position_spinbox.value())
        if target_slot == self.slot_id:
            return
        self._swap_slot_pair(self.slot_id, target_slot)

    def randomize_slots(self):
        main_window = self.window()
        if main_window is None:
            return

        left_column = getattr(main_window, "left_column_widget", None)
        if left_column is None:
            return

        slot_names = {}
        randomizable_slots = []
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            middle_tab = getattr(left_column.middle_frame, f"character_tab_{slot_id}", None)
            lower_tab = getattr(left_column.lower_frame, f"character_tab_{slot_id}", None)
            if middle_tab is not None and lower_tab is not None:
                slot_names[slot_id] = middle_tab.fluff_tab.character_select_combobox.currentText()
                coordinate_tab = lower_tab.sub_notebook.character_sub_tab_2
                if coordinate_tab.can_randomize_checkbox.isChecked():
                    randomizable_slots.append(slot_id)

        slot_limit = self._get_active_slot_limit(left_column)
        plan = get_randomized_swap_plan(slot_names, randomizable_slots, slot_limit)
        if not plan:
            return

        for source_slot, target_slot in plan:
            self._swap_slot_pair(source_slot, target_slot)

        self.refresh_position_spinbox_limit()

    def get_selected_coordinates(self):
        return self.horizontal_spinbox.value(), self.vertical_spinbox.value()

    def randomize_selected_coordinates(self):
        step_values = get_coordinate_step_values(self._model_type)
        self.horizontal_spinbox.setValue(random.choice(step_values))
        self.vertical_spinbox.setValue(random.choice(step_values))

    def set_auto_coordinates(self):
        auto_value = get_auto_coordinate_value(self._model_type)
        self.horizontal_spinbox.setValue(auto_value)
        self.vertical_spinbox.setValue(auto_value)

    def set_selected_coordinates(self, x_value, y_value):
        self.horizontal_spinbox.setValue(snap_coordinate_value(x_value, self._model_type))
        self.vertical_spinbox.setValue(snap_coordinate_value(y_value, self._model_type))

