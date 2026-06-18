"""
Utilidades compartidas por los editores (píxel y pintura).

De momento centraliza la conversión RGBA→BGRA premultiplicado que cairo
necesita para crear superficies (Format.ARGB32). Antes estaba duplicada en
ambos editores. Usa numpy si está disponible (rápido) o un fallback en Python
puro.
"""
try:
    import numpy as np
    _NP = True
except ImportError:  # numpy es opcional
    _NP = False


def premultiply_bgra(data: bytes, w: int, h: int) -> bytearray:
    """Convierte bytes RGBA (orden Pillow) a BGRA premultiplicado por alfa,
    el formato que espera cairo.ImageSurface (Format.ARGB32, little-endian)."""
    if _NP:
        arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 4)
        af  = arr[:, :, 3:4].astype(np.float32) / 255.0
        pre = (arr[:, :, :3].astype(np.float32) * af).astype(np.uint8)
        out = np.empty((h, w, 4), dtype=np.uint8)
        out[:, :, 0] = pre[:, :, 2]
        out[:, :, 1] = pre[:, :, 1]
        out[:, :, 2] = pre[:, :, 0]
        out[:, :, 3] = arr[:, :, 3]
        return bytearray(out.tobytes())
    out = bytearray(len(data))
    for i in range(w * h):
        r, g, b, a = data[i*4], data[i*4+1], data[i*4+2], data[i*4+3]
        f = a / 255
        out[i*4], out[i*4+1], out[i*4+2], out[i*4+3] = (
            int(b*f), int(g*f), int(r*f), a)
    return out


def pil_to_cairo(im) -> bytearray:
    """Igual que premultiply_bgra pero tomando una imagen Pillow RGBA."""
    w, h = im.size
    return premultiply_bgra(im.tobytes(), w, h)
