from PySide6.QtWidgets import QGridLayout, QFrame, QButtonGroup, QSizePolicy, QPushButton, QHBoxLayout, QStackedWidget, QWidget
from PySide6.QtCore import Qt
from ui.columns.notebooks.right_column_tabs.vibes_master_tab import VibeReferenceMasterTab
from ui.columns.notebooks.right_column_tabs.artists_master_tab import ArtistsMasterTab
from ui.columns.notebooks.right_column_tabs.saved_prompts_master_tab import SavedPromptsMasterTab
from ui.columns.notebooks.right_column_tabs.debug_info_tab import DebugInfoTab
from ui.columns.notebooks.right_column_tabs.image_curator_tab import ImageCuratorTab

class RightColumn(QFrame):
    """Right column: same structure, ready for its own logic."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("right_column")
        self.build_right_column()

    def build_right_column(self):
       
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(5, 8, 5, 5)
        self.grid.setSpacing(3)
        self.grid.setRowStretch(0, 0)
        self.grid.setRowStretch(1, 1)
        self.grid.setColumnStretch(0, 1)

        self.button_frame = QFrame(self)
        self.button_frame.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.grid.addWidget(self.button_frame, 0, 0)

        self.button_frame_grid = QHBoxLayout(self.button_frame) 
        self.button_frame_grid.setContentsMargins(0,0,0,0) 
        self.button_frame_grid.setSpacing(0)
        self.button_frame_grid.setAlignment(Qt.AlignTop)
        

        self.button_1 = QPushButton("Info")
        self.button_1.setCheckable(True) 
        self.button_1.setChecked(True)
        self.button_1.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.button_1.setMinimumWidth(5)
        self.button_frame_grid.addWidget(self.button_1)


        self.button_2 = QPushButton("Vibe")
        self.button_2.setCheckable(True) 
        self.button_2.setChecked(False)
        self.button_2.setMinimumWidth(5)
        self.button_2.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.button_frame_grid.addWidget(self.button_2)

        self.button_3 = QPushButton("Artists")
        self.button_3.setCheckable(True) 
        self.button_3.setChecked(False)
        self.button_3.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.button_3.setMinimumWidth(5)
        self.button_frame_grid.addWidget(self.button_3)

        self.button_4 = QPushButton("Prompts")
        self.button_4.setCheckable(True) 
        self.button_4.setChecked(False)
        self.button_4.setMinimumWidth(5)
        self.button_4.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.button_frame_grid.addWidget(self.button_4)

        self.button_5 = QPushButton("Curate")
        self.button_5.setCheckable(True) 
        self.button_5.setChecked(False)
        self.button_5.setMinimumWidth(5)
        self.button_5.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.button_frame_grid.addWidget(self.button_5)

        # Group them
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)          # exactly one can be checked at a time
        self.button_group.addButton(self.button_1, 0)             # optional: assign IDs for easy lookup
        self.button_group.addButton(self.button_2, 1)
        self.button_group.addButton(self.button_3, 2)
        self.button_group.addButton(self.button_4, 3)
        self.button_group.addButton(self.button_5, 4)

        self.main_stack = QStackedWidget(self)
        self.grid.addWidget(self.main_stack, 1, 0)

        self.page0 = DebugInfoTab(self)
        self.page1 = VibeReferenceMasterTab(self)
        self.page2 = ArtistsMasterTab(self)
        self.page3 = SavedPromptsMasterTab(self)
        self.page4 = ImageCuratorTab(
            self,
            self.preview_curated_image,
            self.show_curation_metadata,
            self.curation_values,
            self.window().set_curation_mode,
            self.copy_previous_enabled,
            self.show_curation_image_path,
            self.copy_previous_fields,
        )

        self.main_stack.addWidget(self.page0)
        self.main_stack.addWidget(self.page1)
        self.main_stack.addWidget(self.page2)
        self.main_stack.addWidget(self.page3)
        self.main_stack.addWidget(self.page4)
        
        self.button_group.idToggled.connect(self.on_page_button_toggled) #connect main stack

    def on_page_button_toggled(self, page_index, checked):
        if checked:
            self.main_stack.setCurrentIndex(page_index)
            if page_index == 4:
                self.page4.activate_mode(self.page4.curation_mode_active())
            else:
                self.window().set_curation_mode(False)

    def preview_curated_image(self, image_path):
        main_window = self.window()
        main_window.centre_column_widget.update_image(str(image_path))
        main_window.setProperty("most_recent_image", str(image_path))

    def show_curation_metadata(self, manifest):
        self.window().left_column_widget.set_curation_manifest(manifest)

    def show_curation_image_path(self, image_path):
        self.window().left_column_widget.set_curation_image_path(image_path)

    def curation_values(self):
        return self.window().left_column_widget.curation_values()

    def copy_previous_enabled(self):
        return self.window().left_column_widget.copy_previous_enabled()

    def copy_previous_fields(self):
        return self.window().left_column_widget.copy_previous_fields()



