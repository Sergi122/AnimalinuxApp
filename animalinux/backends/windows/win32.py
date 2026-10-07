"""Llamadas Win32 vía ctypes (sin dependencias). Solo se importa en Windows.

Todo aquí es barato: user32/gdi32/shell32 ya están cargadas por GTK, y cada
función se resuelve una sola vez al importar.
"""
import ctypes
import os
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # pragma: no cover
    dwmapi = None

LRESULT = ctypes.c_ssize_t
HWND = wt.HWND

# ── constantes ──────────────────────────────────────────────────────────────
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
HWND_TOPMOST = HWND(-1)
SPI_GETWORKAREA = 0x0030
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4

# ── firmas (HWND como puntero: evita truncar a 32 bits) ─────────────────────
user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.SetWindowPos.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetCursorPos.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [HWND]
user32.IsIconic.argtypes = [HWND]
user32.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wt.RECT)]
user32.GetClassNameW.argtypes = [HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wt.DWORD)]
user32.GetForegroundWindow.restype = HWND
user32.SystemParametersInfoW.argtypes = [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]
user32.SetWindowRgn.argtypes = [HWND, wt.HRGN, wt.BOOL]
gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
gdi32.CreateRectRgn.restype = wt.HRGN
user32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowW.restype = HWND
shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]

if hasattr(user32, "GetWindowLongPtrW"):
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
else:  # Windows de 32 bits
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW
_get_long.argtypes = [HWND, ctypes.c_int]
_get_long.restype = ctypes.c_ssize_t
_set_long.argtypes = [HWND, ctypes.c_int, ctypes.c_ssize_t]
_set_long.restype = ctypes.c_ssize_t

_WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, HWND, wt.LPARAM)
_PID = os.getpid()


# ── DPI ─────────────────────────────────────────────────────────────────────
def system_scale() -> float:
    """Escala de pantalla del sistema (1.0 = 96 ppp). GDK trabaja en píxeles
    lógicos y Win32 en físicos: hay que convertir al hablar con Win32."""
    try:
        return max(1.0, user32.GetDpiForSystem() / 96.0)
    except (AttributeError, OSError):
        return 1.0


# ── ventana GTK -> HWND ─────────────────────────────────────────────────────
def hwnd_from_gtk(gtk_window):
    surf = gtk_window.get_surface()
    if surf is None:
        return None
    try:
        import gi
        gi.require_version("GdkWin32", "4.0")
        from gi.repository import GdkWin32
        h = GdkWin32.Win32Surface.get_handle(surf)
        if h:
            return int(h)
    except Exception:  # noqa: BLE001
        pass
    try:  # alternativa: puntero GObject -> gdk_win32_surface_get_handle
        getp = ctypes.pythonapi.PyCapsule_GetPointer
        getp.restype = ctypes.c_void_p
        getp.argtypes = [ctypes.py_object, ctypes.c_char_p]
        ptr = getp(surf.__gpointer__, None)
        fn = ctypes.CDLL("libgtk-4-1.dll").gdk_win32_surface_get_handle
        fn.restype = ctypes.c_void_p
        fn.argtypes = [ctypes.c_void_p]
        return fn(ptr)
    except Exception:  # noqa: BLE001
        return None


# ── ventana: estilo, posición, forma ────────────────────────────────────────
def make_overlay_window(hwnd):
    """Siempre encima, fuera de la barra de tareas/Alt-Tab y sin robar foco."""
    ex = _get_long(hwnd, GWL_EXSTYLE)
    ex = (ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST) & ~WS_EX_APPWINDOW
    _set_long(hwnd, GWL_EXSTYLE, ex)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def move_window(hwnd, x, y):
    user32.SetWindowPos(hwnd, None, int(x), int(y), 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)


def set_window_shape(hwnd, x, y, w, h):
    """Recorta la ventana a un rectángulo (px físicos, coords de la ventana):
    lo de fuera deja pasar los clics al escritorio. El sistema es dueño de la
    región tras SetWindowRgn."""
    rgn = gdi32.CreateRectRgn(int(x), int(y), int(x + w), int(y + h))
    user32.SetWindowRgn(hwnd, rgn, True)


def cursor_pos():
    pt = wt.POINT()
    if user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return None


def work_area():
    """(x, y, w, h) del área útil del monitor primario (sin la barra de tareas)."""
    r = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    return r.left, r.top, r.right - r.left, r.bottom - r.top


# ── ventanas abiertas ───────────────────────────────────────────────────────
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                  "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow"}


def _frame_rect(hwnd):
    r = wt.RECT()
    if dwmapi is not None and dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return r
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r
    return None


def top_level_rects(min_w=80, min_h=40):
    """[(left, top, right, bottom)] en px físicos de las ventanas «de verdad»
    (visibles, no minimizadas, no cloaked, no de herramientas ni del shell)."""
    out = []
    cls = ctypes.create_unicode_buffer(64)
    pid = wt.DWORD()
    cloaked = wt.DWORD()

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        if _get_long(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True   # incluye a las propias mascotas
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == _PID:
            return True
        if dwmapi is not None:
            cloaked.value = 0
            dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED,
                                         ctypes.byref(cloaked), ctypes.sizeof(cloaked))
            if cloaked.value:
                return True   # ventanas UWP/otro escritorio virtual
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in _SHELL_CLASSES:
            return True
        r = _frame_rect(hwnd)
        if r is None or r.right - r.left < min_w or r.bottom - r.top < min_h:
            return True
        out.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(_WNDENUMPROC(cb), 0)
    return out


def fullscreen_app_active() -> bool:
    """¿Hay una app/juego a pantalla completa (o presentación)? Una sola
    llamada del shell: más fiable y barata que comparar rectángulos."""
    state = ctypes.c_int(0)
    if shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in (QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN,
                           QUNS_PRESENTATION_MODE)
