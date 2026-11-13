"""Aísla las DLL de Vosk de las de MSYS2.

La rueda oficial de Vosk para Windows trae libvosk.dll compilada con MinGW
para *msvcrt* y su propia libstdc++-6.dll / libgcc_s_seh-1.dll /
libwinpthread-1.dll. El Python de MSYS2 (UCRT) ya tiene cargadas unas DLL
con esos MISMOS nombres pero para *ucrt*, y Windows reutiliza las que ya
están en memoria → libvosk.dll falla al cargar (error 0x7f, falta una
función). Solución: renombrar las tres auxiliares a nombres propios del
mismo largo y cambiar esos nombres dentro de las tablas de importación.

Uso: python patch_vosk.py <carpeta del paquete vosk>
"""
import os
import sys

RENAME = {                       # mismo largo: el parche es byte a byte
    b"libstdc++-6.dll": b"libvskcpp-6.dll",
    b"libgcc_s_seh-1.dll": b"libvskgcc_seh1.dll",
    b"libwinpthread-1.dll": b"libvskpthread-1.dll",
}
for a, b in RENAME.items():
    assert len(a) == len(b)

d = sys.argv[1]
files = ["libvosk.dll"] + [a.decode() for a in RENAME]
for name in files:
    src = os.path.join(d, name)
    if not os.path.exists(src):          # ya parchado antes
        continue
    data = open(src, "rb").read()
    n = 0
    for a, b in RENAME.items():
        for variant in (a, a.upper()):
            n += data.count(variant)
            data = data.replace(variant, b if variant == a else b.upper())
    new = RENAME.get(name.encode(), name.encode()).decode()
    open(os.path.join(d, new), "wb").write(data)
    if new != name:
        os.remove(src)
    print(f"{name} -> {new}: {n} referencias cambiadas")
