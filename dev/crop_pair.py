"""usage: crop_pair.py <mine_scaled.png> <ref.png> <dx> <dy> <x> <y> <w> <h> <zoom> <out.png>
ref region (x,y,w,h); mine region is offset by (dx,dy) (mine = ref + (dx,dy)). Output: ref | mine side by side, zoomed."""
import sys
from PIL import Image
mine_p, ref_p = sys.argv[1], sys.argv[2]
dx, dy, x, y, w, h, z = map(int, sys.argv[3:10])
out = sys.argv[10]
ref = Image.open(ref_p).convert("L").crop((x, y, x + w, y + h)).resize((w * z, h * z), Image.NEAREST)
mine = Image.open(mine_p).convert("L").crop((x + dx, y + dy, x + dx + w, y + dy + h)).resize((w * z, h * z), Image.NEAREST)
canvas = Image.new("L", (w * z * 2 + 12, h * z), 128)
canvas.paste(ref, (0, 0)); canvas.paste(mine, (w * z + 12, 0))
canvas.save(out)
