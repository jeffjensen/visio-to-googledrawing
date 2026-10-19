"""usage: b64show.py <file.emf> [cols]  -> prints length and the base64 wrapped at `cols` columns, line-numbered in a comment-free way"""
import base64, sys, textwrap
b = base64.b64encode(open(sys.argv[1], "rb").read()).decode()
cols = int(sys.argv[2]) if len(sys.argv) > 2 else 76
print(f"[{len(b)} chars, {(len(b)+cols-1)//cols} lines of {cols}]")
for ln in textwrap.wrap(b, cols, break_on_hyphens=False, break_long_words=True):
    print(ln)
print("[end]")
