import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import QLabel, QToolButton


class ImageCuratorEntry(QToolButton):
    selected = Signal(object)

    PREVIEW_MAX_SIZE = 440

    def __init__(self, parent, image_path, status=None):
        super().__init__(parent)
        self.image_path = Path(image_path)
        self.setCheckable(True)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setText(self.image_path.name)
        self.setToolTip(str(self.image_path))
        self.setFixedSize(132, 154)
        self.setIconSize(QSize(116, 116))
        self.set_status_outline(status)

        self.clicked.connect(lambda: self.selected.emit(self.image_path))

        # The preview popup is a native top-level window (Qt.ToolTip), which is
        # expensive to create. Galleries can render dozens of entries per page,
        # so both the popup widget and its pixmap are created lazily on first
        # hover rather than up front for every entry.
        self.preview_popup = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.show_in_explorer()
        super().mouseDoubleClickEvent(event)

    def show_in_explorer(self):
        """Open Windows Explorer with this image selected."""
        subprocess.Popen(["explorer", "/select,", os.path.normpath(str(self.image_path))])

    def set_thumbnail(self, image):
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            self.setIcon(QIcon(pixmap))

    def _ensure_preview_loaded(self):
        if self.preview_popup is not None:
            return

        image_reader = QImageReader(str(self.image_path))
        image_reader.setAutoTransform(True)
        source_size = image_reader.size()
        if source_size.isValid() and (
            source_size.width() > self.PREVIEW_MAX_SIZE or source_size.height() > self.PREVIEW_MAX_SIZE
        ):
            image_reader.setScaledSize(
                source_size.scaled(self.PREVIEW_MAX_SIZE, self.PREVIEW_MAX_SIZE, Qt.KeepAspectRatio)
            )

        image = image_reader.read()
        if image.isNull():
            return

        self.preview_popup = QLabel(self, Qt.ToolTip | Qt.FramelessWindowHint)
        self.preview_popup.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap.fromImage(image)
        self.preview_popup.setPixmap(pixmap)
        self.preview_popup.resize(pixmap.size())

    def enterEvent(self, event):
        super().enterEvent(event)
        self._ensure_preview_loaded()

        if self.preview_popup is None:
            return

        popup_size = self.preview_popup.size()
        top_left = self.mapToGlobal(QPoint(0, 0))
        top_right = self.mapToGlobal(QPoint(self.width(), 0))

        screen = self.screen()
        screen_geometry = screen.availableGeometry() if screen is not None else None

        # Prefer showing to the right of the thumbnail; fall back to the left
        # if there isn't enough room (entries can sit in either grid column).
        popup_x = top_right.x() + 8
        if screen_geometry is not None and popup_x + popup_size.width() > screen_geometry.right():
            popup_x = top_left.x() - popup_size.width() - 8

        popup_y = top_left.y()
        if screen_geometry is not None:
            popup_y = max(screen_geometry.top(), min(popup_y, screen_geometry.bottom() - popup_size.height()))

        self.preview_popup.move(popup_x, popup_y)
        self.preview_popup.show()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.preview_popup is not None:
            self.preview_popup.hide()

    def set_status_outline(self, status):
        normalized_status = str(status or "").strip().lower()
        if normalized_status == "keep":
            self.setStyleSheet("border: 3px solid #4CAF50;")
        elif normalized_status == "trash":
            self.setStyleSheet("border: 3px solid #E57373;")
        else:
            self.setStyleSheet("")