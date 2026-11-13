"""onnxruntime sin su módulo de Python: la API en C de onnxruntime.dll vía ctypes.

En AnimaWin el Python es el de MSYS2 y su paquete python-onnxruntime viene
roto (falta onnxruntime_pybind11_state), y las ruedas oficiales de PyPI son
para el Python de python.org (otra ABI). La librería oficial de Microsoft
(onnxruntime.dll) en cambio expone una API en C pura, que sirve desde
cualquier proceso. Aquí solo se usa lo justo para el recorte: crear la
sesión, un tensor float32 de entrada y Run().

La tabla OrtApi solo crece por el final entre versiones (compatibilidad
binaria garantizada por onnxruntime), así que las posiciones son fijas;
se sacaron de onnxruntime_c_api.h (v1.31.1).
"""
import ctypes
import os
import sys
from pathlib import Path

import numpy as np

# posición de cada función en struct OrtApi
_IDX = {
    "GetErrorMessage": 2, "CreateEnv": 3, "CreateSession": 7, "Run": 9,
    "CreateSessionOptions": 10, "SetIntraOpNumThreads": 24,
    "CreateTensorWithDataAsOrtValue": 49, "GetTensorMutableData": 51,
    "CreateCpuMemoryInfo": 69, "ReleaseEnv": 92, "ReleaseStatus": 93,
    "ReleaseMemoryInfo": 94, "ReleaseSession": 95, "ReleaseValue": 96,
    "ReleaseSessionOptions": 100,
}
_API_VERSION = 11          # todo lo de arriba existe desde mucho antes
_FLOAT = 1                 # ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT
_ARENA, _MEM_DEFAULT = 1, 0
_WARNING = 2               # ORT_LOGGING_LEVEL_WARNING

P = ctypes.c_void_p
PP = ctypes.POINTER(ctypes.c_void_p)
_SIG = {
    "GetErrorMessage": (ctypes.c_char_p, P),
    "CreateEnv": (P, ctypes.c_int, ctypes.c_char_p, PP),
    "CreateSession": (P, P, ctypes.c_wchar_p if sys.platform == "win32" else ctypes.c_char_p, P, PP),
    "Run": (P, P, P, ctypes.POINTER(ctypes.c_char_p), PP, ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, PP),
    "CreateSessionOptions": (P, PP),
    "SetIntraOpNumThreads": (P, P, ctypes.c_int),
    "CreateTensorWithDataAsOrtValue": (P, P, P, ctypes.c_size_t, ctypes.POINTER(ctypes.c_int64),
                                       ctypes.c_size_t, ctypes.c_int, PP),
    "GetTensorMutableData": (P, P, PP),
    "CreateCpuMemoryInfo": (P, ctypes.c_int, ctypes.c_int, PP),
}
for _n in ("ReleaseEnv", "ReleaseStatus", "ReleaseMemoryInfo", "ReleaseSession",
           "ReleaseValue", "ReleaseSessionOptions"):
    _SIG[_n] = (None, P)


class OrtError(RuntimeError):
    pass


def _candidates():
    name = "onnxruntime.dll" if sys.platform == "win32" else "libonnxruntime.so"
    if os.environ.get("ANIMALINUX_ORT_LIB"):
        yield os.environ["ANIMALINUX_ORT_LIB"]
    roots = [Path(getattr(sys, "_MEIPASS", "")), Path(sys.executable).parent]
    for r in roots:
        if str(r):
            yield str(r / "onnxruntime_capi" / name)
    if sys.platform != "win32":
        for d in ("/usr/lib", "/usr/local/lib", "/usr/lib64"):
            yield f"{d}/{name}"


def find_library():
    for c in _candidates():
        if c and os.path.isfile(c):
            return c
    return None


class _Api:
    def __init__(self, path):
        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(os.path.dirname(path))
        self.lib = ctypes.CDLL(path)
        get_base = self.lib.OrtGetApiBase
        get_base.restype = P
        base = get_base()
        if not base:
            raise OrtError("OrtGetApiBase devolvió NULL")
        get_api = ctypes.CFUNCTYPE(P, ctypes.c_uint32)(ctypes.cast(base, PP)[0])
        api = get_api(_API_VERSION)
        if not api:
            raise OrtError("esta onnxruntime no soporta la API pedida")
        table = ctypes.cast(api, PP)
        self.f = {}
        for name, idx in _IDX.items():
            res, *args = _SIG[name]
            self.f[name] = ctypes.CFUNCTYPE(res, *args)(table[idx])

    def check(self, status):
        if status:
            msg = self.f["GetErrorMessage"](status)
            self.f["ReleaseStatus"](status)
            raise OrtError((msg or b"error").decode("utf-8", "replace"))

    def call(self, name, *args):
        self.check(self.f[name](*args))


_api = None


def api():
    global _api
    if _api is None:
        path = find_library()
        if not path:
            raise OrtError("no encontré onnxruntime")
        _api = _Api(path)
    return _api


class _Input:
    def __init__(self, name):
        self.name = name


class Session:
    """Lo mínimo de onnxruntime.InferenceSession que usa core/cutout.py.
    Modelo de UNA entrada y UNA salida float32 de forma fija."""

    def __init__(self, model_path, input_name, output_name, output_shape, threads=0):
        a = self.a = api()
        self.input_name, self.output_name = input_name, output_name
        self.output_shape = tuple(output_shape)
        self.env, self.opts, self.sess, self.mem = P(), P(), P(), P()
        a.call("CreateEnv", _WARNING, b"animalinux", ctypes.byref(self.env))
        a.call("CreateSessionOptions", ctypes.byref(self.opts))
        if threads:
            a.call("SetIntraOpNumThreads", self.opts, int(threads))
        path = str(model_path) if sys.platform == "win32" else os.fsencode(str(model_path))
        a.call("CreateSession", self.env, path, self.opts, ctypes.byref(self.sess))
        a.call("CreateCpuMemoryInfo", _ARENA, _MEM_DEFAULT, ctypes.byref(self.mem))

    def get_inputs(self):
        return [_Input(self.input_name)]

    def run(self, _outputs, feed):
        a = self.a
        x = np.ascontiguousarray(feed[self.input_name], dtype=np.float32)
        shape = (ctypes.c_int64 * x.ndim)(*x.shape)
        val, out = P(), P()
        a.call("CreateTensorWithDataAsOrtValue", self.mem, x.ctypes.data_as(P), x.nbytes,
               shape, x.ndim, _FLOAT, ctypes.byref(val))
        try:
            in_names = (ctypes.c_char_p * 1)(self.input_name.encode())
            out_names = (ctypes.c_char_p * 1)(self.output_name.encode())
            ins = (P * 1)(val)
            a.call("Run", self.sess, None, in_names, ins, 1, out_names, 1, ctypes.byref(out))
            try:
                ptr = P()
                a.call("GetTensorMutableData", out, ctypes.byref(ptr))
                n = int(np.prod(self.output_shape))
                buf = (ctypes.c_float * n).from_address(ptr.value)
                res = np.frombuffer(buf, dtype=np.float32, count=n).reshape(self.output_shape).copy()
            finally:
                a.f["ReleaseValue"](out)
        finally:
            a.f["ReleaseValue"](val)
        return [res]

    def __del__(self):
        try:
            f = self.a.f
            for name, h in (("ReleaseMemoryInfo", self.mem), ("ReleaseSession", self.sess),
                            ("ReleaseSessionOptions", self.opts), ("ReleaseEnv", self.env)):
                if h:
                    f[name](h)
        except Exception:  # noqa: BLE001
            pass
