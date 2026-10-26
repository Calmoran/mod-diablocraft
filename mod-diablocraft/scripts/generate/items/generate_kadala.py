#!/usr/bin/env python3
"""Generate Kadala's vendor rows (diablocraft-m2po, docs/proposals/kadala.md section 5 Part 3).

    python3 mod-diablocraft/scripts/generate/items/generate_kadala.py

Sources: kadala.csv (the 14 prices, in her order), kadala_entries.csv (one Mystery item per entry and the base kinds
it stands for), kadala_npc.csv (her creature row), account_economy.csv (the Blood Shard item), item_display.csv (the
icons), base_items.csv and class_map.csv (who may buy a class entry). One migration writes (kadala_0001_vendor.sql, applied;
kadala_0003_vendor.sql since diablocraft-ngybv, the same render with the Necromancer playable, so the Mystery Phylactery is
hers, applied on dev; kadala_0004_vendor.sql since diablocraft-vawmy.4, with the Demon Hunter playable, so the Mystery Quiver
is the Hunter's and the classes are keyed by class_names.item_key, applied on dev; kadala_0005_vendor.sql since
diablocraft-jjug3, with the Witch Doctor playable, so the Mystery Mojo is the Witch Doctor's, applied on dev;
kadala_0006_vendor.sql since diablocraft-r0d0h, with the Shaman in class_map.csv and no Shaman weapon or shield base yet, so the Mystery
Shield, One-Handed and Two-Handed are every class's but the Shaman's until the Shaman's bases land;
kadala_0007_vendor.sql since diablocraft-xnrvn.3, with the Shaman's bases in, so those three are every class's again):

  * her creature_template and model (a clone of the donor's, vendor flag only; the designer places her, then picks her model);
  * one Mystery item_template row per entry (a plain miscellaneous item nobody ever holds);
  * her npc_vendor rows, in the sheet's order, each priced by an ExtendedCost;
  * the itemextendedcost_dbc rows (one per distinct price): the server reads them from here, the client from its
    ItemExtendedCost.dbc, which Part 4's builder appends from these same rows.

The window draws a price only from the client's file, so Kadala shows no price until Part 4 ships the client patch.
"""
import csv
import functools
import operator
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
from class_names import item_key  # noqa: E402
from generate_rifts import quote  # noqa: E402
from generate_sql import base_wear_mask  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
NAME = "kadala_0007_vendor.sql"
ENTRIES_NAME = "kadala_0002_entries.sql"
# Constants (identities, not tunables): the stock ItemExtendedCost.dbc ends at 2997, ours start above it, one per price
# in ascending order. The core's list stops sending at 150 entries (Creature.h MAX_VENDOR_ITEMS).
EXTENDED_COST_FIRST = 3000
MAX_VENDOR_ITEMS = 150
ITEM_CLASS_MISC, ITEM_FLAG_PURCHASE_RECORD, BIND_ON_PICKUP, QUALITY_WHITE = 15, 0x08000000, 1, 1
PRICE = re.compile(r"(\d+) Blood Shards")
ENTRY_COLUMNS = {"item_entry", "name", "cost_rule", "slot", "base_types", "display_type", "description", "source"}
NPC_COLUMNS = {"entry", "clone_entry", "name", "subname", "level", "npcflag", "source"}


def read(name, columns=None, directory=None):
    with ((directory or MODULE / "data/d3") / name).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        rows = list(reader)
    if columns is not None and set(reader.fieldnames or ()) != columns:
        raise ValueError(f"{name}: expected the columns {sorted(columns)}")
    if not rows:
        raise ValueError(f"{name}: no rows")
    return rows


def number(row, key, what):
    try:
        return int(row[key])
    except (TypeError, ValueError):
        raise ValueError(f"{what}: {key} must be a whole number, got {row[key]!r}") from None


