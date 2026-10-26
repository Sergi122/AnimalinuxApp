"""
El «director» de la compañía: decide qué hacen las mascotas por lo que pasa
en el equipo y entre ellas. Las órdenes que cada mascota sabe cumplir están
en overlay/companion.py; aquí se decide cuándo y a quién darlas.

  - reacciones: música → bailan; CPU al rojo → cansadas; batería baja →
    preocupadas; de noche → duermen más (y juntas); notificación → se
    sobresaltan.
  - cursor: si lo dejas quieto, una se acerca a mirarlo; si lo mueves rápido
    cerca del suelo, lo persigue como un gato con un láser.
  - juguetes: pelota / ovillo que se lanzan con el mouse; las mascotas corren
    a patearlos.
  - juegos entre mascotas: pillarse y escondidas detrás de una ventana.
  - escritorios: al cambiar de escritorio una o dos «te siguen» entrando
    corriendo por el borde.
  - Pomodoro con cartelito, recordatorios (agua / levantarse) y modo no
    molestar (manual o automático al compartir pantalla / grabar).
"""
import random
import time

from gi.repository import Gio, GLib

from .. import settings
from ..backends import current as backend
from ..i18n import N_, tr
from .sysmon import SystemMonitor

PLAY_MS = 250                 # ritmo del director (cursor, juguetes, juegos)
MAX_TOYS = 3
TOY_INTEREST_S = 25           # tras esto quietos, los juguetes aburren

DEFAULTS = {
    "react_music": True, "react_cpu": True, "react_notify": True,
    "react_night": True, "react_battery": True,
    "night_start": 23, "night_end": 7,
    "cursor_play": True, "pet_games": True, "follow_workspace": True,
    "pomodoro_work": 25, "pomodoro_break": 5, "pomodoro_long": 15,
    "pomodoro_pet": "",
    "remind_water": 0, "remind_stand": 0,      # minutos; 0 = apagado
    "dnd_auto": True,
    "sport_difficulty": "medium", "sport_mode": "points", "sport_minutes": 5,
    "sport_points": 10, "sport_rivals": 2, "sport_helper": False,
    "sport_rival_ids": [], "sport_helper_id": "", "sport_last": "football",
}


def sport_opts():
    return {"difficulty": cfg("sport_difficulty"), "mode": cfg("sport_mode"),
            "minutes": cfg("sport_minutes"), "points": cfg("sport_points"),
            "rivals": cfg("sport_rivals"), "helper": cfg("sport_helper"),
            "rival_ids": cfg("sport_rival_ids"), "helper_id": cfg("sport_helper_id")}


def cfg(key):
    return settings.get(key, DEFAULTS.get(key))


def cfg_all():
    return {k: cfg(k) for k in DEFAULTS}


def _fmt(secs):
    secs = max(0, int(secs))
    return f"{secs // 60:02d}:{secs % 60:02d}"


