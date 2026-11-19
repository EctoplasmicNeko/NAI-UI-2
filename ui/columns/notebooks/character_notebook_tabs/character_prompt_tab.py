from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QFrame, QTextEdit, QPushButton, QSizePolicy, QButtonGroup, QStackedWidget, QStyle

class CharacterPromptTab(QFrame):
    positive_preview_requested = Signal(bool)
    negative_preview_requested = Signal(bool)

    def __init__(self, parent):
        super().__init__(parent)
        self.build_character_prompt_tab()

    def build_character_prompt_tab(self):

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 5, 0, 0)
        self.grid.setSpacing(5)

        self.grid.setColumnStretch(0, 0)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(2, 0)

        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 1)   
        self.grid.setRowStretch(2, 0)
        self.grid.setRowStretch(3, 1)
        
        self.positive_prompt_title_bar = QFrame(self)
        self.grid.addWidget(self.positive_prompt_title_bar, 0, 0, 1, 3)
        self.positive_prompt_title_bar.setObjectName("positive_prompt_title_bar")
        self.positive_prompt_title_bar_grid = QGridLayout(self.positive_prompt_title_bar)
        self.positive_prompt_title_bar_grid.setContentsMargins(0,0,0,0) 
        self.positive_prompt_title_bar_grid.setSpacing(0)
        self.positive_prompt_title_bar_grid.setAlignment(Qt.AlignTop)
        self.positive_prompt_title_bar_grid.setColumnStretch(0, 0)
        self.positive_prompt_title_bar_grid.setColumnStretch(1, 1)  
        self.positive_prompt_title_bar_grid.setColumnStretch(2, 0)  

        self.positive_left_button_frame = QFrame(self)
        self.positive_left_button_frame.setObjectName("positive_left_button_frame")
        self.positive_prompt_title_bar_grid.addWidget(self.positive_left_button_frame, 0, 0)
        self.positive_left_button_frame_grid = QGridLayout(self.positive_left_button_frame)
        self.positive_left_button_frame_grid.setContentsMargins(0,0,0,0) 
        self.positive_left_button_frame_grid.setSpacing(0)
        self.positive_left_button_frame_grid.setAlignment(Qt.AlignTop)

        self.positive_button_group = QButtonGroup(self)
        self.positive_button_group.setObjectName("positive_button_group")
        self.positive_button_group.setExclusive(True)

        self.positive_prompt_button = QPushButton("P")
        self.positive_prompt_button.setObjectName("positive_prompt_button")
        self.positive_prompt_button.setCheckable(True) 
        self.positive_prompt_button.setChecked(True)
        self.positive_button_group.addButton(self.positive_prompt_button)
        self.positive_left_button_frame_grid.addWidget(self.positive_prompt_button, 0, 0)
        self.positive_prompt_button.setFixedSize(30, 30)
        self.positive_prompt_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        self.positive_character_button = QPushButton("C")
        self.positive_character_button.setObjectName("positive_character_button")
        self.positive_character_button.setCheckable(True)
        self.positive_character_button.setChecked(False)
        self.positive_button_group.addButton(self.positive_character_button)
        self.positive_left_button_frame_grid.addWidget(self.positive_character_button, 0, 1)
        self.positive_character_button.setFixedSize(30, 30)
        self.positive_character_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)  

        self.positive_static_button = QPushButton("S")
        self.positive_static_button.setObjectName("positive_static_button")
        self.positive_static_button.setCheckable(True)
        self.positive_static_button.setChecked(False)
        self.positive_button_group.addButton(self.positive_static_button)
        self.positive_left_button_frame_grid.addWidget(self.positive_static_button, 0, 2)
        self.positive_static_button.setFixedSize(30, 30)
        self.positive_static_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.positive_static_button.setToolTip("Static positive prompt; remains attached to this slot during swaps.")

        self.positive_prompt_label = QPushButton('Positive Prompt', self)
        self.positive_prompt_label.setObjectName("positive_prompt_label")
        self.positive_prompt_label.setFixedHeight(30)
        self.positive_prompt_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.positive_prompt_label.setCheckable(True)
        self.positive_prompt_label.setToolTip("Positive Prompt — click to preview the compiled character prompt.")
        self.positive_prompt_label.clicked.connect(
            lambda checked: self.positive_preview_requested.emit(checked)
        )
        self.positive_prompt_title_bar_grid.addWidget(self.positive_prompt_label, 0, 1)

        self.positive_right_button_frame = QFrame(self)
        self.positive_right_button_frame.setObjectName("positive_right_button_frame")
        self.positive_prompt_title_bar_grid.addWidget(self.positive_right_button_frame, 0, 2)
        self.positive_right_button_frame_grid = QGridLayout(self.positive_right_button_frame)
        self.positive_right_button_frame_grid.setContentsMargins(0,0,0,0) 
        self.positive_right_button_frame_grid.setSpacing(0)
        self.positive_right_button_frame_grid.setAlignment(Qt.AlignTop)

        self.positive_prompt_outfit_button = QPushButton("O")
        self.positive_prompt_outfit_button.setObjectName("positive_prompt_outfit_button")
        self.positive_prompt_outfit_button.setCheckable(True) 
        self.positive_prompt_outfit_button.setChecked(True)
        self.positive_button_group.addButton(self.positive_prompt_outfit_button)
        self.positive_right_button_frame_grid.addWidget(self.positive_prompt_outfit_button, 0, 0)
        self.positive_prompt_outfit_button.setFixedSize(30, 30)
        self.positive_prompt_outfit_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        self.positive_global_button = QPushButton("G")
        self.positive_global_button.setObjectName("positive_global_button")
        self.positive_global_button.setCheckable(True)
        self.positive_global_button.setChecked(False)
        self.positive_button_group.addButton(self.positive_global_button)
        self.positive_right_button_frame_grid.addWidget(self.positive_global_button, 0, 1)
        self.positive_global_button.setFixedSize(30, 30)
        self.positive_global_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.positive_global_button.setToolTip("Character tags added to the global positive prompt.")

        self.positive_prompt_delete_button = QPushButton(self)
        self.positive_prompt_delete_button.setObjectName("positive_prompt_delete_button")
        self.positive_prompt_delete_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.positive_prompt_delete_button.setToolTip("Clear the selected positive prompt.")
        self.positive_prompt_delete_button.setAccessibleName("Clear positive prompt")
        self.positive_prompt_delete_button.pressed.connect(lambda: self.positive_current_textbox.clear())
        self.positive_prompt_delete_button.setFixedSize(30, 30)
        self.positive_prompt_delete_button.setMinimumHeight(30)
        self.positive_right_button_frame_grid.addWidget(self.positive_prompt_delete_button, 0, 2,)

        self.positive_stack = QStackedWidget(self)
        self.grid.addWidget(self.positive_stack, 1, 0, 1, 3)

        self.positive_prompt_textbox = QTextEdit(self)
        self.positive_prompt_textbox.setMinimumHeight(50)
        self.positive_prompt_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_stack.addWidget(self.positive_prompt_textbox)

        self.positive_prompt_character_textbox = QTextEdit(self)
        self.positive_prompt_character_textbox.setMinimumHeight(50)
        self.positive_prompt_character_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_stack.addWidget(self.positive_prompt_character_textbox)

        self.positive_prompt_global_textbox = QTextEdit(self)
        self.positive_prompt_global_textbox.setMinimumHeight(50)
        self.positive_prompt_global_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_stack.addWidget(self.positive_prompt_global_textbox)

        self.positive_prompt_outfit_textbox = QTextEdit(self)
        self.positive_prompt_outfit_textbox.setMinimumHeight(50)
        self.positive_prompt_outfit_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_stack.addWidget(self.positive_prompt_outfit_textbox)

        self.positive_prompt_static_textbox = QTextEdit(self)
        self.positive_prompt_static_textbox.setMinimumHeight(50)
        self.positive_prompt_static_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_stack.addWidget(self.positive_prompt_static_textbox)

        self.positive_compiled_preview = QTextEdit(self)
        self.positive_compiled_preview.setReadOnly(True)
        self.positive_compiled_preview.setMinimumHeight(50)
        self.positive_compiled_preview.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.positive_compiled_preview.setPlaceholderText("No compiled character positive prompt.")
        self.positive_stack.addWidget(self.positive_compiled_preview)

        self.positive_prompt_button.clicked.connect(lambda: self.set_positive_mode(0, 'Positive Prompt', self.positive_prompt_textbox))
        self.positive_character_button.clicked.connect(lambda: self.set_positive_mode(1, 'Character Positive Prompt', self.positive_prompt_character_textbox))
        self.positive_global_button.clicked.connect(lambda: self.set_positive_mode(2, 'Global Positive Prompt', self.positive_prompt_global_textbox))
        self.positive_prompt_outfit_button.clicked.connect(lambda: self.set_positive_mode(3, 'Outfit Positive Prompt', self.positive_prompt_outfit_textbox))
        self.positive_static_button.clicked.connect(lambda: self.set_positive_mode(4, 'Static Positive Prompt', self.positive_prompt_static_textbox))

        self.positive_current_textbox = self.positive_prompt_textbox


        self.negative_prompt_title_bar = QFrame(self)
        self.grid.addWidget(self.negative_prompt_title_bar, 2, 0, 1, 3)
        self.negative_prompt_title_bar.setObjectName("negative_prompt_title_bar")
        self.negative_prompt_title_bar_grid = QGridLayout(self.negative_prompt_title_bar)
        self.negative_prompt_title_bar_grid.setContentsMargins(0,0,0,0) 
        self.negative_prompt_title_bar_grid.setSpacing(0)
        self.negative_prompt_title_bar_grid.setAlignment(Qt.AlignTop)
        self.negative_prompt_title_bar_grid.setColumnStretch(0, 0)
        self.negative_prompt_title_bar_grid.setColumnStretch(1, 1)  
        self.negative_prompt_title_bar_grid.setColumnStretch(2, 0)  

        self.negative_left_button_frame = QFrame(self)
        self.negative_left_button_frame.setObjectName("negative_left_button_frame")
        self.negative_prompt_title_bar_grid.addWidget(self.negative_left_button_frame, 0, 0)
        self.negative_left_button_frame_grid = QGridLayout(self.negative_left_button_frame)
        self.negative_left_button_frame_grid.setContentsMargins(0,0,0,0) 
        self.negative_left_button_frame_grid.setSpacing(0)
        self.negative_left_button_frame_grid.setAlignment(Qt.AlignTop)

        self.negative_button_group = QButtonGroup(self)
        self.negative_button_group.setExclusive(True)

        self.negative_prompt_button = QPushButton("P")
        self.negative_prompt_button.setObjectName("negative_prompt_button")
        self.negative_prompt_button.setCheckable(True) 
        self.negative_prompt_button.setChecked(True)
        self.negative_button_group.addButton(self.negative_prompt_button)
        self.negative_left_button_frame_grid.addWidget(self.negative_prompt_button, 0, 0)
        self.negative_prompt_button.setFixedSize(30, 30)
        self.negative_prompt_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        self.negative_character_button = QPushButton("C")
        self.negative_character_button.setObjectName("negative_character_button")
        self.negative_character_button.setCheckable(True)
        self.negative_character_button.setChecked(False)
        self.negative_button_group.addButton(self.negative_character_button)
        self.negative_left_button_frame_grid.addWidget(self.negative_character_button, 0, 1)
        self.negative_character_button.setFixedSize(30, 30)
        self.negative_character_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)  

        self.negative_static_button = QPushButton("S")
        self.negative_static_button.setObjectName("negative_static_button")
        self.negative_static_button.setCheckable(True)
        self.negative_static_button.setChecked(False)
        self.negative_button_group.addButton(self.negative_static_button)
        self.negative_left_button_frame_grid.addWidget(self.negative_static_button, 0, 2)
        self.negative_static_button.setFixedSize(30, 30)
        self.negative_static_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.negative_static_button.setToolTip("Static negative prompt; remains attached to this slot during swaps.")
         
        self.negative_prompt_label = QPushButton('Negative Prompt', self)
        self.negative_prompt_label.setObjectName("negative_prompt_label")
        self.negative_prompt_label.setFixedHeight(30)
        self.negative_prompt_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.negative_prompt_label.setCheckable(True)
        self.negative_prompt_label.setToolTip("Negative Prompt — click to preview the compiled character prompt.")
        self.negative_prompt_label.clicked.connect(
            lambda checked: self.negative_preview_requested.emit(checked)
        )
        self.negative_prompt_title_bar_grid.addWidget(self.negative_prompt_label, 0, 1)

        self.negative_right_button_frame = QFrame(self)
        self.negative_right_button_frame.setObjectName("negative_right_button_frame")
        self.negative_prompt_title_bar_grid.addWidget(self.negative_right_button_frame, 0, 2)
        self.negative_right_button_frame_grid = QGridLayout(self.negative_right_button_frame)
        self.negative_right_button_frame_grid.setContentsMargins(0,0,0,0) 
        self.negative_right_button_frame_grid.setSpacing(0)
        self.negative_right_button_frame_grid.setAlignment(Qt.AlignTop)

        self.negative_prompt_outfit_button = QPushButton("O")
        self.negative_prompt_outfit_button.setObjectName("negative_prompt_outfit_button")
        self.negative_prompt_outfit_button.setCheckable(True) 
        self.negative_prompt_outfit_button.setChecked(True)
        self.negative_button_group.addButton(self.negative_prompt_outfit_button)
        self.negative_right_button_frame_grid.addWidget(self.negative_prompt_outfit_button, 0, 0)
        self.negative_prompt_outfit_button.setFixedSize(30, 30)
        self.negative_prompt_outfit_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        self.negative_global_button = QPushButton("G")
        self.negative_global_button.setObjectName("negative_global_button")
        self.negative_global_button.setCheckable(True)
        self.negative_global_button.setChecked(False)
        self.negative_button_group.addButton(self.negative_global_button)
        self.negative_right_button_frame_grid.addWidget(self.negative_global_button, 0, 1)
        self.negative_global_button.setFixedSize(30, 30)
        self.negative_global_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.negative_global_button.setToolTip("Character tags added to the global negative prompt.")
        self.negative_prompt_delete_button = QPushButton(self)
        self.negative_prompt_delete_button.setObjectName("negative_prompt_delete_button")
        self.negative_prompt_delete_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.negative_prompt_delete_button.setToolTip("Clear the selected negative prompt.")
        self.negative_prompt_delete_button.setAccessibleName("Clear negative prompt")
        self.negative_prompt_delete_button.pressed.connect(lambda: self.negative_current_textbox.clear())
        self.negative_prompt_delete_button.setFixedSize(30, 30)
        self.negative_prompt_delete_button.setMinimumHeight(30)
        self.negative_right_button_frame_grid.addWidget(self.negative_prompt_delete_button, 0, 2,)

        self.negative_stack = QStackedWidget(self)
        self.grid.addWidget(self.negative_stack, 3, 0, 1, 3)

        self.negative_prompt_textbox = QTextEdit(self)
        self.negative_prompt_textbox.setMinimumHeight(50)
        self.negative_prompt_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_stack.addWidget(self.negative_prompt_textbox)

        self.negative_prompt_character_textbox = QTextEdit(self)
        self.negative_prompt_character_textbox.setMinimumHeight(50)
        self.negative_prompt_character_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_stack.addWidget(self.negative_prompt_character_textbox)

        self.negative_prompt_global_textbox = QTextEdit(self)
        self.negative_prompt_global_textbox.setMinimumHeight(50)
        self.negative_prompt_global_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_stack.addWidget(self.negative_prompt_global_textbox)

        self.negative_prompt_outfit_textbox = QTextEdit(self)
        self.negative_prompt_outfit_textbox.setMinimumHeight(50)
        self.negative_prompt_outfit_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_stack.addWidget(self.negative_prompt_outfit_textbox)  

        self.negative_prompt_static_textbox = QTextEdit(self)
        self.negative_prompt_static_textbox.setMinimumHeight(50)
        self.negative_prompt_static_textbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_stack.addWidget(self.negative_prompt_static_textbox)

        self.negative_compiled_preview = QTextEdit(self)
        self.negative_compiled_preview.setReadOnly(True)
        self.negative_compiled_preview.setMinimumHeight(50)
        self.negative_compiled_preview.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Ignored)
        self.negative_compiled_preview.setPlaceholderText("No compiled character negative prompt.")
        self.negative_stack.addWidget(self.negative_compiled_preview)

        self.negative_prompt_button.clicked.connect(lambda: self.set_negative_mode(0, 'Negative Prompt', self.negative_prompt_textbox))
        self.negative_character_button.clicked.connect(lambda: self.set_negative_mode(1, 'Character Negative Prompt', self.negative_prompt_character_textbox))
        self.negative_global_button.clicked.connect(lambda: self.set_negative_mode(2, 'Global Negative Prompt', self.negative_prompt_global_textbox))
        self.negative_prompt_outfit_button.clicked.connect(lambda: self.set_negative_mode(3, 'Outfit Negative Prompt', self.negative_prompt_outfit_textbox))
        self.negative_static_button.clicked.connect(lambda: self.set_negative_mode(4, 'Static Negative Prompt', self.negative_prompt_static_textbox))

        self.negative_current_textbox = self.negative_prompt_textbox
        self.negative_prompt_button.setChecked(True)
        self.positive_prompt_button.setChecked(True)

        self._prompt_content_pairs = (
            (self.positive_prompt_button, self.positive_prompt_textbox),
            (self.positive_character_button, self.positive_prompt_character_textbox),
            (self.positive_global_button, self.positive_prompt_global_textbox),
            (self.positive_prompt_outfit_button, self.positive_prompt_outfit_textbox),
            (self.positive_static_button, self.positive_prompt_static_textbox),
            (self.negative_prompt_button, self.negative_prompt_textbox),
            (self.negative_character_button, self.negative_prompt_character_textbox),
            (self.negative_global_button, self.negative_prompt_global_textbox),
            (self.negative_prompt_outfit_button, self.negative_prompt_outfit_textbox),
            (self.negative_static_button, self.negative_prompt_static_textbox),
        )
        for button, textbox in self._prompt_content_pairs:
            textbox.textChanged.connect(
                lambda button=button, textbox=textbox: self._update_prompt_content_button(button, textbox)
            )
            self._update_prompt_content_button(button, textbox)

    @staticmethod
    def _update_prompt_content_button(button, textbox):
        has_content = bool(textbox.toPlainText().strip())
        if button.property("has_prompt_content") == has_content:
            return

        button.setProperty("has_prompt_content", has_content)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    
    def set_negative_mode(self, index, label, textbox):
        self.negative_prompt_label.setChecked(False)
        self.negative_stack.setCurrentIndex(index)
        self.negative_prompt_label.setText(label)
        self.negative_prompt_label.setToolTip(
            f"{label} — click to preview the compiled character prompt."
        )
        self.negative_current_textbox = textbox
        self.negative_prompt_delete_button.setEnabled(True)


    def set_positive_mode(self, index, label, textbox):
        self.positive_prompt_label.setChecked(False)
        self.positive_stack.setCurrentIndex(index)
        self.positive_prompt_label.setText(label)
        self.positive_prompt_label.setToolTip(
            f"{label} — click to preview the compiled character prompt."
        )
        self.positive_current_textbox = textbox
        self.positive_prompt_delete_button.setEnabled(True)

    def show_positive_preview(self, prompt):
        self.positive_compiled_preview.setPlainText(prompt)
        self.positive_stack.setCurrentWidget(self.positive_compiled_preview)
        self.positive_prompt_delete_button.setEnabled(False)

    def show_negative_preview(self, prompt):
        self.negative_compiled_preview.setPlainText(prompt)
        self.negative_stack.setCurrentWidget(self.negative_compiled_preview)
        self.negative_prompt_delete_button.setEnabled(False)

    def hide_positive_preview(self):
        self.positive_stack.setCurrentWidget(self.positive_current_textbox)
        self.positive_prompt_delete_button.setEnabled(True)

    def hide_negative_preview(self):
        self.negative_stack.setCurrentWidget(self.negative_current_textbox)
        self.negative_prompt_delete_button.setEnabled(True)