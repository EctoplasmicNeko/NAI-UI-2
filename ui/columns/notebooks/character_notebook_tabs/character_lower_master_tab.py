import json
import random
from PySide6.QtWidgets import QGridLayout, QFrame, QDoubleSpinBox
from ui.columns.notebooks.character_sub_notebook import CharacterSubNotebook
from signaling.character_changed_signal import character_changed_signal
from signaling.outfit_changed import outfit_changed_signal
from data.paths import CHARACTERS_DIR
from process.character_autocycle_manager import CharacterAutoCycleManager
from data.datahub import copy_character_quick_weight_values, get_all_characters, get_character, get_universal_quick_weights, save_universal_quick_weights
from signaling.refresh_character_lists import refresh_character_lists_signal
from data.character_labels import label_values
from data.outfits import compile_outfit_prompt
from windows.character_editor import parse_prompt_text


def _quick_weight_lookup(raw_values):
    """Turn saved merged quick-weight strings (e.g. "1.5::tag::") into {lower_tag: (tag, strength)}."""
    lookup = {}
    for raw_value in raw_values or []:
        for entry in parse_prompt_text(str(raw_value)):
            tag = str(entry.get('tag', '')).strip()
            if tag:
                lookup[tag.lower()] = (tag, float(entry.get('strength', 1.0)))
    return lookup


def _append_unmatched_quick_weights(prompt, unmatched):
    """Keep saved quick weights in the prompt if the current character cannot restore them."""
    if not unmatched:
        return prompt

    fallback_tags = [
        f"{strength:.1f}::{tag}::"
        for tag, strength in unmatched.values()
    ]
    return ", ".join(part for part in (prompt.strip(), ", ".join(fallback_tags)) if part)