class Companion:
    def __init__(self, app):
        self.app = app
        self.manager = app.manager
        self.sys = SystemMonitor(self._on_sys_state, self._on_sys_event, cfg_all)
        self.sys_state = dict(self.sys.state)
        self.dnd_manual = False
        self.dnd = False
        self._play_id = 0
        self._cursor_prev = None       # (t, x, y)
        self._cursor_still_since = 0.0
        self._cursor_still_done = False
        self._laser_pet = None
        self._laser_until = 0.0
        self._cooldown = {}            # id de mascota -> instante libre
        self._game = None
        self._match = None
        self._next_game = time.monotonic() + random.uniform(60, 150)
        self._low_bat_said = False
        self.pomodoro = Pomodoro(self)
        self._remind_min = {"water": 0, "stand": 0}
        self._remind_id = 0

    # ── arranque / parada ─────────────────────────────────────────────────
    def start(self):
        self.sys.start()
        self._play_id = GLib.timeout_add(PLAY_MS, self._play_tick)
        self._remind_id = GLib.timeout_add_seconds(60, self._remind_tick)
        self.manager.on_workspace_change(self._on_workspace)

    def stop(self):
        self.sys.stop()
        for sid in (self._play_id, self._remind_id):
            if sid:
                GLib.source_remove(sid)
        self._play_id = self._remind_id = 0
        self.pomodoro.stop(quiet=True)

    # ── ayudantes ─────────────────────────────────────────────────────────
    def pets(self, life=True):
        out = []
        for w in self.manager.mascots.values():
            if life and w.mode != "life":
                continue
            out.append(w)
        return out

    def _free(self, w, now):
        return self._cooldown.get(id(w), 0) <= now

    def _hold(self, w, secs):
        self._cooldown[id(w)] = time.monotonic() + secs

    # ── sistema → humor ───────────────────────────────────────────────────
    def _on_sys_state(self, st):
        self.sys_state = st
        self.apply_moods()
        self._update_dnd()
        if st.get("low_battery") and cfg("react_battery"):
            if not self._low_bat_said and not self.dnd:
                pets = self.pets(life=False)
                if pets:
                    random.choice(pets).say(tr("🔋 Batería baja… ¿me enchufas?"), 10)
                self._low_bat_said = True
        else:
            self._low_bat_said = False

    def mood_now(self):
        st = self.sys_state
        if st.get("music") and cfg("react_music"):
            return "dance"
        if st.get("low_battery") and cfg("react_battery"):
            return "worried"
        if st.get("hot") and cfg("react_cpu"):
            return "tired"
        if st.get("night") and cfg("react_night"):
            return "night"
        return None

    def apply_moods(self):
        mood = self.mood_now()
        for w in self.pets(life=False):
            w.set_mood(mood)

    def _on_sys_event(self, name):
        if name != "notification" or not cfg("react_notify") or self.dnd:
            return
        for w in self.pets():
            if w.is_awake() or random.random() < 0.5:
                GLib.timeout_add(random.randint(0, 350),
                                 lambda w=w: (w.startle(), False)[1])

    # ── no molestar ───────────────────────────────────────────────────────
    def set_dnd_manual(self, on):
        self.dnd_manual = bool(on)
        self._update_dnd()

    def _update_dnd(self):
        on = self.dnd_manual or bool(self.sys_state.get("sharing") and cfg("dnd_auto"))
        if on != self.dnd:
            self.dnd = on
            self.manager.set_hidden_all(on)

    # ── escritorios ───────────────────────────────────────────────────────
    def _on_workspace(self, direction):
        if not cfg("follow_workspace") or self.dnd:
            return
        cands = [w for w in self.pets() if w.is_awake() and not w.is_busy()]
        random.shuffle(cands)
        for i, w in enumerate(cands):
            # se van y llegan de un salto, una detrás de otra
            GLib.timeout_add(120 + i * 260,
                             lambda w=w: (w.enter_from(-direction), False)[1])

    # ── juguetes ──────────────────────────────────────────────────────────
    def throw_toy(self, kind="ball"):
        if len(self.manager.toys) >= MAX_TOYS:
            oldest = next(iter(self.manager.toys))
            self.manager.remove_toy(oldest)
        win = self.manager.spawn_toy(kind)
        if win is not None:
            win.kick(random.choice((-1, 1)), 1.2)
        return win

    def clear_toys(self):
        for tid in list(self.manager.toys):
            self.manager.remove_toy(tid)

    # ── deportes ──────────────────────────────────────────────────────────
    def match_started(self, match):
        self.clear_toys()
        if self._game is not None:
            self._game.end()
            self._game = None
        self._match = match
        from ..backends import current as be
        if be.NAME == "linux":
            from ..backends.linux import kwin
            if kwin.active():
                kwin.bridge().want_cursor("sport", 16)

    def match_over(self, match):
        self._match = None
        from ..backends import current as be
        if be.NAME == "linux":
            from ..backends.linux import kwin
            if kwin.active():
                kwin.bridge().want_cursor("sport", 0)
        if match.result in ("win", "lose", "draw"):
            key = {"win": "win", "lose": "lose", "draw": "draw"}[match.result]
            self.notify("sport", {"win": tr("¡Ganaste el partido! {a} – {b}"),
                                  "lose": tr("Las mascotas ganaron {b} – {a}"),
                                  "draw": tr("Empate {a} – {b}")}[key].format(
                a=match.score["you"], b=match.score["pets"]))

    # ── el ritmo del director ─────────────────────────────────────────────
    def _play_tick(self):
        if self.dnd or self._match is not None:
            return True
        pets = self.pets()
        if not pets:
            return True
        now = time.monotonic()
        try:
            self._toys_tick(pets, now)
            if cfg("cursor_play"):
                self._cursor_tick(pets, now)
            if cfg("pet_games"):
                self._games_tick(pets, now)
            self._sleep_together(pets)
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
        return True

    def _toys_tick(self, pets, now):
        for toy in list(self.manager.toys.values()):
            if toy.toy_idle_s() > TOY_INTEREST_S:
                continue
            tcx = toy.center_x()
            tbottom = toy._y + toy._cat_h
            near = sorted(
                (w for w in pets if w.is_awake() and not w.is_busy()
                 and w._mon_x == toy._mon_x),
                key=lambda w: abs(w.center_x() - tcx))[:2]
            for w in near:
                reach = (w._cat_w + toy._cat_w) * 0.35
                dx = tcx - w.center_x()
                low = abs((w._y + w._cat_h) - tbottom) < max(20, w._cat_h * 0.5)
                if abs(dx) < reach and low and self._free(w, now):
                    toy.kick(1 if dx > 0 else -1, random.uniform(0.8, 1.2))
                    w.face_toward(tcx)
                    w.trigger_greet("greet", fallback_jump=False)
                    self._hold(w, 1.2)
                elif self._free(w, now):
                    w.chase(tcx - w._cat_w / 2, "toy")

    def _cursor_tick(self, pets, now):
        p = None
        for w in pets:
            p = w._cursor_global()
            if p is not None:
                break
        if p is None:
            return
        gx, gy = p
        prev = self._cursor_prev
        self._cursor_prev = (now, gx, gy)
        if prev is None:
            self._cursor_still_since = now
            return
        dt = max(1e-3, now - prev[0])
        speed = ((gx - prev[1]) ** 2 + (gy - prev[2]) ** 2) ** 0.5 / dt
        if speed > 15:
            self._cursor_still_since = now
            self._cursor_still_done = False

        here = [w for w in pets
                if w._mon_x <= gx < w._mon_x + w._screen_w
                and w._mon_y <= gy < w._mon_y + w._screen_h]
        if not here:
            return
        lx = gx - here[0]._mon_x
        ly = gy - here[0]._mon_y

        # rápido y cerca del suelo → persecución tipo láser
        low = ly > here[0]._screen_h * 0.55
        if speed > 1400 and low:
            w = self._laser_pet
            if w is None or w not in here or not w.is_awake():
                cands = [c for c in here if c.is_awake() and not c.is_busy()
                         and self._free(c, now)]
                if cands:
                    w = min(cands, key=lambda c: abs(c.center_x() - lx))
                    self._laser_pet = w
                    self._laser_until = now + 6
            if w is not None and now < self._laser_until:
                w.chase(lx - w._cat_w / 2, "laser")
            elif w is not None:
                w.stop_chase()
                self._hold(w, 15)
                self._laser_pet = None
            return
        if self._laser_pet is not None and speed < 200:
            self._laser_pet = None

        # quieto un rato → una se acerca a mirarlo
        if (not self._cursor_still_done and now - self._cursor_still_since > 3.5
                and random.random() < 0.5):
            self._cursor_still_done = True
            cands = [c for c in here if c.is_awake() and not c.is_busy()
                     and self._free(c, now) and c._state in ("idle", "walk", "rest")]
            if cands:
                w = min(cands, key=lambda c: abs(c.center_x() - lx))
                side = -1 if w.center_x() < lx else 1
                if w.chase(lx - w._cat_w / 2 + side * w._cat_w * 0.6, "cursor", run=False):
                    self._hold(w, 25)

    # ── juegos entre mascotas ─────────────────────────────────────────────
    def _games_tick(self, pets, now):
        g = self._game
        if g is not None:
            if not g.tick(now):
                self._game = None
                self._next_game = now + random.uniform(90, 240)
            return
        if now < self._next_game or self.mood_now() in ("night", "tired"):
            return
        if self.manager.toys:
            return
        awake = [w for w in pets if w.is_awake() and not w.is_busy()
                 and w._state in ("idle", "walk", "rest")]
        if len(awake) < 2:
            self._next_game = now + 30
            return
        random.shuffle(awake)
        a, b = awake[0], awake[1]
        if a._mon_x != b._mon_x:
            self._next_game = now + 30
            return
        game = None
        if random.random() < 0.45:
            game = HideAndSeek.make(a, b)
        if game is None:
            game = Tag(a, b)
        self._game = game
        self._game.start(now)

    def start_game(self, kind):
        """Desde el panel: «¡a jugar!»."""
        pets = [w for w in self.pets() if w.is_awake() and not w.is_busy()]
        if len(pets) < 2:
            return False
        random.shuffle(pets)
        a, b = pets[0], pets[1]
        game = HideAndSeek.make(a, b) if kind == "hide" else Tag(a, b)
        if game is None:
            return False
        if self._game is not None:
            self._game.end()
        self._game = game
        game.start(time.monotonic())
        return True

    def _sleep_together(self, pets):
        if self.mood_now() != "night":
            return
        sleepers = [w for w in pets if w._state == "sleep"]
        if not sleepers:
            return
        for w in pets:
            if (w.is_awake() and not w.is_busy() and w._state in ("idle", "rest")
                    and random.random() < 0.02):
                s = min(sleepers, key=lambda o: abs(o.center_x() - w.center_x()))
                if s._mon_x != w._mon_x:
                    continue
                side = -1 if w.center_x() < s.center_x() else 1
                w.sleep_near(s._x + side * s._cat_w * 0.75)

    # ── recordatorios ─────────────────────────────────────────────────────
    REMINDERS = {
        "water": ("remind_water", N_("💧 ¡Toma un poco de agua!")),
        "stand": ("remind_stand", N_("🧍 ¡Levántate y estírate un poco!")),
    }

    def _remind_tick(self):
        for kind, (key, text) in self.REMINDERS.items():
            every = int(cfg(key) or 0)
            if every <= 0:
                self._remind_min[kind] = 0
                continue
            self._remind_min[kind] += 1
            if self._remind_min[kind] >= every:
                self._remind_min[kind] = 0
                self.remind(tr(text))
        return True

    def remind(self, text):
        if self.dnd:
            return
        pets = self.pets(life=False)
        if pets:
            w = random.choice(pets)
            w.say(text, 12)
            if w.mode == "life" and not w.is_busy():
                w.trigger_greet("greet", fallback_jump=False)
        self.notify("remind", text)

    def notify(self, nid, body, title=None):
        if self.dnd:
            return
        try:
            n = Gio.Notification.new(title or backend.APP_NAME)
            n.set_body(body)
            self.app.send_notification(nid, n)
        except Exception:  # noqa: BLE001
            pass


