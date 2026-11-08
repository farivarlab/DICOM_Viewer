from PySide6.QtWidgets import QDialog, QVBoxLayout, QComboBox, QCheckBox, QDialogButtonBox, QLabel


class ExportDialog(QDialog):
    def __init__(self, parent=None, volume=False, colorbar_visible=True, colorbar_available=True):
        super().__init__(parent)
        self._volume = volume
        self._colorbar_available = colorbar_available
        self.setWindowTitle("Export PNG")
        self.setMinimumWidth(410)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        description = QLabel("Export the full image with its current contrast, colormap, rotation, and flips." if not volume
                             else "Export the current 3D camera view as a PNG image.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.content = QComboBox()
        self.content.addItems(["Annotated — measurements, text and DICOM overlays", "Unannotated — image pixels only"])
        self.content.setVisible(not volume)
        layout.addWidget(self.content)
        self.information = QCheckBox("Include patient and acquisition information")
        self.information.setVisible(not volume)
        layout.addWidget(self.information)
        self.colorbar = QCheckBox("Include colorbar")
        self.colorbar.setChecked(colorbar_visible)
        layout.addWidget(self.colorbar)
        self.content.currentIndexChanged.connect(self.update_options)
        self.update_options()
        self.content.setToolTip("Text already burned into the image pixels remains in both export modes.")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def annotated(self):
        return not self._volume and self.content.currentIndex() == 0

    @property
    def include_information(self):
        return self.annotated and self.information.isChecked()

    def update_options(self, index=0):
        self.information.setEnabled(self.annotated)
        self.colorbar.setEnabled(self._colorbar_available and (self._volume or self.annotated))

    @property
    def include_colorbar(self):
        return self.colorbar.isEnabled() and self.colorbar.isChecked()
