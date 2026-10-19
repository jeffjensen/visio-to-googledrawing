"""Walk a Visio page and produce flat draw operations in output (EMF logical) units.

Output units: x to the right, y down, `upi` units per *paper* inch.  Each op is a dict:
    {'kind': 'path', 'subpaths': [Subpath...], 'fill': '#rrggbb'|None,
     'stroke': {'color','width','pattern'}|None}
"""
import math

from .geom import geometry, local_matrix, mapply, mmul, rotate, translate, Subpath
from .model import fnum
from .text import get_face, importer_text_params, layout, natural_size, parse_paragraphs

ARROW_SIZE = [0.6, 0.8, 1.0, 1.3, 1.7, 2.3, 3.0]     # BeginArrowSize / EndArrowSize index factors


class Ctx:
    def __init__(self, doc, page, upi, text_mode="importer"):
        self.doc, self.page, self.upi = doc, page, upi
        self.text_mode = text_mode                      # 'importer': text records; 'outline': glyph paths
        self.k = page.paper_ratio * upi                 # output units per drawing inch
        self.ops = []

    def to_dev(self, p):
        return (p[0] * self.k, (self.page.height - p[1]) * self.k)

    def dev_path(self, sp_page):
        """Subpath in page coordinates -> output units"""
        sp = Subpath(self.to_dev(sp_page.start))
        for s in sp_page.segs:
            sp.segs.append((s[0],) + tuple(self.to_dev(p) for p in s[1:]))
        sp.closed = sp_page.closed
        return sp


def _line_spec(ctx, shape, gs):
    if gs.no_line:
        return None
    pat = int(fnum(shape.value("LinePattern"), 1))
    if pat == 0:
        return None
    w = fnum(shape.value("LineWeight"), 0.0104166)
    color = ctx.doc.color(shape.value("LineColor"), "#000000")
    return {"color": color, "width": max(w * ctx.upi, 1.0), "pattern": pat, "paper_w": w}


def _fill_spec(ctx, shape, gs):
    if gs.no_fill:
        return None
    pat = int(fnum(shape.value("FillPattern"), 1))
    if pat == 0:
        return None
    return ctx.doc.color(shape.value("FillForegnd"), "#FFFFFF")


def _arrow(ctx, tip, direction, kind, size_ix, paper_w, color):
    """filled triangular arrowhead with its tip at `tip` pointing along `direction` (output units)"""
    f = ARROW_SIZE[max(0, min(6, size_ix))]
    lw = max(paper_w, 0.0033)
    length, width = 6.0 * lw * f * ctx.upi, 8.0 * lw * f * ctx.upi
    dx, dy = direction
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    bx, by = tip[0] - dx * length, tip[1] - dy * length
    nx, ny = -dy, dx
    sp = Subpath(tip)
    sp.segs = [("L", (bx + nx * width / 2, by + ny * width / 2)), ("L", (bx - nx * width / 2, by - ny * width / 2)),
               ("L", tip)]
    sp.closed = True
    ctx.ops.append({"kind": "path", "subpaths": [sp], "fill": color, "stroke": None})


def _tangent_start(sp):
    s = sp.segs[0]
    p1 = s[1]
    return (sp.start[0] - p1[0], sp.start[1] - p1[1])          # pointing away from the path (outward)


def _tangent_end(sp):
    s = sp.segs[-1]
    prev = s[-2] if s[0] == "C" else (sp.segs[-2][-1] if len(sp.segs) > 1 else sp.start)
    return (s[-1][0] - prev[0], s[-1][1] - prev[1])


def render_geometry(ctx, shape, m):
    for gs in geometry(shape):
        if gs.no_show or not gs.subpaths:
            continue
        fill = _fill_spec(ctx, shape, gs)
        line = _line_spec(ctx, shape, gs)
        if fill is None and line is None:
            continue
        subs = [ctx.dev_path(sp.transformed(m)) for sp in gs.subpaths if sp.segs]
        if not subs:
            continue
        ctx.ops.append({"kind": "path", "subpaths": subs, "fill": fill, "stroke": line})
        if line is not None:
            barrow = int(fnum(shape.value("BeginArrow"), 0))
            earrow = int(fnum(shape.value("EndArrow"), 0))
            open_subs = [s for s in subs if not s.closed]
            if barrow and open_subs:
                _arrow(ctx, open_subs[0].start, _tangent_start(open_subs[0]), barrow,
                       int(fnum(shape.value("BeginArrowSize"), 2)), line["paper_w"], line["color"])
            if earrow and open_subs:
                last = open_subs[-1]
                _arrow(ctx, last.end(), _tangent_end(last), earrow,
                       int(fnum(shape.value("EndArrowSize"), 2)), line["paper_w"], line["color"])


