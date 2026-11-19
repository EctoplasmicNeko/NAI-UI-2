import faulthandler
from copy import deepcopy
from datetime import datetime
import math
import os
import re
import shutil
import sys
import threading
import traceback
from PIL import Image, ImageOps

from PySide6.QtWidgets import QApplication, QFrame, QLayout, QWidget, QGridLayout
from PySide6.QtCore import QTimer, QThread

from widget.dropawareframe import DropAwareFrame
from process.CompletionSignaler import completion_signaler
from data.datahub import get_data, load_image_tree
from windows.error import Error
from windows.import_on_drop import (
    ImportDialog,
    derive_legacy_quick_weights,
    prepend_missing_quick_weights,
    prepare_saved_quick_weights_for_import,
)
from signaling.import_signal import import_signal
from windows.wildcard_manager import ManageWildcardWindow

from ui.columns.left_column import LeftColumn
from ui.columns.centre_column import CentreColumn
from ui.columns.right_column import RightColumn
from process.workers import GenerateWorker
from process.account_usage import AccountUsageController
from process.frequency import should_cycle_on_frequency, loops_until_next
from data.save import load_config, save_config, load_default
from process.drop_handling import get_metadata, is_valid_image_file
from process.metadata import get_imported_coordinate_mode
from windows.manage_characters import ManageCharacterWindow
from windows.manage_sizes import ManageSizesWindow
from windows.all_character_settings import AllCharacterSettingsWindow
from data.character_slots import MAX_CHARACTER_SLOTS
from data.paths import USER_DIR
from data.themes import render_theme
from PySide6.QtGui import QImageReader, QImage
from PySide6.QtCore import Qt, qInstallMessageHandler


_crash_log = None
GENERATION_WATCHDOG_HEARTBEAT_MS = 5_000
GENERATION_WATCHDOG_TIMEOUT_SECONDS = 10


def build_reset_ui_state(state):
    reset_state = deepcopy(state)

    generate = reset_state.setdefault('generate', {})
    generate['seed'] = 0
    for key in ('legacy_v3', 'legacy_v4', 'SMEA', 'DYN', 'variety+', 'decrisp', 'brownian'):
        generate[key] = False
    generate['rescale'] = 0.0
    generate['cfg'] = -1

    reset_state.setdefault('colorize', {}).update({
        'colorize_strength': 'Normal',
        'colorize_strength_weight': 0,
        'colorize_prompt': '',
    })
    reset_state.setdefault('emotion', {}).update({
        'emotion_type': 'Neutral',
        'emotion_strength': 'Normal',
        'emotion_prompt': '',
        'emotion_strength_weight': 0,
        'emotion_merged_prompt': 'neutral;;',
    })

    reset_state.setdefault('global_prompt', {}).update({
        'global_positive_prompt': '',
        'global_negative_prompt': '',
        'global_positive_preset_name': 'None',
        'global_positive_preset_tags': '',
        'global_positive_preset_target': None,
        'global_negative_preset_name': 'None',
        'global_negative_preset_tags': '',
        'character_number': 0,
    })

    workflow = reset_state.setdefault('workflow', {})
    workflow.update({
        'request_name': 'generate',
        'request_url': 'https://image.novelai.net/ai/generate-image',
        'task_list': ['Generate'],
        'loops': 1,
        'sets': 1,
        'filter_1': 'None',
        'filter_2': 'None',
        'filter_3': 'None',
        'filter_1_mode': 'include',
        'filter_2_mode': 'include',
        'filter_3_mode': 'include',
    })

    modifiers = reset_state.setdefault('modifiers', {})
    for key, value in list(modifiers.items()):
        if isinstance(value, bool):
            modifiers[key] = False
    modifiers['max_behavior'] = 'stop'

    vibe = reset_state.setdefault('vibe', {})
    vibe.update({
        'reference_image_paths': [],
        'reference_strengths': [],
        'reference_information_extracted': [],
        'normalize_strength': False,
        'vibe_enabled': False,
        'random_vibes': False,
        'advance_vibes': False,
        'randomize_strengths': False,
    })
    for entry in vibe.get('entries', {}).values():
        if isinstance(entry, dict):
            entry['selected'] = False

    artist = reset_state.setdefault('artist', {})
    artist.update({
        'prompt_entries': [],
        'artists_enabled': False,
        'random_artists': False,
        'advance_artists': False,
        'randomize_strengths': False,
    })
    for entry in artist.get('entries', {}).values():
        if isinstance(entry, dict):
            entry['selected'] = False

    character_reset = {
        'character': 'None',
        'character_positive_prompt': '',
        'character_negative_prompt': '',
        'character_static_positive_prompt': '',
        'character_static_negative_prompt': '',
        'character_positive_quick_weights': [],
        'character_negative_quick_weights': [],
        'character_preset_positive': '',
        'character_preset_negative': '',
        'character_preset_global_positive': '',
        'character_preset_global_negative': '',
        'character_outfit_preset_positive': '',
        'character_outfit_preset_negative': '',
        'most_recent_outfit': 'None',
        'character_outfit_role_preset': 'None',
        'character_outfit_modifier_preset': '',
        'character_outfit_modifier_presets': [],
        'character_outfit_suppressed_slots': [],
        'character_reference_path': None,
        'character_reference_enabled': False,
        'character_reference_style_aware': 'character',
        'character_reference_fidelity': 1.0,
        'character_reference_strength': 0.0,
        'character_coordinate_button': 0,
        'character_coordinate_mode': 'auto',
        'character_x_coordinate': 0.0,
        'character_y_coordinate': 0.0,
        'character_can_randomize_position': False,
        'character_swap_prompts': False,
        'character_auto_randomize_enabled': False,
        'character_auto_randomize_frequency': 1,
        'character_tag_associations': [],
        'character_labels': [],
        'chance_tag': [],
        'character_outfit_removals': [],
        'character_global_tag_association_enabled': False,
        'character_disable_associations': False,
        'character_randomize_quick_weights': False,
        'character_quick_weights_positive_only': False,
        'boys_to_girls': False,
        'girls_to_boys': False,
        'use_default_expression': False,
        'character_default_expression': [],
        'character_can_scramble': False,
        'auto_advance_characters': False,
        'auto_random_characters': False,
        'auto_advance_character_frequency': 1,
        'auto_advance_character_label1': 'None',
        'label1_mode': 'include',
        'auto_advance_character_label2': 'None',
        'label2_mode': 'include',
        'auto_advance_character_label3': 'None',
        'label3_mode': 'include',
        '_pending_negative_injections': [],
    }
    for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
        reset_state.setdefault(f'character_{slot_id}', {}).update(deepcopy(character_reset))

    return reset_state


