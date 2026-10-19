"""Survey the shape features used by the pages of an extracted .vsdx.

usage: python -I survey_vsdx.py <extracted-dir>
"""
import collections
import os
import sys
import xml.etree.ElementTree as ET

NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}
V = "{%s}" % NS["v"]


def load(path):
    return ET.parse(path).getroot()


def walk(shapes_el, depth=0):
    for s in shapes_el.findall("v:Shape", NS):
        yield s, depth
        sub = s.find("v:Shapes", NS)
        if sub is not None:
            yield from walk(sub, depth + 1)


def survey_page(path, masters):
    root = load(path)
    shapes_el = root.find("v:Shapes", NS)
    types = collections.Counter()
    rows = collections.Counter()
    sections = collections.Counter()
    cells = collections.Counter()
    masterrefs = collections.Counter()
    nshapes = 0
    texts = 0
    maxdepth = 0
    if shapes_el is not None:
        for s, d in walk(shapes_el):
            nshapes += 1
            maxdepth = max(maxdepth, d)
            types[s.get("Type") or "Shape"] += 1
            if s.get("Master"):
                masterrefs[masters.get(s.get("Master"), s.get("Master"))] += 1
            for c in s.findall("v:Cell", NS):
                cells[c.get("N")] += 1
            for sec in s.findall("v:Section", NS):
                sections[sec.get("N")] += 1
                if sec.get("N") == "Geometry":
                    for r in sec.findall("v:Row", NS):
                        rows[r.get("T")] += 1
            t = s.find("v:Text", NS)
            if t is not None and "".join(t.itertext()).strip():
                texts += 1
    conns = root.find("v:Connects", NS)
    nconn = len(conns) if conns is not None else 0
    return dict(nshapes=nshapes, maxdepth=maxdepth, types=types, rows=rows, sections=sections,
                cells=cells, masterrefs=masterrefs, texts=texts, nconn=nconn)


def main(d):
    mroot = load(os.path.join(d, "visio", "masters", "masters.xml"))
    rels = {}
    rp = os.path.join(d, "visio", "masters", "_rels", "masters.xml.rels")
    if os.path.exists(rp):
        for r in load(rp):
            rels[r.get("Id")] = r.get("Target")
    masters = {}
    for m in mroot.findall("v:Master", NS):
        masters[m.get("ID")] = f"{m.get('NameU') or m.get('Name')}#{m.get('ID')}"
    print("MASTERS:", ", ".join(masters.values()))
    pdir = os.path.join(d, "visio", "pages")
    proot = load(os.path.join(pdir, "pages.xml"))
    prels = {r.get("Id"): r.get("Target") for r in load(os.path.join(pdir, "_rels", "pages.xml.rels"))}
    for p in proot.findall("v:Page", NS):
        rid = p.find("v:Rel", NS).get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        fn = prels[rid]
        info = survey_page(os.path.join(pdir, fn), masters)
        print(f"\n--- page {p.get('Name')!r} ({fn}) shapes={info['nshapes']} depth={info['maxdepth']} "
              f"texts={info['texts']} connects={info['nconn']}")
        print("  types   :", dict(info["types"]))
        print("  masters :", dict(info["masterrefs"]))
        print("  rows    :", dict(info["rows"]))
        print("  sections:", dict(info["sections"]))
        interesting = ["Angle", "FlipX", "FlipY", "LinePattern", "LineWeight", "LineColor", "FillForegnd", "FillBkgnd",
                       "FillPattern", "Rounding", "BeginArrow", "EndArrow", "TxtAngle", "LocPinX", "LockAspect",
                       "ThemeIndex", "QuickStyleLineColor", "FillForegndTrans", "LineColorTrans", "ShapeSplit",
                       "ObjType", "ShapeShdwType", "LayerMember", "TheText", "HideText", "UseGroupRect"]
        print("  cells   :", {k: info["cells"][k] for k in interesting if info["cells"].get(k)})


if __name__ == "__main__":
    main(sys.argv[1])
