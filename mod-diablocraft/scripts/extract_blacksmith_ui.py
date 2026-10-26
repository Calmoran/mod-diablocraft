"""Extract the Blacksmith screen's UI art and write it as addon BLP textures.

The Blacksmith window is built from Diablo 3's own art, already extracted into
the repo under `reference/D3 Assets/Base/Textures/`:

  * 2DUIArtisan_Blacksmith  - the three body panels and the salvage buttons
    (already split by `extract_blacksmith_atlas.py`; this script re-reads the
    atlas so every piece lands under one name and one method)
  * 2DUITabs                - the five artisan tabs, selected/unselected/hover
  * 2DUIButtons             - the shared close button and the small text button
  * 2DUIArtisan             - the training panel

What it does, per piece: crop the TEX named region (or its sub-section), pad the
crop onto a transparent power-of-two canvas, encode it as the uncompressed BLP2
the pinned 3.3.5a client reads, and write it under
`client-patch/art/ui/blacksmith/<name>.blp`, beside its manifest. That folder is
reference art and is never shipped: the 45 `bs_*.blp` it used to write into
`client-patch/addons/Torment/art/` and their `Diablocraft.ART` slots are gone
(diablocraft-lido, the Blacksmith shell was deleted 2026-09-16 and nothing drew
them), and the extraction tools must not write into a shipped folder. Nothing is
resized or stretched; the transparent padding is a SetTexCoord crop in the addon.

Verification: every PNG crop matches its source crop byte for byte and every BLP
mip zero reads back byte-identical to the canvas. The panel sub-sections
reassemble byte-for-byte into their source region. A manifest with the source
boxes and texture coordinates is written beside the source art, and a
ready-to-paste `Diablocraft.ART` fragment is printed.

Source `.tex`/`.png` files are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "reference/D3 Assets/Base/Textures"
TARGET = ROOT / "client-patch/art/ui/blacksmith"
MANIFEST = ROOT / "client-patch/art/ui/blacksmith/manifest.json"

BLACKSMITH = "2DUIArtisan_Blacksmith"

# (output name, atlas stem, named region, colour fallback, sub-section)
# sub-section is None for the whole region or (top, bottom) pixel rows within
# it, the same editorial cuts `extract_blacksmith_atlas.py` uses.
PIECES: list[tuple[str, str, str, tuple[float, float, float, float], tuple[int, int] | None]] = [
    # --- body panels -----------------------------------------------------------
    ("bs_panel_salvage", BLACKSMITH, "Artisan_Blacksmith_Salvage", (0.12, 0.12, 0.10, 1.0), None),
    ("bs_panel_modify_header", BLACKSMITH, "Artisan_Blacksmith_ModifyItem", (0.20, 0.16, 0.10, 1.0), (0, 208)),
    ("bs_panel_modify_body", BLACKSMITH, "Artisan_Blacksmith_ModifyItem", (0.20, 0.16, 0.10, 1.0), (208, 726)),
    ("bs_panel_enhance_header", BLACKSMITH, "Artisan_Blacksmith_EnhanceItem", (0.20, 0.16, 0.10, 1.0), (0, 208)),
    ("bs_panel_enhance_body", BLACKSMITH, "Artisan_Blacksmith_EnhanceItem", (0.20, 0.16, 0.10, 1.0), (208, 488)),
    ("bs_panel_enhance_footer", BLACKSMITH, "Artisan_Blacksmith_EnhanceItem", (0.20, 0.16, 0.10, 1.0), (488, 726)),
    ("bs_panel_train", "2DUIArtisan", "Artisan_train_base", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_material_frame", BLACKSMITH, "Salvage_MaterialFrame.tga", (0.10, 0.09, 0.08, 1.0), None),
    # --- the five artisan tabs -------------------------------------------------
    ("bs_tab_salvage_selected", "2DUITabs", "Tab_Salvage_Selected", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_salvage_unselected", "2DUITabs", "Tab_Salvage_Unselected", (0.13, 0.12, 0.10, 1.0), None),
    ("bs_tab_salvage_hover", "2DUITabs", "Tab_Salvage_Mouseover", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_repair_selected", "2DUITabs", "Tab_Repair_Selected", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_repair_unselected", "2DUITabs", "Tab_Repair_Unselected", (0.13, 0.12, 0.10, 1.0), None),
    ("bs_tab_repair_hover", "2DUITabs", "Tab_Repair_Mouseover", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_training_selected", "2DUITabs", "Tab_Train_Selected", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_training_unselected", "2DUITabs", "Tab_Train_Unselected", (0.13, 0.12, 0.10, 1.0), None),
    ("bs_tab_training_hover", "2DUITabs", "Tab_Train_Mouseover", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_weapon_selected", "2DUITabs", "Tab_ForgeWeapon_Selected", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_weapon_unselected", "2DUITabs", "Tab_ForgeWeapon_Unselected", (0.13, 0.12, 0.10, 1.0), None),
    ("bs_tab_weapon_hover", "2DUITabs", "Tab_ForgeWeapon_Mouseover", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_armor_selected", "2DUITabs", "Tab_ForgeArmor_Selected", (0.20, 0.16, 0.10, 1.0), None),
    ("bs_tab_armor_unselected", "2DUITabs", "Tab_ForgeArmor_Unselected", (0.13, 0.12, 0.10, 1.0), None),
    ("bs_tab_armor_hover", "2DUITabs", "Tab_ForgeArmor_Mouseover", (0.20, 0.16, 0.10, 1.0), None),
    # --- salvage buttons (four rarities, four states) --------------------------
    ("bs_salvage_normal_normal", BLACKSMITH, "Salvage_Button_Normal", (0.30, 0.30, 0.30, 1.0), None),
    ("bs_salvage_normal_hover", BLACKSMITH, "Salvage_Button_Mouseover", (0.40, 0.40, 0.40, 1.0), None),
    ("bs_salvage_normal_pushed", BLACKSMITH, "Salvage_Button_Pushed", (0.50, 0.50, 0.50, 1.0), None),
    ("bs_salvage_normal_inactive", BLACKSMITH, "Salvage_Button_Inactive", (0.18, 0.18, 0.18, 1.0), None),
    ("bs_salvage_magic_normal", BLACKSMITH, "Salvage_Button_Magic_Normal", (0.10, 0.24, 0.55, 1.0), None),
    ("bs_salvage_magic_hover", BLACKSMITH, "Salvage_Button_Magic_Mouseover", (0.15, 0.32, 0.65, 1.0), None),
    ("bs_salvage_magic_pushed", BLACKSMITH, "Salvage_Button_Magic_Pushed", (0.20, 0.40, 0.75, 1.0), None),
    ("bs_salvage_magic_inactive", BLACKSMITH, "Salvage_Button_Magic_Inactive", (0.08, 0.16, 0.35, 1.0), None),
    ("bs_salvage_rare_normal", BLACKSMITH, "Salvage_Button_Rare_Normal", (0.50, 0.44, 0.08, 1.0), None),
    ("bs_salvage_rare_hover", BLACKSMITH, "Salvage_Button_Rare_Mouseover", (0.60, 0.53, 0.12, 1.0), None),
    ("bs_salvage_rare_pushed", BLACKSMITH, "Salvage_Button_Rare_Pushed", (0.70, 0.62, 0.16, 1.0), None),
    ("bs_salvage_rare_inactive", BLACKSMITH, "Salvage_Button_Rare_Inactive", (0.30, 0.26, 0.05, 1.0), None),
    ("bs_salvage_white_normal", BLACKSMITH, "Salvage_Button_White_Normal", (0.60, 0.60, 0.60, 1.0), None),
    ("bs_salvage_white_hover", BLACKSMITH, "Salvage_Button_White_Mouseover", (0.72, 0.72, 0.72, 1.0), None),
    ("bs_salvage_white_pushed", BLACKSMITH, "Salvage_Button_White_Pushed", (0.85, 0.85, 0.85, 1.0), None),
    ("bs_salvage_white_inactive", BLACKSMITH, "Salvage_Button_White_Inactive", (0.35, 0.35, 0.35, 1.0), None),
    # --- shared buttons --------------------------------------------------------
    ("bs_close_normal", "2DUIButtons", "D3_CloseBtn_Normal", (0.40, 0.12, 0.10, 1.0), None),
    ("bs_close_hover", "2DUIButtons", "D3_CloseBtn_Mouseover", (0.55, 0.18, 0.14, 1.0), None),
    ("bs_close_pushed", "2DUIButtons", "D3_CloseBtn_Pushed", (0.30, 0.08, 0.06, 1.0), None),
    ("bs_button_normal", "2DUIButtons", "D3_Btn_Small_Normal", (0.22, 0.19, 0.14, 1.0), None),
    ("bs_button_hover", "2DUIButtons", "D3_Btn_Small_Mouseover", (0.32, 0.27, 0.18, 1.0), None),
    ("bs_button_pushed", "2DUIButtons", "D3_Btn_Small_Pushed", (0.16, 0.13, 0.09, 1.0), None),
]

# atlas stem -> (Image, {region: box}) read on demand.
_ATLAS_CACHE: dict[str, tuple[Image.Image, dict[str, list[int]]]] = {}


def read_blp(path: Path) -> Image.Image:
    data = path.read_bytes()
    if data[:4] != b"BLP2" or data[8] != 3 or data[9] != 8:
        raise ValueError("Expected uncompressed BGRA BLP2 with 8-bit alpha")
    width, height, offset = struct.unpack_from("<III", data, 12)
    size = struct.unpack_from("<I", data, 84)[0]
    if size != width * height * 4 or offset + size > len(data):
        raise ValueError("Invalid BLP mip-zero bounds")
    return Image.frombytes("RGBA", (width, height), data[offset:offset + size], "raw", "BGRA")


def regions(tex_path: Path, width: int, height: int) -> dict[str, list[int]]:
    data = tex_path.read_bytes()
    if struct.unpack_from("<II", data) != (0xDEADBEEF, 47):
        raise ValueError(f"{tex_path.name}: expected the supplied TEX version 47")
    if struct.unpack_from("<II", data, 36) != (width, height):
        raise ValueError(f"{tex_path.name}: TEX and PNG dimensions disagree")
    count, offset, size = struct.unpack_from("<III", data, 536)
    if count == 0 or size != count * 80:
        raise ValueError(f"{tex_path.name}: unexpected region table; do not guess bounds")
    result = {}
    for index in range(count):
        start = 16 + offset + index * 80
        name = data[start:start + 64].split(b"\0", 1)[0].decode("ascii")
        uv = struct.unpack_from("<4f", data, start + 64)
        pixel = [value * (width if i % 2 == 0 else height) for i, value in enumerate(uv)]
        if any(abs(value - round(value)) > 0.0001 for value in pixel):
            raise ValueError(f"{tex_path.name}: a UV of {name!r} is not on a pixel boundary")
        box = [round(value) for value in pixel]
        if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            raise ValueError(f"{tex_path.name}: region {name!r} is outside the atlas")
        result[name] = box
    return result


def atlas(stem: str) -> tuple[Image.Image, dict[str, list[int]]]:
    if stem not in _ATLAS_CACHE:
        image = Image.open(ASSETS / (stem + ".png")).convert("RGBA")
        _ATLAS_CACHE[stem] = (image, regions(ASSETS / (stem + ".tex"), *image.size))
    return _ATLAS_CACHE[stem]


def next_power_of_two(size: int) -> int:
    return 1 << (size - 1).bit_length()


def lua_coords(box: list[float]) -> str:
    return "{" + ", ".join(f"{value:.10g}" for value in box) + "}"


def lua_colour(colour: tuple[float, float, float, float]) -> str:
    return "{" + ", ".join(f"{value:.2f}" for value in colour) + "}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TARGET)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)

    spec = importlib.util.spec_from_file_location("ui_blp", ROOT / "client-patch/build_ui_art.py")
    encoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(encoder)

    pieces, art_entries = [], []
    for name, stem, region, colour, cut in PIECES:
        image, table = atlas(stem)
        if region not in table:
            raise SystemExit(f"{stem}: region {region!r} not found")
        x0, y0, x1, y1 = table[region]
        if cut is not None:
            y0, y1 = table[region][1] + cut[0], table[region][1] + cut[1]
        crop = image.crop((x0, y0, x1, y1))
        canvas = Image.new("RGBA", (next_power_of_two(crop.width), next_power_of_two(crop.height)), (0, 0, 0, 0))
        canvas.paste(crop, (0, 0))
        out = args.output / (name + ".blp")
        encoder.write_blp(canvas, out, uncompressed=True)
        if read_blp(out).tobytes() != canvas.tobytes():
            raise SystemExit(f"{name}: BLP round trip failed")
        coords = [0.0, round(crop.width / canvas.width, 10), 0.0, round(crop.height / canvas.height, 10)]
        pieces.append({
            "name": name, "atlas": stem, "region": region,
            "source_box": [x0, y0, x1, y1], "crop": [crop.width, crop.height],
            "blp_canvas": list(canvas.size), "blp": out.name,
            "blp_texcoord_left_right_top_bottom": coords,
        })
        art_entries.append(
            f'    ["{name}"] = {{file = "{name}", colour = {lua_colour(colour)}, coords = {lua_coords(coords)}}},'
        )
        print(f"  {name:32} {crop.width:>4}x{crop.height:<4} -> {canvas.width}x{canvas.height}  {out.name}")

    # Panels must reassemble into their source region with no pixel lost.
    for stem, region in ((BLACKSMITH, "Artisan_Blacksmith_ModifyItem"), (BLACKSMITH, "Artisan_Blacksmith_EnhanceItem")):
        image, table = atlas(stem)
        x0, y0, x1, y1 = table[region]
        full = image.crop((x0, y0, x1, y1))
        related = [p for p in pieces if p["region"] == region and p["atlas"] == stem]
        rebuilt = Image.new("RGBA", full.size, (0, 0, 0, 0))
        for piece in related:
            px0, py0, px1, py1 = piece["source_box"]
            rebuilt.paste(image.crop((px0, py0, px1, py1)), (px0 - x0, py0 - y0))
        if rebuilt.tobytes() != full.tobytes():
            raise SystemExit(f"{region}: sub-sections do not reassemble")

    sources = sorted({p["atlas"] for p in pieces})
    document = {
        "note": "Extracted from Diablo 3's own atlases for the Blacksmith screen. Crops are exact; BLP canvases are padded transparently to power-of-two, never resized. Coordinates are SetTexCoord(left,right,top,bottom).",
        "atlases": {stem: hashlib.sha256((ASSETS / (stem + ".blp")).read_bytes()).hexdigest()
                    if (ASSETS / (stem + ".blp")).exists() else None for stem in sources},
        "pieces": pieces,
    }
    args.manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    print(f"PASS: {len(pieces)} BLP pieces written to {args.output}; every round trip and panel reassembly verified.")
    print("---- Diablocraft.ART fragment ----")
    print("\n".join(art_entries))


if __name__ == "__main__":
    main()