# ── juegos ─────────────────────────────────────────────────────────────────
class Tag:
    """A persigue a B; si la pilla, se saludan y cambian. Dos rondas."""

    def __init__(self, a, b):
        self.it, self.runner = a, b
        self.rounds = 0
        self.until = 0.0
        self.pause = 0.0

    def start(self, now):
        self.until = now + 16
        self._go()

    def _go(self):
        self.runner.flee(self.it.center_x())
        self.it.chase(self.runner._x, "pet")

    def tick(self, now):
        a, b = self.it, self.runner
        if now > self.until or a._state == "sleep" or b._state == "sleep":
            self.end()
            return False
        if now < self.pause:
            return True
        if a._state not in ("chase",) and not a.is_busy():
            a.chase(b._x, "pet")
        if b._state not in ("flee",) and not b.is_busy():
            b.flee(a.center_x())
        if a._state == "chase":
            a._chase_x = float(b._x)
            a._chase_ttl = 60
        if b._state == "flee":
            b._chase_ttl = 60
        if abs(a.center_x() - b.center_x()) < (a._cat_w + b._cat_w) * 0.3 \
                and abs(a._y - b._y) < max(a._cat_h, b._cat_h):
            self.rounds += 1
            a.stop_chase()
            b.stop_chase()
            a.face_toward(b.center_x())
            b.face_toward(a.center_x())
            a.say(tr("¡Te pillé!"), 2)
            a.trigger_greet("greet", fallback_jump=False)
            b.trigger_greet("greet", fallback_jump=False)
            if self.rounds >= 2:
                return False
            self.it, self.runner = b, a
            self.pause = now + 2.0
            GLib.timeout_add(2000, lambda: (self._go(), False)[1])
        return True

    def end(self):
        self.it.stop_chase()
        self.runner.stop_chase()


