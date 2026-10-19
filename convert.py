"""Convert the pages of a Visio .vsdx file to EMF files (one per page).

usage: .venv\\Scripts\\python.exe -I convert.py <file.vsdx | extracted-dir> [<out-dir>] [--upi N|0] [--page NAME ...]
                                              [--prefix P] [--crop IN] [--svg DPI] [--text-mode importer|outline] [--uniq]

SRC is a .vsdx file (unzipped to a temporary directory first) or a directory that already holds an
unzipped .vsdx (see extract_vsdx.py).  OUT defaults to ./<name>-emf.  Each page becomes
"<prefix> - <page>.emf"; the prefix defaults to the .vsdx file's name (none for a directory).
A page that uses a Visio feature the converter does not know is skipped with a message on stderr, and
the exit status is then 1.

--upi 0 (default) picks the largest resolution (<= 3000 units/inch) at which every coordinate of the
cropped page still fits in 16 bits, which keeps the EMF compact.
"""
import argparse
import os
import re
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from extract_vsdx import extract        # noqa: E402
from vsdxconv.model import Doc          # noqa: E402
from vsdxconv.render import crop_to_content, render_page  # noqa: E402
from vsdxconv.emit import emit_emf       # noqa: E402
from vsdxconv.svgprev import to_svg     # noqa: E402

MAX_UPI = 3000
INT16_SAFE = 32000


def safe(name):
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip()


def build(doc, page, upi, crop, text_mode):
    ctx = render_page(doc, page, upi, text_mode)
    if crop is not None:
        w, h = crop_to_content(ctx.ops, crop * upi)
    else:
        w, h = page.width * ctx.k, page.height * ctx.k
    return ctx, round(w), round(h)


def open_doc(src, tmp):
    """Doc for `src`: a directory holding an unzipped .vsdx, or a .vsdx file (unzipped under `tmp`)."""
    root = src
    if os.path.isfile(src):
        if not zipfile.is_zipfile(src):
            sys.exit("%s is not a .vsdx file (an OPC zip); the old binary .vsd format is not supported" % src)
        root = os.path.join(tmp, "vsdx")
        extract(src, root)
    elif not os.path.isdir(src):
        sys.exit("no such file or directory: %s" % src)
    if not os.path.isfile(os.path.join(root, "visio", "document.xml")):
        sys.exit("%s does not look like a Visio drawing (no visio/document.xml)" % src)
    return Doc(root)


def main():
    ap = argparse.ArgumentParser(description="Convert the pages of a Visio .vsdx file to EMF files (one per page).")
    ap.add_argument("src", help="a .vsdx file, or a directory holding an unzipped .vsdx")
    ap.add_argument("out", nargs="?", help="output directory (default: ./<name>-emf)")
    ap.add_argument("--upi", type=int, default=0, help="output units per paper inch (0 = automatic)")
    ap.add_argument("--page", action="append", help="only these page names")
    ap.add_argument("--prefix", help="file-name prefix, giving '<prefix> - <page>.emf' "
                                      "(default: the .vsdx file's name; none for a directory)")
    ap.add_argument("--svg", type=int, metavar="DPI", help="also write an SVG preview at this px/inch")
    ap.add_argument("--text-mode", choices=["importer", "outline"], default="importer")
    ap.add_argument("--crop", type=float, metavar="MARGIN_IN", help="crop to content plus this margin (paper inches)")
    ap.add_argument("--uniq", action="store_true", help="make near-identical records distinct (padded record bounds, varied start vertex)")
    a = ap.parse_args()
    stem = os.path.splitext(os.path.basename(os.path.normpath(a.src)))[0]
    out = a.out or safe(stem) + "-emf"
    prefix = a.prefix if a.prefix is not None else (stem if os.path.isfile(a.src) else "")
    skipped = []
    with tempfile.TemporaryDirectory(prefix="vsdx-") as tmp:
        doc = open_doc(a.src, tmp)
        names = [p.name for p in doc.pages]
        missing = [n for n in (a.page or []) if n not in names]
        if missing:
            sys.exit("no such page: %s (pages in this file: %s)"
                     % (", ".join(map(repr, missing)), ", ".join(map(repr, names))))
        os.makedirs(out, exist_ok=True)
        for page in doc.pages:
            if a.page and page.name not in a.page:
                continue
            try:
                upi = a.upi or MAX_UPI
                ctx, w, h = build(doc, page, upi, a.crop, a.text_mode)
                if not a.upi:
                    upi = min(MAX_UPI, int(INT16_SAFE / (max(w, h) / upi)))
                    ctx, w, h = build(doc, page, upi, a.crop, a.text_mode)
            except NotImplementedError as e:
                print(f"skipped {page.name!r}: not supported yet: {e}", file=sys.stderr)
                skipped.append(page.name)
                continue
            data = emit_emf(ctx.ops, w, h, upi, uniq=a.uniq)
            name = (prefix + " - " if prefix else "") + safe(page.name)
            path = os.path.join(out, name + ".emf")
            with open(path, "wb") as f:
                f.write(data)
            print(f"{page.name!r}: {len(ctx.ops)} ops, {w}x{h} units @ {upi}/in -> {path} ({len(data)} bytes)")
            if a.svg:
                with open(os.path.join(out, name + ".svg"), "w", encoding="utf-8") as f:
                    f.write(to_svg(ctx.ops, w, h, a.svg, upi))
    if skipped:
        sys.exit(1)


if __name__ == "__main__":
    main()
