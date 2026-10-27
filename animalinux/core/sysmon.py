"""
Lo que pasa en el equipo, para que las mascotas reaccionen.

Un solo objeto, barato: un temporizador lento (cada 3 s) para CPU, batería y
hora, y señales de D-Bus (sin sondeo) para la música (MPRIS) y las
notificaciones. Avisa con dos callbacks:

    on_state(state)   cuando cambia algo de `state` (dict, ver STATE0)
    on_event(name)    eventos sueltos: "notification"

Todo va envuelto en try/except: si una fuente no existe (sin batería, sin
D-Bus, Windows) simplemente no aporta nada.
"""
import os
import sys
import time

from gi.repository import Gio, GLib

STATE0 = {
    "music": False,        # algún reproductor MPRIS en «Playing»
    "cpu": 0.0,            # uso medio de CPU (0-100)
    "hot": False,          # CPU alta sostenida
    "battery": None,       # % o None si no hay batería
    "charging": True,
    "low_battery": False,
    "night": False,
    "sharing": False,      # compartiendo pantalla / grabando (OBS…)
}

POLL_S = 3
HOT_ON, HOT_OFF = 85.0, 60.0         # histéresis de «CPU al rojo»
HOT_SAMPLES = 3                       # ~9 s seguidos por encima
LOW_BAT, LOW_BAT_OFF = 20, 25
SHARE_MIN_S = 2.5                     # compartir de verdad, no una captura suelta


def _in_night(hour, start, end):
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


