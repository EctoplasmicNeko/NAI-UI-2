from pathlib import Path
from threading import Thread

from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from data.paths import CURATION_DIR, OUTPUT_DIR
from process.image_curation import (
    CurationError,
    CurationProgress,
    apply_curation,
    apply_trash_curation,
    calculate_character_matches,
    calculate_pairing_matches,
    images_in_folder,
    is_managed_folder,
    initialize_curation_manifests,
    load_curation_manifest,
    load_pairing_tags,
    output_folders,
    sort_by_character_curation,
    sort_by_set_curation,
    update_curation_manifest,
)
from ui.columns.notebooks.right_column_tabs.image_curator_entry import ImageCuratorEntry
from windows.error import Error

MANIFEST_INIT_THREAD_NAME = "curation-manifest-init"
CURATION_APPLY_THREAD_NAME = "curation-apply"


class ThumbnailLoader(QObject):
    thumbnail_ready = Signal(object, object)
    finished = Signal()

    def __init__(self, image_paths, icon_size):
        super().__init__()
        self.image_paths = list(image_paths)
        self.icon_size = QSize(icon_size)
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def run(self):
        for image_path in self.image_paths:
            if self.cancelled:
                break

            image_reader = QImageReader(str(image_path))
            image_reader.setScaledSize(self.icon_size)
            image = image_reader.read()
            if not self.cancelled and not image.isNull():
                self.thumbnail_ready.emit(image_path, image)

        self.finished.emit()


