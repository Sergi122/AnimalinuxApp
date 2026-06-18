"""
Iconos SVG inline para los editores (no dependen del icon-theme del sistema).

Estilo línea monocromo (tipo Lucide/Feather), pensados para un chrome
profesional oscuro como Clip Studio Paint. Se renderizan vía GdkPixbuf
(librsvg) y se cachean como texturas por (nombre, tamaño).

Uso:
    from .icons import icon_image, set_button_icon
    btn.set_child(icon_image("pencil", 18))
"""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib  # noqa: E402

# trazo claro para fondo oscuro; el estado activo se marca con el fondo del botón
_STROKE = "#dfe3f2"

# cada entrada es el CONTENIDO del <svg> (paths). fill="none" salvo los "sólidos".
_PATHS = {
    # ── herramientas ──
    "brush":   '<path d="M14 3l7 7-6 4-5-5z"/><path d="M10 9l-4 4c-1.2 1.2-1.2 3.2 0 4.4 1.2 1.2 3.2 1.2 4.4 0l4-4"/>',
    "pencil":  '<path d="M4 20l4-1L19 7l-3-3L5 15l-1 4z"/><path d="M14 6l4 4"/>',
    "eraser":  '<path d="M15 4l5 5-9 9H6l-3-3 9-9z"/><path d="M6 21h14"/>',
    "fill":    '<path d="M11 4l7 7-6.5 6.5a2 2 0 0 1-3 0L5 14a2 2 0 0 1 0-3z"/>'
               '<path d="M9 6l2-2"/><path d="M20 14c1.2 1.6 1.2 3 0 4"/>',
    "replace": '<path d="M4 9a7 7 0 0 1 12-3l2 2"/><path d="M18 4v4h-4"/>'
               '<path d="M20 15a7 7 0 0 1-12 3l-2-2"/><path d="M6 20v-4h4"/>',
    "outline": '<rect x="4" y="4" width="16" height="16" rx="1.5"/>',
    "rect_fill": '<rect x="4" y="4" width="16" height="16" rx="1.5" fill="%s" stroke="none"/>' % _STROKE,
    "ellipse": '<circle cx="12" cy="12" r="8"/>',
    "ellipse_fill": '<circle cx="12" cy="12" r="8" fill="%s" stroke="none"/>' % _STROKE,
    "line":    '<path d="M5 19L19 5"/>',
    "dither":  '<rect x="4" y="4" width="4" height="4" fill="%s" stroke="none"/>'
               '<rect x="12" y="4" width="4" height="4" fill="%s" stroke="none"/>'
               '<rect x="8" y="10" width="4" height="4" fill="%s" stroke="none"/>'
               '<rect x="16" y="10" width="4" height="4" fill="%s" stroke="none"/>'
               '<rect x="4" y="16" width="4" height="4" fill="%s" stroke="none"/>'
               '<rect x="12" y="16" width="4" height="4" fill="%s" stroke="none"/>'
               % (_STROKE, _STROKE, _STROKE, _STROKE, _STROKE, _STROKE),
    "wand":    '<path d="M6 18L14 10"/><path d="M17 3l1 3 3 1-3 1-1 3-1-3-3-1 3-1z"/>',
    "smudge":  '<path d="M5 16c3 0 4-8 7-8s2 6 5 6"/><circle cx="18" cy="15" r="2" fill="%s" stroke="none"/>' % _STROKE,
    "gradient": '<rect x="4" y="5" width="16" height="14" rx="1.5"/>'
                '<path d="M4 12h16" stroke-opacity="0.5"/>',
    "select":  '<rect x="4" y="4" width="16" height="16" rx="1" stroke-dasharray="3 3"/>',
    "move":    '<path d="M12 3v18M3 12h18"/>'
               '<path d="M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
    "pick":    '<path d="M18 4a2 2 0 0 1 2 2 2 2 0 0 1-.6 1.4L16 11l1 1-2 2-1-1-7 7H4v-3l7-7-1-1 2-2 1 1 3.6-3.4A2 2 0 0 1 18 4z"/>',
    "vec_pen": '<path d="M5 5l6 14 2-6 6-2z"/><path d="M5 5l8 8"/>',
    # ── barra superior ──
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/><path d="M8 11h6"/>',
    "zoom_in":  '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/><path d="M8 11h6M11 8v6"/>',
    "fit":      '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "play":     '<path d="M7 4l13 8-13 8z" fill="%s" stroke="none"/>' % _STROKE,
    "pause":    '<rect x="6" y="4" width="4" height="16" fill="%s" stroke="none"/>'
                '<rect x="14" y="4" width="4" height="16" fill="%s" stroke="none"/>' % (_STROKE, _STROKE),
    "onion":    '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "sym_none": '<path d="M6 6l12 12M18 6L6 18"/>',
    "sym_h":    '<path d="M12 4v16" stroke-dasharray="2 2"/><path d="M9 9l-3 3 3 3M15 9l3 3-3 3"/>',
    "sym_v":    '<path d="M4 12h16" stroke-dasharray="2 2"/><path d="M9 9l3-3 3 3M9 15l3 3 3-3"/>',
    "sym_hv":   '<path d="M12 4v16M4 12h16" stroke-dasharray="2 2"/>',
    "import":   '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a1 1 0 0 1 1 1v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "undo":     '<path d="M9 7L4 12l5 5"/><path d="M4 12h10a5 5 0 0 1 0 10h-2"/>',
    "redo":     '<path d="M15 7l5 5-5 5"/><path d="M20 12H10a5 5 0 0 0 0 10h2"/>',
    "help":     '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 0 1 4 2c0 1.5-2 2-2 3.5"/><circle cx="11.6" cy="17.5" r="0.6" fill="%s" stroke="none"/>' % _STROKE,
    "save":     '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
                '<path d="M8 3v5h7M8 14h8v7H8z"/>',
    "gif":      '<rect x="3" y="5" width="18" height="14" rx="2"/>'
                '<path d="M3 9h2M3 13h2M3 17h2M19 9h2M19 13h2M19 17h2" stroke-opacity="0.6"/>',
    "copy":     '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "paste":    '<rect x="5" y="5" width="14" height="16" rx="2"/><path d="M9 5V3.5h6V5"/><path d="M9 11h6M9 15h4" stroke-opacity="0.6"/>',
    "add":      '<path d="M12 5v14M5 12h14"/>',
    "duplicate":'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "trash":    '<path d="M4 7h16"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'
                '<path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>',
    "merge":    '<path d="M8 4v6M16 4v6"/><path d="M5 10h14l-7 8z" fill="%s" stroke="none"/>' % _STROKE,
    "flatten":  '<rect x="4" y="14" width="16" height="6" rx="1"/><path d="M7 11h10M9 8h6"/>',
    "up":       '<path d="M12 19V6M6 12l6-6 6 6"/>',
    "down":     '<path d="M12 5v13M6 12l6 6 6-6"/>',
    "eye":      '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "eye_off":  '<path d="M4 5l16 14"/><path d="M9 6.5A10 10 0 0 1 12 5c6 0 10 7 10 7a16 16 0 0 1-3 3.5M6 8.5A16 16 0 0 0 2 12s4 7 10 7a10 10 0 0 0 3-.5"/>',
    "lock":     '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "camera":   '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7l2-3h4l2 3"/><circle cx="12" cy="13.5" r="3.2"/>',
    "audio":    '<path d="M9 18V6l10-2v12"/><circle cx="6.5" cy="18" r="2.3" fill="%s" stroke="none"/><circle cx="16.5" cy="16" r="2.3" fill="%s" stroke="none"/>' % (_STROKE, _STROKE),
    "smooth":   '<path d="M3 14c3.5 0 3.5-6 7-6s3.5 8 7 8"/>',
    "stabilizer": '<path d="M9 11V6.5a2 2 0 0 1 4 0V11M13 9a2 2 0 0 1 4 0v5a6 6 0 0 1-6 6 6 6 0 0 1-4.2-1.7L4 16l1.5-1.5L9 16"/>',
    "reset":    '<path d="M5 12a7 7 0 1 1 2 4.9"/><path d="M4 17v-5h5"/>',
    "folder_open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a1 1 0 0 1 1 1v2H3z"/><path d="M3 10h19l-2 8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "close":    '<path d="M6 6l12 12M18 6L6 18"/>',
}

