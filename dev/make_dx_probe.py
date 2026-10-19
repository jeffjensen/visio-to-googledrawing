"""Minimal probe: does the importer honor the Dx array of EMR_EXTTEXTOUTW?   usage: python make_dx_probe.py out.emf"""
import base64, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import emf as E
TEXT = "Fasten rails 5 3/8"
SIZE = 40
m = E.Emf(1200, 400, units_per_inch=300)
m.text_color("#000000")
m.text_align(E.TA_LEFT | E.TA_BASELINE)
m.font("Roboto", SIZE)
m.text(50, 80, TEXT)                                    # natural
m.text(50, 160, TEXT, dx=[SIZE * 0.5] * len(TEXT))      # every char 0.5 em apart (narrow)
m.text(50, 240, TEXT, dx=[SIZE * 1.0] * len(TEXT))      # every char 1.0 em apart (wide)
data = m.build()
open(sys.argv[1], "wb").write(data)
print(len(data), "bytes")
print(base64.b64encode(data).decode())