class HideAndSeek:
    """B se esconde detrás de una ventana mientras A cuenta; A la busca un
    rato y B sale de un salto."""

    def __init__(self, seeker, hider, spot_x):
        self.seeker, self.hider, self.spot = seeker, hider, spot_x
        self.phase = "hide"
        self.t_phase = 0.0
        self.until = 0.0

    @classmethod
    def make(cls, a, b):
        for seeker, hider in ((a, b), (b, a)):
            if not hider.can_hide() or hider._y < hider._floor_y - 2:
                continue
            x = cls._spot_for(hider)
            if x is not None:
                return cls(seeker, hider, x)
        return None

    @staticmethod
    def _spot_for(w):
        """Una X donde la mascota quede entera tapada por una ventana."""
        try:
            rects = backend.window_rects()
        except Exception:  # noqa: BLE001
            return None
        top = w._mon_y + w._floor_y
        bottom = top + w._cat_h
        spots = []
        for (x0, y0, x1, y1) in rects:
            if y0 <= top and y1 >= bottom and (x1 - x0) >= w._cat_w + 20:
                lx0 = max(0, x0 - w._mon_x + 10)
                lx1 = min(w._screen_w - w._cat_w, x1 - w._mon_x - w._cat_w - 10)
                if lx1 > lx0:
                    spots.append(random.uniform(lx0, lx1))
        if not spots:
            return None
        return min(spots, key=lambda s: abs(s - w._x))

    def start(self, now):
        self.seeker.count(3.5)
        self.seeker.say(tr("1, 2, 3…"), 3)
        self.hider.hide_at(self.spot)
        self.t_phase = now
        self.until = now + 40

    def tick(self, now):
        s, h = self.seeker, self.hider
        if now > self.until:
            self.end()
            return False
        if self.phase == "hide":
            if h._state not in ("to_hide", "hidden"):
                self.end()
                return False
            if h.is_hidden() and s._state != "count":
                self.phase = "seek"
                self.t_phase = now
                self.seek_for = random.uniform(6, 10)
                s.say(tr("¿Dónde estás?"), 3)
            return True
        if self.phase == "seek":
            if s._state not in ("chase",) and not s.is_busy():
                s.chase(random.uniform(0, s._screen_w - s._cat_w), "pet", run=False)
            if now - self.t_phase > self.seek_for:
                h.unhide()
                h.say(tr("¡Aquí estoy!"), 2.5)
                self.phase = "found"
                self.t_phase = now
            return True
        if self.phase == "found":
            if not s.is_busy():
                s.chase(h._x, "pet")
            if abs(s.center_x() - h.center_x()) < (s._cat_w + h._cat_w) * 0.4 \
                    or now - self.t_phase > 8:
                s.stop_chase()
                s.face_toward(h.center_x())
                h.face_toward(s.center_x())
                s.trigger_greet("greet", fallback_jump=False)
                h.trigger_greet("greet", fallback_jump=False)
                return False
            return True
        return False

    def end(self):
        self.hider.unhide()
        self.seeker.stop_chase()