class SystemMonitor:
    def __init__(self, on_state, on_event, cfg):
        """cfg() -> dict con night_start/night_end/dnd_auto (se relee en cada
        vuelta, así los cambios del panel se aplican sin reiniciar)."""
        self.on_state = on_state
        self.on_event = on_event
        self.cfg = cfg
        self.state = dict(STATE0)
        self._cpu_prev = None
        self._hot_n = 0
        self._players = {}            # nombre de bus -> "Playing"/"Paused"…
        self._bus = None
        self._mon_bus = None
        self._subs = []
        self._timer = 0
        self._share_hypr = False
        self._share_poll = 0
        self._share_check = 0

    # ── ciclo de vida ─────────────────────────────────────────────────────
    def start(self):
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._bus = None
        if self._bus is not None:
            self._watch_mpris()
            self._watch_notifications()
        self._watch_hypr_screencast()
        self._poll()
        self._timer = GLib.timeout_add_seconds(POLL_S, self._poll)

    def stop(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        if self._share_check:
            GLib.source_remove(self._share_check)
            self._share_check = 0
        if self._bus is not None:
            for sid in self._subs:
                self._bus.signal_unsubscribe(sid)
        self._subs = []
        if self._mon_bus is not None:
            try:
                self._mon_bus.close_sync(None)
            except GLib.Error:
                pass
            self._mon_bus = None

    def _set(self, **kw):
        changed = False
        for k, v in kw.items():
            if self.state.get(k) != v:
                self.state[k] = v
                changed = True
        if changed:
            self.on_state(dict(self.state))

    # ── sondeo lento: CPU, batería, hora, compartir pantalla ──────────────
    def _poll(self):
        try:
            cpu = self._read_cpu()
        except Exception:  # noqa: BLE001
            cpu = None
        upd = {}
        if cpu is not None:
            upd["cpu"] = round(cpu, 1)
            hot = self.state["hot"]
            if cpu >= HOT_ON:
                self._hot_n += 1
                if self._hot_n >= HOT_SAMPLES:
                    hot = True
            else:
                self._hot_n = 0
                if cpu < HOT_OFF:
                    hot = False
            upd["hot"] = hot
        try:
            pct, charging = self._read_battery()
        except Exception:  # noqa: BLE001
            pct, charging = None, True
        upd["battery"] = pct
        upd["charging"] = charging
        low = self.state["low_battery"]
        if pct is None or charging:
            low = False
        elif pct <= LOW_BAT:
            low = True
        elif pct >= LOW_BAT_OFF:
            low = False
        upd["low_battery"] = low
        c = self.cfg()
        upd["night"] = _in_night(time.localtime().tm_hour,
                                 int(c.get("night_start", 23)),
                                 int(c.get("night_end", 7)))
        if c.get("dnd_auto", True):
            self._share_poll += 1
            if self._share_poll % 3 == 1:       # ~cada 9 s: más caro
                upd["sharing"] = self._share_hypr or _sharing_now()
            else:
                upd["sharing"] = self._share_hypr or self.state["sharing"]
        else:
            upd["sharing"] = False
        self._set(**upd)
        return True

    def _read_cpu(self):
        if sys.platform == "win32":
            return _cpu_windows(self)
        with open("/proc/stat", "rb") as f:
            parts = f.readline().split()[1:]
        vals = [int(x) for x in parts]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)
        prev = self._cpu_prev
        self._cpu_prev = (idle, total)
        if prev is None or total == prev[1]:
            return None
        return 100.0 * (1.0 - (idle - prev[0]) / float(total - prev[1]))

    def _read_battery(self):
        if sys.platform == "win32":
            return _battery_windows()
        base = "/sys/class/power_supply"
        best = None
        charging = True
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name)
            try:
                with open(os.path.join(p, "type")) as f:
                    if f.read().strip() != "Battery":
                        continue
                with open(os.path.join(p, "capacity")) as f:
                    cap = int(f.read().strip())
                with open(os.path.join(p, "status")) as f:
                    st = f.read().strip()
            except OSError:
                continue
            best = cap if best is None else min(best, cap)
            charging = st in ("Charging", "Full", "Not charging")
        if best is None:
            return None, True
        return best, charging

    # ── música: MPRIS por señales ─────────────────────────────────────────
    def _watch_mpris(self):
        bus = self._bus
        self._subs.append(bus.signal_subscribe(
            None, "org.freedesktop.DBus.Properties", "PropertiesChanged",
            "/org/mpris/MediaPlayer2", None, Gio.DBusSignalFlags.NONE,
            self._on_mpris_props))
        self._subs.append(bus.signal_subscribe(
            "org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged",
            "/org/freedesktop/DBus", None, Gio.DBusSignalFlags.NONE,
            self._on_name_owner))
        bus.call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                 "org.freedesktop.DBus", "ListNames", None,
                 GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, 2000, None,
                 self._on_list_names)

    def _on_list_names(self, bus, res):
        try:
            names = bus.call_finish(res).unpack()[0]
        except GLib.Error:
            return
        for n in names:
            if n.startswith("org.mpris.MediaPlayer2."):
                self._query_player(n)

    def _query_player(self, name):
        def done(bus, res):
            try:
                v = bus.call_finish(res).unpack()[0]
            except GLib.Error:
                v = None
            self._players[name] = v
            self._update_music()
        self._bus.call(name, "/org/mpris/MediaPlayer2",
                       "org.freedesktop.DBus.Properties", "Get",
                       GLib.Variant("(ss)", ("org.mpris.MediaPlayer2.Player",
                                             "PlaybackStatus")),
                       GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, 2000,
                       None, done)

    def _on_mpris_props(self, bus, sender, path, iface, signal, params):
        try:
            iface_name, changed, _inv = params.unpack()
        except Exception:  # noqa: BLE001
            return
        if iface_name != "org.mpris.MediaPlayer2.Player":
            return
        if "PlaybackStatus" in changed:
            # el emisor llega como nombre único (:1.42): se busca qué nombre
            # bien conocido tiene ese dueño consultando a todos de nuevo
            for n in list(self._players):
                self._query_player(n)
            if not self._players:
                bus.call("org.freedesktop.DBus", "/org/freedesktop/DBus",
                         "org.freedesktop.DBus", "ListNames", None,
                         GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE,
                         2000, None, self._on_list_names)

    def _on_name_owner(self, bus, sender, path, iface, signal, params):
        name, _old, new = params.unpack()
        if not name.startswith("org.mpris.MediaPlayer2."):
            return
        if new:
            self._query_player(name)
        else:
            self._players.pop(name, None)
            self._update_music()

    def _update_music(self):
        self._set(music=any(v == "Playing" for v in self._players.values()))

    # ── notificaciones: monitor de D-Bus (solo mira, no toca nada) ────────
    def _watch_notifications(self):
        """Una conexión aparte en modo monitor recibe una copia de cada
        llamada Notify del escritorio. No se leen títulos ni textos: solo
        cuenta que llegó una (y se ignoran las de esta misma app)."""
        try:
            addr = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
            conn = Gio.DBusConnection.new_for_address_sync(
                addr, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
            conn.add_filter(self._notify_filter)
            conn.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus",
                "org.freedesktop.DBus.Monitoring", "BecomeMonitor",
                GLib.Variant("(asu)", ([
                    "type='method_call',interface='org.freedesktop.Notifications',"
                    "member='Notify'"], 0)),
                None, Gio.DBusCallFlags.NONE, 2000, None)
            self._mon_bus = conn
        except GLib.Error:
            self._mon_bus = None

    def _notify_filter(self, conn, msg, incoming):
        # corre en el hilo de D-Bus: solo se pasa al hilo principal
        try:
            if (msg.get_member() == "Notify" and
                    msg.get_message_type() == Gio.DBusMessageType.METHOD_CALL):
                body = msg.get_body()
                app = body.get_child_value(0).get_string() if body else ""
                from ..backends import current as backend
                if app not in (backend.APP_NAME, "animalinux", "python3",
                               "__main__.py", GLib.get_application_name()):
                    GLib.idle_add(self._emit_notification)
        except Exception:  # noqa: BLE001
            pass
        # devolver el mensaje: si se descarta (None) también se pierde la
        # respuesta a BecomeMonitor y la conexión se queda colgada
        return msg

    def _emit_notification(self):
        self.on_event("notification")
        return False

    # ── compartir pantalla ────────────────────────────────────────────────
    def _watch_hypr_screencast(self):
        """Hyprland avisa por su socket de eventos: screencast>>1,…"""
        try:
            from ..backends.linux import hypr
        except Exception:  # noqa: BLE001
            return
        hypr.events().on("screencast", self._on_hypr_screencast)

    def _on_hypr_screencast(self, data):
        """Hyprland también avisa «screencast» por cada CAPTURA de pantalla
        (grim, la herramienta de capturas…), que dura menos de medio segundo:
        solo cuenta como compartir si sigue activo SHARE_MIN_S después (si
        no, las mascotas parpadeaban y no salían en tus capturas)."""
        on = data.split(",", 1)[0].strip() == "1"
        if self._share_check:
            GLib.source_remove(self._share_check)
            self._share_check = 0
        if on:
            self._share_check = GLib.timeout_add(int(SHARE_MIN_S * 1000), self._share_confirm)
            return False
        self._share_hypr = False
        self._set(sharing=_sharing_now())
        return False

    def _share_confirm(self):
        self._share_check = 0
        self._share_hypr = True
        self._set(sharing=True)
        return False


