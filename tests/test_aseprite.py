"""Lectura/escritura de .aseprite sin Aseprite."""
import struct
import zlib

from animalinux.editors import aseprite as ase


def _sprite():
    spr = ase.AseSprite(4, 3)
    a = ase.AseLayer("fondo", True, 255)
    b = ase.AseLayer("ojos", False, 128)
    red = bytes((255, 0, 0, 255))
    a.frames = [red * 12, bytes(48)]
    px = bytearray(48)
    px[(1 * 4 + 2) * 4:(1 * 4 + 3) * 4] = bytes((0, 0, 255, 255))
    b.frames = [bytes(px), bytes(px)]
    spr.layers = [a, b]
    spr.durations = [80, 120]
    return spr


def test_roundtrip_keeps_layers_frames_and_pixels():
    spr = _sprite()
    back = ase.parse(ase.build(spr))
    assert (back.width, back.height) == (4, 3)
    assert [l.name for l in back.layers] == ["fondo", "ojos"]
    assert [l.visible for l in back.layers] == [True, False]
    assert back.layers[1].opacity == 128
    assert back.durations == [80, 120]
    for la, lb in zip(spr.layers, back.layers):
        assert la.frames == lb.frames


def test_header_is_what_aseprite_expects():
    data = ase.build(_sprite())
    size, magic, frames, w, h, depth = struct.unpack_from("<IHHHHH", data)
    assert size == len(data) and magic == 0xA5E0 and (frames, w, h, depth) == (2, 4, 3, 32)
    assert struct.unpack_from("<H", data, 128 + 4)[0] == 0xF1FA


def test_reads_indexed_and_linked_cels():
    # sprite indexado 2×1 con paleta, un cel crudo y un fotograma enlazado
    def chunk(t, p):
        return struct.pack("<IH", len(p) + 6, t) + p
    layer = chunk(0x2004, struct.pack("<HHHHHHB3s", 1, 0, 0, 0, 0, 0, 255, b"\0" * 3)
                  + struct.pack("<H", 1) + b"L")
    pal = chunk(0x2019, struct.pack("<III8s", 2, 0, 1, b"\0" * 8)
                + struct.pack("<HBBBB", 0, 0, 0, 0, 0) + struct.pack("<HBBBB", 0, 9, 8, 7, 255))
    cel0 = chunk(0x2005, struct.pack("<HhhBHh5sHH", 0, 0, 0, 255, 0, 0, b"\0" * 5, 2, 1) + bytes((1, 0)))
    cel1 = chunk(0x2005, struct.pack("<HhhBHh5s", 0, 0, 0, 255, 1, 0, b"\0" * 5) + struct.pack("<H", 0))

    def frame(chunks):
        body = b"".join(chunks)
        return struct.pack("<IHHH2sI", 16 + len(body), 0xF1FA, len(chunks), 100, b"\0\0", len(chunks)) + body
    payload = frame([layer, pal, cel0]) + frame([cel1])
    head = struct.pack("<IHHHHHIHIIB3sHBBhhHH84s", 128 + len(payload), 0xA5E0, 2, 2, 1, 8, 1,
                       100, 0, 0, 0, b"\0" * 3, 2, 1, 1, 0, 0, 16, 16, b"\0" * 84)
    spr = ase.parse(head + payload)
    assert spr.layers[0].frames[0] == bytes((9, 8, 7, 255, 0, 0, 0, 0))
    assert spr.layers[0].frames[1] == spr.layers[0].frames[0]


def test_rejects_garbage():
    import pytest
    with pytest.raises(ase.AseError):
        ase.parse(b"\0" * 200)
    assert zlib  # (zlib lo usa el escritor)
