
from PySide6.QtWidgets import QGridLayout, QFrame, QStackedWidget
from ui.columns.notebooks.main_notebook import MainNotebook
from ui.columns.notebooks.character_lower_notebook import CharacterLowerNotebook
from ui.columns.notebooks.character_middle_notebook import CharacterMiddleNotebook
from ui.columns.notebooks.left_column_tabs.curation_metadata_tab import CurationMetadataTab
from data.character_labels import label_values
from data.character_slots import MAX_CHARACTER_SLOTS
from data.datahub import get_all_characters
from signaling.refresh_character_lists import refresh_character_lists_signal

class LeftColumn(QFrame):
    def __init__(self, parent, image_cache):
        super().__init__(parent)
        self.setObjectName("left_column")
        self.image_cache = image_cache
        self.characters = get_all_characters()
        self.build_left_column()
        self.upper_frame.page4.character_sorting_combo.currentIndexChanged.connect(self.refresh_all_character_lists)
        refresh_character_lists_signal.refresh_lists.connect(self.refresh_all_character_lists)

    def build_left_column(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(5, 5, 5, 5)
        self.grid.setSpacing(5)

        self.content_stack = QStackedWidget(self)
        self.grid.addWidget(self.content_stack, 0, 0)

        self.standard_content = QFrame(self.content_stack)
        self.standard_grid = QGridLayout(self.standard_content)
        self.standard_grid.setContentsMargins(0, 0, 0, 0)
        self.standard_grid.setSpacing(5)

        self.standard_grid.setRowStretch(0,45)
        self.standard_grid.setRowStretch(1,0)
        self.standard_grid.setRowStretch(2,45)

        self.upper_frame = MainNotebook(self, self.image_cache)
        self.standard_grid.addWidget(self.upper_frame, 0, 0)

        self.middle_frame = CharacterMiddleNotebook(self, self.image_cache)
        self.standard_grid.addWidget(self.middle_frame, 1, 0)

        self.lower_frame = CharacterLowerNotebook(self, self.image_cache)
        self.standard_grid.addWidget(self.lower_frame, 2, 0)

        self.curation_metadata_tab = CurationMetadataTab(self.content_stack)
        self.content_stack.addWidget(self.standard_content)
        self.content_stack.addWidget(self.curation_metadata_tab)

        self.middle_frame.button_group.idToggled.connect(
            lambda button_id, checked: self.lower_frame.stack.setCurrentIndex(button_id) if checked else None
        )
        character_counter = self.upper_frame.page1.character_number_counter
        character_counter.valueChanged.connect(self.middle_frame.set_character_count)
        self.middle_frame.set_character_count(character_counter.value())

    def set_curation_mode(self, active):
        self.content_stack.setCurrentWidget(self.curation_metadata_tab if active else self.standard_content)

    def set_curation_manifest(self, manifest):
        self.curation_metadata_tab.set_character_choices(getattr(self, "character_list", []))
        self.curation_metadata_tab.set_curation_manifest(manifest)

    def set_curation_image_path(self, image_path):
        self.curation_metadata_tab.set_current_image_path(image_path)

    def curation_values(self):
        return self.curation_metadata_tab.curation_values()

    def copy_previous_enabled(self):
        return self.curation_metadata_tab.copy_previous_enabled()

    def copy_previous_fields(self):
        return self.curation_metadata_tab.copy_previous_fields()

    def refresh_all_character_lists(self):
        self.characters = get_all_characters()
        self.character_list = self.get_sorted_characters_by_priority()
        self.curation_metadata_tab.set_character_choices(self.character_list)

        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            middle_tab = getattr(self.middle_frame, f"character_tab_{slot_id}")
            lower_tab = getattr(self.lower_frame, f"character_tab_{slot_id}")
            character_combo = middle_tab.fluff_tab.character_select_combobox
            selected_character = character_combo.currentText()

            middle_tab.characters = self.characters
            middle_tab.fluff_tab.characters = self.characters
            middle_tab.character_list = self.character_list
            middle_tab.on_refresh_character_list()
            lower_tab.characters = self.characters
            lower_tab.character_autocycle_manager.base_character_list = self.character_list
            lower_tab.on_refresh_character_list()

            character_combo.setCurrentText(
                selected_character if selected_character in self.character_list else "None"
            )
            middle_tab.on_character_change()


    def get_character_priority_score(self, character_dict):
        sort_type = self.upper_frame.page4.character_sorting_combo.currentText()

        if sort_type == "Status":
            labels = label_values(character_dict.get("labels", []))
            if not isinstance(labels, list):
                return 0
            if "Main" in labels:
                return 3
            if "Supporting" in labels:
                return 2
            if "Minor" in labels:
                return 1
            return 0

        if sort_type in ("Youngest", "Oldest"):
            age = character_dict.get("age", None)
            try:
                age_int = int(age)
            except (TypeError, ValueError):
                age_int = 10**9  # unknown ages sink to the bottom
            return -age_int if sort_type == "Youngest" else age_int

        if sort_type == "Custom":
            try:
                return int(character_dict.get("sort_position", 10**9))
            except (TypeError, ValueError):
                return 10**9

        # Alphabetical doesn't need a numeric score
        return 0

    def get_sorted_characters_by_priority(self):
        sort_type = self.upper_frame.page4.character_sorting_combo.currentText()
        visible_characters = [character for character in self.characters if not character.get("exclude_from_character_list", False)]

        if sort_type == "Alphabetical":
            return sorted((c.get("nameID","") for c in visible_characters), key=str.lower)

        if sort_type == "Custom":
            sorted_chars = sorted(
                visible_characters,
                key=lambda c: (self.get_character_priority_score(c), str(c.get("nameID", "")).lower())
            )
            return [c.get("nameID", "") for c in sorted_chars]

        sorted_chars = sorted(visible_characters, key=lambda c: (-self.get_character_priority_score(c), str(c.get("nameID","")).lower()))
        return [c.get("nameID","") for c in sorted_chars]




    


       
