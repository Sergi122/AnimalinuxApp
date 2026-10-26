"""
Leer y guardar archivos de Aseprite (.aseprite / .ase) sin Aseprite.

Formato oficial: https://github.com/aseprite/aseprite/blob/main/docs/ase-file-specs.md

Se conserva lo que el editor de píxeles entiende: tamaño, capas (nombre,
visible, opacidad), fotogramas con su duración y los píxeles de cada cel.
Al leer, las capas de grupo y de tilemap se saltan, los cels enlazados se
copian y los modos indexado/escala de grises se convierten a RGBA. Al guardar
se escribe RGBA 32 bits con los cels comprimidos (zlib), como Aseprite.
"""
import struct
import zlib

MAGIC_FILE = 0xA5E0
MAGIC_FRAME = 0xF1FA
CHUNK_OLD_PALETTE = 0x0004
CHUNK_LAYER = 0x2004
CHUNK_CEL = 0x2005
CHUNK_PALETTE = 0x2019

MAX_SIDE = 4096
MAX_FRAMES = 1024
MAX_FILE = 256 * 1024 * 1024


class AseError(ValueError):
    pass


class AseLayer:
    def __init__(self, name, visible=True, opacity=255):
        self.name = name
        self.visible = visible
        self.opacity = opacity
        self.frames = []          # bytes RGBA (w*h*4) por fotograma


class AseSprite:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.layers = []          # de abajo hacia arriba
        self.durations = []       # ms por fotograma


# ── lectura ────────────────────────────────────────────────────────────────
class _R:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos

    def take(self, fmt):
        n = struct.calcsize(fmt)
        if self.p + n > len(self.d):
            raise AseError("archivo truncado")
        v = struct.unpack_from(fmt, self.d, self.p)
        self.p += n
        return v if len(v) > 1 else v[0]

    def string(self):
        n = self.take("<H")
        s = self.d[self.p:self.p + n]
        self.p += n
        return s.decode("utf-8", "replace")


def read(path):
    with open(path, "rb") as f:
        data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise AseError("archivo demasiado grande")
    return parse(data)


def parse(data):
    r = _R(data)
    (_size, magic, nframes, w, h, depth, flags, _speed, _z1, _z2,
     transp) = r.take("<IHHHHHIHIIB")
    if magic != MAGIC_FILE:
        raise AseError("no es un archivo de Aseprite")
    if not (0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE) or nframes > MAX_FRAMES:
        raise AseError("tamaño no soportado")
    if depth not in (32, 16, 8):
        raise AseError("profundidad de color no soportada")
    r.p = 128
    bpp = depth // 8
    palette = [(0, 0, 0, 0)] * 256
    has_uuid = bool(flags & 4)

    spr = AseSprite(w, h)
    raw_layers = []                # (tipo, AseLayer|None)
    cels = []                      # por fotograma: {índice_capa: bytes}
    for fi in range(nframes):
        start = r.p
        fbytes, fmagic, old_n, dur, _res, new_n = r.take("<IHHH2sI")
        if fmagic != MAGIC_FRAME:
            raise AseError("fotograma corrupto")
        nchunks = new_n if new_n else old_n
        spr.durations.append(dur or 100)
        frame_cels = {}
        for _ in range(nchunks):
            cstart = r.p
            csize, ctype = r.take("<IH")
            if csize < 6 or cstart + csize > len(data):
                raise AseError("chunk corrupto")
            cr = _R(data, r.p)
            if ctype == CHUNK_LAYER:
                lflags, ltype, _lvl, _dw, _dh, _blend, opac = cr.take("<HHHHHHB")
                cr.p += 3
                name = cr.string()
                if ltype == 2:
                    cr.take("<I")
                if has_uuid:
                    cr.p += 16
                if not (flags & 1):
                    opac = 255
                lay = AseLayer(name, bool(lflags & 1), opac) if ltype == 0 else None
                raw_layers.append((ltype, lay))
            elif ctype == CHUNK_CEL:
                li, x, y, opac, ctyp, _z = cr.take("<HhhBHh")
                cr.p += 5
                if ctyp == 1:
                    link = cr.take("<H")
                    if link < len(cels) and li in cels[link]:
                        frame_cels[li] = cels[link][li]
                elif ctyp in (0, 2):
                    cw, ch = cr.take("<HH")
                    if cw > MAX_SIDE or ch > MAX_SIDE:
                        raise AseError("cel demasiado grande")
                    body = data[cr.p:cstart + csize]
                    if ctyp == 2:
                        d = zlib.decompressobj()
                        body = d.decompress(body, cw * ch * bpp)
                    px = _to_rgba(body[:cw * ch * bpp], cw, ch, bpp, palette, transp)
                    frame_cels[li] = (x, y, cw, ch, px, opac)
            elif ctype == CHUNK_PALETTE:
                _n, first, last = cr.take("<III")
                cr.p += 8
                for i in range(first, min(last, 255) + 1):
                    eflags, pr, pg, pb, pa = cr.take("<HBBBB")
                    if eflags & 1:
                        cr.string()
                    palette[i] = (pr, pg, pb, pa)
            elif ctype == CHUNK_OLD_PALETTE and not any(palette[1:]):
                npk = cr.take("<H")
                idx = 0
                for _ in range(npk):
                    skip, n = cr.take("<BB")
                    idx += skip
                    for _k in range(n or 256):
                        pr, pg, pb = cr.take("<BBB")
                        if idx < 256:
                            palette[idx] = (pr, pg, pb, 255)
                        idx += 1
            r.p = cstart + csize
        cels.append(frame_cels)
        r.p = start + fbytes

    # componer cada cel en un lienzo del tamaño del sprite
    idx_map = {}
    for i, (ltype, lay) in enumerate(raw_layers):
        if lay is not None:
            idx_map[i] = lay
            spr.layers.append(lay)
    if not spr.layers:
        spr.layers.append(AseLayer("Capa 1"))
    for frame_cels in cels:
        for i, lay in idx_map.items():
            lay.frames.append(_place(frame_cels.get(i), w, h))
        if not idx_map:
            spr.layers[0].frames.append(bytes(w * h * 4))
    return spr


