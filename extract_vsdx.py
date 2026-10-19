"""Extract a .vsdx (OPC zip) into a NEW, EMPTY directory and print a manifest.

usage: python -I extract_vsdx.py <file.vsdx> <empty-or-nonexistent-dest-dir>

convert.py does this itself (into a temporary directory) when it is given a .vsdx file; run this script
only to look at the XML inside a package by hand.
"""
import os
import sys
import zipfile


def extract(src, dest):
    """Unzip `src` into the new or empty directory `dest`; returns the archive's member list.

    Refuses a non-empty `dest` and any member whose path would land outside it."""
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit(f"refusing: {dest} is not empty")
    os.makedirs(dest, exist_ok=True)
    root = os.path.realpath(dest)
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        for info in infos:
            target = os.path.realpath(os.path.join(dest, info.filename))
            # zip-slip guard
            if not (target == root or target.startswith(root + os.sep)):
                sys.exit(f"refusing unsafe member path: {info.filename}")
        z.extractall(dest)
    return infos


def main(src, dest):
    for info in extract(src, dest):
        print(f"{info.file_size:>9}  {info.filename}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
