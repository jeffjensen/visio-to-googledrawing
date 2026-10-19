"""Visio .vsdx loader: styles, masters, pages and shapes with inheritance.

A shape's effective cell value is resolved as
    shape's own cell -> master shape's cell -> style-sheet chain -> caller default.
Cached values (V) are used throughout: Visio writes the evaluated value for every
cell whose value differs from the master's cached value, so an absent cell equals
the master's cell and no formula evaluation is required.
"""
import os
import xml.etree.ElementTree as ET

NS = "http://schemas.microsoft.com/office/visio/2012/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def q(tag):
    return "{%s}%s" % (NS, tag)


# Visio's built-in palette (indices 0-23); 24+ come from the document's Colors table.
DEFAULT_PALETTE = [
    "#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF",
    "#800000", "#008000", "#000080", "#808000", "#800080", "#008080", "#C0C0C0", "#E6E6E6",
    "#CDCDCD", "#B3B3B3", "#9A9A9A", "#808080", "#666666", "#4D4D4D", "#333333", "#1A1A1A",
]

LINE_CELLS = {"LineWeight", "LineColor", "LinePattern", "Rounding", "BeginArrow", "EndArrow",
              "BeginArrowSize", "EndArrowSize", "LineCap", "LineColorTrans"}
FILL_CELLS = {"FillForegnd", "FillBkgnd", "FillPattern", "FillForegndTrans", "FillBkgndTrans",
              "ShdwForegnd", "ShdwPattern"}
# everything else that is style-controlled and text related falls under the text style
TEXT_CELLS = {"LeftMargin", "RightMargin", "TopMargin", "BottomMargin", "VerticalAlign",
              "TextBkgnd", "TextBkgndTrans", "TextDirection", "DefaultTabStop"}

# hard defaults used when the style chain only says "Themed" (the packages have no theme part;
# these are the values of the built-in "No Style" style sheet)
DEFAULTS = {
    "LineWeight": "0.01041666666666667", "LineColor": "0", "LinePattern": "1", "Rounding": "0",
    "BeginArrow": "0", "EndArrow": "0", "BeginArrowSize": "2", "EndArrowSize": "2", "LineCap": "0",
    "FillForegnd": "1", "FillBkgnd": "0", "FillPattern": "1",
    "LeftMargin": "0.05555555555555555", "RightMargin": "0.05555555555555555",
    "TopMargin": "0.05555555555555555", "BottomMargin": "0.05555555555555555",
    "VerticalAlign": "1", "TextBkgnd": "0",
}


class Row:
    __slots__ = ("t", "ix", "n", "cells", "deleted")


class Sec:
    __slots__ = ("name", "ix", "cells", "rows", "deleted")


def parse_cells(el):
    return {c.get("N"): c.get("V") for c in el.findall(q("Cell"))}


def parse_section(el):
    s = Sec()
    s.name, s.ix, s.deleted = el.get("N"), el.get("IX"), el.get("Del") == "1"
    s.cells = parse_cells(el)
    s.rows = []
    for r in el.findall(q("Row")):
        row = Row()
        row.t, row.ix, row.n, row.deleted = r.get("T"), r.get("IX"), r.get("N"), r.get("Del") == "1"
        row.cells = parse_cells(r)
        s.rows.append(row)
    return s


def fnum(v, default=None):
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class Style:
    def __init__(self, el):
        self.id = el.get("ID")
        self.name = el.get("NameU")
        self.parent = {"line": el.get("LineStyle"), "fill": el.get("FillStyle"), "text": el.get("TextStyle")}
        self.cells = parse_cells(el)
        self.sections = [parse_section(s) for s in el.findall(q("Section"))]


