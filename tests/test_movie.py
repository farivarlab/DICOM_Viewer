"""Animated GIF export."""
import numpy as np
from PIL import Image

from lumen.movie import MAX_FRAMES, movie_positions, save_gif
from test_workflow import app, window, study, install


def test_positions_are_capped_and_include_both_ends():
    assert movie_positions(5) == [0, 1, 2, 3, 4]
    long = movie_positions(5000)
    assert len(long) == MAX_FRAMES and long[0] == 0 and long[-1] == 4999


def test_gif_pads_frames_and_loops(tmp_path):
    frames = [np.full((10, 20, 3), 50, np.uint8), np.full((8, 16, 3), 200, np.uint8)]
    save_gif(frames, tmp_path / "movie.gif", 10)
    with Image.open(tmp_path / "movie.gif") as image:
        assert image.n_frames == 2 and image.size == (20, 10)
        assert image.info.get("loop") == 0 and image.info.get("duration") == 100


def test_viewer_exports_every_slice_and_restores_the_view(window, study, app, tmp_path, monkeypatch):
    install(window, study, app)
    window.change_window(400, -974)  # the fixture's -1024…-924 HU would all be black at the default window
    window.slider_changed(1)
    output = tmp_path / "slices.gif"
    monkeypatch.setattr("lumen.app.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(output), "GIF"))
    window.export_movie()
    with Image.open(output) as image:
        assert image.n_frames == 3
    assert window.source_index == 1