class CharacterLowerMasterTab(QFrame):

    def __init__(self, parent, image_cache, ID):
        super().__init__(parent)
        self.current_character = 'None'
        self.ID = ID
        self.image_cache = image_cache
        self.build_character_master_tab()
        character_changed_signal.character_changed_signal.connect(self.on_character_change)
        refresh_character_lists_signal.mutators_changed.connect(self.refresh_mutators)
        self.character_autocycle_manager = CharacterAutoCycleManager(self, self.current_character)
              
    def build_character_master_tab(self):

        self.characters = get_all_characters()                

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.sub_notebook = CharacterSubNotebook(self,self.image_cache, self.ID)
        self.grid.addWidget(self.sub_notebook, 0, 0)
        self.sub_notebook.character_sub_tab_4.mutators_page.personal_data_loaded.connect(
            self._apply_mutator_data
        )

        prompt_tab = self.sub_notebook.character_sub_tab_1.prompt_tab
        prompt_tab.positive_preview_requested.connect(
            lambda checked: self._set_compiled_prompt_preview(True, checked)
        )
        prompt_tab.negative_preview_requested.connect(
            lambda checked: self._set_compiled_prompt_preview(False, checked)
        )

        self.sub_notebook.character_sub_tab_1.quick_weights_tab.quickWeightsChanged.connect(
            self.on_quick_weights_changed
)
        self.sub_notebook.character_sub_tab_4.copy_quick_weights_button.clicked.connect(
            self.copy_quick_weights_to_other_characters
        )
        outfit_changed_signal.outfit_changed.connect(
            self.on_outfit_preset_changed
        )
        self.sub_notebook.character_sub_tab_5.outfit_role_toggled.connect(
            self.on_outfit_role_toggled
        )
        self.sub_notebook.character_sub_tab_5.outfit_modifier_toggled.connect(
            self.on_outfit_modifier_toggled
        )
        self.sub_notebook.character_sub_tab_5.outfit_slot_suppression_changed.connect(
            self.on_outfit_slot_suppression_changed
        )

    @staticmethod
    def _normalize_outfit_role(value):
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().lower().split())

    def _find_outfit_name_for_role(self, character, selected_role, selected_modifiers=None):
        normalized_selected_role = self._normalize_outfit_role(selected_role)
        if not normalized_selected_role or normalized_selected_role == "none":
            return None

        outfits = character.get("outfits", [])
        exact_matches = []
        loose_matches = []
        seen_exact = set()
        seen_loose = set()

        # Prefer exact role matches, then fall back to loose role/name matching.
        for outfit in outfits:
            if not self._outfit_has_all_modifiers(outfit, selected_modifiers or []):
                continue
            outfit_name = outfit.get("name")
            if not outfit_name:
                continue

            if self._normalize_outfit_role(outfit.get("role")) == normalized_selected_role:
                if outfit_name not in seen_exact:
                    exact_matches.append(outfit_name)
                    seen_exact.add(outfit_name)
                continue

            if self._normalize_outfit_role(outfit.get("Role")) == normalized_selected_role:
                if outfit_name not in seen_exact:
                    exact_matches.append(outfit_name)
                    seen_exact.add(outfit_name)
                continue

        for outfit in outfits:
            if not self._outfit_has_all_modifiers(outfit, selected_modifiers or []):
                continue
            outfit_name = outfit.get("name")
            if not outfit_name:
                continue

            for candidate in (outfit.get("role"), outfit.get("Role"), outfit.get("name")):
                normalized_candidate = self._normalize_outfit_role(candidate)
                if not normalized_candidate:
                    continue
                if (
                    normalized_selected_role in normalized_candidate
                    or normalized_candidate in normalized_selected_role
                ):
                    if outfit_name not in seen_loose and outfit_name not in seen_exact:
                        loose_matches.append(outfit_name)
                        seen_loose.add(outfit_name)
                    break

        if exact_matches:
            return random.choice(exact_matches)

        if loose_matches:
            return random.choice(loose_matches)

        return None

    @staticmethod
    def _normalize_outfit_modifier(value):
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().lower().split())

    def _outfit_has_all_modifiers(self, outfit, selected_modifiers):
        normalized_required = [
            self._normalize_outfit_modifier(value)
            for value in (selected_modifiers or [])
            if self._normalize_outfit_modifier(value)
        ]

        if not normalized_required:
            return True

        raw_modifiers = outfit.get("modifier", [])
        if not isinstance(raw_modifiers, list):
            return False

        normalized_modifiers = {
            self._normalize_outfit_modifier(item)
            for item in raw_modifiers
            if isinstance(item, str)
        }

        return all(required in normalized_modifiers for required in normalized_required)

    def _find_first_outfit_name_for_modifiers(self, character, selected_modifiers):
        for outfit in character.get("outfits", []):
            if not isinstance(outfit, dict):
                continue
            if self._outfit_has_all_modifiers(outfit, selected_modifiers):
                return outfit.get("name")
        return None

    def _get_current_character_data(self):
        if self.current_character == 'None':
            return None

        for character in self.characters:
            if character.get("nameID") == self.current_character:
                return character

        return None

    def _set_compiled_prompt_preview(self, positive, enabled):
        prompt_tab = self.sub_notebook.character_sub_tab_1.prompt_tab
        if not enabled:
            if positive:
                prompt_tab.hide_positive_preview()
            else:
                prompt_tab.hide_negative_preview()
            return

        from copy import deepcopy

        from process.process_generate import (
            prepare_negative_character_prompt,
            prepare_positive_character_prompt,
        )

        main_window = self.window()
        state = deepcopy(main_window.get_ui_state())
        global_prompt = state["global_prompt"]
        global_prompt["character_number"] = max(
            int(global_prompt.get("character_number", 0) or 0),
            self.ID,
        )
        for slot_id in range(1, global_prompt["character_number"] + 1):
            state[f"character_{slot_id}"]["_pending_negative_injections"] = []

        positive_captions = prepare_positive_character_prompt(state)
        if positive:
            compiled_prompt = positive_captions[self.ID - 1]["char_caption"]
        else:
            negative_captions = prepare_negative_character_prompt(state)
            compiled_prompt = negative_captions[self.ID - 1]["char_caption"]

        if positive:
            prompt_tab.show_positive_preview(compiled_prompt)
        else:
            prompt_tab.show_negative_preview(compiled_prompt)

    def _populate_outfit_combo(self, character):
        outfits = character.get("outfits", [])
        outfit_names = [
            outfit.get("name")
            for outfit in outfits
            if isinstance(outfit, dict) and outfit.get("name")
        ]

        self.sub_notebook.character_sub_tab_5.outfit_combo.blockSignals(True)
        self.sub_notebook.character_sub_tab_5.outfit_combo.clear()
        self.sub_notebook.character_sub_tab_5.outfit_combo.addItems(["None"] + outfit_names)
        self.sub_notebook.character_sub_tab_5.outfit_combo.blockSignals(False)

    def _apply_outfit_selection_from_role(self, character, selected_role):
        selected_modifiers = self.sub_notebook.character_sub_tab_5.get_selected_outfit_modifiers()

        normalized_role = self._normalize_outfit_role(selected_role)

        if normalized_role == "none":
            # Explicit None role should always force the outfit to None.
            update_outfit = 'None'
        elif not normalized_role:
            update_outfit = character.get('most_recent_outfit', 'None')
            if update_outfit != 'None':
                current_outfit = next(
                    (
                        outfit
                        for outfit in character.get("outfits", [])
                        if isinstance(outfit, dict) and outfit.get("name") == update_outfit
                    ),
                    None,
                )
                if current_outfit is None or not self._outfit_has_all_modifiers(current_outfit, selected_modifiers):
                    update_outfit = 'None'

            if update_outfit == 'None' and selected_modifiers:
                update_outfit = self._find_first_outfit_name_for_modifiers(character, selected_modifiers) or 'None'
        else:
            update_outfit = self._find_outfit_name_for_role(character, selected_role, selected_modifiers) or 'None'

        if update_outfit == 'None':
            self.sub_notebook.character_sub_tab_5.outfit_combo.setCurrentText("None")
            self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.clear()
            self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.clear()
        else:
            self.sub_notebook.character_sub_tab_5.outfit_combo.setCurrentText(update_outfit)

    def on_character_change(self, ID, current_character):
        if ID != self.ID:
            return  # Not for this tab
        self.current_character = current_character

        if current_character != 'None':
            for character in self.characters:  # <-- loop over the dicts
                if character.get("nameID") == current_character:

                    self.sub_notebook.character_sub_tab_3.rebuild_character_references(current_character.lower())

                    character_positive_prompt = []
                    for tag in character['c_positive']:
                        cleaned_cpos_tag = tag['tag'].strip()
                        if tag['strength'] == 1.0:
                            character_positive_prompt.append(tag['tag'])
                        else:
                            character_positive_prompt.append(f"{tag['strength']:.1f}::{cleaned_cpos_tag}::")

                    self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_character_textbox.setText(", ".join(character_positive_prompt))

                    character_negative_prompt = []
                    for tag in character['c_negative']:
                        cleaned_cneg_tag = tag['tag'].strip()
                        if tag['strength'] == 1.0:
                            character_negative_prompt.append(tag['tag'])
                        else:
                            character_negative_prompt.append(f"{tag['strength']:.1f}::{cleaned_cneg_tag}::")

                    self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_character_textbox.setText(", ".join(character_negative_prompt))

                    character_positive_global = []
                    for tag in character.get('g_positive', []):
                        if tag:
                            cleaned_gpos_tag = tag['tag'].strip()
                            if tag['strength'] == 1.0:
                                character_positive_global.append(tag['tag'])
                            else:
                                character_positive_global.append(f"{tag['strength']:.1f}::{cleaned_gpos_tag}::")

                    self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_global_textbox.setText(", ".join(character_positive_global))

                    character_negative_global = []
                    for tag in character.get('g_negative', []):
                        cleaned_gneg_tag = tag['tag'].strip()
                        if tag['strength'] == 1.0:
                            character_negative_global.append(tag['tag'])
                        else:
                            character_negative_global.append(f"{tag['strength']:.1f}::{cleaned_gneg_tag}::")

                    self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_global_textbox.setText(", ".join(character_negative_global))

                    self.sub_notebook.character_sub_tab_1.quick_weights_tab.rebuild_quick_weights(
                        current_character,
                        character.get("quick_weights") or [],
                        get_universal_quick_weights(),
                        self.sub_notebook.character_sub_tab_1.quick_weights_tab.current_mode
                    )

                    self._populate_outfit_combo(character)
                    
                    selected_role = self.sub_notebook.character_sub_tab_5.get_selected_outfit_role()
                    self._apply_outfit_selection_from_role(character, selected_role)
                    
                    
                    
                
                    self.setProperty('tag_associations', character.get("tag_associations") or [])
                    self.setProperty('character_labels', label_values(character.get("labels") or []))
                    self.setProperty('chance_tag', character.get("chance_tag") or [])
                    self.sub_notebook.character_sub_tab_4.mutators_page.set_character(
                        current_character, label_values(character.get("labels") or [])
                    )
                    
                    break


        else:

            self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_character_textbox.clear()
            self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_character_textbox.clear()
            self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_global_textbox.clear()
            self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_global_textbox.clear()
            self.sub_notebook.character_sub_tab_5.outfit_combo.clear()
            self.sub_notebook.character_sub_tab_5.outfit_combo.addItem("None")
            self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.clear()
            self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.clear()

            self.sub_notebook.character_sub_tab_1.quick_weights_tab.rebuild_quick_weights(
                None,
                [],
                get_universal_quick_weights(),
                self.sub_notebook.character_sub_tab_1.quick_weights_tab.current_mode
            )
            self.sub_notebook.character_sub_tab_3.rebuild_character_references(None)
            self.setProperty('character_labels', [])
            self.setProperty('chance_tag', [])
            self.setProperty('character_outfit_removals', [])
            self.sub_notebook.character_sub_tab_4.mutators_page.set_character(None, [])

    def refresh_mutators(self, character_id=""):
        if character_id and character_id != self.current_character:
            return
        character = get_character(self.current_character)
        modifiers = self.sub_notebook.character_sub_tab_4
        if character is not None:
            self._apply_mutator_data(character)
        modifiers.mutators_page.set_character(
            self.current_character, self.property('character_labels') or []
        )

    def _apply_mutator_data(self, character):
        self.setProperty('tag_associations', character.get("tag_associations") or [])
        self.setProperty('chance_tag', character.get("chance_tag") or [])
        self.setProperty('character_labels', label_values(character.get("labels") or []))

    def export_state(self, randomize_coordinates=False, randomize_quick_weights=False):

        modifiers_tab = self.sub_notebook.character_sub_tab_4
        if randomize_quick_weights and modifiers_tab.randomize_quick_weights_button.isChecked():
            self.sub_notebook.character_sub_tab_1.quick_weights_tab.randomize_quick_weights(
                modifiers_tab.quick_weights_positive_only_button.isChecked()
            )
        coordinate_tab = self.sub_notebook.character_sub_tab_2
        coordinate_mode = coordinate_tab.get_coordinate_mode()
        if randomize_coordinates and coordinate_mode == 'random':
            coordinate_tab.randomize_selected_coordinates()

        x_coordinate = coordinate_tab.horizontal_spinbox.value()
        y_coordinate = coordinate_tab.vertical_spinbox.value()
        button_id = coordinate_tab.coordinate_to_button_id(x_coordinate, y_coordinate)

        positive_quick_weights = []
        negative_quick_weights = []

        for widget in self.sub_notebook.character_sub_tab_1.quick_weights_tab.findChildren(QDoubleSpinBox):
            if bool(widget.property('locked')):
                continue
            value = widget.value()
            if value != 0:
                tag = widget.property('tag')
                value_str = f"{value:.1f}" #gets rid of trailing fraction and keeps number to one decimal point
                merged = f"{value_str}::{tag}::"
                is_negative = widget.property('negative')
                if is_negative:
                    negative_quick_weights.append(merged)
                else:
                    positive_quick_weights.append(merged)

        active_reference = None
        if self.current_character != 'None':
            btn = self.sub_notebook.character_sub_tab_3.reference_button_group.checkedButton()
            if btn is not None:
                active_reference = btn.property('image_path')
        
        fidelity = self.sub_notebook.character_sub_tab_3.fidelity_spinner.value()
        fidelity = f"{fidelity:.2f}"
        fidelity = float(fidelity)
        overall_fidelity = 1.00 - fidelity #for whatever reason, NAI uses inverse fidelity for this parameter
        
        reference_strength = self.sub_notebook.character_sub_tab_3.refstrength_spinner.value()
        reference_strength = f"{reference_strength:.2f}"
        reference_strength = float(reference_strength)
        
        if self.sub_notebook.character_sub_tab_3.style_aware_checkbox.isChecked():
            styleaware = 'character&style'
        else:
            styleaware = 'character'
        

        return {
        'character_positive_prompt': self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_textbox.toPlainText(), #generation
        'character_negative_prompt': self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_textbox.toPlainText(), #generation
        'character_static_positive_prompt': self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_static_textbox.toPlainText(),
        'character_static_negative_prompt': self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_static_textbox.toPlainText(),
        'character_coordinate_button': button_id, #save/load
        'character_coordinate_mode': coordinate_mode,
        'character_coordinate_markers_visible': coordinate_tab.show_markers_button.isChecked(),
        'character_can_randomize_position': coordinate_tab.can_randomize_checkbox.isChecked(),
        'character_swap_prompts': coordinate_tab.swap_prompts_checkbox.isChecked(),
        'character_auto_randomize_enabled': coordinate_tab.auto_randomize_button.isChecked(),
        'character_auto_randomize_frequency': coordinate_tab.auto_randomize_frequency_spinbox.value(),
        'character_y_coordinate': y_coordinate, #generation
        'character_x_coordinate': x_coordinate, #generation
        'character_positive_quick_weights': positive_quick_weights, #generation
        'character_negative_quick_weights': negative_quick_weights, #generation
        'character_preset_positive': self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_character_textbox.toPlainText(),
        'character_preset_negative': self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_character_textbox.toPlainText(),
        'character_preset_global_positive': self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_global_textbox.toPlainText(),
        'character_preset_global_negative': self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_global_textbox.toPlainText(),
        'character_outfit_preset_positive': self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.toPlainText(),
        'character_outfit_preset_negative': self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.toPlainText(),
        'most_recent_outfit': self.sub_notebook.character_sub_tab_5.outfit_combo.currentText(),
        'character_outfit_role_preset': self.sub_notebook.character_sub_tab_5.get_selected_outfit_role(),
        'character_outfit_modifier_preset': self.sub_notebook.character_sub_tab_5.get_selected_outfit_modifier(),
        'character_outfit_modifier_presets': self.sub_notebook.character_sub_tab_5.get_selected_outfit_modifiers(),
        'character_outfit_suppressed_slots': self.sub_notebook.character_sub_tab_5.get_suppressed_outfit_slots(),
        'character_reference_path': active_reference,
        'character_reference_enabled': self.sub_notebook.character_sub_tab_3.enable_reference_checkbox.isChecked(),
        'character_reference_style_aware': styleaware,
        'character_reference_fidelity': overall_fidelity,
        'character_reference_strength': reference_strength,
        'character_tag_associations': self.property('tag_associations') if self.current_character != 'None' else [],
        'character_labels': self.property('character_labels') if self.current_character != 'None' else [],
        'chance_tag': self.property('chance_tag') if self.current_character != 'None' else [],
        'character_outfit_removals': self.property('character_outfit_removals') if self.current_character != 'None' else [],
        'character_global_tag_association_enabled': self.sub_notebook.character_sub_tab_4.global_tag_association_button.isChecked(),
        'character_disable_associations': self.sub_notebook.character_sub_tab_4.disable_associations_button.isChecked(),
        'character_randomize_quick_weights': self.sub_notebook.character_sub_tab_4.randomize_quick_weights_button.isChecked(),
        'character_quick_weights_positive_only': self.sub_notebook.character_sub_tab_4.quick_weights_positive_only_button.isChecked(),
        'boys_to_girls': self.sub_notebook.character_sub_tab_4.boys_to_girls_button.isChecked(),
        'girls_to_boys': self.sub_notebook.character_sub_tab_4.girls_to_boys_button.isChecked(),
        'use_default_expression': self.sub_notebook.character_sub_tab_4.use_default_expression_button.isChecked(),
        'character_can_scramble': self.sub_notebook.character_sub_tab_4.can_scramble_button.isChecked(),
        'auto_advance_characters': self.sub_notebook.character_sub_tab_4.auto_advance_characters_checkbox.isChecked(),
        'auto_random_characters': self.sub_notebook.character_sub_tab_4.auto_random_characters_checkbox.isChecked(),
        'auto_advance_character_frequency': self.sub_notebook.character_sub_tab_4.auto_advance_character_frequency_spinbox.value(),
        'auto_advance_character_label1': self.sub_notebook.character_sub_tab_4.auto_advance_character_label1_combo.currentText(),
        'label1_mode': self.sub_notebook.character_sub_tab_4.label1_mode,
        'auto_advance_character_label2': self.sub_notebook.character_sub_tab_4.auto_advance_character_label2_combo.currentText(),
        'label2_mode': self.sub_notebook.character_sub_tab_4.label2_mode,
        'auto_advance_character_label3': self.sub_notebook.character_sub_tab_4.auto_advance_character_label3_combo.currentText(),
        'label3_mode': self.sub_notebook.character_sub_tab_4.label3_mode,
        'character_default_expression': self.get_character_default_expression() if self.current_character != 'None' else []
        }
        
    def import_state(self, loaded, import_filters=True):
        loaded_character = loaded['character']

        coordinate_tab = self.sub_notebook.character_sub_tab_2
        coordinate_tab.apply_model_type()
        saved_id = loaded.get('character_coordinate_button', 0)
        coordinate_mode = loaded.get('character_coordinate_mode', 'auto')
        coordinate_tab.set_coordinate_mode(coordinate_mode)
        coordinate_tab.show_markers_button.setChecked(
            loaded.get('character_coordinate_markers_visible', True)
        )
        coordinate_tab.can_randomize_checkbox.setChecked(
            loaded.get('character_can_randomize_position', False)
        )
        coordinate_tab.swap_prompts_checkbox.setChecked(
            loaded.get('character_swap_prompts', True)
        )
        coordinate_tab.auto_randomize_button.setChecked(
            loaded.get('character_auto_randomize_enabled', False)
        )
        coordinate_tab.auto_randomize_frequency_spinbox.setValue(
            loaded.get('character_auto_randomize_frequency', 1)
        )

        if isinstance(saved_id, int) and saved_id not in (-1, 0):
            x_coordinate, y_coordinate = coordinate_tab.button_id_to_coordinates(saved_id)
            coordinate_tab.set_selected_coordinates(x_coordinate, y_coordinate)
        else:
            x_coordinate = loaded.get('character_x_coordinate', 0.0)
            y_coordinate = loaded.get('character_y_coordinate', 0.0)
            coordinate_tab.set_selected_coordinates(x_coordinate, y_coordinate)

        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_textbox.setText(loaded['character_positive_prompt'])
        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_textbox.setText(loaded['character_negative_prompt'])
        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_static_textbox.setText(
            loaded.get('character_static_positive_prompt', '')
        )
        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_static_textbox.setText(
            loaded.get('character_static_negative_prompt', '')
        )

        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_character_textbox.setText(loaded['character_preset_positive'])
        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_character_textbox.setText(loaded['character_preset_negative'])

        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_global_textbox.setText(loaded['character_preset_global_positive'])
        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_global_textbox.setText(loaded['character_preset_global_negative'])

        self.sub_notebook.character_sub_tab_5.set_selected_outfit_role(
            loaded.get('character_outfit_role_preset', 'None')
        )
        self.sub_notebook.character_sub_tab_5.set_selected_outfit_modifier(
            loaded.get('character_outfit_modifier_presets', loaded.get('character_outfit_modifier_preset', ''))
        )
        self.sub_notebook.character_sub_tab_5.set_suppressed_outfit_slots(
            loaded.get('character_outfit_suppressed_slots', [])
        )

        self.sub_notebook.character_sub_tab_5.outfit_combo.setCurrentText(loaded['most_recent_outfit'])

        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.setText(loaded['character_outfit_preset_positive'])
        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.setText(loaded['character_outfit_preset_negative'])

        # Apply saved quick weight values to the spinners created by the character selection above.
        remaining_positive, remaining_negative = (
            self.sub_notebook.character_sub_tab_1.quick_weights_tab.apply_saved_values(
                _quick_weight_lookup(loaded.get('character_positive_quick_weights')),
                _quick_weight_lookup(loaded.get('character_negative_quick_weights')),
            )
        )
        if remaining_positive:
            prompt_tab = self.sub_notebook.character_sub_tab_1.prompt_tab
            prompt_tab.positive_prompt_textbox.setText(
                _append_unmatched_quick_weights(
                    prompt_tab.positive_prompt_textbox.toPlainText(),
                    remaining_positive,
                )
            )
        if remaining_negative:
            prompt_tab = self.sub_notebook.character_sub_tab_1.prompt_tab
            prompt_tab.negative_prompt_textbox.setText(
                _append_unmatched_quick_weights(
                    prompt_tab.negative_prompt_textbox.toPlainText(),
                    remaining_negative,
                )
            )

        reference_tab = self.sub_notebook.character_sub_tab_3
        reference_tab.enable_reference_checkbox.setChecked(
            loaded.get('character_reference_enabled', False)
        )
        reference_tab.style_aware_checkbox.setChecked(
            loaded.get('character_reference_style_aware', 'character') == 'character&style'
        )
        reference_tab.fidelity_spinner.setValue(
            1.0 - float(loaded.get('character_reference_fidelity', 0.0))
        )
        reference_tab.refstrength_spinner.setValue(
            loaded.get('character_reference_strength', 0.0)
        )
        selected_reference = loaded.get('character_reference_path')
        for button in reference_tab.reference_button_group.buttons():
            button.setChecked(
                selected_reference is not None
                and button.property('image_path') == selected_reference
            )

        self.sub_notebook.character_sub_tab_4.import_state(loaded, import_filters=import_filters)

    def get_character_default_expression(self):
        """Get the default_expression list for the current character from their JSON file."""
        if self.current_character == 'None':
            return []
        
        for character in self.characters:
            if character.get("nameID") == self.current_character:
                return character.get("default_expression", [])
        return []

    def copy_quick_weights_to_other_characters(self):
        quick_tab = self.sub_notebook.character_sub_tab_1.quick_weights_tab
        values = {
            quick_tab._lock_key(spinner.property("tag"), spinner.property("negative")):
                spinner.value()
            for spinner in quick_tab.findChildren(QDoubleSpinBox)
        }
        copy_character_quick_weight_values(self.current_character, values)

    def on_quick_weights_changed(self, character_name, quick_weights_data, source_mode):
        if source_mode == "universal":
            # Universal mode only edits a character-filtered subset, so merge
            # updates into the full universal list to avoid deleting unrelated entries.
            full_universal_quick_weights = get_universal_quick_weights([])

            def weight_key(weight):
                return (
                    weight.get("tag"),
                    bool(weight.get("negative", False)),
                    float(weight.get("min", 0.0)),
                    float(weight.get("max", 0.0)),
                )

            incoming_by_key = {
                weight_key(weight): dict(weight)
                for weight in quick_weights_data
                if isinstance(weight, dict)
            }

            merged_universal_quick_weights = []
            replaced_keys = set()

            for existing_weight in full_universal_quick_weights:
                if not isinstance(existing_weight, dict):
                    continue

                key = weight_key(existing_weight)
                updated_weight = incoming_by_key.get(key)
                if updated_weight is not None:
                    merged_universal_quick_weights.append(updated_weight)
                    replaced_keys.add(key)
                else:
                    merged_universal_quick_weights.append(existing_weight)

            # Include any incoming entries that did not already exist in the file.
            for key, incoming_weight in incoming_by_key.items():
                if key not in replaced_keys:
                    merged_universal_quick_weights.append(incoming_weight)

            save_universal_quick_weights(merged_universal_quick_weights)
            return

        changed_character = None

        for character in self.characters:
            if character.get("nameID") == character_name:
                character["quick_weights"] = quick_weights_data
                changed_character = character
                break

        if not changed_character:
            return

        characters_file_path = CHARACTERS_DIR / f"{character_name}.json"
        with characters_file_path.open("w", encoding="utf-8") as f:
            json.dump(changed_character, f, indent=2, ensure_ascii=False)


    def on_outfit_preset_changed(self, new_outfit_name, ID):
        """Update the currently selected character's most recent outfit and save."""

        if ID != self.ID:
            return  # Not for this tab

        if self.current_character == "None":
            self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.clear()
            self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.clear()
            self.setProperty('character_outfit_removals', [])
            return
        else:
            for character in self.characters:  # <-- loop over the dicts
                if character.get("nameID") == self.current_character:
                    # Find the outfit details
                    outfit_details = next((outfit for outfit in character['outfits'] if outfit['name'] == new_outfit_name), None)
                    if outfit_details:
                        suppressed_slots = self.sub_notebook.character_sub_tab_5.get_suppressed_outfit_slots()
                        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.setText(compile_outfit_prompt(outfit_details, "positive", suppressed_slots))
                        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.setText(compile_outfit_prompt(outfit_details, "negative", suppressed_slots))
                        self.setProperty('character_outfit_removals', outfit_details.get('remove') or [])
                    else:
                        self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.clear()
                        self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.clear()
                        self.setProperty('character_outfit_removals', [])
                    break

        changed = False

        for character in self.characters:
            if character.get("nameID") == self.current_character:
                character["most_recent_outfit"] = new_outfit_name
                changed = True
                break

        if not changed:
            return

        characters_file_path = CHARACTERS_DIR / f"{self.current_character}.json"
        with characters_file_path.open("w", encoding="utf-8") as f:
            json.dump(character, f, indent=2, ensure_ascii=False)

    def on_outfit_slot_suppression_changed(self, ID):
        """Recompile the currently displayed outfit prompt after a slot suppression toggle."""

        if ID != self.ID or self.current_character == "None":
            return

        current_outfit_name = self.sub_notebook.character_sub_tab_5.outfit_combo.currentText()
        if not current_outfit_name or current_outfit_name == "None":
            return

        for character in self.characters:
            if character.get("nameID") == self.current_character:
                outfit_details = next((outfit for outfit in character['outfits'] if outfit['name'] == current_outfit_name), None)
                if outfit_details:
                    suppressed_slots = self.sub_notebook.character_sub_tab_5.get_suppressed_outfit_slots()
                    self.sub_notebook.character_sub_tab_1.prompt_tab.positive_prompt_outfit_textbox.setText(compile_outfit_prompt(outfit_details, "positive", suppressed_slots))
                    self.sub_notebook.character_sub_tab_1.prompt_tab.negative_prompt_outfit_textbox.setText(compile_outfit_prompt(outfit_details, "negative", suppressed_slots))
                break

    def on_outfit_role_toggled(self, selected_role, is_checked, ID):
        if ID != self.ID:
            return

        # Only auto-select when toggled on; toggling off leaves the current outfit unchanged.
        if not is_checked:
            return

        character = self._get_current_character_data()
        if character is None:
            return

        self._apply_outfit_selection_from_role(character, selected_role)

    def on_outfit_modifier_toggled(self, selected_modifier, is_checked, ID):
        if ID != self.ID:
            return

        character = self._get_current_character_data()
        if character is None:
            return

        selected_role = self.sub_notebook.character_sub_tab_5.get_selected_outfit_role()
        self._apply_outfit_selection_from_role(character, selected_role)


    def on_refresh_character_list(self):
        self.sub_notebook.character_sub_tab_4.reload_labels()
        self.refresh_mutators()
    
