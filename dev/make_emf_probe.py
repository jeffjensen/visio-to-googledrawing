"""Probe: does Drive convert a tiny EMF to a Drawing, and does it keep text/Beziers?

usage: python -I make_emf_probe.py <out.emf>
"""
import base64
import struct
import sys


class Emf:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.recs = []
        self.nobj = 1
        self._rec(18, struct.pack("<I", 1))  # SETBKMODE transparent

    def _rec(self, typ, body=b""):
        body += b"\0" * (-len(body) % 4)
        self.recs.append(struct.pack("<II", typ, 8 + len(body)) + body)

    def pen(self, color, width, style=0):
        h = self.nobj
        self.nobj += 1
        self._rec(38, struct.pack("<IIiiI", h, style, width, 0, color))
        self._rec(37, struct.pack("<I", h))

    def brush(self, color, hollow=False):
        h = self.nobj
        self.nobj += 1
        self._rec(39, struct.pack("<IIII", h, 1 if hollow else 0, color, 0))
        self._rec(37, struct.pack("<I", h))

    def font(self, face, height, esc=0):
        h = self.nobj
        self.nobj += 1
        name = face.encode("utf-16-le").ljust(64, b"\0")
        lf = struct.pack("<iiiii8B", -height, 0, esc, esc, 400, 0, 0, 0, 0, 0, 0, 4, 0x22) + name
        self._rec(82, struct.pack("<I", h) + lf)
        self._rec(37, struct.pack("<I", h))

    def text_color(self, c):
        self._rec(24, struct.pack("<I", c))

    def text_align(self, a):
        self._rec(22, struct.pack("<I", a))

    def _bounds(self, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return struct.pack("<iiii", min(xs), min(ys), max(xs), max(ys))

    def _poly16(self, typ, pts):
        body = self._bounds(pts) + struct.pack("<I", len(pts)) + b"".join(struct.pack("<hh", x, y) for x, y in pts)
        self._rec(typ, body)

    def polybezier(self, pts):
        self._poly16(85, pts)

    def polygon(self, pts):
        self._poly16(86, pts)

    def polyline(self, pts):
        self._poly16(87, pts)

    def rectangle(self, l, t, r, b):
        self._rec(43, struct.pack("<iiii", l, t, r, b))

    def text(self, x, y, s):
        u = s.encode("utf-16-le")
        n = len(s)
        off_string = 8 + 16 + 4 + 4 + 4 + 8 + 4 + 4 + 4 + 16 + 4  # header + fields up to string
        pad = u + b"\0" * (-len(u) % 4)
        dx = b"".join(struct.pack("<i", 8) for _ in range(n))
        body = (struct.pack("<iiii", x, y - 20, x + 8 * n, y + 6)          # rclBounds
                + struct.pack("<Iff", 1, 1.0, 1.0)                         # iGraphicsMode, exScale, eyScale
                + struct.pack("<iiIIIiiiiI", x, y, n, off_string, 0, 0, 0, 0, 0, off_string + len(pad))
                + pad + dx)
        self._rec(84, body)

    def build(self):
        self._rec(14, struct.pack("<III", 0, 16, 20))                      # EOF
        body = b"".join(self.recs)
        n_bytes = 88 + len(body)
        header = struct.pack(
            "<II4i4iIIIIHHIII2i2i",
            1, 88,
            0, 0, self.w - 1, self.h - 1,                                  # bounds (device)
            0, 0, int(self.w * 26.4583), int(self.h * 26.4583),            # frame, 0.01 mm
            0x464D4520, 0x10000, n_bytes, len(self.recs) + 1, self.nobj, 0,
            0, 0, 0,
            1024, 768, 270, 203,
        )
        return header + body


def main(out):
    m = Emf(400, 300)
    m.pen(0x000000, 1)
    m.brush(0, hollow=True)
    m.font("Calibri", 14)
    m.text_color(0)
    m.text_align(24)  # TA_BASELINE | TA_LEFT
    m.text(20, 40, "Hello EMF Calibri")
    m.rectangle(20, 28, 150, 44)
    m.font("Arial", 14, esc=900)
    m.text(360, 250, "Rot 90")
    m.pen(0x000000, 2)
    m.polybezier([(20, 120), (60, 60), (120, 60), (160, 120), (200, 180), (240, 180), (280, 120)])
    m.brush(0xCFE5DD)
    m.pen(0x333333, 1)
    m.polygon([(30, 200), (130, 200), (130, 260), (30, 260)])
    data = m.build()
    with open(out, "wb") as f:
        f.write(data)
    print(len(data), "bytes")
    print(base64.b64encode(data).decode())


if __name__ == "__main__":
    main(sys.argv[1])
