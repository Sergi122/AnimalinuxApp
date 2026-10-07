"""Bandeja del sistema en Windows (Shell_NotifyIcon) sin procesos ni librerías
extra: una ventana oculta en el MISMO hilo; el bucle de mensajes lo bombea GDK.

La misma ventana oculta sirve de buzón de instancia única: un segundo
`animalinux --show` la localiza por su clase y le envía la orden con
WM_COPYDATA (ver forward()).
"""
import ctypes
from ctypes import wintypes as wt

from . import win32
from ...i18n import tr

user32, shell32, kernel32 = win32.user32, win32.shell32, win32.kernel32

CLASS_NAME = "AnimaLinuxTrayWnd"
WM_USER = 0x0400
WM_TRAY = WM_USER + 1
WM_COPYDATA = 0x004A
WM_COMMAND = 0x0111
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MF_STRING, MF_SEPARATOR = 0, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_BOTTOMALIGN = 0x0002, 0x0100, 0x0020
ID_SHOW, ID_QUIT = 1, 2

WNDPROC = ctypes.WINFUNCTYPE(win32.LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT),
                ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128)]


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wt.DWORD),
                ("lpData", ctypes.c_void_p)]


user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = win32.LRESULT
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SendMessageW.restype = win32.LRESULT
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, wt.HMENU,
                                   wt.HINSTANCE, wt.LPVOID]
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.LoadImageW.restype = wt.HANDLE
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int,
                              ctypes.c_int, wt.UINT]
user32.LoadIconW.restype = wt.HICON
user32.LoadIconW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]


def forward(args) -> bool:
    """Reenvía args a la instancia en marcha. True si había una."""
    hwnd = user32.FindWindowW(CLASS_NAME, None)
    if not hwnd:
        return False
    data = "\0".join(args).encode("utf-8")
    buf = ctypes.create_string_buffer(data, len(data) + 1)
    cds = COPYDATASTRUCT(1, len(data), ctypes.cast(buf, ctypes.c_void_p))
    user32.SendMessageW(hwnd, WM_COPYDATA, 0, ctypes.addressof(cds))
    return True


def _icon_handle():
    """Icono de la app: logo.png -> .ico temporal; si falla, el de Windows."""
    try:
        from PIL import Image
        from pathlib import Path
        from ... import paths
        src = Path(__file__).resolve().parents[2] / "ui" / "assets" / "logo.png"
        paths.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        ico = paths.RUNTIME_DIR / "tray.ico"
        if not ico.exists():
            Image.open(src).convert("RGBA").save(
                ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48)])
        h = user32.LoadImageW(None, str(ico), 1, 0, 0, 0x10 | 0x40)  # FROMFILE|DEFAULTSIZE
        if h:
            return h
    except Exception:  # noqa: BLE001
        pass
    return user32.LoadIconW(None, ctypes.c_void_p(32512))  # IDI_APPLICATION


class Tray:
    def __init__(self, app):
        self._app = app
        self._proc = WNDPROC(self._wndproc)   # referencia viva: si el GC la suelta, crash
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = CLASS_NAME
        user32.RegisterClassW(ctypes.byref(wc))
        self._hwnd = user32.CreateWindowExW(0, CLASS_NAME, "AnimaLinux", 0, 0, 0, 0, 0,
                                            None, None, wc.hInstance, None)
        self._nid = NOTIFYICONDATAW()
        self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._nid.hWnd = self._hwnd
        self._nid.uID = 1
        self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self._nid.uCallbackMessage = WM_TRAY
        self._nid.hIcon = _icon_handle()
        self._nid.szTip = "AnimaLinux"
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))

    # ---- mensajes ----
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY and lparam in (WM_LBUTTONUP, WM_RBUTTONUP):
                if lparam == WM_LBUTTONUP:
                    self._dispatch(["--show"])
                else:
                    self._menu(hwnd)
                return 0
            if msg == WM_COPYDATA:
                cds = ctypes.cast(lparam, ctypes.POINTER(COPYDATASTRUCT)).contents
                raw = ctypes.string_at(cds.lpData, cds.cbData) if cds.cbData else b""
                args = [a for a in raw.decode("utf-8", "ignore").split("\0") if a]
                self._dispatch(args)
                return 1
        except Exception:  # noqa: BLE001
            pass   # una excepción no puede cruzar el límite de ctypes
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _dispatch(self, args):
        from gi.repository import GLib
        GLib.idle_add(lambda: self._app.handle_args(args) and False)

    def _menu(self, hwnd):
        pt = win32.cursor_pos() or (0, 0)
        m = user32.CreatePopupMenu()
        user32.AppendMenuW(m, MF_STRING, ID_SHOW, tr("⚙  Configurar"))
        user32.AppendMenuW(m, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(m, MF_STRING, ID_QUIT, tr("⏻  Salir de AnimaLinux"))
        user32.SetForegroundWindow(hwnd)   # sin esto el menú no se cierra al hacer clic fuera
        cmd = user32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_BOTTOMALIGN,
                                    pt[0], pt[1], 0, hwnd, None)
        user32.DestroyMenu(m)
        if cmd == ID_SHOW:
            self._dispatch(["--show"])
        elif cmd == ID_QUIT:
            self._dispatch(["--quit"])

    def destroy(self):
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
        user32.DestroyWindow(self._hwnd)
