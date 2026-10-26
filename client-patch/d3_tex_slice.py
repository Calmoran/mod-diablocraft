#!/usr/bin/env python3
"""Slice a Diablo III .tex atlas into WoW textures for the ForgeUI editor.

Two steps, the first in WhiteoutTex (tools/WhiteoutTex), the second here:

  1. In WhiteoutTex open the D3 install (File > Open CASC, the "Diablo III"
     folder), find the .tex you want, and save it as PNG next to a copy of the
     .tex in reference/D3 Assets/Base/Textures/ with the same name
     (2DUITabs.tex + 2DUITabs.png). A BLP saved by WhiteoutTex works too.
  2. python client-patch/d3_tex_slice.py "reference/D3 Assets/Base/Textures/2DUITabs.tex"
     (several .tex paths at once are fine)

Three modes:

  (slice, the default)  one BLP per frame, padded to power-of-two
  --whole <tex>         ONE BLP of the entire atlas plus atlas_coords.csv giving
                        every frame's L/R/T/B against it - paste four numbers in
                        ForgeUI instead of adding a file per piece
  --index <folder>      every frame name in every .tex under the folder, into
                        reference/D3 Assets/sliced/tex_index.csv. Reads frame
                        tables only, so NO PNG is needed and a whole CASC dump
                        indexes in seconds. This is how you find which atlas
                        holds a piece: search the CSV by name or by pixel size.

ForgeUI rejects any crop under 0.04 of the image in either direction and draws
the whole texture instead (122_GroupsAndButtonStates, ResolveButtonNormalUV).
Both --whole and --index flag those frames. They still work as a plain Texture
widget; it is a Button's Normal/Inactive face that substitutes the full atlas.

The .tex supplies Blizzard's frame table (names and rectangles); the PNG/BLP
supplies the pixels. The .tex pixel data itself is a layout this script does
not decode, which is why WhiteoutTex does that half.

For each .tex this writes:

  reference/D3 Assets/sliced/<name>/atlas.png        the whole atlas, decoded
  reference/D3 Assets/sliced/<name>/png/<frame>.png  one PNG per frame, exact size
  reference/D3 Assets/sliced/<name>/manifest.csv     frame, size, texcoord right/bottom
  reference/D3 Assets/sliced/<name>/contact.png      everything on one sheet
  WoW Client/Interface/AddOns/ForgeUI/textures/<name>/<frame>.blp
                                                     ready for the editor: paste
                                                     Interface\AddOns\ForgeUI\textures\<name>\<frame>.blp

WoW needs power-of-two textures, so every frame is padded (never scaled) to the
next power of two at the top-left. In ForgeUI set Tex Coords R and B to the
values in manifest.csv (L and T stay 0) and the padding disappears. Restart the
client after adding files: it indexes Interface\\AddOns at launch.

Format notes (D3 .tex, version 47, verified on 2DUIArtisan_Blacksmith and
2DUITabs): 0xDEADBEEF, version, width at word 9, height at word 10; the frame
table pointer sits at byte 536: count, offset, byte size. Each record is 80
bytes: name[64] then four floats u0,v0,u1,v1 as fractions of the atlas.
"""
from __future__ import annotations

import csv
import importlib.util
import re
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SLICED = ROOT / "reference" / "D3 Assets" / "sliced"
FORGE = ROOT / "WoW Client" / "Interface" / "AddOns" / "ForgeUI" / "textures"

spec = importlib.util.spec_from_file_location("build_ui_art", ROOT / "client-patch" / "build_ui_art.py")
build_ui_art = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_ui_art)


def read_frames(data: bytes) -> tuple[int, int, list[tuple[str, float, float, float, float]]]:
    if struct.unpack_from("<I", data, 0)[0] != 0xDEADBEEF:
        raise SystemExit("not a D3 .tex (bad magic)")
    width, height = struct.unpack_from("<II", data, 36)
    count, offset, _size = struct.unpack_from("<III", data, 536)
    frames = []
    for index in range(count):
        record = offset + 16 + 80 * index  # table offsets are relative to byte 16
        name = data[record:record + 64].split(b"\0")[0].decode("ascii", "replace")
        u0, v0, u1, v1 = struct.unpack_from("<4f", data, record + 64)
        frames.append((name, u0, v0, u1, v1))
    return width, height, frames


