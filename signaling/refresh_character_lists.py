from PySide6.QtCore import QObject, Signal

class RefreshCharacterListsSignal(QObject):
    refresh_lists = Signal()
    reload_character_data = Signal()
    mutators_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

refresh_character_lists_signal = RefreshCharacterListsSignal()