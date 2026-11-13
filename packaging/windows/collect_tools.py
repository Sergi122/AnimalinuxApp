"""Copia ejecutables de MSYS2 (UCRT64) y TODAS sus DLL a una carpeta.

Uso: python collect_tools.py DESTINO ffmpeg ffprobe mpv

Recorre las tablas de importación de cada .exe/.dll (lector PE propio, sin
dependencias) de forma recursiva y copia toda DLL que exista en la carpeta
bin de MSYS2; las del sistema (KERNEL32, api-ms-win-*, …) se quedan fuera.
(`ldd` de MSYS2 se saltaba algunas: libz-1.dll faltó en la primera prueba.)
"""
import os
import shutil
import struct
import sys


def imports(path):
    """Nombres de DLL importadas (tabla normal + carga diferida)."""
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    dd = opt + (112 if magic == 0x20B else 96)          # data directories
    secs = []
    sh = opt + opt_size
    for i in range(nsec):
        vsize, va, raw_size, raw = struct.unpack_from("<IIII", data, sh + i * 40 + 8)
        secs.append((va, max(vsize, raw_size), raw))

    def off(rva):
        for va, size, raw in secs:
            if va <= rva < va + size:
                return rva - va + raw
        return None

    def cstr(o):
        return data[o:data.index(b"\0", o)].decode("ascii", "replace")

    names = []
    for idx, step, name_at in ((1, 20, 12), (13, 32, 4)):   # import, delay-import
        rva, size = struct.unpack_from("<II", data, dd + idx * 8)
        o = off(rva) if rva else None
        while o is not None:
            entry = data[o:o + step]
            if len(entry) < step or not any(entry):
                break
            nrva = struct.unpack_from("<I", entry, name_at)[0]
            no = off(nrva)
            if no is not None:
                names.append(cstr(no))
            o += step
    return names


def main():
    dest = sys.argv[1]
    os.makedirs(dest, exist_ok=True)
    bindir = os.path.dirname(sys.executable)          # C:/msys64/ucrt64/bin
    local = {f.lower(): f for f in os.listdir(bindir) if f.lower().endswith(".dll")}
    todo, seen = [], set()
    for exe in sys.argv[2:]:
        # el .exe de verdad: shutil.which("mpv") devuelve mpv.com (un lanzador)
        src = os.path.join(bindir, exe + ".exe")
        if not os.path.isfile(src):
            sys.exit(f"falta {exe}.exe en {bindir}")
        shutil.copy2(src, dest)
        todo.append(src)
    while todo:
        for dll in imports(todo.pop()):
            key = dll.lower()
            if key in seen or key not in local:
                continue
            seen.add(key)
            p = os.path.join(bindir, local[key])
            shutil.copy2(p, dest)
            todo.append(p)
    # comprobación: toda DLL importada está al lado o es del sistema de Windows
    have = {f.lower() for f in os.listdir(dest)}
    sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    sysdlls = {f.lower() for f in os.listdir(sysdir)} if os.path.isdir(sysdir) else set()
    for f in os.listdir(dest):
        miss = [d for d in imports(os.path.join(dest, f))
                if d.lower() not in have and d.lower() not in sysdlls
                and not d.lower().startswith(("api-ms-", "ext-ms-"))]
        if miss:
            sys.exit(f"a {f} le faltan {miss}")
    size = sum(os.path.getsize(os.path.join(dest, f)) for f in os.listdir(dest))
    print(f"tools: {len(have)} archivos, {size / 2**20:.0f} MB")


if __name__ == "__main__":
    main()
