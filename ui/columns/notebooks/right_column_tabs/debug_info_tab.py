from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
)

from signaling.debug_signal import debug_signal
from process.account_usage import AccountUsage


MAX_LOG_LINES = 4000
MAX_MESSAGE_CHARS = 4000
# Each message uses two blocks (text + blank spacer); reserve room for the overflow notice.
MAX_PENDING_MESSAGES = MAX_LOG_LINES // 2 - 1
TRICKLE_INTERVAL_MS = 25
# Large bursts drain over roughly this many ticks so the panel never lags far behind.
TRICKLE_CATCHUP_TICKS = 20
LEVEL_COLORS = {
    "INFO": "#7db7ff",
    "WARNING": "#f0c36a",
    "ERROR": "#ff7373",
    "SUCCESS": "#74d680",
}
DEFAULT_LEVEL_COLOR = "#dddddd"


def _configure_stable_text_view(widget):
    # Fixed scrollbar policies plus width wrapping stop scrollbar show/hide layout loops.
    widget.setReadOnly(True)
    widget.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    widget.setUndoRedoEnabled(False)


class DebugInfoTab(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("debug_info_tab")
        self._pending_messages = []
        self._dropped_message_count = 0
        self._next_operation_text = None
        self._account_usage_snapshot: AccountUsage | None = None
        self._formats = {}
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(TRICKLE_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._trickle_pending_messages)
        self.build_debug_info_tab()
        debug_signal.message_signal.connect(self.append_message)
        debug_signal.clear_signal.connect(self.clear_messages)
        debug_signal.generation_start_signal.connect(self.on_generation_started)

    def build_debug_info_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.header_frame = QFrame(self)
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(6, 4, 6, 4)
        self.header_layout.setSpacing(6)

        self.title_label = QLabel("Info / Debug", self.header_frame)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header_layout.addWidget(self.title_label)

        self.auto_clear_checkbox = QCheckBox("Auto-clear on generation start", self.header_frame)
        self.auto_clear_checkbox.setChecked(True)
        self.header_layout.addWidget(self.auto_clear_checkbox)

        self.clear_button = QPushButton("Clear", self.header_frame)
        self.clear_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.clear_button.clicked.connect(self.clear_messages)
        self.header_layout.addWidget(self.clear_button)

        self.grid.addWidget(self.header_frame, 0, 0)

        self.message_textbox = QPlainTextEdit(self)
        self.message_textbox.setObjectName("debug_log")
        _configure_stable_text_view(self.message_textbox)
        self.message_textbox.setMaximumBlockCount(MAX_LOG_LINES)
        self.message_textbox.setPlaceholderText("Debug and workflow messages will appear here.")
        self.grid.setRowStretch(1, 1)
        self.grid.addWidget(self.message_textbox, 1, 0)

        self.next_operation_header_label = QLabel("Upcoming Triggers", self)
        self.next_operation_header_label.setObjectName("next_operation_header_label")
        self.grid.addWidget(self.next_operation_header_label, 2, 0)

        self.next_operation_label = QPlainTextEdit(self)
        self.next_operation_label.setObjectName("next_operation_label")
        _configure_stable_text_view(self.next_operation_label)
        self.next_operation_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.next_operation_label.setFixedHeight(90)
        self.next_operation_label.setPlaceholderText("No active timers.")
        self.grid.addWidget(self.next_operation_label, 3, 0)

        self.account_usage_label = QLabel(self)
        self.account_usage_label.setObjectName("account_usage_readout")
        self.account_usage_label.setTextFormat(Qt.PlainText)
        self.account_usage_label.setWordWrap(True)
        self.account_usage_label.setStyleSheet("color: #FFE066; padding: 6px;")
        self.grid.addWidget(self.account_usage_label, 4, 0)
        self.update_account_usage("no_key")

    def update_account_usage(self, status: str, data: object = None) -> None:
        if status in {"no_key", "key_changed"}:
            self._account_usage_snapshot = None
        elif status == "ready" and isinstance(data, AccountUsage):
            self._account_usage_snapshot = data
        snapshot = self._account_usage_snapshot
        if snapshot is None:
            description = {
                "no_key": "Unavailable (no API key)",
                "key_changed": "Loading...",
                "loading": "Loading...",
                "error": "Unavailable (refresh failed)",
            }.get(status, "Unavailable")
            text = f"Remaining Anlas: {description}\nRemaining V5: {description}"
        else:
            total_percent = snapshot.total_percent
            v5 = f"{total_percent:g}%" if total_percent is not None else "Unavailable"
            text = f"Remaining Anlas: {snapshot.total_anlas:,}\nRemaining V5: {v5}"
            if status != "ready":
                text += "\nLast known values (refresh failed)" if status == "error" else "\nLast known values (refreshing)"
        self.account_usage_label.setText(text)
        tooltip = str(data) if status == "error" else ""
        if snapshot is not None and snapshot.total_percent is None:
            tooltip = "\n".join(part for part in (snapshot.unavailable_reason, tooltip) if part)
        self.account_usage_label.setToolTip(tooltip)

    def append_message(self, timestamp, level, message):
        level = str(level)
        text = f"[{timestamp}] [{level}] {message}"
        if len(text) > MAX_MESSAGE_CHARS:
            omitted = len(text) - MAX_MESSAGE_CHARS
            text = f"{text[:MAX_MESSAGE_CHARS]} ... [{omitted} characters truncated]"
        self._pending_messages.append((level, text))
        if len(self._pending_messages) > MAX_PENDING_MESSAGES:
            overflow = len(self._pending_messages) - MAX_PENDING_MESSAGES
            del self._pending_messages[:overflow]
            self._dropped_message_count += overflow
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _format_for_level(self, level):
        char_format = self._formats.get(level)
        if char_format is None:
            char_format = QTextCharFormat()
            char_format.setForeground(QColor(LEVEL_COLORS.get(level, DEFAULT_LEVEL_COLOR)))
            self._formats[level] = char_format
        return char_format

    def _trickle_pending_messages(self):
        backlog = len(self._pending_messages)
        count = max(1, -(-backlog // TRICKLE_CATCHUP_TICKS))
        self.flush_pending_messages(limit=count)
        if not self._pending_messages:
            self._flush_timer.stop()

    def flush_pending_messages(self, limit=None):
        if not self._pending_messages and not self._dropped_message_count:
            return
        if limit is None:
            limit = len(self._pending_messages)
        messages = self._pending_messages[:limit]
        del self._pending_messages[:limit]
        if self._dropped_message_count:
            messages.insert(0, (
                "WARNING",
                f"[Debug panel] {self._dropped_message_count} older messages skipped to keep the UI responsive.",
            ))
            self._dropped_message_count = 0

        scrollbar = self.message_textbox.verticalScrollBar()
        follow_tail = scrollbar.value() >= scrollbar.maximum() - 4
        document = self.message_textbox.document()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.End)
        cursor.beginEditBlock()
        needs_separator = not document.isEmpty()
        for level, text in messages:
            if needs_separator:
                cursor.insertBlock()
                cursor.insertBlock()
            cursor.insertText(text, self._format_for_level(level))
            needs_separator = True
        cursor.endEditBlock()
        if follow_tail:
            scrollbar.setValue(scrollbar.maximum())

    def on_generation_started(self):
        if self.auto_clear_checkbox.isChecked():
            self.clear_messages()

    def clear_messages(self):
        self._flush_timer.stop()
        self._pending_messages = []
        self._dropped_message_count = 0
        self.message_textbox.clear()

    def update_next_operation(self, lines):
        text = "\n".join(lines) if lines else "No active timers."
        if text == self._next_operation_text:
            return
        self._next_operation_text = text
        self.next_operation_label.setPlainText(text)

    def export_state(self):
        return {}