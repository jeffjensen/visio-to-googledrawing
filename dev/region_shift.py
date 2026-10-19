"""Sub-pixel shift between mine and ref per region.
usage: region_shift.py <mine.png> <ref.png> <dx> <dy> name:x,y,w,h [name:x,y,w,h ...]
(ref region coords; mine region = ref + (dx,dy)).  Reports (sx, sy) such that mine ~ ref shifted by (sx, sy) pixels."""
import sys
import numpy as np
from PIL import Image

def load(p): return 255 - np.asarray(Image.open(p).convert("L"), dtype=np.float32)

def shift(a, b, up=8, search=6):
    A = np.asarray(Image.fromarray(a).resize((a.shape[1]*up, a.shape[0]*up), Image.BICUBIC), dtype=np.float32)
    B = np.asarray(Image.fromarray(b).resize((b.shape[1]*up, b.shape[0]*up), Image.BICUBIC), dtype=np.float32)
    best, bs = -1e18, (0, 0)
    s = search * up
    # coarse-to-fine: step 2 then refine
    for step in (4, 1):
        cy, cx = bs
        rng = range(-s if step == 4 else cy-4, (s+1) if step == 4 else cy+5, step)
        rngx = range(-s if step == 4 else cx-4, (s+1) if step == 4 else cx+5, step)
        for dy in rng:
            for dx in rngx:
                y0, y1 = max(0, dy), min(A.shape[0], A.shape[0] + dy)
                x0, x1 = max(0, dx), min(A.shape[1], A.shape[1] + dx)
                aa = A[y0:y1, x0:x1]; bb = B[y0-dy:y1-dy, x0-dx:x1-dx]
                sc = float((aa*bb).sum())
                if sc > best: best, bs = sc, (dy, dx)
    return bs[1]/up, bs[0]/up

mine = load(sys.argv[1]); ref = load(sys.argv[2])
dx, dy = int(sys.argv[3]), int(sys.argv[4])
for spec in sys.argv[5:]:
    name, rest = spec.split(":")
    x, y, w, h = map(int, rest.split(","))
    r = ref[y:y+h, x:x+w]
    m = mine[y+dy:y+dy+h, x+dx:x+dx+w]
    sx, sy = shift(r, m)
    print(f"{name:14} ref ink shift needed: ref = mine shifted by (x={sx:+.2f}, y={sy:+.2f}) px")
