#!/usr/bin/env python3
"""How necromancer.png was cut from the designer's Necromancer icon (diablocraft-im7mr.4); kept to redo the cut, not run by the
build.

    python3 client-patch/art/Interface/Glues/CharacterCreate/source/cut_necromancer.py <alex's png> necromancer.png

The designer's file (900x482, `_agent-scratch/necromancer-build-2026-10-15/alex-necro-icon-2026-10-16.png`) has no alpha: the
art sits on a baked 20 px white/grey (255/240) checkerboard with a soft white glow under the disc. The background is
what reaches the border through checkerboard or near-white grey pixels; within 3 px of it, the edge is unmixed from
the background against a dark outline. The art is then centred in a square with the Monk source's margin (art 233 of
250 px) and scaled to 256 px. Prints the art's box in the designer's file.
"""
import sys
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB"); px = im.load(); w, h = im.size
CELL = 20
def bg(x, y): return 255 if ((x // CELL) + (y // CELL)) % 2 == 0 else 240
def matches(x, y):
    v = bg(x, y); r, g, b = px[x, y]
    if abs(r - v) <= 3 and abs(g - v) <= 3 and abs(b - v) <= 3:
        return True
    return min(r, g, b) >= 215 and max(r, g, b) - min(r, g, b) <= 12   # the soft white glow under the disc
m = [[matches(x, y) for x in range(w)] for y in range(h)]
isbg = [[False]*w for _ in range(h)]       # the background is what reaches the border through background-looking pixels
stack = [(x, y) for x in range(w) for y in (0, h-1)] + [(x, y) for y in range(h) for x in (0, w-1)]
while stack:
    x, y = stack.pop()
    if 0 <= x < w and 0 <= y < h and m[y][x] and not isbg[y][x]:
        isbg[y][x] = True
        stack += [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
# distance (chebyshev, up to 3) from the background
near = [[False]*w for _ in range(h)]
for y in range(h):
    for x in range(w):
        if isbg[y][x]:
            for j in range(max(0, y-3), min(h, y+4)):
                for i in range(max(0, x-3), min(w, x+4)):
                    near[j][i] = True
o = Image.new("RGBA", (w, h)); op = o.load()
for y in range(h):
    for x in range(w):
        r, g, b = px[x, y]
        if isbg[y][x]:
            op[x, y] = (0, 0, 0, 0); continue
        if not near[y][x]:
            op[x, y] = (r, g, b, 255); continue
        v = max(bg(x, y), max(r, g, b))
        a = max(0.0, min(1.0, 1 - min(r, g, b) / v + 0.0))   # edge colours unmixed against a dark outline
        a = max(a, 0.0)
        if a < 0.02:
            op[x, y] = (0, 0, 0, 0); continue
        c = [max(0, min(255, round((ch - (1 - a) * v) / a))) for ch in (r, g, b)]
        op[x, y] = (*c, round(a * 255))
box = o.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
print("art box", box)
x0, y0, x1, y1 = box
side = round(max(x1 - x0, y1 - y0) * 250 / 233)     # the Monk's source: art 233 of 250
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
sq.alpha_composite(o.crop(box), (round(side/2 - (x1-x0)/2), round(side/2 - (y1-y0)/2)))
sq = sq.resize((256, 256), Image.LANCZOS)
sq.save(out, optimize=True)
print(out, sq.size)