def _to_rgba(body, w, h, bpp, palette, transp):
    n = w * h
    if len(body) < n * bpp:
        body = body + bytes(n * bpp - len(body))
    if bpp == 4:
        return bytes(body[:n * 4])
    out = bytearray(n * 4)
    if bpp == 2:
        for i in range(n):
            v, a = body[2 * i], body[2 * i + 1]
            out[4 * i:4 * i + 4] = bytes((v, v, v, a))
    else:
        for i in range(n):
            k = body[i]
            if k == transp:
                continue
            out[4 * i:4 * i + 4] = bytes(palette[k])
    return bytes(out)


def _place(cel, w, h):
    canvas = bytearray(w * h * 4)
    if cel is None:
        return bytes(canvas)
    x, y, cw, ch, px, opac = cel
    for row in range(ch):
        ty = y + row
        if not 0 <= ty < h:
            continue
        x0, x1 = max(0, x), min(w, x + cw)
        if x1 <= x0:
            continue
        src = px[(row * cw + (x0 - x)) * 4:(row * cw + (x1 - x)) * 4]
        if opac < 255:
            src = bytearray(src)
            src[3::4] = bytes(a * opac // 255 for a in src[3::4])
        canvas[(ty * w + x0) * 4:(ty * w + x1) * 4] = src
    return bytes(canvas)


# ── escritura ──────────────────────────────────────────────────────────────
def _chunk(ctype, payload):
    return struct.pack("<IH", len(payload) + 6, ctype) + payload


def _string(s):
    b = s.encode("utf-8")[:65535]
    return struct.pack("<H", len(b)) + b


def write(path, spr):
    with open(path, "wb") as f:
        f.write(build(spr))


def build(spr):
    w, h = spr.width, spr.height
    nframes = len(spr.layers[0].frames) if spr.layers else 0
    frames = []
    for fi in range(nframes):
        chunks = []
        if fi == 0:
            for lay in spr.layers:
                chunks.append(_chunk(CHUNK_LAYER, struct.pack(
                    "<HHHHHHB3s", 1 | 2 if lay.visible else 2, 0, 0, 0, 0, 0,
                    max(0, min(255, int(lay.opacity))), b"\0\0\0") + _string(lay.name)))
            # paleta mínima (Aseprite la espera aunque el sprite sea RGBA)
            chunks.append(_chunk(CHUNK_PALETTE, struct.pack(
                "<III8s", 1, 0, 0, b"\0" * 8) + struct.pack("<HBBBB", 0, 0, 0, 0, 255)))
        for li, lay in enumerate(spr.layers):
            px = lay.frames[fi]
            box = _bbox(px, w, h)
            if box is None:
                continue                      # cel vacío: no se guarda
            x0, y0, x1, y1 = box
            cw, ch = x1 - x0, y1 - y0
            rows = b"".join(px[(y * w + x0) * 4:(y * w + x1) * 4] for y in range(y0, y1))
            chunks.append(_chunk(CHUNK_CEL, struct.pack(
                "<HhhBHh5sHH", li, x0, y0, 255, 2, 0, b"\0" * 5, cw, ch)
                + zlib.compress(rows, 6)))
        body = b"".join(chunks)
        dur = spr.durations[fi] if fi < len(spr.durations) else 100
        n = len(chunks)
        frames.append(struct.pack("<IHHH2sI", 16 + len(body), MAGIC_FRAME,
                                  min(n, 0xFFFF), max(1, int(dur)), b"\0\0", n) + body)
    payload = b"".join(frames)
    header = struct.pack("<IHHHHHIHIIB3sHBBhhHH84s",
                         128 + len(payload), MAGIC_FILE, nframes, w, h, 32, 1,
                         100, 0, 0, 0, b"\0\0\0", 0, 1, 1, 0, 0, 16, 16, b"\0" * 84)
    return header + payload


def _bbox(px, w, h):
    alpha = px[3::4]
    if not any(alpha):
        return None
    ys = [y for y in range(h) if any(alpha[y * w:(y + 1) * w])]
    x0, x1 = w, 0
    for y in ys:
        row = alpha[y * w:(y + 1) * w]
        i0 = next(i for i, a in enumerate(row) if a)
        i1 = w - next(i for i, a in enumerate(reversed(row)) if a)
        x0, x1 = min(x0, i0), max(x1, i1)
    return x0, ys[0], x1, ys[-1] + 1
