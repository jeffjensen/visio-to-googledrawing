"""usage: baselines.py <png> x y w h   -> baseline rows (sub-pixel) of text lines in the region"""
import sys
import numpy as np
from PIL import Image
p = sys.argv[1]; x, y, w, h = map(int, sys.argv[2:6])
a = 255 - np.asarray(Image.open(p).convert("L"), dtype=np.float64)[y:y+h, x:x+w]
prof = a.sum(axis=1)
# lines = contiguous groups of rows with ink
rows = prof > prof.max() * 0.04
lines, start = [], None
for i, r in enumerate(rows):
    if r and start is None: start = i
    if (not r) and start is not None:
        lines.append((start, i)); start = None
if start is not None: lines.append((start, len(rows)))
out = []
for s, e in lines:
    seg = prof[max(0, s-1):e+2]
    # baseline = location of the steepest ink decrease after the main body (centroid of drop)
    d = seg[:-1] - seg[1:]
    k = int(np.argmax(d))
    # sub-pixel: weight of top 3 around k
    ks = np.arange(max(0, k-1), min(len(d), k+2))
    base = float((ks * d[ks]).sum() / d[ks].sum()) + max(0, s-1) + y + 1.0
    out.append(round(base, 2))
print("line top/bottom rows:", [(s+y, e+y) for s, e in lines])
print("baselines:", out, " pitches:", [round(out[i+1]-out[i], 2) for i in range(len(out)-1)])
