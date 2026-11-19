from PySide6.QtWidgets import QGridLayout, QFrame, QStackedWidget, QHBoxLayout, QPushButton, QButtonGroup, QSizePolicy
from PySide6.QtCore import Qt
from data.character_slots import CHARACTER_SLOTS_PER_ROW, MAX_CHARACTER_SLOTS
from ui.columns.notebooks.character_notebook_tabs.character_middle_master_tab import CharacterMiddleMasterTab



class CharacterMiddleNotebook(QFrame):

    def __init__(self, parent, image_cache,):
        super().__init__(parent)
        self.setObjectName("character_middle_notebook")
        self.image_cache = image_cache
        self.build_UI()
    
    def build_UI(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 0)
        self.grid.setRowStretch(2, 1)

        self.button_frame = QFrame(self)
        self.grid.addWidget(self.button_frame, 0, 0)
        self.button_frame_grid = QHBoxLayout(self.button_frame)
        self.button_frame_grid.setContentsMargins(0, 0, 0, 0)
        self.button_frame_grid.setSpacing(0)
        self.button_frame_grid.setAlignment(Qt.AlignTop)

        self.second_button_frame = QFrame(self)
        self.grid.addWidget(self.second_button_frame, 1, 0)
        self.second_button_frame_grid = QHBoxLayout(self.second_button_frame)
        self.second_button_frame_grid.setContentsMargins(0, 0, 0, 0)
        self.second_button_frame_grid.setSpacing(0)
        self.second_button_frame_grid.setAlignment(Qt.AlignTop)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons = []
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            button_name = f"Character {slot_id}"
            button = QPushButton(button_name, self)
            button.setCheckable(True)
            button.setMinimumWidth(5)
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
            button_layout = (
                self.button_frame_grid
                if slot_id <= CHARACTER_SLOTS_PER_ROW
                else self.second_button_frame_grid
            )
            button_layout.addWidget(button)
            button_layout.setStretch(button_layout.count() - 1, 1)
            self.button_group.addButton(button, slot_id - 1)
            self.buttons.append(button)
            setattr(self, f"button_name_{slot_id}", button_name)
            setattr(self, f"button_{slot_id}", button)

        self.stack = QStackedWidget(self)
        self.grid.addWidget(self.stack, 2, 0)
        self.character_tabs = []
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            tab = CharacterMiddleMasterTab(self, self.image_cache, slot_id)
            button = self.buttons[slot_id - 1]
            tab.fluff_tab.character_select_combobox.currentIndexChanged.connect(
                lambda _index, selected_button=button, selected_tab=tab, selected_slot=slot_id: self.update_tab_for_character(
                    selected_button,
                    selected_tab,
                    str(selected_slot),
                )
            )
            self.stack.addWidget(tab)
            self.character_tabs.append(tab)
            setattr(self, f"character_tab_{slot_id}", tab)

        self.button_group.idToggled.connect(self._on_button_toggled)
        self.button_1.setChecked(True)
        self.set_character_count(0)

    def _on_button_toggled(self, button_id, checked):
        if checked:
            self.stack.setCurrentIndex(button_id)

    def set_character_count(self, count):
        count = max(0, min(MAX_CHARACTER_SLOTS, int(count)))
        self.second_button_frame.setVisible(count > CHARACTER_SLOTS_PER_ROW)
        if count <= CHARACTER_SLOTS_PER_ROW and self.stack.currentIndex() >= CHARACTER_SLOTS_PER_ROW:
            fallback_index = max(0, min(count, CHARACTER_SLOTS_PER_ROW) - 1)
            self.buttons[fallback_index].setChecked(True)
    

    def update_tab_for_character(self, button, cha_tab, button_num):
        name = cha_tab.fluff_tab.character_select_combobox.currentText()
        if name != "None":
            button.setText(name)
        else:
            button.setText(f'Character {button_num}')

