"""Print each EMF as a label line plus ONE unbroken base64 line (for copying into create_file).

usage: python -I b64line.py <emf> [<emf> ...]
"""
import base64, os, sys

for p in sys.argv[1:]:
    b = base64.b64encode(open(p, "rb").read()).decode("ascii")
    print("### %s  (%d chars)" % (os.path.splitext(os.path.basename(p))[0], len(b)))
    print(b)
