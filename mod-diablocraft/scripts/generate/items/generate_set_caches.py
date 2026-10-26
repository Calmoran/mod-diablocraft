#!/usr/bin/env python3
"""Generate the set caches and their vendor (diablocraft-bzr0, docs/proposals/kadala.md section 6.6, Part 8).

    python3 mod-diablocraft/scripts/generate/items/generate_set_caches.py

Sources: set_caches.csv (one cache item per set: its entry), set_cache_vendor.csv (the fourteenth vendor), and
everything generate_slot_vendors.py reads, because a cache holds exactly the set pieces the slot vendors list (6.6:
"a cache holds every listed piece"). One migration writes (set_caches_0001.sql, applied; set_caches_0002.sql since diablocraft-wna0c, the same render with the six
Monk sets' caches added, applied on dev; set_caches_0004.sql since diablocraft-ngybv, with the six Necromancer sets' too,
applied on dev; set_caches_0005.sql since diablocraft-jfd7p, with the six Crusader sets' too, applied on dev;
set_caches_0006.sql since diablocraft-vawmy.4, with the six Demon Hunter sets' too, applied on dev;
set_caches_0007.sql since diablocraft-jjug3, with the six Witch Doctor sets' too):

  * dc_set_cache and dc_set_cache_piece: which items are caches and what each opens into (the open hook reads them);
  * one item_template row per cache: named after the set, green, a plain miscellaneous item with the stock has-loot
    flag (the client draws <Right Click to Open> itself), no price, a description naming the pieces. The INSERT names its
    columns one row to a line, which is the shape client-patch/dbc/build_item.py reads for the cache icons (Part 9);
  * the vendor's creature_template and model (a clone of the donor's, vendor flag only; the designer places and dresses it);
  * its npc_vendor rows: every cache, by set name A to Z, free;
  * one stock NPC_VENDOR condition per cache whose set has a level (6.7.2 b): the player's level at or above it.

Nothing here is Kadala's: no Blood Shard, no price, no extended cost.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_slot_vendors as slot_vendors  # noqa: E402
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
from generate_rifts import quote  # noqa: E402
from generate_sql import ENTRY_BASE, SHELL_ENTRY_BASE, read_base_item_ids  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
NAME = "set_caches_0007.sql"
CACHE_COLUMNS = {"entry", "set_name", "source"}
VENDOR_COLUMNS = {"entry", "name", "clone_entry", "level", "npcflag", "source"}
# Constants (identities, not tunables): item_template.description is a 255-character column, ITEM_FLAG_HAS_LOOT is 4
# (ItemTemplate.h), and the cache is a copy of the stock Heavy Junkbox (16885): miscellaneous, material 1, the has-loot
# flag, the junkbox's display (client icon), minus its lock. Quality 2 is green, like the set pieces it holds.
MAX_DESCRIPTION = 255
HAS_LOOT_FLAG = 4
CLASS_MISC, SUBCLASS_JUNK, DISPLAY_ID, QUALITY_GREEN, MATERIAL = 15, 0, 15590, 2, 1


def pieces_by_set(directory=None):
    """{set name: [(item entry, d3_name, level or 0)]} of the set pieces the slot vendors list, A to Z."""
    d3 = directory or MODULE / "data/d3"
    _, lists = slot_vendors.listed(d3)
    bases = {r["d3_id"]: r for r in slot_vendors.read("base_items.csv", d3)}
    ids = read_base_item_ids(d3 / "base_item_ids.csv", set(bases))
    set_of = {ids[d3_id]: row["set_name"] for d3_id, row in bases.items() if row["rarity"] == "set"}
    out = {}
    for items in lists.values():
        for item in items:
            if item[0] in set_of:
                out.setdefault(set_of[item[0]], []).append(item)
    return {name: sorted(items, key=lambda i: (i[1], i[0])) for name, items in out.items()}


def read_sheets(directory=None):
    d3 = directory or MODULE / "data/d3"
    caches = slot_vendors.read("set_caches.csv", d3)
    vendor = slot_vendors.read("set_cache_vendor.csv", d3)
    if not caches or set(caches[0]) != CACHE_COLUMNS:
        raise ValueError(f"set_caches.csv: expected the columns {sorted(CACHE_COLUMNS)}")
    if len(vendor) != 1 or set(vendor[0]) != VENDOR_COLUMNS:
        raise ValueError(f"set_cache_vendor.csv: expected one row with the columns {sorted(VENDOR_COLUMNS)}")
    return caches, vendor[0]


def listed(directory=None):
    """[(cache entry, set name, [(piece entry, d3_name, level)], set level)] in vendor (set name A to Z) order."""
    d3 = directory or MODULE / "data/d3"
    caches, _ = read_sheets(d3)
    sets = pieces_by_set(d3)
    entries = [int(c["entry"]) for c in caches]
    if len(set(entries)) != len(entries) or len({c["set_name"] for c in caches}) != len(caches):
        raise ValueError("set_caches.csv: an entry or a set twice")
    taken = {int(r["item_entry"]) for r in slot_vendors.read("base_item_ids.csv", d3)}
    for entry in entries:
        if not ENTRY_BASE <= entry < SHELL_ENTRY_BASE:
            raise ValueError(f"set_caches.csv: {entry} is outside the item range {ENTRY_BASE}-{SHELL_ENTRY_BASE - 1}")
        if entry in taken:
            raise ValueError(f"set_caches.csv: {entry} is a base item's entry")
    if {c["set_name"] for c in caches} != set(sets):
        missing = sorted(set(sets) - {c["set_name"] for c in caches})
        extra = sorted({c["set_name"] for c in caches} - set(sets))
        raise ValueError(f"set_caches.csv: sets with a listed piece and no cache {missing}; caches for a set with none {extra}")
    out = []
    for cache in caches:
        pieces = sets[cache["set_name"]]
        description = description_of(pieces)
        if len(description) > MAX_DESCRIPTION:
            raise ValueError(f"{cache['set_name']}: the description is {len(description)} characters, the column holds "
                             f"{MAX_DESCRIPTION}")
        out.append((int(cache["entry"]), cache["set_name"], pieces, max(level for _, _, level in pieces)))
    if len(out) > slot_vendors.MAX_VENDOR_ITEMS:
        raise ValueError(f"{len(out)} caches, the core sends only {slot_vendors.MAX_VENDOR_ITEMS} to a window")
    return sorted(out, key=lambda c: (c[1], c[0]))


def description_of(pieces):
    return "Contains " + ", ".join(name for _, name, _ in pieces) + "."


def render(directory=None):
    d3 = directory or MODULE / "data/d3"
    caches = listed(d3)
    _, vendor = read_sheets(d3)
    v_entry, v_level, v_flag, donor = (int(vendor[k]) for k in ("entry", "level", "npcflag", "clone_entry"))
    cache_ids = ",".join(str(c[0]) for c in caches)
    items = ",\n".join(
        f"  ({entry}, {CLASS_MISC}, {SUBCLASS_JUNK}, {quote(name)}, {DISPLAY_ID}, {QUALITY_GREEN}, {HAS_LOOT_FLAG}, 1, 0, 0, 0, 0, "
        f"1, 0, {MATERIAL}, 0, {max(level, 1)}, {quote(description_of(pieces))})"
        for entry, name, pieces, level in caches)
    pieces = ",\n".join(f"({entry}, {item})" for entry, _, items_, _ in caches for item, _, _ in items_)
    sets = ",\n".join(f"({entry}, {quote(name)})" for entry, name, _, _ in caches)
    rows = ",\n".join(f"({v_entry}, {position}, {entry}, 0, 0, 0, 0)" for position, (entry, *_) in enumerate(caches))
    conditions = ",\n".join(
        f"({slot_vendors.SOURCE_NPC_VENDOR}, {v_entry}, {entry}, 0, 0, {slot_vendors.CONDITION_LEVEL}, 0, {level}, "
        f"{slot_vendors.COMP_HIGH_EQ}, 0, 0, 0, 0, '', {quote('set cache: from level ' + str(level))})"
        for entry, _, _, level in caches if level)
    return f"""-- Generated by generate_set_caches.py from set_caches.csv, set_cache_vendor.csv and the slot vendors' sheets (diablocraft-bzr0); never edit.