def entry_mask(rows, bits):
    """AllowableClass an entry gets from the generic bases it stands for: -1 when any names no class or the union is every playable class."""
    masks = [base_wear_mask(row, bits) for row in rows]
    if not masks:
        raise ValueError("an entry stands for no base kind")
    if -1 in masks:
        return -1
    mask = functools.reduce(operator.or_, masks)
    # Every playable class may wear it: no restriction, as items_0011 reads a base that names no class.
    return -1 if mask == functools.reduce(operator.or_, bits.values()) else mask


def render(directory=None):
    d3 = (directory or MODULE / "data/d3")
    entries, npcs = read("kadala_entries.csv", ENTRY_COLUMNS, d3), read("kadala_npc.csv", NPC_COLUMNS, d3)
    rules = {r["rule"]: r["value"] for r in read("kadala.csv", None, d3)}
    economy = [r for r in read("account_economy.csv", None, d3) if r["name"] == "Blood Shard" and r["kind"] == "material"]
    displays = {(r["slot"], r["type"]): int(r["wow_display_id"]) for r in read("item_display.csv", None, d3)}
    bases = [r for r in read("base_items.csv", None, d3) if not r["rarity"]]
    bits = {item_key(r["d3_class"]): 1 << (int(r["wow_class_id"]) - 1) for r in read("class_map.csv", None, d3)}
    if len(economy) != 1 or len(npcs) != 1:
        raise ValueError("expected one Blood Shard ledger material and one Kadala creature row")
    shard, npc = int(economy[0]["item_entry"]), npcs[0]
    if len(entries) > MAX_VENDOR_ITEMS:
        raise ValueError(f"{len(entries)} entries: the core sends only {MAX_VENDOR_ITEMS} to a vendor window")
    if len({number(e, "item_entry", e["name"]) for e in entries}) != len(entries):
        raise ValueError("duplicate Mystery item entry")
    order = list(rules)  # kadala.csv's row order is her order; an entry may not come before the one above it
    prices, last = {}, -1
    for e in entries:
        rule = e["cost_rule"]
        if rule not in rules or not rule.startswith("cost_") or not PRICE.fullmatch(rules[rule]):
            raise ValueError(f"{e['name']}: {rule} is not a price row of kadala.csv")
        if order.index(rule) < last:
            raise ValueError(f"{e['name']}: out of the sheet's order")
        last = order.index(rule)
        prices[e["name"]] = int(PRICE.fullmatch(rules[rule]).group(1))
    cost_ids = {price: EXTENDED_COST_FIRST + i for i, price in enumerate(sorted(set(prices.values())))}

    items, vendor = [], []
    for slot_no, e in enumerate(entries):
        wanted = set(filter(None, e["base_types"].split(";")))
        kinds = [r for r in bases if r["slot"] == e["slot"] and (not wanted or r["type"] in wanted)]
        if wanted and {r["type"] for r in kinds} != wanted:
            raise ValueError(f"{e['name']}: base_types names a kind base_items.csv does not have")
        mask = entry_mask(kinds, bits)
        if (e["slot"], e["display_type"]) not in displays:
            raise ValueError(f"{e['name']}: no item_display.csv row for {e['slot']}/{e['display_type']}")
        entry = int(e["item_entry"])
        bonding = BIND_ON_PICKUP if mask != -1 else 0
        items.append(f"  ({entry}, {ITEM_CLASS_MISC}, 0, {quote(e['name'])}, {displays[(e['slot'], e['display_type'])]}, "
                     f"{QUALITY_WHITE}, 0, 1, 0, 0, 0, {mask}, 0, 1, {bonding}, 70, {quote(e['description'])})")
        vendor.append(f"({npc['entry']}, {slot_no}, {entry}, 0, 0, {cost_ids[prices[e['name']]]}, 0)")

    costs = ",\n".join(f"({cid}, 0, 0, 0, {shard}, 0, 0, 0, 0, {price}, 0, 0, 0, 0, 0, 0)"
                       for price, cid in cost_ids.items())
    entry, donor = int(npc["entry"]), int(npc["clone_entry"])
    ids = ",".join(e["item_entry"] for e in entries)
    return f"""-- Generated by generate_kadala.py from kadala.csv, kadala_entries.csv and kadala_npc.csv (diablocraft-m2po); never edit.
-- Kadala's stock vendor: her creature, one Mystery item per entry, her list and the Blood Shard prices.
SET NAMES utf8mb4;
DELETE FROM `itemextendedcost_dbc` WHERE `ID` IN ({",".join(map(str, cost_ids.values()))});
INSERT INTO `itemextendedcost_dbc`
  (`ID`, `HonorPoints`, `ArenaPoints`, `ArenaBracket`, `ItemID_1`, `ItemID_2`, `ItemID_3`, `ItemID_4`, `ItemID_5`,
   `ItemCount_1`, `ItemCount_2`, `ItemCount_3`, `ItemCount_4`, `ItemCount_5`, `RequiredArenaRating`, `ItemPurchaseGroup`)
VALUES
{costs};
DELETE FROM `item_template` WHERE `entry` IN ({ids});
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `AllowableClass`, `maxcount`, `stackable`, `bonding`, `ItemLevel`, `description`)
VALUES
{",\n".join(items)};
CREATE TEMPORARY TABLE dc_kadala_template LIKE creature_template;
INSERT INTO dc_kadala_template SELECT * FROM creature_template WHERE entry={donor};
UPDATE dc_kadala_template SET entry={entry}, name={quote(npc["name"])}, subname={quote(npc["subname"])}, minlevel={number(npc, "level", "Kadala")}, maxlevel={number(npc, "level", "Kadala")}, npcflag={number(npc, "npcflag", "Kadala")}, gossip_menu_id=0, ScriptName='', AIName='';
DELETE FROM `creature_template` WHERE `entry`={entry};
INSERT INTO `creature_template` SELECT * FROM dc_kadala_template;
DROP TEMPORARY TABLE dc_kadala_template;
DELETE FROM `creature_template_model` WHERE `CreatureID`={entry};
INSERT INTO `creature_template_model` SELECT {entry}, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild` FROM `creature_template_model` WHERE `CreatureID`={donor};
DELETE FROM `npc_vendor` WHERE `entry`={entry};
INSERT INTO `npc_vendor` (`entry`, `slot`, `item`, `maxcount`, `incrtime`, `ExtendedCost`, `VerifiedBuild`) VALUES
{",\n".join(vendor)};
"""


