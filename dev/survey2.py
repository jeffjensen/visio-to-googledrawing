"""Distinct values of the rendering-relevant cells across all shapes of all pages (+ masters).

usage: python -I survey2.py <extracted-dir> [<extracted-dir> ...]
"""
import collections
import os
import sys
import xml.etree.ElementTree as ET

NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}
CELLS = ["LinePattern", "FillPattern", "BeginArrow", "EndArrow", "BeginArrowSize", "EndArrowSize", "Rounding",
         "LineCap", "LineColor", "FillForegnd", "FillBkgnd", "LineWeight", "TextBkgnd", "VerticalAlign",
         "LineColorTrans", "FillForegndTrans", "ShdwPattern", "ShapeShdwShow", "FillGradientEnabled",
         "LineGradientEnabled", "HideText", "TxtAngle", "LockWidth"]
SECT_CELLS = ["NoFill", "NoLine", "NoShow"]


def walk(el):
    for s in el.findall("v:Shape", NS):
        yield s
        sub = s.find("v:Shapes", NS)
        if sub is not None:
            yield from walk(sub)


def scan(path, where, acc):
    r = ET.parse(path).getroot()
    shapes_el = r.find("v:Shapes", NS)
    if shapes_el is None:
        return
    for s in walk(shapes_el):
        for c in s.findall("v:Cell", NS):
            if c.get("N") in CELLS:
                acc[c.get("N")][c.get("V")] += 1
        for sec in s.findall("v:Section", NS):
            if sec.get("N") == "Geometry":
                for c in sec.findall("v:Cell", NS):
                    if c.get("N") in SECT_CELLS:
                        acc["Geom." + c.get("N")][c.get("V")] += 1
            if sec.get("N") == "Character":
                for row in sec.findall("v:Row", NS):
                    for c in row.findall("v:Cell", NS):
                        acc["Char." + c.get("N")][c.get("V")] += 1
            if sec.get("N") == "Paragraph":
                for row in sec.findall("v:Row", NS):
                    for c in row.findall("v:Cell", NS):
                        acc["Para." + c.get("N")][c.get("V")] += 1
        if s.find("v:Fld", NS) is not None or any("fld" in (x.tag or "") for x in s.iter()):
            acc["_has_fld"][where] += 1
        for sec in s.findall("v:Section", NS):
            acc["_sections"][sec.get("N")] += 1
        if s.get("Type") not in (None, "Shape", "Group"):
            acc["_type"][s.get("Type")] += 1
        if s.find("v:Data", NS) is not None or s.find("v:ForeignData", NS) is not None:
            acc["_foreign"][where] += 1


def main(dirs):
    acc = collections.defaultdict(collections.Counter)
    for d in dirs:
        base = os.path.basename(d)
        for sub in ("pages", "masters"):
            p = os.path.join(d, "visio", sub)
            for fn in sorted(os.listdir(p)):
                if fn.endswith(".xml") and fn not in ("pages.xml", "masters.xml"):
                    scan(os.path.join(p, fn), f"{base}/{sub}/{fn}", acc)
        # page-level layer info
        pg = os.path.join(d, "visio", "pages")
        for fn in sorted(os.listdir(pg)):
            if fn.startswith("pages"):
                r = ET.parse(os.path.join(pg, fn)).getroot()
                for page in r.findall("v:Page", NS):
                    ps = page.find("v:PageSheet", NS)
                    for sec in ps.findall("v:Section", NS) if ps is not None else []:
                        if sec.get("N") == "Layer":
                            for row in sec.findall("v:Row", NS):
                                acc["_layers:" + base + ":" + page.get("Name")][
                                    str({c.get("N"): c.get("V") for c in row.findall("v:Cell", NS) if c.get("N") in ("Name", "Visible", "Print", "Active", "Lock", "Color")})] += 1
    for k in sorted(acc):
        vals = ", ".join(f"{v!r}x{n}" for v, n in acc[k].most_common(14))
        print(f"{k:34} {vals}")


if __name__ == "__main__":
    main(sys.argv[1:])