-- The set caches: one item per set that opens into every listed piece of it, and the vendor that gives them away free. Until release (diablocraft-bzr0, plan section 6.6).
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_set_cache` (
  `entry` INT UNSIGNED NOT NULL,
  `set_name` VARCHAR(80) NOT NULL,
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_set_cache_piece` (
  `cache_entry` INT UNSIGNED NOT NULL,
  `item_entry` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`cache_entry`, `item_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `dc_set_cache`;
INSERT INTO `dc_set_cache` (`entry`, `set_name`) VALUES
{sets};
DELETE FROM `dc_set_cache_piece`;
INSERT INTO `dc_set_cache_piece` (`cache_entry`, `item_entry`) VALUES
{pieces};
DELETE FROM `item_template` WHERE `entry` IN ({cache_ids});
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `maxcount`, `stackable`, `BagFamily`, `Material`, `bonding`, `ItemLevel`, `description`)
VALUES
{items};
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId`={slot_vendors.SOURCE_NPC_VENDOR} AND `SourceGroup`={v_entry};
DELETE FROM `npc_vendor` WHERE `entry`={v_entry};
DELETE FROM `creature_template_model` WHERE `CreatureID`={v_entry};
DELETE FROM `creature_template` WHERE `entry`={v_entry};
CREATE TEMPORARY TABLE dc_set_cache_vendor_template LIKE creature_template;
INSERT INTO dc_set_cache_vendor_template SELECT * FROM creature_template WHERE entry={donor};
UPDATE dc_set_cache_vendor_template SET entry={v_entry}, name={quote(vendor['name'])}, subname='', minlevel={v_level}, maxlevel={v_level}, npcflag={v_flag}, gossip_menu_id=0, ScriptName='', AIName='';
INSERT INTO `creature_template` SELECT * FROM dc_set_cache_vendor_template;
DROP TEMPORARY TABLE dc_set_cache_vendor_template;
INSERT INTO `creature_template_model` SELECT {v_entry}, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild` FROM `creature_template_model` WHERE `CreatureID`={donor};
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`) VALUES
{rows};
INSERT INTO `conditions` (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`,
  `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`, `ConditionValue3`,
  `NegativeCondition`, `ErrorType`, `ErrorTextId`, `ScriptName`, `Comment`) VALUES
{conditions};
"""


def generate():
    sql = render()
    target = MODULE / "data/sql/db-world/updates" / NAME
    write_migration(MODULE, target, sql)
    write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / NAME, sql)], label="set cache rows")
    print(f"Generated {NAME}")


if __name__ == "__main__":
    generate()