def render_entries(directory=None):
    """dc_kadala_entry: what each Mystery entry sells, for the purchase hook (Part 5, dc_kadala.cpp).

    The slot and the kinds are the sheet's own words and match dc_base_item.slot and .type, so the hook's slot filter
    reads them with no second copy in code. A kind the base items do not have is refused by render(), not here.
    """
    entries = read("kadala_entries.csv", ENTRY_COLUMNS, directory or MODULE / "data/d3")
    values = ",\n".join(f"({int(e['item_entry'])}, {quote(e['slot'])}, {quote(e['base_types'])})" for e in entries)
    return f"""-- Generated by generate_kadala.py from kadala_entries.csv (diablocraft-aeo7); never edit.
-- What each Mystery entry sells: its slot and, for the class off-hands and the shield, the base kinds.
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_kadala_entry` (
  `item_entry` INT UNSIGNED NOT NULL,
  `slot` VARCHAR(32) NOT NULL,
  `base_types` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`item_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `dc_kadala_entry`;
INSERT INTO `dc_kadala_entry` (`item_entry`, `slot`, `base_types`) VALUES
{values};
"""


def generate():
    updates = MODULE / "data/sql/db-world/updates"
    for name, sql, label in ((NAME, render(), "Kadala vendor rows"), (ENTRIES_NAME, render_entries(), "Kadala entry table")):
        target = updates / name
        write_migration(MODULE, target, sql)
        write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / name, sql)], label=label)
        print(f"Generated {name}")


if __name__ == "__main__":
    generate()
