"""Shape transforms and geometry-section evaluation (cubic-Bezier output)."""
import math

from .model import fnum

IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mmul(m, n):
    """Matrix m applied after n.  Tuples are (a, b, c, d, e, f): x' = a x + c y + e, y' = b x + d y + f."""
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)


def mapply(m, p):
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def translate(tx, ty):
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def rotate(ang):
    c, s = math.cos(ang), math.sin(ang)
    return (c, s, -s, c, 0.0, 0.0)


def local_matrix(shape):
    """shape-local coordinates -> parent coordinates: Pin . Rot(Angle) . (-LocPin) . Flip."""
    w, h = shape.num("Width"), shape.num("Height")
    fx = shape.num("FlipX") != 0
    fy = shape.num("FlipY") != 0
    flip = (-1.0 if fx else 1.0, 0.0, 0.0, -1.0 if fy else 1.0, w if fx else 0.0, h if fy else 0.0)
    m = mmul(translate(-shape.num("LocPinX"), -shape.num("LocPinY")), flip)
    m = mmul(rotate(shape.num("Angle")), m)
    return mmul(translate(shape.num("PinX"), shape.num("PinY")), m)


class Subpath:
    """start point + segments; a segment is ('L', p) or ('C', c1, c2, p)."""
    __slots__ = ("start", "segs", "closed")

    def __init__(self, start):
        self.start = start
        self.segs = []
        self.closed = False

    def end(self):
        if not self.segs:
            return self.start
        s = self.segs[-1]
        return s[-1]

    def transformed(self, m):
        sp = Subpath(mapply(m, self.start))
        for s in self.segs:
            sp.segs.append((s[0],) + tuple(mapply(m, p) for p in s[1:]))
        sp.closed = self.closed
        return sp

    def shifted(self, dx, dy):
        return self.transformed((1.0, 0.0, 0.0, 1.0, dx, dy))


class GeoSection:
    __slots__ = ("ix", "no_fill", "no_line", "no_show", "subpaths")


def _arc_beziers(p0, p1, p2, angle, ratio):
    """Visio EllipticalArcTo: arc from p0 to p2 through control point p1, on the ellipse whose
    major axis lies at `angle` and whose major/minor axis ratio is `ratio`.  Returns cubic segments."""
    if abs(ratio) < 1e-9:
        return [("L", p2)]
    ca, sa = math.cos(angle), math.sin(angle)

    def to_v(p):  # rotate the axes onto x/y, then stretch so the ellipse becomes a circle
        return (ca * p[0] + sa * p[1], (-sa * p[0] + ca * p[1]) * ratio)

    def from_v(v):
        uy = v[1] / ratio
        return (ca * v[0] - sa * uy, sa * v[0] + ca * uy)

    (x1, y1), (x2, y2), (x3, y3) = to_v(p0), to_v(p1), to_v(p2)
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [("L", p2)]
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    cx = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    cy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    r = math.hypot(x1 - cx, y1 - cy)
    t0 = math.atan2(y1 - cy, x1 - cx)
    t2 = math.atan2(y3 - cy, x3 - cx)
    ccw = ((x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)) > 0
    sweep = (t2 - t0) % (2 * math.pi) if ccw else -((t0 - t2) % (2 * math.pi))
    n = max(1, int(math.ceil(abs(sweep) / (math.pi / 2) - 1e-9)))
    delta = sweep / n
    k = 4.0 / 3.0 * math.tan(delta / 4.0)
    segs = []
    for i in range(n):
        a = t0 + i * delta
        b = a + delta
        ca_, sa_, cb_, sb_ = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
        q0 = (cx + r * ca_, cy + r * sa_)
        q1 = (q0[0] - k * r * sa_, q0[1] + k * r * ca_)
        q3 = (cx + r * cb_, cy + r * sb_)
        q2 = (q3[0] + k * r * sb_, q3[1] - k * r * cb_)
        end = p2 if i == n - 1 else from_v(q3)
        segs.append(("C", from_v(q1), from_v(q2), end))
    return segs


