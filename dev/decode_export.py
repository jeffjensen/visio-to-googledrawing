"""Decode the base64 'content' field of a saved Drive download_file_content result.

usage: python -I decode_export.py <tool-result.json> <out-file>
"""
import base64
import json
import sys


def main(src, dest):
    with open(src, "r", encoding="utf-8") as f:
        obj = json.load(f)
    data = base64.b64decode(obj["content"])
    with open(dest, "wb") as f:
        f.write(data)
    print(f"{obj.get('title')!r} {obj.get('mimeType')} -> {dest} ({len(data)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
