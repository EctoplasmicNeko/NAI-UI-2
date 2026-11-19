import threading

from PySide6.QtCore import QObject, Signal
from data.save import save_config
from process.process_main import run_process
from signaling.debug_signal import debug_error, debug_generation_started, debug_info, debug_success


class GenerateWorker(QObject):
    finished = Signal()
    result = Signal(str, dict)   # image_path, state
    error = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        try:
            debug_generation_started()
            debug_info("GenerateWorker", "Saving UI state")
            save_config(self.state)
            debug_info("GenerateWorker", "Starting process")
            image_path = run_process(self.state, cancel_event=self.cancel_event)
            self.result.emit(image_path or '', self.state)
            if image_path:
                debug_success("GenerateWorker", f"Process finished: {image_path}")
            else:
                debug_error("GenerateWorker", "Process ended without an output image")
        except Exception as exc:
            debug_error("GenerateWorker", str(exc))
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
