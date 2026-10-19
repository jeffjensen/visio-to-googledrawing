"""Calibration EMF: lines of text at the real operating scale, to measure the importer's text widths.
usage: venv python calib_text.py <out.emf> <out_meta.json>"""
import base64, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import emf as E
import uharfbuzz as hb
from fontTools.ttLib import TTFont

_F = os.path.join(os.path.dirname(HERE), "fonts")
ROB = {0: os.path.join(_F, "Roboto-Regular.ttf"), 1: os.path.join(_F, "Roboto-Bold.ttf"),
       2: os.path.join(_F, "Roboto-Italic.ttf"), 3: os.path.join(_F, "Roboto-BoldItalic.ttf")}
STRINGS = ["Fasten panels to these rails w/hardware", "General Notes", "5 3/8\" 'Frame' Side Panel", "Sample Drawing – Overview from above"]
EMS = [221, 295, 369, 443]                  # Roboto em' in units (= 0.885 x 6/8/10/12 pt at 3000 units/in)
W, H = 8000, 6600
m = E.Emf(W, H, units_per_inch=3000)
m.text_color("#000000")
m.text_align(E.TA_LEFT | E.TA_BASELINE)
meta = {"scale": min(800 * 11 / 12 / W, 600 * 11 / 12 / H), "lines": []}
fonts = {k: hb.Font(hb.Face(hb.Blob.from_file_path(p))) for k, p in ROB.items()}
upem = TTFont(ROB[0])["head"].unitsPerEm
def rob_width(style, s):
    buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties()
    hb.shape(fonts[style], buf, {"kern": True, "liga": False})
    return sum(p.x_advance for p in buf.glyph_positions) / upem
y = 150
# part A: default width, all sizes, regular
for em in EMS:
    for s in STRINGS[:2]:
        m.font("Roboto", em)
        m.text(100, y, s)
        meta["lines"].append({"s": s, "em": em, "style": 0, "lfw": 0, "y": y, "rob_w": rob_width(0, s) * em})
        y += em * 1.4
# part B: styles at em 295
for style, kw in [(1, {"bold": True}), (2, {"italic": True}), (3, {"bold": True, "italic": True})]:
    m.font("Roboto", 295, **kw)
    m.text(100, y, STRINGS[1])
    meta["lines"].append({"s": STRINGS[1], "em": 295, "style": style, "lfw": 0, "y": y, "rob_w": rob_width(style, STRINGS[1]) * 295})
    y += 295 * 1.4
# part C: lfWidth scaling at em 295: lfw = 0.6*em*f for f in 0.8, 0.9, 1.0, 1.1
for f in (0.8, 0.9, 1.1):
    lfw = round(0.6 * 295 * f)
    m.font("Roboto", 295, width=lfw)
    m.text(100, y, STRINGS[0])
    meta["lines"].append({"s": STRINGS[0], "em": 295, "style": 0, "lfw": lfw, "f": f, "y": y, "rob_w": rob_width(0, STRINGS[0]) * 295})
    y += 295 * 1.4
data = m.build()
open(sys.argv[1], "wb").write(data)
json.dump(meta, open(sys.argv[2], "w"))
print(len(data), "bytes; last y", y)
print(base64.b64encode(data).decode())
