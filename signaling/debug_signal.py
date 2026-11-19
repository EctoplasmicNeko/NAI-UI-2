from datetime import datetime

from PySide6.QtCore import QObject, Signal


class DebugSignalBus(QObject):
    message_signal = Signal(str, str, str)
    clear_signal = Signal()
    generation_start_signal = Signal()

    def emit_message(self, level, source, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.message_signal.emit(timestamp, str(level).upper(), f"{source}: {message}")

    def clear(self):
        self.clear_signal.emit()

    def generation_started(self):
        self.generation_start_signal.emit()


debug_signal = DebugSignalBus()


def debug_info(source, message):
    debug_signal.emit_message("info", source, message)


def debug_warning(source, message):
    debug_signal.emit_message("warning", source, message)


def debug_error(source, message):
    debug_signal.emit_message("error", source, message)


def debug_success(source, message):
    debug_signal.emit_message("success", source, message)


def clear_debug_panel():
    debug_signal.clear()


def debug_generation_started():
    debug_signal.generation_started()