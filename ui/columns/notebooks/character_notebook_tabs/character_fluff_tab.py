import html
from PySide6.QtWidgets import QGridLayout, QFrame, QComboBox, QLabel, QSizePolicy, QVBoxLayout
from PySide6.QtGui import QPixmap, QFont, QFontMetrics, QTextDocument
from PySide6.QtCore import Qt
from signaling.minimal_character_tab import minimal_character_tab
from data.datahub import get_all_characters


class AutoResizingLabel(QLabel):
    def __init__(self, text="", parent=None, prefix=None, base_point_size=None, min_point_size=6):
        super().__init__(text, parent)
        self._min_point_size = min_point_size
        self._full_text = text
        self._prefix = prefix
        self.setTextFormat(Qt.RichText)
        pt = self.font().pointSize()
        self._base_point_size = base_point_size if base_point_size is not None else (pt if pt > 0 else 10)

    def setText(self, text: str):
        self._full_text = str(text) if text is not None else ""
        self.adjust_font_size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_font_size()

    def showEvent(self, event):
        super().showEvent(event)
        self.adjust_font_size()

    def adjust_font_size(self):
        if not self._full_text:
            super().setText("")
            return

        avail_width = self.contentsRect().width()
        if avail_width <= 10:
            return

        base_font = QFont(self.font())
        base_font.setPointSize(self._base_point_size)

        prefix_str = ""
        value_str = self._full_text

        if self._prefix and self._full_text.startswith(self._prefix):
            prefix_str = self._prefix
            value_str = self._full_text[len(self._prefix):]
        elif self._prefix is None and ": " in self._full_text and not ("<" in self._full_text and ">" in self._full_text):
            parts = self._full_text.split(": ", 1)
            prefix_str = parts[0] + ": "
            value_str = parts[1]

        if prefix_str:
            escaped_prefix = html.escape(prefix_str)
            escaped_value = html.escape(value_str)
            best_size = self._base_point_size

            for size in range(self._base_point_size, self._min_point_size - 1, -1):
                doc = QTextDocument()
                doc.setDefaultFont(base_font)
                html_content = f'{escaped_prefix}<span style="font-size:{size}pt;">{escaped_value}</span>'
                doc.setHtml(html_content)
                calc_width = doc.idealWidth()
                if calc_width <= avail_width:
                    best_size = size
                    break
                best_size = size

            self.setFont(base_font)
            super().setText(f'{escaped_prefix}<span style="font-size:{best_size}pt;">{escaped_value}</span>')
        else:
            font = QFont(self.font())
            best_size = self._base_point_size

            is_html = "<" in self._full_text and ">" in self._full_text

            for size in range(self._base_point_size, self._min_point_size - 1, -1):
                font.setPointSize(size)
                if is_html:
                    doc = QTextDocument()
                    doc.setDefaultFont(font)
                    doc.setHtml(self._full_text)
                    calc_width = doc.idealWidth()
                else:
                    fm = QFontMetrics(font)
                    calc_width = fm.horizontalAdvance(self._full_text) if hasattr(fm, 'horizontalAdvance') else fm.width(self._full_text)

                if calc_width <= avail_width:
                    best_size = size
                    break
                best_size = size

            font.setPointSize(best_size)
            self.setFont(font)
            super().setText(self._full_text)


