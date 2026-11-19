import random

from PySide6.QtWidgets import QButtonGroup, QGridLayout, QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QSizePolicy, QSpinBox, QCheckBox, QDoubleSpinBox, QPushButton
from PySide6.QtCore import Qt
from data.datahub import get_data
from process.frequency import frequency_matches


MAX_SEED = 4294967294


def _coerce_bool(value):
        if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)


class ModifierSettingsTab(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.build_modifier_settings_tab()
        self.modifiers_ui_init()

    def build_modifier_settings_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(5)

        self.mode_button_frame = QFrame(self)
        self.mode_button_layout = QHBoxLayout(self.mode_button_frame)
        self.mode_button_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_button_layout.setSpacing(0)
        self.parameter_button = QPushButton("Parameter", self.mode_button_frame)
        self.parameter_button.setCheckable(True)
        self.parameter_button.setChecked(True)
        self.prompt_button = QPushButton("Prompt", self.mode_button_frame)
        self.prompt_button.setCheckable(True)
        self.mode_button_layout.addWidget(self.parameter_button)
        self.mode_button_layout.addWidget(self.prompt_button)
        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)
        self.mode_button_group.addButton(self.parameter_button, 0)
        self.mode_button_group.addButton(self.prompt_button, 1)
        self.grid.addWidget(self.mode_button_frame, 0, 0)

        self.stack = QStackedWidget(self)
        self.grid.addWidget(self.stack, 1, 0)
        self.grid.setRowStretch(1, 1)

        self.parameter_page = QFrame(self.stack)
        self.parameter_grid = QGridLayout(self.parameter_page)
        self.parameter_grid.setContentsMargins(0, 0, 0, 0)
        self.parameter_grid.setSpacing(0)
        self.parameter_grid.setRowStretch(1, 1)
        self.stack.addWidget(self.parameter_page)

        self.prompt_page = QFrame(self.stack)
        self.prompt_grid = QGridLayout(self.prompt_page)
        self.prompt_grid.setContentsMargins(8, 8, 8, 8)
        self.prompt_grid.setSpacing(8)
        self.stack.addWidget(self.prompt_page)
        self.mode_button_group.idToggled.connect(lambda button_id, checked: self.stack.setCurrentIndex(button_id) if checked else None)

        self.max_behavior_frame = QFrame(self.parameter_page)
        self.max_behavior_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.max_behavior_layout = QHBoxLayout(self.max_behavior_frame)
        self.max_behavior_layout.setContentsMargins(6, 4, 6, 4)
        self.max_behavior_layout.setSpacing(6)
        self.stop_on_max_button = QPushButton("Stop on Max", self.max_behavior_frame)
        self.stop_on_max_button.setCheckable(True)
        self.loop_on_max_button = QPushButton("Loop on Max", self.max_behavior_frame)
        self.loop_on_max_button.setCheckable(True)
        self.stop_on_max_button.setChecked(True)
        self.max_behavior_layout.addWidget(self.stop_on_max_button)
        self.max_behavior_layout.addWidget(self.loop_on_max_button)
        self.max_behavior_group = QButtonGroup(self)
        self.max_behavior_group.setExclusive(True)
        self.max_behavior_group.addButton(self.stop_on_max_button)
        self.max_behavior_group.addButton(self.loop_on_max_button)
        self.parameter_grid.addWidget(self.max_behavior_frame, 0, 0)

        # 1) Make one scroll area
        self.scroll = QScrollArea(self.parameter_page)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setWidgetResizable(True)                          # critical: width follows viewport
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setAlignment(Qt.AlignTop)
        self.parameter_grid.addWidget(self.scroll, 1, 0)

        # 2) Real content lives in here
        self.inner = QFrame()
        self.inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.inner_grid = QGridLayout(self.inner)
        self.inner_grid.setContentsMargins(8, 8, 8, 8)
        self.inner_grid.setSpacing(8)
        self.inner_grid.setColumnStretch(0, 1)

        self.scroll.setWidget(self.inner)

        self.scramble_global_positive_checkbox = QCheckBox("Scramble Global Positive", self.prompt_page)
        self.scramble_global_negative_checkbox = QCheckBox("Scramble Global Negative", self.prompt_page)
        self.scramble_character_positive_checkbox = QCheckBox("Scramble Character Positive", self.prompt_page)
        self.scramble_character_negative_checkbox = QCheckBox("Scramble Character Negative", self.prompt_page)
        self.prompt_grid.addWidget(self.scramble_global_positive_checkbox, 0, 0)
        self.prompt_grid.addWidget(self.scramble_global_negative_checkbox, 1, 0)
        self.prompt_grid.addWidget(self.scramble_character_positive_checkbox, 2, 0)
        self.prompt_grid.addWidget(self.scramble_character_negative_checkbox, 3, 0)
        self.prompt_grid.setRowStretch(4, 1)

        # --- sampler Creep ---

        self.sampler_creep_checkbox = QCheckBox("Sampler Creep", self.inner)
        self.sampler_creep_checkbox.toggled.connect(self.adjust_sampler_creep_ui)
        self.inner_grid.addWidget(self.sampler_creep_checkbox, 0, 0)

        self.sampler_creep_frequency_counter = QSpinBox(self.inner)
        self.sampler_creep_frequency_counter.setSingleStep(1)
        self.sampler_creep_frequency_counter.setPrefix("Frequency:   ")
        self.sampler_creep_frequency_counter.setMinimum(1)
        self.inner_grid.addWidget(self.sampler_creep_frequency_counter, 0, 1)

        # --- Schedule Creep ---

        self.schedule_creep_checkbox = QCheckBox("Schedule Creep", self.inner)
        self.schedule_creep_checkbox.toggled.connect(self.adjust_schedule_creep_ui)
        self.inner_grid.addWidget(self.schedule_creep_checkbox, 1, 0)

        self.schedule_creep_frequency_counter = QSpinBox(self.inner)
        self.schedule_creep_frequency_counter.setSingleStep(1)
        self.schedule_creep_frequency_counter.setPrefix("Frequency:   ")
        self.schedule_creep_frequency_counter.setMinimum(1)
        self.inner_grid.addWidget(self.schedule_creep_frequency_counter, 1, 1)

        # --- Seed Creep ---

        self.seed_creep_checkbox = QCheckBox("Seed Creep", self.inner)
        self.seed_creep_checkbox.toggled.connect(self.adjust_seed_creep_ui)
        self.inner_grid.addWidget(self.seed_creep_checkbox, 2, 0)

        self.seed_creep_frequency_counter = QSpinBox(self.inner)
        self.seed_creep_frequency_counter.setSingleStep(1)
        self.seed_creep_frequency_counter.setPrefix("Frequency:   ")
        self.seed_creep_frequency_counter.setMinimum(1)
        self.inner_grid.addWidget(self.seed_creep_frequency_counter, 2, 1)

        self.seed_creep_increment_counter = QSpinBox(self.inner)
        self.seed_creep_increment_counter.setSingleStep(1)
        self.seed_creep_increment_counter.setPrefix("Increment:   ")
        self.seed_creep_increment_counter.setMinimum(1)
        self.inner_grid.addWidget(self.seed_creep_increment_counter, 2, 2)

        self.seed_creep_min_counter = QDoubleSpinBox(self.inner)
        self.seed_creep_min_counter.setSingleStep(1)
        self.seed_creep_min_counter.setPrefix("Min:   ")
        self.seed_creep_min_counter.setDecimals(0)
        self.seed_creep_min_counter.setRange(0, MAX_SEED)
        self.inner_grid.addWidget(self.seed_creep_min_counter, 3, 1)

        self.seed_creep_max_counter = QDoubleSpinBox(self.inner)
        self.seed_creep_max_counter.setSingleStep(1)
        self.seed_creep_max_counter.setPrefix("Max:   ")
        self.seed_creep_max_counter.setDecimals(0)
        self.seed_creep_max_counter.setRange(0, MAX_SEED)
        self.seed_creep_max_counter.setValue(MAX_SEED)
        self.inner_grid.addWidget(self.seed_creep_max_counter, 3, 2)

        # --- Steps Creep ---

        self.steps_creep_checkbox = QCheckBox("Steps Creep", self.inner)
        self.steps_creep_checkbox.toggled.connect(self.adjust_steps_creep_ui)
        self.inner_grid.addWidget(self.steps_creep_checkbox, 4, 0)

        self.steps_random_button = QCheckBox("Steps Random", self.inner)
        self.steps_random_button.toggled.connect(self.adjust_steps_creep_ui)
        self.inner_grid.addWidget(self.steps_random_button, 4, 3)

        self.steps_creep_frequency_counter = QSpinBox(self.inner)
        self.steps_creep_frequency_counter.setSingleStep(1)
        self.steps_creep_frequency_counter.setPrefix("Frequency:   ")
        self.steps_creep_frequency_counter.setMinimum(1)
        self.inner_grid.addWidget(self.steps_creep_frequency_counter, 4, 1)

        self.steps_creep_increment_counter = QSpinBox(self.inner)
        self.steps_creep_increment_counter.setSingleStep(1)
        self.steps_creep_increment_counter.setPrefix("Increment:   ")
        self.steps_creep_increment_counter.setMinimum(1)
        self.inner_grid.addWidget(self.steps_creep_increment_counter, 4, 2)

        self.steps_creep_min_counter = QSpinBox(self.inner)
        self.steps_creep_min_counter.setSingleStep(1)
        self.steps_creep_min_counter.setPrefix("Min:   ")
        self.steps_creep_min_counter.setMinimum(1)
        self.inner_grid.addWidget(self.steps_creep_min_counter, 5, 1)

        self.steps_creep_max_counter = QSpinBox(self.inner)
        self.steps_creep_max_counter.setSingleStep(1)
        self.steps_creep_max_counter.setPrefix("Max:   ")
        self.steps_creep_max_counter.setMinimum(1)
        self.inner_grid.addWidget(self.steps_creep_max_counter, 5, 2)

        # --- Scale Creep ---

        self.scale_creep_checkbox = QCheckBox("Scale Creep", self.inner)
        self.scale_creep_checkbox.toggled.connect(self.adjust_scale_creep_ui)
        self.inner_grid.addWidget(self.scale_creep_checkbox, 6, 0)

        self.scale_random_button = QCheckBox("Scale Random", self.inner)
        self.scale_random_button.toggled.connect(self.adjust_scale_creep_ui)
        self.inner_grid.addWidget(self.scale_random_button, 6, 3)

        self.scale_creep_frequency_counter = QSpinBox(self.inner)
        self.scale_creep_frequency_counter.setSingleStep(1)
        self.scale_creep_frequency_counter.setPrefix("Frequency:   ")
        self.scale_creep_frequency_counter.setMinimum(1)
        self.inner_grid.addWidget(self.scale_creep_frequency_counter, 6, 1)

        self.scale_creep_increment_counter = QDoubleSpinBox(self.inner)
        self.scale_creep_increment_counter.setSingleStep(0.1)
        self.scale_creep_increment_counter.setPrefix("Increment:   ")
        self.scale_creep_increment_counter.setDecimals(1)
        self.scale_creep_increment_counter.setMinimum(0.1)
        self.inner_grid.addWidget(self.scale_creep_increment_counter, 6, 2)

        self.scale_creep_min_counter = QDoubleSpinBox(self.inner)
        self.scale_creep_min_counter.setSingleStep(0.1)
        self.scale_creep_min_counter.setPrefix("Min:   ")
        self.scale_creep_min_counter.setDecimals(1)
        self.scale_creep_min_counter.setMinimum(0.1)
        self.inner_grid.addWidget(self.scale_creep_min_counter, 7, 1)

        self.scale_creep_max_counter = QDoubleSpinBox(self.inner)
        self.scale_creep_max_counter.setSingleStep(0.1)
        self.scale_creep_max_counter.setPrefix("Max:   ")
        self.scale_creep_max_counter.setDecimals(1)
        self.scale_creep_max_counter.setMinimum(0.1)
        self.inner_grid.addWidget(self.scale_creep_max_counter, 7, 2)

        # --- CFG Creep ---

        self.cfg_creep_checkbox = QCheckBox("CFG Creep", self.inner)
        self.cfg_creep_checkbox.toggled.connect(self.adjust_cfg_creep_ui)
        self.inner_grid.addWidget(self.cfg_creep_checkbox, 8, 0)

        self.cfg_random_button = QCheckBox("CFG Random", self.inner)
        self.cfg_random_button.toggled.connect(self.adjust_cfg_creep_ui)
        self.inner_grid.addWidget(self.cfg_random_button, 8, 3)

        self.cfg_creep_frequency_counter = QSpinBox(self.inner)
        self.cfg_creep_frequency_counter.setSingleStep(1)
        self.cfg_creep_frequency_counter.setPrefix("Frequency:   ")
        self.cfg_creep_frequency_counter.setMinimum(1)
        self.inner_grid.addWidget(self.cfg_creep_frequency_counter, 8, 1)

        self.cfg_creep_increment_counter = QDoubleSpinBox(self.inner)
        self.cfg_creep_increment_counter.setSingleStep(0.1)
        self.cfg_creep_increment_counter.setPrefix("Increment:   ")
        self.cfg_creep_increment_counter.setDecimals(1)
        self.cfg_creep_increment_counter.setMinimum(0.1)
        self.inner_grid.addWidget(self.cfg_creep_increment_counter, 8, 2)

        self.cfg_creep_min_counter = QDoubleSpinBox(self.inner)
        self.cfg_creep_min_counter.setSingleStep(0.1)
        self.cfg_creep_min_counter.setPrefix("Min:   ")
        self.cfg_creep_min_counter.setDecimals(1)
        self.cfg_creep_min_counter.setMinimum(0.1)
        self.inner_grid.addWidget(self.cfg_creep_min_counter, 9, 1)

        self.cfg_creep_max_counter = QDoubleSpinBox(self.inner)
        self.cfg_creep_max_counter.setSingleStep(0.1)
        self.cfg_creep_max_counter.setPrefix("Max:   ")
        self.cfg_creep_max_counter.setDecimals(1)
        self.cfg_creep_max_counter.setMinimum(0.1)
        self.inner_grid.addWidget(self.cfg_creep_max_counter, 9, 2)

        self._organize_modifier_sections()

    def _organize_modifier_sections(self):
        while self.inner_grid.count():
                item = self.inner_grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                        widget.setParent(self.inner)

        sections = [
                (self.sampler_creep_checkbox, self.sampler_creep_frequency_counter),
                (self.schedule_creep_checkbox, self.schedule_creep_frequency_counter),
                (self.seed_creep_checkbox, self.seed_creep_frequency_counter, self.seed_creep_increment_counter, self.seed_creep_min_counter, self.seed_creep_max_counter),
                (self.steps_creep_checkbox, self.steps_random_button, self.steps_creep_frequency_counter, self.steps_creep_increment_counter, self.steps_creep_min_counter, self.steps_creep_max_counter),
                (self.scale_creep_checkbox, self.scale_random_button, self.scale_creep_frequency_counter, self.scale_creep_increment_counter, self.scale_creep_min_counter, self.scale_creep_max_counter),
                (self.cfg_creep_checkbox, self.cfg_random_button, self.cfg_creep_frequency_counter, self.cfg_creep_increment_counter, self.cfg_creep_min_counter, self.cfg_creep_max_counter),
        ]

        for index, controls in enumerate(sections):
                section_frame = QFrame(self.inner)
                section_frame.setObjectName("modifier_section")
                section_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                section_layout = QGridLayout(section_frame)
                section_layout.setContentsMargins(8, 6, 8, 8)
                section_layout.setHorizontalSpacing(8)
                section_layout.setVerticalSpacing(6)
                section_layout.setColumnStretch(0, 1)
                section_layout.setColumnStretch(1, 1)

                random_button = controls[1] if len(controls) > 2 and isinstance(controls[1], QCheckBox) else None
                numeric_controls = controls[2:] if random_button is not None else controls[1:]
                controls[0].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                section_layout.addWidget(controls[0], 0, 0)
                if random_button is not None:
                        random_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                        section_layout.addWidget(random_button, 0, 1)

                for control_index, control in enumerate(numeric_controls):
                        control.setMinimumWidth(120)
                        control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                        row, column = divmod(control_index, 2)
                        section_layout.addWidget(control, row + 1, column)

                self.inner_grid.addWidget(section_frame, index, 0)

        self.inner_grid.setColumnStretch(0, 1)
        self.inner_grid.setRowStretch(len(sections), 1)

    def adjust_sampler_creep_ui(self):
        state = self.sampler_creep_checkbox.isChecked()
        if state:
                self.sampler_creep_frequency_counter.setDisabled(False)
        else:
            self.sampler_creep_frequency_counter.setDisabled(True)
            
    def adjust_schedule_creep_ui(self):
        state = self.schedule_creep_checkbox.isChecked()
        if state:
                self.schedule_creep_frequency_counter.setDisabled(False)
        else:
            self.schedule_creep_frequency_counter.setDisabled(True)

    def adjust_seed_creep_ui(self):
        state = self.seed_creep_checkbox.isChecked()
        self.seed_creep_frequency_counter.setDisabled(not state)
        self.seed_creep_increment_counter.setDisabled(not state)
        self.seed_creep_min_counter.setDisabled(not state)
        self.seed_creep_max_counter.setDisabled(not state)

    def adjust_steps_creep_ui(self):
                self._sync_exclusive_modifier_mode(self.steps_creep_checkbox, self.steps_random_button)
                self._apply_numeric_modifier_controls(
                        self.steps_creep_checkbox,
                        self.steps_random_button,
                        self.steps_creep_frequency_counter,
                        self.steps_creep_increment_counter,
                        self.steps_creep_min_counter,
                        self.steps_creep_max_counter,
                )

    def adjust_scale_creep_ui(self):
                self._sync_exclusive_modifier_mode(self.scale_creep_checkbox, self.scale_random_button)
                self._apply_numeric_modifier_controls(
                        self.scale_creep_checkbox,
                        self.scale_random_button,
                        self.scale_creep_frequency_counter,
                        self.scale_creep_increment_counter,
                        self.scale_creep_min_counter,
                        self.scale_creep_max_counter,
                )

    def adjust_cfg_creep_ui(self):
                self._sync_exclusive_modifier_mode(self.cfg_creep_checkbox, self.cfg_random_button)
                self._apply_numeric_modifier_controls(
                        self.cfg_creep_checkbox,
                        self.cfg_random_button,
                        self.cfg_creep_frequency_counter,
                        self.cfg_creep_increment_counter,
                        self.cfg_creep_min_counter,
                        self.cfg_creep_max_counter,
                )

    def _sync_exclusive_modifier_mode(self, creep_checkbox, random_button):
            sender = self.sender()
            if sender is creep_checkbox and creep_checkbox.isChecked():
                    random_button.blockSignals(True)
                    random_button.setChecked(False)
                    random_button.blockSignals(False)
            elif sender is random_button and random_button.isChecked():
                    creep_checkbox.blockSignals(True)
                    creep_checkbox.setChecked(False)
                    creep_checkbox.blockSignals(False)

    def _apply_numeric_modifier_controls(self, creep_checkbox, random_button, frequency_counter, increment_counter, *range_counters):
            creep_enabled = creep_checkbox.isChecked()
            random_enabled = random_button.isChecked()
            frequency_counter.setDisabled(not (creep_enabled or random_enabled))
            increment_counter.setDisabled(not creep_enabled)
            for range_counter in range_counters:
                    range_counter.setDisabled(not (creep_enabled or random_enabled))

    def modifiers_ui_init(self):
         self.adjust_sampler_creep_ui()
         self.adjust_schedule_creep_ui()
         self.adjust_seed_creep_ui()
         self.adjust_steps_creep_ui()
         self.adjust_scale_creep_ui()
         self.adjust_cfg_creep_ui()

    def export_state(self):
            return {
                    "sampler_creep": self.sampler_creep_checkbox.isChecked(),
                    "sampler_creep_frequency": self.sampler_creep_frequency_counter.value(),
                    "schedule_creep": self.schedule_creep_checkbox.isChecked(),
                    "schedule_creep_frequency": self.schedule_creep_frequency_counter.value(),
                    "seed_creep": self.seed_creep_checkbox.isChecked(),
                    "seed_creep_frequency": self.seed_creep_frequency_counter.value(),
                    "seed_creep_increment": self.seed_creep_increment_counter.value(),
                    "seed_creep_min": self.seed_creep_min_counter.value(),
                    "seed_creep_max": self.seed_creep_max_counter.value(),
                    "steps_creep": self.steps_creep_checkbox.isChecked(),
                    "steps_random": self.steps_random_button.isChecked(),
                    "steps_creep_frequency": self.steps_creep_frequency_counter.value(),
                    "steps_creep_increment": self.steps_creep_increment_counter.value(),
                    "steps_creep_min": self.steps_creep_min_counter.value(),
                    "steps_creep_max": self.steps_creep_max_counter.value(),
                    "scale_creep": self.scale_creep_checkbox.isChecked(),
                    "scale_random": self.scale_random_button.isChecked(),
                    "scale_creep_frequency": self.scale_creep_frequency_counter.value(),
                    "scale_creep_increment": self.scale_creep_increment_counter.value(),
                    "scale_creep_min": self.scale_creep_min_counter.value(),
                    "scale_creep_max": self.scale_creep_max_counter.value(),
                    "cfg_creep": self.cfg_creep_checkbox.isChecked(),
                    "cfg_random": self.cfg_random_button.isChecked(),
                    "cfg_creep_frequency": self.cfg_creep_frequency_counter.value(),
                    "cfg_creep_increment": self.cfg_creep_increment_counter.value(),
                    "cfg_creep_min": self.cfg_creep_min_counter.value(),
                    "cfg_creep_max": self.cfg_creep_max_counter.value(),
                    "scramble_global_positive": self.scramble_global_positive_checkbox.isChecked(),
                    "scramble_global_negative": self.scramble_global_negative_checkbox.isChecked(),
                    "scramble_character_positive": self.scramble_character_positive_checkbox.isChecked(),
                    "scramble_character_negative": self.scramble_character_negative_checkbox.isChecked(),
                    "max_behavior": "loop" if self.loop_on_max_button.isChecked() else "stop",
            }

    def import_state(self, state):
            controls = {
                    "sampler_creep": self.sampler_creep_checkbox,
                    "schedule_creep": self.schedule_creep_checkbox,
                    "seed_creep": self.seed_creep_checkbox,
                    "steps_creep": self.steps_creep_checkbox,
                    "steps_random": self.steps_random_button,
                    "scale_creep": self.scale_creep_checkbox,
                    "scale_random": self.scale_random_button,
                    "cfg_creep": self.cfg_creep_checkbox,
                    "cfg_random": self.cfg_random_button,
                    "scramble_global_positive": self.scramble_global_positive_checkbox,
                    "scramble_global_negative": self.scramble_global_negative_checkbox,
                    "scramble_character_positive": self.scramble_character_positive_checkbox,
                    "scramble_character_negative": self.scramble_character_negative_checkbox,
            }
            for key, checkbox in controls.items():
                    checkbox.setChecked(_coerce_bool(state.get(key, False)))

            spinboxes = {
                    "sampler_creep_frequency": self.sampler_creep_frequency_counter,
                    "schedule_creep_frequency": self.schedule_creep_frequency_counter,
                    "seed_creep_frequency": self.seed_creep_frequency_counter,
                    "seed_creep_increment": self.seed_creep_increment_counter,
                    "seed_creep_min": self.seed_creep_min_counter,
                    "seed_creep_max": self.seed_creep_max_counter,
                    "steps_creep_frequency": self.steps_creep_frequency_counter,
                    "steps_creep_increment": self.steps_creep_increment_counter,
                    "steps_creep_min": self.steps_creep_min_counter,
                    "steps_creep_max": self.steps_creep_max_counter,
                    "scale_creep_frequency": self.scale_creep_frequency_counter,
                    "scale_creep_increment": self.scale_creep_increment_counter,
                    "scale_creep_min": self.scale_creep_min_counter,
                    "scale_creep_max": self.scale_creep_max_counter,
                    "cfg_creep_frequency": self.cfg_creep_frequency_counter,
                    "cfg_creep_increment": self.cfg_creep_increment_counter,
                    "cfg_creep_min": self.cfg_creep_min_counter,
                    "cfg_creep_max": self.cfg_creep_max_counter,
            }
            for key, spinbox in spinboxes.items():
                    if key in state:
                            spinbox.setValue(state[key])
            if state.get("max_behavior") == "loop":
                    self.loop_on_max_button.setChecked(True)
            else:
                    self.stop_on_max_button.setChecked(True)

    @staticmethod
    def _increment_with_wrap(current, increment, lower, upper):
            next_value = current + increment
            if next_value > upper:
                    return lower
            return max(lower, min(upper, next_value))

    @staticmethod
    def _random_float(lower, upper, decimals=1):
            return round(random.uniform(lower, upper), decimals)

    @staticmethod
    def _advance_combobox(combobox):
            item_count = combobox.count()
            if item_count <= 0:
                    return
            combobox.setCurrentIndex((combobox.currentIndex() + 1) % item_count)

    def apply_modifiers(self, generation_number=1):
            settings = self.export_state()
            generate_tab = self.window().left_column_widget.upper_frame.page0.image_master_stack_generate
            settings_tab = generate_tab.image_settings_tab

            if settings["seed_creep"] and frequency_matches(settings["seed_creep_frequency"], generation_number):
                    lower, upper = sorted((int(settings["seed_creep_min"]), int(settings["seed_creep_max"])))
                    if self.loop_on_max_button.isChecked():
                            seed = self._increment_with_wrap(
                                    int(settings_tab.seed_select_counter.value()),
                                    settings["seed_creep_increment"],
                                    lower,
                                    upper,
                            )
                    else:
                            seed = int(settings_tab.seed_select_counter.value()) + settings["seed_creep_increment"]
                    settings_tab.seed_select_counter.setValue(seed)

            if settings["steps_random"] and frequency_matches(settings["steps_creep_frequency"], generation_number):
                    lower, upper = sorted((settings["steps_creep_min"], settings["steps_creep_max"]))
                    settings_tab.steps_select_counter.setValue(random.randint(lower, upper))
            elif settings["steps_creep"] and frequency_matches(settings["steps_creep_frequency"], generation_number):
                    lower, upper = sorted((settings["steps_creep_min"], settings["steps_creep_max"]))
                    steps = settings_tab.steps_select_counter.value() + settings["steps_creep_increment"]
                    if self.loop_on_max_button.isChecked():
                            steps = self._increment_with_wrap(
                                    settings_tab.steps_select_counter.value(),
                                    settings["steps_creep_increment"],
                                    lower,
                                    upper,
                            )
                    settings_tab.steps_select_counter.setValue(max(lower, min(upper, steps)))

            if settings["scale_random"] and frequency_matches(settings["scale_creep_frequency"], generation_number):
                    lower, upper = sorted((settings["scale_creep_min"], settings["scale_creep_max"]))
                    settings_tab.scale_select_counter.setValue(self._random_float(lower, upper, decimals=1))
            elif settings["scale_creep"] and frequency_matches(settings["scale_creep_frequency"], generation_number):
                    lower, upper = sorted((settings["scale_creep_min"], settings["scale_creep_max"]))
                    scale = settings_tab.scale_select_counter.value() + settings["scale_creep_increment"]
                    if self.loop_on_max_button.isChecked():
                            scale = self._increment_with_wrap(
                                    settings_tab.scale_select_counter.value(),
                                    settings["scale_creep_increment"],
                                    lower,
                                    upper,
                            )
                    settings_tab.scale_select_counter.setValue(max(lower, min(upper, scale)))

            if settings["cfg_random"] and frequency_matches(settings["cfg_creep_frequency"], generation_number):
                    lower, upper = sorted((settings["cfg_creep_min"], settings["cfg_creep_max"]))
                    settings_tab.cfg_select_counter.setValue(round(random.uniform(lower, upper)))
            elif settings["cfg_creep"] and frequency_matches(settings["cfg_creep_frequency"], generation_number):
                    lower, upper = sorted((settings["cfg_creep_min"], settings["cfg_creep_max"]))
                    cfg = settings_tab.cfg_select_counter.value() + settings["cfg_creep_increment"]
                    if self.loop_on_max_button.isChecked():
                            cfg = self._increment_with_wrap(
                                    settings_tab.cfg_select_counter.value(),
                                    settings["cfg_creep_increment"],
                                    lower,
                                    upper,
                            )
                    settings_tab.cfg_select_counter.setValue(max(lower, min(upper, cfg)))

            if settings["sampler_creep"] and frequency_matches(settings["sampler_creep_frequency"], generation_number):
                    self._advance_combobox(settings_tab.sampler_select_combobox)

            if settings["schedule_creep"] and frequency_matches(settings["schedule_creep_frequency"], generation_number):
                    self._advance_combobox(settings_tab.schedule_select_combobox)

            return None


"""
this whole tab is basically bad code, there are much better ways to build the tab and to run functions in it. Also, consider putting all the sections in their 
own container and using 3columns of stretch,. It's fine as it is but that would give more flexibility for coloring it in.  
"""

         






        

        

        

        

        

        

        

        

        
