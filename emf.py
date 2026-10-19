"""Minimal EMF writer (the records the Visio converter needs).

Logical units are whatever the caller chooses; MM_TEXT mapping, origin top-left, y down.
The reference device is declared with `units_per_inch` resolution so the header's bounds, frame and
device size are mutually consistent.  Objects (pens/brushes/fonts) are created on demand and cached;
nothing is deleted.

The files are transmitted as hand-copied base64, so they are kept compact: point records use the
16-bit variants whenever every point fits, and fields that readers ignore are filled with non-zero
data rather than long zero runs (which are easy to miscopy).
"""
import random
import struct

R_POLYBEZIER = 2
R_POLYGON = 3
R_POLYLINE = 4
R_POLYBEZIERTO = 5
R_POLYLINETO = 6
R_POLYPOLYGON = 8
R_EOF = 14
R_SETBKMODE = 18
R_SETPOLYFILLMODE = 19
R_SETTEXTALIGN = 22
R_SETTEXTCOLOR = 24
R_MOVETOEX = 27
R_SELECTOBJECT = 37
R_CREATEPEN = 38
R_CREATEBRUSHINDIRECT = 39
R_ELLIPSE = 42
R_RECTANGLE = 43
R_BEGINPATH = 59
R_ENDPATH = 60
R_CLOSEFIGURE = 61
R_FILLPATH = 62
R_STROKEANDFILLPATH = 63
R_STROKEPATH = 64
R_EXTCREATEFONTINDIRECTW = 82
R_EXTTEXTOUTW = 84
R_POLYBEZIER16 = 85
R_POLYGON16 = 86
R_POLYLINE16 = 87
R_POLYBEZIERTO16 = 88
R_POLYLINETO16 = 89
R_POLYPOLYGON16 = 91

TA_LEFT, TA_RIGHT, TA_CENTER = 0, 2, 6
TA_TOP, TA_BOTTOM, TA_BASELINE = 0, 8, 24

PS_SOLID, PS_DASH, PS_DOT, PS_DASHDOT, PS_DASHDOTDOT, PS_NULL = 0, 1, 2, 3, 4, 5

# bytes after the terminating NUL of a face name are ignored by readers; fill them with non-zero text
_FACE_FILLER = "zQvKmJwPdLhXcRtBnYfGsAeUo"


def _colorref(c):
    if isinstance(c, str):
        c = c.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    else:
        r, g, b = c
    return r | (g << 8) | (b << 16)


def _i(v):
    return int(round(v))


def _fits16(pts):
    return all(-32768 <= _i(x) <= 32767 and -32768 <= _i(y) <= 32767 for x, y in pts)


