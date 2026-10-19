"""Overlay a rendered preview on a reference PNG.

usage: python compare.py <mine.png> <ref.png> <out.png> [--mine-dpi N]
Finds the translation (and checks scale) that best aligns `mine` (scaled to 96 dpi) to `ref`
by cross-correlating ink masks, then writes an overlay: ref=red channel, mine=cyan.
"""
import sys
import numpy as np
from PIL import Image

def ink(path, scale_to=None):
    im = Image.open(path).convert("L")
    if scale_to:
        im = im.resize(scale_to, Image.LANCZOS)
    a = 255 - np.asarray(im, dtype=np.float32)
    return a / 255.0

def best_shift(a, b, search=80):
    """shift (dy,dx) so that b[y-dy, x-dx] ~ a[y,x]; coarse FFT correlation"""
    H = max(a.shape[0], b.shape[0]) + 2*search
    W = max(a.shape[1], b.shape[1]) + 2*search
    fa = np.fft.rfft2(a, s=(H, W)); fb = np.fft.rfft2(b, s=(H, W))
    corr = np.fft.irfft2(fa * np.conj(fb), s=(H, W))
    idx = np.unravel_index(np.argmax(corr), corr.shape)
    dy = idx[0] if idx[0] < H//2 else idx[0]-H
    dx = idx[1] if idx[1] < W//2 else idx[1]-W
    return dy, dx

def main():
    mine_p, ref_p, out_p = sys.argv[1:4]
    mine_im = Image.open(mine_p).convert("L")
    scale = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[4] == "--scale" else 1.0
    if scale != 1.0:
        mine_im = mine_im.resize((round(mine_im.width*scale), round(mine_im.height*scale)), Image.LANCZOS)
        mine_im.save(out_p + ".mine.png")
        mine_p = out_p + ".mine.png"
    a = ink(ref_p); b = ink(mine_p)
    dy, dx = best_shift(a, b)
    print("shift (mine -> ref): dy=%d dx=%d   ref=%s mine=%s" % (dy, dx, a.shape, b.shape))
    H, W = a.shape
    m = np.zeros_like(a)
    ys, xs = max(0, dy), max(0, dx)
    # place b shifted by (dy,dx)
    y0, x0 = dy, dx
    for y in range(max(0, y0), min(H, y0 + b.shape[0])):
        pass
    canvas = np.zeros((H, W), dtype=np.float32)
    sy0, sx0 = max(0, -y0), max(0, -x0)
    dy0, dx0 = max(0, y0), max(0, x0)
    h = min(b.shape[0]-sy0, H-dy0); w = min(b.shape[1]-sx0, W-dx0)
    canvas[dy0:dy0+h, dx0:dx0+w] = b[sy0:sy0+h, sx0:sx0+w]
    out = np.ones((H, W, 3), dtype=np.float32)
    out[..., 0] = 1 - canvas          # mine only -> remove red => cyan
    out[..., 1] = 1 - a               # ref only  -> remove green => magenta/red
    out[..., 2] = 1 - np.maximum(a, canvas) * 0 - 0
    # simpler: R = 1 - mine ; G = 1 - min(1, ref+mine) ... use classic: ref->red, mine->cyan, both->black
    out[..., 0] = 1 - canvas
    out[..., 1] = 1 - np.maximum(a, canvas)
    out[..., 2] = 1 - np.maximum(a, canvas)
    # where both present: black-ish; ref only (a>0,canvas=0): R=1,G=1-a,B=1-a -> red; mine only: R=1-c,G=1-c,B=1-c? fix below
    both = np.minimum(a, canvas)
    ref_only = np.clip(a - canvas, 0, 1)
    mine_only = np.clip(canvas - a, 0, 1)
    img = np.ones((H, W, 3), dtype=np.float32)
    img[..., 0] -= (both + mine_only)          # mine & both remove red -> appear cyan/black
    img[..., 1] -= (both + ref_only)
    img[..., 2] -= (both + ref_only)
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out_p)
    inter = float((both).sum()); uni = float(np.maximum(a, canvas).sum())
    print("ink overlap (IoU-like): %.3f" % (inter / uni))

main()