_cache = {}


def _render(name, size):
    body = _PATHS.get(name)
    if body is None:
        return None
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 24 24" fill="none" stroke="%s" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">%s</svg>'
        % (size, size, _STROKE, body)
    )
    try:
        stream = Gio.MemoryInputStream.new_from_bytes(
            GLib.Bytes.new(svg.encode("utf-8")))
        pb = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
            stream, size, size, True, None)
        return Gdk.Texture.new_for_pixbuf(pb)
    except Exception:  # noqa: BLE001
        return None


def icon_texture(name, size=18):
    key = (name, size)
    if key not in _cache:
        _cache[key] = _render(name, size)
    return _cache[key]


def icon_image(name, size=18):
    """Devuelve un Gtk.Image con el icono; si falla, un Image vacío."""
    tex = icon_texture(name, size)
    img = Gtk.Image()
    if tex is not None:
        img.set_from_paintable(tex)
    img.set_pixel_size(size)
    return img


def icon_button(name, tooltip="", size=18, toggle=False, css="tool-btn"):
    """Crea un botón (o toggle) con icono SVG y tooltip."""
    btn = Gtk.ToggleButton() if toggle else Gtk.Button()
    btn.set_child(icon_image(name, size))
    if tooltip:
        btn.set_tooltip_text(tooltip)
    if css:
        btn.add_css_class(css)
    return btn
