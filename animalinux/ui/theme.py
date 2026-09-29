"""
Tema profesional para AnimaLinux — prioridad USER (800) para vencer Adwaita.
"""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

import colorsys

# Presets: nombre → color principal. El resto se DERIVA del principal.
PRESETS = {
    "blue":   ("Azul",     "#4d8dff"),
    "cyan":   ("Cian",     "#2fc4e0"),
    "violet": ("Violeta",  "#a680ff"),
    "pink":   ("Rosa",     "#ff6fa5"),
    "green":  ("Verde",    "#35d391"),
    "orange": ("Naranja",  "#ff9a3d"),
    "red":    ("Rojo",     "#ff5e6c"),
}
DEFAULT_THEME = "blue"


def _hex(r, g, b):
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _rgb_str(hexcol):
    h = hexcol.lstrip("#")
    return "%d,%d,%d" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _hls_shift(hexcol, dh=0.0, dl=0.0, min_s=0.0, max_s=1.0):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    hh = (hh + dh) % 1.0
    ll = max(0.30, min(0.80, ll + dl))
    ss = max(min_s, min(max_s, ss))
    return _hex(*colorsys.hls_to_rgb(hh, ll, ss))


def build_palette(accent="#4d8dff"):
    """Combinación armónica a partir del color principal.

    · G1 / G2: colores vecinos en la rueda (análogos, ±~30°) para los degradados.
      En el azul salen un cian y un índigo.
    · Fondos: el mismo matiz pero casi negro y poco saturado, para que todo
      «respire» el color elegido sin cansar."""
    h, l, s = colorsys.rgb_to_hls(*(int(accent.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)))
    hh, _, _ = colorsys.rgb_to_hsv(*(int(accent.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)))

    def bg(sat, val):
        return _hex(*colorsys.hsv_to_rgb(hh, sat, val))

    g1 = _hls_shift(accent, dh=-0.085, dl=0.05, min_s=0.65)      # vecino frío
    g2 = _hls_shift(accent, dh=+0.075, dl=0.00, min_s=0.60)      # vecino cálido
    P = dict(
        BG=bg(0.42, 0.075), BG2=bg(0.46, 0.052), PANEL=bg(0.38, 0.118),
        CARD=bg(0.36, 0.125), CARD2=bg(0.34, 0.155),
        WIDGET=bg(0.34, 0.155), WIDGET2=bg(0.30, 0.225),
        ACCENT=accent, ACCENT2=_hls_shift(accent, dl=0.13),
        ON_ACCENT="#0a0d16",
        TEXT=bg(0.04, 0.97), TEXT2=bg(0.14, 0.72), MUTED=bg(0.16, 0.46),
        BORDER=bg(0.30, 0.225), BORDER2=bg(0.32, 0.38),
        RED="#ff8fa8", RED_BG="#3a1a26", RED_BG_HOVER="#4d2231", GREEN="#7be0b0",
        G1=g1, G2=g2, G1L=_hls_shift(g1, dl=0.16), G2L=_hls_shift(g2, dl=0.16),
    )
    P["A_RGB"], P["G1_RGB"], P["G2_RGB"] = _rgb_str(accent), _rgb_str(g1), _rgb_str(g2)
    P["OK_RGB"], P["RED_RGB"] = _rgb_str(P["GREEN"]), _rgb_str(P["RED"])
    return P


def resolve(theme_id):
    """'blue' | 'violet'… | '#rrggbb' → color principal."""
    if theme_id in PRESETS:
        return PRESETS[theme_id][1]
    t = str(theme_id or "").strip()
    if len(t) == 7 and t.startswith("#"):
        try:
            int(t[1:], 16); return t.lower()
        except ValueError:
            pass
    return PRESETS[DEFAULT_THEME][1]


# Las constantes viven a nivel de módulo (las leen las cadenas CSS al construirse).
globals().update(build_palette(PRESETS[DEFAULT_THEME][1]))

