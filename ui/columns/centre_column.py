from pathlib import Path

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QToolButton, QStyle, QToolTip
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QSize
from data.character_slots import MAX_CHARACTER_SLOTS
from data.paths import IMAGES_DIR
from process.CompletionSignaler import completion_signaler
from windows.fullscreen_image import FullscreenImageWindow

class CentreColumn(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("centre_column")
        self.current_image_path = None
        self._loaded_image_size = QSize()
        self._overlay_image_size = QSize()
        self._coordinate_tokens = {}
        self._coordinate_positions = {}
        self._coordinate_marker_visibility = {}
        self._curation_mode = False
        self._curation_wheel_callback = None
        self._upcoming_image_frame = None
        self._fullscreen_window = None
        completion_signaler.window_lock_signal.connect(self._set_generation_locked)
        completion_signaler.complete_signal.connect(self._unlock_generation)
        self.build_centre_column()


    def build_centre_column(self):

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.grid.setColumnStretch(0, 1)
        self.grid.setRowStretch(0, 1)
        self.viewport_button = QToolButton(self)
        self.viewport_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.viewport_button.setCursor(Qt.PointingHandCursor)
        self.viewport_button.setToolTip("Generate image")
        self.viewport_button.setAutoRaise(True)
        self.viewport_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.viewport_button.setLayoutDirection(Qt.LeftToRight)
        self.viewport_button.installEventFilter(self)

        self.grid.addWidget(self.viewport_button, 0, 0)

        self.fullscreen_button = QToolButton(self)
        self.fullscreen_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton))
        self.fullscreen_button.setToolTip("View image fullscreen")
        self.fullscreen_button.setAutoRaise(True)
        self.fullscreen_button.clicked.connect(self.show_fullscreen_image)
        self.fullscreen_button.raise_()

        self._upcoming_image_frame = QFrame(self)
        self._upcoming_image_frame.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._upcoming_image_frame.setStyleSheet(
            "background: rgba(70, 150, 220, 35);"
            "border: 2px solid rgba(70, 150, 220, 180);"
        )
        self._upcoming_image_frame.hide()

        for character_id in range(1, MAX_CHARACTER_SLOTS + 1):
            token_path = self._find_coordinate_token(character_id)
            if token_path is None:
                continue
            token_pixmap = QPixmap(str(token_path))
            if token_pixmap.isNull():
                continue
            token_label = QLabel(self)
            token_label.setFixedSize(32, 32)
            token_label.setAlignment(Qt.AlignCenter)
            token_label.setAutoFillBackground(False)
            token_label.setStyleSheet("background: transparent; border: none;")
            token_label.setPixmap(token_pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            token_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            token_label.hide()
            self._coordinate_tokens[character_id] = token_label

    def _set_generation_locked(self, locked):
        QToolTip.hideText()
        self.viewport_button.blockSignals(locked)
        self.viewport_button.setToolTip("" if locked else "Generate image")

    def _unlock_generation(self):
        self._set_generation_locked(False)

    @staticmethod
    def _find_coordinate_token(character_id):
        token_dir = IMAGES_DIR / "coordinate_tokens"
        for token_path in sorted(token_dir.glob(f"token_{character_id}.*")):
            if token_path.is_file():
                return token_path
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 8
        self.fullscreen_button.adjustSize()
        self.fullscreen_button.move(
            self.width() - self.fullscreen_button.width() - margin,
            margin,
        )
        self._update_coordinate_overlay()

    def set_coordinate_overlay(self, positions, image_width, image_height):
        self._coordinate_positions = positions or {}
        self._overlay_image_size = QSize(int(image_width or 0), int(image_height or 0))
        self._update_coordinate_overlay()

    def set_coordinate_marker_visible(self, character_id, visible):
        self._coordinate_marker_visibility[character_id] = bool(visible)
        self._update_coordinate_overlay()

    def set_curation_mode(self, active):
        self._curation_mode = bool(active)
        self._update_coordinate_overlay()

    def set_curation_wheel_callback(self, callback):
        self._curation_wheel_callback = callback

    def eventFilter(self, watched, event):
        if watched is self.viewport_button and event.type() == QEvent.Wheel and self._curation_mode:
            wheel_delta = event.angleDelta().y()
            if wheel_delta and self._curation_wheel_callback is not None:
                self._curation_wheel_callback(-1 if wheel_delta > 0 else 1)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _displayed_image_rect(self):
        source_size = self._overlay_image_size

        if (
            not source_size.isValid()
            or source_size.width() <= 0
            or source_size.height() <= 0
        ):
            return QRect()

        available_size = self.viewport_button.size()
        scale = min(
            available_size.width() / source_size.width(),
            available_size.height() / source_size.height(),
            1.0,
        )
        displayed_size = QSize(
            max(1, round(source_size.width() * scale)),
            max(1, round(source_size.height() * scale)),
        )
        button_geometry = self.viewport_button.geometry()
        button_center = button_geometry.topLeft() + QPoint(
            button_geometry.width() // 2,
            button_geometry.height() // 2,
        )
        displayed_center = QPoint(
            displayed_size.width() // 2,
            displayed_size.height() // 2,
        )
        top_left = button_center - displayed_center
        return QRect(top_left, displayed_size)

    def _update_coordinate_overlay(self):
        if self._curation_mode:
            if self._upcoming_image_frame is not None:
                self._upcoming_image_frame.hide()
            for token_label in self._coordinate_tokens.values():
                token_label.hide()
            return

        image_rect = self._displayed_image_rect()
        if not image_rect.isValid():
            if self._upcoming_image_frame is not None:
                self._upcoming_image_frame.hide()
            for token_label in self._coordinate_tokens.values():
                token_label.hide()
            return

        self._upcoming_image_frame.setGeometry(image_rect)
        frame_matches_loaded_image = (
            self._loaded_image_size.isValid()
            and self._loaded_image_size == self._overlay_image_size
        )
        self._upcoming_image_frame.setVisible(not frame_matches_loaded_image)
        self._upcoming_image_frame.raise_()

        for character_id, token_label in self._coordinate_tokens.items():
            if not self._coordinate_marker_visibility.get(character_id, True):
                token_label.hide()
                continue
            position = self._coordinate_positions.get(character_id)
            if position is None:
                token_label.hide()
                continue
            x_value, y_value = position
            center = QPoint(
                image_rect.left() + round(float(x_value) * image_rect.width()),
                image_rect.top() + round(float(y_value) * image_rect.height()),
            )
            token_label.move(center - token_label.rect().center())
            token_label.raise_()
            token_label.show()

    def update_image(self, image_path):
        self.current_image_path = image_path
        pixmap = QPixmap(image_path)

        if pixmap.isNull():
            return False

        self._loaded_image_size = pixmap.size()

        self.viewport_button.updateGeometry()

        label_width = self.viewport_button.width()
        label_height = self.viewport_button.height()

        image_width = pixmap.width()
        image_height = pixmap.height()

        # Only reduce size, never enlarge
        if image_width > label_width or image_height > label_height:
            pixmap = pixmap.scaled(
                label_width,
                label_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

        self.viewport_button.setIcon(QIcon(pixmap))
        self.viewport_button.setIconSize(QSize(pixmap.width(), pixmap.height()))
        self.viewport_button.setAutoRepeat
        self.viewport_button.setAutoRepeatDelay(300)
        self.viewport_button.setAutoRepeatInterval(100)
        if self._fullscreen_window is not None:
            self._fullscreen_window.set_image(image_path)
        self._update_coordinate_overlay()
        return True

    def show_fullscreen_image(self):
        if self._fullscreen_window is None:
            self._fullscreen_window = FullscreenImageWindow()
            self._fullscreen_window.image_clicked.connect(self.viewport_button.click)
        self._fullscreen_window.show_image(self.current_image_path)

        

        
        