# ── Pomodoro ───────────────────────────────────────────────────────────────
class Pomodoro:
    """Trabajo / descanso con cartelito sobre una mascota. Cada 4 bloques de
    trabajo, un descanso largo."""

    def __init__(self, comp):
        self.comp = comp
        self.phase = None          # None | "work" | "break"
        self.ends = 0.0
        self.done = 0              # bloques de trabajo completados
        self._tick_id = 0
        self._pet = None

    @property
    def running(self):
        return self.phase is not None

    def remaining(self):
        return max(0.0, self.ends - time.monotonic()) if self.running else 0.0

    def start(self):
        self.done = 0
        self._begin("work")
        if not self._tick_id:
            self._tick_id = GLib.timeout_add(1000, self._tick)

    def stop(self, quiet=False):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0
        self.phase = None
        if self._pet is not None:
            try:
                self._pet.set_sign(None)
            except Exception:  # noqa: BLE001
                pass
        self._pet = None
        if not quiet:
            self.comp.notify("pomodoro", tr("Pomodoro detenido."))

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def _minutes(self, key):
        return max(1, int(cfg(key) or 1))

    def _begin(self, phase):
        self.phase = phase
        if phase == "work":
            mins = self._minutes("pomodoro_work")
            self.comp.notify("pomodoro", tr("🍅 ¡A concentrarse! {m} minutos.", m=mins))
        else:
            long_ = self.done > 0 and self.done % 4 == 0
            mins = self._minutes("pomodoro_long" if long_ else "pomodoro_break")
            self.comp.notify("pomodoro", tr("☕ ¡Descanso! {m} minutos para estirarte.", m=mins))
            pet = self._choose_pet()
            if pet is not None:
                pet.stretch()
                for w in self.comp.pets():
                    if w is not pet:
                        GLib.timeout_add(random.randint(200, 1200),
                                         lambda w=w: (w.stretch(), False)[1])
        self.ends = time.monotonic() + mins * 60
        self._refresh_sign()

    def _choose_pet(self):
        mascots = self.comp.manager.mascots
        want = cfg("pomodoro_pet")
        if want and want in mascots:
            return mascots[want]
        if self._pet is not None and self._pet in mascots.values():
            return self._pet
        pets = list(mascots.values())
        life = [w for w in pets if w.mode == "life"]
        return (life or pets or [None])[0]

    def _refresh_sign(self):
        pet = self._choose_pet()
        if pet is not self._pet:
            if self._pet is not None:
                try:
                    self._pet.set_sign(None)
                except Exception:  # noqa: BLE001
                    pass
            self._pet = pet
        if pet is None:
            return
        icon = "🍅" if self.phase == "work" else "☕"
        pet.set_sign(f"{icon} {_fmt(self.remaining())}")

    def _tick(self):
        if not self.running:
            self._tick_id = 0
            return False
        if self.remaining() <= 0:
            if self.phase == "work":
                self.done += 1
                self._begin("break")
            else:
                self._begin("work")
        else:
            self._refresh_sign()
        return True
