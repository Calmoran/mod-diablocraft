#!/usr/bin/env python3
"""Turn the D3 UI font kit into fonts the 3.3.5a client can actually load.

The stash kit under the agent scratch holds the five fonts D3 ships, recovered
from its own Flash/SWF UI: `ExocetLight.otf`, `SansSerif.ttf`, `Serif.ttf`,
`Script.ttf` and `Axe Bad Data.ttf`. They are handed to us as real font files,
but only one of them (`ExocetLight.otf`) is postscript-outline CFF, and the
client cannot read CFF - the same reason the rift art had to become BLP. So
this tool ships three of the five into `client-patch/addons/Torment/fonts/`,
where the addon loads them by path with

    fontString:SetFont("Interface\\AddOns\\Torment\\fonts\\<file>", size, flags)

(`OWN_ADDONS` in release.sh zips the whole addon folder, so anything dropped in
places.)

    Exocet.ttf    ExocetLight.otf, CFF charstrings converted to quadratic glyf.
                  Full charset, no subsetting - the source is only 53 KB and
                  the font is used for names, banners and the EQUIPPED plaque.
    SansSerif.ttf SansSerif.ttf subset to the characters the tooltips, labels
                  and numbers actually use (ASCII, Latin-1 Supplement, General
                  Punctuation, plus euro and trademark). TrueType outlines kept.
    Serif.ttf     Serif.ttf subset to ASCII only, for the single big damage /
                  armor number; nothing outside ASCII is ever drawn in it.

`Script.ttf` (monster hover text) and `Axe Bad Data.ttf` (D3's debug font) are
deliberately not shipped, but are recorded under `not_shipped` so the manifest
says what was looked at.

The CFF -> glyf conversion follows the well-known fontTools `otf2ttf` recipe:
draw every glyph through `Cu2QuPen` (cubic to quadratic) into a `TTGlyphPen`,
build `glyf`/`loca`, drop `CFF `, and rebuild `maxp` for glyf (version 1.0,
component counts). `head.indexToLocFormat` and `loca` are recomputed by the
compile pass; `head.modified` is pinned off (`recalcTimestamp = False`) so the
output is reproducible and `--check` is byte-stable.

    python client-patch/build_tooltip_fonts.py --source <d3-fonts>/fonts
    python client-patch/build_tooltip_fonts.py --source <d3-fonts>/fonts --check
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path

try:
    import fontTools
    from fontTools import subset
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable
    HAVE_FONTTOOLS = True
except ImportError:  # --check only hashes committed files; plain python3 can run it
    HAVE_FONTTOOLS = False

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "addons" / "Torment" / "fonts"
MANIFEST = OUT / "manifest.json"

# The characters SansSerif is subset to. Written in fontTools' --unicodes form.
UNICODES = ("U+0020-U+007E,U+00A0-U+00FF,U+2010-U+2027,"
            "U+2030,U+2039-U+203A,U+20AC,U+2122")
# Serif only ever draws the big damage/armor number, so ASCII is enough.
SERIF_UNICODES = "U+0020-U+007E"

# The five kit files by name, and what each output is for.
SHIPPED = {
    "Exocet.ttf": "D3 Exocet: item names, the banner, the EQUIPPED plaque",
    "SansSerif.ttf": "D3 SansSerif: body text, labels, numbers, flavour (BlizzardGlobal)",
    "Serif.ttf": "D3 Serif: the big damage/armor number (D3Serif)",
}
NOT_SHIPPED = {
    "Script.ttf": "monster / hover text - not used by this tooltip reskin",
    "Axe Bad Data.ttf": "D3's debug font - not used by this tooltip reskin",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def otf_to_ttf(font: TTFont, max_err: float = 1.0) -> TTFont:
    """Convert a CFF font in place to quadratic glyf outlines (otf2ttf recipe)."""
    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()

    glyf = newTable("glyf")
    glyf.glyphOrder = glyph_order
    glyf.glyphs = {}
    for name in glyph_order:
        pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(pen, max_err))
        glyf.glyphs[name] = pen.glyph()
    font["glyf"] = glyf

    del font["CFF "]
    for table in ("VORG", "GPOS", "GSUB"):
        if table in font:
            del font[table]

    font["loca"] = newTable("loca")
    glyf.compile(font)

    maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    maxp.numGlyphs = len(glyph_order)
    maxp.maxZones = 1
    maxp.maxTwilightPoints = 0
    maxp.maxStorage = 0
    maxp.maxFunctionDefs = 0
    maxp.maxInstructionDefs = 0
    maxp.maxStackElements = 0
    maxp.maxSizeOfInstructions = 0
    maxp.maxComponentElements = max(
        (len(g.components) if hasattr(g, "components") else 0)
        for g in glyf.glyphs.values()
    )
    font["maxp"] = maxp

    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = glyph_order

    font.sfntVersion = "\x00\x01\x00\x00"
    return font


def subset_font(font: TTFont, unicodes: str) -> TTFont:
    """Subset to the given unicode ranges, keeping TrueType outlines."""
    options = subset.Options()
    options.recalc_bounds = True
    options.hinting = False       # drop fpgm/prep/cvt: unused shrink on these fonts
    options.legacy_kern = False
    # fontTools' parse_unicodes does not accept the "U+" prefix, so strip it.
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=subset.parse_unicodes(re.sub(r"[Uu]\+", "", unicodes)))
    subsetter.subset(font)
    return font


def render(source: Path, unicodes: str | None = None, to_ttf: bool = False) -> bytes:
    if not HAVE_FONTTOOLS:
        raise SystemExit("fontTools is required to build fonts; install it "
                         "(e.g. a venv) and run from there")
    font = TTFont(str(source))
    if to_ttf:
        font = otf_to_ttf(font)
    elif unicodes is not None:
        font = subset_font(font, unicodes)
    font.recalcTimestamp = False  # byte-stable output for --check
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def source_record(source: Path) -> dict:
    data = source.read_bytes()
    font = TTFont(str(source))
    return {
        "source": source.name,
        "source_sha256": sha256(data),
        "source_bytes": len(data),
        "tables": sorted(t for t in font.keys() if t != "GlyphOrder"),
    }


def build(source_dir: Path) -> dict:
    if not HAVE_FONTTOOLS:
        raise SystemExit("fontTools is required to build fonts; install it "
                         "(e.g. a venv) and run from there")
    fonts = []
    not_shipped = []
    for output, use in SHIPPED.items():
        source_name = "ExocetLight.otf" if output == "Exocet.ttf" else output
        source = source_dir / source_name
        if not source.is_file():
            raise SystemExit(f"missing source font: {source}")
        record = source_record(source)
        data = render(source, unicodes=None if output == "Exocet.ttf" else
                      (SERIF_UNICODES if output == "Serif.ttf" else UNICODES),
                      to_ttf=output == "Exocet.ttf")
        out = OUT / output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        result = TTFont(str(out))
        fonts.append({
            "output": output,
            "source": source.name,
            "source_sha256": record["source_sha256"],
            "source_bytes": record["source_bytes"],
            "output_sha256": sha256(data),
            "output_bytes": len(data),
            "outlines": "glyf",
            "tables": sorted(t for t in result.keys() if t != "GlyphOrder"),
            "use": use,
        })
    for output, reason in NOT_SHIPPED.items():
        source = source_dir / output
        if not source.is_file():
            raise SystemExit(f"missing source font: {source}")
        record = source_record(source)
        record["reason"] = reason
        not_shipped.append(record)
    manifest = {
        "tool": "build_tooltip_fonts.py",
        "fontTools": fontTools.version,
        "unicodes": UNICODES,
        "serif_unicodes": SERIF_UNICODES,
        "fonts": fonts,
        "not_shipped": not_shipped,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def check(source_dir: Path) -> int:
    manifest = json.loads(MANIFEST.read_text())
    failures = 0
    for entry in manifest["fonts"]:
        source = source_dir / entry["source"]
        if not source.is_file():
            print(f"{entry['output']:16} MISSING SOURCE {source}")
            failures += 1
            continue
        source_data = source.read_bytes()
        if sha256(source_data) != entry["source_sha256"]:
            print(f"{entry['output']:16} source changed: {source}")
            failures += 1
        out = OUT / entry["output"]
        if not out.is_file():
            print(f"{entry['output']:16} MISSING {out}")
            failures += 1
            continue
        data = out.read_bytes()
        ok = sha256(data) == entry["output_sha256"] and len(data) == entry["output_bytes"]
        if HAVE_FONTTOOLS:  # also prove the outputs rebuild byte-for-byte
            rebuilt = render(source, unicodes=None if entry["output"] == "Exocet.ttf" else
                             (SERIF_UNICODES if entry["output"] == "Serif.ttf" else UNICODES),
                             to_ttf=entry["output"] == "Exocet.ttf")
            ok = ok and sha256(rebuilt) == entry["output_sha256"]
        print(f"{entry['output']:16} {'ok' if ok else 'MISMATCH'}  {len(data)} bytes  {sha256(data)[:16]}")
        if not ok:
            failures += 1
    for entry in manifest["not_shipped"]:
        source = source_dir / entry["source"]
        if source.is_file() and sha256(source.read_bytes()) != entry["source_sha256"]:
            print(f"{entry['source']:16} source changed (not shipped)")
            failures += 1
    if failures:
        print(f"{failures} mismatch(es)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="folder holding the five D3 font files by name")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed outputs against manifest.json; write nothing")
    arguments = parser.parse_args()

    if not arguments.source.is_dir():
        raise SystemExit(f"no source font folder at {arguments.source}")

    if arguments.check:
        return check(arguments.source)

    manifest = build(arguments.source)
    for entry in manifest["fonts"]:
        print(f"{entry['output']:16} {entry['output_bytes']:>8} bytes  "
              f"{entry['source']} -> glyf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