def _ellipse_segments(cx, cy, ax, ay, bx, by):
    """closed ellipse: centre + two conjugate semi-diameters (ax,ay) and (bx,by) -> start and 4 Beziers."""
    k = 4.0 / 3.0 * math.tan(math.pi / 8.0)
    start = (cx + ax, cy + ay)
    pts = []
    for i in range(4):
        a = i * math.pi / 2
        b = a + math.pi / 2

        def pt(t, dt=0.0):
            # point on the ellipse and its tangent scaled by k
            return (cx + ax * math.cos(t) + bx * math.sin(t), cy + ay * math.cos(t) + by * math.sin(t))

        def tan(t):
            return (-ax * math.sin(t) + bx * math.cos(t), -ay * math.sin(t) + by * math.cos(t))
        p0, p3 = pt(a), pt(b)
        t0, t3 = tan(a), tan(b)
        c1 = (p0[0] + k * t0[0], p0[1] + k * t0[1])
        c2 = (p3[0] - k * t3[0], p3[1] - k * t3[1])
        pts.append(("C", c1, c2, p3 if i < 3 else start))
    return start, pts


def geometry(shape):
    """Evaluate the shape's Geometry sections in shape-local coordinates."""
    w, h = shape.num("Width"), shape.num("Height")
    secs = shape.merged_sections("Geometry")
    out = []
    for ix in sorted(secs, key=lambda k: int(k) if k is not None else 0):
        sec = secs[ix]
        gs = GeoSection()
        gs.ix = ix
        gs.no_fill = fnum(sec["cells"].get("NoFill"), 0) != 0
        gs.no_line = fnum(sec["cells"].get("NoLine"), 0) != 0
        gs.no_show = fnum(sec["cells"].get("NoShow"), 0) != 0
        gs.subpaths = []
        cur = None
        for key in sorted(sec["rows"], key=lambda k: int(k)):
            row = sec["rows"][key]
            t, c = row["t"], row["cells"]

            def g(n, d=0.0):
                return fnum(c.get(n), d)

            if t in ("MoveTo", "RelMoveTo"):
                x, y = (g("X"), g("Y")) if t == "MoveTo" else (g("X") * w, g("Y") * h)
                cur = Subpath((x, y))
                gs.subpaths.append(cur)
            elif t in ("LineTo", "RelLineTo"):
                x, y = (g("X"), g("Y")) if t == "LineTo" else (g("X") * w, g("Y") * h)
                cur.segs.append(("L", (x, y)))
            elif t == "EllipticalArcTo":
                p2 = (g("X"), g("Y"))
                cur.segs.extend(_arc_beziers(cur.end(), (g("A"), g("B")), p2, g("C"), g("D", 1.0)))
            elif t == "Ellipse":
                cx, cy = g("X"), g("Y")
                start, segs = _ellipse_segments(cx, cy, g("A") - cx, g("B") - cy, g("C") - cx, g("D") - cy)
                cur = Subpath(start)
                cur.segs = segs
                cur.closed = True
                gs.subpaths.append(cur)
            elif t in ("RelCubBezTo", "CubBezTo"):
                sx, sy = (w, h) if t == "RelCubBezTo" else (1.0, 1.0)
                cur.segs.append(("C", (g("A") * sx, g("B") * sy), (g("C") * sx, g("D") * sy), (g("X") * sx, g("Y") * sy)))
            else:
                raise NotImplementedError("geometry row type %r (shape %s)" % (t, shape.id))
        for sp in gs.subpaths:
            if not sp.closed and sp.segs:
                e, s = sp.end(), sp.start
                if abs(e[0] - s[0]) < 1e-6 and abs(e[1] - s[1]) < 1e-6:
                    sp.closed = True
        out.append(gs)
    return out