class Shape:
    def __init__(self, doc, el, master=None, master_shape=None, parent=None):
        self.doc = doc
        self.id = el.get("ID")
        self.type = el.get("Type") or "Shape"
        self.name = el.get("NameU") or el.get("Name") or ""
        self.parent = parent
        self.cells = parse_cells(el)
        self.sections = [parse_section(s) for s in el.findall(q("Section"))]
        self.style_ids = {"line": el.get("LineStyle"), "fill": el.get("FillStyle"), "text": el.get("TextStyle")}
        self.text_el = el.find(q("Text"))
        mid = el.get("Master")
        if mid is not None:
            master = doc.masters[mid]
            master_shape = master.root
        elif el.get("MasterShape") is not None and master is not None:
            master_shape = master.by_id.get(el.get("MasterShape"))
        self.master = master
        self.master_shape = master_shape
        self.children = []
        sub = el.find(q("Shapes"))
        if sub is not None:
            for ch in sub.findall(q("Shape")):
                self.children.append(Shape(doc, ch, master=master, parent=self))

    # -- raw lookups ------------------------------------------------------
    def cell(self, name):
        v = self.cells.get(name)
        if v is not None:
            return v
        return self.master_shape.cell(name) if self.master_shape is not None else None

    def style_id(self, kind):
        v = self.style_ids.get(kind)
        if v is None and self.master_shape is not None:
            return self.master_shape.style_id(kind)
        return v if v is not None else self.doc.default_style[kind]

    def kind_of(self, name):
        if name in LINE_CELLS:
            return "line"
        if name in FILL_CELLS:
            return "fill"
        return "text"

    def value(self, name):
        """Effective cell value string (style chain and defaults applied) or None."""
        v = self.cell(name)
        if v is not None and v != "Themed":
            return v
        v = self.doc.style_cell(self.style_id(self.kind_of(name)), self.kind_of(name), name)
        if v is not None and v != "Themed":
            return v
        return DEFAULTS.get(name)

    def num(self, name, default=0.0):
        return fnum(self.cell(name), default)

    def merged_sections(self, name):
        """{ix: {'cells': {...}, 'rows': {key: {'t':..,'cells':{..}}}}} master first, shape overrides."""
        result = {}
        chain = ([self.master_shape] if self.master_shape is not None else []) + [self]
        for sh in chain:
            for sec in sh.sections:
                if sec.name != name:
                    continue
                if sec.deleted:
                    result.pop(sec.ix, None)
                    continue
                entry = result.setdefault(sec.ix, {"cells": {}, "rows": {}})
                entry["cells"].update(sec.cells)
                for row in sec.rows:
                    key = row.ix if row.ix is not None else row.n
                    if row.deleted:
                        entry["rows"].pop(key, None)
                        continue
                    e = entry["rows"].setdefault(key, {"t": row.t, "cells": {}})
                    if row.t:
                        e["t"] = row.t
                    e["cells"].update(row.cells)
        return result

    def row_value(self, section, ix, name):
        """Cell of Character/Paragraph row `ix`: shape -> master -> text style (row 0)."""
        ms = self.merged_sections(section)
        sec = ms.get(None) or next(iter(ms.values()), None)
        if sec is not None:
            for key in (ix, "0"):
                row = sec["rows"].get(key)
                if row is not None and row["cells"].get(name) not in (None, "Themed"):
                    return row["cells"][name]
        v = self.doc.style_row_cell(self.style_id("text"), section, name)
        return v if v not in (None, "Themed") else None


class Master:
    def __init__(self, doc, el_root, name):
        self.name = name
        self.by_id = {}
        self.top = []
        shapes = el_root.find(q("Shapes"))
        if shapes is not None:
            for sh_el in shapes.findall(q("Shape")):
                s = Shape(doc, sh_el)
                self.top.append(s)
        self._index(self.top)
        self.root = self.top[0] if self.top else None

    def _index(self, shapes):
        for s in shapes:
            self.by_id[s.id] = s
            self._index(s.children)


