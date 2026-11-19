import shutil
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QFrame, QGridLayout, QLabel, QInputDialog, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout
from PySide6.QtCore import Qt

from data.paths import USER_DIR
from ui.columns.notebooks.right_column_tabs.saved_prompt_entry import SavedPromptEntry
from windows.confirmation import Confirm
from windows.error import Error


class SavedPromptsMasterTab(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.saved_prompts_root_dir = USER_DIR / "saved_prompts"
        self.saved_prompts_root_dir.mkdir(parents=True, exist_ok=True)
        self.current_page_widget = None
        self.pages = []
        self.build_saved_prompts_tab()
        self.refresh_saved_prompts()

    def build_saved_prompts_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.save_prompt_button = QPushButton("Save Prompt", self)
        self.save_prompt_button.clicked.connect(self.save_current_prompt)
        self.grid.addWidget(self.save_prompt_button, 0, 0)

        self.create_folder_button = QPushButton("Create Folder", self)
        self.create_folder_button.clicked.connect(self.create_folder)
        self.grid.addWidget(self.create_folder_button, 0, 1)

        self.subfolder_combobox = QComboBox(self)
        self.grid.addWidget(self.subfolder_combobox, 1, 0, 1, 2)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_content = QFrame(self.scroll_area)
        self.scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.scroll_area.setWidget(self.scroll_content)
        self.prompts_layout = QVBoxLayout(self.scroll_content)
        self.prompts_layout.setContentsMargins(4, 4, 4, 4)
        self.prompts_layout.setSpacing(8)
        self.grid.addWidget(self.scroll_area, 2, 0, 1, 2)
        self.grid.setRowStretch(2, 1)
        self.subfolder_combobox.currentIndexChanged.connect(self.refresh_saved_prompts)

    def create_folder(self):
        folder_name, accepted = QInputDialog.getText(self, "Create Folder", "Folder name:")
        if not accepted:
            return

        folder_name = folder_name.strip()
        if not folder_name or Path(folder_name).name != folder_name:
            Error(self, "Please enter a valid folder name.")
            return

        folder_path = self.saved_prompts_root_dir / folder_name
        if folder_path.exists():
            Error(self, "A folder with that name already exists.")
            return

        try:
            folder_path.mkdir(parents=True)
        except OSError as exc:
            Error(self, f"Unable to create folder: {exc}")
            return

        self.refresh_saved_prompts()
        index = self.subfolder_combobox.findData(folder_name)
        if index >= 0:
            self.subfolder_combobox.setCurrentIndex(index)

    def save_current_prompt(self):
        source_path = self.window().property("most_recent_image")
        if not source_path or not Path(source_path).is_file():
            Error(self, "No loaded image is available to save as a prompt.")
            return

        name, accepted = QInputDialog.getText(self, "Save Prompt", "File name:")
        if not accepted:
            return

        name = name.strip()
        if not name or Path(name).name != name:
            Error(self, "Please enter a valid file name.")
            return

        source_path = Path(source_path)
        if not Path(name).suffix:
            name = f"{name}{source_path.suffix}"

        folder_name = self.subfolder_combobox.currentData()
        destination_dir = self.saved_prompts_root_dir
        if folder_name not in {None, "__all__", "__root__"}:
            destination_dir /= str(folder_name)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / name

        if destination_path.exists():
            Error(self, "A saved prompt with that file name already exists.")
            return

        try:
            shutil.copy2(source_path, destination_path)
        except OSError as exc:
            Error(self, f"Unable to save prompt: {exc}")
            return

        self.refresh_saved_prompts()

    def _clear_entries(self):
        while self.prompts_layout.count():
            item = self.prompts_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _files_by_folder(self):
        image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        folders = {"__root__": [], "__all__": []}
        root_files = sorted(path for path in self.saved_prompts_root_dir.iterdir() if path.is_file() and path.suffix.lower() in image_suffixes)
        folders["__root__"].extend(root_files)
        folders["__all__"].extend(root_files)
        for subfolder in sorted(path for path in self.saved_prompts_root_dir.iterdir() if path.is_dir()):
            files = sorted(path for path in subfolder.rglob("*") if path.is_file() and path.suffix.lower() in image_suffixes)
            folders[subfolder.name] = files
            folders["__all__"].extend(files)
        for name in folders:
            folders[name] = sorted(set(folders[name]))
        return folders

    def _refresh_subfolder_options(self, folders):
        selected_value = self.subfolder_combobox.currentData()
        self.subfolder_combobox.blockSignals(True)
        self.subfolder_combobox.clear()
        self.subfolder_combobox.addItem("All", "__all__")
        self.subfolder_combobox.addItem("Root", "__root__")
        for name in sorted(name for name in folders if name not in {"__all__", "__root__"}):
            self.subfolder_combobox.addItem(name, name)
        selected_index = self.subfolder_combobox.findData(selected_value)
        self.subfolder_combobox.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.subfolder_combobox.blockSignals(False)

    def refresh_saved_prompts(self):
        self._clear_entries()
        folders = self._files_by_folder()
        self._refresh_subfolder_options(folders)
        image_paths = folders.get(self.subfolder_combobox.currentData(), [])
        if not image_paths:
            placeholder = QLabel("No saved prompts found.", self.scroll_content)
            placeholder.setAlignment(Qt.AlignCenter)
            self.prompts_layout.addWidget(placeholder)
            self.prompts_layout.addStretch(1)
            return

        callback = self.window().file_dropped
        for image_path in image_paths:
            entry = SavedPromptEntry(
                self.scroll_content,
                image_path,
                lambda checked=False, path=image_path: callback(str(path)),
                lambda checked=False, path=image_path: self.delete_prompt(path),
            )
            self.prompts_layout.addWidget(entry)
        self.prompts_layout.addStretch(1)

    def delete_prompt(self, image_path):
        confirmation = Confirm(self, "Delete Prompt", f"Delete the saved prompt '{Path(image_path).name}'?", "Delete", "Cancel")
        if not confirmation.exec():
            return
        try:
            Path(image_path).unlink()
        except OSError as exc:
            Error(self, f"Unable to delete prompt: {exc}")
            return
        self.refresh_saved_prompts()

    def export_state(self):
        return {"subfolder": self.subfolder_combobox.currentData()}

    def import_state(self, state):
        selected_index = self.subfolder_combobox.findData(state.get("subfolder"))
        if selected_index >= 0:
            self.subfolder_combobox.setCurrentIndex(selected_index)