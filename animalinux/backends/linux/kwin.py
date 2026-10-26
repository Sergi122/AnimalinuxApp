"""
Puente con KWin (KDE Plasma en Wayland).

KWin soporta wlr-layer-shell, así que las mascotas usan el mismo overlay que en
Hyprland. Lo que Wayland no deja saber a una app —dónde están las ventanas,
dónde está el cursor, en qué escritorio estás, si hay algo a pantalla
completa— lo cuenta un pequeño script de KWin que cargamos por D-Bus
(org.kde.KWin /Scripting) y que nos llama a nosotros:

    dev.animalinux.App  /dev/animalinux/KWinBridge
    dev.animalinux.KWinBridge.Push(tipo, json) -> intervalo_cursor_ms

tipo = "windows" | "desktop" | "cursor" | "fullscreen". La respuesta le dice
al script cada cuánto mandar el cursor (0 = no lo mandes): solo se pide
mientras alguna mascota juega con él, así KWin no nos despierta en balde.
"""
import json
import os
import time

from gi.repository import Gio, GLib

_DEBUG = bool(os.environ.get("ANIMALINUX_DEBUG"))
BUS_PATH = "/dev/animalinux/KWinBridge"
IFACE = "dev.animalinux.KWinBridge"
PLUGIN = "animalinux-bridge"

_XML = f"""<node><interface name="{IFACE}">
<method name="Push"><arg type="s" direction="in"/><arg type="s" direction="in"/>
<arg type="i" direction="out"/></method></interface></node>"""

# Script de KWin (Plasma 6). Sin temporizadores: todo por señales; el cursor
# se limita por tiempo dentro del propio script.
_SCRIPT = r"""
var SVC = "%(svc)s", PATH = "%(path)s", IFACE = "%(iface)s";
var cursorEvery = 0, lastCursor = 0, pending = false, lastWin = "";
function push(kind, data) {
    callDBus(SVC, PATH, IFACE, "Push", kind, JSON.stringify(data), function (r) {
        if (typeof r === "number") cursorEvery = r;
    });
}
function deskNum() {
    var d = workspace.currentDesktop;
    if (d.x11DesktopNumber !== undefined) return d.x11DesktopNumber;
    var all = workspace.desktops;
    for (var i = 0; i < all.length; i++) if (all[i].id === d.id) return i + 1;
    return -1;
}
function onDesk(w) {
    if (w.onAllDesktops) return true;
    var d = w.desktops || [], cur = workspace.currentDesktop.id;
    for (var i = 0; i < d.length; i++) if (d[i].id === cur) return true;
    return false;
}
function sendWindows() {
    pending = false;
    var out = [], fs = false, list = workspace.windowList();
    for (var i = 0; i < list.length; i++) {
        var w = list[i];
        if (!(w.normalWindow || w.dialog) || w.minimized || w.skipTaskbar) continue;
        if (!onDesk(w)) continue;
        var g = w.frameGeometry;
        out.push([g.x, g.y, g.x + g.width, g.y + g.height]);
        if (w.fullScreen && w.active) fs = true;
    }
    // solo si cambió algo (las propias mascotas también son superficies que
    // se mueven y KWin avisa de cada movimiento)
    var key = JSON.stringify(out) + fs;
    if (key !== lastWin) { lastWin = key; push("windows", {rects: out, fullscreen: fs}); }
    sendArea();
}
var lastArea = "";
function sendArea() {
    // área de trabajo (sin paneles) de cada pantalla: el suelo de las mascotas
    var outs = workspace.screens || [], areas = [];
    for (var i = 0; i < outs.length; i++) {
        var a = workspace.clientArea(KWin.MaximizeArea, outs[i], workspace.currentDesktop);
        var g = outs[i].geometry;
        areas.push([g.x, g.y, g.width, g.height, a.x, a.y, a.width, a.height]);
    }
    var key = JSON.stringify(areas);
    if (key !== lastArea) { lastArea = key; push("area", {areas: areas}); }
}
function soon() { if (!pending) { pending = true; sendWindows(); } }
function hook(w) {
    // solo ventanas de verdad: las mascotas (layer-shell) se mueven sin parar
    if (!(w.normalWindow || w.dialog)) return;
    w.frameGeometryChanged.connect(soon);
    w.minimizedChanged.connect(soon);
    if (w.fullScreenChanged) w.fullScreenChanged.connect(soon);
    if (w.desktopsChanged) w.desktopsChanged.connect(soon);
}
var all = workspace.windowList();
for (var i = 0; i < all.length; i++) hook(all[i]);
workspace.windowAdded.connect(function (w) { hook(w); soon(); });
workspace.windowRemoved.connect(soon);
workspace.windowActivated.connect(soon);
var lastDesk = deskNum();
workspace.currentDesktopChanged.connect(function () {
    var now = deskNum();
    push("desktop", {from: lastDesk, to: now});
    lastDesk = now;
    soon();
});
workspace.cursorPosChanged.connect(function () {
    if (cursorEvery <= 0) return;
    var t = Date.now();
    if (t - lastCursor < cursorEvery) return;
    lastCursor = t;
    var p = workspace.cursorPos;
    push("cursor", {x: p.x, y: p.y});
});
sendWindows();
push("desktop", {from: -1, to: lastDesk});
var p0 = workspace.cursorPos;
push("cursor", {x: p0.x, y: p0.y});
"""


def is_kde_wayland():
    desk = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return "KDE" in desk and bool(os.environ.get("WAYLAND_DISPLAY"))


