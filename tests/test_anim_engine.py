"""Pruebas del motor del editor de animación (sin ventanas)."""
import numpy as np
import pytest

from animalinux.editors import anim_engine as ae


@pytest.fixture
def sc():
    return ae.Scene(64, 48, fps=12)


def paint_line(sc, li=0, f=0, color=(255, 0, 0, 255), size=6):
    d = sc.drawing_for_edit(li, f)
    sc.begin_edit(d)
    sp = ae.StrokePainter(d, "round", size, 0.9, 255, color)
    for x in range(5, 40, 3): sp.add(x, 20)
    sp.finish(40, 20)
    sc.end_edit()
    return d


def test_stroke_paints_and_region_undo(sc):
    d = paint_line(sc)
    assert d.arr[20, 20, 3] > 200 and tuple(d.arr[20, 20, :3]) == (255, 0, 0)
    assert d.bufarr[20, 20, 3] == d.arr[20, 20, 3]         # búfer cairo sincronizado
    sc.undo()
    assert d.arr[20, 20, 3] == 0
    sc.redo()
    assert d.arr[20, 20, 3] > 200


def test_all_brush_kinds_render():
    for kind in ae.BRUSH_TYPES:
        tip = ae.brush_tip(kind, 8, 0.5)
        assert tip.shape[0] == tip.shape[1] and tip.max() > 0, kind


def test_eraser_and_alpha_lock(sc):
    d = paint_line(sc)
    sc.begin_edit(d)
    sp = ae.StrokePainter(d, "pencil", 8, 1, 255, (0, 0, 0, 255), erase=True)
    sp.add(20, 20); sp.finish(20, 20); sc.end_edit()
    assert d.arr[20, 20, 3] == 0
    d2 = paint_line(sc, f=1)
    sc.begin_edit(d2)
    sp = ae.StrokePainter(d2, "pencil", 30, 1, 255, (0, 0, 255, 255), alpha_lock=True)
    sp.add(20, 20); sp.finish(20, 20); sc.end_edit()
    assert d2.arr[5, 5, 3] == 0                             # no pinta fuera del trazo
    assert tuple(d2.arr[20, 20, :3]) == (0, 0, 255)


def test_exposure_hold_and_new_drawing(sc):
    d = paint_line(sc)
    sc.ensure_frames(6)
    assert sc.extend_exposure(0, 0, 3)
    l = sc.layers[0]
    assert l.at(3) is d and l.at(4) is None
    d2 = sc.duplicate_drawing(0, 2)
    assert d2 is not d and l.at(2) is d2 and l.at(1) is d
    sc.undo()
    assert sc.layers[0].at(2) is d          # deshacer reemplaza los objetos capa


def test_frames_insert_delete_keep_layers_in_sync(sc):
    sc.add_layer("raster")
    sc.ensure_frames(4)
    sc.insert_frames(1, 2)
    assert sc.frame_count == 6 and all(len(l.exposure) == 6 for l in sc.layers)
    assert sc.delete_frames(0, 2)
    assert sc.frame_count == 4 and all(len(l.exposure) == 4 for l in sc.layers)
    sc.undo()
    assert sc.frame_count == 6


def test_camera_keys_interpolate(sc):
    sc.ensure_frames(11)
    sc.set_camera_key(0, {"tx": 0, "scale": 1})
    sc.set_camera_key(10, {"tx": 100, "scale": 2})
    c = sc.camera_at(5)
    assert c["tx"] == pytest.approx(50) and c["scale"] == pytest.approx(1.5)
    assert sc.camera_at(20)["tx"] == 100


def test_composite_blend_and_opacity(sc):
    paint_line(sc, color=(255, 0, 0, 255))
    top = sc.add_layer("raster")
    d = sc.layers[top].drawings
    dr = sc.drawing_for_edit(top, 0)
    dr.arr[:, :] = (0, 0, 255, 255); dr.refresh(0, 0, 64, 48)
    sc.layers[top].opacity = 128
    im = sc.to_pil(0)
    px = im.getpixel((2, 2))
    assert px[2] > 100 and px[3] == 255 or px[3] > 100          # azul semitransparente
    sc.layers[top].visible = False
    assert sc.to_pil(0).getpixel((2, 2))[3] == 0


def test_merge_down(sc):
    paint_line(sc, color=(255, 0, 0, 255))
    top = sc.add_layer("raster")
    dr = sc.drawing_for_edit(top, 0)
    dr.arr[40:44, 10:20] = (0, 255, 0, 255); dr.refresh(0, 0, 64, 48)
    assert sc.merge_down(top)
    assert len(sc.layers) == 1
    d = sc.layers[0].at(0)
    assert d.arr[20, 20, 3] > 200 and tuple(d.arr[41, 12]) == (0, 255, 0, 255)


def test_bucket_fill_with_gap_closing(sc):
    d = sc.drawing_for_edit(0, 0)
    arr = d.arr
    arr[10:30, 10] = arr[10:30, 30] = (0, 0, 0, 255)
    arr[10, 10:31] = arr[29, 10:31] = (0, 0, 0, 255)
    arr[10, 20] = (0, 0, 0, 0)                               # hueco de 1 px
    leak = ae.flood_region(arr, 20, 20, tol=32, gap=0)
    closed = ae.flood_region(arr, 20, 20, tol=32, gap=2)
    assert leak.sum() > closed.sum()                         # sin cerrar se escapa
    assert closed[20, 20] and not closed[5, 5]