def _rect_subpath(x0, y0, x1, y1):
    sp = Subpath((x0, y0))
    sp.segs = [("L", (x1, y0)), ("L", (x1, y1)), ("L", (x0, y1)), ("L", (x0, y0))]
    sp.closed = True
    return sp


def render_text(ctx, shape, m):
    if fnum(shape.cell("HideText"), 0) != 0:
        return
    paras = parse_paragraphs(shape)
    if not paras:
        return
    r = ctx.page.paper_ratio
    w, h = shape.num("Width"), shape.num("Height")
    if shape.cell("TxtWidth") is None and shape.cell("BeginX") is not None:
        # 1-D shape without text-block cells: the block fits the text
        nw, nh = natural_size(shape, paras)
        txtw, txth = nw / r, nh / r
    else:
        txtw = fnum(shape.cell("TxtWidth"), w)
        txth = fnum(shape.cell("TxtHeight"), h)
    pinx = fnum(shape.cell("TxtPinX"), w / 2.0)
    piny = fnum(shape.cell("TxtPinY"), h / 2.0)
    locx = fnum(shape.cell("TxtLocPinX"), txtw / 2.0)
    locy = fnum(shape.cell("TxtLocPinY"), txth / 2.0)
    ang = fnum(shape.cell("TxtAngle"), 0.0)
    # text block (drawing inches, origin bottom-left, y up) -> page
    b2p = mmul(m, mmul(translate(pinx, piny), mmul(rotate(ang), translate(-locx, -locy))))

    def to_dev(u, v):
        return ctx.to_dev(mapply(b2p, (u, v)))

    placed = layout(shape, paras, txtw * r, txth * r)

    # optional opaque text background (white boxes behind line labels): Visio hugs the text lines
    bk = shape.value("TextBkgnd")
    if bk is not None and bk not in ("0", "Themed") and placed:
        pad = 0.012
        x_lo = min(x0 for _, x0, ln in placed) - pad
        x_hi = max(x0 + ln.width for _, x0, ln in placed) + pad
        y_lo = placed[0][0] - 0.75 * placed[0][2].size - pad
        y_hi = placed[-1][0] + 0.25 * placed[-1][2].size + pad
        corners = [(x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi), (x_lo, y_lo)]
        pts = [to_dev(px / r, txth - py / r) for px, py in corners]
        sp = Subpath(pts[0])
        sp.segs = [("L", p) for p in pts[1:]]
        sp.closed = True
        ctx.ops.append({"kind": "path", "subpaths": [sp], "fill": ctx.doc.color(bk, "#FFFFFF"), "stroke": None})
    if ctx.text_mode == "importer":
        _emit_importer_text(ctx, placed, r, txth, to_dev)
        return
    by_color = {}
    for baseline, x0, ln in placed:
        x = x0
        for tok in ln.toks:
            face = get_face(tok.fmt.bits)
            x_start = x
            for gid, adv, xoff, yoff in tok.glyphs:
                for c in face.outline(gid):
                    def tf(p, x=x, xoff=xoff, yoff=yoff, size=tok.size):
                        px = x + (xoff + p[0]) * size
                        py = baseline - (yoff + p[1]) * size
                        return to_dev(px / r, txth - py / r)
                    sp = Subpath(tf(c.start))
                    for s in c.segs:
                        sp.segs.append((s[0],) + tuple(tf(p) for p in s[1:]))
                    sp.closed = True
                    by_color.setdefault(tok.fmt.color, []).append(sp)
                x += adv * tok.size + tok.fmt.letterspace
            if tok.fmt.bits & 4:                               # underline, continuous across spaces
                ypos = baseline - face.underline_pos * tok.size
                th = max(face.underline_thick * tok.size, 0.004)
                p0 = to_dev(x_start / r, txth - (ypos - th / 2) / r)
                p1 = to_dev(x / r, txth - (ypos + th / 2) / r)
                by_color.setdefault(tok.fmt.color, []).append(_rect_subpath(p0[0], p0[1], p1[0], p1[1]))
    for color, subs in by_color.items():
        ctx.ops.append({"kind": "path", "subpaths": subs, "fill": color, "stroke": None})


