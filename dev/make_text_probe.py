"""Probe: how does Google's WMF importer treat text, rotation, dash pens, etc.

usage: python -I make_text_probe.py <out.wmf>
"""
import base64
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wmf as W  # noqa: E402


def main(out):
    m = W.Wmf(400, 300, inch=96)
    m.pen("#000000", 1)
    m.brush(None)

    # 1. plain text with a tight reference rectangle (baseline at y=40, x from 20)
    m.font("Calibri", 14)
    m.text_color("#000000")
    m.text_align(W.TA_LEFT | W.TA_BASELINE)
    m.text(20, 40, "Plain Calibri 14")
    m.rectangle(20, 28, 112, 44)

    # 2. bigger text
    m.font("Calibri", 28)
    m.text(20, 90, "Bigger 28")
    m.rectangle(20, 66, 134, 98)

    # 3. rotated 90 degrees (escapement is tenths of a degree CCW)
    m.font("Calibri", 14, escapement=900)
    m.text_align(W.TA_LEFT | W.TA_BASELINE)
    m.text(360, 250, "Rotated 90 text")

    # 4. centered text over a vertical reference line at x=200
    m.font("Calibri", 14)
    m.text_align(W.TA_CENTER | W.TA_BASELINE)
    m.text(200, 130, "Centered")
    m.polyline([(200, 100), (200, 140)])

    # 5. dash / dot pens
    m.pen("#000000", 1, W.PS_DASH)
    m.polyline([(20, 170), (120, 170), (120, 200)])
    m.pen("#000000", 3, W.PS_DASH)
    m.polyline([(20, 215), (120, 215)])
    m.pen("#000000", 1, W.PS_DOT)
    m.polyline([(150, 170), (250, 170)])

    # 6. hollow polygon + ellipse
    m.pen("#000000", 1)
    m.polygon([(150, 200), (200, 250), (100, 250)])
    m.ellipse(260, 160, 340, 210)

    # 7. dense polyline (sine) and a filled polygon with no outline
    pts = [(20 + i * 3, 275 + 10 * math.sin(i / 4.0)) for i in range(0, 41)]
    m.polyline(pts)
    m.pen(None, 0)
    m.brush("#dde5cf")
    m.polygon([(230, 230), (300, 230), (300, 270), (230, 270)])

    data = m.build()
    with open(out, "wb") as f:
        f.write(data)
    print(len(data), "bytes")
    print(base64.b64encode(data).decode())


if __name__ == "__main__":
    main(sys.argv[1])
