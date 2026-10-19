"""usage: dump_ops.py <extracted-dir> <page name> <upi> <x0> <y0> <x1> <y1>   (device-unit box, y down)"""
import os, sys
_D = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_D, os.path.dirname(_D)]
from vsdxconv.model import Doc
from vsdxconv.render import render_page
d, pname, upi = sys.argv[1], sys.argv[2], int(sys.argv[3])
bx0, by0, bx1, by1 = map(float, sys.argv[4:8])
doc = Doc(d)
page = next(p for p in doc.pages if p.name == pname)
ctx = render_page(doc, page, upi)
print("k =", ctx.k, "page", page.width, page.height)
for i, op in enumerate(ctx.ops):
    pts = []
    for sp in op["subpaths"]:
        pts.append(sp.start)
        for s in sp.segs:
            pts.extend(s[1:])
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    if max(xs) < bx0 or min(xs) > bx1 or max(ys) < by0 or min(ys) > by1:
        continue
    st = op["stroke"]
    print(i, "fill", op["fill"], "stroke", (st["color"], round(st["width"], 2), st["pattern"], round(st.get("paper_w", 0), 5)) if st else None,
          "n_sub", len(op["subpaths"]), "bbox", (round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)),
          "first", [tuple(round(c, 1) for c in p) for p in pts[:3]])
