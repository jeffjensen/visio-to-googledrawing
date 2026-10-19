"""Write a tiny valid placeable WMF (rectangle + diagonal line) and print its base64.

usage: python -I make_probe_wmf.py <out.wmf>
"""
import base64
import struct
import sys


def rec(func, *params_words):
    """One WMF record: size in WORDs (incl. 3-word prefix), function, params."""
    body = b"".join(params_words)
    size_words = (6 + len(body)) // 2
    return struct.pack("<IH", size_words, func) + body


def i16(*v):
    return struct.pack("<" + "h" * len(v), *v)


def build():
    records = [
        rec(0x020B, i16(0, 0)),                                   # SetWindowOrg(y,x)
        rec(0x020C, i16(300, 400)),                               # SetWindowExt(y,x)
        rec(0x02FA, struct.pack("<HhhI", 0, 2, 0, 0x000000)),     # CreatePenIndirect solid w=2 black
        rec(0x02FC, struct.pack("<HIH", 0, 0xCFE5DD, 0)),         # CreateBrushIndirect solid (BGR)
        rec(0x012D, i16(0)),                                      # SelectObject pen
        rec(0x012D, i16(1)),                                      # SelectObject brush
        rec(0x041B, i16(80, 150, 20, 20)),                        # Rectangle(bottom,right,top,left)
        rec(0x0214, i16(120, 20)),                                # MoveTo(y,x)
        rec(0x0213, i16(250, 300)),                               # LineTo(y,x)
        rec(0x0000),                                              # EOF
    ]
    body = b"".join(records)
    max_rec = max(struct.unpack_from("<I", r)[0] for r in records)
    total_words = (18 + len(body)) // 2
    header = struct.pack("<HHHIHIH", 1, 9, 0x0300, total_words, 2, max_rec, 0)
    # placeable header
    words = struct.pack("<IHhhhhHI", 0x9AC6CDD7, 0, 0, 0, 400, 300, 96, 0)
    checksum = 0
    for (w,) in struct.iter_unpack("<H", words[:20]):
        checksum ^= w
    placeable = words + struct.pack("<H", checksum)
    return placeable + header + body


if __name__ == "__main__":
    data = build()
    with open(sys.argv[1], "wb") as f:
        f.write(data)
    print(len(data), "bytes")
    print(base64.b64encode(data).decode())
