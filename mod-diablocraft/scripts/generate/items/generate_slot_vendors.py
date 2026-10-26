#!/usr/bin/env python3
"""Generate the legendary slot vendors (diablocraft-y2gt, docs/proposals/kadala.md section 6, Part 7).

    python3 mod-diablocraft/scripts/generate/items/generate_slot_vendors.py

Sources: slot_vendors.csv (one vendor per slot), base_items.csv, base_item_ids.csv, set_classes.csv, class_map.csv and
bounty_cache_legendaries.csv. One migration writes (slot_vendors_0001.sql, applied; slot_vendors_0002.sql since
diablocraft-dm9vg.8, the same render without the Horadric Cache's legendaries, applied on dev; slot_vendors_0004.sql since
diablocraft-ngybv, the same render with the Necromancer playable, applied on dev; slot_vendors_0005.sql since
diablocraft-jfd7p, with the Crusader playable too, applied on dev; slot_vendors_0006.sql since diablocraft-vawmy.4, with the
Demon Hunter playable too, applied on dev; slot_vendors_0007.sql since diablocraft-jjug3, with the
Witch Doctor playable too; slot_vendors_0008.sql since diablocraft-xnrvn.3, with the Shaman's Ritual Mace legendary):

  * dc_slot_vendor: which creatures are slot vendors (the buy hook reads it; the slot is for the tests);
  * each vendor's creature_template and model (a clone of the donor's, vendor flag only; the designer places and dresses it);
  * its npc_vendor rows: every current-pool legendary and set item of its slot that a playable class can wear
    (6.7.1 a), by name, A to Z, free (no ExtendedCost), except the Horadric Cache's legendaries, which come only
    from the cache (the designer, decisions 2026-10-12 (1));
  * one stock NPC_VENDOR condition per entry that has a level (6.7.2 b): the player's level at or above it, which
    hides the entry from the list and refuses it at the buy.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
from class_names import item_key  # noqa: E402
from generate_rifts import quote  # noqa: E402
from generate_sql import base_wear_mask, read_base_item_ids  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
NAME = "slot_vendors_0008.sql"
# Constants (identities, not tunables): the core's list stops sending at 150 entries (Creature.h MAX_VENDOR_ITEMS);
# conditions.SourceTypeOrReferenceId 23 is CONDITION_SOURCE_TYPE_NPC_VENDOR, ConditionTypeOrReference 27 is
# CONDITION_LEVEL and ConditionValue2 3 is COMP_TYPE_HIGH_EQ (ConditionMgr.h, Util.h).
MAX_VENDOR_ITEMS = 150
SOURCE_NPC_VENDOR, CONDITION_LEVEL, COMP_HIGH_EQ = 23, 27, 3
VENDOR_COLUMNS = {"entry", "name", "slot", "clone_entry", "level", "npcflag", "source"}


def read(name, directory):
    with (directory / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def listed(directory=None):
    """{vendor entry: [(item entry, d3_name, level or 0)]} in list order, with the vendor rows.

    A base is listed when it is a current-pool legendary or set item (the 254 older versions and the Ethereals are
    not, 6.7.1) and some playable class can wear it: its own class lists, a set piece kept to its set's class, as
    items_0011 and items_0020 write AllowableClass. Blacksmith-crafted sets are listed: here they are free.
    """
    d3 = directory or MODULE / "data/d3"
    vendors = read("slot_vendors.csv", d3)
    if not vendors or set(vendors[0]) != VENDOR_COLUMNS:
        raise ValueError(f"slot_vendors.csv: expected the columns {sorted(VENDOR_COLUMNS)}")
    bases = read("base_items.csv", d3)
    ids = read_base_item_ids(d3 / "base_item_ids.csv", {r["d3_id"] for r in bases})
    bits = {item_key(r["d3_class"]): 1 << (int(r["wow_class_id"]) - 1) for r in read("class_map.csv", d3)}
    set_class = {r["set_name"]: r["class_key"] for r in read("set_classes.csv", d3)}
    cache_only = {int(r["item_entry"]) for r in read("bounty_cache_legendaries.csv", d3)}
    slots = [v["slot"] for v in vendors]
    if len(set(slots)) != len(slots) or len({v["entry"] for v in vendors}) != len(vendors):
        raise ValueError("slot_vendors.csv: a slot or an entry twice")
    lists = {v["slot"]: [] for v in vendors}
    for row in bases:
        if row["rarity"] not in ("legendary", "set") or row["pool_version"] != "yes":
            continue
        if ids[row["d3_id"]] in cache_only:
            continue  # the cache's own (dm9vg.8)
        mask = base_wear_mask(row, bits)
        if row["rarity"] == "set":
            if row["set_name"] not in set_class:
                raise ValueError(f"set_classes.csv has no row for the set {row['set_name']!r}")
            key = set_class[row["set_name"]]
            if key:
                mask = bits.get(key, 0) if mask == -1 else mask & bits.get(key, 0)
        if mask == 0:
            continue  # no playable class can wear it yet; it joins by itself when its class does
        if row["slot"] not in lists:
            raise ValueError(f"{row['d3_name']}: no slot vendor for slot {row['slot']!r}")
        level = int(row["item_level"]) if row["item_level"] else 0
        lists[row["slot"]].append((ids[row["d3_id"]], row["d3_name"], level))
    out = {}
    for v in vendors:
        # A to Z as a player reads it, case aside: "Crown of the Invoker" before "Crown of Valor" (diablocraft-jfd7p).
        items = sorted(lists[v["slot"]], key=lambda i: (i[1].casefold(), i[1], i[0]))
        if not items:
            raise ValueError(f"{v['name']}: nothing to list")
        if len(items) > MAX_VENDOR_ITEMS:
            raise ValueError(f"{v['name']}: {len(items)} entries, the core sends only {MAX_VENDOR_ITEMS} to a window")
        if len({name for _, name, _ in items}) != len(items):
            raise ValueError(f"{v['name']}: two entries share a name")
        out[int(v["entry"])] = items
    return vendors, out


def render(directory=None):
    vendors, lists = listed(directory)
    ids = ",".join(str(int(v["entry"])) for v in vendors)
    donors = {int(v["clone_entry"]) for v in vendors}
    if len(donors) != 1:
        raise ValueError("slot_vendors.csv: one donor creature for all")
    donor = donors.pop()
    entries = ",\n".join(f"({int(v['entry'])}, {quote(v['slot'])})" for v in vendors)
    creatures = []
    for v in vendors:
        entry, level, flag = int(v["entry"]), int(v["level"]), int(v["npcflag"])
        creatures.append(
            f"UPDATE dc_slot_vendor_template SET entry={entry}, name={quote(v['name'])}, subname='', minlevel={level}, "
            f"maxlevel={level}, npcflag={flag}, gossip_menu_id=0, ScriptName='', AIName='';\n"
            f"INSERT INTO `creature_template` SELECT * FROM dc_slot_vendor_template;\n"
            f"INSERT INTO `creature_template_model` SELECT {entry}, `Idx`, `CreatureDisplayID`, `DisplayScale`, "
            f"`Probability`, `VerifiedBuild` FROM `creature_template_model` WHERE `CreatureID`={donor};")
    rows, conditions = [], []
    for vendor, items in lists.items():
        for position, (item, name, level) in enumerate(items):
            rows.append(f"({vendor}, {position}, {item}, 0, 0, 0, 0)")
            if level:
                conditions.append(f"({SOURCE_NPC_VENDOR}, {vendor}, {item}, 0, 0, {CONDITION_LEVEL}, 0, {level}, "
                                  f"{COMP_HIGH_EQ}, 0, 0, 0, 0, '', {quote('slot vendor: from level ' + str(level))})")
    return f"""-- Generated by generate_slot_vendors.py from slot_vendors.csv, base_items.csv, set_classes.csv and bounty_cache_legendaries.csv (diablocraft-y2gt, dm9vg.8); never edit.
