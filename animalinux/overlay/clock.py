"""
Reloj único del proceso: un solo GLib timeout para TODAS las mascotas.

Antes cada mascota tenía sus propios temporizadores (animación + comportamiento)
y además un tick callback permanente del frame clock que despertaba al proceso
en cada vsync aunque no cambiara nada. Con 8 mascotas eran ~340 despertares/s.

Aquí cada tarea se registra con su periodo y el reloj duerme hasta la próxima
que venza. Las tareas que vencen casi a la vez (tolerancia TOL_US) se ejecutan
en el mismo despertar, y las que comparten periodo se alinean a la misma fase,
así un despertar sirve a varias mascotas.
"""
from gi.repository import GLib

TOL_US = 3000          # tareas que vencen dentro de esta ventana comparten despertar


class Clock:
    _inst = None

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        self._tasks = {}      # id -> [periodo_us, vence_us, fn]
        self._next = 1
        self._src = 0
        self._epoch = GLib.get_monotonic_time()

    # ── API ────────────────────────────────────────────────────────────────
    def every(self, ms, fn):
        """Ejecuta fn() cada `ms` milisegundos mientras devuelva True (como
        GLib.timeout_add) o hasta que se cancele. Devuelve un id para cancel()."""
        period = max(1000, int(ms * 1000))
        now = GLib.get_monotonic_time()
        # alinear la fase con el resto de tareas de igual periodo
        k = (now - self._epoch) // period + 1
        due = self._epoch + k * period
        tid = self._next
        self._next += 1
        self._tasks[tid] = [period, due, fn]
        self._reschedule()
        return tid

    def cancel(self, tid):
        if self._tasks.pop(tid, None) is not None:
            self._reschedule()

    # ── interno ────────────────────────────────────────────────────────────
    def _reschedule(self):
        if self._src:
            GLib.source_remove(self._src)
            self._src = 0
        if not self._tasks:
            return
        soonest = min(t[1] for t in self._tasks.values())
        delay_ms = max(1, (soonest - GLib.get_monotonic_time() + 999) // 1000)
        self._src = GLib.timeout_add(int(delay_ms), self._fire)

    def _fire(self):
        self._src = 0
        now = GLib.get_monotonic_time()
        for tid, t in list(self._tasks.items()):
            if t[1] > now + TOL_US:
                continue
            keep = True
            try:
                keep = bool(t[2]())      # misma convención que GLib.timeout_add
            except Exception:  # noqa: BLE001
                keep = True    # una mascota que falla no tumba al resto
            if tid not in self._tasks:
                continue       # se canceló dentro de su propia tarea
            if not keep:
                del self._tasks[tid]
                continue
            t[1] += t[0]
            if t[1] <= now:    # nos quedamos atrás (suspensión, carga): no acumular
                t[1] = now + t[0]
        self._reschedule()
        return False
