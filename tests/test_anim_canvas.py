"""Pruebas de la vista del editor de animación (gestos simulados, requiere GTK con pantalla)."""
import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk  # noqa: E402

if not Gtk.init_check():
    pytest.skip("sin pantalla para GTK", allow_module_level=True)

from animalinux.editors.anim_canvas import AnimCanvas  # noqa: E402
from animalinux.editors import anim_engine as ae  # noqa: E402


class G:
    def __init__(self, b=1, m=0): self.b, self.m = b, Gdk.ModifierType(m)
    def get_current_button(self): return self.b
    def get_current_event_state(self): return self.m


@pytest.fixture
def cv():
    c = AnimCanvas(ae.Scene(200, 150))
    c._fit_pending = False; c._z = 1.0; c._ox = c._oy = 0.0
    return c


def drag(c, tool, pts, btn=1):
    c.set_tool(tool); g = G(btn); c._g = g
    x0, y0 = c._c2s(*pts[0]); c._drag_begin(g, x0, y0)
    for p in pts[1:]:
        x, y = c._c2s(*p); c._drag_update(g, x - x0, y - y0)
    x, y = c._c2s(*pts[-1]); c._drag_end(g, x - x0, y - y0)


def test_brush_creates_drawing_in_one_undo_step(cv):
    drag(cv, "brush", [(20, 20), (100, 40), (150, 30)])
    d = cv.layer.at(0)
    assert d is not None and d.arr[..., 3].any()
    cv.undo()
    assert cv.layer.at(0) is None                      # crear + pintar = un solo paso
    cv.redo()
    assert cv.layer.at(0).arr[..., 3].any()


def test_right_click_paints_background_color(cv):
    cv.fg, cv.bg = (255, 0, 0, 255), (0, 0, 255, 255)
    cv.props["smoothing"] = 0
    drag(cv, "pencil", [(50, 50), (60, 50)], btn=3)
    px = cv.layer.at(0).arr[50, 55]
    assert tuple(px[:3]) == (0, 0, 255)


def test_paint_bucket_fills_closed_shape_behind_lines(cv):
    cv.fg = (0, 200, 0, 255); cv.props["smoothing"] = 0
    drag(cv, "rect", [(40, 40), (120, 100)])
    drag(cv, "paint", [(80, 70)])
    arr = cv.layer.at(0).arr
    assert tuple(arr[70, 80, :3]) == (0, 200, 0) and arr[10, 10, 3] == 0


def test_vector_layer_select_move_and_delete(cv):
    cv.add_layer("vector")
    cv.props["smoothing"] = 0
    drag(cv, "brush", [(20, 20), (60, 60), (100, 30)])
    d = cv.layer.at(0)
    assert len(d.strokes) == 1
    p = d.strokes[0]["pts"][0][:2]
    drag(cv, "select", [p]); assert cv.vsel == {0}
    before = d.strokes[0]["pts"][0][0]
    drag(cv, "select", [p, (p[0] + 15, p[1])])
    assert d.strokes[0]["pts"][0][0] == pytest.approx(before + 15, abs=1)
    cv.clear_selection()
    assert d.strokes == []


def test_camera_tool_creates_key_and_undo(cv):
    cv.mode = "camera"
    drag(cv, "camera", [(50, 50), (80, 60)])
    assert cv.scene.cam_keys[0]["tx"] == pytest.approx(30, abs=1)
    cv.undo()
    assert 0 not in cv.scene.cam_keys


def test_onion_and_light_table_render_without_errors(cv):
    drag(cv, "brush", [(20, 20), (100, 40)])
    cv.scene.ensure_frames(3); cv.go_to(1); drag(cv, "brush", [(30, 60), (110, 80)])
    cv.onion = True; cv.light_table = True; cv.symmetry = "h"; cv.mirror_view = True
    import cairo
    surf = cairo.ImageSurface(cairo.Format.ARGB32, 300, 200)
    cv._draw(cv, cairo.Context(surf), 300, 200)
