"""Minimal placeable-WMF writer (just what the Visio converter needs).

Coordinates are INT16 logical units with the origin at the top-left, y down.
Objects (pens/brushes/fonts) are created once and never deleted, so handles are
simply 0,1,2,... in creation order.
"""
import struct

# record functions
SETBKMODE = 0x0102
SETMAPMODE = 0x0103
SETPOLYFILLMODE = 0x0106
SETTEXTALIGN = 0x012E
SETTEXTCOLOR = 0x0209
SETWINDOWORG = 0x020B
SETWINDOWEXT = 0x020C
LINETO = 0x0213
MOVETO = 0x0214
SELECTOBJECT = 0x012D
CREATEPENINDIRECT = 0x02FA
CREATEFONTINDIRECT = 0x02FB
CREATEBRUSHINDIRECT = 0x02FC
POLYGON = 0x0324
POLYLINE = 0x0325
ELLIPSE = 0x0418
RECTANGLE = 0x041B
EXTTEXTOUT = 0x0A32
POLYPOLYGON = 0x0538
EOF = 0x0000

# text alignment flags
TA_LEFT, TA_RIGHT, TA_CENTER = 0, 2, 6
TA_TOP, TA_BOTTOM, TA_BASELINE = 0, 8, 24

PS_SOLID, PS_DASH, PS_DOT, PS_DASHDOT, PS_DASHDOTDOT, PS_NULL = 0, 1, 2, 3, 4, 5


def _w(*v):
    return struct.pack("<" + "H" * len(v), *[x & 0xFFFF for x in v])


def _i(*v):
    return struct.pack("<" + "h" * len(v), *v)


def _clamp(v):
    return max(-32768, min(32767, int(round(v))))


def _colorref(rgb):
    """rgb is '#rrggbb' or a (r,g,b) tuple -> little-endian COLORREF DWORD."""
    if isinstance(rgb, str):
        rgb = rgb.lstrip("#")
        r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
    else:
        r, g, b = rgb
    return struct.pack("<BBBB", r, g, b, 0)


class Wmf:
    def __init__(self, width, height, inch=96):
        self.width = _clamp(width)
        self.height = _clamp(height)
        self.inch = inch
        self._records = []
        self._objects = 0
        self._cache = {}
        self._current = {}
        self._rec(SETMAPMODE, _w(8))                      # MM_ANISOTROPIC
        self._rec(SETWINDOWORG, _i(0, 0))
        self._rec(SETWINDOWEXT, _i(self.height, self.width))
        self._rec(SETBKMODE, _w(1, 0))                    # TRANSPARENT
        self._rec(SETPOLYFILLMODE, _w(1, 0))              # ALTERNATE
        self._text_align = None

    # -- plumbing --------------------------------------------------------
    def _rec(self, func, *parts):
        body = b"".join(parts)
        if len(body) % 2:
            body += b"\0"
        size_words = (6 + len(body)) // 2
        self._records.append(struct.pack("<IH", size_words, func) + body)

    def _create(self, key, func, body):
        if key in self._cache:
            return self._cache[key]
        self._rec(func, body)
        h = self._objects
        self._objects += 1
        self._cache[key] = h
        return h

    def _select(self, kind, handle):
        if self._current.get(kind) != handle:
            self._rec(SELECTOBJECT, _w(handle))
            self._current[kind] = handle

    # -- state -----------------------------------------------------------
    def pen(self, color, width, style=PS_SOLID):
        """color None (or style PS_NULL) -> no outline."""
        if color is None:
            style, color = PS_NULL, "#000000"
        width = max(0, _clamp(width))
        key = ("pen", color, width, style)
        body = _w(style) + _i(width, 0) + _colorref(color)
        self._select("pen", self._create(key, CREATEPENINDIRECT, body))

    def brush(self, color):
        """color None -> hollow brush."""
        if color is None:
            key = ("brush", None)
            body = _w(1) + _colorref("#000000") + _w(0)
        else:
            key = ("brush", color)
            body = _w(0) + _colorref(color) + _w(0)
        self._select("brush", self._create(key, CREATEBRUSHINDIRECT, body))

    def font(self, face, height, escapement=0, bold=False, italic=False, underline=False):
        """height is the em height in logical units (passed negative = char height)."""
        h = -abs(_clamp(height))
        key = ("font", face, h, escapement, bold, italic, underline)
        name = face.encode("ascii", "replace")[:31].ljust(32, b"\0")
        body = (_i(h, 0, escapement, escapement, 700 if bold else 400)
                + bytes([1 if italic else 0, 1 if underline else 0, 0, 0, 0, 0, 4, 0x22]) + name)
        self._select("font", self._create(key, CREATEFONTINDIRECT, body))

    def text_color(self, color):
        self._rec(SETTEXTCOLOR, _colorref(color))

    def text_align(self, flags):
        if self._text_align != flags:
            self._rec(SETTEXTALIGN, _w(flags, 0))
            self._text_align = flags

    # -- drawing ---------------------------------------------------------
    def polygon(self, pts):
        pts = [(_clamp(x), _clamp(y)) for x, y in pts]
        self._rec(POLYGON, _i(len(pts)), b"".join(_i(x, y) for x, y in pts))

    def polyline(self, pts):
        pts = [(_clamp(x), _clamp(y)) for x, y in pts]
        self._rec(POLYLINE, _i(len(pts)), b"".join(_i(x, y) for x, y in pts))

    def polypolygon(self, polys):
        polys = [[(_clamp(x), _clamp(y)) for x, y in p] for p in polys if len(p) >= 3]
        if not polys:
            return
        counts = b"".join(_w(len(p)) for p in polys)
        pts = b"".join(_i(x, y) for p in polys for x, y in p)
        self._rec(POLYPOLYGON, _w(len(polys)), counts, pts)

    def rectangle(self, left, top, right, bottom):
        self._rec(RECTANGLE, _i(_clamp(bottom), _clamp(right), _clamp(top), _clamp(left)))

    def ellipse(self, left, top, right, bottom):
        self._rec(ELLIPSE, _i(_clamp(bottom), _clamp(right), _clamp(top), _clamp(left)))

    def text(self, x, y, s):
        data = s.encode("cp1252", "replace")
        self._rec(EXTTEXTOUT, _i(_clamp(y), _clamp(x), len(data)), _w(0), data)

    # -- output ----------------------------------------------------------
    def build(self):
        records = self._records + [struct.pack("<IH", 3, EOF)]
        body = b"".join(records)
        max_rec = max(struct.unpack_from("<I", r)[0] for r in records)
        total_words = (18 + len(body)) // 2
        header = struct.pack("<HHHIHIH", 1, 9, 0x0300, total_words, self._objects, max_rec, 0)
        head = struct.pack("<IHhhhhHI", 0x9AC6CDD7, 0, 0, 0, self.width, self.height, self.inch, 0)
        checksum = 0
        for (v,) in struct.iter_unpack("<H", head[:20]):
            checksum ^= v
        return head + struct.pack("<H", checksum) + header + body
