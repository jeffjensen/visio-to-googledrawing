"""Text: runs/paragraphs from the Visio <Text> element, wrapping layout, glyph outlines.

Glyph outlines come from the real TrueType font (Calibri), so the converted drawing matches the
Visio rendering; they are emitted as vector paths, not live text (Google's metafile importer turns
text into outlines anyway).

Units: font sizes, margins and line spacing are paper inches; the text block (TxtWidth etc.) is in
drawing inches, converted with `paper_ratio` (paper inches per drawing inch).
"""
import os

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

from .geom import Subpath
from .model import fnum

FONT_DIR = r"C:\Windows\Fonts"
FACE_FILES = {0: "calibri.ttf", 1: "calibrib.ttf", 2: "calibrii.ttf", 3: "calibriz.ttf"}
FEATURES = {"kern": True, "liga": False, "clig": False}

# calibration knobs (tuned against Visio's own PNG export)
ASCENT_PER_EM = 0.88     # first baseline below the top of a line box, in em (line box = |SpLine| x size)


class _Pen(BasePen):
    """Collects outline contours as Subpath objects in font units (y up), quadratics -> cubics."""

    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.contours = []
        self._cur = None

    def _moveTo(self, pt):
        self._cur = Subpath(pt)

    def _lineTo(self, pt):
        self._cur.segs.append(("L", pt))

    def _curveToOne(self, p1, p2, p3):
        self._cur.segs.append(("C", p1, p2, p3))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        c1 = (p0[0] + 2.0 / 3.0 * (p1[0] - p0[0]), p0[1] + 2.0 / 3.0 * (p1[1] - p0[1]))
        c2 = (p2[0] + 2.0 / 3.0 * (p1[0] - p2[0]), p2[1] + 2.0 / 3.0 * (p1[1] - p2[1]))
        self._cur.segs.append(("C", c1, c2, p2))

    def _closePath(self):
        self._cur.closed = True
        self.contours.append(self._cur)
        self._cur = None

    def _endPath(self):
        if self._cur is not None:
            self._cur.closed = True
            self.contours.append(self._cur)
            self._cur = None


