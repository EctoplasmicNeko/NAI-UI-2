from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QToolButton, QVBoxLayout, QSizePolicy


class FullscreenImageWindow(QDialog):
    image_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Viewer")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet("background: #111;")

        self.image_button = QToolButton(self)
        self.image_button.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        self.image_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.image_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image_button.setText("No image")
        self.image_button.setStyleSheet(
            "QToolButton {"
            "background: transparent;"
            "border: 1px solid transparent;"
            "}"
            "QToolButton:pressed {"
            "background: rgba(255, 255, 255, 0.28);"
            "border: 1px solid rgba(255, 255, 255, 0.65);"
            "}"
        )
        self.image_button.clicked.connect(self.image_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_button)
        self._source_pixmap = QPixmap()

    def set_image(self, image_path):
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return
        self._source_pixmap = pixmap
        self.image_button.setText("")
        self._refresh_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_image()

    def _refresh_image(self):
        if self._source_pixmap.isNull():
            return
        scaled_pixmap = self._source_pixmap.scaled(
            self.image_button.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_button.setIcon(QIcon(scaled_pixmap))
        self.image_button.setIconSize(scaled_pixmap.size())

    def show_image(self, image_path):
        if image_path is not None:
            self.set_image(image_path)
        if not self.isVisible():
            self.resize(900, 700)
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
