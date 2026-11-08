from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from lumen.browser import CaseBrowser, ROLE, PAGE_SIZE
from lumen.model import FileInfo, FrameReference, Series


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def browser(app):
    widget = CaseBrowser()
    widget.show()
    yield widget
    widget.close()


def series(uid="test", files=1, frames=1):
    result = Series(uid, "Acquisition", "Synthetic patient", "Case one", "CT", "20260101")
    result.paths = [Path(f"C:/synthetic/{uid}/image-{i:05d}.dcm") for i in range(files)]
    result.files = {path: FileInfo(path, frames, i) for i, path in enumerate(result.paths)}
    result.frames = files * frames
    return result


def loaded(item, references):
    return SimpleNamespace(series=item, references=references, source=range(len(references)),
                           reference=lambda index: references[index])


def test_large_multiframe_file_is_paged_on_expansion(browser):
    item = series(frames=20_000)
    browser.populate([item])
    branch = browser.series_items[item.uid]
    branch.setExpanded(True)
    file = branch.child(0)
    file.setExpanded(True)
    assert file.childCount() == 79
    assert not browser.frame_nodes
    page = file.child(0)
    page.setExpanded(True)
    assert page.childCount() == PAGE_SIZE
    assert len(browser.frame_nodes) == PAGE_SIZE


def test_large_file_list_expands_only_requested_page(browser):
    item = series(files=10_000)
    browser.populate([item])
    branch = browser.series_items[item.uid]
    branch.setExpanded(True)
    assert branch.childCount() == 40
    assert not browser.file_nodes
    page = branch.child(2)
    page.setExpanded(True)
    assert len(browser.file_nodes) == PAGE_SIZE
    assert page.child(0).data(0, ROLE).path == item.paths[PAGE_SIZE * 2]


def test_search_matches_paths_without_materializing_other_series(browser):
    items = [series(str(i), files=1_000) for i in range(20)]
    browser.populate(items)
    browser.filter("image-00777.dcm")
    assert len(browser.file_nodes) == 20
    assert all(branch.childCount() == 1 for branch in browser.series_items.values())
    browser.filter("unmatched-name")
    assert not browser.file_nodes
    assert all(branch.isHidden() for branch in browser.series_items.values())


def test_patient_search_keeps_unopened_file_lists_lazy(browser):
    items = [series(str(i), files=200) for i in range(20)]
    browser.populate(items)
    browser.filter("synthetic patient")
    assert not browser.file_nodes
    assert all(not branch.isHidden() for branch in browser.series_items.values())


def test_sync_selects_file_on_unopened_page_without_emitting_request(browser):
    item = series(files=1_000)
    refs = [FrameReference(path) for path in item.paths]
    browser.populate([item])
    browser.set_loaded(loaded(item, refs))
    emitted = []
    browser.requested.connect(emitted.append)
    browser.sync_image(800)
    assert browser.currentItem().data(0, ROLE).path == item.paths[800]
    assert len(browser.file_nodes) <= PAGE_SIZE
    assert not emitted


def test_sync_does_not_select_a_filtered_out_image(browser):
    item = series(files=4)
    refs = [FrameReference(path) for path in item.paths]
    browser.populate([item])
    browser.set_loaded(loaded(item, refs))
    browser.sync_image(0)
    browser.filter("image-00001.dcm")
    assert browser.currentItem() is None
    browser.sync_image(1)
    assert browser.currentItem().data(0, ROLE).path == item.paths[1]
    browser.sync_image(2)
    assert browser.currentItem() is None
    assert browser.series_items[item.uid].childCount() == 1
    browser.filter("")
    assert browser.currentItem().data(0, ROLE).path == item.paths[2]


def test_page_selection_does_not_request_loading(browser):
    item = series(files=1_000)
    browser.populate([item])
    branch = browser.series_items[item.uid]
    branch.setExpanded(True)
    emitted = []
    browser.requested.connect(emitted.append)
    browser.setCurrentItem(branch.child(0))
    assert not emitted


def test_loaded_order_and_counts_follow_actual_decoded_references(browser):
    item = series(files=3)
    browser.populate([item])
    refs = [FrameReference(item.paths[2]), FrameReference(item.paths[0])]
    browser.set_loaded(loaded(item, refs))
    branch = browser.series_items[item.uid]
    assert branch.childCount() == 2
    assert branch.child(0).data(0, ROLE).path == item.paths[2]
    assert "2 displayed images" in branch.toolTip(0)
