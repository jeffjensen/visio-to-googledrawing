"""Probe which face names Google's EMF importer maps to distinct fonts, and (optionally) whether Dx is honored.

usage: venv python make_font_probe.py <out.emf> <out_meta.json> [dx]
"""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import emf as E  # noqa: E402
from vsdxconv.text import get_face  # noqa: E402

FACES = ["Calibri", "Carlito", "Lato", "Arial", "Arimo", "Roboto", "Open Sans", "Segoe UI", "Noto Sans",
         "Source Sans Pro", "Cambria", "Times New Roman", "Verdana", "Courier New", "Comic Sans MS", "Trebuchet MS"]
TEXT = "Fasten panels to these rails w/hardware 5 3/8"
SIZE = 40
WITH_DX = len(sys.argv) > 3 and sys.argv[3] == "dx"

n_lines = len(FACES) + (3 if WITH_DX else 0)
W, H = 4000, 120 + 90 * n_lines
m = E.Emf(W, H, units_per_inch=300)
m.text_color("#000000")
m.text_align(E.TA_LEFT | E.TA_BASELINE)
shaped = get_face(0).shape(TEXT)
adv = [a * SIZE for _, a, _, _ in shaped]
meta = {"text": TEXT, "size": SIZE, "calibri_width": sum(adv), "lines": []}
y = 90
for name in FACES:
    m.font(name, SIZE)
    m.text(100, y, TEXT)
    meta["lines"].append({"face": name, "y": y, "dx": False})
    y += 90
if WITH_DX:
    m.font("Roboto", SIZE)
    m.text(100, y, TEXT, dx=adv)
    meta["lines"].append({"face": "Roboto+DxCalibri", "y": y, "dx": True})
    y += 90
    m.text(100, y, TEXT, dx=[a * 1.5 for a in adv])
    meta["lines"].append({"face": "Roboto+Dx1.5x", "y": y, "dx": True})
    y += 90
    m.font("Carlito", SIZE)
    m.text(100, y, TEXT, dx=adv)
    meta["lines"].append({"face": "Carlito+DxCalibri", "y": y, "dx": True})
    y += 90
data = m.build()
with open(sys.argv[1], "wb") as f:
    f.write(data)
with open(sys.argv[2], "w") as f:
    json.dump(meta, f)
print(len(data), "bytes; calibri width at size", SIZE, "=", round(meta["calibri_width"], 1))
print(base64.b64encode(data).decode())