class Face:
    def __init__(self, path):
        self.tt = TTFont(path)
        self.upem = float(self.tt["head"].unitsPerEm)
        self.glyphset = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.hb_font = hb.Font(hb.Face(hb.Blob.from_file_path(path)))
        post = self.tt["post"]
        self.underline_pos = post.underlinePosition / self.upem
        self.underline_thick = post.underlineThickness / self.upem
        self._outlines = {}

    def shape(self, text):
        """-> [(glyph_id, x_advance_em, x_offset_em, y_offset_em)] for the text."""
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.hb_font, buf, FEATURES)
        return [(i.codepoint, p.x_advance / self.upem, p.x_offset / self.upem, p.y_offset / self.upem)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def outline(self, gid):
        """Contours (Subpath list, em units, y up) of a glyph id."""
        c = self._outlines.get(gid)
        if c is None:
            pen = _Pen(self.glyphset)
            self.glyphset[self.order[gid]].draw(pen)
            u = self.upem
            c = []
            for sp in pen.contours:
                s2 = Subpath((sp.start[0] / u, sp.start[1] / u))
                s2.closed = True
                for seg in sp.segs:
                    s2.segs.append((seg[0],) + tuple((p[0] / u, p[1] / u) for p in seg[1:]))
                c.append(s2)
            self._outlines[gid] = c
        return c


_FACES = {}


def get_face(style_bits):
    key = (1 if style_bits & 1 else 0) | (2 if style_bits & 2 else 0)
    if key not in _FACES:
        _FACES[key] = Face(os.path.join(FONT_DIR, FACE_FILES[key]))
    return _FACES[key]


# --- Roboto: what Google's metafile importer substitutes for every font name -----------------------
ROBOTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")
ROBOTO_FILES = {0: "Roboto-Regular.ttf", 1: "Roboto-Bold.ttf", 2: "Roboto-Italic.ttf", 3: "Roboto-BoldItalic.ttf"}
# measured importer advance width / HarfBuzz advance width of the real Roboto face
ROBOTO_K = {0: 1.002, 1: 1.043, 2: 1.010, 3: 1.052}
# Roboto at this fraction of the Calibri em matches Calibri's cap height and x-height
HEIGHT_SCALE = 0.885
# the importer scales glyphs horizontally by lfWidth / (0.6 * em)
LFWIDTH_REF = 0.6
_ROBOTO = {}


def roboto_face(style_bits):
    key = (1 if style_bits & 1 else 0) | (2 if style_bits & 2 else 0)
    if key not in _ROBOTO:
        _ROBOTO[key] = Face(os.path.join(ROBOTO_DIR, ROBOTO_FILES[key]))
    return _ROBOTO[key], key


def importer_text_params(style_bits, size_paper_in, calibri_adv_paper_in, text, upi):
    """(em, lfWidth) in output units so that the importer's Roboto rendering of `text` is as tall as the
    Calibri text (cap/x-height) and exactly as wide as the Calibri layout."""
    em = max(1, int(round(HEIGHT_SCALE * size_paper_in * upi)))
    face, key = roboto_face(style_bits)
    adv_r = sum(a for _, a, _, _ in face.shape(text)) * em * ROBOTO_K[key]
    sx = (calibri_adv_paper_in * upi) / adv_r if adv_r > 0 else 1.0
    return em, max(1, int(round(sx * LFWIDTH_REF * em)))


class Fmt:
    """Resolved character formatting of one run."""
    __slots__ = ("size", "bits", "color", "caps", "pos", "scale", "letterspace")


class Run:
    __slots__ = ("text", "fmt")

    def __init__(self, text, fmt):
        self.text = text
        self.fmt = fmt


class Para:
    __slots__ = ("runs", "ix", "fmt0")

    def __init__(self):
        self.runs = []
        self.ix = None
        self.fmt0 = None


def char_fmt(shape, ix):
    ix = ix or "0"
    f = Fmt()
    f.size = fnum(shape.row_value("Character", ix, "Size"), 0.1666666666666667)
    f.bits = int(fnum(shape.row_value("Character", ix, "Style"), 0))
    f.color = shape.doc.color(shape.row_value("Character", ix, "Color"), "#000000")
    f.caps = int(fnum(shape.row_value("Character", ix, "Case"), 0))
    f.pos = int(fnum(shape.row_value("Character", ix, "Pos"), 0))
    f.scale = fnum(shape.row_value("Character", ix, "FontScale"), 1.0)
    f.letterspace = fnum(shape.row_value("Character", ix, "Letterspace"), 0.0)
    return f


def parse_paragraphs(shape):
    """Split the <Text> element into paragraphs of formatted runs ("\\n" ends a paragraph)."""
    te = shape.text_el
    if te is None:
        return []
    chunks = []                                  # (cp ix, pp ix, text)
    cp, pp = "0", "0"
    if te.text:
        chunks.append((cp, pp, te.text))
    for ch in te:
        tag = ch.tag.split("}")[-1]
        if tag == "cp":
            cp = ch.get("IX")
        elif tag == "pp":
            pp = ch.get("IX")
        elif tag == "fld" and ch.text:
            chunks.append((cp, pp, ch.text))
        if ch.tail:
            chunks.append((cp, pp, ch.tail))
    paras = []
    cur = Para()
    for cpx, ppx, s in chunks:
        parts = s.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, part in enumerate(parts):
            if i > 0:                            # newline terminates the current paragraph
                if cur.ix is None:
                    cur.ix, cur.fmt0 = ppx, char_fmt(shape, cpx)
                paras.append(cur)
                cur = Para()
            if part:
                if cur.ix is None:
                    cur.ix, cur.fmt0 = ppx, char_fmt(shape, cpx)
                cur.runs.append(Run(part, char_fmt(shape, cpx)))
    if cur.runs:
        paras.append(cur)
    return paras


# ---------------------------------------------------------------------------
class Token:
    __slots__ = ("text", "fmt", "adv", "space", "glyphs", "size")


def _tokens(para):
    """words and spaces, each carrying its run's formatting (advance in paper inches)"""
    toks = []
    for run in para.runs:
        text = run.text.upper() if run.fmt.caps == 1 else run.text
        i = 0
        while i < len(text):
            j = i
            is_sp = text[i] == " "
            while j < len(text) and (text[j] == " ") == is_sp:
                j += 1
            t = Token()
            t.text, t.fmt, t.space = text[i:j], run.fmt, is_sp
            t.size = run.fmt.size * (run.fmt.scale or 1.0)
            t.glyphs = get_face(run.fmt.bits).shape(t.text)
            t.adv = sum(a for _, a, _, _ in t.glyphs) * t.size + run.fmt.letterspace * len(t.text)
            toks.append(t)
            i = j
    return toks


class Line:
    __slots__ = ("toks", "width", "size", "para")


def wrap(para, avail):
    """greedy word wrap -> [Line]; widths in paper inches, trailing spaces trimmed"""
    toks = _tokens(para)
    lines = []
    cur, w = [], 0.0

    def flush():
        nonlocal cur, w
        while cur and cur[-1].space:
            w -= cur[-1].adv
            cur.pop()
        ln = Line()
        ln.toks, ln.width, ln.para = cur, max(w, 0.0), para
        ln.size = max([t.size for t in cur], default=(para.fmt0.size if para.fmt0 else 0.1666))
        lines.append(ln)
        cur, w = [], 0.0

    for t in toks:
        if t.space:
            if cur:
                cur.append(t)
                w += t.adv
            continue
        if cur and w + t.adv > avail + 1e-9:
            flush()
        cur.append(t)
        w += t.adv
    if cur or not lines:
        flush()
    return lines


class Block:
    """laid-out text: per-glyph placement in block coordinates (paper inches, origin top-left, y down)"""
    __slots__ = ("lines", "height")


def _margins(shape):
    return (fnum(shape.value("LeftMargin"), 0.0555555), fnum(shape.value("RightMargin"), 0.0555555),
            fnum(shape.value("TopMargin"), 0.0555555), fnum(shape.value("BottomMargin"), 0.0555555))


def natural_size(shape, paras):
    """Text block size (paper inches, margins included) that just fits the text without wrapping.
    This is what Visio uses for 1-D shapes (lines/connectors) that carry no explicit text-block cells."""
    ml, mr, mt, mb = _margins(shape)
    widest, total = 0.0, 0.0
    for p in paras:
        sp_line = fnum(shape.row_value("Paragraph", p.ix, "SpLine"), -1.2)
        sp_before = fnum(shape.row_value("Paragraph", p.ix, "SpBefore"), 0.0)
        sp_after = fnum(shape.row_value("Paragraph", p.ix, "SpAfter"), 0.0)
        lines = wrap(p, 1e9)
        for k, ln in enumerate(lines):
            widest = max(widest, ln.width)
            total += (ln.size * -sp_line if sp_line < 0 else sp_line)
            total += (sp_before if k == 0 else 0.0) + (sp_after if k == len(lines) - 1 else 0.0)
    return widest + ml + mr, total + mt + mb


def layout(shape, paras, block_w_paper, block_h_paper):
    """-> list of (baseline_y, x_start, Line) in block-local paper inches (y down from the block top)"""
    ml, mr, mt, mb = _margins(shape)
    valign = int(fnum(shape.value("VerticalAlign"), 1))
    avail = max(block_w_paper - ml - mr, 0.0)
    rows = []                                       # (line, align, pitch)
    total = 0.0
    for p in paras:
        align = int(fnum(shape.row_value("Paragraph", p.ix, "HorzAlign"), 0))
        sp_line = fnum(shape.row_value("Paragraph", p.ix, "SpLine"), -1.2)
        sp_before = fnum(shape.row_value("Paragraph", p.ix, "SpBefore"), 0.0)
        sp_after = fnum(shape.row_value("Paragraph", p.ix, "SpAfter"), 0.0)
        lines = wrap(p, avail)
        for k, ln in enumerate(lines):
            if sp_line < 0:
                pitch = ln.size * -sp_line
            else:
                pitch = sp_line
            extra_before = sp_before if k == 0 else 0.0
            extra_after = sp_after if k == len(lines) - 1 else 0.0
            rows.append((ln, align, pitch, extra_before, extra_after))
            total += pitch + extra_before + extra_after
    avail_h = block_h_paper - mt - mb
    top = mt + (avail_h - total) * (0.0 if valign == 0 else 0.5 if valign == 1 else 1.0)
    out = []
    y = top
    for ln, align, pitch, eb, ea in rows:
        y += eb
        baseline = y + ln.size * ASCENT_PER_EM
        if align == 1:
            x0 = ml + (avail - ln.width) / 2.0
        elif align == 2:
            x0 = ml + avail - ln.width
        else:
            x0 = ml
        out.append((baseline, x0, ln))
        y += pitch + ea
    return out
