"""Probe: bold / italic / underline / lfWidth handling.   usage: python make_style_probe.py out.emf"""
import base64, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import emf as E
TEXT = "General Notes 5 3/8"
SIZE = 40
m = E.Emf(1400, 700, units_per_inch=300)
m.text_color("#000000")
m.text_align(E.TA_LEFT | E.TA_BASELINE)
y = 70
for label, kw in [("normal", {}), ("bold", {"bold": True}), ("italic", {"italic": True}), ("underline", {"underline": True}),
                  ("bold+italic", {"bold": True, "italic": True}), ("width12", {"width": 12}), ("width24", {"width": 24})]:
    m.font("Roboto", SIZE, **kw)
    m.text(50, y, TEXT)
    y += 90
data = m.build()
open(sys.argv[1], "wb").write(data)
print(len(data), "bytes")
print(base64.b64encode(data).decode())