class KWinBridge:
    def __init__(self):
        self.rects = None            # [(x0, y0, x1, y1)] globales o None
        self.fullscreen = False
        self.cursor = None           # (x, y, instante)
        self.desktop = None          # número del escritorio actual
        self.areas = []              # [(mon_x, mon_y, w, h, area_x, area_y, aw, ah)]
        self._area_cbs = []
        self.ok = False
        self._desk_cbs = []
        self._fs_cbs = []
        self._cursor_wants = {}      # quién -> ms
        self._reg = 0
        self._conn = None
        self._script_id = None

    # ── arranque ──────────────────────────────────────────────────────────
    def start(self, app):
        conn = app.get_dbus_connection()
        if conn is None:
            return False
        self._conn = conn
        try:
            node = Gio.DBusNodeInfo.new_for_xml(_XML)
            self._reg = conn.register_object(
                BUS_PATH, node.interfaces[0], self._on_call, None, None)
        except GLib.Error:
            return False
        from ... import paths
        paths.ensure_dirs()
        js = paths.RUNTIME_DIR / "kwin-bridge.js"
        js.write_text(_SCRIPT % {"svc": app.get_application_id(),
                                 "path": BUS_PATH, "iface": IFACE},
                      encoding="utf-8")
        try:
            self._kwin("/Scripting", "org.kde.kwin.Scripting", "unloadScript",
                       GLib.Variant("(s)", (PLUGIN,)))
            res = self._kwin("/Scripting", "org.kde.kwin.Scripting", "loadScript",
                             GLib.Variant("(ss)", (str(js), PLUGIN)))
            sid = res.unpack()[0]
            if sid < 0:
                return False
            self._script_id = sid
            # Plasma 6: /Scripting/Script<N>; Plasma 5: /<N>
            for path in (f"/Scripting/Script{sid}", f"/{sid}"):
                try:
                    self._kwin(path, "org.kde.kwin.Script", "run", None)
                    break
                except GLib.Error:
                    continue
        except GLib.Error as e:
            if _DEBUG:
                print(f"[kwin] no se pudo cargar el script: {e}", flush=True)
            return False
        if _DEBUG:
            print(f"[kwin] script {sid} cargado", flush=True)
        self.ok = True
        return True

    def stop(self):
        if self._conn is not None:
            try:
                self._kwin("/Scripting", "org.kde.kwin.Scripting", "unloadScript",
                           GLib.Variant("(s)", (PLUGIN,)))
            except GLib.Error:
                pass
            if self._reg:
                self._conn.unregister_object(self._reg)
                self._reg = 0
        self.ok = False

    def _kwin(self, path, iface, method, params):
        return self._conn.call_sync("org.kde.KWin", path, iface, method, params,
                                    None, Gio.DBusCallFlags.NONE, 3000, None)

    # ── llamadas del script ───────────────────────────────────────────────
    def _on_call(self, conn, sender, path, iface, method, params, invocation):
        try:
            kind, raw = params.unpack()
            data = json.loads(raw) if len(raw) < 200_000 else {}
            self._handle(kind, data)
        except Exception:  # noqa: BLE001
            pass
        invocation.return_value(GLib.Variant("(i)", (self.cursor_interval(),)))

    def _handle(self, kind, data):
        if _DEBUG:
            print(f"[kwin] {kind}: {str(data)[:160]}", flush=True)
        if kind == "windows":
            rects = []
            for r in data.get("rects", [])[:200]:
                if len(r) == 4:
                    rects.append(tuple(int(v) for v in r))
            self.rects = rects
            fs = bool(data.get("fullscreen"))
            if fs != self.fullscreen:
                self.fullscreen = fs
                for cb in self._fs_cbs:
                    cb(fs)
        elif kind == "area":
            self.areas = [tuple(int(v) for v in a) for a in data.get("areas", [])
                          if len(a) == 8][:16]
            for cb in self._area_cbs:
                cb()
        elif kind == "cursor":
            self.cursor = (int(data.get("x", 0)), int(data.get("y", 0)),
                           time.monotonic())
        elif kind == "desktop":
            a, b = data.get("from", -1), data.get("to", -1)
            if b >= 0:
                self.desktop = b
            if b >= 0 and a != b:
                d = 0 if a < 0 else (1 if b > a else -1)   # 0 = primer aviso
                for cb in self._desk_cbs:
                    cb(d, b)

    # ── API para el resto de la app ───────────────────────────────────────
    def want_cursor(self, who, ms):
        """Pide el cursor cada `ms` (0 = ya no hace falta)."""
        if ms > 0:
            self._cursor_wants[who] = ms
        else:
            self._cursor_wants.pop(who, None)

    def cursor_interval(self):
        return min(self._cursor_wants.values()) if self._cursor_wants else 0

    def cursor_pos(self):
        c = self.cursor
        if c is None:
            return None
        # el script solo manda el cursor al moverse: si está quieto, la última
        # posición sigue siendo buena
        return c[0], c[1]

    def on_desktop(self, cb):
        self._desk_cbs.append(cb)

    def on_area(self, cb):
        self._area_cbs.append(cb)

    def bottom_gap(self, mon_x, mon_y, w, h):
        """px que ocupan los paneles abajo en ese monitor (o None)."""
        for (mx, my, mw, mh, ax, ay, aw, ah) in self.areas:
            if mx == mon_x and my == mon_y:
                return max(0, (my + mh) - (ay + ah))
        return None

    def on_fullscreen(self, cb):
        self._fs_cbs.append(cb)


_BRIDGE = None


def bridge():
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = KWinBridge()
    return _BRIDGE


def active():
    return _BRIDGE is not None and _BRIDGE.ok


def start(app):
    if not is_kde_wayland():
        return False
    return bridge().start(app)