def _css_main():
    return f"""
/* ═══════════════════════════════════════════════
   RESET GLOBAL — limpia gradientes de Adwaita
   ═══════════════════════════════════════════════ */
* {{
  -gtk-icon-shadow: none;
  text-shadow: none;
}}

/* ── ventana raíz ── */
window,
.background {{
  background-color: {BG};
  background-image: none;
  color: {TEXT};
}}
/* ventanas de mascota: fondo completamente transparente */
window.animalinux-mascot,
window.animalinux-mascot * {{
  background-color: transparent;
  background-image: none;
  box-shadow: none;
}}
dialog, messagedialog {{
  background-color: {PANEL};
  background-image: none;
  color: {TEXT};
}}

/* ── contenedores transparentes ── */
box, grid, paned, viewport, scrolledwindow,
overlay, stack, revealer {{
  background-color: transparent;
  background-image: none;
  color: {TEXT};
}}

/* ── TODOS los labels heredan el color ── */
label {{
  color: {TEXT};
  background-color: transparent;
  background-image: none;
}}
.caption, .caption > label {{
  color: {TEXT2};
  font-size: 11px;
}}
.dim-label {{
  color: {TEXT2};
  font-size: 12px;
}}
.status-label {{
  color: {ACCENT2};
  font-size: 12px;
  font-family: monospace;
  font-weight: bold;
}}
.monospace {{
  font-family: monospace;
  color: {GREEN};
  font-size: 12px;
}}

/* ── headerbar ── */
headerbar {{
  background-color: {PANEL};
  background-image: none;
  box-shadow: none;
  border-bottom: 2px solid {ACCENT};
  color: {TEXT};
  min-height: 36px;
  padding: 0 8px;
}}
headerbar > * {{
  color: {TEXT};
}}
headerbar label, headerbar .title {{
  color: {TEXT};
  font-weight: bold;
}}
windowcontrols button {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: 1px solid {BORDER};
  border-radius: 50%;
  min-width: 16px;
  min-height: 16px;
  padding: 2px;
}}
windowcontrols button label {{
  color: {TEXT};
}}

/* ═══════════════════════════════════════════════
   BOTONES — reset completo + estilos propios
   ═══════════════════════════════════════════════ */
button {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 5px 12px;
  min-height: 28px;
  font-size: 12px;
  transition: background-color 120ms, border-color 120ms;
}}
button > label,
button label {{
  color: {TEXT};
  font-size: 12px;
  font-weight: normal;
}}
button:hover {{
  background-color: {WIDGET2};
  background-image: none;
  border-color: {BORDER2};
  color: #ffffff;
}}
button:hover > label,
button:hover label {{
  color: #ffffff;
}}
button:active {{
  background-color: {ACCENT};
  background-image: none;
  border-color: {ACCENT2};
  color: {ON_ACCENT};
}}
button:active > label,
button:active label {{
  color: {ON_ACCENT};
}}
button:disabled {{
  background-color: {PANEL};
  background-image: none;
  color: {MUTED};
  border-color: {BORDER};
  opacity: 0.6;
}}
button:disabled > label,
button:disabled label {{
  color: {MUTED};
}}

/* acción principal */
button.suggested-action {{
  background-color: {ACCENT};
  background-image: none;
  box-shadow: none;
  color: {ON_ACCENT};
  border-color: {ACCENT2};
  font-weight: bold;
}}
button.suggested-action > label,
button.suggested-action label {{
  color: {ON_ACCENT};
  font-weight: bold;
}}
button.suggested-action:hover {{
  background-color: {ACCENT2};
  background-image: none;
  border-color: {ACCENT2};
  color: {ON_ACCENT};
}}
button.suggested-action:hover > label,
button.suggested-action:hover label {{
  color: {ON_ACCENT};
}}

/* acción destructiva */
button.destructive-action {{
  background-color: {RED_BG};
  background-image: none;
  box-shadow: none;
  color: {RED};
  border-color: {RED};
  font-weight: bold;
}}
button.destructive-action > label,
button.destructive-action label {{
  color: {RED};
  font-weight: bold;
}}
button.destructive-action:hover {{
  background-color: {RED_BG_HOVER};
  background-image: none;
  color: #ffffff;
}}
button.destructive-action:hover > label,
button.destructive-action:hover label {{
  color: #ffffff;
}}

/* ── toggle buttons ── */
togglebutton {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 5px 12px;
  min-height: 28px;
  font-size: 12px;
}}
togglebutton > label,
togglebutton label {{
  color: {TEXT};
  font-size: 12px;
}}
togglebutton:hover {{
  background-color: {WIDGET2};
  background-image: none;
  color: #ffffff;
}}
togglebutton:hover > label,
togglebutton:hover label {{
  color: #ffffff;
}}
togglebutton:checked {{
  background-color: {ACCENT};
  background-image: none;
  color: {ON_ACCENT};
  border-color: {ACCENT2};
  font-weight: bold;
}}
togglebutton:checked > label,
togglebutton:checked label {{
  color: {ON_ACCENT};
  font-weight: bold;
}}
togglebutton:checked:hover {{
  background-color: {ACCENT2};
  background-image: none;
  color: {ON_ACCENT};
}}
togglebutton:checked:hover > label,
togglebutton:checked:hover label {{
  color: {ON_ACCENT};
}}

/* ── entradas de texto ── */
entry,
spinbutton {{
  background-color: {PANEL};
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 4px 8px;
  min-height: 26px;
  font-size: 12px;
}}
entry > text,
spinbutton > text {{
  color: {TEXT};
  background-color: transparent;
}}
entry:focus,
spinbutton:focus {{
  border-color: {ACCENT};
  box-shadow: none;
}}
entry placeholder {{
  color: {MUTED};
}}
spinbutton button {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: none;
  border-left: 1px solid {BORDER};
  border-radius: 0;
  min-height: 13px;
  padding: 1px 5px;
}}
spinbutton button > label,
spinbutton button label {{
  color: {TEXT};
}}
spinbutton button:hover {{
  background-color: {WIDGET2};
  background-image: none;
  color: #ffffff;
}}
spinbutton button:hover > label,
spinbutton button:hover label {{
  color: #ffffff;
}}

/* ── dropdown ── */
dropdown,
combobox {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: 1px solid {BORDER};
  border-radius: 6px;
  min-height: 28px;
}}
dropdown > button,
combobox > button {{
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  color: {TEXT};
  border: none;
  padding: 4px 10px;
  min-height: 28px;
}}
dropdown > button > label,
dropdown > button label,
combobox > button > label,
combobox > button label {{
  color: {TEXT};
  font-size: 12px;
}}
dropdown > button:hover,
combobox > button:hover {{
  background-color: {WIDGET2};
  background-image: none;
  color: #ffffff;
}}
dropdown > button:hover > label,
dropdown > button:hover label,
combobox > button:hover > label,
combobox > button:hover label {{
  color: #ffffff;
}}

/* popover del dropdown */
popover {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: 0 4px 16px rgba(0,0,0,0.6);
  border: 1px solid {BORDER};
  border-radius: 8px;
}}
popover > contents {{
  background-color: {WIDGET};
  background-image: none;
  padding: 4px;
}}
popover label {{
  color: {TEXT};
}}

/* lista en popover */
listview {{
  background-color: transparent;
  background-image: none;
  color: {TEXT};
}}
listview > row {{
  background-color: transparent;
  background-image: none;
  padding: 6px 12px;
  border-radius: 5px;
  color: {TEXT};
}}
listview > row > label,
listview > row label {{
  color: {TEXT};
}}
listview > row:hover {{
  background-color: {WIDGET2};
  background-image: none;
  color: #ffffff;
}}
listview > row:hover > label,
listview > row:hover label {{
  color: #ffffff;
}}
listview > row:selected {{
  background-color: {ACCENT};
  background-image: none;
  color: {ON_ACCENT};
}}
listview > row:selected > label,
listview > row:selected label {{
  color: {ON_ACCENT};
  font-weight: bold;
}}

/* ── scale ── */
scale trough {{
  background-color: {PANEL};
  background-image: none;
  border: 1px solid {BORDER};
  border-radius: 4px;
  min-height: 5px;
}}
scale highlight {{
  background-color: {ACCENT};
  background-image: none;
  border-radius: 4px;
}}
scale slider {{
  background-color: {ACCENT2};
  background-image: none;
  box-shadow: none;
  border: 2px solid {ACCENT};
  border-radius: 50%;
  min-width: 15px;
  min-height: 15px;
}}
scale slider:hover {{
  background-color: {ACCENT2};
  background-image: none;
  border-color: {TEXT2};
}}

/* ── scrollbars ── */
scrollbar {{
  background-color: transparent;
  background-image: none;
  margin: 0;
}}
/* SIN min-width/min-height/border propios: en GTK4 (visto en 4.22) ese
   min-size tan chico junto al borde le hacía calcular un tamaño interno
   negativo para el gizmo del slider ("GtkGizmo (slider) reported min
   width -6"). Confirmado por descarte: sacando esto desaparece el warning;
   heredar el tamaño de Adwaita no cambia cómo se ve (verificado en pantalla). */
scrollbar slider {{
  background-color: {WIDGET2};
  background-image: none;
  border-radius: 4px;
  background-clip: padding-box;
}}
scrollbar slider:hover {{
  background-color: {ACCENT};
  background-image: none;
}}

/* ── listbox (pestaña Con vida / Normal en control) ── */
listbox {{
  background-color: {PANEL};
  background-image: none;
  border-radius: 8px;
  border: 1px solid {BORDER};
}}
listbox > row {{
  background-color: transparent;
  background-image: none;
  color: {TEXT};
  padding: 4px;
  border-bottom: 1px solid {BORDER};
}}
listbox > row > * {{
  color: {TEXT};
}}
listbox > row label {{
  color: {TEXT};
}}
listbox > row:hover {{
  background-color: {WIDGET};
  background-image: none;
}}
listbox > row:selected {{
  background-color: {ACCENT};
  background-image: none;
}}
listbox > row:selected label {{
  color: {ON_ACCENT};
}}
/* notebook (pestañas) */
notebook > header {{
  background-color: {PANEL};
  background-image: none;
  border-bottom: 2px solid {BORDER};
}}
notebook > header > tabs > tab {{
  background-color: {WIDGET};
  background-image: none;
  color: {TEXT};
  border-radius: 5px 5px 0 0;
  padding: 6px 14px;
  border: 1px solid {BORDER};
  border-bottom: none;
}}
notebook > header > tabs > tab:checked {{
  background-color: {ACCENT};
  background-image: none;
  color: {ON_ACCENT};
  border-color: {ACCENT};
}}
notebook > header > tabs > tab label {{
  color: {TEXT};
}}
notebook > header > tabs > tab:checked label {{
  color: {ON_ACCENT};
  font-weight: bold;
}}
notebook > stack {{
  background-color: {BG};
  background-image: none;
}}
/* switch */
switch {{
  background-color: {WIDGET2};
  background-image: none;
  border-radius: 14px;
  min-width: 46px;
  min-height: 24px;
}}
switch:checked {{
  background-color: {ACCENT};
  background-image: none;
}}
switch slider {{
  background-color: #ffffff;
  background-image: none;
  border-radius: 50%;
  min-width: 20px;
  min-height: 20px;
  margin: 2px;
}}
/* el track queda blanco al activarse: la perilla pasa a oscura para que
   se siga distinguiendo (blanco sobre blanco sería invisible) */
switch:checked slider {{
  background-color: {ON_ACCENT};
  background-image: none;
}}

/* checkbutton (chips de "poses activas") */
checkbutton check {{
  background-color: {WIDGET2};
  background-image: none;
  border-radius: 4px;
  min-width: 16px;
  min-height: 16px;
  border: 1px solid {BORDER};
  color: {ON_ACCENT};
}}
checkbutton check:checked {{
  background-color: {ACCENT};
  background-image: none;
  border-color: {ACCENT};
  color: {ON_ACCENT};
}}
checkbutton label {{
  font-size: 12px;
}}

/* ── frame ── */
frame {{
  border: 1px solid {BORDER};
  border-radius: 6px;
  background-color: transparent;
  background-image: none;
}}
frame > label {{
  color: {ACCENT2};
  font-weight: bold;
  padding: 0 5px;
}}

/* ── separador ── */
separator {{
  background-color: {BORDER};
  background-image: none;
  min-width: 1px;
  min-height: 1px;
  margin: 3px 0;
}}

/* ── tarjeta (capa activa) ── */
.card {{
  background-color: {WIDGET};
  background-image: none;
  border: 2px solid {ACCENT};
  border-radius: 6px;
  padding: 2px;
}}

/* ── colorbutton ── */
colorbutton {{
  border: 2px solid {BORDER};
  border-radius: 6px;
  min-height: 28px;
  min-width: 60px;
  padding: 2px;
}}
colorbutton:hover {{
  border-color: {ACCENT};
}}

/* ── thumbnail de frame ── */
button.frame-thumb {{
  background-color: {WIDGET};
  background-image: none;
  box-shadow: none;
  border: 1px solid {BORDER};
  border-radius: 5px;
  padding: 2px;
}}
button.frame-thumb > label,
button.frame-thumb label {{
  color: {TEXT};
  font-size: 11px;
}}
button.frame-thumb:hover {{
  background-color: {WIDGET2};
  background-image: none;
  border-color: {BORDER2};
}}
button.frame-thumb:hover > label,
button.frame-thumb:hover label {{
  color: #ffffff;
}}
button.frame-thumb.suggested-action {{
  background-color: {WIDGET2};
  background-image: none;
  border: 2px solid {ACCENT};
}}
button.frame-thumb.suggested-action > label,
button.frame-thumb.suggested-action label {{
  color: #ffffff;
  font-weight: bold;
}}

/* ═══════════════════════════════════════════════
   CARDS de mascota (ventana de control)
   acento neutro (blanco) · fondo casi negro
   ═══════════════════════════════════════════════ */
.mascot-card {{
  background-color: {PANEL};
  background-image: none;
  border: 1px solid {WIDGET};
  border-radius: 12px;
  padding: 10px;
}}
.mascot-card:hover {{
  border-color: {ACCENT};
}}
.mascot-card.card-life {{
  border-left: 3px solid {ACCENT};
}}
.card-title {{
  font-weight: bold;
  font-size: 1.05em;
  color: #ffffff;
}}
entry.card-title {{
  background-color: transparent;
  background-image: none;
  border: 1px solid transparent;
  padding: 2px 4px;
  min-height: 0;
}}
entry.card-title:focus {{
  background-color: {WIDGET};
  border: 1px solid {ACCENT};
}}
.card-meta {{
  color: {TEXT2};
  font-size: 0.9em;
}}
.card-preview {{
  background-color: {BG2};
  border: 1px solid {WIDGET};
  border-radius: 8px;
}}
button.accent {{
  background-color: {ACCENT};
  background-image: none;
  border: none;
  color: {ON_ACCENT};
}}
button.accent:hover {{
  background-color: {ACCENT2};
  background-image: none;
}}
button.accent > label,
button.accent label {{
  color: {ON_ACCENT};
}}
.section-head {{
  font-weight: bold;
  font-size: 1.1em;
  color: #ffffff;
}}

/* ═══════════════════════════════════════════════
   EDITORES — chrome profesional tipo Clip Studio Paint
   ═══════════════════════════════════════════════ */
.editor-toolbar {{
  background-color: {BG2};
  background-image: none;
  border-bottom: 1px solid {BORDER};
  padding: 4px 6px;
}}
.editor-panel {{
  background-color: {BG2};
  background-image: none;
  border-right: 1px solid {BORDER};
}}
.editor-panel.right {{
  border-right: none;
  border-left: 1px solid {BORDER};
}}
.editor-statusbar {{
  background-color: {BG2};
  background-image: none;
  border-top: 1px solid {BORDER};
  color: {TEXT2};
}}
.panel-head {{
  color: {TEXT2};
  font-size: 0.75em;
  font-weight: bold;
  margin: 6px 2px 2px 2px;
}}
/* botones de herramienta: cuadrados, planos, acento al estar activos */
button.tool-btn {{
  background-color: transparent;
  background-image: none;
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 5px;
  min-width: 18px;
  min-height: 18px;
}}
button.tool-btn:hover {{
  background-color: {WIDGET};
}}
button.tool-btn:checked,
button.tool-btn.active {{
  background-color: {ACCENT};
  background-image: none;
  border-color: {ACCENT2};
  color: {ON_ACCENT};
}}
/* botón de cerrar (X): rojo al pasar el ratón */
button.close-btn:hover {{
  background-color: {RED_BG_HOVER};
  background-image: none;
  border-color: {RED};
}}
button.close-btn:hover label,
button.close-btn:hover > label {{
  color: #ffffff;
}}
/* línea de tiempo / tira de fotogramas */
.timeline {{
  background-color: {BG2};
  background-image: none;
}}
button.frame-cell {{
  background-color: {WIDGET};
  background-image: none;
  border: 1px solid {BORDER};
  border-radius: 7px;
  padding: 3px;
}}
button.frame-cell:hover {{
  border-color: {ACCENT};
}}
button.frame-cell.current {{
  border: 2px solid {ACCENT};
  background-color: {WIDGET2};
}}
button.frame-cell label {{
  color: {TEXT2};
  font-size: 0.78em;
}}
button.frame-cell.current label {{
  color: #ffffff;
}}

/* ═══════════════════════════════════════════════
   GUÍA DE POSES — diálogo "¿Cómo crear poses?"
   ═══════════════════════════════════════════════ */
.pose-row {{
  background-color: {PANEL};
  background-image: none;
  border: 1px solid {WIDGET};
  border-radius: 10px;
  padding: 8px 10px;
}}
.pose-row:hover {{
  border-color: {ACCENT};
}}
.pose-row.pose-mandatory {{
  border-left: 3px solid {ACCENT};
}}
.pose-emoji {{
  font-size: 1.5em;
  min-width: 34px;
  min-height: 34px;
}}
.pose-emoji-badge {{
  background-color: {WIDGET};
  background-image: none;
  border-radius: 999px;
}}
.pose-name {{
  font-weight: bold;
  font-family: monospace;
  color: #ffffff;
}}
.pose-desc {{
  color: {TEXT2};
  font-size: 0.92em;
}}
.badge {{
  border-radius: 999px;
  padding: 2px 9px;
  font-size: 0.78em;
  font-weight: bold;
}}
.badge-mandatory {{
  background-color: {ACCENT};
  background-image: none;
  color: {ON_ACCENT};
}}
.badge-optional {{
  background-color: {WIDGET};
  background-image: none;
  color: {TEXT2};
  border: 1px solid {BORDER};
}}
.step-num {{
  background-color: {ACCENT};
  background-image: none;
  color: {ON_ACCENT};
  border-radius: 999px;
  min-width: 24px;
  min-height: 24px;
  font-weight: bold;
  font-size: 0.85em;
}}
.step-text {{
  color: {TEXT};
}}
.folder-tree {{
  background-color: {BG2};
  background-image: none;
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 10px 12px;
  color: {TEXT2};
  font-family: monospace;
  font-size: 0.92em;
}}
.folder-tree .folder-required {{
  color: {GREEN};
}}
.note-box {{
  background-color: {WIDGET};
  background-image: none;
  border-left: 3px solid {ACCENT};
  border-radius: 6px;
  padding: 8px 10px;
  color: {TEXT2};
  font-size: 0.92em;
}}
"""

