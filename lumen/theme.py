from pathlib import Path


STYLE = """
QWidget { background: #f5f7f9; color: #273847; font-family: 'Segoe UI'; font-size: 12px; }
QMainWindow { background: #e4e9ee; }
QMenuBar, QMenu { background: #ffffff; }
QMenuBar::item:selected, QMenu::item:selected { background: #e0efeb; color: #145d54; }
QToolBar { background: #ffffff; border: none; border-bottom: 1px solid #d4dde4; spacing: 4px; padding: 5px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 0; padding: 6px 8px; }
QToolButton:hover { background: #edf2f5; }
QToolButton:pressed { background: #d9e5e9; border-color: #8196a5; }
QToolButton:checked { background: #d9eee6; color: #125f54; border-color: #3b8877; }
QToolButton:checked:hover { background: #c9e5da; }
QToolButton:focus, QPushButton:focus { border: 1px solid #126b5e; }
QPushButton { background: #ffffff; border: 1px solid #8196a5; border-radius: 0; padding: 8px 12px; }
QPushButton:hover { background: #eaf1f4; border-color: #55788a; }
QPushButton:pressed { background: #d9e5e9; }
QPushButton#primary { background: #187b6c; color: #ffffff; border: 1px solid #187b6c; font-weight: 600; }
QPushButton#primary:hover { background: #12695c; }
QPushButton#primary:focus { border: 2px solid #0b3d35; padding: 7px 11px; }
QPushButton:disabled, QToolButton:disabled { color: #929faa; background: #edf1f4; border-color: #d4dde4; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: #ffffff; border: 1px solid #8196a5; border-radius: 0; padding: 6px; selection-background-color: #cce7df; selection-color: #174c44; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus { border: 1px solid #126b5e; outline: 1px solid #126b5e; }
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled { background: #edf1f4; color: #8b9aa5; border-color: #d4dde4; }
QLineEdit QToolButton { padding: 1px; border: none; background: transparent; }
QComboBox QAbstractItemView { background: #ffffff; color: #273847; selection-background-color: #deefea; selection-color: #125f54; }
QComboBox { padding-right: 30px; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: top right; border-left: 1px solid #8196a5; width: 25px; background: #edf2f5; }
QComboBox::drop-down:hover { background: #deebe6; }
QComboBox::down-arrow { image: url(__RESOURCES__/chevron-down.svg); width: 10px; height: 6px; }
QComboBox::down-arrow:disabled { image: url(__RESOURCES__/chevron-down-disabled.svg); }
QDoubleSpinBox, QSpinBox { padding-right: 25px; }
QDoubleSpinBox::up-button, QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 21px; border-left: 1px solid #8196a5; border-bottom: 1px solid #b2c0ca; background: #edf2f5; }
QDoubleSpinBox::down-button, QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 21px; border-left: 1px solid #8196a5; background: #edf2f5; }
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover { background: #deebe6; }
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow { image: url(__RESOURCES__/chevron-up.svg); width: 9px; height: 5px; }
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow { image: url(__RESOURCES__/chevron-down.svg); width: 9px; height: 5px; }
QDoubleSpinBox::up-arrow:disabled, QSpinBox::up-arrow:disabled { image: url(__RESOURCES__/chevron-up-disabled.svg); }
QDoubleSpinBox::down-arrow:disabled, QSpinBox::down-arrow:disabled { image: url(__RESOURCES__/chevron-down-disabled.svg); }
QToolButton#qt_toolbar_ext_button { qproperty-icon: url(__RESOURCES__/more.svg); min-width: 21px; padding: 5px; border: 1px solid #8196a5; background: #edf2f5; }
QLabel#brand { font-size: 28px; font-weight: 600; letter-spacing: 1px; color: #203b44; }
QLabel#eyebrow { color: #3e7368; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#muted { color: #596b79; }
QLabel#section { color: #5a7181; font-size: 10px; font-weight: 600; letter-spacing: 1px; padding-top: 14px; padding-bottom: 4px; }
QLabel#volumeTitle { background: #0b131c; color: #adbfd3; font-size: 10px; font-weight: 600; }
QLabel#welcomeTitle { color: #203b44; font-size: 32px; font-weight: 500; }
QListWidget { border: none; background: #f5f7f9; outline: none; }
QListWidget::item { background: #ffffff; border: 1px solid #d4dde4; padding: 13px 10px; margin: 4px 0; border-radius: 0; }
QListWidget::item:selected { background: #e2f0eb; border: 1px solid #74ab9b; color: #185c50; }
QListWidget::item:hover { border-color: #8ca6b5; }
QTreeWidget { background: #ffffff; border: 1px solid #d4dde4; outline: none; padding: 3px; }
QTreeWidget::item { padding: 4px 3px; border: 1px solid transparent; }
QTreeWidget::item:selected { background: #d9eee6; color: #145d54; border-left: 2px solid #237a67; }
QTreeWidget::item:hover { background: #edf4f1; }
QTreeWidget:focus, QTableView:focus { border: 1px solid #126b5e; }
QDockWidget::title { padding: 7px 12px; background: #e8eef2; color: #405d70; border-bottom: 1px solid #d4dde4; }
QGroupBox { border: 1px solid #d4dde4; border-radius: 0; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #5a7181; }
QStatusBar { background: #edf2f5; color: #596b79; border-top: 1px solid #d4dde4; }
QSplitter::handle { background: #d4dde4; width: 4px; height: 4px; }
QSplitter::handle:hover { background: #82b2a2; }
QSlider::groove:horizontal { height: 4px; background: #ccd7de; border-radius: 0; }
QSlider::sub-page:horizontal { background: #438f7f; border-radius: 0; }
QSlider::handle:horizontal { background: #1e7565; width: 12px; margin: -5px 0; border-radius: 0; }
QSlider::handle:horizontal:focus { border: 1px solid #093b31; background: #126451; }
QSlider::handle:horizontal:disabled { background: #a8b7c1; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #8196a5; background: #ffffff; }
QCheckBox::indicator:checked { border-color: #187b6c; background: #187b6c; image: url(__RESOURCES__/check.svg); }
QCheckBox::indicator:focus { border: 1px solid #073f34; }
QCheckBox:disabled { color: #929faa; }
QCheckBox::indicator:disabled { border-color: #c7d2da; background: #e7edf1; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #e8eef2; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #92a6b4; min-height: 28px; margin: 2px; }
QScrollBar::handle:vertical:hover { background: #5b8290; }
QScrollBar:horizontal { background: #e8eef2; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: #92a6b4; min-width: 28px; margin: 2px; }
QScrollBar::handle:horizontal:hover { background: #5b8290; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QTableView { background: #ffffff; gridline-color: #d4dde4; border: 1px solid #d4dde4; alternate-background-color: #f0f4f7; selection-background-color: #d9eee6; selection-color: #145d54; }
QHeaderView::section { background: #e8eef2; color: #405d70; padding: 7px; border: none; }
QToolTip { background: #ffffff; color: #273847; border: 1px solid #aebfc9; padding: 6px; }
""".replace("__RESOURCES__", (Path(__file__).resolve().parent / "resources").as_posix())
