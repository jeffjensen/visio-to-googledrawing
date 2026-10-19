"""Tiny parser for Google Drawings SVG exports: yields (attrs, [subpaths of points]) per <path>."""
import re
import xml.etree.ElementTree as ET

NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
TOK = re.compile(r"([a-zA-Z])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")

def parse_d(d, samples=8):
    """-> list of subpaths, each a list of (x, y) points (curves sampled)"""
    toks = [(m.group(1), m.group(2)) for m in TOK.finditer(d)]
    i, cmd, cur, start = 0, None, (0.0, 0.0), (0.0, 0.0)
    subs, pts = [], []
    def num():
        nonlocal i
        v = float(toks[i][1]); i += 1
        return v
    while i < len(toks):
        if toks[i][0]:
            cmd = toks[i][0]; i += 1
            if cmd in "zZ":
                if pts: subs.append(pts); pts = []
                cur = start
                continue
        rel = cmd.islower()
        c = cmd.lower()
        if c == "m":
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            if pts: subs.append(pts)
            pts = [cur]; start = cur
            cmd = "l" if rel else "L"
        elif c == "l":
            x, y = num(), num()
            cur = (cur[0] + x, cur[1] + y) if rel else (x, y)
            pts.append(cur)
        elif c == "c":
            v = [num() for _ in range(6)]
            if rel:
                p1 = (cur[0] + v[0], cur[1] + v[1]); p2 = (cur[0] + v[2], cur[1] + v[3]); p3 = (cur[0] + v[4], cur[1] + v[5])
            else:
                p1, p2, p3 = (v[0], v[1]), (v[2], v[3]), (v[4], v[5])
            for k in range(1, samples + 1):
                t = k / samples; u = 1 - t
                pts.append((u*u*u*cur[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                            u*u*u*cur[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))
            cur = p3
        elif c == "h":
            x = num(); cur = (cur[0] + x, cur[1]) if rel else (x, cur[1]); pts.append(cur)
        elif c == "v":
            y = num(); cur = (cur[0], cur[1] + y) if rel else (cur[0], y); pts.append(cur)
        else:
            raise ValueError("unsupported path command %r" % cmd)
    if pts: subs.append(pts)
    return subs

def read_paths(svg_path):
    root = ET.parse(svg_path).getroot()
    out = []
    for el in root.iter():
        if el.tag.endswith("}path") and el.get("d") and el.get("id") is None:
            out.append((dict(el.attrib), parse_d(el.get("d"))))
    return out