def _css_modern():
    return f"""
/* ═══════════════════════════════════════════════
   MODERNO — transiciones suaves, degradados y brillos
   ═══════════════════════════════════════════════ */
button {{
  border-radius: 10px;
  transition: background-color 180ms ease, border-color 180ms ease,
              box-shadow 220ms ease, opacity 160ms ease;
}}
button:hover {{
  box-shadow: 0 6px 18px -8px rgba({A_RGB},0.55);
}}
button:active {{
  box-shadow: none;
}}
button.suggested-action {{
  background-image: linear-gradient(to right, {G1}, {ACCENT} 62%, {G2});
  border-color: transparent;
  box-shadow: 0 8px 26px -10px rgba({A_RGB},0.75);
}}
button.suggested-action:hover {{
  background-image: linear-gradient(to right, {G1}, {ACCENT} 62%, {G2});
  border-color: transparent;
  box-shadow: 0 12px 34px -8px rgba({G1_RGB},0.7);
}}
togglebutton:checked {{
  background-image: linear-gradient(to right, {G1}, {ACCENT});
  border-color: transparent;
}}
switch {{
  border-radius: 999px;
  transition: background-color 220ms ease, border-color 220ms ease;
}}
switch:checked {{
  background-image: linear-gradient(to right, {G1}, {ACCENT});
  border-color: transparent;
}}
switch slider {{
  transition: margin 200ms ease, background-color 200ms ease;
}}
scale highlight {{
  background-image: linear-gradient(to right, {G1}, {ACCENT});
}}
entry, spinbutton {{
  border-radius: 10px;
  transition: border-color 180ms ease, box-shadow 220ms ease;
}}
entry:focus, spinbutton:focus {{
  box-shadow: 0 0 0 3px rgba({A_RGB},0.22);
}}
popover > contents {{
  border-radius: 14px;
  border: 1px solid {BORDER2};
  box-shadow: 0 18px 44px -14px rgba(0,0,0,0.85);
}}
tooltip {{
  border-radius: 8px;
}}

/* ── ventana principal (control) ── */
window.ctl {{
  background-color: {BG};
  background-image:
    radial-gradient(circle at 12% -8%, rgba({G2_RGB},0.30), transparent 42%),
    radial-gradient(circle at 96% 2%, rgba({G1_RGB},0.17), transparent 38%);
}}
.ctl-header {{
  padding: 12px 18px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  background-color: rgba(20,18,28,0.55);
}}
.ctl-logo {{
  border-radius: 12px;
  background-image: linear-gradient(135deg, rgba({G1_RGB},0.35), rgba({A_RGB},0.35));
  padding: 3px;
}}
.ctl-title {{
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.3px;
}}
.chip {{
  background-color: rgba({A_RGB},0.16);
  color: {ACCENT2};
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 700;
}}
.ctl-search {{
  border-radius: 999px;
  padding: 4px 14px;
  min-height: 34px;
  background-color: rgba(255,255,255,0.05);
  border-color: rgba(255,255,255,0.08);
}}
.ctl-search:focus-within {{
  border-color: {ACCENT};
  background-color: rgba(255,255,255,0.08);
}}
.ghost {{
  background-color: transparent;
  border-color: transparent;
  color: {TEXT2};
}}
.ghost:hover {{
  background-color: rgba(255,255,255,0.07);
  border-color: transparent;
  box-shadow: none;
}}
.pill {{
  border-radius: 999px;
  padding: 6px 16px;
}}
.seg {{
  background-color: rgba(255,255,255,0.05);
  border-radius: 14px;
  padding: 3px;
}}
.seg togglebutton {{
  background-color: transparent;
  background-image: none;
  border: none;
  border-radius: 11px;
  padding: 6px 16px;
  color: {TEXT2};
  transition: background-color 200ms ease, color 200ms ease;
}}
.seg togglebutton label {{
  color: {TEXT2};
  font-weight: 600;
}}
.seg togglebutton:hover {{
  background-color: rgba(255,255,255,0.07);
  box-shadow: none;
}}
.seg togglebutton:checked {{
  background-image: linear-gradient(to right, rgba({G1_RGB},0.28), rgba({A_RGB},0.34));
  color: #ffffff;
  box-shadow: inset 0 0 0 1px rgba({A_RGB},0.45);
}}
.seg togglebutton:checked label {{
  color: #ffffff;
}}
.upd-banner {{
  background-image: linear-gradient(to right, rgba({G1_RGB},0.18), rgba({A_RGB},0.20));
  border: 1px solid rgba({A_RGB},0.38);
  border-radius: 14px;
  padding: 8px 14px;
}}
.ctl-status {{
  color: {TEXT2};
  font-size: 12px;
}}

/* ── tarjetas de mascota ── */
@keyframes card-in {{
  from {{ opacity: 0; margin-top: 18px; }}
  to   {{ opacity: 1; margin-top: 0; }}
}}
.mcard {{
  background-color: {CARD};
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 20px;
  box-shadow: 0 12px 32px -20px rgba(0,0,0,0.95);
  animation: card-in 460ms cubic-bezier(0.2,0.8,0.2,1) both;
  transition: border-color 220ms ease, box-shadow 280ms ease, background-color 280ms ease;
}}
.mcard:hover {{
  background-color: {CARD2};
  border-color: rgba({A_RGB},0.55);
  box-shadow: 0 22px 46px -18px rgba({A_RGB},0.38);
}}
.mcard.on-desktop {{
  border-color: rgba({OK_RGB},0.34);
}}
.mcard.d0  {{ animation-delay: 0ms; }}   .mcard.d1  {{ animation-delay: 45ms; }}
.mcard.d2  {{ animation-delay: 90ms; }}  .mcard.d3  {{ animation-delay: 135ms; }}
.mcard.d4  {{ animation-delay: 180ms; }} .mcard.d5  {{ animation-delay: 225ms; }}
.mcard.d6  {{ animation-delay: 270ms; }} .mcard.d7  {{ animation-delay: 315ms; }}
.mcard.d8  {{ animation-delay: 360ms; }} .mcard.d9  {{ animation-delay: 405ms; }}
.mcard.d10 {{ animation-delay: 450ms; }} .mcard.d11 {{ animation-delay: 495ms; }}
.mcard-stage {{
  border-radius: 15px;
  margin: 10px 10px 4px 10px;
  background-image:
    radial-gradient(circle at 50% 42%, rgba({A_RGB},0.26), transparent 66%),
    linear-gradient(to bottom, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
}}
.mbadge {{
  border-radius: 999px;
  padding: 2px 9px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.3px;
  margin: 8px;
}}
.mbadge-life {{ background-color: rgba({G1_RGB},0.22); color: {G1L}; }}
.mbadge-gif  {{ background-color: rgba({G2_RGB},0.17);  color: {G2L}; }}
.mbadge-live {{ background-color: rgba({OK_RGB},0.20); color: {GREEN}; }}
entry.mcard-title {{
  background-color: transparent;
  border-color: transparent;
  box-shadow: none;
  font-size: 15px;
  font-weight: 700;
  padding: 2px 6px;
  min-height: 24px;
}}
entry.mcard-title:hover {{
  background-color: rgba(255,255,255,0.05);
}}
entry.mcard-title:focus {{
  background-color: rgba(255,255,255,0.07);
  border-color: {ACCENT};
}}
.mcard-meta {{
  color: {TEXT2};
  font-size: 11.5px;
  margin: 0 12px 2px 12px;
}}
.mcard-actions {{
  padding: 8px 10px 12px 12px;
}}
.mcard-actions label.sw-label {{
  color: {TEXT2};
  font-size: 12px;
}}
.menu-item {{
  background-color: transparent;
  border-color: transparent;
  border-radius: 9px;
  padding: 6px 10px;
  min-height: 24px;
}}
.menu-item:hover {{
  background-color: rgba({A_RGB},0.18);
  box-shadow: none;
}}
.menu-item.danger label {{ color: {RED}; }}
.menu-item.danger:hover {{ background-color: rgba({RED_RGB},0.16); }}
.menu-sep {{
  background-color: rgba(255,255,255,0.08);
  min-height: 1px;
  margin: 4px 0;
}}
.menu-title {{
  color: {TEXT2};
  font-size: 11px;
  font-weight: 700;
  margin: 4px 10px 2px 10px;
}}

/* ── estado vacío y arrastrar/soltar ── */
.empty-title {{
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.4px;
}}
.empty-sub {{
  color: {TEXT2};
  font-size: 14px;
}}
.drop-hint {{
  background-color: rgba({A_RGB},0.14);
  border: 2px dashed rgba({A_RGB},0.85);
  border-radius: 24px;
  margin: 14px;
}}
.drop-hint label {{
  font-size: 22px;
  font-weight: 800;
}}

/* ── diálogo «nueva mascota» ── */
.opt-card {{
  background-color: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.09);
  border-radius: 18px;
  padding: 16px 10px;
}}
.opt-card:hover {{
  background-color: rgba({A_RGB},0.13);
  border-color: rgba({A_RGB},0.6);
  box-shadow: 0 14px 34px -16px rgba({A_RGB},0.6);
}}
.opt-title {{
  font-size: 14px;
  font-weight: 800;
}}

.card-preview {{
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
}}

/* ── selector de tema y tutorial ── */
button.swatch {{
  padding: 4px;
  min-width: 28px;
  min-height: 28px;
  border-radius: 999px;
  background-color: transparent;
  border: 2px solid transparent;
}}
button.swatch:hover {{
  background-color: rgba(255,255,255,0.08);
  box-shadow: none;
}}
button.swatch.swatch-on {{
  border-color: {TEXT};
}}
window.tour {{
  background-color: {BG};
  background-image:
    radial-gradient(circle at 50% -10%, rgba({A_RGB},0.30), transparent 55%),
    radial-gradient(circle at 100% 100%, rgba({G1_RGB},0.14), transparent 45%);
}}
.tour-emoji {{
  font-size: 64px;
  margin-bottom: 4px;
}}
.tour-bullet {{
  background-color: rgba(255,255,255,0.05);
  border-radius: 12px;
  padding: 9px 14px;
  font-size: 13px;
}}
.tour-dots {{
  font-size: 12px;
  letter-spacing: 2px;
}}
"""