class Emf:
    def __init__(self, width, height, units_per_inch, uniq=False):
        self.w, self.h = _i(width), _i(height)
        self.uniq = uniq
        self._rng = random.Random(1)
        self.upi = units_per_inch
        self.frame = (_i(self.w / units_per_inch * 2540), _i(self.h / units_per_inch * 2540))
        self.dev_mm = (_i(self.w / units_per_inch * 25.4), _i(self.h / units_per_inch * 25.4))
        self._recs = []
        self._nobj = 1                      # handle 0 is reserved
        self._cache = {}
        self._cur = {}
        self._rec(R_SETBKMODE, struct.pack("<I", 1))        # TRANSPARENT
        self._rec(R_SETPOLYFILLMODE, struct.pack("<I", 1))  # ALTERNATE (even-odd)

    # -- plumbing --------------------------------------------------------
    def _rec(self, typ, body=b""):
        body += b"\0" * (-len(body) % 4)
        self._recs.append(struct.pack("<II", typ, 8 + len(body)) + body)

    def _select(self, kind, h):
        if self._cur.get(kind) != h:
            self._rec(R_SELECTOBJECT, struct.pack("<I", h))
            self._cur[kind] = h

    def _bounds(self, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pad = [self._rng.randrange(1, 8) for _ in range(4)] if self.uniq else [0, 0, 0, 0]
        return struct.pack("<iiii", _i(min(xs)) - pad[0], _i(min(ys)) - pad[1], _i(max(xs)) + pad[2], _i(max(ys)) + pad[3])

    @staticmethod
    def _pts32(pts):
        return b"".join(struct.pack("<ii", _i(x), _i(y)) for x, y in pts)

    @staticmethod
    def _pts16(pts):
        return b"".join(struct.pack("<hh", _i(x), _i(y)) for x, y in pts)

    def _poly(self, rec32, rec16, pts):
        if _fits16(pts):
            self._rec(rec16, self._bounds(pts) + struct.pack("<I", len(pts)) + self._pts16(pts))
        else:
            self._rec(rec32, self._bounds(pts) + struct.pack("<I", len(pts)) + self._pts32(pts))

    # -- state -----------------------------------------------------------
    def pen(self, color, width, style=PS_SOLID):
        if color is None:
            style, color = PS_NULL, "#000000"
        width = max(0, _i(width))
        key = ("pen", _colorref(color), width, style)
        if key not in self._cache:
            h = self._nobj
            self._nobj += 1
            self._rec(R_CREATEPEN, struct.pack("<IIiiI", h, style, width, 0, _colorref(color)))
            self._cache[key] = h
        self._select("pen", self._cache[key])

    def brush(self, color):
        key = ("brush", None if color is None else _colorref(color))
        if key not in self._cache:
            h = self._nobj
            self._nobj += 1
            if color is None:
                self._rec(R_CREATEBRUSHINDIRECT, struct.pack("<IIII", h, 1, 0, 0))
            else:
                self._rec(R_CREATEBRUSHINDIRECT, struct.pack("<IIII", h, 0, _colorref(color), 0))
            self._cache[key] = h
        self._select("brush", self._cache[key])

    def fill_mode(self, winding=False):
        self._rec(R_SETPOLYFILLMODE, struct.pack("<I", 2 if winding else 1))

    def font(self, face, height, escapement=0, bold=False, italic=False, underline=False, width=0):
        """em height in logical units; escapement in tenths of a degree (counter-clockwise)."""
        key = ("font", face, _i(height), _i(escapement), bold, italic, underline, _i(width))
        if key not in self._cache:
            h = self._nobj
            self._nobj += 1
            text = (face[:6] + chr(0) + _FACE_FILLER)[:31]
            name = text.encode("utf-16-le").ljust(64, bytes([0]))
            lf = struct.pack("<iiiii8B", -abs(_i(height)), _i(width), _i(escapement), _i(escapement),
                             700 if bold else 400, 1 if italic else 0, 1 if underline else 0, 0, 0, 0, 0, 4, 0x22) + name
            self._rec(R_EXTCREATEFONTINDIRECTW, struct.pack("<I", h) + lf)
            self._cache[key] = h
        self._select("font", self._cache[key])

    def text_color(self, color):
        c = _colorref(color)
        if self._cur.get("tcolor") != c:
            self._rec(R_SETTEXTCOLOR, struct.pack("<I", c))
            self._cur["tcolor"] = c

    def text_align(self, flags):
        if self._cur.get("align") != flags:
            self._rec(R_SETTEXTALIGN, struct.pack("<I", flags))
            self._cur["align"] = flags

    def text(self, x, y, s):
        """EMR_EXTTEXTOUTW at reference point (x, y) per the current text alignment."""
        u = s.encode("utf-16-le")
        n = len(s)
        off_string = 76
        pad = u + bytes(-len(u) % 4)
        bx0, by0, bx1, by1 = _i(x) - 50, _i(y) - 400, _i(x) + 50 * n, _i(y) + 200
        body = (struct.pack("<iiii", bx0, by0, bx1, by1)                       # rclBounds
                + struct.pack("<Iff", 1, 1.0, 1.0)                              # iGraphicsMode, exScale, eyScale
                + struct.pack("<iiIII", _i(x), _i(y), n, off_string, 0)         # reference, nChars, offString, options
                + struct.pack("<iiii", bx0, by0, bx1, by1)                      # rcl (ignored without clip/opaque flags)
                + struct.pack("<I", 0)                                          # offDx: none
                + pad)
        self._rec(R_EXTTEXTOUTW, body)

    # -- drawing ---------------------------------------------------------
    def polygon(self, pts):
        self._poly(R_POLYGON, R_POLYGON16, pts)

    def polyline(self, pts):
        self._poly(R_POLYLINE, R_POLYLINE16, pts)

    def polybezier(self, pts):
        """pts = start, then triples (c1, c2, end)."""
        self._poly(R_POLYBEZIER, R_POLYBEZIER16, pts)

    def polypolygon(self, polys):
        polys = [p for p in polys if len(p) >= 3]
        if not polys:
            return
        allpts = [pt for p in polys for pt in p]
        wide = not _fits16(allpts)
        body = (self._bounds(allpts) + struct.pack("<II", len(polys), len(allpts))
                + b"".join(struct.pack("<I", len(p)) for p in polys)
                + (self._pts32(allpts) if wide else self._pts16(allpts)))
        self._rec(R_POLYPOLYGON if wide else R_POLYPOLYGON16, body)

    def rectangle(self, l, t, r, b):
        self._rec(R_RECTANGLE, struct.pack("<iiii", _i(l), _i(t), _i(r), _i(b)))

    def ellipse(self, l, t, r, b):
        self._rec(R_ELLIPSE, struct.pack("<iiii", _i(l), _i(t), _i(r), _i(b)))

    # path brackets
    def begin_path(self):
        self._rec(R_BEGINPATH)

    def end_path(self):
        self._rec(R_ENDPATH)

    def close_figure(self):
        self._rec(R_CLOSEFIGURE)

    def move_to(self, x, y):
        self._rec(R_MOVETOEX, struct.pack("<ii", _i(x), _i(y)))

    def polybezier_to(self, pts):
        self._poly(R_POLYBEZIERTO, R_POLYBEZIERTO16, pts)

    def polyline_to(self, pts):
        self._poly(R_POLYLINETO, R_POLYLINETO16, pts)

    def fill_path(self):
        self._rec(R_FILLPATH, struct.pack("<iiii", 0, 0, self.w, self.h))

    def stroke_and_fill_path(self):
        self._rec(R_STROKEANDFILLPATH, struct.pack("<iiii", 0, 0, self.w, self.h))

    def stroke_path(self):
        self._rec(R_STROKEPATH, struct.pack("<iiii", 0, 0, self.w, self.h))

    # -- output ----------------------------------------------------------
    def build(self):
        self._rec(R_EOF, struct.pack("<III", 0, 16, 20))
        body = b"".join(self._recs)
        header = struct.pack(
            "<II4i4iIIIIHHIII2i2i",
            1, 88,
            0, 0, self.w - 1, self.h - 1,
            0, 0, self.frame[0], self.frame[1],
            0x464D4520, 0x10000, 88 + len(body), len(self._recs) + 1, self._nobj, 0,
            0, 0, 0,
            self.w, self.h, self.dev_mm[0], self.dev_mm[1],
        )
        return header + body
