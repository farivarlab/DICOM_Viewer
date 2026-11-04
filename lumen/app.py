from __future__ import annotations

import argparse
from pathlib import Path
import sys
import traceback
import threading
import time

import numpy as np
from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, Signal, QTimer, QSize, QUrl
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence, QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QToolBar, QComboBox, QDoubleSpinBox, QSpinBox,
    QSlider, QLineEdit, QSplitter, QStackedWidget, QDockWidget, QToolButton,
    QFileDialog, QMessageBox, QCheckBox, QFormLayout, QScrollArea, QDialog,
)

from . import __version__
from .colors import STOPS
from .importer import import_paths
from .icons import icon, ACTION_ICONS
from .model import ImageVolume, load_series, demo_volume
from .slice_view import SliceView
from .theme import STYLE
from .volume_view import VolumeView
from .browser import CaseBrowser, Target
from .metadata import MetadataPane
from .export_dialog import ExportDialog
from .model import functional

PRESETS = {"Soft tissue": (400, 40), "Lung": (1500, -600), "Bone": (2000, 400),
           "Brain": (80, 40), "Abdomen": (350, 50), "Angiography": (700, 200)}


class JobSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    cancelled = Signal()


class JobCancelled(Exception):
    pass


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = JobSignals()
        self.cancel_event = threading.Event()
        self.last_progress = 0.

    def progress(self, message):
        if self.cancel_event.is_set():
            raise JobCancelled()
        now = time.monotonic()
        if now - self.last_progress >= .08:
            self.signals.progress.emit(message)
            self.last_progress = now

    @staticmethod
    def discard(result):
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], list):
            for temporary in result[1]:
                if hasattr(temporary, "cleanup"):
                    temporary.cleanup()

    def run(self):
        try:
            result = self.function(self.progress)
            if self.cancel_event.is_set():
                self.discard(result)
                raise JobCancelled()
            self.signals.finished.emit(result)
        except JobCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            traceback.print_exc()
            self.signals.failed.emit(str(exc))


