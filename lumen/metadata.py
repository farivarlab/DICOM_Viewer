import csv
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton,
    QTableView, QAbstractItemView, QHeaderView, QFileDialog, QMessageBox,
)
from .icons import icon


class MetadataModel(QAbstractTableModel):
    """Expose metadata strings on demand instead of allocating a widget item per cell."""
    HEADERS = ("Tag / path", "Name", "VR", "Value")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.search_rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.search_rows = [" ".join(values).casefold() for values in rows]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self.rows[index.row()][index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section] if 0 <= section < len(self.HEADERS) else None
        return section + 1


class MetadataFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""

    def set_query(self, query):
        self.query = query.casefold()
        # The native setter invalidates the proxy efficiently, while our override
        # matches a cached row string without repeated Python/Qt calls per column.
        self.setFilterFixedString(self.query)

    def filterAcceptsRow(self, source_row, source_parent):
        return not self.query or self.query in self.sourceModel().search_rows[source_row]


class MetadataPane(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.dataset = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.caption = QLabel("No file selected")
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter DICOM tags…")
        self.search.setAccessibleName("Filter DICOM metadata")
        self.search.setClearButtonEnabled(True)
        export = QPushButton("Export CSV…")
        export.setIcon(icon("export"))
        export.clicked.connect(self.export)
        top.addWidget(self.caption, 1)
        top.addWidget(self.search, 1)
        top.addWidget(export)
        layout.addLayout(top)
        self.model = MetadataModel(self)
        self.proxy = MetadataFilter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(2, 50)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.search.textChanged.connect(self.filter)

    def set_dataset(self, dataset, caption):
        self.caption.setText(caption)
        if dataset is self.dataset:
            return
        self.dataset = dataset
        self.rows = []

        def visit(ds, prefix=""):
            for element in ds:
                tag = f"{prefix}{element.tag}"
                if element.VR == "SQ":
                    self.rows.append((tag, element.name, element.VR, f"{len(element.value)} item(s)"))
                    for i, item in enumerate(element.value):
                        visit(item, f"{tag}[{i}]/")
                else:
                    value = f"<{len(element.value):,} bytes>" if isinstance(element.value, bytes) else str(element.value)
                    self.rows.append((tag, element.name, element.VR, value[:600]))
        visit(dataset)
        self.model.set_rows(self.rows)
        self.filter(self.search.text())

    def filter(self, query):
        self.proxy.set_query(query)

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export metadata", "metadata.csv", "CSV (*.csv)")
        if path:
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["Tag", "Name", "VR", "Value"])
                    writer.writerows(tuple("'" + v if v.startswith(("=", "+", "-", "@")) else v for v in row) for row in self.rows)
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))
