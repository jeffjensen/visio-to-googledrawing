"""usage: emf_walk.py file.emf   -> list records (type, size) and decode text records"""
import struct, sys
data = open(sys.argv[1], "rb").read()
pos, n = 0, 0
counts = {}
while pos < len(data):
    typ, size = struct.unpack_from("<II", data, pos)
    counts[typ] = counts.get(typ, 0) + 1
    if typ == 84:
        off_string, = struct.unpack_from("<I", data, pos + 8 + 16 + 12 + 12)
        nchars, = struct.unpack_from("<I", data, pos + 8 + 16 + 12 + 8)
        s = data[pos + off_string: pos + off_string + nchars * 2].decode("utf-16-le")
        print(f"@{pos:6d} TEXT n={nchars} size={size} off_string={off_string} {s!r}")
    if size == 0 or pos + size > len(data):
        print("BAD record at", pos, typ, size); break
    pos += size
    n += 1
print("records:", n, "types:", dict(sorted(counts.items())))
print("file length", len(data), "pos", pos)