# ── compartir pantalla fuera de Hyprland ───────────────────────────────────
_RECORDERS = {"obs", "obs64", "obs-studio", "simplescreenrecorder",
              "kooha", "gpu-screen-recorder", "wf-recorder", "wl-screenrec"}


def _sharing_now():
    """¿Alguien graba o comparte la pantalla? OBS & cía. por nombre de
    proceso; en Linux además las capturas de pantalla activas de PipeWire
    (lo que usan Meet, Discord, Zoom… por el portal)."""
    if sys.platform == "win32":
        return False
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/comm") as f:
                    if f.read().strip().lower() in _RECORDERS:
                        return True
            except OSError:
                continue
    except OSError:
        pass
    return _pipewire_screencast()


def _pipewire_screencast():
    import json
    import shutil
    import subprocess
    if not shutil.which("pw-dump"):
        return False
    try:
        out = subprocess.run(["pw-dump"], capture_output=True, text=True,
                             timeout=3).stdout
        objs = json.loads(out)
    except Exception:  # noqa: BLE001
        return False
    for o in objs:
        info = o.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") != "Video/Source":
            continue
        name = (props.get("node.name", "") + " " +
                props.get("media.name", "")).lower()
        if any(k in name for k in ("xdph", "xdpw", "screencast", "kwin",
                                   "gnome-shell", "screen")):
            if info.get("state") == "running":
                return True
    return False


# ── Windows ────────────────────────────────────────────────────────────────
def _cpu_windows(mon):
    import ctypes
    from ctypes import wintypes

    class FT(ctypes.Structure):
        _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

    idle, kern, user = FT(), FT(), FT()
    if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return None

    def v(ft):
        return (ft.hi << 32) | ft.lo
    i, total = v(idle), v(kern) + v(user)      # kernel incluye idle
    prev = mon._cpu_prev
    mon._cpu_prev = (i, total)
    if prev is None or total == prev[1]:
        return None
    return 100.0 * (1.0 - (i - prev[0]) / float(total - prev[1]))


def _battery_windows():
    import ctypes

    class SPS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("Reserved1", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    s = SPS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
        return None, True
    if s.BatteryFlag & 128 or s.BatteryLifePercent == 255:
        return None, True                      # sin batería
    return int(s.BatteryLifePercent), s.ACLineStatus == 1