def test_fill_goes_behind_lines(sc):
    d = sc.drawing_for_edit(0, 0)
    d.arr[10:20, 10:20] = (0, 0, 0, 255)
    mask = np.zeros((48, 64), bool); mask[5:25, 5:25] = True
    ae.fill_behind(d.arr, mask, (255, 255, 0, 255), grow=0)
    assert tuple(d.arr[15, 15]) == (0, 0, 0, 255)            # la línea sigue encima
    assert tuple(d.arr[7, 7]) == (255, 255, 0, 255)


def test_shapes_and_gradient():
    cov = ae.shape_coverage(40, 40, "ellipse", [(5, 5), (35, 35)], 2, fill=True)
    assert cov[20, 20] > 0.99 and cov[1, 1] == 0
    g = ae.gradient_array(10, 4, (0, 0), (9, 0), (0, 0, 0, 255), (255, 255, 255, 255))
    assert g[0, 0, 0] == 0 and g[0, 9, 0] == 255


def test_vector_strokes_hit_undo_and_render(sc):
    sc.add_layer("vector")
    li = len(sc.layers) - 1
    d = sc.drawing_for_edit(li, 0)
    sc.begin_edit(d)
    d.strokes.append({"pts": [(5, 5, 1.0), (30, 30, 1.0)], "color": (0, 0, 0, 255), "width": 4,
                      "closed": False, "fill": None})
    d.touch(); sc.end_edit()
    assert ae.stroke_hit(d.strokes[0], 17, 17, 3) and not ae.stroke_hit(d.strokes[0], 50, 5, 3)
    assert sc.to_pil(0).getpixel((17, 17))[3] > 0
    sc.undo()
    assert d.strokes == []


def test_project_roundtrip(tmp_path, sc):
    paint_line(sc)
    sc.add_layer("vector")
    d = sc.drawing_for_edit(1, 0)
    d.strokes.append({"pts": [(1, 1, 1.0), (9, 9, 1.0)], "color": (1, 2, 3, 255), "width": 3,
                      "closed": False, "fill": None})
    sc.ensure_frames(5); sc.extend_exposure(0, 0, 3)
    sc.set_camera_key(2, {"tx": 5})
    sc.layers[0].blend = "Multiplicar"
    p = tmp_path / "x.alproj"
    sc.save(str(p))
    b = ae.Scene.load(str(p))
    assert (b.w, b.h, b.frame_count) == (64, 48, 5)
    assert b.layers[0].blend == "Multiplicar" and b.layers[0].exposure[:4] == [0, 0, 0, 0]
    assert b.layers[1].kind == "vector" and len(b.layers[1].at(0).strokes) == 1
    assert b.cam_keys[2]["tx"] == 5
    assert np.array_equal(b.layers[0].at(0).arr, sc.layers[0].at(0).arr)


def test_v1_projects_still_open(tmp_path):
    import io, json, zipfile
    from PIL import Image
    p = tmp_path / "old.alproj"
    im = Image.new("RGBA", (16, 16), (0, 0, 0, 0)); im.putpixel((3, 3), (9, 9, 9, 255))
    buf = io.BytesIO(); im.save(buf, "PNG")
    meta = {"version": 1, "canvas": {"w": 16, "h": 16}, "cur": 0, "frame_labels": [""],
            "frame_camera": [{"tx": 0, "ty": 0, "scale": 1.0, "rot": 0.0}],
            "frames": [{"layers": [{"name": "Capa 1", "visible": True, "opacity": 255,
                                    "blend_mode": "Normal", "locked": False, "alpha_locked": False,
                                    "img": "f0/l0.png", "type": "raster"}]}]}
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("project.json", json.dumps(meta)); zf.writestr("f0/l0.png", buf.getvalue())
    sc = ae.Scene.load(str(p))
    assert sc.w == 16 and sc.layers[0].at(0).arr[3, 3, 3] == 255


def test_undo_restores_scene_size(sc):
    d = sc.drawing_for_edit(0, 0)
    sc.snap()
    sc.w, sc.h = 100, 80                       # como hace «Tamaño de la escena»
    sc.layers[0].drawings[0] = ae.Drawing(100, 80, "raster")
    sc.undo()
    assert (sc.w, sc.h) == (64, 48) and sc.layers[0].drawings[0] is d
    sc.redo()
    assert (sc.w, sc.h) == (100, 80)


@pytest.mark.parametrize("meta", [
    {"version": 2, "w": 10 ** 9, "h": 10, "frames": 1, "layers": []},
    {"version": 2, "w": 10, "h": 10, "frames": 10 ** 9, "layers": []},
    [1, 2],
])
def test_hostile_project_is_rejected(tmp_path, meta):
    """Un .alproj ajeno no debe poder pedir lienzos o fotogramas gigantes."""
    import json
    import zipfile
    p = tmp_path / "x.alproj"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("project.json", json.dumps(meta))
    with pytest.raises(ValueError):
        ae.Scene.load(str(p))
