#!/usr/bin/env python3
"""Generate the client-side chain beam rows for Fire Chains and Health Link.

13-elite-affixes S7/S10 and docs/test-affix-round-two.md section 8. The two
affixes are paired dummy auras (generate_spells.py owns the Spell.dbc rows); the
client draws the beam from the aura's caster to the unit it is on when the
spell's SpellVisual carries a SpellVisualKit whose Chain charProc names a
SpellChainEffects row. This script appends those three client rows per affix.

Every stock record is preserved byte for byte. SpellVisual and SpellVisualKit
have regular WDBC records; SpellChainEffects.dbc does not (its record size is
not fields*4 - the client parses a packed layout), so its owned rows are cloned
byte for byte from a stock row and only the id is rewritten.

Run after generate_spells.py, which also calls this. Data:
data/d3/chain_beam_visuals.csv. Output: client-patch/dbc/ plus
client-patch/chain-beams-manifest.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_wings import DBC

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "mod-diablocraft/data/d3/chain_beam_visuals.csv"
BASE = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CLIENT = ROOT / "client-patch/dbc"
MANIFEST = ROOT / "client-patch/chain-beams-manifest.json"

LAYOUTS = {"SpellVisual.dbc": 32, "SpellVisualKit.dbc": 38}
# SpellVisualKit.dbc 3.3.5a packed layout (wowdev): charProc[4] then four
# charParam quads. The Chain proc uses charProc[0]=12, paramZero[0]=chain id,
# paramOne[0]=targetCount and paramTwo[0]=forever.
KIT_CHAR_PROC, KIT_PARAM_ZERO, KIT_PARAM_ONE, KIT_PARAM_TWO = 17, 21, 25, 29
# SpellVisual.dbc: StateKit is drawn for as long as the aura is on the unit.
VIS_STATE_KIT = 4
CHAIN_PROC = 12
TARGET_COUNT = 1
# SpellChainEffects.dbc 3.3.5a: m_Texture is the eighth field, at 0x1C. The
# record is packed (its size is not fields*4), so fields must be read at their
# documented byte offsets, never by scanning for anything that looks like one.
CHAIN_TEXTURE_OFFSET = 0x1C


def float_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def records_by_id(records: list[bytes]) -> dict[int, bytes]:
    return {struct.unpack_from("<I", record)[0]: record for record in records}


def merge_records(records: list[bytes], managed: dict[int, bytes],
                  owned: set[int]) -> list[bytes]:
    """Preserved records plus the owned ones, kept ordered by id."""
    body = [r for r in records if struct.unpack_from("<I", r)[0] not in owned]
    body.extend(managed[ident] for ident in sorted(managed))
    body.sort(key=lambda r: struct.unpack_from("<I", r)[0])
    return body


def encode_records(records: list[bytes], fields: int, size: int,
                   strings: bytes) -> bytes:
    return (struct.pack("<4s4I", b"WDBC", len(records), fields, size, len(strings))
            + b"".join(records) + strings)


class ChainEffectsDBC:
    """SpellChainEffects.dbc: preserve non-owned records and clone owned ones."""

    def __init__(self, path: Path):
        raw = path.read_bytes()
        magic, count, fields, size, string_size = struct.unpack_from("<4s4I", raw)
        if magic != b"WDBC" or len(raw) != 20 + count * size + string_size:
            raise ValueError(f"{path}: unexpected SpellChainEffects layout")
        self.fields, self.size = fields, size
        self.records = [raw[20 + i * size:20 + (i + 1) * size] for i in range(count)]
        self.strings = raw[20 + count * size:]
        self.managed: dict[int, bytes] = {}

    def clone(self, source_id: int, new_id: int, owned: set[int]) -> bytes:
        existing = records_by_id(self.records)
        if source_id not in existing:
            raise ValueError(f"SpellChainEffects.dbc has no source row {source_id}")
        if new_id in self.managed:
            raise ValueError(f"Duplicate generated chain id {new_id}")
        if new_id not in owned and new_id in existing:
            raise ValueError(f"Chain id {new_id} already belongs to another record")
        record = bytearray(existing[source_id])
        struct.pack_into("<I", record, 0, new_id)
        self.managed[new_id] = bytes(record)
        return record

    def texture(self, record: bytes) -> str:
        value = struct.unpack_from("<I", record, CHAIN_TEXTURE_OFFSET)[0]
        if not value or value >= len(self.strings):
            return ""
        end = self.strings.find(b"\x00", value)
        if end < 0:
            return ""
        return self.strings[value:end].decode("utf-8", "replace")


def read_beams() -> list[dict[str, str]]:
    with DATA.open(encoding="utf-8-sig", newline="") as stream:
        beams = list(csv.DictReader(stream))
    if not beams:
        raise ValueError("chain_beam_visuals.csv is empty")
    for field in ("key", "spell_id", "visual_id", "kit_id", "chain_id"):
        if len({row[field] for row in beams}) != len(beams):
            raise ValueError(f"Duplicate {field} in chain_beam_visuals.csv")
    for row in beams:
        for field in ("spell_id", "visual_id", "kit_id", "chain_id",
                      "chain_template", "kit_template", "visual_template"):
            if not row[field].isdigit() or int(row[field]) <= 0:
                raise ValueError(f"{row['key']}: {field} must be a positive integer")
        if float(row["forever"]) < 0:
            raise ValueError(f"{row['key']}: forever cannot be negative")
    return beams


def source(name: str) -> DBC:
    """The input table: the patched client table when it exists, else stock."""
    path = CLIENT / name
    return DBC(path if path.exists() else BASE / name, LAYOUTS[name])


def generate() -> dict:
    beams = read_beams()
    previous = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    owned = {key: set(previous.get(key, [])) for key in
             ("spell_ids", "visual_ids", "kit_ids", "chain_ids")}
    # Ids are still regenerated from the CSV if a stale manifest lost them.
    owned["spell_ids"] |= {int(row["spell_id"]) for row in beams}
    owned["visual_ids"] |= {int(row["visual_id"]) for row in beams}
    owned["kit_ids"] |= {int(row["kit_id"]) for row in beams}
    owned["chain_ids"] |= {int(row["chain_id"]) for row in beams}

    visual, kit = source("SpellVisual.dbc"), source("SpellVisualKit.dbc")
    chain = ChainEffectsDBC(CLIENT / "SpellChainEffects.dbc"
                            if (CLIENT / "SpellChainEffects.dbc").exists()
                            else BASE / "SpellChainEffects.dbc")
    templates = {
        "visual": DBC(BASE / "SpellVisual.dbc", 32),
        "kit": DBC(BASE / "SpellVisualKit.dbc", 38),
    }
    for row in beams:
        visual_id, kit_id = int(row["visual_id"]), int(row["kit_id"])
        values = templates["visual"].row(int(row["visual_template"]))
        values[0] = visual_id
        values[VIS_STATE_KIT] = kit_id
        visual.add(values, owned["visual_ids"])

        values = templates["kit"].row(int(row["kit_template"]))
        values[0] = kit_id
        values[KIT_CHAR_PROC] = CHAIN_PROC
        values[KIT_PARAM_ZERO] = float_bits(float(row["chain_id"]))
        values[KIT_PARAM_ONE] = float_bits(TARGET_COUNT)
        values[KIT_PARAM_TWO] = float_bits(float(row["forever"]))
        kit.add(values, owned["kit_ids"])

        record = chain.clone(int(row["chain_template"]), int(row["chain_id"]),
                             owned["chain_ids"])
        texture = chain.texture(record)
        if texture.lower() != row["chain_texture"].lower():
            raise ValueError(f"{row['key']}: stock chain {row['chain_template']} is "
                             f"{texture!r}, not {row['chain_texture']!r}")

    # Build the merged lists, verify every stock record survives byte for byte,
    # then encode. Nothing is written until all three tables are validated.
    merged_visual = merge_records(visual.records, visual.managed, owned["visual_ids"])
    merged_kit = merge_records(kit.records, kit.managed, owned["kit_ids"])
    merged_chain = merge_records(chain.records, chain.managed, owned["chain_ids"])
    checks = [
        (merged_visual, DBC(BASE / "SpellVisual.dbc", 32), owned["visual_ids"]),
        (merged_kit, DBC(BASE / "SpellVisualKit.dbc", 38), owned["kit_ids"]),
        (merged_chain, ChainEffectsDBC(BASE / "SpellChainEffects.dbc"), owned["chain_ids"]),
    ]
    for records, original, owned_ids in checks:
        read_back = records_by_id(records)
        for ident, record in records_by_id(original.records).items():
            if ident not in owned_ids and read_back.get(ident) != record:
                raise ValueError(f"stock record {ident} changed during generation")

    encoded = {
        "SpellVisual.dbc": encode_records(merged_visual, visual.fields,
                                          visual.fields * 4, bytes(visual.strings)),
        "SpellVisualKit.dbc": encode_records(merged_kit, kit.fields,
                                             kit.fields * 4, bytes(kit.strings)),
        "SpellChainEffects.dbc": encode_records(merged_chain, chain.fields,
                                                chain.size, chain.strings),
    }
    CLIENT.mkdir(parents=True, exist_ok=True)
    for name, payload in encoded.items():
        (CLIENT / name).write_bytes(payload)
    manifest = {
        "chain_ids": sorted(owned["chain_ids"]),
        "kit_ids": sorted(owned["kit_ids"]),
        "visual_ids": sorted(owned["visual_ids"]),
        "spell_ids": sorted(owned["spell_ids"]),
        "rows": [{key: row[key] for key in
                  ("key", "spell_id", "visual_id", "kit_id", "chain_id",
                   "chain_template", "chain_texture")} for row in beams],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"chain beams: generated {len(beams)} SpellVisual/SpellVisualKit/"
          f"SpellChainEffects row sets; existing client DBC rows preserved")
    for row in beams:
        print(f"  {row['key']}: spell {row['spell_id']}, visual {row['visual_id']}, "
              f"kit {row['kit_id']}, chain {row['chain_id']} ({row['chain_texture']})")
    return manifest


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()