def _emit_importer_text(ctx, placed, r, txth, to_dev):
    """One text record per same-format run of a laid-out line (Google's importer renders them)."""
    for baseline, x0, ln in placed:
        x = x0
        i = 0
        toks = ln.toks
        while i < len(toks):
            key = (toks[i].fmt.bits & 7, toks[i].fmt.color, round(toks[i].size, 5))
            j = i
            adv = 0.0
            text = ""
            while j < len(toks) and (toks[j].fmt.bits & 7, toks[j].fmt.color, round(toks[j].size, 5)) == key:
                adv += toks[j].adv
                text += toks[j].text
                j += 1
            bits, color, size = toks[i].fmt.bits, toks[i].fmt.color, toks[i].size
            if text.strip() or (bits & 4):
                o = to_dev(x / r, txth - baseline / r)
                n = to_dev((x + 1.0) / r, txth - baseline / r)          # one paper inch along the baseline
                ang = math.atan2(-(n[1] - o[1]), n[0] - o[0])
                em, lfw = importer_text_params(bits, size, adv, text, ctx.upi)
                # text box (for cropping): baseline origin, advance along the direction, 0.75/0.25 em up/down
                ux, uy = math.cos(ang), -math.sin(ang)
                vx, vy = -math.sin(ang), -math.cos(ang)
                w_u, a_u, d_u = adv * ctx.upi, 0.78 * em, 0.25 * em
                quad = [(o[0] + vx * a_u, o[1] + vy * a_u), (o[0] + ux * w_u + vx * a_u, o[1] + uy * w_u + vy * a_u),
                        (o[0] + ux * w_u - vx * d_u, o[1] + uy * w_u - vy * d_u), (o[0] - vx * d_u, o[1] - vy * d_u)]
                ctx.ops.append({"kind": "text", "x": o[0], "y": o[1], "angle10": int(round(math.degrees(ang) * 10)) % 3600,
                                "em": em, "lfw": lfw, "bits": bits, "color": color, "text": text, "quad": quad,
                                "subpaths": [], "fill": None, "stroke": None})
            x += adv
            i = j


def render_shape(ctx, shape, parent_m):
    if shape.type == "Guide":
        return
    m = mmul(parent_m, local_matrix(shape))
    render_geometry(ctx, shape, m)
    for ch in shape.children:
        render_shape(ctx, ch, m)
    render_text(ctx, shape, m)


def render_page(doc, page, upi, text_mode="importer"):
    ctx = Ctx(doc, page, upi, text_mode)
    ident = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for s in page.shapes:
        render_shape(ctx, s, ident)
    return ctx


def crop_to_content(ops, margin_units):
    """Translate all ops so the content bounding box (plus margin) starts at the origin.
    Returns (width, height) of the cropped canvas in output units."""
    xs, ys = [], []
    for op in ops:
        half = op["stroke"]["width"] / 2.0 if op["stroke"] else 0.0
        for sp in op["subpaths"]:
            pts = [sp.start] + [p for s in sp.segs for p in s[1:]]
            for x, y in pts:
                xs += [x - half, x + half]
                ys += [y - half, y + half]
        for x, y in op.get("quad", ()):
            xs.append(x)
            ys.append(y)
    x0, y0 = min(xs) - margin_units, min(ys) - margin_units
    x1, y1 = max(xs) + margin_units, max(ys) + margin_units
    for op in ops:
        op["subpaths"] = [sp.shifted(-x0, -y0) for sp in op["subpaths"]]
        if op["kind"] == "text":
            op["x"] -= x0
            op["y"] -= y0
            op["quad"] = [(x - x0, y - y0) for x, y in op["quad"]]
    return x1 - x0, y1 - y0
