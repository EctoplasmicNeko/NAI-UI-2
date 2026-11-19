from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QPixmap


class ArtistEntry(QFrame):

    def __init__(self, parent, file_path, strength=1.0):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        image_size = 160
        outer_margin = 10

        self.setFixedHeight(image_size + outer_margin * 2)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Plain)

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.image_label.setFixedSize(image_size, image_size)
        pixmap = QPixmap(str(self.file_path))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(image_size, image_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(pixmap)
        self.image_label.installEventFilter(self)
        self.grid.addWidget(self.image_label, 1, 0, 3, 1, Qt.AlignLeft | Qt.AlignVCenter)

        self.preview_popup = QLabel(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.preview_popup.setAttribute(Qt.WA_DeleteOnClose, False)
        self.preview_popup.setAlignment(Qt.AlignCenter)
        popup_pixmap = QPixmap(str(self.file_path))
        if not popup_pixmap.isNull():
            popup_pixmap = popup_pixmap.scaled(440, 440, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_popup.setPixmap(popup_pixmap)
            self.preview_popup.resize(popup_pixmap.size())

        self.controls_frame = QWidget(self)
        self.controls_frame.setAttribute(Qt.WA_TranslucentBackground, True)
        self.controls_frame.setAutoFillBackground(False)
        self.controls_layout = QVBoxLayout(self.controls_frame)
        self.controls_layout.setContentsMargins(12, 0, 12, 0)
        self.controls_layout.setSpacing(10)
        self.controls_layout.addStretch(1)

        self.name_label = QLabel(self.file_path.stem, self.controls_frame)
        self.name_label.setToolTip(str(self.file_path))
        self.name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        name_font = self.name_label.font()
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet("background: transparent; border: none;")
        self.controls_layout.addWidget(self.name_label, 0, Qt.AlignLeft)

        self.use_artist_checkbox = QCheckBox("Use Artist", self.controls_frame)
        self.use_artist_checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.controls_layout.addWidget(self.use_artist_checkbox)

        self.strength_spinner = QDoubleSpinBox(self.controls_frame)
        self.strength_spinner.setDecimals(2)
        self.strength_spinner.setSingleStep(0.05)
        self.strength_spinner.setRange(0.0, 10.0)
        self.strength_spinner.setValue(strength)
        self.strength_spinner.setPrefix("Strength: ")
        self.strength_spinner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.controls_layout.addWidget(self.strength_spinner)
        self.controls_layout.addStretch(1)

        self.grid.addWidget(self.controls_frame, 1, 1, 3, 1)
        self.grid.setRowStretch(0, 1)
        self.grid.setRowStretch(4, 1)
        self.grid.setContentsMargins(outer_margin, outer_margin, outer_margin, outer_margin)
        self.grid.setColumnStretch(1, 1)

    def eventFilter(self, watched, event):
        if watched is self.image_label:
            if event.type() == QEvent.Enter and not self.preview_popup.pixmap().isNull():
                popup_position = self.image_label.mapToGlobal(QPoint(-self.preview_popup.width() - 8, 0))
                self.preview_popup.move(popup_position)
                self.preview_popup.show()
            elif event.type() == QEvent.Leave:
                self.preview_popup.hide()
        return super().eventFilter(watched, event)