def read_blp_uncompressed(data: bytes) -> Image.Image:
    """BLP2 encoding 3 (raw BGRA), the flavour WhiteoutTex writes by default."""
    magic, _type, encoding, _alpha, _alpha_type, _mips, width, height = struct.unpack_from("<4sIBBBBII", data, 0)
    if magic != b"BLP2" or encoding != 3:
        raise SystemExit("only uncompressed BLP2 is read here; save a PNG from WhiteoutTex instead")
    offset, size = struct.unpack_from("<I", data, 20)[0], struct.unpack_from("<I", data, 84)[0]
    return Image.frombytes("RGBA", (width, height), data[offset:offset + size], "raw", "BGRA")


def load_pixels(tex: Path) -> Image.Image:
    png, blp = tex.with_suffix(".png"), tex.with_suffix(".blp")
    if png.exists():
        return Image.open(png).convert("RGBA")
    if blp.exists():
        return read_blp_uncompressed(blp.read_bytes())
    raise SystemExit(f"{tex.name}: save it as {png.name} (or .blp) from WhiteoutTex first")


def pot(value: int) -> int:
    return 1 << max(0, (value - 1).bit_length())


def slice_tex(path: Path, out_root: Path = None) -> None:
    name = path.stem
    width, height, frames = read_frames(path.read_bytes())
    image = load_pixels(path)
    if image.size != (width, height):
        raise SystemExit(f"{name}: pixels are {image.size} but the .tex says {(width, height)}")
    out = SLICED / name
    (out / "png").mkdir(parents=True, exist_ok=True)
    forge = (out_root or FORGE) / name
    forge.mkdir(parents=True, exist_ok=True)
    image.save(out / "atlas.png")
    if not frames:
        print(f"{name}: no frame table, atlas.png written only")
        return

    rows = []
    for frame, u0, v0, u1, v1 in frames:
        x0, y0 = round(u0 * image.width), round(v0 * image.height)
        x1, y1 = round(u1 * image.width), round(v1 * image.height)
        if x1 <= x0 or y1 <= y0:
            continue
        piece = image.crop((x0, y0, x1, y1))
        safe = re.sub(r"[^A-Za-z0-9_\-]", "_", frame.replace(".tga", ""))
        piece.save(out / "png" / f"{safe}.png")
        canvas = Image.new("RGBA", (pot(piece.width), pot(piece.height)), (0, 0, 0, 0))
        canvas.paste(piece, (0, 0))
        build_ui_art.write_blp(canvas, forge / f"{safe}.blp", False)
        rows.append({
            "frame": safe, "width": piece.width, "height": piece.height,
            "canvas": f"{canvas.width}x{canvas.height}",
            "texcoord_right": round(piece.width / canvas.width, 4),
            "texcoord_bottom": round(piece.height / canvas.height, 4),
            "atlas_rect": f"{x0},{y0},{x1 - x0},{y1 - y0}",
            "forgeui_path": f"Interface\\AddOns\\ForgeUI\\textures\\{name}\\{safe}.blp",
        })
    with open(out / "manifest.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    sheet = Image.new("RGBA", (1600, 4000), (60, 60, 60, 255))
    draw = ImageDraw.Draw(sheet)
    x = y = 8
    row_height = 0
    for row in rows:
        piece = Image.open(out / "png" / f"{row['frame']}.png")
        scale = min(1.0, 300 / piece.width, 300 / piece.height)
        piece = piece.resize((max(1, int(piece.width * scale)), max(1, int(piece.height * scale))))
        if x + piece.width + 8 > sheet.width:
            x, y, row_height = 8, y + row_height + 22, 0
        sheet.alpha_composite(piece, (x, y))
        draw.text((x, y + piece.height + 2), f"{row['frame']} {row['width']}x{row['height']}", fill=(255, 220, 120, 255))
        x += piece.width + 8
        row_height = max(row_height, piece.height)
    sheet.crop((0, 0, sheet.width, y + row_height + 26)).save(out / "contact.png")
    print(f"{name}: {len(rows)} frames -> {out} and {forge}")


def index_dir(root: Path) -> None:
    """Every frame name in every .tex under root. Reads frame tables only -
    no pixels, so no PNG is needed and a whole CASC dump indexes in seconds."""
    files = sorted(root.rglob("*.tex"))
    if not files:
        raise SystemExit(f"no .tex files under {root}")
    rows, skipped = [], []
    for path in files:
        try:
            width, height, frames = read_frames(path.read_bytes())
        except Exception:
            skipped.append(path.name)
            continue
        for frame, u0, v0, u1, v1 in frames:
            rows.append({
                "atlas": path.stem,
                "atlas_size": f"{width}x{height}",
                "frame": frame.replace(".tga", ""),
                "width": round((u1 - u0) * width),
                "height": round((v1 - v0) * height),
                "under_forgeui_floor": "yes" if (u1 - u0) < 0.04 or (v1 - v0) < 0.04 else "",
                "tex_file": str(path.relative_to(root)) if root in path.parents else path.name,
            })
    if not rows:
        raise SystemExit("no frame tables found")
    SLICED.mkdir(parents=True, exist_ok=True)
    out = SLICED / "tex_index.csv"
    with open(out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} frames across {len(files) - len(skipped)} atlases -> {out}")
    if skipped:
        print(f"skipped {len(skipped)} non-D3-.tex files: {', '.join(skipped[:8])}")


def whole_tex(path: Path, out_root: Path = None) -> None:
    """The whole atlas as ONE client-ready BLP, plus every frame's tex coords
    against it. One file per atlas instead of one per piece."""
    name = path.stem
    width, height, frames = read_frames(path.read_bytes())
    image = load_pixels(path)
    if image.size != (width, height):
        raise SystemExit(f"{name}: pixels are {image.size} but the .tex says {(width, height)}")
    if (pot(width), pot(height)) != (width, height):
        raise SystemExit(f"{name}: {width}x{height} is not power-of-two; the client will not load it")
    root = out_root or FORGE
    root.mkdir(parents=True, exist_ok=True)
    blp = root / f"{name}.blp"
    build_ui_art.write_blp(image, blp, False)
    rows = []
    for frame, u0, v0, u1, v1 in frames:
        pixel_w, pixel_h = round((u1 - u0) * width), round((v1 - v0) * height)
        if pixel_w <= 0 or pixel_h <= 0:
            continue
        rows.append({
            "frame": frame.replace(".tga", ""),
            "width": pixel_w, "height": pixel_h,
            "L": round(u0, 4), "R": round(u1, 4), "T": round(v0, 4), "B": round(v1, 4),
            "under_forgeui_floor": "yes" if (u1 - u0) < 0.04 or (v1 - v0) < 0.04 else "",
            "forgeui_path": f"Interface\\AddOns\\ForgeUI\\textures\\{name}.blp",
        })
    out = SLICED / name
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "atlas_coords.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    flagged = sum(1 for row in rows if row["under_forgeui_floor"])
    note = ""
    if flagged:
        note = (f"; {flagged} frames are under ForgeUI's 0.04 crop floor - draw those as a "
                f"Texture widget, not a Button's Normal/Inactive face, or they render the whole atlas")
    print(f"{name}: atlas -> {blp}; {len(rows)} frames -> {out / 'atlas_coords.csv'}{note}")



def expand(arguments: list[str]) -> list[Path]:
    """A folder means every .tex inside it; a file means that file."""
    paths = []
    for argument in arguments:
        path = Path(argument)
        paths.extend(sorted(path.rglob("*.tex")) if path.is_dir() else [path])
    return paths


def main() -> int:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    if args[0] == "--index":
        if len(args) != 2:
            raise SystemExit('usage: --index "<folder holding .tex files>"')
        index_dir(Path(args[1]))
        return 0

    out_root = None
    if "--out" in args:
        position = args.index("--out")
        if position + 1 >= len(args):
            raise SystemExit('--out needs a folder')
        out_root = Path(args[position + 1])
        del args[position:position + 2]

    whole = args and args[0] == "--whole"
    paths = expand(args[1:] if whole else args)
    if not paths:
        raise SystemExit('nothing to do: pass .tex files or a folder of them')

    done, no_png, failed = 0, [], []
    for path in paths:
        try:
            (whole_tex if whole else slice_tex)(path, out_root)
            done += 1
        except (SystemExit, Exception) as error:
            message = str(error)
            (no_png if "from WhiteoutTex first" in message else failed).append((path.name, message))
    if len(paths) > 1:
        print(f"\n{done} of {len(paths)} atlases written.")
        if no_png:
            print(f"{len(no_png)} skipped, no PNG beside the .tex yet: "
                  f"{', '.join(name for name, _ in no_png[:8])}"
                  f"{' ...' if len(no_png) > 8 else ''}")
        for name, message in failed:
            print(f"FAILED {name}: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
