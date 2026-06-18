"""
Tema profesional para AnimaLinux — prioridad USER (800) para vencer Adwaita.
"""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

# Paleta (UI v2 — acento #7B61FF, fondo #1a1a2e)
BG      = "#1a1a2e"   # fondo general — azul noche muy oscuro
PANEL   = "#16213e"   # paneles laterales / cards — azul profundo
WIDGET  = "#243352"   # fondo de widgets (botones, entradas)
WIDGET2 = "#33476b"   # hover / resaltado leve
ACCENT  = "#7B61FF"   # morado/violeta (acento principal del spec)
ACCENT2 = "#9079ff"   # hover del acento
TEXT    = "#cdd6f4"   # texto principal — blanco azulado
TEXT2   = "#a6adc8"   # texto secundario
BORDER  = "#45475a"   # borde estándar
RED     = "#f38ba8"   # destructivo
GREEN   = "#a6e3a1"   # confirmación

_CSS = f"""
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
  border-color: #6c7086;
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
  color: #ffffff;
}}
button:active > label,
button:active label {{
  color: #ffffff;
}}
button:disabled {{
  background-color: {PANEL};
  background-image: none;
  color: #585b70;
  border-color: #313244;
  opacity: 0.6;
}}
button:disabled > label,
button:disabled label {{
  color: #585b70;
}}

/* acción principal */
button.suggested-action {{
  background-color: {ACCENT};
  background-image: none;
  box-shadow: none;
  color: #ffffff;
  border-color: {ACCENT2};
  font-weight: bold;
}}
button.suggested-action > label,
button.suggested-action label {{
  color: #ffffff;
  font-weight: bold;
}}
button.suggested-action:hover {{
  background-color: {ACCENT2};
  background-image: none;
  border-color: #b4a4ff;
  color: #ffffff;
}}
button.suggested-action:hover > label,
button.suggested-action:hover label {{
  color: #ffffff;
}}

/* acción destructiva */
button.destructive-action {{
  background-color: #5c2230;
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
  background-color: #7c2e40;
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
  color: #ffffff;
  border-color: {ACCENT2};
  font-weight: bold;
}}
togglebutton:checked > label,
togglebutton:checked label {{
  color: #ffffff;
  font-weight: bold;
}}
togglebutton:checked:hover {{
  background-color: {ACCENT2};
  background-image: none;
  color: #ffffff;
}}
togglebutton:checked:hover > label,
togglebutton:checked:hover label {{
  color: #ffffff;
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
  color: #585b70;
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
  color: #ffffff;
}}
listview > row:selected > label,
listview > row:selected label {{
  color: #ffffff;
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
  background-color: #c4b5fd;
  background-image: none;
  border-color: {ACCENT2};
}}

/* ── scrollbars ── */
scrollbar {{
  background-color: transparent;
  background-image: none;
  margin: 0;
}}
scrollbar slider {{
  background-color: {WIDGET2};
  background-image: none;
  border-radius: 4px;
  min-width: 6px;
  min-height: 6px;
  border: 2px solid transparent;
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
  color: #ffffff;
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
  color: #ffffff;
  border-color: {ACCENT};
}}
notebook > header > tabs > tab label {{
  color: {TEXT};
}}
notebook > header > tabs > tab:checked label {{
  color: #ffffff;
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
  background-color: #1e1b38;
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
  border-color: #6c7086;
}}
button.frame-thumb:hover > label,
button.frame-thumb:hover label {{
  color: #ffffff;
}}
button.frame-thumb.suggested-action {{
  background-color: #2d2b5e;
  background-image: none;
  border: 2px solid {ACCENT};
}}
button.frame-thumb.suggested-action > label,
button.frame-thumb.suggested-action label {{
  color: #ffffff;
  font-weight: bold;
}}

/* ═══════════════════════════════════════════════
   CARDS de mascota (ventana de control, UI v2)
   acento #7B61FF · fondo #1a1a2e · card #16213e
   ═══════════════════════════════════════════════ */
.mascot-card {{
  background-color: #16213e;
  background-image: none;
  border: 1px solid #243352;
  border-radius: 12px;
  padding: 10px;
}}
.mascot-card:hover {{
  border-color: #7B61FF;
}}
.mascot-card.card-life {{
  border-left: 3px solid #7B61FF;
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
  border: 1px solid #7B61FF;
}}
.card-meta {{
  color: {TEXT2};
  font-size: 0.9em;
}}
.card-preview {{
  background-color: #0e1730;
  border: 1px solid #243352;
  border-radius: 8px;
}}
button.accent {{
  background-color: #7B61FF;
  background-image: none;
  border: none;
  color: #ffffff;
}}
button.accent:hover {{
  background-color: #9079ff;
  background-image: none;
}}
button.accent > label,
button.accent label {{
  color: #ffffff;
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
  background-color: #14142a;
  background-image: none;
  border-bottom: 1px solid #2a2a45;
  padding: 4px 6px;
}}
.editor-panel {{
  background-color: #14142a;
  background-image: none;
  border-right: 1px solid #2a2a45;
}}
.editor-panel.right {{
  border-right: none;
  border-left: 1px solid #2a2a45;
}}
.editor-statusbar {{
  background-color: #14142a;
  background-image: none;
  border-top: 1px solid #2a2a45;
  color: {TEXT2};
}}
.panel-head {{
  color: #8b8fa7;
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
  background-color: #243352;
}}
button.tool-btn:checked,
button.tool-btn.active {{
  background-color: #7B61FF;
  background-image: none;
  border-color: #9079ff;
}}
/* botón de cerrar (X): rojo al pasar el ratón */
button.close-btn:hover {{
  background-color: #e05260;
  background-image: none;
  border-color: #f06a78;
}}
button.close-btn:hover label,
button.close-btn:hover > label {{
  color: #ffffff;
}}
/* línea de tiempo / tira de fotogramas */
.timeline {{
  background-color: #101023;
  background-image: none;
}}
button.frame-cell {{
  background-color: #1b1b34;
  background-image: none;
  border: 1px solid #2a2a45;
  border-radius: 7px;
  padding: 3px;
}}
button.frame-cell:hover {{
  border-color: #7B61FF;
}}
button.frame-cell.current {{
  border: 2px solid #7B61FF;
  background-color: #241f45;
}}
button.frame-cell label {{
  color: {TEXT2};
  font-size: 0.78em;
}}
button.frame-cell.current label {{
  color: #ffffff;
}}
"""

_provider: Gtk.CssProvider | None = None


def _get_provider() -> Gtk.CssProvider:
    global _provider
    if _provider is None:
        _provider = Gtk.CssProvider()
        _provider.load_from_data(_CSS.encode("utf-8"))
    return _provider


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
