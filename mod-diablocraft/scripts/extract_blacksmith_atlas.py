"""Losslessly split the supplied Blacksmith BLP atlas using its TEX region table.

The TEX defines 23 named regions. EnhanceItem and ModifyItem contain three and
two visible panel sections respectively; exporting those sections yields the
requested 26 pieces. Their three original full panels are also retained.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "reference/D3 Assets/Base/Textures/2DUIArtisan_Blacksmith.blp"


def read_blp(path: Path) -> Image.Image:
    data = path.read_bytes()
    if data[:4] != b"BLP2" or data[8] != 3 or data[9] != 8:
        raise ValueError("Expected the supplied uncompressed BGRA BLP2 with 8-bit alpha")
    width, height, offset = struct.unpack_from("<III", data, 12)
    size = struct.unpack_from("<I", data, 84)[0]
    if size != width * height * 4 or offset + size > len(data):
        raise ValueError("Invalid BLP mip-zero bounds")
    return Image.frombytes("RGBA", (width, height), data[offset:offset+size], "raw", "BGRA")


def regions(path: Path, width: int, height: int) -> list[dict]:
    data = path.read_bytes()
    if struct.unpack_from("<II", data) != (0xDEADBEEF, 47):
        raise ValueError("Expected the supplied TEX version 47")
    if struct.unpack_from("<II", data, 36) != (width, height):
        raise ValueError("TEX and BLP atlas dimensions disagree")
    count, offset, size = struct.unpack_from("<III", data, 536)
    # TEX offsets are relative to its 16-byte container header. Each region is
    # a 64-byte NUL-terminated name followed by four normalized float bounds.
    if count != 23 or size != count * 80:
        raise ValueError("Unexpected Blacksmith region table; do not guess bounds")
    result = []
    for index in range(count):
        start = 16 + offset + index * 80
        name = data[start:start+64].split(b"\0", 1)[0].decode("ascii")
        uv = struct.unpack_from("<4f", data, start+64)
        pixel = [value * (width if i % 2 == 0 else height) for i, value in enumerate(uv)]
        if any(abs(value-round(value)) > 0.0001 for value in pixel):
            raise ValueError("A UV does not resolve to an exact pixel boundary")
        box = [round(value) for value in pixel]
        if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            raise ValueError("Region outside atlas")
        result.append({"source_region": name, "name": Path(name).stem, "box": box,
                       "bounds_source": "TEX named region"})
    return result


def split_panels(original: list[dict]) -> list[dict]:
    # Pixel boundaries measured at the visible horizontal panel separators in
    # this atlas. These subdivisions are editorial, not separate TEX records.
    cuts = {
        "Artisan_Blacksmith_EnhanceItem": [(216, "Header"), (496, "Body"), (734, "Footer")],
        "Artisan_Blacksmith_ModifyItem": [(216, "Header"), (734, "Body")],
    }
    result = []
    for region in original:
        if region["name"] not in cuts:
            result.append(region.copy())
            continue
        x0, y0, x1, y1 = region["box"]
        cursor = y0
        for bottom, label in cuts[region["name"]]:
            assert cursor < bottom <= y1
            result.append({**region, "name": region["name"] + "_" + label,
                           "box": [x0, cursor, x1, bottom],
                           "bounds_source": "visible panel section within TEX named region"})
            cursor = bottom
        assert cursor == y1, "panel partition must retain every source row"
    assert len(result) == 26
    return result


def next_power_of_two(size: int) -> int:
    return 1 << (size-1).bit_length()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.source.with_name(args.source.stem + "_split")
    atlas = read_blp(args.source)
    original = regions(args.source.with_suffix(".tex"), *atlas.size)
    pieces = split_panels(original)
    for folder in ("png", "blp", "original_panels"):
        (output / folder).mkdir(parents=True, exist_ok=True)

    spec = importlib.util.spec_from_file_location("ui_blp", ROOT / "client-patch/build_ui_art.py")
    encoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(encoder)
    manifest = []
    previews = []
    for index, piece in enumerate(pieces, 1):
        crop = atlas.crop(piece["box"])
        name = piece["name"]
        png_path, blp_path = output / "png" / (name + ".png"), output / "blp" / (name + ".blp")
        crop.save(png_path)
        # BLP canvases are power-of-two for the WoW client. Pad transparently;
        # never resize/recompress the source pixels. UVs exclude the padding.
        canvas = Image.new("RGBA", tuple(next_power_of_two(value) for value in crop.size), (0, 0, 0, 0))
        canvas.paste(crop, (0, 0))
        encoder.write_blp(canvas, blp_path, uncompressed=True)
        assert Image.open(png_path).convert("RGBA").tobytes() == crop.tobytes()
        assert read_blp(blp_path).tobytes() == canvas.tobytes()
        manifest.append({"number": index, **piece, "width": crop.width, "height": crop.height,
                         "png": png_path.relative_to(output).as_posix(),
                         "blp": blp_path.relative_to(output).as_posix(),
                         "blp_canvas": list(canvas.size),
                         "blp_texcoord_left_right_top_bottom": [0, crop.width/canvas.width, 0, crop.height/canvas.height]})
        previews.append((index, name, crop))

    for region in original[:3]:
        full = atlas.crop(region["box"])
        full.save(output / "original_panels" / (region["name"] + ".png"))
        related = [piece for piece in pieces if piece["source_region"] == region["source_region"]]
        rebuilt = Image.new("RGBA", full.size)
        for piece in related:
            rebuilt.paste(atlas.crop(piece["box"]), (piece["box"][0]-region["box"][0], piece["box"][1]-region["box"][1]))
        assert rebuilt.tobytes() == full.tobytes(), "panel sections must reassemble losslessly"

    document = {"source": args.source.name,
                "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                "tex_sha256": hashlib.sha256(args.source.with_suffix(".tex").read_bytes()).hexdigest(),
                "atlas_size": list(atlas.size), "named_regions": original,
                "note": "23 original named regions become 26 pieces by splitting EnhanceItem into 3 and ModifyItem into 2. PNGs are exact crops. BLPs preserve pixels on transparent power-of-two canvases.",
                "pieces": manifest}
    (output / "manifest.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    cell_w, cell_h, cols = 320, 236, 4
    sheet = Image.new("RGB", (cols*cell_w, ((len(previews)+cols-1)//cols)*cell_h), (32, 34, 38))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for index, name, crop in previews:
        x, y = ((index-1) % cols)*cell_w, ((index-1)//cols)*cell_h
        draw.rectangle((x+4, y+4, x+cell_w-5, y+cell_h-5), outline=(90, 95, 102))
        preview = crop.copy()
        preview.thumbnail((cell_w-24, 166))
        sheet.paste(preview, (x+(cell_w-preview.width)//2, y+10+(166-preview.height)//2), preview)
        caption = f"{index:02}  {name}\n{crop.width} x {crop.height}"
        lines = []
        for line in caption.splitlines():
            lines.extend(textwrap.wrap(line, width=38))
        draw.multiline_text((x+12, y+180), "\n".join(lines), font=font, fill=(232, 232, 232), spacing=3)
    sheet.save(output / "contact_sheet.png")
    (output / "README.txt").write_text(
        "26 Blacksmith atlas pieces\n\n"
        "png/: exact-size RGBA crops, original pixels and transparency.\n"
        "blp/: the same 26 pieces as uncompressed BLP2 with mipmaps. Canvases are padded to power-of-two sizes, never stretched.\n"
        "original_panels/: the three complete panels from the original TEX metadata.\n"
        "manifest.json: original region names, source pixel bounds, sizes and BLP UVs.\n"
        "contact_sheet.png: numbered preview of all 26 pieces.\n\n"
        "The companion TEX has 23 named regions. To produce 26 visual pieces, EnhanceItem was divided into header/body/footer and ModifyItem into header/body. All original panel pixels are retained.\n"
        "No game files are installed or changed.\n", encoding="utf-8")
    print(f"PASS: 26 PNGs, 26 BLPs, 3 original panels; exact pixel/alpha round trips and panel reassembly verified.\n{output}")


if __name__ == "__main__":
    main()