-- The legendary slot vendors: creatures, lists (free, A to Z) and the level conditions. Until release (diablocraft-y2gt, plan section 6.7.2).
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_slot_vendor` (
  `entry` INT UNSIGNED NOT NULL,
  `slot` VARCHAR(32) NOT NULL,
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `dc_slot_vendor`;
INSERT INTO `dc_slot_vendor` (`entry`, `slot`) VALUES
{entries};
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId`={SOURCE_NPC_VENDOR} AND `SourceGroup` IN ({ids});
DELETE FROM `npc_vendor` WHERE `entry` IN ({ids});
DELETE FROM `creature_template_model` WHERE `CreatureID` IN ({ids});
DELETE FROM `creature_template` WHERE `entry` IN ({ids});
CREATE TEMPORARY TABLE dc_slot_vendor_template LIKE creature_template;
INSERT INTO dc_slot_vendor_template SELECT * FROM creature_template WHERE entry={donor};
{chr(10).join(creatures)}
DROP TEMPORARY TABLE dc_slot_vendor_template;
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`) VALUES
{",\n".join(rows)};
INSERT INTO `conditions` (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`,
  `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`, `ConditionValue3`,
  `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`) VALUES
{",\n".join(conditions)};
"""


def generate():
    sql = render()
    target = MODULE / "data/sql/db-world/updates" / NAME
    write_migration(MODULE, target, sql)
    write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / NAME, sql)], label="slot vendor rows")
    print(f"Generated {NAME}")


if __name__ == "__main__":
    generate()
