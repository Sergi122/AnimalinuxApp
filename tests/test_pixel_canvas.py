"""Pruebas del modelo del lienzo de píxeles (capas, fotogramas, undo, selección)."""
import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

if not Gtk.init_check():
    pytest.skip("sin pantalla para GTK", allow_module_level=True)

from animalinux.editors.pixel_canvas import PixelCanvas, brush_offsets, pixel_perfect  # noqa: E402

RED = (255, 0, 0, 255)


@pytest.fixture
def cv():
    return PixelCanvas(16, 16)


def px(c, x, y, li=None, fi=None):
    i = (y * c.cw + x) * 4
    return tuple(c.cel(li, fi)[i:i + 4])


def test_paint_and_undo(cv):
    cv.snap_undo()
    cv._paint_stamps([(3, 3)], RED)
    assert px(cv, 3, 3) == RED
    cv.undo()
    assert px(cv, 3, 3) == (0, 0, 0, 0)
    cv.redo()
    assert px(cv, 3, 3) == RED


def test_layers_frames_stay_in_sync(cv):
    cv.add_layer()
    cv.duplicate_frame()
    cv.new_frame()
    assert len(cv.layers) == 2 and cv.frame_count == 3
    assert all(len(l.frames) == 3 for l in cv.layers)
    cv.undo()
    assert cv.frame_count == 2
    cv.delete_frame()
    assert cv.frame_count == 1


def test_locked_layer_blocks_drawing(cv):
    cv.layer.locked = True
    assert cv._locked() is True


def test_merge_down_keeps_pixels(cv):
    cv._paint_stamps([(1, 1)], RED)
    cv.add_layer()
    cv._paint_stamps([(2, 2)], (0, 0, 255, 255))
    cv.merge_down()
    assert len(cv.layers) == 1
    assert px(cv, 1, 1) == RED and px(cv, 2, 2) == (0, 0, 255, 255)


def test_selection_copy_paste_and_clear(cv):
    cv._paint_stamps([(2, 2)], RED)
    cv.select_all()
    cv.copy_selection(cut=True)
    assert px(cv, 2, 2) == (0, 0, 0, 0)
    cv.paste_selection()
    assert px(cv, 2, 2) == RED


def test_sprite_transforms(cv):
    cv._paint_stamps([(0, 0)], RED)
    cv.flip_sprite(True)
    assert px(cv, 15, 0) == RED
    cv.canvas_size(20, 10)
    assert (cv.cw, cv.ch) == (20, 10)
    cv.rotate_sprite(90)
    assert (cv.cw, cv.ch) == (10, 20)


def test_tiled_mode_wraps(cv):
    cv.tiled = "x"
    cv._paint_stamps([(15, 5), (16, 5)], RED)
    assert px(cv, 0, 5) == RED


def test_opacity_and_lock_alpha(cv):
    cv.opacity = 128
    cv.ink = "alpha"
    cv._paint_stamps([(4, 4)], RED)
    assert px(cv, 4, 4)[3] == 128
    cv.opacity, cv.ink = 255, "lock_alpha"
    cv._paint_stamps([(9, 9)], RED)
    assert px(cv, 9, 9) == (0, 0, 0, 0)          # no pinta sobre transparente


def test_brush_shapes_and_pixel_perfect():
    assert len(brush_offsets(3, "square")) == 9
    assert len(brush_offsets(3, "circle")) == 5
    assert pixel_perfect([(0, 0), (1, 0), (1, 1), (2, 1)]) == [(0, 0), (1, 1), (2, 1)]