class ImageCuratorTab(QFrame):
    bulk_actions_enabled_changed = Signal(bool)
    IMAGES_PER_PAGE = 60

    def __init__(self, parent, preview_image_callback, metadata_callback=None, curation_values_callback=None, curation_mode_callback=None, copy_previous_enabled_callback=None, image_path_callback=None, copy_previous_fields_callback=None):
        super().__init__(parent)
        self.preview_image_callback = preview_image_callback
        self.metadata_callback = metadata_callback or (lambda manifest: None)
        self.curation_values_callback = curation_values_callback or (lambda: {})
        self.curation_mode_callback = curation_mode_callback or (lambda active: None)
        self.copy_previous_enabled_callback = copy_previous_enabled_callback or (lambda: False)
        self.image_path_callback = image_path_callback or (lambda image_path: None)
        self.copy_previous_fields_callback = copy_previous_fields_callback or (lambda: {})
        self.output_dir = OUTPUT_DIR
        self.entries = {}
        self.last_selected_path = None
        self.current_page = 0
        self.image_paths = []
        self._refresh_gallery_pending = False
        self._select_first_after_refresh = False
        self._thumbnail_generation = 0
        self._thumbnail_worker = None
        self._thumbnail_threads = []
        self.destroyed.connect(lambda: self._stop_thumbnail_threads())
        self.build_image_curator_tab()
        self._refresh_folder_options()
        self._update_controls()

    def build_image_curator_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(3)

        self.mode_frame = QFrame(self)
        self.mode_layout = QHBoxLayout(self.mode_frame)
        self.mode_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_layout.setSpacing(3)
        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.setExclusive(True)
        self.gallery_mode_button = QPushButton("Gallery", self.mode_frame)
        self.gallery_mode_button.setCheckable(True)
        self.gallery_mode_button.setChecked(True)
        self.mode_button_group.addButton(self.gallery_mode_button, 0)
        self.mode_layout.addWidget(self.gallery_mode_button)
        self.curation_mode_button = QPushButton("Curation", self.mode_frame)
        self.curation_mode_button.setCheckable(True)
        self.mode_button_group.addButton(self.curation_mode_button, 1)
        self.mode_layout.addWidget(self.curation_mode_button)
        self.mode_button_group.idToggled.connect(self._on_mode_toggled)
        self.grid.addWidget(self.mode_frame, 0, 0, 1, 2)

        self.folder_combobox = QComboBox(self)
        self.folder_combobox.currentIndexChanged.connect(self.refresh_gallery)
        self.grid.addWidget(self.folder_combobox, 1, 0, 1, 2)

        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.clicked.connect(self.refresh_gallery)
        self.grid.addWidget(self.refresh_button, 2, 0)

        self.page_jump_combobox = QComboBox(self)
        self.page_jump_combobox.currentIndexChanged.connect(self._jump_to_page)
        self.grid.addWidget(self.page_jump_combobox, 2, 1)

        self.previous_page_button = QPushButton("Previous", self)
        self.previous_page_button.clicked.connect(self.show_previous_page)
        self.grid.addWidget(self.previous_page_button, 3, 0)

        self.next_page_button = QPushButton("Next", self)
        self.next_page_button.clicked.connect(self.show_next_page)
        self.grid.addWidget(self.next_page_button, 3, 1)

        self.page_label = QLabel(self)
        self.page_label.setAlignment(Qt.AlignCenter)
        self.grid.addWidget(self.page_label, 4, 0, 1, 2)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_content = QWidget(self.scroll_area)
        self.thumbnail_layout = QGridLayout(self.scroll_content)
        self.thumbnail_layout.setContentsMargins(4, 4, 4, 4)
        self.thumbnail_layout.setSpacing(4)
        self.thumbnail_layout.addWidget(QLabel("Open Curate to load this folder.", self.scroll_content), 0, 0, 1, 2)
        self.scroll_area.setWidget(self.scroll_content)
        self.grid.addWidget(self.scroll_area, 5, 0, 1, 2)

        self.apply_button = QPushButton("Apply Curation", self)
        self.apply_button.clicked.connect(self.apply_selected_curation)
        self.grid.addWidget(self.apply_button, 6, 0, 1, 2)

        self.grid.setRowStretch(5, 1)

    def _on_mode_toggled(self, mode_id, checked):
        if checked:
            self.activate_mode(mode_id == 1)

    def activate_mode(self, curation_active):
        self.curation_mode_callback(curation_active)
        if curation_active:
            self.initialize_manifests()
        self._schedule_gallery_refresh(select_first=curation_active)
        self._update_controls()

    def _schedule_gallery_refresh(self, select_first=False):
        self._select_first_after_refresh = self._select_first_after_refresh or select_first
        if self._refresh_gallery_pending:
            return
        self._refresh_gallery_pending = True
        QTimer.singleShot(0, self._refresh_gallery_after_activation)

    def _refresh_gallery_after_activation(self):
        self._refresh_gallery_pending = False
        select_first = self._select_first_after_refresh
        self._select_first_after_refresh = False
        self.refresh_gallery()
        if select_first:
            self.select_first_image()

    def curation_mode_active(self):
        return self.curation_mode_button.isChecked()

    def _clear_entries(self):
        self._cancel_thumbnail_loader()
        self._thumbnail_generation += 1
        self.entries = {}
        while self.thumbnail_layout.count():
            item = self.thumbnail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _cancel_thumbnail_loader(self):
        if self._thumbnail_worker is not None:
            self._thumbnail_worker.cancel()
            self._thumbnail_worker = None

    def _stop_thumbnail_threads(self):
        self._cancel_thumbnail_loader()
        for thread in list(self._thumbnail_threads):
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
        self._thumbnail_threads.clear()

    def _start_thumbnail_loader(self, page_images):
        self._cancel_thumbnail_loader()
        self._thumbnail_generation += 1
        generation = self._thumbnail_generation
        if not page_images or not self.isVisible():
            return

        thread = QThread(self)
        worker = ThumbnailLoader(page_images, QSize(116, 116))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.thumbnail_ready.connect(
            lambda image_path, image, generation=generation: self._set_entry_thumbnail(generation, image_path, image)
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread: self._thumbnail_threads.remove(thread) if thread in self._thumbnail_threads else None)
        self._thumbnail_worker = worker
        self._thumbnail_threads.append(thread)
        thread.start()

    def _set_entry_thumbnail(self, generation, image_path, image):
        if generation != self._thumbnail_generation:
            return
        entry = self.entries.get(Path(image_path))
        if entry is not None:
            entry.set_thumbnail(image)

    def _refresh_folder_options(self):
        selected_folder = self.folder_combobox.currentData()
        folders = output_folders(self.output_dir)
        self.folder_combobox.blockSignals(True)
        self.folder_combobox.clear()
        for folder in folders:
            relative_path = folder.relative_to(self.output_dir)
            label = "Output" if not relative_path.parts else relative_path.as_posix()
            # Store as str: QComboBox.findData compares custom Python objects by identity, not value.
            self.folder_combobox.addItem(label, str(folder))
        selected_index = self.folder_combobox.findData(selected_folder)
        self.folder_combobox.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.folder_combobox.blockSignals(False)

    def refresh_gallery(self):
        self._refresh_folder_options()
        folder = self.folder_combobox.currentData()
        if folder is None:
            self.image_paths = []
            self.current_page = 0
            self.last_selected_path = None
            self._clear_entries()
            self._update_controls()
            return

        self.image_paths = images_in_folder(Path(folder))
        if self.last_selected_path not in self.image_paths:
            self.last_selected_path = None
        page_count = max(1, (len(self.image_paths) + self.IMAGES_PER_PAGE - 1) // self.IMAGES_PER_PAGE)
        self.current_page = min(self.current_page, page_count - 1)
        self._show_current_page()

    def initialize_manifests(self):
        Thread(target=initialize_curation_manifests, args=(self.output_dir,), name=MANIFEST_INIT_THREAD_NAME, daemon=True).start()

    def select_first_image(self):
        if not self.image_paths:
            return
        if self.current_page != 0:
            self.current_page = 0
            self._show_current_page()
        self.select_image(self.image_paths[0])

    def show_previous_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._show_current_page()

    def show_next_page(self):
        page_count = max(1, (len(self.image_paths) + self.IMAGES_PER_PAGE - 1) // self.IMAGES_PER_PAGE)
        if self.current_page < page_count - 1:
            self.current_page += 1
            self._show_current_page()

    def _jump_to_page(self, index):
        if index < 0 or index == self.current_page:
            return
        self.current_page = index
        self._show_current_page()

    def advance_image(self, offset):
        if not self.image_paths:
            return

        try:
            current_index = self.image_paths.index(self.last_selected_path)
        except ValueError:
            current_index = 0 if offset > 0 else len(self.image_paths) - 1

        target_index = max(0, min(len(self.image_paths) - 1, current_index + offset))
        target_page = target_index // self.IMAGES_PER_PAGE
        if target_page != self.current_page:
            self.current_page = target_page
            self._show_current_page()

        target_path = self.image_paths[target_index]
        self.select_image(target_path)

    def _show_current_page(self):
        self._clear_entries()
        page_count = max(1, (len(self.image_paths) + self.IMAGES_PER_PAGE - 1) // self.IMAGES_PER_PAGE)
        page_start = self.current_page * self.IMAGES_PER_PAGE
        page_images = self.image_paths[page_start:page_start + self.IMAGES_PER_PAGE]
        if not page_images:
            placeholder = QLabel("No images in this folder.", self.scroll_content)
            placeholder.setAlignment(Qt.AlignCenter)
            self.thumbnail_layout.addWidget(placeholder, 0, 0, 1, 2)
        else:
            for index, image_path in enumerate(page_images):
                status = load_curation_manifest(image_path)["status"] if self.curation_mode_active() else None
                entry = ImageCuratorEntry(self.scroll_content, image_path, status)
                entry.selected.connect(self.select_image)
                self.entries[image_path] = entry
                self.thumbnail_layout.addWidget(entry, index // 2, index % 2)
            self._start_thumbnail_loader(page_images)

        self.page_label.setText(f"Page {self.current_page + 1} of {page_count}")
        self.previous_page_button.setEnabled(self.current_page > 0)
        self.next_page_button.setEnabled(self.current_page < page_count - 1)
        self.page_jump_combobox.blockSignals(True)
        self.page_jump_combobox.clear()
        self.page_jump_combobox.addItems([f"Page {page_number + 1}" for page_number in range(page_count)])
        self.page_jump_combobox.setCurrentIndex(self.current_page)
        self.page_jump_combobox.blockSignals(False)
        self._update_controls()

    def save_selected_curation_values(self, values):
        if self.last_selected_path is not None and self.last_selected_path.is_file():
            update_curation_manifest(self.last_selected_path, values)
            entry = self.entries.get(self.last_selected_path)
            if entry is not None:
                entry.set_status_outline(values.get("status"))

    def select_image(self, image_path):
        image_path = Path(image_path)
        entry = self.entries[image_path]
        previous_image_path = self.last_selected_path
        for path, other_entry in self.entries.items():
            if path != image_path:
                other_entry.setChecked(False)
        entry.setChecked(True)

        self.last_selected_path = image_path
        self.preview_image_callback(image_path)
        if self.curation_mode_active():
            self.image_path_callback(image_path)
            if (
                self.copy_previous_enabled_callback()
                and previous_image_path is not None
                and previous_image_path != image_path
                and previous_image_path.is_file()
            ):
                copy_values = self.curation_values_callback()
                copy_fields = self.copy_previous_fields_callback()
                if isinstance(copy_values, dict) and isinstance(copy_fields, dict):
                    filtered_values = {
                        field: value
                        for field, value in copy_values.items()
                        if field in copy_fields and copy_fields.get(field)
                    }
                    if filtered_values:
                        update_curation_manifest(image_path, filtered_values)
                        if "status" in filtered_values:
                            entry.set_status_outline(filtered_values.get("status"))
            self.metadata_callback(load_curation_manifest(image_path))
        self._update_controls()

    def _update_controls(self):
        current_folder = self.folder_combobox.currentData()
        actions_enabled = self.curation_mode_active() and bool(self.image_paths) and current_folder is not None and not is_managed_folder(
            Path(current_folder), self.output_dir
        )
        self.apply_button.setEnabled(actions_enabled)
        self.bulk_actions_enabled_changed.emit(actions_enabled)

    def _create_progress_dialog(self, title, label_text, total):
        progress = QProgressDialog(label_text, "Cancel", 0, total, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)
        return progress

    def _auto_calculate_all(self, field):
        folder = self.folder_combobox.currentData()
        if not self.curation_mode_active() or folder is None or is_managed_folder(Path(folder), self.output_dir):
            return
        updated_count = 0
        skipped_count = 0
        label = "pairings" if field == "pairing" else "characters"
        progress = None
        cancelled = False
        try:
            images = images_in_folder(Path(folder))
            pairing_tags = load_pairing_tags(CURATION_DIR / "pairing_tags.json") if field == "pairing" else {}
            progress = self._create_progress_dialog(f"Auto-Calculate All {label.title()}", f"Auto-calculating {label}...", len(images))
            for index, image_path in enumerate(images):
                if progress.wasCanceled():
                    cancelled = True
                    break
                progress.setLabelText(f"Auto-calculating {label}: {index} of {len(images)} images processed")
                QApplication.processEvents()
                matches = (
                    calculate_pairing_matches(image_path, pairing_tags)
                    if field == "pairing"
                    else calculate_character_matches(image_path)
                )
                if matches is None:
                    skipped_count += 1
                else:
                    update_curation_manifest(image_path, {field: matches})
                    updated_count += 1
                progress.setValue(index + 1)
            if self.last_selected_path is not None and self.last_selected_path.is_file():
                self.metadata_callback(load_curation_manifest(self.last_selected_path))
        except (CurationError, OSError) as exc:
            Error(self, f"Unable to auto-calculate {field} after updating {updated_count} image(s): {exc}")
            return
        finally:
            if progress is not None:
                progress.close()
        status = "cancelled" if cancelled else "finished"
        print(f"Auto-calculate all {label} {status}: updated {updated_count} image(s); skipped {skipped_count} without required metadata.")

    def apply_selected_curation(self):
        images = list(self.image_paths)
        if not images:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Apply Curation")
        layout = QGridLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(QLabel(f"Choose how to apply curation to {len(images)} image(s).", dialog), 0, 0)
        selected_action = {"value": None}

        for row, (label, action) in enumerate(
            (("Apply All", "all"), ("Apply to Trash", "trash"), ("Sort by Set", "set"), ("Sort by Character", "character")),
            start=1,
        ):
            button = QPushButton(label, dialog)
            button.clicked.connect(lambda checked=False, action=action: (selected_action.update(value=action), dialog.accept()))
            layout.addWidget(button, row, 0)

        cancel_button = QPushButton("Cancel", dialog)
        cancel_button.clicked.connect(dialog.reject)
        layout.addWidget(cancel_button, 5, 0)
        if not dialog.exec():
            return

        actions = {
            "all": ("Apply All", apply_curation),
            "trash": ("Apply to Trash", apply_trash_curation),
            "set": ("Sort by Set", sort_by_set_curation),
            "character": ("Sort by Character", sort_by_character_curation),
        }
        if selected_action["value"] not in actions:
            return
        action_title, action_function = actions[selected_action["value"]]

        progress = CurationProgress()
        try:
            self._run_with_progress(action_title, len(images), progress, lambda: action_function(images, self.output_dir, progress))
        except CurationError as exc:
            Error(self, str(exc))
        except OSError as exc:
            Error(self, f"Unable to move selected images: {exc}")
        else:
            status = "cancelled" if progress.cancelled else "finished"
            print(f"{action_title} {status}: {progress.processed} of {len(images)} image(s) processed.")

        # Refresh even after an error or cancellation, since earlier batches may already have moved.
        self.refresh_gallery()

    def _run_with_progress(self, title, total, progress, work):
        """Run file work on a worker thread so the window keeps repainting; the UI only reads progress counters."""
        dialog = self._create_progress_dialog(title, f"{title}: 0 of {total} images processed\nanalyzing", total)
        dialog.canceled.connect(progress.cancel)
        outcome = {}

        def run():
            try:
                outcome["result"] = work()
            except BaseException as exc:
                outcome["error"] = exc

        worker = Thread(target=run, name=CURATION_APPLY_THREAD_NAME, daemon=True)
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(50)

        def poll():
            if dialog.wasCanceled():
                progress.cancel()
            if not progress.cancelled:
                dialog.setValue(progress.processed)
                block_text = f"block {progress.block} of {progress.block_count}"
                if progress.stage == CurationProgress.CHECKING:
                    detail = f"analyzing {block_text} ({progress.checked} of {total} analyzed)"
                elif progress.stage == CurationProgress.MOVING:
                    detail = f"moving {block_text}"
                else:
                    detail = f"writing Hydrus tags {progress.tagged} of {progress.tag_total} ({block_text})"
                dialog.setLabelText(f"{title}: {progress.processed} of {total} images processed\n{detail}")
            if not worker.is_alive():
                timer.stop()
                loop.quit()

        timer.timeout.connect(poll)
        worker.start()
        timer.start()
        loop.exec()
        # Closing a QProgressDialog emits canceled(), which must not mark a finished run as cancelled.
        dialog.canceled.disconnect(progress.cancel)
        dialog.close()
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("result")