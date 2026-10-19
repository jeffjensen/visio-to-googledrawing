"""Draw operations -> EMF bytes.

Straight-line shapes use plain polygon / polyline records; anything with curves (and all text
outlines) uses path brackets so the Béziers survive intact in Google's importer.
"""
import emf as E

DASH = {1: E.PS_SOLID, 2: E.PS_DASH, 3: E.PS_DOT, 4: E.PS_DASHDOT, 5: E.PS_DASHDOTDOT}


def _has_curves(subs):
    return any(s[0] == "C" for sp in subs for s in sp.segs)


def _poly_points(sp, rng=None):
    pts = [sp.start]
    for s in sp.segs:
        pts.append(s[-1])
    if sp.closed and len(pts) > 1 and pts[-1] == pts[0]:
        pts.pop()                       # polygon records close themselves
    if rng is not None and sp.closed and len(pts) >= 3:
        k = rng.randrange(len(pts))     # same polygon, different start vertex / direction
        pts = pts[k:] + pts[:k]
        if rng.random() < 0.5:
            pts.reverse()
    return pts


def _path(m, subs, close_all):
    m.begin_path()
    for sp in subs:
        m.move_to(*sp.start)
        run_kind, run = None, []
        for s in sp.segs:
            kind = s[0]
            pts = list(s[1:])
            if kind != run_kind and run:
                (m.polyline_to if run_kind == "L" else m.polybezier_to)(run)
                run = []
            run_kind = kind
            run.extend(pts)
        if run:
            (m.polyline_to if run_kind == "L" else m.polybezier_to)(run)
        if sp.closed or close_all:
            m.close_figure()
    m.end_path()


def _set_stroke(m, stroke):
    if stroke is None:
        m.pen(None, 0)
    else:
        m.pen(stroke["color"], stroke["width"], DASH.get(stroke["pattern"], E.PS_DASH))


def _set_fill(m, fill):
    m.brush(fill)


def emit_text(m, op):
    m.font("Roboto", op["em"], escapement=op["angle10"], bold=bool(op["bits"] & 1), italic=bool(op["bits"] & 2),
           underline=bool(op["bits"] & 4), width=op["lfw"])
    m.text_color(op["color"])
    m.text_align(E.TA_LEFT | E.TA_BASELINE)
    m.text(op["x"], op["y"], op["text"])


def emit_op(m, op):
    if op["kind"] == "text":
        emit_text(m, op)
        return
    subs, fill, stroke = op["subpaths"], op["fill"], op["stroke"]
    if not subs:
        return
    all_closed = all(sp.closed for sp in subs)
    curves = _has_curves(subs)
    rng = m._rng if (m.uniq and (stroke is None or stroke["pattern"] == 1)) else None
    if not curves:
        if fill is not None and (stroke is None or all_closed):
            _set_stroke(m, stroke)
            _set_fill(m, fill)
            polys = [_poly_points(sp, rng) for sp in subs]
            if len(polys) == 1:
                m.polygon(polys[0])
            else:
                m.polypolygon(polys)
            return
        if fill is not None:                       # open shapes that are filled and stroked
            _set_stroke(m, None)
            _set_fill(m, fill)
            m.polypolygon([_poly_points(sp) for sp in subs])
        _set_stroke(m, stroke)
        _set_fill(m, None)
        for sp in subs:
            pts = _poly_points(sp, rng)
            (m.polygon if sp.closed else m.polyline)(pts)
        return
    # curves: path brackets
    if fill is not None and stroke is not None and all_closed:
        _set_stroke(m, stroke)
        _set_fill(m, fill)
        _path(m, subs, close_all=True)
        m.stroke_and_fill_path()
        return
    if fill is not None:
        _set_stroke(m, None)
        _set_fill(m, fill)
        _path(m, subs, close_all=True)
        m.fill_path()
    if stroke is not None:
        _set_stroke(m, stroke)
        _set_fill(m, None)
        _path(m, subs, close_all=False)
        m.stroke_path()


def emit_emf(ops, width_units, height_units, upi, uniq=False):
    m = E.Emf(width_units, height_units, upi, uniq=uniq)
    for op in ops:
        emit_op(m, op)
    return m.build()