def label(text, name=None, wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lumen · DICOM Viewer")
        self.resize(1520, 960)
        self.setMinimumSize(1120, 740)
        self.setAcceptDrops(True)
        self.data: ImageVolume | None = None
        self.series = []
        self.temporaries = []
        self.busy = False
        self._closing = False
        self._plane_cache = {}
        self._inversion_override = None
        self.cursor = [0, 0, 0]
        self.source_index = 0
        self.mode = "2D stack"
        self.tool = "Window"
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.cine_timer = QTimer(self)
        self.cine_timer.timeout.connect(self.cine_step)
        self._create_actions()
        self._create_toolbar()
        self._create_workspace()
        self._create_metadata()
        self._create_menu()
        self.statusBar().showMessage("Ready · Open a DICOM folder, files, DICOMDIR, or ZIP")
        self.status_hint = label("LOCAL FILES  ·  RESEARCH VIEWER", "eyebrow")
        self.statusBar().addPermanentWidget(self.status_hint)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(icon("close"))
        self.cancel_button.clicked.connect(self.cancel_job)
        self.cancel_button.hide()
        self.statusBar().addPermanentWidget(self.cancel_button)
        self._set_data_enabled(False)

    def action(self, text, callback, shortcut=None, checkable=False):
        action = QAction(text, self)
        action.setIcon(icon(ACTION_ICONS[text]))
        action.setCheckable(checkable)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setToolTip(f"{text} ({shortcut})" if shortcut else text)
        action.triggered.connect(callback)
        return action

    def _create_actions(self):
        self.open_action = self.action("Open files…", self.open_files, "Ctrl+O")
        self.folder_action = self.action("Open folder…", self.open_folder, "Ctrl+Shift+O")
        self.demo_action = self.action("Load demo", self.load_demo)
        self.export_action = self.action("Save image…", self.export_image, "Ctrl+S")
        self.export_action.setText("Export PNG…")
        self.export_action.setToolTip("Export annotated or unannotated PNG (Ctrl+S)")
        self.copy_action = self.action("Copy image", self.copy_image, "Ctrl+C")
        self.tags_action = self.action("DICOM tags", self.show_tags, "Ctrl+I", True)
        self.fit_action = self.action("Fit", self.fit_active, "F")
        self.reset_action = self.action("Reset", self.reset_views, "R")
        self.rotate_action = self.action("Rotate 90°", lambda: self.active_view.rotate(), "]")
        self.flip_h_action = self.action("Flip H", lambda: self.active_view.flip(True), "H")
        self.flip_v_action = self.action("Flip V", lambda: self.active_view.flip(False), "V")
        self.clear_action = self.action("Clear marks", self.clear_marks)
        self.cine_action = self.action("Play cine", self.toggle_cine, "Space", True)
        self.invert_action = self.action("Invert", self.invert, "I", True)
        self.fullscreen_action = self.action("Full screen", self.fullscreen, "F11")
        self.tool_group = QActionGroup(self)
        self.tools = {}
        for name, shortcut in (("Window", "W"), ("Pan", "P"), ("Zoom", "Z"), ("Scroll", "S"),
                               ("Crosshair", "C"), ("Length", "D"), ("Rectangle", None),
                               ("Ellipse", "E"), ("Angle", "A"), ("Arrow", None), ("Text", "T")):
            action = self.action(name, lambda checked, n=name: self.select_tool(n), shortcut, True)
            self.tool_group.addAction(action)
            self.tools[name] = action
        self.tools["Window"].setChecked(True)
        self.data_actions = [self.export_action, self.copy_action, self.tags_action, self.fit_action,
            self.reset_action, self.rotate_action, self.flip_h_action, self.flip_v_action,
            self.clear_action, self.cine_action, self.invert_action, *self.tools.values()]

    def _create_menu(self):
        file_menu = self.menuBar().addMenu("File")
        for action in (self.open_action, self.folder_action, self.demo_action, self.export_action, self.copy_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.action("Exit", self.close, "Alt+F4"))
        view_menu = self.menuBar().addMenu("View")
        for action in (self.fit_action, self.reset_action, self.invert_action, self.rotate_action,
                       self.flip_h_action, self.flip_v_action, self.tags_action, self.fullscreen_action):
            view_menu.addAction(action)
        tools = self.menuBar().addMenu("Tools")
        tools.addActions(list(self.tools.values()))
        tools.addAction(self.clear_action)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.action("Controls", self.show_help, "F1"))
        help_menu.addAction(self.action("Third-party notices", self.show_notices))
        help_menu.addAction(self.action("About Lumen", lambda: QMessageBox.about(self, "Lumen",
            f"Lumen {__version__}\nOffline DICOM viewer · Python / Qt / VTK\n\n"
            "Research and education software. Not validated for diagnostic use.\n"
            "Input DICOM files are opened read only.\nNo networking, accounts, or uploads.")))

    def _create_toolbar(self):
        main = QToolBar("Workspace", self)
        main.setMovable(False)
        main.setIconSize(QSize(19, 19))
        main.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(main)
        main.addAction(self.open_action)
        main.addAction(self.folder_action)
        main.addSeparator()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["2D stack", "MPR", "MPR + 3D", "3D volume"])
        self.mode_combo.setCurrentText(self.mode)
        self.mode_combo.setMinimumWidth(130)
        self.mode_combo.setToolTip("View layout")
        self.mode_combo.setAccessibleName("View layout")
        self.mode_combo.currentTextChanged.connect(self.change_mode)
        main.addWidget(self.mode_combo)
        main.addSeparator()
        for action in (self.fit_action, self.reset_action, self.rotate_action, self.flip_h_action,
                       self.flip_v_action, self.invert_action):
            main.addAction(action)
            main.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        spacer = QWidget()
        spacer.setStyleSheet("background: transparent;")
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        main.addWidget(spacer)
        main.addAction(self.tags_action)
        main.addAction(self.export_action)
        self.addToolBarBreak()
        self.tool_bar = QToolBar("Image tools", self)
        self.tool_bar.setMovable(False)
        self.tool_bar.setIconSize(QSize(22, 22))
        self.tool_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(self.tool_bar)
        for name, action in self.tools.items():
            if name in ("Crosshair", "Arrow"):
                self.tool_bar.addSeparator()
            self.tool_bar.addAction(action)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.clear_action)

    def _create_workspace(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)
        sidebar = QWidget()
        sidebar.setMinimumWidth(265)
        sidebar.setMaximumWidth(480)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 12, 12, 12)
        side.addWidget(label("lumen", "brand"))
        side.addWidget(label("DICOM WORKSPACE", "eyebrow"))
        side.addSpacing(6)
        self.open_button = QPushButton("Open a study")
        self.open_button.setIcon(icon("folder", color="#ffffff"))
        self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self.open_folder)
        side.addWidget(self.open_button)
        side.addWidget(label("PATIENTS / CASES / FILES", "section"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search patients, cases, files…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_series)
        side.addWidget(self.search)
        self.browser = CaseBrowser()
        self.browser.requested.connect(self.open_target)
        side.addWidget(self.browser, 1)
        self.acquisition = label("No series loaded", "muted", True)
        side.addWidget(self.acquisition)
        splitter.addWidget(sidebar)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.study_title = label("Image workspace")
        self.study_title.setContentsMargins(18, 13, 18, 13)
        center_layout.addWidget(self.study_title)
        self.pages = QStackedWidget()
        center_layout.addWidget(self.pages, 1)
        welcome = QWidget()
        welcome.setStyleSheet("background: #f5f7f9;")
        wl = QVBoxLayout(welcome)
        wl.setContentsMargins(70, 60, 70, 60)
        wl.addStretch()
        wl.addWidget(label("A CLOSER LOOK", "eyebrow"))
        wl.addSpacing(15)
        wl.addWidget(label("Your images.\nA clear perspective.", "welcomeTitle"))
        wl.addSpacing(15)
        wl.addWidget(label("Open a DICOM study to explore slices, linked multiplanar\nreconstructions, and interactive 3D volumes.", "muted", True))
        wl.addSpacing(25)
        start = QPushButton("Open DICOM folder")
        start.setIcon(icon("folder", color="#ffffff"))
        start.setObjectName("primary")
        start.setMaximumWidth(210)
        start.clicked.connect(self.open_folder)
        wl.addWidget(start)
        sample = QPushButton("Try the generated phantom")
        sample.setIcon(icon("demo"))
        sample.setMaximumWidth(210)
        sample.clicked.connect(self.load_demo)
        wl.addWidget(sample)
        wl.addSpacing(28)
        wl.addWidget(label("OR DROP FILES, A FOLDER, OR A ZIP HERE", "eyebrow"))
        wl.addStretch()
        self.pages.addWidget(welcome)
        self.canvas = QWidget()
        self.grid = QGridLayout(self.canvas)
        self.grid.setContentsMargins(3, 3, 3, 3)
        self.grid.setSpacing(3)
        self.views = {name: SliceView(name) for name in ("Source", "Axial", "Coronal", "Sagittal")}
        for view in self.views.values():
            self.grid.addWidget(view)
            view.hide()
            view.activated.connect(self.activate_view)
            view.scrolled.connect(self.scroll_slice)
            view.window_changed.connect(self.change_window)
            view.cursor_changed.connect(self.move_crosshair)
            view.probed.connect(self.statusBar().showMessage)
        self.active_view = self.views["Source"]
        self.active_view.title = "2D image"
        self.active_view.active = True
        self.volume_view = VolumeView()
        self.grid.addWidget(self.volume_view)
        self.volume_view.hide()
        self.pages.addWidget(self.canvas)
        self.navigation = QWidget()
        nav = QHBoxLayout(self.navigation)
        nav.setContentsMargins(12, 8, 12, 10)
        cine = QToolButton()
        cine.setDefaultAction(self.cine_action)
        cine.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        nav.addWidget(cine)
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(12)
        self.fps.setSuffix(" fps")
        self.fps.valueChanged.connect(lambda n: self.cine_timer.setInterval(round(1000 / n)))
        nav.addWidget(self.fps)
        self.previous_button = QToolButton()
        self.previous_button.setIcon(icon("previous"))
        self.previous_button.setToolTip("Previous image (Up)")
        self.previous_button.clicked.connect(lambda: self.scroll_slice(self.active_view.plane, -1))
        nav.addWidget(self.previous_button)
        self.slice_slider = QSlider(Qt.Orientation.Horizontal)
        self.slice_slider.valueChanged.connect(self.slider_changed)
        nav.addWidget(self.slice_slider, 1)
        self.next_button = QToolButton()
        self.next_button.setIcon(icon("next"))
        self.next_button.setToolTip("Next image (Down)")
        self.next_button.clicked.connect(lambda: self.scroll_slice(self.active_view.plane, 1))
        nav.addWidget(self.next_button)
        self.slice_spin = QSpinBox()
        self.slice_spin.setRange(1, 1)
        self.slice_spin.setKeyboardTracking(False)
        self.slice_spin.setToolTip("Jump to image number")
        self.slice_spin.valueChanged.connect(lambda value: self.slider_changed(value - 1))
        nav.addWidget(self.slice_spin)
        self.slice_label = label("—", "muted")
        self.slice_label.setMinimumWidth(44)
        nav.addWidget(self.slice_label)
        center_layout.addWidget(self.navigation)
        splitter.addWidget(center)

        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setMinimumWidth(235)
        inspector_scroll.setMaximumWidth(300)
        inspector = QWidget()
        inspector_scroll.setWidget(inspector)
        settings = QVBoxLayout(inspector)
        settings.setContentsMargins(18, 12, 18, 18)
        self.display_controls = QWidget()
        display_settings = QVBoxLayout(self.display_controls)
        display_settings.setContentsMargins(0, 0, 0, 0)
        display_settings.addWidget(label("DISPLAY", "section"))
        form = QFormLayout()
        form.setSpacing(9)
        self.preset = QComboBox()
        self.preset.addItems(["DICOM default", "Auto contrast", *PRESETS, "Custom"])
        self.preset.currentTextChanged.connect(self.apply_preset)
        form.addRow("Preset", self.preset)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1, 1e9)
        self.width_spin.setDecimals(1)
        self.width_spin.setValue(400)
        self.level_spin = QDoubleSpinBox()
        self.level_spin.setRange(-1e9, 1e9)
        self.level_spin.setDecimals(1)
        self.level_spin.setValue(40)
        self.width_spin.valueChanged.connect(lambda v: self.change_window(v, self.level_spin.value()))
        self.level_spin.valueChanged.connect(lambda v: self.change_window(self.width_spin.value(), v))
        form.addRow("Width", self.width_spin)
        form.addRow("Level", self.level_spin)
        self.cmap = QComboBox()
        self.cmap.addItems(list(STOPS))
        self.cmap.currentTextChanged.connect(lambda _: self.refresh_views())
        form.addRow("Colormap", self.cmap)
        display_settings.addLayout(form)
        self.overlays = QCheckBox("DICOM information")
        self.overlays.setChecked(True)
        self.overlays.toggled.connect(self.update_overlays)
        display_settings.addWidget(self.overlays)
        self.embedded_overlays = QCheckBox("Embedded DICOM overlays")
        self.embedded_overlays.setChecked(True)
        self.embedded_overlays.toggled.connect(self.update_overlays)
        display_settings.addWidget(self.embedded_overlays)
        settings.addWidget(self.display_controls)
        self.mpr_controls = QWidget()
        mpr_settings = QVBoxLayout(self.mpr_controls)
        mpr_settings.setContentsMargins(0, 0, 0, 0)
        self.crosshairs = QCheckBox("Linked crosshairs")
        self.crosshairs.setChecked(True)
        self.crosshairs.toggled.connect(self.update_overlays)
        mpr_settings.addWidget(self.crosshairs)
        mpr_settings.addWidget(label("MPR RECONSTRUCTION", "section"))
        mpr_form = QFormLayout()
        self.slab_mode = QComboBox()
        self.slab_mode.addItems(["Slice", "MIP", "MinIP", "Average"])
        self.slab_mode.currentTextChanged.connect(lambda _: self.refresh_views())
        self.slab_mm = QDoubleSpinBox()
        self.slab_mm.setRange(.1, 150)
        self.slab_mm.setValue(10)
        self.slab_mm.setSuffix(" mm")
        self.slab_mm.valueChanged.connect(lambda _: self.refresh_views())
        mpr_form.addRow("Projection", self.slab_mode)
        mpr_form.addRow("Slab", self.slab_mm)
        mpr_settings.addLayout(mpr_form)
        self.position_label = label("LPS coordinates\n—", "muted", True)
        mpr_settings.addWidget(self.position_label)
        settings.addWidget(self.mpr_controls)
        self.mpr_controls.hide()
        self.volume_controls = QWidget()
        volume_settings = QVBoxLayout(self.volume_controls)
        volume_settings.setContentsMargins(0, 0, 0, 0)
        volume_settings.addWidget(label("3D VOLUME", "section"))
        volume_form = QFormLayout()
        self.volume_preset = QComboBox()
        self.volume_preset.addItems(["CT tissue", "CT bone", "CT lung", "Scalar"])
        self.volume_preset.currentTextChanged.connect(self.change_volume)
        self.volume_blend = QComboBox()
        self.volume_blend.addItems(["Composite", "MIP", "MinIP"])
        self.volume_blend.currentTextChanged.connect(self.change_volume)
        volume_form.addRow("Appearance", self.volume_preset)
        volume_form.addRow("Render", self.volume_blend)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(10, 300)
        self.opacity.setValue(100)
        self.opacity.valueChanged.connect(self.change_volume)
        volume_form.addRow("Opacity", self.opacity)
        self.crop = QSlider(Qt.Orientation.Horizontal)
        self.crop.setRange(0, 95)
        self.crop.valueChanged.connect(lambda value: self.volume_view.set_crop(value / 100))
        volume_form.addRow("Cutaway", self.crop)
        volume_settings.addLayout(volume_form)
        reset_3d = QPushButton("Reset 3D camera")
        reset_3d.setIcon(icon("camera"))
        reset_3d.clicked.connect(self.volume_view.reset_camera)
        volume_settings.addWidget(reset_3d)
        settings.addWidget(self.volume_controls)
        self.volume_controls.hide()
        self.control_hint = label("", "muted", True)
        settings.addSpacing(12)
        settings.addWidget(self.control_hint)
        help_button = QPushButton("Keyboard controls")
        help_button.setIcon(icon("help"))
        help_button.clicked.connect(self.show_help)
        settings.addWidget(help_button)
        settings.addStretch()
        settings.addWidget(label("Research & education\nNot validated for diagnosis", "muted", True))
        self.inspector = inspector
        splitter.addWidget(inspector_scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 950, 260])

    def _create_metadata(self):
        self.metadata_pane = MetadataPane()
        self.metadata_dock = QDockWidget("DICOM metadata", self)
        self.metadata_dock.setObjectName("metadataDock")
        self.metadata_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.metadata_dock.setWidget(self.metadata_pane)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.metadata_dock)
        self.metadata_dock.visibilityChanged.connect(self._metadata_visibility)
        self.metadata_dock.hide()

    def _metadata_visibility(self, visible):
        self.tags_action.setChecked(visible)
        if visible:
            self.update_metadata()

    def update_metadata(self):
        if self.data and self.metadata_dock.isVisible():
            ref = self.data.reference(self.source_index)
            caption = ref.path.name if ref.path else f"Image {self.source_index + 1}"
            if self.mode != "2D stack":
                caption = f"Source header · {caption}"
            self.metadata_pane.set_dataset(self.data.header(self.source_index), f"{caption} · frame {ref.frame + 1}")

    def _set_data_enabled(self, enabled):
        for action in self.data_actions:
            action.setEnabled(enabled)
        self.inspector.setEnabled(enabled)
        self.mode_combo.setEnabled(enabled)
        self.navigation.setEnabled(enabled)
        for view in self.views.values():
            view.setEnabled(enabled)
        self.volume_view.setEnabled(enabled)
        if enabled:
            self.update_control_state()

    def update_control_state(self):
        if not self.data:
            return
        is_2d = self.mode != "3D volume"
        scalar_2d = is_2d and not self.data.is_color
        self.tool_bar.setEnabled(is_2d)
        self.cine_action.setEnabled(is_2d and self.slice_slider.maximum() > 0)
        self.clear_action.setEnabled(is_2d)
        for action in (self.rotate_action, self.flip_h_action, self.flip_v_action):
            action.setEnabled(is_2d)
        self.invert_action.setEnabled(scalar_2d)
        for widget in (self.preset, self.width_spin, self.level_spin, self.cmap):
            widget.setEnabled(scalar_2d)
        units = self.data.frame_units(self.source_index) if self.mode == "2D stack" else self.data.units
        for i in range(self.preset.count()):
            if self.preset.itemText(i) in PRESETS:
                self.preset.model().item(i).setEnabled(units == "HU")
        for i in range(self.volume_preset.count()):
            self.volume_preset.model().item(i).setEnabled(self.volume_preset.itemText(i) == "Scalar" or self.data.units == "HU")
        self.opacity.setEnabled(self.volume_blend.currentText() == "Composite")
        for action in self.tools.values():
            action.setEnabled(is_2d)
        self.tools["Window"].setEnabled(scalar_2d)
        self.tools["Crosshair"].setEnabled(self.mode in ("MPR", "MPR + 3D"))
        self.slab_mm.setEnabled(self.slab_mode.currentText() != "Slice")
        for i in range(1, self.mode_combo.count()):
            self.mode_combo.model().item(i).setEnabled(self.data.mpr_available)
        self.overlays.setEnabled(is_2d)
        self.embedded_overlays.setEnabled(self.mode == "2D stack" and bool(self.data.overlay_layers(self.source_index)))

    def start_job(self, function, callback):
        if self.busy:
            return
        self.stop_cine()
        self.busy = True
        self._set_data_enabled(False)
        self.cancel_button.setText("Cancel")
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self.open_action.setEnabled(False)
        self.folder_action.setEnabled(False)
        self.demo_action.setEnabled(False)
        self.open_button.setEnabled(False)
        self.browser.setEnabled(False)
        self.job = Job(function)
        self.job.signals.progress.connect(self.statusBar().showMessage)
        self.job.signals.finished.connect(lambda result: self.finish_job(callback, result))
        self.job.signals.failed.connect(self.fail_job)
        self.job.signals.cancelled.connect(self.job_cancelled)
        self.pool.start(self.job)

    def end_job(self):
        self.busy = False
        self.cancel_button.hide()
        for action in (self.open_action, self.folder_action, self.demo_action):
            action.setEnabled(True)
        for widget in (self.open_button, self.browser):
            widget.setEnabled(True)
        self._set_data_enabled(self.data is not None)
        if self._closing:
            QTimer.singleShot(0, self.close)

    def cancel_job(self):
        if self.busy:
            self.job.cancel_event.set()
            self.cancel_button.setText("Cancelling…")
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Cancelling the current operation…")

    def job_cancelled(self):
        self.end_job()
        self.restore_current_selection()
        self.statusBar().showMessage("Operation cancelled")

    def restore_current_selection(self):
        if self.data:
            self.browser.sync_image(self.source_index)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(self.mode)
        self.mode_combo.blockSignals(False)

    def finish_job(self, callback, result):
        self.end_job()
        if self._closing:
            Job.discard(result)
            return
        try:
            callback(result)
        except Exception as exc:
            traceback.print_exc()
            self.fail_job(str(exc))

    def fail_job(self, message):
        self.end_job()
        self.restore_current_selection()
        if self._closing:
            return
        self.statusBar().showMessage("Operation failed · the previous image is still open")
        QMessageBox.warning(self, "Unable to open images", message)

    def open_files(self):
        if self.busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Open DICOM files / DICOMDIR / ZIP", "",
                                              "All files (*);;DICOM (*.dcm *.dicom);;ZIP archives (*.zip)")
        if paths:
            self.open_paths(paths)

    def open_folder(self):
        if self.busy:
            return
        path = QFileDialog.getExistingDirectory(self, "Open DICOM study folder")
        if path:
            self.open_paths([path])

    def open_paths(self, paths):
        if not self.busy:
            self.start_job(lambda progress: import_paths(paths, progress), self.imported)

    def imported(self, result):
        scan, temporaries = result
        self.temporaries.extend(temporaries)
        if not scan.series:
            raise ValueError("No DICOM pixel images were found in the selected files.")
        existing = {s.uid: s for s in self.series}
        for series in scan.series:
            if series.uid in existing:
                target = existing[series.uid]
                target.paths = sorted(set(target.paths + series.paths))
                target.files.update(series.files)
                target.frames = sum(info.frames for info in target.files.values())
            else:
                self.series.append(series)
        self.populate_series()
        self.statusBar().showMessage(f"Indexed {len(scan.series)} series · skipped {scan.skipped} non-image/unreadable files")
        self.open_target(Target(scan.series[0].uid, "series"), force=True)

    def populate_series(self):
        self.browser.populate(self.series, self.data)
        self.filter_series(self.search.text())

    def filter_series(self, text):
        self.browser.filter(text)

    def open_target(self, target, force=False):
        if self.busy:
            return
        series = next((s for s in self.series if s.uid == target.uid), None)
        if series is None:
            return
        if self.data and self.data.series.uid == target.uid and not force:
            if target.kind != "series":
                self.mode_combo.setCurrentText("2D stack")
                path = self.data.path_aliases.get(target.path, target.path)
                index = self._frame_lookup.get((path, target.frame))
                if index is None:
                    self.statusBar().showMessage("This file is not part of the displayed image stack")
                    self.restore_current_selection()
                    return
                self.slider_changed(index)
            return
        self.start_job(lambda progress: demo_volume() if series.uid == "demo" else load_series(series, progress, reconstruct=False),
                       lambda data: self.set_data(data, target))

    def load_demo(self):
        if self.busy:
            return
        if not any(s.uid == "demo" for s in self.series):
            self.series.append(demo_volume().series)
            self.populate_series()
        self.open_target(Target("demo", "series"))
        if self.data and self.data.series.uid == "demo" and not self.busy:
            self.mode_combo.setCurrentText("2D stack")
            self.reset_views()

    def set_data(self, data, target=None):
        self.data = data
        self._plane_cache.clear()
        self._inversion_override = None
        self._frame_lookup = {(data.reference(i).path, data.reference(i).frame): i for i in range(len(data.source))}
        path = data.path_aliases.get(target.path, target.path) if target else None
        self.source_index = self._frame_lookup.get((path, target.frame), 0) if target and target.kind != "series" else 0
        self.browser.set_loaded(data)
        self.filter_series(self.search.text())
        self.cursor = [int(n // 2) for n in data.canonical.shape[::-1]] if data.mpr_ready else [0, 0, 0]
        for view in self.views.values():
            view.marks.clear()
            view.pending.clear()
            view._needs_fit = True
            view._render_key = None
            view._annotation_key = None
        for widget, value in ((self.width_spin, data.width), (self.level_spin, data.level)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(0)
        self.preset.blockSignals(False)
        self.invert_action.setChecked(data.inverted)
        self.volume_preset.setCurrentText("CT tissue" if data.units == "HU" else "Scalar")
        self.volume_view.clear_volume()
        self.study_title.setText(f"{data.series.patient}   /   {data.series.description}")
        nz, ny, nx = data.source.shape[:3]
        spacing = f"{data.spacing[0]:.2f} × {data.spacing[1]:.2f} mm" if data.calibrated else "Uncalibrated pixels"
        self.acquisition.setText(f"{data.series.modality} · {nx} × {ny} · {spacing}")
        self.acquisition.setToolTip(data.geometry_note)
        self._set_data_enabled(True)
        self.cine_action.setEnabled(len(data.source) > 1)
        self.tools["Crosshair"].setEnabled(data.mpr_available)
        if not data.mpr_ready and self.tool == "Crosshair":
            self.tools["Window"].setChecked(True)
            self.select_tool("Window")
        self.pages.setCurrentIndex(1)
        if self.mode_combo.currentText() != "2D stack":
            self.mode_combo.setCurrentText("2D stack")
        else:
            self.change_mode("2D stack")
        self.statusBar().showMessage(f"{nz:,} images loaded · use the wheel, arrow keys, or image number to browse")

    def change_mode(self, mode):
        if self.data is None:
            return
        if self.busy:
            return
        self.stop_cine()
        if mode != "2D stack" and self.data.mpr_available and not self.data.mpr_ready:
            data = self.data
            self.start_job(lambda progress: data.prepare_mpr(progress), lambda result: self.mpr_prepared(result, mode))
            return
        if mode != "2D stack" and not self.data.mpr_ready:
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentText("2D stack")
            self.mode_combo.blockSignals(False)
            self.statusBar().showMessage(self.data.geometry_note)
            mode = "2D stack"
        self.mode = mode
        self.display_controls.setVisible(mode != "3D volume")
        self.control_hint.setText("Drag: orbit · wheel: zoom\nMiddle drag: pan" if mode == "3D volume" else
            "Wheel: browse · Ctrl+wheel: zoom\nRight drag: contrast · middle drag: pan")
        self.mpr_controls.setVisible(mode in ("MPR", "MPR + 3D"))
        self.volume_controls.setVisible("3D" in mode)
        is_2d = mode != "3D volume"
        self.tool_bar.setEnabled(is_2d)
        for action in (self.rotate_action, self.flip_h_action, self.flip_v_action, self.invert_action):
            action.setEnabled(is_2d)
        for action in self.tools.values():
            action.setEnabled(is_2d)
        self.tools["Crosshair"].setEnabled(is_2d and self.data.mpr_ready and mode != "2D stack")
        for widget in (*self.views.values(), self.volume_view):
            self.grid.removeWidget(widget)
            widget.hide()
        for index in (0, 1):
            self.grid.setRowStretch(index, 0)
            self.grid.setColumnStretch(index, 0)
        names = ["Source"] if mode == "2D stack" else (["Axial", "Coronal", "Sagittal"] if mode != "3D volume" else [])
        positions = [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1)]
        for i, name in enumerate(names):
            view = self.views[name]
            self.grid.addWidget(view, *(positions[i] if mode != "MPR" or i < 2 else (1, 0, 1, 2)))
            view.show()
        if "3D" in mode:
            self.grid.addWidget(self.volume_view, *( (1, 1, 1, 1) if names else (0, 0, 1, 1)))
            self.volume_view.show()
            if getattr(self.volume_view, "_loaded_uid", None) != id(self.data):
                self.volume_view.set_volume(self.data)
                self.volume_view._loaded_uid = id(self.data)
            QTimer.singleShot(100, self.volume_view.render)
        self.grid.setRowStretch(0, 1)
        self.grid.setColumnStretch(0, 1)
        if len(names) > 1:
            self.grid.setRowStretch(1, 1)
            self.grid.setColumnStretch(1, 1)
        if self.tool == "Crosshair" and mode in ("2D stack", "3D volume"):
            self.tools["Window"].setChecked(True)
            self.select_tool("Window")
        self.navigation.setVisible(bool(names))
        self.activate_view(self.views[names[0]] if names else self.views["Axial"])
        self.refresh_views()
        self.update_control_state()
        QTimer.singleShot(0, self.fit_visible)

    def mpr_prepared(self, data, mode):
        self.cursor = [int(n // 2) for n in data.canonical.shape[::-1]]
        self.change_mode(mode)

    def activate_view(self, view):
        self.active_view.active = False
        self.active_view.viewport().update()
        self.active_view = view
        view.active = True
        view.viewport().update()
        self.update_navigation()

    def fit_visible(self):
        for view in self.views.values():
            if view.isVisible():
                view.fit_image()

    def fit_active(self):
        if self.mode == "3D volume":
            self.volume_view.reset_camera()
        else:
            self.active_view.fit_image()

    def refresh_views(self):
        data = self.data
        if data is None:
            return
        if self.mode == "2D stack" and self.preset.currentText() == "DICOM default":
            for widget, value in zip((self.width_spin, self.level_spin), data.frame_window(self.source_index)):
                widget.blockSignals(True)
                widget.setValue(value)
                widget.blockSignals(False)
        if self._inversion_override is None:
            self.invert_action.setChecked(data.frame_inverted(self.source_index) if self.mode == "2D stack" else data.inverted)
        width, level = self.width_spin.value(), self.level_spin.value()
        for name, view in self.views.items():
            if not view.isVisible():
                continue
            if name != "Source" and not data.mpr_ready:
                continue
            position = self.source_index if name == "Source" else self.cursor[{"Axial": 2, "Coronal": 1, "Sagittal": 0}[name]]
            plane_key = (id(data), position, self.slab_mode.currentText(), self.slab_mm.value())
            if name not in self._plane_cache or self._plane_cache[name][0] != plane_key:
                self._plane_cache[name] = (plane_key, data.plane(name, self.cursor, self.source_index,
                    self.slab_mode.currentText(), self.slab_mm.value()))
            image, spacing = self._plane_cache[name][1]
            crosshair, directions = None, None
            if name == "Source":
                index, total = self.source_index, len(data.source)
                header = data.header(index)
                ref = data.reference(index)
                orientation = functional(header, ref.frame, "PlaneOrientationSequence", "ImageOrientationPatient")
                if orientation is not None:
                    directions = (orientation[:3], orientation[3:])
            else:
                x, y, z = self.cursor
                nz, ny, nx = data.canonical.shape
                index, total = {"Axial": (z, nz), "Coronal": (y, ny), "Sagittal": (x, nx)}[name]
                crosshair = {"Axial": (x, y), "Coronal": (x, nz - 1 - z), "Sagittal": (y, nz - 1 - z)}[name]
                directions = {"Axial": ((1, 0, 0), (0, 1, 0)), "Coronal": ((1, 0, 0), (0, 0, -1)),
                              "Sagittal": ((0, 1, 0), (0, 0, -1))}[name]
            key = (name, index, self.slab_mode.currentText(), self.slab_mm.value()) if name != "Source" else (name, index)
            view.set_image(image, spacing, key, width, level, self.cmap.currentText(), self.invert_action.isChecked(),
                data.frame_calibrated(index) if name == "Source" else True,
                f"{index + 1} / {total}   ·   {self.slab_mode.currentText() if name != 'Source' else 'Reconstruction'}",
                crosshair, directions, data.frame_units(index) if name == "Source" else data.units)
            # Reconstructed planes do not represent one acquired instance.
            view.set_file_annotations(data.header(self.source_index) if name == "Source" else data.dataset,
                data.overlay_layers(self.source_index) if name == "Source" else (), reconstruction=name != "Source")
            if name == "Source":
                ref = data.reference(index)
                filename = ref.path.name if ref.path else "Demo image"
                view.subtitle = f"{index + 1} / {total} · {filename}" + (f" · frame {ref.frame + 1}" if ref.frame else "")
        if self.mode == "2D stack":
            sx, sy = data.frame_spacing(self.source_index)
            spacing_text = f"{sx:.2f} × {sy:.2f} mm" if data.frame_calibrated(self.source_index) else "uncalibrated pixels"
            self.acquisition.setText(f"{data.series.modality} · {data.source.shape[2]} × {data.source.shape[1]}\n{spacing_text}")
        if data.mpr_ready:
            point = np.asarray(data.canonical_origin) + np.asarray(self.cursor) * data.canonical_spacing
            self.position_label.setText(f"Patient LPS · mm\nL {point[0]:.1f}   P {point[1]:.1f}   S {point[2]:.1f}")
        else:
            self.position_label.setText("Patient coordinates unavailable")
        self.update_navigation()
        if self.mode == "2D stack":
            self.browser.sync_image(self.source_index)
        self.update_metadata()
        if not self.busy:
            self.update_control_state()

    def update_navigation(self):
        if self.data is None:
            return
        plane = self.active_view.plane
        if plane == "Source":
            index, count = self.source_index, len(self.data.source)
        elif self.data.mpr_ready:
            axis = {"Axial": 2, "Coronal": 1, "Sagittal": 0}[plane]
            index, count = self.cursor[axis], self.data.canonical.shape[2 - axis]
        else:
            return
        self.slice_slider.blockSignals(True)
        self.slice_slider.setRange(0, count - 1)
        self.slice_slider.setValue(index)
        self.slice_slider.blockSignals(False)
        self.slice_spin.blockSignals(True)
        self.slice_spin.setRange(1, count)
        self.slice_spin.setValue(index + 1)
        self.slice_spin.blockSignals(False)
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < count - 1)
        self.slice_label.setText(f"/ {count}")

    def slider_changed(self, value):
        if self.data is None:
            return
        value = int(np.clip(value, 0, self.slice_slider.maximum()))
        if self.active_view.plane == "Source":
            self.source_index = value
        else:
            self.cursor[{"Axial": 2, "Coronal": 1, "Sagittal": 0}[self.active_view.plane]] = value
        self.refresh_views()

    def scroll_slice(self, plane, steps):
        if self.data is None:
            return
        self.activate_view(self.views[plane])
        self.slider_changed(int(np.clip(self.slice_slider.value() + steps, 0, self.slice_slider.maximum())))

    def move_crosshair(self, plane, u, v):
        if self.data and self.data.mpr_ready and plane != "Source":
            self.cursor = self.data.pixel_to_cursor(plane, u, v, self.cursor)
            self.refresh_views()

    def change_window(self, width, level, from_preset=False):
        if not from_preset:
            self.preset.blockSignals(True)
            self.preset.setCurrentText("Custom")
            self.preset.blockSignals(False)
        for widget, value in ((self.width_spin, width), (self.level_spin, level)):
            widget.blockSignals(True)
            widget.setValue(value)
            widget.blockSignals(False)
        self.refresh_views()

    def apply_preset(self, preset):
        if self.data is None:
            return
        if preset == "Custom":
            return
        if preset == "DICOM default":
            width, level = self.data.frame_window(self.source_index) if self.mode == "2D stack" else (self.data.width, self.data.level)
        elif preset == "Auto contrast":
            image = self.active_view.image
            if image is None:
                image = self.data.source[self.source_index]
            lo, hi = np.percentile(image, (1, 99))
            width, level = max(1, hi - lo), (lo + hi) / 2
        else:
            width, level = PRESETS[preset]
        self.change_window(width, level, from_preset=True)

    def select_tool(self, name):
        self.tool = name
        for view in self.views.values():
            view.tool = name
            view.pending.clear()
            view.preview = None
            cursor = Qt.CursorShape.CrossCursor if name in ("Crosshair", "Length", "Rectangle", "Ellipse", "Angle", "Arrow", "Text") else (
                Qt.CursorShape.OpenHandCursor if name == "Pan" else Qt.CursorShape.ArrowCursor)
            view.viewport().setCursor(cursor)
            view.viewport().update()
        if name == "Angle":
            self.statusBar().showMessage("Click three points: first endpoint, vertex, second endpoint")

    def invert(self):
        self._inversion_override = self.invert_action.isChecked()
        self.refresh_views()

    def update_overlays(self):
        for view in self.views.values():
            view.show_overlays = self.overlays.isChecked()
            view.show_crosshair = self.crosshairs.isChecked()
            view.show_dicom_overlays = self.embedded_overlays.isChecked()
            for item in view.overlay_items:
                item.setVisible(view.show_dicom_overlays)
            view.viewport().update()

    def change_volume(self, *args):
        self.volume_view.preset = self.volume_preset.currentText()
        self.volume_view.blend = self.volume_blend.currentText()
        self.volume_view.opacity = self.opacity.value() / 100
        self.volume_view.update_transfer()
        if self.data and not self.busy:
            self.update_control_state()

    def reset_views(self):
        if self.data is None:
            return
        for view in self.views.values():
            view.reset()
        self.invert_action.setChecked(self.data.inverted)
        self._inversion_override = None
        self.cmap.setCurrentIndex(0)
        self.preset.setCurrentIndex(0)
        self.change_window(self.data.width, self.data.level, from_preset=True)
        self.volume_view.reset_camera()

    def clear_marks(self):
        for view in self.views.values():
            view.marks.clear()
            view.pending.clear()
            view.preview = None
            view.viewport().update()

    def toggle_cine(self, checked):
        if checked:
            if self.mode == "3D volume":
                self.mode_combo.setCurrentText("2D stack")
                self.cine_action.setChecked(True)
            self.cine_action.setText("Pause cine")
            self.cine_action.setIcon(icon("pause"))
            self.cine_timer.start(round(1000 / self.fps.value()))
        else:
            self.stop_cine()

    def stop_cine(self):
        self.cine_timer.stop()
        self.cine_action.setChecked(False)
        self.cine_action.setText("Play cine")
        self.cine_action.setIcon(icon("play"))

    def cine_step(self):
        if self.data:
            self.slider_changed((self.slice_slider.value() + 1) % (self.slice_slider.maximum() + 1))

    def show_tags(self, checked=False):
        self.metadata_dock.setVisible(checked)
        if checked:
            self.resizeDocks([self.metadata_dock], [260], Qt.Orientation.Vertical)

    def image_capture(self, annotated=True, include_information=False):
        if self.mode == "3D volume":
            return self.volume_view.capture()
        return self.active_view.render_image(annotated, include_information)

    def export_image(self):
        self.stop_cine()
        options = ExportDialog(self, volume=self.mode == "3D volume")
        if options.exec() != QDialog.DialogCode.Accepted:
            return
        suggested = "lumen-volume.png" if self.mode == "3D volume" else (
            "lumen-annotated.png" if options.annotated else "lumen-unannotated.png")
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", suggested, "PNG (*.png)")
        if path:
            try:
                if not Path(path).suffix:
                    path += ".png"
                image = self.image_capture(options.annotated, options.include_information)
                if image is None or not image.save(path, "PNG"):
                    raise OSError("Could not save the image to this location.")
                self.statusBar().showMessage(f"Saved {Path(path).name}")
            except Exception as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def copy_image(self):
        if self.metadata_pane.table.hasFocus():
            indexes = self.metadata_pane.table.selectionModel().selectedIndexes()
            if indexes:
                rows = sorted({index.row() for index in indexes})
                columns = sorted({index.column() for index in indexes})
                cells = {(index.row(), index.column()): str(index.data() or "") for index in indexes}
                text = "\n".join("\t".join(cells.get((row, column), "") for column in columns) for row in rows)
                QApplication.clipboard().setText(text)
                self.statusBar().showMessage("Selected metadata copied")
            return
        self.stop_cine()
        try:
            image = self.image_capture()
            if image:
                QApplication.clipboard().setImage(image)
                self.statusBar().showMessage("Current view copied to the clipboard")
        except Exception as exc:
            QMessageBox.warning(self, "Copy failed", str(exc))

    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def show_help(self):
        QMessageBox.information(self, "Viewer controls",
            "Open: Ctrl+O (files), Ctrl+Shift+O (folder), or drag and drop.\n\n"
            "Wheel / arrow keys: browse. Ctrl+wheel: zoom.\n"
            "Down: next image · Up: previous · Page Up/Down: 10 images.\n"
            "Home/End: first/last. Use the image number to jump directly.\n"
            "Right drag: window/level. Middle drag: pan.\n"
            "W: window · P: pan · Z: zoom · S: scroll\n"
            "C: linked crosshair · D: distance · E: ellipse ROI\n"
            "A: three-point angle · T: text\n"
            "R: reset · F: fit · I: invert · H/V: flip · ]: rotate\n"
            "Space: cine · Delete: remove last mark · Esc: cancel drawing\n"
            "Ctrl+I: metadata · Ctrl+S: save view · Ctrl+C: copy view\n\n"
            "MPR uses patient LPS coordinates. Click a pane to select it.\n"
            "In 3D, left drag orbits, middle drag pans, and the wheel zooms.\n"
            "The cutaway slider removes the posterior side of the volume.")

    def show_notices(self):
        candidates = [Path(__file__).resolve().parent.parent / "THIRD_PARTY" / "README.txt",
                      Path(__file__).resolve().parent.parent / "build" / "release_materials" / "THIRD_PARTY" / "README.txt"]
        for path in candidates:
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                return
        QMessageBox.information(self, "Third-party notices", "License texts are supplied in the portable release's THIRD_PARTY folder.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy:
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.open_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.busy:
            self._closing = True
            self.cancel_job()
            self.statusBar().showMessage("Cancelling and closing…")
            event.ignore()
            return
        self.stop_cine()
        self.volume_view.shutdown()
        for temporary in self.temporaries:
            temporary.cleanup()
        event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lumen offline DICOM viewer")
    parser.add_argument("paths", nargs="*", help="DICOM files, directories, DICOMDIR, or ZIP archives")
    parser.add_argument("--demo", action="store_true", help="Open the generated phantom")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Lumen DICOM")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Lumen")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "resources" / "lumen.svg")))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    if args.paths:
        QTimer.singleShot(50, lambda: window.open_paths(args.paths))
    elif args.demo:
        QTimer.singleShot(50, window.load_demo)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