def _install_crash_logging():
    global _crash_log

    USER_DIR.mkdir(parents=True, exist_ok=True)
    _crash_log = (USER_DIR / "crash.log").open("a", encoding="utf-8", buffering=1)
    timestamp = datetime.now().isoformat(timespec="seconds")
    _crash_log.write(f"\n{timestamp} Process started (pid={os.getpid()})\n")
    faulthandler.enable(_crash_log, all_threads=True)

    def write_exception(exception_type, exception_value, exception_traceback):
        timestamp = datetime.now().isoformat(timespec="seconds")
        _crash_log.write(f"\n{timestamp} Uncaught exception:\n")
        traceback.print_exception(
            exception_type,
            exception_value,
            exception_traceback,
            file=_crash_log,
        )

    def write_thread_exception(args):
        timestamp = datetime.now().isoformat(timespec="seconds")
        _crash_log.write(f"\n{timestamp} Uncaught exception in thread {args.thread.name}:\n")
        traceback.print_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            file=_crash_log,
        )

    def write_qt_message(message_type, context, message):
        _crash_log.write(f"Qt {message_type.name}: {message}\n")

    sys.excepthook = write_exception
    threading.excepthook = write_thread_exception
    qInstallMessageHandler(write_qt_message)


class MainUI(DropAwareFrame):
    def __init__(self, ):
        super().__init__(parent=None, on_files_dropped=self.file_dropped)
        self.setObjectName("mainUI")

        self.import_dialgue_settings_state = False
        self.import_dialgue_prompt_state = False
        self.import_dialgue_seed_state = False
        self.import_dialgue_characters_state = False

        self.loops = 0
        self.sets = 0
        self.total_loops = 0
        self.requested_loops = 0
        self.requested_sets = 0
        self.new_request = True
        self.incriment_set = False
        self._auto_randomize_set_pending = False
        self.workflow_start_task = None
        self.cancel_requested = False
        self.generate_worker = None
        self.generate_thread = None
        self._close_requested = False
        self._generation_watchdog_active = False
        self._generation_watchdog_phase = "idle"
        self._generation_watchdog_timer = None

        self.image_cache = load_image_tree()
        self.build_main_ui()
        self.setWindowTitle("NAI UI 2")
        try: 
            loaded_config = load_config()
            self.left_column_widget.refresh_all_character_lists()
            self.restore_ui_state(loaded_config)
            import_signal.import_image_signal.connect(self.on_image_imported)
            import_signal.import_reference_signal.connect(self.on_reference_imported)
        except Exception as e:
            Error(self, f"Error occurred while loading configuration - default values will be used: {str(e)}")
            loaded_config = load_default()
            self.left_column_widget.refresh_all_character_lists()
            self.restore_ui_state(loaded_config)
            import_signal.import_image_signal.connect(self.on_image_imported)
            import_signal.import_reference_signal.connect(self.on_reference_imported)

        self.models = get_data("models") #load the models dictionary from the data cache
        self.schedulers = get_data("schedules") #load the models dictionary from the data cache
        self.samplers = get_data("samplers") #load the models dictionary from the data cache
        self.sizes = get_data("sizes") #load the sizes dictionary from the data cache
        self.account_usage = AccountUsageController(self)
        settings_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab
        self.account_usage.updated.connect(settings_tab.set_account_usage)
        self.account_usage.updated.connect(self.right_column_widget.page0.update_account_usage)
        api_entry = self.left_column_widget.upper_frame.page4.API_entry
        api_entry.textChanged.connect(self.account_usage.set_api_key)
        self.account_usage.set_api_key(api_entry.text())

    def build_main_ui(self):
        self.main_grid_layout = QGridLayout(self)
        self.main_grid_layout.setSizeConstraint(QLayout.SetNoConstraint)
        self.main_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.main_grid_layout.setSpacing(0)

        self.left_column_widget = LeftColumn(self, self.image_cache)
        self.centre_column_widget = CentreColumn(self)
        self.centre_right_divider = QFrame(self)
        self.centre_right_divider.setObjectName("centre_right_divider")
        self.centre_right_divider.setFixedWidth(2)
        self.right_column_widget = RightColumn(self)
        self.left_column_widget.setMinimumSize(0, 0)
        self.centre_column_widget.setMinimumSize(0, 0)
        self.right_column_widget.setMinimumSize(0, 0)

        self.main_grid_layout.addWidget(self.left_column_widget, 0, 0)
        self.main_grid_layout.addWidget(self.centre_column_widget, 0, 1)
        self.main_grid_layout.addWidget(self.centre_right_divider, 0, 2)
        self.main_grid_layout.addWidget(self.right_column_widget, 0, 3)

        self.main_grid_layout.setColumnStretch(0, 1)
        self.main_grid_layout.setColumnStretch(1, 3)
        self.main_grid_layout.setColumnStretch(2, 0)
        self.main_grid_layout.setColumnStretch(3, 1)
        self.main_grid_layout.setRowStretch(0, 1)

        #Bound buttons
        account_bars_button = self.left_column_widget.upper_frame.page4.show_account_usage_bars_button
        image_settings_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab
        account_bars_button.toggled.connect(image_settings_tab.set_account_bars_visible)
        image_settings_tab.set_account_bars_visible(account_bars_button.isChecked())
        self.left_column_widget.upper_frame.page4.generate_button.pressed.connect(lambda: self.core_loop())
        self.left_column_widget.upper_frame.page4.manage_characters_button.pressed.connect(lambda: self.launch_manage_characters())
        self.left_column_widget.upper_frame.page4.manage_sizes_action.triggered.connect(self.launch_manage_sizes)
        self.left_column_widget.upper_frame.page4.manage_wildcard_button.pressed.connect(self.launch_manage_wildcards)
        self.left_column_widget.upper_frame.page4.all_character_settings_button.pressed.connect(lambda: self.launch_all_character_settings())
        self.left_column_widget.upper_frame.page4.reset_ui_requested.connect(self.reset_ui)
        self.centre_column_widget.viewport_button.pressed.connect(lambda: self.core_loop())
        self.left_column_widget.upper_frame.page4.theme_combo.currentIndexChanged.connect(lambda: self.apply_theme(QApplication.instance(), self.left_column_widget.upper_frame.page4.theme_combo.currentText()))
        self.left_column_widget.upper_frame.page4.use_alt_character_portraits_checkbox.toggled.connect(self.on_alt_character_portraits_toggled)
        import_signal.import_signal.connect(self.import_state_from_image_metadata)
        self.left_column_widget.upper_frame.page2.cancel_task_button.pressed.connect(lambda: self.abort_loops())
        self.left_column_widget.curation_metadata_tab.values_changed.connect(
            self.right_column_widget.page4.save_selected_curation_values
        )
        self.left_column_widget.curation_metadata_tab.auto_calculate_all_requested.connect(
            self.right_column_widget.page4._auto_calculate_all
        )
        self.right_column_widget.page4.bulk_actions_enabled_changed.connect(
            self.left_column_widget.curation_metadata_tab.set_bulk_actions_enabled
        )
        self.left_column_widget.curation_metadata_tab.set_bulk_actions_enabled(
            self.right_column_widget.page4.apply_button.isEnabled()
        )
        self._connect_coordinate_overlay()
        completion_signaler.loop_start_signal.connect(self._auto_randomize_character_slots)
        completion_signaler.set_start_signal.connect(self._mark_auto_randomize_set_pending)
        self._connect_next_operation_refresh()
        self._refresh_next_operation_panel()

    def reset_ui(self):
        if self.generate_worker is not None or not self.new_request:
            self.abort_loops()

        self.restore_ui_state(build_reset_ui_state(self.get_ui_state()))
        self._auto_randomize_set_pending = False
        self._refresh_next_operation_panel()
        self.update_coordinate_overlay()

    def set_curation_mode(self, active):
        if active and (self.generate_worker is not None or not self.new_request):
            self.abort_loops()
        self.left_column_widget.set_curation_mode(active)
        self.centre_column_widget.set_curation_mode(active)
        self.centre_column_widget.set_curation_wheel_callback(
            self.right_column_widget.page4.advance_image if active else None
        )
        self.left_column_widget.upper_frame.page4.generate_button.setEnabled(not active)
        # blockSignals (not setEnabled) so the viewport still previews images and handles curation wheel scrolling.
        self.centre_column_widget.viewport_button.blockSignals(active)

    def _connect_coordinate_overlay(self):
        sizes_combo = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab.sizes_comboxbox
        sizes_combo.currentIndexChanged.connect(self.update_coordinate_overlay)

        for character_id in range(1, MAX_CHARACTER_SLOTS + 1):
            coordinate_tab = getattr(
                self.left_column_widget.lower_frame,
                f"character_tab_{character_id}",
            ).sub_notebook.character_sub_tab_2
            coordinate_tab.horizontal_spinbox.valueChanged.connect(self.update_coordinate_overlay)
            coordinate_tab.vertical_spinbox.valueChanged.connect(self.update_coordinate_overlay)
            coordinate_tab.show_markers_button.toggled.connect(
                self._set_all_coordinate_markers_visible
            )

        self.update_coordinate_overlay()

    def _mark_auto_randomize_set_pending(self):
        self._auto_randomize_set_pending = True

    def _auto_randomize_character_slots(self, action_type):
        if action_type.lower() != "generate":
            return

        coordinate_tab = self.left_column_widget.lower_frame.character_tab_1.sub_notebook.character_sub_tab_2
        if not coordinate_tab.auto_randomize_button.isChecked():
            self._auto_randomize_set_pending = False
            return

        should_randomize = should_cycle_on_frequency(
            coordinate_tab.auto_randomize_frequency_spinbox.value(),
            self.total_loops + 1,
            self._auto_randomize_set_pending,
        )
        self._auto_randomize_set_pending = False
        if should_randomize:
            coordinate_tab.randomize_slots()

    def _set_all_coordinate_markers_visible(self, visible):
        for character_id in range(1, MAX_CHARACTER_SLOTS + 1):
            coordinate_tab = getattr(
                self.left_column_widget.lower_frame,
                f"character_tab_{character_id}",
            ).sub_notebook.character_sub_tab_2
            button = coordinate_tab.show_markers_button
            button.blockSignals(True)
            button.setChecked(visible)
            button.blockSignals(False)
            self.centre_column_widget.set_coordinate_marker_visible(character_id, visible)

    def update_coordinate_overlay(self):
        positions = {}
        for character_id in range(1, MAX_CHARACTER_SLOTS + 1):
            coordinate_tab = getattr(
                self.left_column_widget.lower_frame,
                f"character_tab_{character_id}",
            ).sub_notebook.character_sub_tab_2
            positions[character_id] = coordinate_tab.get_selected_coordinates()
            self.centre_column_widget.set_coordinate_marker_visible(
                character_id,
                coordinate_tab.show_markers_button.isChecked(),
            )

        sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab
        image_width = sizes_tab.sizes_comboxbox.property("image_width")
        image_height = sizes_tab.sizes_comboxbox.property("image_height")
        self.centre_column_widget.set_coordinate_overlay(positions, image_width, image_height)

    def _refresh_next_operation_panel(self):
        self.right_column_widget.page0.update_next_operation(self._collect_next_operation_lines())

    def _connect_next_operation_refresh(self):
        refresh = self._refresh_next_operation_panel

        vibe_tab = self.right_column_widget.page1
        artist_tab = self.right_column_widget.page2
        for widget in (
            vibe_tab.random_vibes_checkbox, vibe_tab.advance_vibes_checkbox,
            artist_tab.random_artists_checkbox, artist_tab.advance_artists_checkbox,
        ):
            widget.toggled.connect(refresh)
        for widget in (
            vibe_tab.random_vibe_frequency_spinbox, vibe_tab.advance_vibe_frequency_spinbox,
            artist_tab.random_artist_frequency_spinbox, artist_tab.advance_artist_frequency_spinbox,
        ):
            widget.valueChanged.connect(refresh)

        modifier_tab = self.left_column_widget.upper_frame.page3
        for widget in (
            modifier_tab.seed_creep_checkbox,
            modifier_tab.steps_creep_checkbox, modifier_tab.steps_random_button,
            modifier_tab.scale_creep_checkbox, modifier_tab.scale_random_button,
            modifier_tab.cfg_creep_checkbox, modifier_tab.cfg_random_button,
            modifier_tab.sampler_creep_checkbox, modifier_tab.schedule_creep_checkbox,
        ):
            widget.toggled.connect(refresh)
        for widget in (
            modifier_tab.seed_creep_frequency_counter,
            modifier_tab.steps_creep_frequency_counter,
            modifier_tab.scale_creep_frequency_counter,
            modifier_tab.cfg_creep_frequency_counter,
            modifier_tab.sampler_creep_frequency_counter,
            modifier_tab.schedule_creep_frequency_counter,
        ):
            widget.valueChanged.connect(refresh)

        self.left_column_widget.upper_frame.page1.character_number_counter.valueChanged.connect(refresh)

        for character_id in range(1, MAX_CHARACTER_SLOTS + 1):
            character_tab = getattr(self.left_column_widget.lower_frame, f"character_tab_{character_id}")
            modifiers_tab = character_tab.sub_notebook.character_sub_tab_4
            modifiers_tab.auto_advance_characters_checkbox.toggled.connect(refresh)
            modifiers_tab.auto_random_characters_checkbox.toggled.connect(refresh)
            modifiers_tab.auto_advance_character_frequency_spinbox.valueChanged.connect(refresh)

            coordinate_tab = character_tab.sub_notebook.character_sub_tab_2
            coordinate_tab.auto_randomize_button.toggled.connect(refresh)
            coordinate_tab.auto_randomize_frequency_spinbox.valueChanged.connect(refresh)
            coordinate_tab.can_randomize_checkbox.toggled.connect(refresh)

    def file_dropped(self, file_path):
        if not is_valid_image_file(file_path):
            Error(self, "The dropped file is not a supported image format.")
            return
        
        try:
            dict_type, metadata = get_metadata(file_path)

            image_sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab
            reference_width = int(image_sizes_tab.sizes_comboxbox.property("image_width") or 0)
            reference_height = int(image_sizes_tab.sizes_comboxbox.property("image_height") or 0)
            import_dialog = ImportDialog(self, file_path, dict_type, metadata, self.import_dialgue_settings_state, self.import_dialgue_prompt_state, self.import_dialgue_seed_state, self.import_dialgue_characters_state, True, reference_width, reference_height)
            import_dialog.exec()

        except Exception:
            image_sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab
            reference_width = int(image_sizes_tab.sizes_comboxbox.property("image_width") or 0)
            reference_height = int(image_sizes_tab.sizes_comboxbox.property("image_height") or 0)
            import_dialog = ImportDialog(self, file_path, None, None, self.import_dialgue_settings_state, self.import_dialgue_prompt_state, self.import_dialgue_seed_state, self.import_dialgue_characters_state, False, reference_width, reference_height)
            import_dialog.exec()
     

    def get_ui_state(self, randomize_coordinates=False, generation_number=1):
        state = {
        'main_window': self.export_state(),
        'generate': self.left_column_widget.upper_frame.page0.image_master_stack_generate.export_state(),
        'colorize': self.left_column_widget.upper_frame.page0.image_master_stack_colorize.export_state(),
        'emotion': self.left_column_widget.upper_frame.page0.image_master_stack_emotion.export_state(),
        'global_prompt': self.left_column_widget.upper_frame.page1.export_state(),
        'workflow': self.left_column_widget.upper_frame.page2.export_state(),
        'settings': self.left_column_widget.upper_frame.page4.export_state(),
        'modifiers': self.left_column_widget.upper_frame.page3.export_state(),
        'vibe': self.right_column_widget.page1.export_state(randomize_vibes=randomize_coordinates, generation_number=generation_number),
        'artist': self.right_column_widget.page2.export_state(randomize_artists=randomize_coordinates, generation_number=generation_number),
        'saved_prompts': self.right_column_widget.page3.export_state(),
        }
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            middle_tab = getattr(self.left_column_widget.middle_frame, f"character_tab_{slot_id}")
            lower_tab = getattr(self.left_column_widget.lower_frame, f"character_tab_{slot_id}")
            state[f"character_{slot_id}"] = middle_tab.export_state() | lower_tab.export_state(
                randomize_coordinates=randomize_coordinates,
                randomize_quick_weights=(
                    randomize_coordinates and slot_id <= state['global_prompt']['character_number']
                ),
            )
        return state

    def _collect_next_operation_lines(self):
        generation_number = self.total_loops + 1
        lines = []

        vibe_tab = self.right_column_widget.page1
        vibe_state = vibe_tab.export_state()
        if vibe_state["random_vibes"]:
            lines.append(f"Vibe Random: {loops_until_next(vibe_state['random_vibe_frequency'], generation_number)}")
        if vibe_state["advance_vibes"]:
            lines.append(f"Vibe Advance: {loops_until_next(vibe_state['advance_vibe_frequency'], generation_number)}")

        artist_tab = self.right_column_widget.page2
        artist_state = artist_tab.export_state()
        if artist_state["random_artists"]:
            lines.append(f"Artist Random: {loops_until_next(artist_state['random_artist_frequency'], generation_number)}")
        if artist_state["advance_artists"]:
            lines.append(f"Artist Advance: {loops_until_next(artist_state['advance_artist_frequency'], generation_number)}")

        modifier_state = self.left_column_widget.upper_frame.page3.export_state()
        creep_labels = [
            ("Seed Creep", "seed_creep", "seed_creep_frequency"),
            ("Steps Random", "steps_random", "steps_creep_frequency"),
            ("Steps Creep", "steps_creep", "steps_creep_frequency"),
            ("Scale Random", "scale_random", "scale_creep_frequency"),
            ("Scale Creep", "scale_creep", "scale_creep_frequency"),
            ("CFG Random", "cfg_random", "cfg_creep_frequency"),
            ("CFG Creep", "cfg_creep", "cfg_creep_frequency"),
            ("Sampler Creep", "sampler_creep", "sampler_creep_frequency"),
            ("Schedule Creep", "schedule_creep", "schedule_creep_frequency"),
        ]
        for label, enabled_key, frequency_key in creep_labels:
            if modifier_state[enabled_key]:
                lines.append(f"{label}: {loops_until_next(modifier_state[frequency_key], generation_number)}")

        active_character_count = max(
            0,
            min(
                MAX_CHARACTER_SLOTS,
                self.left_column_widget.upper_frame.page1.character_number_counter.value(),
            ),
        )
        eligible_auto_swap_count = 0
        for character_id in range(1, active_character_count + 1):
            character_tab = getattr(self.left_column_widget.lower_frame, f"character_tab_{character_id}")
            modifiers_tab = character_tab.sub_notebook.character_sub_tab_4
            if modifiers_tab.auto_advance_characters_checkbox.isChecked() or modifiers_tab.auto_random_characters_checkbox.isChecked():
                mode = "Auto-Advance" if modifiers_tab.auto_advance_characters_checkbox.isChecked() else "Auto-Random"
                frequency = modifiers_tab.auto_advance_character_frequency_spinbox.value()
                if frequency <= 0:
                    lines.append(f"Character {character_id} {mode}: next set ({self.requested_loops - self.loops} left)")
                else:
                    lines.append(f"Character {character_id} {mode}: {loops_until_next(frequency, generation_number)}")

            coordinate_tab = character_tab.sub_notebook.character_sub_tab_2
            if coordinate_tab.can_randomize_checkbox.isChecked():
                eligible_auto_swap_count += 1

        if active_character_count > 0:
            auto_swap_tab = self.left_column_widget.lower_frame.character_tab_1.sub_notebook.character_sub_tab_2
            if auto_swap_tab.auto_randomize_button.isChecked() and eligible_auto_swap_count >= 2:
                frequency = auto_swap_tab.auto_randomize_frequency_spinbox.value()
                if frequency <= 0:
                    lines.append(f"Next Auto-Swap: next set ({self.requested_loops - self.loops} left)")
                else:
                    lines.append(f"Next Auto-Swap: {loops_until_next(frequency, generation_number)}")

        return lines
    
    def check_loop_conditions(self):
        if self.new_request:
            self.loops = 0
            self.sets = 0
            self.total_loops = 0
            self._auto_randomize_set_pending = False

            self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setValue(0)
            self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setValue(0)

            completion_signaler.start_signal.emit()
            self.requested_loops = self.left_column_widget.upper_frame.page2.loops.value()
            self.requested_sets = self.left_column_widget.upper_frame.page2.sets.value()
            if self.requested_sets == 0: #use 'per character' mode
                self.requested_sets = self.left_column_widget.upper_frame.page2.determine_list_length()

            self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setRange(0, self.requested_loops)
            self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setRange(0, self.requested_sets)
            self.left_column_widget.upper_frame.page2.loops.setDisabled(True)
            self.left_column_widget.upper_frame.page2.sets.setDisabled(True)
            self.workflow_start_task = self.left_column_widget.upper_frame.page2.list.item(0).text()
            self.new_request = False
            self._refresh_next_operation_panel()
    
    def abort_loops(self):
        self._stop_generation_watchdog()
        self.cancel_requested = True
        self.loops = 0
        self.sets = 0
        self.total_loops = 0
        self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setValue(0)
        self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setValue(0)

        self.left_column_widget.upper_frame.page2.loops.setDisabled(False) 
        self.left_column_widget.upper_frame.page2.sets.setDisabled(False)
        self.new_request = True
        self.incriment_set = False

        if self.generate_worker is not None:
            self.generate_worker.cancel()
        else:
            self.cancel_requested = False
            completion_signaler.complete_signal.emit()

    def _set_generation_watchdog_phase(self, phase):
        self._generation_watchdog_phase = phase
        if _crash_log is None:
            return
        try:
            timestamp = datetime.now().isoformat(timespec="seconds")
            _crash_log.write(f"{timestamp} Generation phase: {phase}\n")
        except (OSError, ValueError):
            pass

    def _refresh_generation_watchdog(self):
        if not self._generation_watchdog_active or _crash_log is None:
            return
        try:
            faulthandler.cancel_dump_traceback_later()
            faulthandler.dump_traceback_later(
                GENERATION_WATCHDOG_TIMEOUT_SECONDS,
                repeat=False,
                file=_crash_log,
            )
        except (OSError, RuntimeError, ValueError):
            pass

    def _start_generation_watchdog(self, phase):
        self._generation_watchdog_active = True
        self._set_generation_watchdog_phase(phase)
        if self._generation_watchdog_timer is None:
            self._generation_watchdog_timer = QTimer(self)
            self._generation_watchdog_timer.setInterval(GENERATION_WATCHDOG_HEARTBEAT_MS)
            self._generation_watchdog_timer.timeout.connect(self._refresh_generation_watchdog)
        self._generation_watchdog_timer.start()
        self._refresh_generation_watchdog()

    def _stop_generation_watchdog(self):
        if not getattr(self, "_generation_watchdog_active", False):
            return
        self._generation_watchdog_active = False
        generation_watchdog_timer = getattr(self, "_generation_watchdog_timer", None)
        if generation_watchdog_timer is not None:
            generation_watchdog_timer.stop()
        try:
            faulthandler.cancel_dump_traceback_later()
        except (RuntimeError, ValueError):
            pass
        self._generation_watchdog_phase = "idle"

    def core_loop(self):
        generate_thread = getattr(self, "generate_thread", None)
        if self.cancel_requested or generate_thread is not None:
            return
        self.cancel_requested = False
        self._start_generation_watchdog(f"preparing generation {self.total_loops + 1}")
        if self.incriment_set:
            self.incriment_set = False
            self.loops = 0
            self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setValue(self.loops)
            self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setValue(self.sets)
            

        preparation_phase = "locking the interface"
        try:
            completion_signaler.window_lock_signal.emit(True)
            preparation_phase = "initializing the workflow"
            self._set_generation_watchdog_phase(preparation_phase)
            self.check_loop_conditions()
            preparation_phase = "applying generation automation"
            self._set_generation_watchdog_phase(preparation_phase)
            completion_signaler.loop_start_signal.emit(self.left_column_widget.upper_frame.page2.list.item(0).text())
            preparation_phase = "applying generation modifiers"
            self._set_generation_watchdog_phase(preparation_phase)
            modifier_tab = self.left_column_widget.upper_frame.page3
            modifier_tab.apply_modifiers(self.total_loops + 1)
            preparation_phase = "capturing the UI state"
            self._set_generation_watchdog_phase(preparation_phase)
            generation_number = self.total_loops + 1
            state = self.get_ui_state(randomize_coordinates=True, generation_number=generation_number)
        except Exception as exc:
            if _crash_log is not None:
                _crash_log.write(f"\nGeneration failed while {preparation_phase}:\n")
                traceback.print_exc(file=_crash_log)
            self._reset_generation_state()
            Error(self, f"Generation failed while {preparation_phase}: {exc}")
            return

        self.generate_thread = QThread(self)
        generate_thread = self.generate_thread
        self.generate_worker = GenerateWorker(state)
        self.generate_worker.moveToThread(generate_thread)
        generate_thread.started.connect(self.generate_worker.run)
        self.generate_worker.result.connect(self.on_generate_result)
        self.generate_worker.error.connect(self.on_generate_error)
        self.generate_worker.finished.connect(generate_thread.quit)
        self.generate_worker.finished.connect(self.generate_worker.deleteLater)
        generate_thread.finished.connect(lambda: self._on_generate_thread_finished(generate_thread))
        generate_thread.finished.connect(generate_thread.deleteLater)
        generate_thread.start()
        self._set_generation_watchdog_phase(f"generation {generation_number} worker running")

    def _on_generate_thread_finished(self, generate_thread):
        if not self._close_requested:
            self.account_usage.refresh()
        if self.generate_thread is generate_thread:
            self.generate_worker = None
            self.generate_thread = None
            if self._close_requested:
                QTimer.singleShot(0, self.close)

    def _reset_generation_state(self):
        self._stop_generation_watchdog()
        self.loops = 0
        self.sets = 0
        self.total_loops = 0
        self.incriment_set = False
        self.new_request = True
        self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setValue(0)
        self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setValue(0)
        self.left_column_widget.upper_frame.page2.loops.setDisabled(False)
        self.left_column_widget.upper_frame.page2.sets.setDisabled(False)
        completion_signaler.complete_signal.emit()

    def on_generate_error(self, error_message: str):
        if self.cancel_requested:
            self.cancel_requested = False
            self._stop_generation_watchdog()
            completion_signaler.complete_signal.emit()
            return

        self._reset_generation_state()
        Error(self, f"Generation failed: {error_message}")

    def on_generate_result(self, image_path: str, state: dict):
        self._set_generation_watchdog_phase("displaying generation result")
        try:
            self._process_generate_result(image_path, state)
        except Exception as exc:
            phase = getattr(self, "_generation_watchdog_phase", "processing the generation result")
            if _crash_log is not None:
                _crash_log.write(f"\nGeneration failed while {phase}:\n")
                traceback.print_exc(file=_crash_log)
            self._reset_generation_state()
            Error(self, f"Generation failed while {phase}: {exc}")

    def _process_generate_result(self, image_path: str, state: dict):
        if self.cancel_requested:
            self.cancel_requested = False
            self._stop_generation_watchdog()
            completion_signaler.complete_signal.emit()
            return

        if image_path == '':
            self._reset_generation_state()
            Error(self, "Generation failed. Please check your settings and try again.")
            return
        
        else:
            self._set_generation_watchdog_phase("decoding the generated image")
            if not self.centre_column_widget.update_image(image_path):
                self._reset_generation_state()
                Error(self, f"Generation returned an image that could not be displayed: {image_path}")
                return
            self._set_generation_watchdog_phase("advancing the generation workflow")
            self.left_column_widget.upper_frame.page2.cycle_list()

            if state['workflow']['request_name'] == 'generate':
                self.setProperty("most_recent_image", image_path)
                self.setProperty("most_recent_width", state['generate']["image_width"])
                self.setProperty("most_recent_height", state['generate']["image_height"])
                self.loops += 1
                self.total_loops += 1
                self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setValue(self.loops)
                if self.loops >= self.requested_loops:
                    self.incriment_set = True
                    self.sets += 1
                    self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setValue(self.sets)
                    completion_signaler.set_start_signal.emit()
                self._refresh_next_operation_panel()

            next_task = self.left_column_widget.upper_frame.page2.list.item(0).text()
            if self.cancel_requested:
                return

            # Sets only reaches requested_sets on the final loop of the final set,
            # so completion is: final set reached and the task list has cycled
            # back to the task the workflow started on.
            workflow_complete = (
                self.sets >= self.requested_sets
                and next_task == self.workflow_start_task
            )
            if workflow_complete:
                self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_loop_bar.setValue(self.loops)
                self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_settings_tab.generate_progress_set_bar.setValue(self.sets)

                self.left_column_widget.upper_frame.page2.loops.setDisabled(False) 
                self.left_column_widget.upper_frame.page2.sets.setDisabled(False)
                self.new_request = True
                self._stop_generation_watchdog()
                completion_signaler.complete_signal.emit()
            else:
                # Workflow still in progress: pause and wait for the next manual click.
                self._stop_generation_watchdog()
                completion_signaler.window_lock_signal.emit(False)
          

    def on_alt_character_portraits_toggled(self, checked: bool):
        self.image_cache = load_image_tree(checked)
        self.left_column_widget.image_cache = self.image_cache
        self.left_column_widget.upper_frame.page4.image_cache = self.image_cache
        self.left_column_widget.middle_frame.image_cache = self.image_cache
        self.left_column_widget.lower_frame.image_cache = self.image_cache

        character_tabs = [
            getattr(frame, f"character_tab_{slot_id}")
            for frame in (
                self.left_column_widget.middle_frame,
                self.left_column_widget.lower_frame,
            )
            for slot_id in range(1, MAX_CHARACTER_SLOTS + 1)
        ]
        for tab in character_tabs:
            if hasattr(tab, 'image_cache'):
                tab.image_cache = self.image_cache
            if hasattr(tab, 'fluff_tab') and hasattr(tab.fluff_tab, 'image_cache'):
                tab.fluff_tab.image_cache = self.image_cache

        self.left_column_widget.refresh_all_character_lists()

    def restore_ui_state(self, loaded, import_workflow_filters=True, import_character_filters=True):
        self.import_state(loaded['main_window'])
        self.left_column_widget.upper_frame.page0.image_master_stack_generate.import_state(loaded['generate'])
        self.left_column_widget.upper_frame.page0.image_master_stack_colorize.import_state(loaded['colorize'])
        self.left_column_widget.upper_frame.page0.image_master_stack_emotion.import_state(loaded['emotion'])
        self.left_column_widget.upper_frame.page1.import_state(loaded['global_prompt'])
        self.left_column_widget.upper_frame.page2.import_state(loaded['workflow'], import_filters=import_workflow_filters)
        self.left_column_widget.upper_frame.page4.import_state(loaded['settings'])
        self.left_column_widget.upper_frame.page3.import_state(loaded.get('modifiers', {}))
        self.right_column_widget.page1.import_state(loaded.get('vibe', {}))
        self.right_column_widget.page3.import_state(loaded.get('saved_prompts', {}))
        self.right_column_widget.page2.import_state(loaded.get('artist', {}))
        self.on_alt_character_portraits_toggled(self.left_column_widget.upper_frame.page4.use_alt_character_portraits_checkbox.isChecked())

        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            character_state = loaded[f"character_{slot_id}"]
            getattr(
                self.left_column_widget.middle_frame,
                f"character_tab_{slot_id}",
            ).import_state(character_state)
            getattr(
                self.left_column_widget.lower_frame,
                f"character_tab_{slot_id}",
            ).import_state(character_state, import_filters=import_character_filters)

        theme_name = self.left_column_widget.upper_frame.page4.theme_combo.currentText()
        self.apply_theme(QApplication.instance(), theme_name)


    def export_state(self):
        return {
            'most_recent_image': self.property('most_recent_image'),
            'most_recent_height': self.property('most_recent_height'),
            'most_recent_width': self.property('most_recent_width'),
            'import_dialog_settings_state': self.import_dialgue_settings_state,
            'import_dialog_prompt_state': self.import_dialgue_prompt_state,
            'import_dialog_seed_state': self.import_dialgue_seed_state,
            'import_dialog_characters_state': self.import_dialgue_characters_state,
        }
    
    def import_state(self, loaded):
        self.setProperty("most_recent_image", loaded['most_recent_image'])
        self.setProperty("most_recent_width", loaded['most_recent_width'])
        self.setProperty("most_recent_height", loaded['most_recent_height'])
        self.import_dialgue_settings_state = loaded['import_dialog_settings_state']
        self.import_dialgue_prompt_state = loaded['import_dialog_prompt_state']
        self.import_dialgue_seed_state = loaded['import_dialog_seed_state']
        self.import_dialgue_characters_state = loaded['import_dialog_characters_state']

    def closeEvent(self, event):
        self.account_usage.close()
        if self.generate_thread is not None and self.generate_thread.isRunning():
            self._close_requested = True
            self.abort_loops()
            event.ignore()
            return

        state = self.get_ui_state()
        save_config(state)
        event.accept()

    def launch_all_character_settings(self):
        self.all_character_settings_window = AllCharacterSettingsWindow(self)
        if self.all_character_settings_window.exec():
            self.reload_character_label_filters()

    def reload_character_label_filters(self):
        self.left_column_widget.upper_frame.page2.reload_labels()
        for index in range(1, MAX_CHARACTER_SLOTS + 1):
            getattr(self.left_column_widget.lower_frame, f"character_tab_{index}").on_refresh_character_list()

    def launch_manage_characters(self):
        self.manage_char_window = ManageCharacterWindow(self, self.image_cache)
        self.manage_char_window.exec()
        self.image_cache = load_image_tree()
        for slot_id in range(1, MAX_CHARACTER_SLOTS + 1):
            getattr(
                self.left_column_widget.middle_frame,
                f"character_tab_{slot_id}",
            ).image_cache = self.image_cache
        #refresh of character lists will be handled by signal emitted from manage characters window

    def launch_manage_sizes(self):
        self.manage_sizes_window = ManageSizesWindow(self)
        if self.manage_sizes_window.exec():
            self.sizes = get_data("sizes", [])
            sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab
            sizes_tab.reload_sizes(self.sizes)

    def launch_manage_wildcards(self):
        self.manage_wildcard_window = ManageWildcardWindow(self)
        self.manage_wildcard_window.exec()
        

    def import_state_from_image_metadata(self, dict_type: str, metadata: dict, load_settings: bool,
                                         load_prompt: bool, load_seed: bool, load_characters: bool,
                                         restore_quick_weights: bool = True,
                                         disable_associations: bool = False):
        
        self.import_dialgue_prompt_state = load_prompt
        self.import_dialgue_settings_state = load_settings
        self.import_dialgue_seed_state = load_seed
        self.import_dialgue_characters_state = load_characters

        state = self.get_ui_state()

        if dict_type == 'custom':
            
                if load_settings:
                    #generate
                    state['generate']['model_name'] = metadata['generate']['model']
                    state['generate']['sampler_name'] = metadata['generate']['sampler']
                    state['generate']['schedule_name'] = metadata['generate']['schedule']
                    state['generate']['steps'] = metadata['generate']['steps']
                    state['generate']['scale'] = metadata['generate']['scale']  
                    state['generate']['rescale'] = metadata['generate']['rescale']
                    state['generate']['cfg'] = metadata['generate']['cfg']

                    state['generate']['legacy_v3'] = metadata['generate']['legacy_v3']
                    state['generate']['legacy_v4'] = metadata['generate']['legacy_v4']
                    state['generate']['SMEA'] = metadata['generate']['SMEA']
                    state['generate']['DYN'] = metadata['generate']['DYN']
                    state['generate']['variety+'] = metadata['generate']['variety+']
                    state['generate']['decrisp'] = metadata['generate']['decrisp']
                    state['generate']['brownian'] = metadata['generate']['brownian']

                    state['generate']['size_name'] = metadata['generate']['size_name']
                    size_match = re.search(r'(\d+)\s*x\s*(\d+)\s*$', str(state['generate']['size_name']))
                    if size_match:
                        state['generate']['image_height'] = int(size_match.group(1))
                        state['generate']['image_width'] = int(size_match.group(2))

                if load_seed:
                    state['generate']['seed'] = metadata['generate']['seed']

                    #characters     
                if load_characters:
                    character_number = min(
                        MAX_CHARACTER_SLOTS,
                        metadata['global_prompt']['character_number'],
                    )
                    for index in range(1, character_number + 1):
                        key = f"character_{index}"
                        slot_data = metadata['characters'][key]

                        state[key]['character'] = slot_data['character']
                        state[key]['character_disable_associations'] = (
                            True if disable_associations
                            else slot_data.get('character_disable_associations', False)
                        )
                        state[key]['character_randomize_quick_weights'] = slot_data.get(
                            'character_randomize_quick_weights', False
                        )
                        state[key]['character_quick_weights_positive_only'] = slot_data.get(
                            'character_quick_weights_positive_only', False
                        )

                        state[key]['character_positive_prompt'] = slot_data['character_positive_prompt']
                        state[key]['character_negative_prompt'] = slot_data['character_negative_prompt']
                        state[key]['character_static_positive_prompt'] = slot_data.get('character_static_positive_prompt', '')
                        state[key]['character_static_negative_prompt'] = slot_data.get('character_static_negative_prompt', '')
                        # Older metadata predates quick weight capture, so default to empty.
                        positive_quick_weights = slot_data.get('character_positive_quick_weights', [])
                        negative_quick_weights = slot_data.get('character_negative_quick_weights', [])
                        has_quick_weight_data = bool(positive_quick_weights or negative_quick_weights)
                        if has_quick_weight_data and not restore_quick_weights:
                            (
                                state[key]['character_positive_prompt'],
                                state[key]['character_negative_prompt'],
                                positive_quick_weights,
                                negative_quick_weights,
                            ) = prepare_saved_quick_weights_for_import(
                                state[key]['character_positive_prompt'],
                                state[key]['character_negative_prompt'],
                                positive_quick_weights,
                                negative_quick_weights,
                                False,
                            )
                        elif not has_quick_weight_data:
                            compiled_captions = metadata.get('_compiled_character_captions', {}).get(key, {})
                            state[key]['character_positive_prompt'] = prepend_missing_quick_weights(
                                state[key]['character_positive_prompt'],
                                derive_legacy_quick_weights(
                                    slot_data.get('character'),
                                    compiled_captions.get('positive', ''),
                                ),
                            )
                            state[key]['character_negative_prompt'] = prepend_missing_quick_weights(
                                state[key]['character_negative_prompt'],
                                derive_legacy_quick_weights(
                                    slot_data.get('character'),
                                    compiled_captions.get('negative', ''),
                                    negative=True,
                                ),
                            )
                        state[key]['character_positive_quick_weights'] = positive_quick_weights
                        state[key]['character_negative_quick_weights'] = negative_quick_weights
                        state[key]['character_preset_positive'] = slot_data['character_preset_positive']
                        state[key]['character_preset_negative'] = slot_data['character_preset_negative']
                        state[key]['character_preset_global_positive'] = slot_data['character_preset_global_positive']
                        state[key]['character_preset_global_negative'] = slot_data['character_preset_global_negative']
                        state[key]['character_coordinate_button'] = slot_data['character_coordinate_button']
                        state[key]['character_x_coordinate'] = slot_data.get('character_x_coordinate', 0.0)
                        state[key]['character_y_coordinate'] = slot_data.get('character_y_coordinate', 0.0)
                        state[key]['character_coordinate_mode'] = get_imported_coordinate_mode(slot_data)
                        state[key]['character_outfit_preset_positive'] = slot_data['character_outfit_preset_positive']
                        state[key]['character_outfit_preset_negative'] = slot_data['character_outfit_preset_negative']
                        state[key]['most_recent_outfit'] = slot_data['most_recent_outfit']

                if load_prompt:
                    #global prompt
                    state['global_prompt']['global_positive_prompt'] = metadata['global_prompt']['global_positive_prompt']
                    state['global_prompt']['global_negative_prompt'] = metadata['global_prompt']['global_negative_prompt']
                    state['global_prompt']['global_positive_preset_name'] = metadata['global_prompt']['global_positive_preset_name']
                    state['global_prompt']['global_negative_preset_name'] = metadata['global_prompt']['global_negative_preset_name']
                    state['global_prompt']['global_positive_preset_tags'] = metadata['global_prompt']['global_positive_preset_tags']
                    state['global_prompt']['global_negative_preset_tags'] = metadata['global_prompt']['global_negative_preset_tags']
                    state['global_prompt']['character_number'] = min(
                        MAX_CHARACTER_SLOTS,
                        metadata['global_prompt']['character_number'],
                    )
                
        else:
            if dict_type == 'native':
                    
                if load_settings:

                    model_used = metadata['top_level']['source']
                    matched_model = None
                    for model in self.models.values():
                        builds = model.get("builds", [])
                        inpaints = model.get("inpaints", [])

                        if model_used in builds or model_used in inpaints:
                            matched_model = model
                            break

                    if matched_model is None:
                        Error(self, "The model used to generate this image is not mapped. Please contact u/EctoplasmicNeko on Reddit to have it added.")
                        return

                    state['generate']['model_name'] = matched_model["name"]
                    
                    sampler_used = metadata['generate']['sampler']
                    for sampler in self.samplers.values():
                        if sampler_used == sampler["payload_name"]:
                            state['generate']['sampler_name'] = sampler["name"]

                    schedule_used = metadata['generate']['noise_schedule']
                    for schedule in self.schedulers.values():
                        if schedule_used == schedule["payload_name"]:
                            state['generate']['schedule_name'] = schedule["name"]
                        
                    state['generate']['steps'] = metadata['generate']['steps']
                    state['generate']['scale'] = metadata['generate']['scale'] 

                    state['generate']['rescale'] = metadata['generate']['cfg_rescale']

                    used_cfg = metadata['generate']['skip_cfg_above_sigma']
                    if used_cfg is None:
                        used_cfg = -1
                    state['generate']['cfg'] = used_cfg

                    state['generate']['legacy_v3'] = metadata['generate']['legacy_v3_extend']
                    state['generate']['legacy_v4'] = metadata['generate']['legacy_uc']
                    state['generate']['SMEA'] = metadata['generate']['sm']
                    state['generate']['DYN'] = metadata['generate']['sm_dyn']
                    state['generate']['variety+'] = False
                    state['generate']['decrisp'] = metadata['generate']['dynamic_thresholding']
                    state['generate']['brownian'] = metadata['generate']['prefer_brownian']

                    used_height = metadata['generate']['height']
                    used_width = metadata['generate']['width']

                    for size in self.sizes:
                        if size['image_height'] == used_height and size['image_width'] == used_width:
                            state['generate']['size_name'] = size['name']
                            break
                    else:
                        state['generate']['size_name'] = None
                        state['generate']['image_height'] = used_height
                        state['generate']['image_width'] = used_width

                if load_seed:
                    state['generate']['seed'] = metadata['generate']['seed']

                if load_characters:
                    character_number = min(
                        MAX_CHARACTER_SLOTS,
                        metadata['global_prompt']['character_number'],
                    )
                    for index in range(1, character_number + 1):
                        key = f"character_{index}"
                        state[key]['character'] = 'Loaded'  #trigger for character matching screen  
                        state[key]['character_disable_associations'] = disable_associations

                        state[key]['character_positive_prompt'] = metadata['characters'][key]['character_positive_prompt']
                        state[key]['character_negative_prompt'] = metadata['characters'][key]['character_negative_prompt']
                        state[key]['character_static_positive_prompt'] = ''
                        state[key]['character_static_negative_prompt'] = ''
                        # Native metadata bakes quick weights directly into the prompt text above.
                        state[key]['character_positive_quick_weights'] = []
                        state[key]['character_negative_quick_weights'] = []
                        state[key]['character_preset_positive'] = None
                        state[key]['character_preset_negative'] = None
                        state[key]['character_preset_global_positive'] = None
                        state[key]['character_preset_global_negative'] = None

                        x = metadata['characters'][key]['character_x_pos']
                        y = metadata['characters'][key]['character_y_pos']
                        state[key]['character_coordinate_button'] = 0
                        state[key]['character_x_coordinate'] = x
                        state[key]['character_y_coordinate'] = y
                        state[key]['character_coordinate_mode'] = (
                            'coordinate' if metadata['generate'].get('use_coords', False) else 'auto'
                        )

                if load_prompt:
                    #global prompt
                    state['global_prompt']['global_positive_prompt'] = metadata['global_prompt']['global_positive_prompt']
                    state['global_prompt']['global_negative_prompt'] = metadata['global_prompt']['global_negative_prompt']
                    state['global_prompt']['global_positive_preset_name'] = 'None'
                    state['global_prompt']['global_negative_preset_name'] = 'None'
                    state['global_prompt']['global_positive_preset_tags'] = ''
                    state['global_prompt']['global_negative_preset_tags'] = ''
                    state['global_prompt']['character_number'] = min(
                        MAX_CHARACTER_SLOTS,
                        metadata['global_prompt']['character_number'],
                    )
                    

        self.restore_ui_state(state, import_workflow_filters=False, import_character_filters=False)

    def on_image_imported(self, image_path: str, width: int, height: int):
        imported_images_dir = USER_DIR / "imported_image"
        imported_images_dir.mkdir(parents=True, exist_ok=True)

        stored_image_path = imported_images_dir / "imported.png"

        image_reader = QImageReader(image_path)
        image_reader.setAutoTransform(True)
        imported_image = image_reader.read()

        if imported_image.isNull():
            raise ValueError(f"Failed to read image: {image_path}")

        original_width = imported_image.width()
        original_height = imported_image.height()

        def nearest_multiple_of_64(value: int) -> int:
            return max(64, int(round(value / 64)) * 64)

        resized_width = nearest_multiple_of_64(original_width)
        resized_height = nearest_multiple_of_64(original_height)

        if resized_width != original_width or resized_height != original_height:
            imported_image = imported_image.scaled(resized_width, resized_height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        if not imported_image.save(str(stored_image_path), "PNG"):
            raise ValueError(f"Failed to save stored imported image: {stored_image_path}")

        self.centre_column_widget.update_image(str(stored_image_path))
        self.setProperty("most_recent_image", str(stored_image_path))
        self.setProperty("most_recent_width", resized_width)
        self.setProperty("most_recent_height", resized_height)

        for size in self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab.sizes[1:]:
            matched = None
            if int(size['image_height']) == resized_height and int(size['image_width']) == resized_width:
                image_sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab
                size_name = f'{size["name"]} {size["image_height"]} x {size["image_width"]}'
                index = image_sizes_tab.size_list.index(f'{size["name"]} {size["image_height"]} x {size["image_width"]}')
                image_sizes_tab.sizes_comboxbox.setCurrentIndex(index)
                matched = size_name
                break

        if matched != None:
            image_sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab.sizes_comboxbox.setCurrentText(matched)

        else:
            image_sizes_tab = self.left_column_widget.upper_frame.page0.image_master_stack_generate.image_sizes_tab
            image_sizes_tab.heights_list[0] = resized_height
            image_sizes_tab.width_list[0] = resized_width
            image_sizes_tab.sizes_comboxbox.setItemText(0, f"Custom Size {resized_height} x {resized_width}")
            image_sizes_tab.sizes_comboxbox.setProperty("image_height", resized_height)
            image_sizes_tab.sizes_comboxbox.setProperty("image_width", resized_width)
            image_sizes_tab.sizes_comboxbox.setProperty("custom_height", resized_height)
            image_sizes_tab.sizes_comboxbox.setProperty("custom_width", resized_width)
            image_sizes_tab.sizes_comboxbox.setCurrentIndex(0)

    def on_reference_imported(self, image_path: str, width: int, height: int):
        imported_images_dir = USER_DIR / "imported_image"
        imported_images_dir.mkdir(parents=True, exist_ok=True)

        stored_image_path = imported_images_dir / "reference.png"

        with Image.open(image_path) as source_image:
            source_image = ImageOps.exif_transpose(source_image)
            reference_image = source_image.resize(
                (int(width), int(height)),
                Image.Resampling.LANCZOS,
            )
            if reference_image.mode not in ("RGB", "RGBA"):
                reference_image = reference_image.convert("RGBA")
            reference_image.save(str(stored_image_path), "PNG")

        if not stored_image_path.exists():
            raise ValueError(f"Failed to save stored reference image: {stored_image_path}")

        self.centre_column_widget.update_image(str(stored_image_path))
        self.setProperty("most_recent_image", str(stored_image_path))
        self.setProperty("most_recent_width", width)
        self.setProperty("most_recent_height", height)

    def coord_to_index_floor(self, coord: float) -> int:
        # Special-case "None" sentinel
        if coord == 0.0:
            return -1

        raw_index = (coord - 0.1) / 0.2
        index = int(math.floor(raw_index + 1e-6))
        return max(0, min(4, index))  # Clamp to [0, 4]


    def coord_to_button_id(self, x: float, y: float) -> int:
        # (0,0) means "None" -> ID 0
        if x == 0.0 and y == 0.0:
            return 0

        col = self.coord_to_index_floor(x)  # 0 = left
        row = self.coord_to_index_floor(y)  # 0 = bottom
        return row * 5 + col + 1  # 1-based ID


    def apply_theme(self, app, theme_name):
        app.setStyleSheet(render_theme(theme_name))

def run_app():
    _install_crash_logging()
    app = QApplication(sys.argv)
    window = MainUI()
    window.setMinimumSize(0, 0)
    screen = app.primaryScreen()
    if screen is not None:
        window.setGeometry(screen.availableGeometry())
    window.setWindowState(window.windowState() | Qt.WindowMaximized)
    window.show()
    QTimer.singleShot(0, window.showMaximized)
    exit_code = app.exec()
    _crash_log.write(f"Qt event loop exited with code {exit_code}\n")
    sys.exit(exit_code)
