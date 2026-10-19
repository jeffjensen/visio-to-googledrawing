"""Probe 3: frame-vs-bounds sizing, path brackets w/ curves + hole, polypolygon hole, 32-bit pts.

usage: python -I make_emf_probe3.py <out.emf>
"""
import base64
import os
import sys

_D = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_D, os.path.dirname(_D)]
import emf as E  # noqa: E402


def main(out):
    m = E.Emf(1000, 750, units_per_inch=240)                # 1000x750 logical units = 4.17 x 3.125 in
    # 1. full-extent frame rectangle
    m.pen("#000000", 6)
    m.brush(None)
    m.rectangle(3, 3, 996, 746)

    # 2. path bracket: curvy outer shape with a curvy hole, fill+stroke
    m.pen("#000000", 4)
    m.brush("#dde5cf")
    m.begin_path()
    m.move_to(150, 300)
    m.polybezier_to([(150, 150), (250, 100), (350, 100), (450, 100), (550, 150), (550, 300),
                     (550, 450), (450, 500), (350, 500), (250, 500), (150, 450), (150, 300)])
    m.close_figure()
    m.move_to(250, 300)
    m.polybezier_to([(250, 230), (300, 200), (350, 200), (400, 200), (450, 230), (450, 300),
                     (450, 370), (400, 400), (350, 400), (300, 400), (250, 370), (250, 300)])
    m.close_figure()
    m.end_path()
    m.stroke_and_fill_path()

    # 3. polypolygon "O" (square ring) filled black, no outline
    m.pen(None, 0)
    m.brush("#000000")
    m.polypolygon([[(650, 100), (900, 100), (900, 350), (650, 350)],
                   [(720, 170), (830, 170), (830, 280), (720, 280)]])

    # 4. open bezier curve, stroked
    m.pen("#333333", 8)
    m.brush(None)
    m.polybezier([(650, 450), (700, 380), (780, 380), (830, 450), (880, 520), (900, 520), (930, 450)])

    # 5. ellipse fill + stroke
    m.pen("#000000", 3)
    m.brush("#ffd966")
    m.ellipse(650, 520, 900, 700)

    data = m.build()
    with open(out, "wb") as f:
        f.write(data)
    print(len(data), "bytes")
    print(base64.b64encode(data).decode())


if __name__ == "__main__":
    main(sys.argv[1])
