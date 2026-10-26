"""
Diálogo «Exportar como sticker»: elige plataforma (y pose, si la mascota
tiene varias) y guarda el archivo listo para Telegram, Discord o WhatsApp.
"""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .. import stickers  # noqa: E402
from ..i18n import tr  # noqa: E402


class StickerDialog(Gtk.Window):
    def __init__(self, parent, name, fps, frames_loader, poses=("default",)):
        """frames_loader(pose) -> [PIL.Image RGBA]"""
        super().__init__(title=tr("Exportar como sticker"))
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(420, 10)
        self._name, self._fps, self._load = name, fps, frames_loader
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(18)
        self.set_child(box)

        box.append(Gtk.Label(label=tr("¿Para dónde es el sticker?"), xalign=0))
        self._targets = list(stickers.TARGETS)
        self._dd = Gtk.DropDown.new_from_strings(
            [tr(stickers.TARGETS[k]["name"]) for k in self._targets])
        box.append(self._dd)
        self._poses = list(poses)
        self._pose_dd = None
        if len(self._poses) > 1:
            box.append(Gtk.Label(label=tr("Pose"), xalign=0))
            self._pose_dd = Gtk.DropDown.new_from_strings(self._poses)
            box.append(self._pose_dd)
        self._hint = Gtk.Label(xalign=0)
        self._hint.set_wrap(True)
        self._hint.add_css_class("dim-label")
        box.append(self._hint)
        self._dd.connect("notify::selected", lambda *_: self._update_hint())
        self._update_hint()

        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Cancelar"))
        cancel.connect("clicked", lambda _b: self.destroy())
        self._ok = Gtk.Button(label=tr("Guardar…"))
        self._ok.add_css_class("suggested-action")
        self._ok.connect("clicked", lambda _b: self._choose_file())
        row.append(cancel)
        row.append(self._ok)
        box.append(row)

    def _target(self):
        return self._targets[self._dd.get_selected()]

    def _update_hint(self):
        k = self._target()
        c = stickers.TARGETS[k]
        txt = {
            "telegram": tr("512 px, hasta 3 segundos y 256 KB. Súbelo con @Stickers en Telegram (/newvideo)."),
            "discord": tr("320×320 y hasta 512 KB. Servidor → Ajustes → Stickers → Subir."),
            "whatsapp": tr("512×512 y hasta 500 KB. Pásalo a tu móvil y añádelo con una app de stickers."),
            "gif": tr("Lado mayor de {px} px. Sirve en casi cualquier chat.", px=c["size"]),
        }[k]
        if k == "telegram" and not stickers.ffmpeg_ok():
            txt += "\n" + tr("⚠ Falta ffmpeg con VP9: instálalo para este formato.")
        self._hint.set_text(txt)

    def _choose_file(self):
        k = self._target()
        dlg = Gtk.FileDialog()
        dlg.set_title(tr("Guardar sticker"))
        dlg.set_initial_name(f"{self._name}{stickers.TARGETS[k]['ext']}")
        dlg.save(self, None, self._save)

    def _save(self, dlg, res):
        try:
            gf = dlg.save_finish(res)
        except GLib.Error:
            return
        path, k = gf.get_path(), self._target()
        pose = self._poses[self._pose_dd.get_selected()] if self._pose_dd else "default"
        self._ok.set_sensitive(False)
        self._hint.set_text(tr("Creando el sticker…"))

        def work():
            try:
                out, kb = stickers.export(self._load(pose), self._fps, k, path)
                msg = tr("Listo: {name} ({kb} KB)", name=out.name, kb=round(kb))
                ok = True
            except Exception as e:  # noqa: BLE001
                msg, ok = tr(str(e)), False
            GLib.idle_add(self._done, msg, ok, path)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, msg, ok, path):
        self._ok.set_sensitive(True)
        self._hint.set_text(msg)
        if ok:
            from ..backends import current as backend
            backend.open_folder(str(Gio.File.new_for_path(path).get_parent().get_path()))
        return False
