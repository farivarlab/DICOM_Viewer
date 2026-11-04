"""Patient/case browser with bounded, lazy file and frame branches."""
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QAbstractItemView

from .icons import icon

ROLE = Qt.ItemDataRole.UserRole
PAGE_SIZE = 256


@dataclass(frozen=True)
class Target:
    uid: str
    kind: str
    path: Path | None = None
    frame: int = 0
    start: int = 0
    stop: int = 0


class CaseBrowser(QTreeWidget):
    requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(15)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.currentItemChanged.connect(self._selected)
        self.itemExpanded.connect(self._expanded)
        self._icons = {name: icon(name) for name in ("patient", "case", "series", "image")}
        self.series_items, self.series = {}, {}
        self.loaded = None
        self.file_nodes, self.frame_nodes = {}, {}
        self._orders, self._paths, self._positions = {}, {}, {}
        self._file_pages, self._frame_pages = {}, {}
        self._built, self._search_text = set(), {}
        self._query = ""
        self._current_index = None

    def populate(self, series_list, loaded=None):
        previous = self.blockSignals(True)
        self.setUpdatesEnabled(False)
        self.clear()
        self.series_items, self.file_nodes, self.frame_nodes = {}, {}, {}
        self._orders, self._paths, self._positions = {}, {}, {}
        self._file_pages, self._frame_pages = {}, {}
        self._built, self._search_text = set(), {}
        self._query, self._current_index = "", None
        self.series = {series.uid: series for series in series_list}
        self.loaded = loaded
        patients, studies = {}, {}
        for series in series_list:
            patient_key = (series.patient_issuer, series.patient_id or series.patient)
            if patient_key not in patients:
                name = series.patient + (f" · {series.patient_id}" if series.patient_id else "")
                patient = QTreeWidgetItem(self, [name])
                patient.setIcon(0, self._icons["patient"])
                patient.setToolTip(0, name)
                patient.setExpanded(True)
                patients[patient_key] = patient
            case_key = (patient_key, series.study_uid or (series.study, series.date))
            if case_key not in studies:
                name = series.study + (f" · {series.date}" if series.date else "")
                case = QTreeWidgetItem(patients[patient_key], [name])
                case.setIcon(0, self._icons["case"])
                case.setToolTip(0, f"Case: {name}" + (f"\nAccession: {series.accession}" if series.accession else ""))
                case.setExpanded(True)
                studies[case_key] = case
            item = QTreeWidgetItem(studies[case_key], [f"{series.modality} · {series.description} ({series.frames})"])
            item.setIcon(0, self._icons["series"])
            item.setData(0, ROLE, Target(series.uid, "series"))
            item.setToolTip(0, f"{series.title}\n{series.frames:,} images · {len(series.paths):,} files")
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self.series_items[series.uid] = item
            self._search_text[series.uid] = " ".join((series.patient, series.patient_id, series.study,
                series.date, series.accession, series.modality, series.description)).casefold()
        self.blockSignals(previous)
        self.setUpdatesEnabled(True)
        if loaded:
            self.set_loaded(loaded)

    def _selected(self, current, previous):
        target = current.data(0, ROLE) if current else None
        if target and target.kind in ("series", "file", "frame"):
            self.requested.emit(target)

    def _expanded(self, item):
        target = item.data(0, ROLE)
        if not target:
            return
        if target.kind == "series":
            self._files(target.uid)
        elif target.kind == "file" and item.childCount() == 0:
            info = self.series[target.uid].files.get(target.path)
            self._add_frames(item, target.uid, target.path, 0, info.frames if info else 1)
        elif target.kind == "file_page" and item.childCount() == 0:
            self._add_files(item, target.uid, target.start, target.stop)
        elif target.kind == "frame_page" and item.childCount() == 0:
            self._add_frames(item, target.uid, target.path, target.start, target.stop)

    def _order(self, uid):
        if uid not in self._orders:
            series = self.series[uid]
            self._orders[uid] = sorted(set(series.paths), key=lambda p: (
                series.files[p].instance if p in series.files else 0, p.name, str(p)))
        return self._orders[uid]

    def _matches(self, uid):
        paths = self._order(uid)
        if not self._query or self._query in self._search_text[uid]:
            return paths, True
        return [path for path in paths if self._query in str(path).casefold()], False

    def _files(self, uid):
        if uid in self._built:
            return
        self._built.add(uid)
        parent, series = self.series_items[uid], self.series[uid]
        paths, metadata_match = self._matches(uid)
        self._paths[uid] = paths
        self._positions[uid] = {path: i for i, path in enumerate(paths)}
        if series.paths:
            self._add_files(parent, uid, 0, len(paths))
        elif metadata_match:
            self._add_frames(parent, uid, None, 0, series.frames)

    def _add_files(self, parent, uid, start, stop):
        if stop - start > PAGE_SIZE:
            for first in range(start, stop, PAGE_SIZE):
                last = min(stop, first + PAGE_SIZE)
                item = QTreeWidgetItem(parent, [f"Files {first + 1:,}–{last:,}"])
                item.setData(0, ROLE, Target(uid, "file_page", start=first, stop=last))
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self._file_pages[(uid, first)] = item
            return
        series = self.series[uid]
        for path in self._paths[uid][start:stop]:
            info = series.files.get(path)
            count = info.frames if info else 1
            name = path.name + (f" ({count:,} frames)" if count > 1 else "")
            item = QTreeWidgetItem(parent, [name])
            item.setIcon(0, self._icons["image"])
            item.setData(0, ROLE, Target(uid, "file", path))
            item.setToolTip(0, str(path))
            if count > 1:
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self.file_nodes[(uid, path)] = item

    def _add_frames(self, parent, uid, path, start, stop):
        if stop - start > PAGE_SIZE:
            for first in range(start, stop, PAGE_SIZE):
                last = min(stop, first + PAGE_SIZE)
                noun = "Images" if path is None else "Frames"
                item = QTreeWidgetItem(parent, [f"{noun} {first + 1:,}–{last:,}"])
                item.setData(0, ROLE, Target(uid, "frame_page", path, start=first, stop=last))
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                self._frame_pages[(uid, path, first)] = item
            return
        for frame in range(start, stop):
            item = QTreeWidgetItem(parent, [f"Image {frame + 1:04d}" if path is None else f"Frame {frame + 1:,}"])
            item.setIcon(0, self._icons["image"])
            item.setData(0, ROLE, Target(uid, "frame", path, frame))
            self.frame_nodes[(uid, path, frame)] = item

    def _discard_files(self, uid):
        self.series_items[uid].takeChildren()
        self._built.discard(uid)
        for mapping in (self.file_nodes, self.frame_nodes, self._file_pages, self._frame_pages):
            for key in [key for key in mapping if key[0] == uid]:
                del mapping[key]

    def set_loaded(self, data):
        self.loaded, self._current_index = data, None
        uid = data.series.uid
        if uid not in self.series_items:
            return
        previous = self.blockSignals(True)
        if data.references:
            self._orders[uid] = list(dict.fromkeys(ref.path for ref in data.references if ref.path is not None))
        self._discard_files(uid)
        self._files(uid)
        item = self.series_items[uid]
        item.setText(0, f"{data.series.modality} · {data.series.description} ({len(data.source)})")
        item.setToolTip(0, f"{data.series.title}\n{len(data.source):,} displayed images · {len(self._order(uid)):,} files")
        item.setExpanded(True)
        self.blockSignals(previous)

    def sync_image(self, index):
        if self.loaded is None:
            return
        self._current_index = index
        ref, uid = self.loaded.reference(index), self.loaded.series.uid
        if uid not in self.series_items:
            return
        previous = self.blockSignals(True)
        self._files(uid)
        if ref.path is not None and ref.path not in self._positions.get(uid, {}):
            # Keep filtered results in place; do not highlight a different file as current.
            self.setCurrentItem(None)
            self.blockSignals(previous)
            return
        item = self.frame_nodes.get((uid, ref.path, ref.frame)) or self.file_nodes.get((uid, ref.path))
        if item is None and ref.path is not None:
            position = self._positions[uid][ref.path]
            page = self._file_pages.get((uid, position // PAGE_SIZE * PAGE_SIZE))
            if page:
                page.setExpanded(True)
                self._expanded(page)
                item = self.file_nodes.get((uid, ref.path))
        if item is None and ref.path is None:
            page = self._frame_pages.get((uid, None, ref.frame // PAGE_SIZE * PAGE_SIZE))
            if page:
                page.setExpanded(True)
                self._expanded(page)
                item = self.frame_nodes.get((uid, None, ref.frame))
        if item is not None and self.currentItem() is not item:
            self.setCurrentItem(item)
            self.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self.blockSignals(previous)

    def select_series(self, uid):
        item = self.series_items.get(uid)
        if item:
            self.setCurrentItem(item)

    def filter(self, query):
        query = query.strip().casefold()
        if query == self._query:
            return
        self._query = query
        previous = self.blockSignals(True)
        self.setUpdatesEnabled(False)
        for uid, item in self.series_items.items():
            expanded = item.isExpanded() or uid in self._built
            self._discard_files(uid)
            paths, metadata_match = self._matches(uid)
            visible = not query or metadata_match or bool(paths)
            item.setHidden(not visible)
            if visible and (expanded or (query and not metadata_match)):
                self._files(uid)
                item.setExpanded(True)
        for i in range(self.topLevelItemCount()):
            patient = self.topLevelItem(i)
            for j in range(patient.childCount()):
                case = patient.child(j)
                case.setHidden(all(case.child(k).isHidden() for k in range(case.childCount())))
            patient.setHidden(all(patient.child(j).isHidden() for j in range(patient.childCount())))
        if self._current_index is not None:
            self.sync_image(self._current_index)
        self.setUpdatesEnabled(True)
        self.blockSignals(previous)