class Page:
    def __init__(self, name, cells, shapes):
        self.name = name
        self.cells = cells
        self.shapes = shapes

    @property
    def width(self):
        return fnum(self.cells.get("PageWidth"), 8.5)

    @property
    def height(self):
        return fnum(self.cells.get("PageHeight"), 11.0)

    @property
    def paper_ratio(self):
        """paper inches per drawing inch"""
        return fnum(self.cells.get("PageScale"), 1.0) / fnum(self.cells.get("DrawingScale"), 1.0)


class Doc:
    def __init__(self, root):
        self.root = root
        self.styles = {}
        self.palette = {i: c for i, c in enumerate(DEFAULT_PALETTE)}
        self.masters = {}
        self.pages = []
        self.default_style = {"line": "3", "fill": "3", "text": "3"}
        self._load_document()
        self._load_masters()
        self._load_pages()

    def _parse(self, *parts):
        return ET.parse(os.path.join(self.root, *parts)).getroot()

    def _load_document(self):
        r = self._parse("visio", "document.xml")
        for st in r.find(q("StyleSheets")):
            self.styles[st.get("ID")] = Style(st)
        cl = r.find(q("Colors"))
        if cl is not None:
            for c in cl:
                rgb = c.find(q("RGB"))
                val = rgb.get("V") if rgb is not None else c.get("RGB")
                if val:
                    self.palette[int(c.get("IX"))] = val.upper()
        ds = r.find(q("DocumentSettings"))
        if ds is not None:
            self.default_style = {"line": ds.get("DefaultLineStyle", "3"), "fill": ds.get("DefaultFillStyle", "3"),
                                  "text": ds.get("DefaultTextStyle", "3")}

    @staticmethod
    def _rels(path):
        out = {}
        if os.path.exists(path):
            for r in ET.parse(path).getroot():
                out[r.get("Id")] = r.get("Target")
        return out

    def _load_masters(self):
        mp = os.path.join(self.root, "visio", "masters")
        if not os.path.exists(os.path.join(mp, "masters.xml")):
            return
        rels = self._rels(os.path.join(mp, "_rels", "masters.xml.rels"))
        for m in self._parse("visio", "masters", "masters.xml").findall(q("Master")):
            target = rels[m.find(q("Rel")).get("{%s}id" % RNS)]
            self.masters[m.get("ID")] = Master(self, self._parse("visio", "masters", target), m.get("NameU"))

    def _load_pages(self):
        pp = os.path.join(self.root, "visio", "pages")
        rels = self._rels(os.path.join(pp, "_rels", "pages.xml.rels"))
        for p in self._parse("visio", "pages", "pages.xml").findall(q("Page")):
            target = rels[p.find(q("Rel")).get("{%s}id" % RNS)]
            content = self._parse("visio", "pages", target)
            ps = p.find(q("PageSheet"))
            cells = parse_cells(ps) if ps is not None else {}
            shapes_el = content.find(q("Shapes"))
            shapes = [Shape(self, s) for s in shapes_el.findall(q("Shape"))] if shapes_el is not None else []
            self.pages.append(Page(p.get("Name"), cells, shapes))

    # -- styles -----------------------------------------------------------
    def style_cell(self, sid, kind, name):
        seen = set()
        while sid is not None and sid not in seen:
            seen.add(sid)
            st = self.styles.get(sid)
            if st is None:
                return None
            v = st.cells.get(name)
            if v is not None and v != "Themed":
                return v
            sid = st.parent[kind]
        return None

    def style_row_cell(self, sid, section, name):
        seen = set()
        while sid is not None and sid not in seen:
            seen.add(sid)
            st = self.styles.get(sid)
            if st is None:
                return None
            for sec in st.sections:
                if sec.name == section:
                    for row in sec.rows:
                        v = row.cells.get(name)
                        if v is not None and v != "Themed":
                            return v
            sid = st.parent["text"]
        return None

    def color(self, v, default="#000000"):
        if v is None or v == "Themed":
            return default
        if isinstance(v, str) and v.startswith("#"):
            return v.upper()
        try:
            return self.palette.get(int(float(v)), default)
        except (TypeError, ValueError):
            return default