_provider: Gtk.CssProvider | None = None
_theme_id: str | None = None


def _load_theme_id():
    try:
        from .. import settings
        return settings.get("theme", DEFAULT_THEME)
    except Exception:  # noqa: BLE001
        return DEFAULT_THEME


def _make_provider():
    prov = Gtk.CssProvider()
    prov.load_from_data((_css_main() + _css_modern()).encode("utf-8"))
    return prov


def _get_provider() -> Gtk.CssProvider:
    global _provider, _theme_id
    if _provider is None:
        _theme_id = _load_theme_id()
        globals().update(build_palette(resolve(_theme_id)))
        _provider = _make_provider()
    return _provider


def current_theme() -> str:
    _get_provider()
    return _theme_id or DEFAULT_THEME


def set_theme(theme_id: str, save: bool = True):
    """Cambia el tema de color en caliente: todas las ventanas se repintan."""
    global _provider, _theme_id
    display = Gdk.Display.get_default()
    _get_provider()
    old = _provider
    _theme_id = theme_id
    globals().update(build_palette(resolve(theme_id)))
    _provider = _make_provider()
    if display:
        if old is not None:
            Gtk.StyleContext.remove_provider_for_display(display, old)
        Gtk.StyleContext.add_provider_for_display(display, _provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    if save:
        try:
            from .. import settings
            settings.set_val("theme", theme_id)
        except Exception:  # noqa: BLE001
            pass


def apply(widget_or_window):
    """Aplica el tema con prioridad USER (800) — por encima de todo Adwaita."""
    try:
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                _get_provider(),
                Gtk.STYLE_PROVIDER_PRIORITY_USER,
            )
    except Exception:
        pass
