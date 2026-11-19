from data.datahub import get_all_characters
from data.character_labels import label_values
from process.CompletionSignaler import completion_signaler  
from process.frequency import should_cycle_on_frequency
from signaling.cycle_character import cycle_character_signal
import random

class CharacterAutoCycleManager():

    def __init__(self, parent, current_character):
        self.parent = parent
        self.characters = get_all_characters()
        self.cycle_label1 = None
        self.cycle_label2 = None
        self.cycle_label3 = None
        self.base_character_list = []
        self.character_list = []
        self.current_index = 0
        self.new_list = False
        self.current_operation = None
        self.current_character = current_character
        self.set_cycled = False

        completion_signaler.loop_start_signal.connect(self.on_loop_start)
        completion_signaler.set_start_signal.connect(lambda: setattr(self, 'set_cycled', True))

    def on_loop_start(self, action_type: str):
        if action_type == "Generate":
            self.check_operate_cycle()

    def check_operate_cycle(self):
        tab4 = self.parent.sub_notebook.character_sub_tab_4

        # Re-evaluate operation every loop so unchecking a box stops cycling immediately.
        self.current_operation = None
        if tab4.auto_advance_characters_checkbox.isChecked():
            self.current_operation = "auto_cycle"

        elif tab4.auto_random_characters_checkbox.isChecked():
            self.current_operation = "auto_random"

        if self.current_operation is None:
            self.cycle_label1 = None
            self.cycle_label2 = None
            self.cycle_label3 = None
            self.character_list = []
            self.current_index = 0
            self.new_list = False
            return

            
        if self.current_operation == "auto_random" or self.current_operation == "auto_cycle":
        
            self.selected_cycle_label1 = tab4.auto_advance_character_label1_combo.currentText()
            self.selected_cycle_label2 = tab4.auto_advance_character_label2_combo.currentText()
            self.selected_cycle_label3 = tab4.auto_advance_character_label3_combo.currentText()
            self.frequency = tab4.auto_advance_character_frequency_spinbox.value()

            if (self.cycle_label1 != self.selected_cycle_label1 or
                self.cycle_label2 != self.selected_cycle_label2 or
                self.cycle_label3 != self.selected_cycle_label3 or
                self.cycle_label1_mode != getattr(tab4, 'label1_mode', 'include') or
                self.cycle_label2_mode != getattr(tab4, 'label2_mode', 'include') or
                self.cycle_label3_mode != getattr(tab4, 'label3_mode', 'include')):

                self.cycle_label1 = self.selected_cycle_label1
                self.cycle_label2 = self.selected_cycle_label2
                self.cycle_label3 = self.selected_cycle_label3
                self.cycle_label1_mode = tab4.label1_mode
                self.cycle_label2_mode = tab4.label2_mode
                self.cycle_label3_mode = tab4.label3_mode
                self.character_list = []
                self.current_index = -1
                self.build_list()

            # When a new auto-cycle list is started, immediately advance once so
            # the first generated image uses the cycle pool instead of the currently selected character.
            # (Only applies to the N-generation cadence; on-set mode still waits for a real set completion.)
            generation_number = self.parent.window().total_loops + 1
            if self.frequency > 0:
                should_fire = self.new_list or should_cycle_on_frequency(self.frequency, generation_number, self.set_cycled)
            else:
                should_fire = should_cycle_on_frequency(self.frequency, generation_number, self.set_cycled)

            if should_fire:
                if self.current_operation == "auto_cycle":
                    if self.new_list:
                        self.current_index = 0
                        self.new_list = False
                    else:
                        self.current_index = (self.current_index + 1) % len(self.character_list)

                    cycle_character_signal.character_cycle_signal.emit(
                        self.character_list[self.current_index],
                        self.parent.ID
                    )

                elif self.current_operation == "auto_random":
                    selected_character = random.choice(self.character_list)
                    cycle_character_signal.character_cycle_signal.emit(
                        selected_character,
                        self.parent.ID
                    )

                if self.frequency <= 0:
                    self.set_cycled = False

        else:
            self.cycle_label1 = None
            self.cycle_label2 = None
            self.cycle_label3 = None
            self.character_list = []
            self.current_index = 0
            self.new_list = False
            self.current_operation = None
        

    def build_list(self):
        self.new_list = True
        self.character_list = []

        source_names = self.base_character_list if self.base_character_list else [c.get("nameID") for c in self.characters]

        for name in source_names:
            character = next((c for c in self.characters if c.get("nameID") == name), None)
            if character is None:
                continue

            labels = label_values(character.get("labels", []))
            if self.matches_labels(labels):
                self.character_list.append(character.get("nameID"))

        # If filtering produced no matches, keep all from source to avoid empty cycle.
        if not self.character_list:
            self.character_list = list(source_names)


    def matches_labels(self, labels):
        conditions = []
        if self.cycle_label1 != 'None':
            if self.cycle_label1_mode == "include":
                conditions.append(self.cycle_label1 in labels)
            else:
                conditions.append(self.cycle_label1 not in labels)
        if self.cycle_label2 != 'None':
            if self.cycle_label2_mode == "include":
                conditions.append(self.cycle_label2 in labels)
            else:
                conditions.append(self.cycle_label2 not in labels)
        if self.cycle_label3 != 'None':
            if self.cycle_label3_mode == "include":
                conditions.append(self.cycle_label3 in labels)
            else:
                conditions.append(self.cycle_label3 not in labels)
        # All conditions must be true (AND)
        return all(conditions)



        

        