class CharacterFluffTab(QFrame):
    def __init__(self, parent, image_cache):
        super().__init__(parent)
        self.image_cache = image_cache
        self.build_character_fluff_tab()
        minimal_character_tab.on_signal.connect(self.minimal_character_fluff_tab)

    def build_character_fluff_tab(self):

        self.characters = get_all_characters()                
        self.character_list = [
            f'{character["nameID"]}'
            for character in self.characters
            if not character.get("exclude_from_character_list", False)
        ]

        # ---- Base layout ----
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 3)
        self.grid.setSpacing(3)
        self.grid.setColumnStretch(0,1)
        self.grid.setColumnStretch(1,0)
        self.grid.setRowStretch(1,0)



        # ---- Left text block ----
        self.character_select_combobox = QComboBox(self)
        self.character_select_combobox.addItem("None")
        self.character_select_combobox.addItems(self.character_list)
        self.character_select_combobox.setEditable(False)
        self.grid.addWidget(self.character_select_combobox,0, 0)

        self.character_fluff_frame = QFrame(self)
        self.character_fluff_frame_grid = QGridLayout(self.character_fluff_frame)
        self.character_fluff_frame_grid.setContentsMargins(0, 0, 0, 0)
        self.character_fluff_frame_grid.setSpacing(3)
        self.character_fluff_frame_grid.setRowMinimumHeight(0, 25)
        self.character_fluff_frame_grid.setRowMinimumHeight(1, 25)
        self.character_fluff_frame_grid.setRowMinimumHeight(2, 25)
        self.character_fluff_frame_grid.setRowMinimumHeight(3, 25)
        self.character_fluff_frame_grid.setRowMinimumHeight(4, 25)
        self.grid.addWidget(self.character_fluff_frame, 1, 0)    

        self.character_fluff_fullname_label = AutoResizingLabel("", self, prefix="Full Name: ")
        self.character_fluff_fullname_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.character_fluff_fullname_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_fluff_fullname_label.setFixedHeight(25)
        self.character_fluff_frame_grid.addWidget(self.character_fluff_fullname_label, 0, 0, )

        self.character_fluff_species_label = AutoResizingLabel("", self, prefix="Species: ")
        self.character_fluff_species_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.character_fluff_species_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_fluff_species_label.setFixedHeight(25)
        self.character_fluff_frame_grid.addWidget(self.character_fluff_species_label, 1,0 )

        self.character_fluff_subspecies_label = AutoResizingLabel("", self, prefix="Subspecies: ")
        self.character_fluff_subspecies_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.character_fluff_subspecies_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_fluff_subspecies_label.setFixedHeight(25)
        self.character_fluff_frame_grid.addWidget(self.character_fluff_subspecies_label, 2,0 )

        self.character_fluff_age_label = AutoResizingLabel("", self, prefix="Age: ")
        self.character_fluff_age_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.character_fluff_age_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_fluff_age_label.setFixedHeight(25)
        self.character_fluff_frame_grid.addWidget(self.character_fluff_age_label, 3,0 )

        self.character_fluff_gender_label = QLabel(self)
        self.character_fluff_gender_label.setWordWrap(True)
        self.character_fluff_gender_label.setTextFormat(Qt.RichText)
        self.character_fluff_gender_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.character_fluff_gender_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_fluff_gender_label.setFixedHeight(25)
        self.character_fluff_frame_grid.addWidget(self.character_fluff_gender_label, 4,0 )


        self.character_portrait_frame = QFrame(self)
        self.character_portrait_frame.setMinimumSize(170, 170)
        self.character_portrait_frame_grid = QVBoxLayout(self.character_portrait_frame)
        self.character_portrait_frame.setContentsMargins(6, 6, 6, 6)
        self.character_portrait_frame_grid.setSpacing(4)
        self.grid.addWidget(self.character_portrait_frame, 0, 1, 2, 1)

        self.character_fluff_quote_label = QLabel(self)
        self.character_fluff_quote_label.setWordWrap(True)
        self.character_fluff_quote_label.setTextFormat(Qt.RichText)
        self.character_fluff_quote_label.setAlignment(Qt.AlignCenter)
        self.character_fluff_quote_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_fluff_quote_label.setFixedHeight(32)
        self.grid.addWidget(self.character_fluff_quote_label, 2,0, 1, 2 )

        # === portrait label (keep as attribute!) ===
        self.portrait_label = QLabel(self.character_portrait_frame)
        self.portrait_label.setAlignment(Qt.AlignCenter)
        self.portrait_label.setFixedSize(150, 150)
        self.character_portrait_frame_grid.addWidget(self.portrait_label, 0, Qt.AlignCenter)

    def update_portrait(self, path: str):
        """Load and apply a rounded portrait from the given file path."""
        self.pix_path = path
        if self.pix_path == "":
            self.pix_path = self.image_cache['character_portraits']['fluff_placeholder']

        pix = QPixmap(self.pix_path)
        pix = pix.scaled(150, 150, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.portrait_label.setPixmap(pix)

    def minimal_character_fluff_tab(self, enabled: bool):
        if enabled:
            self.character_fluff_frame.show()
            self.character_portrait_frame.show()
            self.character_fluff_quote_label.show()
            self.updateGeometry()
            self.character_fluff_fullname_label.adjust_font_size()
            self.character_fluff_species_label.adjust_font_size()
            self.character_fluff_subspecies_label.adjust_font_size()
            self.character_fluff_age_label.adjust_font_size()
        else:
            self.character_fluff_frame.hide()
            self.character_portrait_frame.hide()
            self.character_fluff_quote_label.hide()
            self.updateGeometry()





