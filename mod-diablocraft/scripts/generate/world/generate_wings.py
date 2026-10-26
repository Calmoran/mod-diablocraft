#!/usr/bin/env python3
# Constant (audit 223, 31884): Avenging Wrath icon donor; Stock spell identity; not gameplay magnitude.
# Constant (audit 224, 43024): Self-aura spell donor; Stock spell identity; not gameplay magnitude.
# Constant (audit 225, 100): Maximum accepted wing visual scale; Input-validation ceiling; actual scale comes from wing_variants.csv.
# Constant (audit 228, 1): Wing shirt bind-on-pickup; Column bonding is native enum 1.
# Constant (audit 230, 0): Wing shirt armor; Cosmetic-only no-combat-bonus contract.
# Constant (audit 231, 1): Wing shirt quality; Native common-quality enum.
"""Generate cosmetic wing assets, client DBC records and server SQL from CSV.

Run after generate_spells.py and build_item.py, before client-patch/build.ps1.
The imported archive's complete DBC files are never copied into the project.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import (require_companion_migration, write_coupled_outputs,
                                write_migration)
from tunable_values import value as tunable_value, integer as tunable_integer
import argparse
import colorsys
import csv
import hashlib
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "mod-diablocraft/data/d3/wing_variants.csv"
SOURCE = ROOT / "client-patch/source/wings"
BASE = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CLIENT = ROOT / "client-patch/dbc"
ART = ROOT / "client-patch/art/Item/ObjectComponents/Wings/DiabloCraft"
MANIFEST = ROOT / "client-patch/wings-manifest.json"
MODEL_PREFIX = "Item\\ObjectComponents\\Wings\\DiabloCraft\\"
SPELL_STRING_FIELDS = set(range(136, 152)) | set(range(153, 169)) | set(range(170, 186)) | set(range(187, 203))


class DBC:
    """Preserve non-owned records byte for byte, including their order."""
    def __init__(self, path: Path, fields: int):
        raw = path.read_bytes()
        magic, count, actual_fields, size, string_size = struct.unpack_from("<4s4I", raw)
        if magic != b"WDBC" or actual_fields != fields or size != fields * 4:
            raise ValueError(f"{path}: unexpected DBC layout")
        if len(raw) != 20 + count * size + string_size:
            raise ValueError(f"{path}: invalid DBC length")
        self.fields = fields
        self.records = [raw[20 + i * size:20 + (i + 1) * size] for i in range(count)]
        self.strings = bytearray(raw[20 + count * size:])
        self.offsets: dict[str, int] = {}
        start = 0
        while start < len(self.strings):
            end = self.strings.index(0, start)
            value = self.strings[start:end].decode("utf-8")
            self.offsets.setdefault(value, start)
            start = end + 1
        self.managed: dict[int, bytes] = {}

    def text(self, offset: int) -> str:
        return self.strings[offset:self.strings.index(0, offset)].decode("utf-8")

    def row(self, ident: int) -> list[int]:
        matches = [r for r in self.records if struct.unpack_from("<I", r)[0] == ident]
        if len(matches) != 1:
            raise ValueError(f"Expected one source row for {ident}, got {len(matches)}")
        return list(struct.unpack("<" + "I" * self.fields, matches[0]))

    def string_offset(self, value: str) -> int:
        if value not in self.offsets:
            self.offsets[value] = len(self.strings)
            self.strings.extend(value.encode("utf-8") + b"\0")
        return self.offsets[value]

    def add(self, values: list[int | str], previous_ids: set[int]) -> None:
        if len(values) != self.fields:
            raise ValueError("Wrong output field count")
        ident = int(values[0])
        if ident in self.managed:
            raise ValueError(f"Duplicate generated ID {ident}")
        if ident not in previous_ids and any(struct.unpack_from("<I", r)[0] == ident for r in self.records):
            raise ValueError(f"Requested ID {ident} already belongs to another record")
        packed = [self.string_offset(v) if isinstance(v, str) else v & 0xffffffff for v in values]
        self.managed[ident] = struct.pack("<" + "I" * self.fields, *packed)

    def encoded(self, previous_ids: set[int]) -> bytes:
        body = []
        emitted = set()
        for record in self.records:
            ident = struct.unpack_from("<I", record)[0]
            if ident in previous_ids:
                # A record we generated before: replace it where it sits (or
                # drop it when the variant is gone) so a no-change run is
                # byte-identical to its input. Appending every managed row to
                # the end instead reordered the last 35 Item.dbc records - the
                # wings before the unidentified shells - on every run.
                if ident in self.managed:
                    body.append(self.managed[ident])
                    emitted.add(ident)
                continue
            body.append(record)
        # New ids (a variant added since the last manifest) go after the records
        # already in the file, in ascending id order.
        body.extend(self.managed[k] for k in sorted(set(self.managed) - emitted))
        return struct.pack("<4s4I", b"WDBC", len(body), self.fields, self.fields * 4, len(self.strings)) + b"".join(body) + bytes(self.strings)


# The numeric tunables and the column each one reads, in the order the shipped
# manifest lists them.
WING_NUMERIC = (("hue_degrees", "hue_degrees"),
                ("saturation", "saturation_multiplier"),
                ("scale", "scale_multiplier"))


def manifest_number(value: float) -> str:
    """Render a float the way the committed manifest does: a whole number has
    no decimal part (0, 1, 45), a fraction keeps it (1.5). str() writes 0.0/1.0
    and rewrites the manifest on every unchanged run."""
    return str(int(value)) if value == int(value) else repr(value)


def read_variants(path: Path | None = None) -> list[dict[str, str]]:
    path = path or DATA
    with path.open(encoding="utf-8-sig", newline="") as stream:
        variants = list(csv.DictReader(stream))
    if not variants:
        raise ValueError("No wing variants configured")
    for field in ("key", "item_entry", "spell_id", "visual_id", "kit_id", "effect_id", "attach_id"):
        if len({r[field] for r in variants}) != len(variants):
            raise ValueError(f"Duplicate wing {field}")
    ordered = []
    for row in variants:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", row["key"]):
            raise ValueError("Invalid wing key")
        if row["recolor_mode"] not in {"original", "hue"}:
            raise ValueError("Unknown recolor mode")
        numbers = {column: tunable_value('ui', f"wing_{row['key']}_{suffix}")
                   for column, suffix in WING_NUMERIC}
        if not 0 <= numbers["hue_degrees"] < 360 or not 0 <= numbers["saturation"] <= 1 \
                or not 0 < numbers["scale"] <= 100:
            raise ValueError("Invalid wing color or scale")
        # Rebuild the row in the manifest's fixed order, with the numeric cells
        # after recolor_mode where the sheet and the committed manifest put
        # them. Appending them would reorder the file on every run.
        fields = {}
        for column, value in row.items():
            fields[column] = value
            if column == "recolor_mode":
                for number_column, _ in WING_NUMERIC:
                    fields[number_column] = manifest_number(numbers[number_column])
        ordered.append(fields)
    return ordered


def renamed_model(model: bytes, stem: str, texture_name: str) -> bytes:
    if model[:4] != b"MD20" or struct.unpack_from("<I", model, 4)[0] != 264:
        raise ValueError("Expected supplied WotLK M2")
    output = bytearray(model)

    def append_name(value: str) -> tuple[int, int]:
        encoded = value.encode("ascii") + b"\0"
        location = len(output)
        output.extend(encoded)
        return len(encoded), location

    struct.pack_into("<II", output, 8, *append_name(stem))
    count, offset = struct.unpack_from("<II", model, 80)
    if count != 3:
        raise ValueError("Source texture layout changed")
    for i, name in enumerate((texture_name, "D3AngelWing_Alpha1.blp", "D3AngelWing_Alpha2.blp")):
        struct.pack_into("<II", output, offset + i * 16 + 8, *append_name(MODEL_PREFIX + name))
    return bytes(output)


def recolor_blp_dxt3(source: bytes, hue_degrees: float, saturation: float) -> bytes:
    """Change RGB565 endpoints only; keep all alpha and block indices exact.

    The supplied BLP2 uses DXT3: 8 explicit-alpha bytes followed by 2 RGB565
    endpoints and 4 color-index bytes per block. Recolor every mip level in
    place, avoiding a lossy decode/recompression round trip. The designer explicitly
    requested scripted recoloring of the existing textures on 2026-09-08.
    """
    magic, kind, encoding, depth, alpha_encoding, mipmaps, width, height = struct.unpack_from("<4sI4BII", source)
    if (magic, kind, encoding, depth, alpha_encoding) != (b"BLP2", 1, 2, 8, 1):
        raise ValueError("Expected the supplied BLP2/DXT3 texture format")
    if not width or not height or not mipmaps:
        raise ValueError("Expected a mipmapped texture")
    offsets = struct.unpack_from("<16I", source, 20)
    lengths = struct.unpack_from("<16I", source, 84)
    output = bytearray(source)
    converted = {}

    def endpoint(value: int) -> int:
        if value not in converted:
            r, g, b = ((value >> 11) & 31) / 31, ((value >> 5) & 63) / 63, (value & 31) / 31
            _, old_saturation, brightness = colorsys.rgb_to_hsv(r, g, b)
            nr, ng, nb = colorsys.hsv_to_rgb(hue_degrees / 360, old_saturation * saturation, brightness)
            converted[value] = (round(nr * 31) << 11) | (round(ng * 63) << 5) | round(nb * 31)
        return converted[value]

    previous_end = 148
    levels = 0
    for level, (offset, length) in enumerate(zip(offsets, lengths)):
        if not offset and not length:
            continue
        w, h = max(1, width >> level), max(1, height >> level)
        expected = ((w + 3) // 4) * ((h + 3) // 4) * 16
        if offset < previous_end or length != expected or offset + length > len(source):
            raise ValueError(f"Invalid or overlapping BLP mip level {level}")
        previous_end = offset + length
        levels += 1
        for block in range(offset, offset + length, 16):
            c0, c1 = struct.unpack_from("<HH", source, block + 8)
            struct.pack_into("<HH", output, block + 8, endpoint(c0), endpoint(c1))
    if levels != max(width, height).bit_length():
        raise ValueError("Incomplete source mip chain")
    return bytes(output)


def sql_columns() -> list[tuple[str, str]]:
    text = (ROOT / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql").read_text(encoding="utf-8")
    definition = text.split("CREATE TABLE `spell_dbc` (", 1)[1].split("\n)", 1)[0]
    columns = re.findall(r"^\s*`([^`]+)`\s+([^\n]+)", definition, re.M)
    if len(columns) != 234:
        raise ValueError("Unexpected spell_dbc schema")
    return columns


def sql_value(value: int | str, definition: str) -> str:
    if isinstance(value, str):
        return "CONVERT(0x" + value.encode("utf-8").hex() + " USING utf8mb4)" if value else "''"
    if definition.startswith("float"):
        return format(struct.unpack("<f", struct.pack("<I", value & 0xffffffff))[0], ".9g")
    if value >= 0x80000000 and "unsigned" not in definition:
        value -= 0x100000000
    return str(value)


def generate(migration: Path | None = None) -> dict:
    updates = ROOT / "mod-diablocraft/data/sql/db-world/updates"
    migration = Path(migration) if migration else updates / "cosmetics_0001_wings.sql"
    # Validate before any read or write: a migration the updater never reads
    # would publish the companions without a DB change.
    require_companion_migration(ROOT / "mod-diablocraft", migration, updates)
    variants = read_variants()
    source = json.loads((SOURCE / "source-records.json").read_text(encoding="utf-8"))
    previous = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"dbc_ids": {}}
    layouts = {"Spell.dbc": 234, "SpellVisual.dbc": 32, "SpellVisualKit.dbc": 38, "SpellVisualEffectName.dbc": 7, "SpellVisualKitModelAttach.dbc": 10, "Item.dbc": 8, "ItemDisplayInfo.dbc": 25}
    dbcs = {name: DBC(CLIENT / name if (CLIENT / name).exists() else BASE / name, fields) for name, fields in layouts.items()}
    previous_ids = {name: set(previous["dbc_ids"].get(name, [])) for name in layouts}
    # Resolve source references against the actual local DBCs, not memory.
    stock_spells = DBC(BASE / "Spell.dbc", 234)
    icon_id = stock_spells.row(31884)[133]  # Verified Avenging Wrath icon source.
    icons = DBC(BASE / "SpellIcon.dbc", 2)
    icon = icons.text(icons.row(icon_id)[1]).replace("\\", "/").split("/")[-1]
    durations = DBC(BASE / "SpellDuration.dbc", 4)
    infinite = [struct.unpack("<4I", r)[0] for r in durations.records if struct.unpack("<4I", r)[1:] == (0xffffffff, 0, 0xffffffff)]
    if not infinite:
        raise ValueError("No permanent aura duration in source DBC")
    range_id = stock_spells.row(43024)[46]  # Supplied pack's self-aura carrier.
    assets: dict[str, bytes] = {}
    for name in ("D3AngelWing_Alpha1.blp", "D3AngelWing_Alpha2.blp"):
        assets[name] = (SOURCE / name).read_bytes()
    spells = []
    items = []
    displays = set()
    for row in variants:
        ids = {k: int(row[k]) for k in ("item_entry", "spell_id", "visual_id", "kit_id", "effect_id", "attach_id", "display_id")}
        stem = "DCAngelicWing_" + row["key"]
        texture = (SOURCE / "D3AngelWing_Red.blp").read_bytes()
        if row["recolor_mode"] != "original":
            texture = recolor_blp_dxt3(texture, float(row["hue_degrees"]), float(row["saturation"]))
        assets[stem + ".blp"] = texture
        assets[stem + ".m2"] = renamed_model((SOURCE / "D3AngelWing_Red.m2").read_bytes(), stem, stem + ".blp")
        assets[stem + "00.skin"] = (SOURCE / "D3AngelWing_Red00.skin").read_bytes()
        for name, id_key in (("SpellVisual.dbc", "visual_id"), ("SpellVisualKit.dbc", "kit_id"), ("SpellVisualEffectName.dbc", "effect_id"), ("SpellVisualKitModelAttach.dbc", "attach_id")):
            values = source[name].copy()
            values[0] = ids[id_key]
            if name == "SpellVisual.dbc":
                values[4] = ids["kit_id"]
            elif name == "SpellVisualEffectName.dbc":
                values[1:3] = [row["name"], MODEL_PREFIX + stem + ".mdx"]
                values[4] = struct.unpack("<I", struct.pack("<f", float(row["scale"])))[0]
            elif name == "SpellVisualKitModelAttach.dbc":
                values[1:3] = [ids["kit_id"], ids["effect_id"]]
            dbcs[name].add(values, previous_ids[name])
        spell: list[int | str] = [0] * 234
        for field in SPELL_STRING_FIELDS:
            spell[field] = ""
        spell[0] = ids["spell_id"]
        # SharedDefines.h: mounted casts + no right-click cancel; normal aura
        # (not PASSIVE, which Aura::CanBeSentToClient would hide).
        spell[4] = 0x01000000 | 0x80000000
        spell[7] = 0x00100000  # SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD.
        spell[28] = stock_spells.row(43024)[28]
        spell[40] = min(infinite)
        spell[46] = range_id
        spell[68] = -1  # No equipped-item class restriction.
        spell[71], spell[86], spell[95] = 6, 1, 4  # APPLY_AURA, caster, DUMMY.
        spell[131], spell[133], spell[136] = ids["visual_id"], icon_id, row["name"]
        spell[170] = "Cosmetic wings. Equip the shirt to display them."
        spell[187] = "Cosmetic wings."
        spell[225] = 1  # Physical school; there is no damage effect.
        dbcs["Spell.dbc"].add(spell, previous_ids["Spell.dbc"])
        spells.append(spell)
        item = [ids["item_entry"], 4, 0, -1, -1, ids["display_id"], 4, 0]
        dbcs["Item.dbc"].add(item, previous_ids["Item.dbc"])
        items.append((row["name"], ids))
        if ids["display_id"] not in displays:
            display: list[int | str] = [0] * 25
            display[0], display[5] = ids["display_id"], icon
            dbcs["ItemDisplayInfo.dbc"].add(display, previous_ids["ItemDisplayInfo.dbc"])
            displays.add(ids["display_id"])
    columns = sql_columns()
    sql = ["-- Generated by generate_wings.py from wing_variants.csv; do not hand-edit.", "-- tunables: cosmetic shirts, no stats, no vendor price, level 1, bind on pickup.", "SET NAMES utf8mb4;", "START TRANSACTION;"]
    spell_ids = ",".join(str(s[0]) for s in spells)
    sql.append(f"DELETE FROM `spell_dbc` WHERE `ID` IN ({spell_ids});")
    sql.append("INSERT INTO `spell_dbc` (" + ",".join("`" + c[0] + "`" for c in columns) + ") VALUES")
    sql.append(",\n".join("(" + ",".join(sql_value(v, columns[i][1]) for i, v in enumerate(spell)) + ")" for spell in spells) + ";")
    item_columns = ["entry", "class", "subclass", "SoundOverrideSubclass", "name", "displayid", "Quality", "BuyCount", "BuyPrice", "SellPrice", "InventoryType", "AllowableClass", "AllowableRace", "ItemLevel", "RequiredLevel", "stackable", "armor", "bonding", "Material", "spellid_1", "spelltrigger_1", "spellcharges_1", "spellcooldown_1", "spellcategorycooldown_1", "description"]
    item_rows = []
    for name, ids in items:
        values = [ids["item_entry"], 4, 0, -1, name, ids["display_id"], 1, 1, tunable_integer("economy", "wing_shirt_vendor_gold"), tunable_integer("economy", "wing_shirt_vendor_gold"), 4, -1, -1, tunable_integer("ui", "wing_shirt_level", minimum=1), tunable_integer("ui", "wing_shirt_level", minimum=1), tunable_integer("ui", "wing_shirt_stack_count", minimum=1), 0, 1, -1, ids["spell_id"], 1, 0, -1, -1, "Cosmetic wings. No combat bonuses."]
        item_rows.append("(" + ",".join(sql_value(v, "int") for v in values) + ")")
    sql.append("INSERT INTO `item_template` (" + ",".join("`" + c + "`" for c in item_columns) + ") VALUES")
    sql.append(",\n".join(item_rows) + "\nON DUPLICATE KEY UPDATE " + ",".join(f"`{c}`=VALUES(`{c}`)" for c in item_columns[1:]) + ";")
    sql.append("COMMIT;")
    encoded = {name: dbc.encoded(previous_ids[name]) for name, dbc in dbcs.items()}
    manifest = {"source_archive_sha256": source["archive_sha256"], "variants": variants, "dbc_ids": {name: sorted(dbc.managed) for name, dbc in dbcs.items()}, "asset_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(assets.items())}}
    sql_bytes = ("\n".join(sql) + "\n").encode("utf-8")
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    # The SQL migration goes through the applied-state guard. The client DBCs,
    # the art, the manifest and the generated mirror are companion outputs
    # (decisions.md 2026-09-23, F2): they may follow a changed sheet only with a
    # new migration carrying the same change, so they are held back when this
    # migration is applied and its render differs.
    module = ROOT / "mod-diablocraft"
    coupled = [(CLIENT / name, payload) for name, payload in encoded.items()]
    coupled += [(ART / name, payload) for name, payload in assets.items()]
    coupled += [(module / "data/generated/cosmetic_wings.sql", sql_bytes), (MANIFEST, manifest_bytes)]
    write_migration(module, migration, sql_bytes)
    write_coupled_outputs(module, migration, sql_bytes, coupled,
                          label='Wing client DBCs, art, manifest and generated mirror')
    print(f"Wings: generated {len(variants)} cosmetic shirts, spells and models; {len(assets)} assets; existing non-wing DBC rows preserved")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration", type=Path)
    args = parser.parse_args()
    generate(args.migration)
