#!/usr/bin/env python3
"""Write the designer's monster model picks into data/d3/monster_family_models.csv, one row per roster monster.

monster-families.md section 4 step 3: each batch of picks is a data-only change. Run this with the
picks file (the CSV the picking page exports), then generate_monster_models.py.

A pick names a WotLK NPC whose look to copy. The row takes that NPC's whole display list from the
world database (every creature_template_model row, with its scale and probability) unless the designer pinned
one display, and checks each weapon id against the world item_template and the client's Item.dbc
(the core drops an unknown item id to 0 with a log error). A bow, crossbow, gun, thrown weapon or
wand goes to the ranged slot, whichever column the designer's page put it in. A monster with no pick keeps
its family's candidate list from the first reshape, with the first candidate as its placeholder.

The first run also reshapes the old file (3 or 4 candidates per family) into the new one: one row
per roster monster, the roster's order.

    python mod-diablocraft/scripts/import_monster_picks.py --picks <monster_model_picks.csv> \
        --mysql /usr/bin/mysql --defaults-file azerothcore-wotlk/build/mysql/client.cnf

Reads the world database; changes nothing in it.
"""

import argparse
import csv
import re
import struct
from pathlib import Path

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_area_copies import Database

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parent
CSV_PATH = MODULE_ROOT / "data/d3/monster_family_models.csv"
ROSTER_PATH = MODULE_ROOT / "data/d3/monster_roster.csv"
ITEM_DBC = REPO_ROOT / "client-patch/dbc/Item.dbc"

COLUMNS = ["family", "monster", "picked", "wow_creature_id", "wow_creature_name", "displays",
           "mainhand", "offhand", "ranged", "scale", "auras", "candidates", "notes", "source_url"]

# Constant, not a tunable: the ItemTemplate InventoryType of a bow, a thrown weapon and a gun, crossbow or wand
# (INVTYPE_RANGED 15, THROWN 25, RANGEDRIGHT 26); an engine enum.
RANGED_INVENTORY_TYPES = {15, 25, 26}


# Slugs the picks store may still hold for monsters renamed on 2026-10-08 (cards q-1007-07 and q-1008-01), old -> new.
RENAMED_SLUGS = {"night-clan-shaman": "moon-clan-shaman", "ice-clan-brawler": "ice-clan-warrior",
                 "bogan-beast": "tusked-bogan", "dune-wasp": "sand-wasp", "shade": "shade-stalker",
                 "plague-swarm": "stinging-swarm"}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def roster_row(by_slug, picked_slug):
    """The roster row for a slug the picks store sent, old or new; None when it is no roster monster."""
    return by_slug.get(RENAMED_SLUGS.get(picked_slug, picked_slug))


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def client_items(path=ITEM_DBC):
    """The ids in the client's Item.dbc (a WDBC file: records of 8 uint32, the id first)."""
    data = path.read_bytes()
    if data[:4] != b"WDBC":
        raise SystemExit(f"{path} is not a DBC file")
    records, _fields, size, _strings = struct.unpack("<4I", data[4:20])
    return {struct.unpack_from("<I", data, 20 + index * size)[0] for index in range(records)}


def reshape(old_rows, roster):
    """The old file's candidate rows -> one row per roster monster, unpicked."""
    candidates = {}
    for row in old_rows:
        candidates.setdefault(row["family"], []).append(row)
    rows = []
    for monster in roster:
        family = candidates[monster["family"]]
        first = family[0]
        rows.append({
            "family": monster["family"], "monster": monster["name"], "picked": "no",
            "wow_creature_id": first["wow_creature_id"], "wow_creature_name": first["wow_creature_name"],
            "displays": f"{first['wow_display_id']}:1:1", "mainhand": "", "offhand": "", "ranged": "",
            "scale": "", "notes": "placeholder: the family's first candidate",
            "candidates": ";".join(f"{row['wow_creature_id']}:{row['wow_display_id']}" for row in family),
            "source_url": first["source_url"]})
    return rows


def donor(db, npc_id, pinned):
    """(name, 'display:scale:probability;...') of the NPC's look, or only the pinned display."""
    name = db.query(f"SELECT name FROM creature_template WHERE entry={int(npc_id)}")
    models = db.query("SELECT CreatureDisplayID, DisplayScale, Probability FROM creature_template_model "
                      f"WHERE CreatureID={int(npc_id)} ORDER BY Idx")
    models = [tuple(line.split("\t")) for line in models]
    if pinned:
        own = [m for m in models if m[0] == pinned]
        scale = own[0][1] if own else "1"
        return (name[0] if name else ""), f"{pinned}:{float(scale):g}:1"
    if not name or not models:
        raise SystemExit(f"NPC {npc_id} is not in creature_template_model; pin a display for it")
    return name[0], ";".join(f"{d}:{float(s):g}:{float(p):g}" for d, s, p in models)


def weapons(db, known, picked, monster):
    """(mainhand, offhand, ranged) item ids as text; every id must exist in both sources."""
    slots = {"mainhand": "", "offhand": "", "ranged": ""}
    for column in ("mainhand", "offhand"):
        item = picked[column].strip()
        if not item:
            continue
        if int(item) not in known:
            raise SystemExit(f"{monster}: item {item} is not in the client's Item.dbc")
        found = db.query(f"SELECT InventoryType FROM item_template WHERE entry={int(item)}")
        if not found:
            raise SystemExit(f"{monster}: item {item} is not in item_template")
        target = "ranged" if int(found[0]) in RANGED_INVENTORY_TYPES else column
        if slots[target]:
            raise SystemExit(f"{monster}: two items for the {target} slot")
        slots[target] = item
    return slots["mainhand"], slots["offhand"], slots["ranged"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--picks", required=True)
    parser.add_argument("--mysql", required=True)
    parser.add_argument("--defaults-file", required=True)
    parser.add_argument("--database", default="acore_world")
    args = parser.parse_args()

    roster = read_csv(ROSTER_PATH)
    rows = read_csv(CSV_PATH)
    if "wow_display_id" in rows[0]:
        rows = reshape(rows, roster)
    by_slug = {slug(row["monster"]): row for row in rows}
    db = Database(args.mysql, args.defaults_file, args.database)
    known = client_items()

    for pick in read_csv(args.picks):
        row = roster_row(by_slug, pick["monster_slug"])
        if row is None:
            raise SystemExit(f"{pick['monster_slug']} is not a roster monster")
        npc = pick["npc_id"].strip()
        if not npc:
            row["notes"] = pick["notes"].strip() or row["notes"]
            continue          # no pick for it (Decaying Cryptstalker has no WotLK look): stays a placeholder
        name, displays = donor(db, npc, pick["display"].strip())
        row["mainhand"], row["offhand"], row["ranged"] = weapons(db, known, pick, row["monster"])
        row.update({"picked": "yes", "wow_creature_id": npc, "wow_creature_name": name or "(not a WotLK NPC)",
                    "displays": displays, "scale": f"{float(pick['scale']):g}" if pick["scale"].strip() else "",
                    "auras": pick.get("auras", "").strip(),
                    "candidates": "", "notes": pick["notes"].strip(),
                    "source_url": f"https://wotlkdb.com/?npc={npc}" if name else ""})

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{sum(row['picked'] == 'yes' for row in rows)} of {len(rows)} monsters picked -> {CSV_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
