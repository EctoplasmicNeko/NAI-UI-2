from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QGridLayout, QFrame, QComboBox
from data.datahub import get_data

class ImageGenerateSizesTab(QFrame):


    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("image_generate_sizes_tab")
        self.build_image_generate_sizes_tab()
        self.update_size_properties()

    def build_image_generate_sizes_tab(self):
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

        self.sizes_comboxbox = QComboBox(self)
        self.sizes_comboxbox.currentIndexChanged.connect(self.update_size_properties)
        self.grid.addWidget(self.sizes_comboxbox, 0, 0)
        self.sizes = []
        self.size_list = []
        self.heights_list = []
        self.width_list = []
        self.reload_sizes()

    def reload_sizes(self, sizes=None):
        previous_index = self.sizes_comboxbox.currentIndex()
        previous_text = self.sizes_comboxbox.currentText()
        previous_height = self.sizes_comboxbox.property('image_height')
        previous_width = self.sizes_comboxbox.property('image_width')
        previous_name = None
        if previous_index > 0 and previous_index - 1 < len(self.sizes):
            previous_name = str(self.sizes[previous_index - 1].get('name', ''))

        custom_height = self.sizes_comboxbox.property('custom_height')
        custom_width = self.sizes_comboxbox.property('custom_width')
        if previous_index == 0:
            custom_height = previous_height
            custom_width = previous_width

        source_sizes = get_data("sizes", []) if sizes is None else sizes
        self.sizes = list(source_sizes or [])
        self.size_list = [f'{size["name"]} {size["image_height"]} x {size["image_width"]}' for size in self.sizes]
        custom_label = 'Custom Size'
        if custom_height is not None and custom_width is not None:
            custom_label = f'Custom Size {custom_height} x {custom_width}'
        self.size_list.insert(0, custom_label)
        self.heights_list = [custom_height] + [size['image_height'] for size in self.sizes]
        self.width_list = [custom_width] + [size['image_width'] for size in self.sizes]

        blocker = QSignalBlocker(self.sizes_comboxbox)
        self.sizes_comboxbox.clear()
        self.sizes_comboxbox.addItems(self.size_list)

        selected_index = self.sizes_comboxbox.findText(previous_text)
        if selected_index < 0 and previous_name:
            selected_index = next(
                (
                    index
                    for index, size in enumerate(self.sizes, start=1)
                    if str(size.get('name', '')) == previous_name
                ),
                -1,
            )
        if selected_index < 0 and previous_height is not None and previous_width is not None:
            selected_index = next(
                (
                    index
                    for index, size in enumerate(self.sizes, start=1)
                    if int(size['image_height']) == int(previous_height)
                    and int(size['image_width']) == int(previous_width)
                ),
                -1,
            )
        if selected_index < 0:
            selected_index = 0
            if previous_height is not None and previous_width is not None:
                self.heights_list[0] = previous_height
                self.width_list[0] = previous_width
                self.sizes_comboxbox.setItemText(
                    0,
                    f'Custom Size {previous_height} x {previous_width}',
                )

        self.sizes_comboxbox.setCurrentIndex(selected_index)
        del blocker
        self.update_size_properties()

    def update_size_properties(self):
        current_index = self.sizes_comboxbox.currentIndex()
        if current_index < 0:
            return
        self.sizes_comboxbox.setProperty('image_height', self.heights_list[current_index])
        self.sizes_comboxbox.setProperty('image_width', self.width_list[current_index])

