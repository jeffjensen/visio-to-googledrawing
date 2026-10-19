"""Inspect pieces of an extracted .vsdx.

usage:
  python -I dump_vsdx.py <extracted-dir> doc                      # faces, colors, stylesheets (summary)
  python -I dump_vsdx.py <extracted-dir> page <pageN> [ID ...]    # shape(s) by ID (or first 5 if none)
  python -I dump_vsdx.py <extracted-dir> master <masterN>         # master xml, compact
"""
import os
import sys
import xml.etree.ElementTree as ET

NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}
V = "{%s}" % NS["v"]


def compact(el, depth=0, out=None, maxdepth=9):
    out = out if out is not None else []
    tag = el.tag.replace(V, "")
    attrs = " ".join(f'{k}="{v}"' for k, v in el.attrib.items())
    text = (el.text or "").strip()
    pad = "  " * depth
    if tag == "Cell":
        f = el.get("F")
        s = f'{pad}{el.get("N")}={el.get("V")}' + (f"  [F={f}]" if f else "")
        extra = {k: v for k, v in el.attrib.items() if k not in ("N", "V", "F")}
        if extra:
            s += f"  {extra}"
        out.append(s)
        return out
    out.append(f"{pad}<{tag} {attrs}>" + (f" text={text!r}" if text else ""))
    if depth < maxdepth:
        for c in el:
            compact(c, depth + 1, out, maxdepth)
    return out


def find_shapes(root):
    for s in root.iter(V + "Shape"):
        yield s


def main():
    d, mode = sys.argv[1], sys.argv[2]
    if mode == "doc":
        r = ET.parse(os.path.join(d, "visio", "document.xml")).getroot()
        fn = r.find("v:FaceNames", NS)
        print("FACES:", [(f.get("ID"), f.get("Name")) for f in fn] if fn is not None else None)
        cl = r.find("v:Colors", NS)
        print("COLORS:", [(c.get("IX"), c.find("v:RGB", NS).get("V") if c.find("v:RGB", NS) is not None else c.get("RGB")) for c in cl] if cl is not None else None)
        ss = r.find("v:StyleSheets", NS)
        for st in ss:
            print(f"STYLE ID={st.get('ID')} Name={st.get('NameU')} LineStyle={st.get('LineStyle')} FillStyle={st.get('FillStyle')} TextStyle={st.get('TextStyle')}")
            if "-v" in sys.argv:
                print("\n".join(compact(st)))
        for tag in ("DocumentSettings", "DocumentSheet"):
            e = r.find("v:" + tag, NS)
            if e is not None:
                print(tag, "\n".join(compact(e, maxdepth=2))[:1500])
    elif mode == "page":
        r = ET.parse(os.path.join(d, "visio", "pages", sys.argv[3] + ".xml")).getroot()
        ids = set(sys.argv[4:])
        n = 0
        if not ids:
            ps = r.find("v:PageSheet", NS)
        for s in find_shapes(r):
            if ids and s.get("ID") not in ids:
                continue
            if not ids and n >= 5:
                break
            n += 1
            print("\n".join(compact(s, maxdepth=3 if not ids else 12)))
            print("-----")
    elif mode == "master":
        r = ET.parse(os.path.join(d, "visio", "masters", sys.argv[3] + ".xml")).getroot()
        print("\n".join(compact(r)))


if __name__ == "__main__":
    main()
