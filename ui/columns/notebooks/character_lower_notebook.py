from PySide6.QtWidgets import QGridLayout, QFrame, QStackedWidget
from data.character_slots import MAX_CHARACTER_SLOTS
from ui.columns.notebooks.character_notebook_tabs.character_lower_master_tab import CharacterLowerMasterTab



class CharacterLowerNotebook(QFrame):

    def __init__(self, parent, image_cache,):
        super().__init__(parent)
        self.setObjectName("character_lower_notebook")
        self.image_cache = image_cache
        self.build_UI()
        
    
    def build_UI(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 1)

        self.button_frame = QFrame(self)
        self.grid.addWidget(self.button_frame, 0, 0)

        self.stack = QStackedWidget(self)
        self.grid.addWidget(self.stack, 1, 0)

        self.character_tabs = []
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            tab = CharacterLowerMasterTab(self, self.image_cache, slot_id)
            self.stack.addWidget(tab)
            self.character_tabs.append(tab)
            setattr(self, f"character_tab_{slot_id}", tab)
        self.stack.setCurrentIndex(0)

