#!/usr/bin/env python3
"""Fill the UNSURE range/radius cells in skill_targeting.csv from Spell.dbc.

The D3 tooltips do not state a range for ten of the 23 skills. Rather than
invent numbers, each of those takes the value from the WoW spell that
barbarian_visuals.csv already maps it to - the same spell whose animation and
icon the shell copies (04-classes §6), so the reach matches what the player sees.

Run from the repo root:

    python mod-diablocraft/scripts/fill_skill_targeting.py

Writes skill_targeting.csv in place and prints every substitution. Cells that
were already numeric are never touched, so rerunning is a no-op.
"""

import csv
import struct
import sys
from pathlib import Path

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 129, 46, 92, 20, 12, 16, 8, 4): Spell.dbc field indices and DBC header/record offsets; Client file format.

MODULE_ROOT = Path(__file__).resolve().parents[1]
DBC_DIR = MODULE_ROOT.parents[0] / "azerothcore-wotlk/build/server/data/dbc"
TARGETING = MODULE_ROOT / "data/d3/skill_targeting.csv"
VISUALS = MODULE_ROOT / "data/d3/barbarian_visuals.csv"

# Field positions inside a Spell.dbc record, taken from the column order of
# azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql (234 columns, 1:1 with
# the DBC's 234 fields; 17 columns per localized string).
FIELD_RANGE_INDEX = 46          # RangeIndex
FIELD_RADIUS_INDEX_1 = 92       # EffectRadiusIndex_1


def load_dbc(name):
    data = (DBC_DIR / name).read_bytes()
    magic, records, fields, record_size, _ = struct.unpack("<4sIIII", data[:20])
    if magic != b"WDBC":
        raise SystemExit(f"{name}: not a WDBC file")
    body = data[20:20 + records * record_size]
    rows = {}
    for index in range(records):
        record = body[index * record_size:(index + 1) * record_size]
        rows[struct.unpack("<I", record[:4])[0]] = record
    return rows, fields


def uint(record, field):
    return struct.unpack("<I", record[field * 4:field * 4 + 4])[0]


def main():
    if not DBC_DIR.is_dir():
        raise SystemExit(f"{DBC_DIR}: not found. Extract the client DBCs first.")
    spells, _ = load_dbc("Spell.dbc")
    ranges, _ = load_dbc("SpellRange.dbc")
    radii, _ = load_dbc("SpellRadius.dbc")

    visuals = {}
    with VISUALS.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["wow_spell_id"]:
                visuals[row["d3_skill"]] = (int(row["wow_spell_id"]), row["wow_spell_name"])

    with TARGETING.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames
        rows = list(reader)
    if "source_spell_id" not in header:
        header = header + ["source_spell_id"]

    changed = 0
    for row in rows:
        row.setdefault("source_spell_id", "")
        skill = row["skill"]
        needs = [column for column in ("range_yards", "radius_yards") if row[column] == "UNSURE"]
        if not needs:
            continue
        if skill not in visuals:
            print(f"  {skill}: no mapped WoW spell, left UNSURE")
            continue
        spell_id, spell_name = visuals[skill]
        record = spells.get(spell_id)
        if record is None:
            raise SystemExit(f"{skill}: spell {spell_id} is not in Spell.dbc")
        for column in needs:
            if column == "range_yards":
                entry = ranges.get(uint(record, FIELD_RANGE_INDEX))
                # SpellRange: ID, MinHostile, MinFriend, MaxHostile, MaxFriend, Flags
                value = struct.unpack("<f", entry[12:16])[0] if entry else None
            else:
                entry = radii.get(uint(record, FIELD_RADIUS_INDEX_1))
                # SpellRadius: ID, Radius, RadiusPerLevel, RadiusMax
                value = struct.unpack("<f", entry[4:8])[0] if entry else None
            if not value:
                print(f"  {skill}: {spell_name} has no {column}, left UNSURE")
                continue
            row[column] = f"{value:g}"
            row["source_spell_id"] = str(spell_id)
            print(f"  {skill}: {column} = {value:g} from {spell_name} ({spell_id})")
            changed += 1
        row["unsure"] = ";".join(part for part in row["unsure"].split(";")
                                 if part and row[part + "_yards"] == "UNSURE")

    with TARGETING.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"filled {changed} cell(s) in {TARGETING.name}")


if __name__ == "__main__":
    main()
