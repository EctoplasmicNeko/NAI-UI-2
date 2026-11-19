from copy import deepcopy

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QTextEdit,
)
from widget.decorated_combobox import DecoratedComboBox
from PySide6.QtCore import Qt
from data.character_slots import MAX_CHARACTER_SLOTS
from data.datahub import get_data


class PromptSettingsTab(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.build_prompt_settings_tab()

    def build_prompt_settings_tab(self):

        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(1)

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.grid.setColumnStretch(0, 0)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 0)
        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 1)   
        self.grid.setRowStretch(2, 0)
        self.grid.setRowStretch(3, 1)   
        self.grid.setRowStretch(4, 0)
        self.grid.setRowStretch(5, 0)   

        self.positive_presets = get_data("positive_preset", []) #load the  dictionary from the data cache
        self.positive_preset_names = [pos_preset["name"] for pos_preset in self.positive_presets]

        self.negative_presets = get_data("negative_preset", []) #load the  dictionary from the data cache
        self.negative_preset_names = [neg_preset["name"] for neg_preset in self.negative_presets]

        self.positive_button_frame = QFrame(self)
        self.grid.addWidget(self.positive_button_frame, 0, 0)
        self.positive_button_frame_grid = QGridLayout(self.positive_button_frame)
        self.positive_button_frame_grid.setContentsMargins(0,0,0,0) 
        self.positive_button_frame_grid.setSpacing(0)   
        self.positive_button_frame_grid.setAlignment(Qt.AlignTop)

        self.positive_button_group = QButtonGroup(self)
        self.positive_button_group.setExclusive(True)

        self.positive_prompt_button = QPushButton("P")
        self.positive_prompt_button.setCheckable(True)  
        self.positive_prompt_button.setChecked(True)
        self.positive_button_group.addButton(self.positive_prompt_button)
        self.positive_button_frame_grid.addWidget(self.positive_prompt_button, 0, 0)    
        self.positive_prompt_button.setFixedSize(30, 30)
        self.positive_prompt_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.positive_prompt_button.clicked.connect(lambda: self.set_positive_mode(0, 'Positive Global Prompt', self.positive_prompt_textbox))

        self.positive_character_button = QPushButton("Q")
        self.positive_character_button.setCheckable(True)   
        self.positive_button_group.addButton(self.positive_character_button)
        self.positive_button_frame_grid.addWidget(self.positive_character_button, 0, 1)    
        self.positive_character_button.setFixedSize(30, 30)
        self.positive_character_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.positive_character_button.clicked.connect(lambda: self.set_positive_mode(1, 'Positive Quality Preset', self.positive_preset_textbox))
        
        self.positive_prompt_label = QPushButton('Positive Global Prompt', self)
        self.positive_prompt_label.setObjectName("positive_prompt_label")
        self.positive_prompt_label.setCheckable(True)
        self.positive_prompt_label.setFixedHeight(30)
        self.positive_prompt_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.positive_prompt_label.setToolTip(
            "Positive Global Prompt — click to preview the compiled positive prompt."
        )
        self.positive_prompt_label.toggled.connect(self._toggle_positive_preview)
        self.grid.addWidget(self.positive_prompt_label, 0, 1,)

        self.positive_prompts_delete_button = QPushButton(self)
        self.positive_prompts_delete_button.setObjectName("positive_prompts_delete_button")
        self.positive_prompts_delete_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.positive_prompts_delete_button.setToolTip("Clear the selected positive prompt.")
        self.positive_prompts_delete_button.setAccessibleName("Clear positive prompt")
        self.positive_prompts_delete_button.pressed.connect(lambda: self.positive_current_textbox.clear())
        self.positive_prompts_delete_button.setFixedSize(30, 30)
        self.grid.addWidget(self.positive_prompts_delete_button, 0, 2,)

        self.positive_prompt_stack = QStackedWidget(self)
        self.grid.addWidget(self.positive_prompt_stack, 1, 0, 1, 3)

        self.positive_prompt_textbox = QTextEdit(self)
        self.positive_prompt_textbox.setMinimumHeight(80)
        self.positive_prompt_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_prompt_stack.addWidget(self.positive_prompt_textbox)

        self.positive_preset_textbox = QTextEdit(self)
        self.positive_preset_textbox.setMinimumHeight(80)
        self.positive_preset_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_prompt_stack.addWidget(self.positive_preset_textbox)

        self.positive_compiled_preview = QTextEdit(self)
        self.positive_compiled_preview.setReadOnly(True)
        self.positive_compiled_preview.setMinimumHeight(80)
        self.positive_compiled_preview.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_compiled_preview.setPlaceholderText("No compiled positive prompt.")
        self.positive_prompt_stack.addWidget(self.positive_compiled_preview)

        self.positive_current_textbox = self.positive_prompt_textbox



        self.negative_button_frame = QFrame(self)
        self.grid.addWidget(self.negative_button_frame, 2, 0)
        self.negative_button_frame_grid = QGridLayout(self.negative_button_frame)
        self.negative_button_frame_grid.setContentsMargins(0,0,0,0) 
        self.negative_button_frame_grid.setSpacing(0)   
        self.negative_button_frame_grid.setAlignment(Qt.AlignTop)

        self.negative_button_group = QButtonGroup(self)
        self.negative_button_group.setExclusive(True)
        self.negative_prompt_button = QPushButton("P")
        self.negative_prompt_button.setCheckable(True)  
        self.negative_prompt_button.setChecked(True)
        self.negative_button_group.addButton(self.negative_prompt_button)
        self.negative_button_frame_grid.addWidget(self.negative_prompt_button, 0, 0)    
        self.negative_prompt_button.setFixedSize(30, 30)
        self.negative_prompt_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.negative_prompt_button.clicked.connect(lambda: self.set_negative_mode(0, 'Negative Global Prompt', self.negative_prompt_textbox))

        self.negative_character_button = QPushButton("Q")
        self.negative_character_button.setCheckable(True)   
        self.negative_button_group.addButton(self.negative_character_button)
        self.negative_button_frame_grid.addWidget(self.negative_character_button, 0, 1)    
        self.negative_character_button.setFixedSize(30, 30)
        self.negative_character_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.negative_character_button.clicked.connect(lambda: self.set_negative_mode(1, 'Negative Quality Preset', self.negative_preset_textbox))
        
        self.negative_prompt_label = QPushButton('Negative Global Prompt', self)
        self.negative_prompt_label.setObjectName("negative_prompt_label")
        self.negative_prompt_label.setCheckable(True)
        self.negative_prompt_label.setFixedHeight(30)
        self.negative_prompt_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.negative_prompt_label.setToolTip(
            "Negative Global Prompt — click to preview the compiled negative prompt."
        )
        self.negative_prompt_label.toggled.connect(self._toggle_negative_preview)
        self.grid.addWidget(self.negative_prompt_label, 2, 1,)

        self.negative_prompts_delete_button = QPushButton(self)
        self.negative_prompts_delete_button.setObjectName("negative_prompts_delete_button")
        self.negative_prompts_delete_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.negative_prompts_delete_button.setToolTip("Clear the selected negative prompt.")
        self.negative_prompts_delete_button.setAccessibleName("Clear negative prompt")
        self.negative_prompts_delete_button.pressed.connect(lambda: self.negative_current_textbox.clear())
        self.negative_prompts_delete_button.setFixedSize(30, 30)
        self.grid.addWidget(self.negative_prompts_delete_button, 2, 2,)

        self.negative_prompt_stack = QStackedWidget(self)
        self.grid.addWidget(self.negative_prompt_stack, 3, 0, 1, 3)

        self.negative_prompt_textbox = QTextEdit(self)
        self.negative_prompt_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_prompt_textbox.setMinimumHeight(80)
        self.negative_prompt_stack.addWidget(self.negative_prompt_textbox)

        self.negative_preset_textbox = QTextEdit(self)
        self.negative_preset_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_preset_textbox.setMinimumHeight(80)
        self.negative_prompt_stack.addWidget(self.negative_preset_textbox)

        self.negative_compiled_preview = QTextEdit(self)
        self.negative_compiled_preview.setReadOnly(True)
        self.negative_compiled_preview.setMinimumHeight(80)
        self.negative_compiled_preview.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_compiled_preview.setPlaceholderText("No compiled negative prompt.")
        self.negative_prompt_stack.addWidget(self.negative_compiled_preview)

        self.negative_current_textbox = self.negative_prompt_textbox

        self.global_positive_preset_combobox = DecoratedComboBox(self)
        self.global_positive_preset_combobox.addItems(self.positive_preset_names)
        self.global_positive_preset_combobox.setPrefix("Positive Quality Preset: ")
        self.global_positive_preset_combobox.currentIndexChanged.connect(lambda: self.store_positive_preset())
        self.grid.addWidget(self.global_positive_preset_combobox, 4,0,1,3)

        self.global_negative_preset_combobox = DecoratedComboBox(self)
        self.global_negative_preset_combobox.addItems(self.negative_preset_names)
        self.global_negative_preset_combobox.setPrefix("Negative Quality Preset: ")
        self.global_negative_preset_combobox.currentIndexChanged.connect(lambda: self.store_negative_preset())
        self.grid.addWidget(self.global_negative_preset_combobox, 5,0,1,3)

        self.character_number_counter = QSpinBox(self)
        self.character_number_counter.setPrefix("Characters:   ")
        self.character_number_counter.setRange(0, MAX_CHARACTER_SLOTS)
        self.grid.addWidget(self.character_number_counter, 6, 0, 1, 3)


    def store_positive_preset(self):
        selected = self.global_positive_preset_combobox.currentText()
        if selected == 'None':
            self.negative_preset_textbox.clear()
            self.global_positive_preset_combobox.setProperty('target', "")
        else:
            for preset in self.positive_presets:
                if preset['name'] == selected:
                    self.positive_preset_textbox.setText(preset['tags'])
                    self.global_positive_preset_combobox.setProperty('target', preset['target'])

    def store_negative_preset(self):
        selected = self.global_negative_preset_combobox.currentText()
        if selected == 'None':
            self.negative_preset_textbox.clear()
        else:
            for preset in self.negative_presets:
                if preset['name'] == selected:
                    self.negative_preset_textbox.setText(preset['tags'])


    def export_state(self):
        return {
            'global_positive_prompt': self.positive_prompt_textbox.toPlainText(),
            'global_negative_prompt': self.negative_prompt_textbox.toPlainText(),
            'global_positive_preset_name': self.global_positive_preset_combobox.currentText(),
            'global_positive_preset_tags': self.positive_preset_textbox.toPlainText(),
            'global_positive_preset_target': self.global_positive_preset_combobox.property('target') or None,
            'global_negative_preset_name': self.global_negative_preset_combobox.currentText(),
            'global_negative_preset_tags': self.negative_preset_textbox.toPlainText(),
            'character_number': self.character_number_counter.value()
        }
    
    
    def import_state(self, loaded):
        self.global_positive_preset_combobox.setCurrentText(loaded['global_positive_preset_name'])
        self.global_negative_preset_combobox.setCurrentText(loaded['global_negative_preset_name'])
        self.positive_prompt_textbox.setText(loaded['global_positive_prompt'])
        self.negative_prompt_textbox.setText(loaded['global_negative_prompt'])
        self.positive_preset_textbox.setText(loaded['global_positive_preset_tags'])
        self.negative_preset_textbox.setText(loaded['global_negative_preset_tags'])
        self.character_number_counter.setValue(loaded['character_number'])


    def set_negative_mode(self, index, label, textbox):
        self.negative_prompt_label.setChecked(False)
        self.negative_prompt_stack.setCurrentIndex(index)
        self.negative_prompt_label.setText(label)
        self.negative_current_textbox = textbox
        self.negative_prompts_delete_button.setEnabled(True)


    def set_positive_mode(self, index, label, textbox):
        self.positive_prompt_label.setChecked(False)
        self.positive_prompt_stack.setCurrentIndex(index)
        self.positive_prompt_label.setText(label)
        self.positive_current_textbox = textbox
        self.positive_prompts_delete_button.setEnabled(True)

    def _compiled_prompt(self, positive):
        main_window = self.window()
        if not hasattr(main_window, "get_ui_state"):
            raise RuntimeError("Cannot compile a prompt preview without the main window UI state.")

        state = deepcopy(main_window.get_ui_state())
        version = state["generate"]["payload_type"]
        character_count = state["global_prompt"].get("character_number", 0)
        for slot_id in range(1, character_count + 1):
            state[f"character_{slot_id}"]["_pending_negative_injections"] = []

        from process.process_generate import prepare_negative_prompt, prepare_positive_prompt

        if positive:
            return prepare_positive_prompt(state, version)
        prepare_positive_prompt(state, version)
        return prepare_negative_prompt(state, version)

    def _toggle_positive_preview(self, enabled):
        if enabled:
            self.positive_compiled_preview.setPlainText(self._compiled_prompt(True))
            self.positive_prompt_stack.setCurrentWidget(self.positive_compiled_preview)
            self.positive_prompts_delete_button.setEnabled(False)
        else:
            self.positive_prompt_stack.setCurrentWidget(self.positive_current_textbox)
            self.positive_prompts_delete_button.setEnabled(True)

    def _toggle_negative_preview(self, enabled):
        if enabled:
            self.negative_compiled_preview.setPlainText(self._compiled_prompt(False))
            self.negative_prompt_stack.setCurrentWidget(self.negative_compiled_preview)
            self.negative_prompts_delete_button.setEnabled(False)
        else:
            self.negative_prompt_stack.setCurrentWidget(self.negative_current_textbox)
            self.negative_prompts_delete_button.setEnabled(True)
