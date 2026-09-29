#!/usr/bin/env python3
"""Auditoría de solo lectura de la biblioteca de AnimaLinux.
Uso: python audit.py [--json salida.json]
Mide por animación/pose: nº de cuadros, tamaño, peso, duplicados, movimiento,
salto del bucle (último→primero), deriva de la base (pies) y bordes semitransparentes."""
import json, os, sys, hashlib, glob
import numpy as np
from PIL import Image
cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
lib = json.load(open(f"{cfg}/animalinux/library.json"))
anims = lib.get("animations", lib)
root = f"{data}/animalinux/animations"

def load(paths):
    out = []
    for p in paths:
        try: out.append(np.asarray(Image.open(p).convert("RGBA")))
        except Exception: out.append(None)
    return out

def analyze(paths):
    r = {"frames": len(paths), "bytes": sum(os.path.getsize(p) for p in paths)}
    if not paths: return r
    fr = load(paths)
    ok = [f for f in fr if f is not None]
    r["unreadable"] = len(fr) - len(ok)
    if not ok: return r
    sizes = {f.shape[:2] for f in ok}
    r["sizes"] = sorted(f"{w}x{h}" for h, w in sizes)
    H, W = ok[0].shape[:2]
    r["px"] = f"{W}x{H}"
    hashes = [hashlib.md5(f.tobytes()).hexdigest() for f in ok]
    r["duplicates"] = len(hashes) - len(set(hashes))
    same = [f for f in ok if f.shape[:2] == (H, W)]
    if len(same) > 1:
        a = [f.astype(np.int16) for f in same]
        d = [float(np.abs(a[i + 1] - a[i]).mean()) for i in range(len(a) - 1)]
        r["motion_mean"] = round(float(np.mean(d)), 3)
        r["near_static_steps"] = sum(1 for x in d if x < 0.05)
        r["loop_seam"] = round(float(np.abs(a[0] - a[-1]).mean()), 3)
        r["seam_vs_motion"] = round(r["loop_seam"] / (r["motion_mean"] + 1e-6), 2)
    bots, cxs, fringe, empty = [], [], [], 0
    for f in same:
        al = f[..., 3]; ys, xs = np.nonzero(al > 8)
        if len(ys) == 0: empty += 1; continue
        bots.append(int(ys.max())); cxs.append(float(xs.mean()))
        fringe.append(float(((al > 8) & (al < 200)).sum() / max(1, (al > 8).sum())))
    r["empty_frames"] = empty
    if bots:
        r["foot_drift_px"] = int(max(bots) - min(bots))
        r["center_drift_px"] = round(max(cxs) - min(cxs), 1)
        r["fringe_ratio"] = round(float(np.mean(fringe)), 3)
        r["fill_ratio"] = round(float(np.mean([(f[..., 3] > 8).mean() for f in same])), 3)
    return r

def issues(name, r, fps):
    out = []
    if r.get("frames", 0) == 0: return ["sin cuadros"]
    if r.get("unreadable"): out.append(f"{r['unreadable']} cuadros ilegibles")
    if len(r.get("sizes", [])) > 1: out.append("cuadros de tamaños distintos " + ",".join(r["sizes"]))
    if r["frames"] < 2: out.append("un solo cuadro (no se mueve)")
    if r.get("duplicates", 0) > r["frames"] * 0.3: out.append(f"{r['duplicates']} cuadros idénticos (desperdicio)")
    if r.get("near_static_steps", 0) > r["frames"] * 0.5: out.append("casi estática")
    if r.get("seam_vs_motion", 0) > 2.5: out.append(f"salto al reiniciar el bucle (x{r['seam_vs_motion']})")
    if r.get("foot_drift_px", 0) > 6 and name not in ("jump", "grab"): out.append(f"la base se mueve {r['foot_drift_px']}px (patina)")
    if r.get("fringe_ratio", 0) > 0.12: out.append(f"bordes semitransparentes {int(r['fringe_ratio']*100)}% (halo)")
    if r["bytes"] / max(1, r["frames"]) > 250_000: out.append(f"pesado: {r['bytes']//r['frames']//1024} KB/cuadro")
    if fps and fps > 24: out.append(f"fps alto ({fps})")
    return out

report = []
for aid, a in anims.items():
    d = f"{root}/{aid}"
    ent = {"id": aid, "name": a.get("name"), "mode": a.get("mode"), "fps": a.get("fps"), "poses": {}}
    top = sorted(glob.glob(f"{d}/*.png"))
    if top: ent["base"] = analyze(top); ent["base"]["issues"] = issues("base", ent["base"], a.get("fps"))
    for pd in sorted(p for p in glob.glob(f"{d}/*") if os.path.isdir(p)):
        pose = os.path.basename(pd)
        r = analyze(sorted(glob.glob(f"{pd}/*.png")))
        r["issues"] = issues(pose, r, a.get("fps")); ent["poses"][pose] = r
    ent["total_bytes"] = sum(os.path.getsize(p) for p in glob.glob(f"{d}/**/*", recursive=True) if os.path.isfile(p))
    report.append(ent)

if "--json" in sys.argv:
    json.dump(report, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1, ensure_ascii=False)
for e in report:
    print(f"\n== {e['name']} [{e['id']}] modo={e['mode']} fps={e['fps']} peso={e['total_bytes']//1024} KB")
    if "base" in e:
        b = e["base"]; print(f"  base: {b['frames']} cuadros {b.get('px')} mov={b.get('motion_mean')} costura={b.get('loop_seam')}", *[f"\n    ! {i}" for i in b["issues"]])
    for p, r in e["poses"].items():
        print(f"  {p}: {r['frames']} cuadros {r.get('px')} mov={r.get('motion_mean')} costura={r.get('loop_seam')} pies±{r.get('foot_drift_px')} {r['bytes']//1024}KB", *[f"\n    ! {i}" for i in r["issues"]])
