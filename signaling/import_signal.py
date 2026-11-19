# signaling/import_signal.py
from PySide6.QtCore import QObject, Signal

class ImportSignalBus(QObject):
    # dict_type, metadata, settings, prompt, seed, characters, restore_quick_weights, disable_associations
    import_signal = Signal(str, dict, bool, bool, bool, bool, bool, bool)
    import_image_signal = Signal(str, int, int)
    import_reference_signal = Signal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.import_signal.connect(self.debug_print)

    def debug_print(self, dict_type: str, metadata: dict,
                    import_prompt: bool, import_characters: bool,
                    import_settings: bool, import_seed: bool,
                    restore_quick_weights: bool, disable_associations: bool):
        pass

# single shared bus
import_signal = ImportSignalBus()
