"""Compare Google's exported rendering of an uploaded Drawing with my expected rendering.

usage: venv python verify_page.py <extracted-dir> <page name> <tool-result.json> <out-prefix> [--upi N] [--crop IN] [--dpi N]

Writes <out-prefix>_google.svg/.png, <out-prefix>_expected.svg/.png and <out-prefix>_overlay.png
(google = red channel removed where only google has ink -> cyan; expected-only -> red; both -> black).
"""
import argparse
import base64
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]

from vsdxconv.model import Doc               # noqa: E402
from vsdxconv.render import crop_to_content, render_page  # noqa: E402
from vsdxconv.svgprev import to_svg_canvas   # noqa: E402


def magick_render(svg, png, dpi):
    subprocess.run(["magick", "-density", str(dpi), "-background", "white", svg, "-flatten", png], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("page")
    ap.add_argument("result_json")
    ap.add_argument("prefix")
    ap.add_argument("--upi", type=int, default=3000)
    ap.add_argument("--crop", type=float, default=0.25)
    ap.add_argument("--dpi", type=int, default=192)
    a = ap.parse_args()
    obj = json.load(open(a.result_json, encoding="utf-8"))
    google_svg = a.prefix + "_google.svg"
    with open(google_svg, "wb") as f:
        f.write(base64.b64decode(obj["content"]))
    doc = Doc(a.src)
    page = next(p for p in doc.pages if p.name == a.page)
    ctx = render_page(doc, page, a.upi)
    w, h = crop_to_content(ctx.ops, a.crop * a.upi)
    svg, s, ox, oy = to_svg_canvas(ctx.ops, round(w), round(h))
    exp_svg = a.prefix + "_expected.svg"
    with open(exp_svg, "w", encoding="utf-8") as f:
        f.write(svg)
    print("EMF bounds %dx%d  expected canvas scale %.6f offset (%.2f, %.2f)" % (round(w), round(h), s, ox, oy))
    g_png, e_png = a.prefix + "_google.png", a.prefix + "_expected.png"
    magick_render(google_svg, g_png, a.dpi)
    magick_render(exp_svg, e_png, a.dpi)
    g = 255 - np.asarray(Image.open(g_png).convert("L"), dtype=np.float32)
    e = 255 - np.asarray(Image.open(e_png).convert("L"), dtype=np.float32)
    if g.shape != e.shape:
        print("size mismatch", g.shape, e.shape)
        h2, w2 = min(g.shape[0], e.shape[0]), min(g.shape[1], e.shape[1])
        g, e = g[:h2, :w2], e[:h2, :w2]
    g, e = g / 255.0, e / 255.0
    both, g_only, e_only = np.minimum(g, e), np.clip(g - e, 0, 1), np.clip(e - g, 0, 1)
    img = np.ones(g.shape + (3,), dtype=np.float32)
    img[..., 0] -= (both + g_only)          # google-only -> cyan
    img[..., 1] -= (both + e_only)          # expected-only -> magenta/red
    img[..., 2] -= (both + e_only)
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(a.prefix + "_overlay.png")
    print("ink: google %.0f expected %.0f both %.0f -> overlap %.3f; google-only %.3f expected-only %.3f (fractions of union)"
          % (g.sum(), e.sum(), both.sum(), both.sum() / np.maximum(g, e).sum(),
             g_only.sum() / np.maximum(g, e).sum(), e_only.sum() / np.maximum(g, e).sum()))


if __name__ == "__main__":
    main()
