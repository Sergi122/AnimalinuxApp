"""
Piezas reutilizables para diálogos de guía/tutorial (poses, editores…).
Mismo lenguaje visual que theme.py: tarjetas en vez de texto plano.
"""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def section_title(text):
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.add_css_class("section-head")
    lbl.set_margin_top(4)
    return lbl


def body(text):
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.set_wrap(True)
    lbl.add_css_class("dim-label")
    return lbl


def note(text):
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.set_wrap(True)
    lbl.add_css_class("dim-label")
    row = Gtk.Box()
    row.add_css_class("note-box")
    row.append(lbl)
    return row


def step_row(n, text):
    row = Gtk.Box(spacing=10)
    num = Gtk.Label(label=str(n))
    num.add_css_class("step-num")
    num.set_halign(Gtk.Align.CENTER); num.set_valign(Gtk.Align.START)
    row.append(num)
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.set_wrap(True)
    lbl.add_css_class("step-text")
    lbl.set_valign(Gtk.Align.CENTER)
    row.append(lbl)
    return row


def emoji_badge(emoji):
    lbl = Gtk.Label(label=emoji)
    lbl.add_css_class("pose-emoji")
    lbl.add_css_class("pose-emoji-badge")
    lbl.set_halign(Gtk.Align.CENTER); lbl.set_valign(Gtk.Align.CENTER)
    return lbl


def icon_badge(icon_widget):
    holder = Gtk.Box()
    holder.add_css_class("pose-emoji-badge")
    holder.set_size_request(34, 34)
    holder.set_halign(Gtk.Align.CENTER); holder.set_valign(Gtk.Align.CENTER)
    holder.append(icon_widget)
    return holder


def item_row(badge_widget, name, desc=None, tag_text=None, tag_kind="optional",
             highlight=False):
    """Fila tipo tarjeta: icono/emoji + nombre + descripción + etiqueta opcional
    (badge_kind: "mandatory" da fondo de acento, "optional" gris)."""
    row = Gtk.Box(spacing=10)
    row.add_css_class("pose-row")
    if highlight:
        row.add_css_class("pose-mandatory")
    if badge_widget is not None:
        row.append(badge_widget)

    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    info.set_hexpand(True)
    name_lbl = Gtk.Label(label=name, xalign=0)
    name_lbl.add_css_class("pose-name")
    info.append(name_lbl)
    if desc:
        desc_lbl = Gtk.Label(label=desc, xalign=0)
        desc_lbl.set_wrap(True)
        desc_lbl.add_css_class("pose-desc")
        info.append(desc_lbl)
    row.append(info)

    if tag_text:
        pill = Gtk.Label(label=tag_text)
        pill.add_css_class("badge")
        pill.add_css_class("badge-mandatory" if tag_kind == "mandatory" else "badge-optional")
        pill.set_valign(Gtk.Align.CENTER)
        row.append(pill)
    return row
