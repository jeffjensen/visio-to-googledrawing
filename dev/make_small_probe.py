"""Probe: does the importer render EMR_SMALLTEXTOUT?   usage: python make_small_probe.py out.emf"""
import base64, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE)]
import emf as E

m = E.Emf(3000, 900, units_per_inch=300)
m.text_color("#000000")
m.text_align(E.TA_LEFT | E.TA_BASELINE)
m.font("Roboto", 200)
m.text(100, 250, "Fasten rails 5 3/8 (EXTTEXTOUTW)")

def small(m, x, y, s, eight_bit):
    ETO_NO_RECT, ETO_SMALL_CHARS = 0x100, 0x200
    opts = ETO_NO_RECT | (ETO_SMALL_CHARS if eight_bit else 0)
    data = s.encode("latin-1") if eight_bit else s.encode("utf-16-le")
    body = struct.pack("<iiIIIff", x, y, len(s), opts, 1, 1.0, 1.0)[:0]
    body = struct.pack("<iiII", x, y, len(s), opts) + struct.pack("<Iff", 1, 1.0, 1.0) + data
    m._rec(108, body)

small(m, 100, 550, "Fasten rails 5 3/8 (SMALL utf16)", False)
small(m, 100, 800, "Fasten rails 5 3/8 (SMALL 8bit)", True)
data = m.build()
open(sys.argv[1], "wb").write(data)
print(len(data), "bytes")
print(base64.b64encode(data).decode())
