"""Draw operations -> SVG, for distortion-free previews and comparisons against the Visio PNGs."""

import math

from .text import LFWIDTH_REF, ROBOTO_K, roboto_face

DASHES = {2: (6, 3), 3: (1.5, 3), 4: (6, 3, 1.5, 3), 5: (6, 3, 1.5, 3, 1.5, 3)}


def _text_path(op):
    """Roboto outlines positioned the way the importer renders a text record (for previews)."""
    face, key = roboto_face(op["bits"])
    em = op["em"]
    sx = op["lfw"] / (LFWIDTH_REF * em) * ROBOTO_K[key]
    ang = math.radians(op["angle10"] / 10.0)
    ux, uy = math.cos(ang), -math.sin(ang)
    vx, vy = -math.sin(ang), -math.cos(ang)
    ox, oy = op["x"], op["y"]
    out = []
    x = 0.0
    for gid, adv, xoff, yoff in face.shape(op["text"]):
        for c in face.outline(gid):
            def tf(p, x=x):
                gx, gy = (x + xoff + p[0]) * em * sx, (yoff + p[1]) * em
                return (ox + ux * gx + vx * gy, oy + uy * gx + vy * gy)
            pts = ["M%.2f %.2f" % tf(c.start)]
            for sg in c.segs:
                q = [tf(pt) for pt in sg[1:]]
                pts.append("L%.2f %.2f" % q[0] if sg[0] == "L" else "C%.2f %.2f %.2f %.2f %.2f %.2f" % (q[0] + q[1] + q[2]))
            out.append("".join(pts) + "Z")
        x += adv
    if op["bits"] & 4:
        w = x * em * sx
        th, pos = 0.07 * em, 0.1 * em
        q = [(0, pos - th / 2), (w, pos - th / 2), (w, pos + th / 2), (0, pos + th / 2)]
        pts = [(ox + ux * a + vx * -b, oy + uy * a + vy * -b) for a, b in q]
        out.append("M%.2f %.2f" % pts[0] + "".join("L%.2f %.2f" % p for p in pts[1:]) + "Z")
    return "".join(out)


def _d(sp):
    out = ["M%.2f %.2f" % sp.start]
    for s in sp.segs:
        if s[0] == "L":
            out.append("L%.2f %.2f" % s[1])
        else:
            out.append("C%.2f %.2f %.2f %.2f %.2f %.2f" % (s[1] + s[2] + s[3]))
    if sp.closed:
        out.append("Z")
    return "".join(out)


def to_svg_canvas(ops, width_units, height_units, canvas_w=800.0, canvas_h=600.0, margin=11.0 / 12.0):
    """How Google's metafile importer lays the picture into its fixed 800x600 canvas:
    uniform scale to fit within `margin` of the canvas, centred."""
    s = min(canvas_w * margin / width_units, canvas_h * margin / height_units)
    ox, oy = (canvas_w - width_units * s) / 2.0, (canvas_h - height_units * s) / 2.0
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
             % (canvas_w, canvas_h, canvas_w, canvas_h), '<rect width="100%" height="100%" fill="#ffffff"/>',
             '<g transform="translate(%.4f %.4f) scale(%.6f)">' % (ox, oy, s)]
    parts += _op_elements(ops)
    parts += ["</g>", "</svg>"]
    return "\n".join(parts), s, ox, oy


def to_svg(ops, width_units, height_units, px_per_inch, upi):
    scale = px_per_inch / upi
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
             % (round(width_units * scale), round(height_units * scale), width_units, height_units),
             '<rect width="100%" height="100%" fill="#ffffff"/>']
    parts += _op_elements(ops)
    parts.append("</svg>")
    return "\n".join(parts)


def _op_elements(ops):
    parts = []
    for op in ops:
        if op["kind"] == "text":
            parts.append('<path d="%s" fill="%s" fill-rule="nonzero"/>' % (_text_path(op), op["color"]))
            continue
        d = "".join(_d(sp) for sp in op["subpaths"])
        fill = op["fill"] or "none"
        st = op["stroke"]
        if st:
            w = st["width"]
            dash = ""
            if st["pattern"] in DASHES:
                dash = ' stroke-dasharray="%s"' % " ".join("%.2f" % (x * w) for x in DASHES[st["pattern"]])
            stroke = ' stroke="%s" stroke-width="%.2f" stroke-linejoin="round" stroke-linecap="round"%s' % (st["color"], w, dash)
        else:
            stroke = ""
        parts.append('<path d="%s" fill="%s" fill-rule="evenodd"%s/>' % (d, fill, stroke))
    return parts
