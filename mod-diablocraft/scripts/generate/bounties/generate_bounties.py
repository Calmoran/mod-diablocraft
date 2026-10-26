#!/usr/bin/env python3
"""Generate the bounty catalogue (diablocraft-dm9vg.1, docs/research/bounties.md 5.1, brief bounties-first-set-2026-10-11).

    python3 mod-diablocraft/scripts/generate/bounties/generate_bounties.py

Sources: bounties.csv (one row a bounty: its column and index, Kill or Click, its zone, its title, the named Unique of a Kill
row and the survey anchors it stands on: the Unique's own anchor, or a Click row's objective spots), rift_open_zones.csv (the
zone keys and each zone's act; a column is an act, one bounty a zone) and rift_anchors.csv (the zones' survey anchors on map 751, generate_open_zone_survey.py). Two
migrations:

  bounties_0001_first_set.sql (diablocraft-dm9vg.1)
  * dc_bounties: one row a bounty, its zone copied from rift_open_zones.csv;
  * dc_bounties_spot: its spots, each an anchor of its zone's survey with the anchor's own position (a Kill's one spot is
    the zone's bounty spot, where its drawn target stands);
  * dc_bounties_target (diablocraft-hyoic.2), from bounty_targets.csv: the master list of named targets a Kill bounty draws
    one of per board, and the title it gives the bounty ("Kill <name>").

  bounties_0002_objectives.sql (W2, diablocraft-dm9vg.2)
  * gameobject_template: one type 10 (goober) object a Click bounty, in the 910140-910164 block, wearing the row's
    objective_display; the module summons it at each spot (src/bounties/dc_bounty_objectives.cpp), nothing is spawned
    from the `gameobject` table;
  * dc_bounties_objective: which template a Click bounty's objectives wear.

  bounties_0003_caches.sql (W4, diablocraft-dm9vg.4), from bounty_caches.csv and bounty_cache_legendaries.csv
  * dc_bounties_cache: one Horadric Cache item a column (an act) and the act reagent it carries;
  * dc_bounties_cache_legendary: each column's act-only legendary pool (decisions 4006a91d); a column with no rows rolls
    no legendaries;
  * one item_template row a cache, the set caches' shape (generate_set_caches.py): green, miscellaneous, the stock has-loot
    flag, the junkbox display, no price, a description naming what it opens into. The INSERT names its columns one row to
    a line, which client-patch/dbc/build_item.py reads for the Item.dbc rows.
  The amounts are the rifts tunables bounty_cache_* (data/tunables/rifts.csv); the earned tier of each cache is the
  characters table dc_bounties_cache_item (bounties_0006_cache_tier.sql), written by the module.

  bounties_0005_quests.sql (diablocraft-dm9vg.17: bounties as quests, ruling 2026-10-12), from bounties.csv
  * quest_template: one quest a bounty, a count n and a target, in the 910200-911999 block. A Kill row has one quest per
    named target it can draw (n = 1, its words "Kill <name>", diablocraft-hyoic.2); a Click row's has rows n = 1 to its spot count, so the tracker reads "Shrines activated 0/n" whatever count a
    board draws (the count is quest_template's, cached by the client with the quest). The objective is the rifts'
    own never-spawned credit creature (910049, made by bounties_0006; never the rifts' 910015, diablocraft-l2hsp), counted by
    the module; its words are the row's
    objective_text, the log's are its title and quest_text. Zero rewards, not sharable, repeatable (as the rift quests);
    QuestSortID is the zone, so the log files it under the zone's name;
  * dc_bounties_quest: which quest shows a bounty at a count, and the world map area its map marks go on (the
    WorldMapArea row of the bounty's map and zone in client-patch/dbc/WorldMapArea.dbc: the copy's clone).
  bounties_0006_quest_credit.sql (diablocraft-dm9vg.20): the bounty quests' own credit creature 910049 ("Bounty Progress",
    never spawned), and the quests moved onto it: 910015 is the two rift bars' alone (dc_rifts.cpp loadBar). Its UPDATE is
    a guard now: bounties_0005 names 910049 itself, since the updater reapplies a regenerated bounties_0005 after it.
  bounties_0004_cache_account_bound.sql (diablocraft-dm9vg.9): the caches bind to account on pickup, like D3's (the designer
  2026-10-12); Item.dbc has no flags or bonding, so the client is unchanged.

The party boards (which bounties a party or a solo player holds, and how far each is) are the characters table
dc_bounties_board (bounties_0005_party_boards.sql), filled by the module (src/bounties/). Never the retired dc_bounty* tables.
"""
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration  # noqa: E402
from generate_rifts import quote  # noqa: E402
from generate_set_caches import CLASS_MISC, DISPLAY_ID, HAS_LOOT_FLAG, MATERIAL, MAX_DESCRIPTION, QUALITY_GREEN, SUBCLASS_JUNK  # noqa: E402
from generate_sql import ENTRY_BASE, SHELL_ENTRY_BASE  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
D3 = MODULE / "data/d3"
NAME = "bounties_0001_first_set.sql"
OBJECTIVES = "bounties_0002_objectives.sql"
CACHES = "bounties_0003_caches.sql"
QUESTS = "bounties_0005_quests.sql"
CREDIT = "bounties_0006_quest_credit.sql"
BOUND = "bounties_0004_cache_account_bound.sql"
# The core's bind-to-account item flag (ItemTemplate.h) and bind on pickup (dm9vg.9).
ITEM_FLAG_IS_BOUND_TO_ACCOUNT, BIND_ON_PICKUP = 0x08000000, 1
CACHE_COLUMNS = ["column", "entry", "name", "reagent_entry", "source"]
POOL_COLUMNS = ["column", "item_entry", "d3_name", "source"]
COLUMNS = ["column", "index", "type", "zone", "title", "unique_entry", "unique_name", "anchors", "spot", "objective_display",
           "objective_text", "quest_text", "source"]
# diablocraft-dm9vg.18: a zone with no stock rare gets a made Unique, a copy of a stock creature under a name of its own,
# standing on a spot of its own (bounties.csv `spot`, x;y;z;o) instead of a survey anchor; its dc_bounties_spot anchor is 0.
UNIQUE_COLUMNS = ["entry", "name", "clone_of", "rank", "level", "source"]
TARGET_COLUMNS = ["entry", "name", "source"]
RANKS = range(0, 5)  # creature_template.rank: normal, elite, rare elite, boss, rare
MAX_LEVEL = 80
# Torment's gameobject block for Click objectives, one a Click bounty: 25 is the board's whole (COLUMN_COUNT x 5 cells).
OBJECTIVE_ENTRIES = range(910140, 910165)
# dm9vg.17: the bounty quests' block, one quest a bounty and a count. hyoic.5 (acts A2): widened from 100 to 1800, a quest a zone and
# a target (16 x 16 now, 41 x 41 when every act is live); the rift quests sit below it (910020-).
QUEST_ENTRIES = range(910200, 912000)
# The bounty quests' credit creature, a never-spawned copy of stock 2840 as the rifts' 910015 is (bounties_0006 makes it; it
# sorts before rifts_0011, so it cannot copy 910015). dc_rifts.cpp takes every quest on 910015 as a rift bar, so rifts went
# off while bounties_0005 named 910015 (dm9vg.20) and again each time a regenerated bounties_0005 was reapplied after
# bounties_0006 (diablocraft-l2hsp): bounties_0005 writes 910049 itself; quest_template has no key on creature_template.
CREDIT_CREATURE, CREDIT_CLONE_OF = 910049, 2840
QUEST_FLAGS = 256          # QUEST_FLAGS_NO_MONEY_FROM_XP, as the rift quests; not QUEST_FLAGS_SHARABLE (8)
MAX_OBJECTIVE_TEXT, MAX_QUEST_TEXT = 80, 255
WORLD_MAP_AREA = MODULE.parent / "client-patch/dbc/WorldMapArea.dbc"
GOOBER = 10  # GAMEOBJECT_TYPE_GOOBER: a player can click it; the module's AI answers the click
TYPES = ("kill", "click")
# Constants (D3's shape, not tunables): five columns, one an act (maxroll bounties: five acts, "Completing all 5 bounties in
# an Act"), and the record fields' widths, so a board record stays under the window bridge's 255 bytes
# (docs/contracts/bounty-messages.md). A Click bounty's spots are one bit each of a 32-bit mask (dc_bounties_board.objectives).
COLUMN_COUNT, MAX_TITLE, MAX_ZONE_NAME, MAX_SPOTS = 5, 80, 64, 32
FORBIDDEN = set("|\t")


def read(name, directory):
    with (Path(directory) / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def made_uniques(directory=None):
    """{entry: row} of bounty_uniques.csv, checked: the Uniques made for zones with no stock rare."""
    rows = read("bounty_uniques.csv", Path(directory or D3))
    if rows and list(rows[0]) != UNIQUE_COLUMNS:
        raise ValueError(f"bounty_uniques.csv: expected the columns {UNIQUE_COLUMNS}")
    out = {}
    for row in rows:
        where = f"bounty_uniques.csv {row['entry']}"
        if not all(row[k].isdigit() for k in ("entry", "clone_of", "rank", "level")):
            raise ValueError(f"{where}: entry, clone_of, rank and level are whole numbers")
        if int(row["rank"]) not in RANKS or not 1 <= int(row["level"]) <= MAX_LEVEL or row["entry"] == row["clone_of"]:
            raise ValueError(f"{where}: rank 0 to 4, level 1 to {MAX_LEVEL}, and a copy of another creature")
        if not row["name"] or len(row["name"].encode()) > MAX_TITLE or FORBIDDEN & set(row["name"]) or "'" in row["name"]:
            raise ValueError(f"{where}: the name is 1 to {MAX_TITLE} bytes with no |, tab or quote")
        if row["entry"] in out:
            raise ValueError(f"{where}: twice")
        out[row["entry"]] = row
    return out


def own_spot(text, where):
    """A made Unique's spot, x;y;z;o, as the anchor shape the catalogue carries (anchor 0)."""
    parts = text.split(";")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        values = []
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        raise ValueError(f"{where}: a spot is four numbers, x;y;z;o")
    return dict(zip(("x", "y", "z", "o"), parts), anchor="0")


def catalogue(directory=None):
    """[(bounty id, row, zone row, [anchor rows])], checked, in (column, index) order. The id is column * 100 + index."""
    d3 = Path(directory or D3)
    rows = read("bounties.csv", d3)
    if not rows or list(rows[0]) != COLUMNS:
        raise ValueError(f"bounties.csv: expected the columns {COLUMNS}")
    zones = {z["key"]: z for z in read("rift_open_zones.csv", d3)}
    anchors = {}
    for a in read("rift_anchors.csv", d3):
        anchors.setdefault(a["dungeon"], {})[int(a["anchor"])] = a
    out, seen, zones_seen = [], set(), set()
    for row in rows:
        where = f"bounties.csv column {row['column']} index {row['index']}"
        column, index = int(row["column"]), int(row["index"])
        if not 1 <= column <= COLUMN_COUNT or not 1 <= index <= 99:
            raise ValueError(f"{where}: column is 1 to {COLUMN_COUNT}, index 1 to 99")
        if (column, index) in seen:
            raise ValueError(f"{where}: twice")
        seen.add((column, index))
        if row["type"] not in TYPES:
            raise ValueError(f"{where}: type is one of {TYPES}")
        zone = zones.get(row["zone"])
        if zone is None:
            raise ValueError(f"{where}: zone {row['zone']!r} is not a key of rift_open_zones.csv")
        # diablocraft-hyoic.1 (docs/research/bounty-acts.md 2.2): the column is the zone's act, and a zone has one bounty, so
        # a board's draw of five cells is five distinct zones of the act.
        if row["zone"] in zones_seen:
            raise ValueError(f"{where}: {row['zone']} has a bounty already; a zone has one")
        zones_seen.add(row["zone"])
        if zone.get("act") != str(column):
            raise ValueError(f"{where}: the column is {row['zone']}'s act (rift_open_zones.csv act {zone.get('act')!r})")
        if len(zone["name"].encode()) > MAX_ZONE_NAME or FORBIDDEN & set(zone["name"]):
            raise ValueError(f"rift_open_zones.csv {zone['key']}: the name is at most {MAX_ZONE_NAME} bytes with no | or tab")
        numbers = [int(n) for n in row["anchors"].split(";") if n.strip()]
        survey = anchors.get(zone["name"], {})
        missing = [n for n in numbers if n not in survey]
        if missing:
            raise ValueError(f"{where}: anchors {missing} are not in {zone['name']}'s survey (rift_anchors.csv)")
        if len(set(numbers)) != len(numbers):
            raise ValueError(f"{where}: an anchor twice")
        if row["unique_entry"] or row["unique_name"]:
            raise ValueError(f"{where}: a row names no Unique; a Kill's target is drawn from bounty_targets.csv per board")
        if row["type"] == "kill":
            # diablocraft-hyoic.2 (ruling 2026-10-12): the row is the zone's bounty spot, one survey anchor or a spot of its own
            # (x;y;z;o); the named target standing there is drawn per board from bounty_targets.csv, its words with it.
            if len(numbers) + bool(row["spot"]) != 1:
                raise ValueError(f"{where}: a Kill row stands on one anchor of its zone's survey or on a spot of its own, not both")
            if row["title"] or row["objective_text"] or row["quest_text"] or row["objective_display"]:
                raise ValueError(f"{where}: a Kill row has no title, objective display or texts; its target's are drawn with it")
            out.append((column * 100 + index, row, zone,
                        [own_spot(row["spot"], where)] if row["spot"] else [survey[n] for n in numbers]))
            continue
        if row["spot"]:
            raise ValueError(f"{where}: only a Kill row stands on a spot of its own")
        if not 1 <= len(numbers) <= MAX_SPOTS:
            raise ValueError(f"{where}: a Click row has 1 to {MAX_SPOTS} objective spots")
        if not row["objective_display"].isdigit() or int(row["objective_display"]) == 0:
            raise ValueError(f"{where}: a Click row names its objective's display (GameObjectDisplayInfo id)")
        if not row["title"] or len(row["title"].encode()) > MAX_TITLE or FORBIDDEN & set(row["title"]):
            raise ValueError(f"{where}: the title is 1 to {MAX_TITLE} bytes with no | or tab")
        for column_name, most in (("objective_text", MAX_OBJECTIVE_TEXT), ("quest_text", MAX_QUEST_TEXT)):
            if not row[column_name].strip() or len(row[column_name].encode()) > most or FORBIDDEN & set(row[column_name]):
                raise ValueError(f"{where}: {column_name} is 1 to {most} bytes with no | or tab")
        out.append((column * 100 + index, row, zone, [survey[n] for n in numbers]))
    if any(r["type"] == "kill" for _, r, _, _ in out) and not targets(d3):
        raise ValueError("bounty_targets.csv: a Kill bounty needs at least one named target")
    return sorted(out, key=lambda b: b[0])


def kill_words(target, zone):
    """A Kill's title, quest text and objective for one target in one zone: dm9vg.1's words, now per drawn target."""
    return (f"Kill {target['name']}", f"Slay {target['name']} in {zone['name']}.", f"{target['name']} slain")


def targets(directory=None):
    """bounty_targets.csv, checked, in sheet order (diablocraft-hyoic.2): the master list of named targets a Kill bounty
    draws from, each a creature_template entry; a made Unique (bounty_uniques.csv) under its own name."""
    d3 = Path(directory or D3)
    rows = read("bounty_targets.csv", d3)
    if rows and list(rows[0]) != TARGET_COLUMNS:
        raise ValueError(f"bounty_targets.csv: expected the columns {TARGET_COLUMNS}")
    made, seen = made_uniques(d3), set()
    longest = max((z["name"] for z in read("rift_open_zones.csv", d3)), key=lambda n: len(n.encode()), default="")
    for row in rows:
        where = f"bounty_targets.csv {row['entry']}"
        if not row["entry"].isdigit() or int(row["entry"]) == 0 or row["entry"] in seen:
            raise ValueError(f"{where}: an entry is a creature_template entry, once")
        seen.add(row["entry"])
        if not row["name"] or FORBIDDEN & set(row["name"]):
            raise ValueError(f"{where}: the name is set, with no | or tab")
        title, text, objective = kill_words(row, {"name": longest})
        if len(title.encode()) > MAX_TITLE or len(objective.encode()) > MAX_OBJECTIVE_TEXT or len(text.encode()) > MAX_QUEST_TEXT:
            raise ValueError(f"{where}: the name makes a title over {MAX_TITLE} bytes or a text over its limit")
        if row["entry"] in made and made[row["entry"]]["name"] != row["name"]:
            raise ValueError(f"{where}: a made Unique keeps its bounty_uniques.csv name, {made[row['entry']]['name']!r}")
    return rows


def render(directory=None):
    bounties = catalogue(directory)
    rows = ",\n".join(
        f"({bid}, {int(r['column'])}, {int(r['index'])}, {quote(r['type'])}, {quote(z['key'])}, {quote(z['name'])}, {int(z['map_id'])}, "
        f"{int(z['zone_id'])}, {quote(r['title'])})"
        for bid, r, z, _ in bounties)
    named = ",\n".join(f"({int(t['entry'])}, {quote(t['name'])}, {quote(kill_words(t, {'name': ''})[0])})" for t in targets(directory))
    spots = ",\n".join(
        f"({bid}, {n}, {int(a['anchor'])}, {a['x']}, {a['y']}, {a['z']}, {a['o']})"
        for bid, _, _, anchors in bounties for n, a in enumerate(anchors, start=1))
    return f"""-- Generated by generate_bounties.py from bounties.csv, bounty_targets.csv, rift_open_zones.csv and rift_anchors.csv (diablocraft-dm9vg.1); never edit.
-- The bounty catalogue: one row a bounty, its zone, and the survey anchors it stands on (docs/research/bounties.md 5.1),
-- and the named targets a Kill bounty draws from per board (bounty_targets.csv, diablocraft-hyoic.2). The tables are the
-- generator's alone, so they are rebuilt whole.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_bounties`;
CREATE TABLE `dc_bounties` (
  `bounty_id` INT UNSIGNED NOT NULL COMMENT 'column * 100 + index',
  `col` TINYINT UNSIGNED NOT NULL COMMENT '1 to 5, the zone''s act (rift_open_zones.csv act)',
  `idx` TINYINT UNSIGNED NOT NULL COMMENT 'the row in the column''s pool',
  `type` VARCHAR(8) NOT NULL COMMENT 'kill or click',
  `zone_key` VARCHAR(32) NOT NULL COMMENT 'rift_open_zones.csv key',
  `zone_name` VARCHAR(64) NOT NULL,
  `map_id` INT UNSIGNED NOT NULL,
  `zone_id` INT UNSIGNED NOT NULL COMMENT 'AreaTable',
  `title` VARCHAR(80) NOT NULL COMMENT 'a Click''s; a Kill''s is its drawn target''s (dc_bounties_target)',
  PRIMARY KEY (`bounty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DROP TABLE IF EXISTS `dc_bounties_target`;
CREATE TABLE `dc_bounties_target` (
  `entry` INT UNSIGNED NOT NULL COMMENT 'creature_template of a named target',
  `name` VARCHAR(80) NOT NULL,
  `title` VARCHAR(80) NOT NULL COMMENT 'the Kill bounty''s title with this target',
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_bounties_spot` (
  `bounty_id` INT UNSIGNED NOT NULL,
  `spot` TINYINT UNSIGNED NOT NULL COMMENT '1 up; a Click objective is bit spot-1 of dc_bounties_board.objectives',
  `anchor` INT UNSIGNED NOT NULL COMMENT 'rift_anchors.csv anchor of the zone',
  `x` FLOAT NOT NULL,
  `y` FLOAT NOT NULL,
  `z` FLOAT NOT NULL,
  `o` FLOAT NOT NULL,
  PRIMARY KEY (`bounty_id`, `spot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `dc_bounties_spot`;
INSERT INTO `dc_bounties` (`bounty_id`, `col`, `idx`, `type`, `zone_key`, `zone_name`, `map_id`, `zone_id`, `title`) VALUES
{rows};
INSERT INTO `dc_bounties_target` (`entry`, `name`, `title`) VALUES
{named};
INSERT INTO `dc_bounties_spot` (`bounty_id`, `spot`, `anchor`, `x`, `y`, `z`, `o`) VALUES
{spots};
""" + render_made_uniques(directory)


def render_made_uniques(directory=None):
    """The made Uniques (diablocraft-dm9vg.18): each a copy of its stock creature and its model under its own entry, name,
    rank and level, with no AI or script of its own (the stock one's SmartAI rows are keyed to the stock entry)."""
    out = ""
    for entry, u in sorted(made_uniques(directory).items()):
        table = f"dc_bounty_unique_{entry}"
        out += f"""-- A made Unique (bounty_uniques.csv): {u['name']}, a copy of creature {u['clone_of']}.
CREATE TEMPORARY TABLE `{table}` LIKE `creature_template`;
INSERT INTO `{table}` SELECT * FROM `creature_template` WHERE `entry` = {u['clone_of']};
UPDATE `{table}` SET `entry` = {entry}, `name` = {quote(u['name'])}, `subname` = NULL, `rank` = {u['rank']}, `minlevel` = {u['level']},
  `maxlevel` = {u['level']}, `AIName` = '', `ScriptName` = '';
DELETE FROM `creature_template` WHERE `entry` = {entry};
INSERT INTO `creature_template` SELECT * FROM `{table}`;
DROP TEMPORARY TABLE `{table}`;
DELETE FROM `creature_template_model` WHERE `CreatureID` = {entry};
INSERT INTO `creature_template_model` (`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild`)
SELECT {entry}, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild` FROM `creature_template_model` WHERE `CreatureID` = {u['clone_of']};
"""
    return out


def render_objectives(directory=None):
    clicks = [(bid, r) for bid, r, _, _ in catalogue(directory) if r["type"] == "click"]
    if len(clicks) > len(OBJECTIVE_ENTRIES):
        raise ValueError(f"bounties.csv: more Click bounties than the {len(OBJECTIVE_ENTRIES)} objective entries")
    entries = list(zip(OBJECTIVE_ENTRIES, clicks))
    zeros = ", ".join(["0"] * 24)
    templates = ",\n".join(f"({entry}, {GOOBER}, {int(r['objective_display'])}, {quote(r['title'])}, '', '', '', 1, {zeros}, '', '', 12340)"
                           for entry, (_, r) in entries)
    links = ",\n".join(f"({bid}, {entry})" for entry, (bid, _) in entries)
    first, last = OBJECTIVE_ENTRIES[0], OBJECTIVE_ENTRIES[-1]
    out = f"""-- Generated by generate_bounties.py from bounties.csv (diablocraft-dm9vg.2); never edit.
-- Bounties W2: the Click objective's object, one type 10 (goober) template a Click bounty wearing its row's
-- objective_display. The module summons it at each spot still to click, owned by the bounty's party
-- (src/bounties/dc_bounty_objectives.cpp); nothing is spawned from the `gameobject` table.
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_bounties_objective` (
  `bounty_id` INT UNSIGNED NOT NULL COMMENT 'dc_bounties.bounty_id of a Click bounty',
  `go_entry` INT UNSIGNED NOT NULL COMMENT 'gameobject_template its objectives wear ({first} to {last})',
  PRIMARY KEY (`bounty_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `dc_bounties_objective`;
DELETE FROM `gameobject_template` WHERE `entry` BETWEEN {first} AND {last};
"""
    if entries:
        columns = ", ".join(f"`{c}`" for c in ["entry", "type", "displayId", "name", "IconName", "castBarCaption", "unk1", "size"]
                            + [f"Data{i}" for i in range(24)] + ["AIName", "ScriptName", "VerifiedBuild"])
        out += f"INSERT INTO `gameobject_template` ({columns}) VALUES\n{templates};\n"
        out += f"INSERT INTO `dc_bounties_objective` (`bounty_id`, `go_entry`) VALUES\n{links};\n"
    return out


def caches(directory=None):
    """[(column, entry, name, reagent entry, reagent name, [(legendary entry, name)])], checked, in column order."""
    d3 = Path(directory or D3)
    rows, pool = read("bounty_caches.csv", d3), read("bounty_cache_legendaries.csv", d3)
    if not rows or list(rows[0]) != CACHE_COLUMNS:
        raise ValueError(f"bounty_caches.csv: expected the columns {CACHE_COLUMNS}")
    if pool and list(pool[0]) != POOL_COLUMNS:
        raise ValueError(f"bounty_cache_legendaries.csv: expected the columns {POOL_COLUMNS}")
    materials = {int(r["item_entry"]): r["name"] for r in read("account_economy.csv", d3) if r["kind"] == "material"}
    bases = {r["d3_id"]: r for r in read("base_items.csv", d3)}
    ids = {int(r["item_entry"]): r["d3_id"] for r in read("base_item_ids.csv", d3)}
    set_caches = {int(r["entry"]) for r in read("set_caches.csv", d3)}
    out, columns, entries = [], set(), set()
    for row in rows:
        where = f"bounty_caches.csv column {row['column']}"
        column, entry, reagent = int(row["column"]), int(row["entry"]), int(row["reagent_entry"])
        if not 1 <= column <= COLUMN_COUNT or column in columns:
            raise ValueError(f"{where}: a column is 1 to {COLUMN_COUNT}, one cache each")
        if not ENTRY_BASE <= entry < SHELL_ENTRY_BASE or entry in ids or entry in set_caches or entry in entries:
            raise ValueError(f"{where}: entry {entry} is outside {ENTRY_BASE}-{SHELL_ENTRY_BASE - 1} or already an item's")
        if reagent not in materials:
            raise ValueError(f"{where}: reagent {reagent} is not a material of account_economy.csv")
        if not row["name"] or FORBIDDEN & set(row["name"]):
            raise ValueError(f"{where}: the name is set, with no | or tab")
        columns.add(column)
        entries.add(entry)
        out.append([column, entry, row["name"], reagent, materials[reagent], []])
    by_column = {c[0]: c for c in out}
    for row in pool:
        where = f"bounty_cache_legendaries.csv column {row['column']} item {row['item_entry']}"
        cache, item = by_column.get(int(row["column"])), int(row["item_entry"])
        if cache is None:
            raise ValueError(f"{where}: the column has no cache in bounty_caches.csv")
        base = bases.get(ids.get(item, ""))
        if base is None or base["rarity"] != "legendary":
            raise ValueError(f"{where}: not a legendary base item Torment has (base_item_ids.csv, base_items.csv)")
        if base["d3_name"] != row["d3_name"]:
            raise ValueError(f"{where}: base item {item} is {base['d3_name']!r}, not {row['d3_name']!r}")
        if item in [i for i, _ in cache[5]]:
            raise ValueError(f"{where}: twice in the column's pool")
        cache[5].append((item, row["d3_name"]))
    for cache in out:
        if len(description_of(cache)) > MAX_DESCRIPTION:
            raise ValueError(f"bounty_caches.csv column {cache[0]}: the description is over {MAX_DESCRIPTION} characters")
    return sorted((tuple(c) for c in out), key=lambda c: c[0])


def description_of(cache):
    legendaries = ", ".join(name for _, name in cache[5])
    return ("Earned by completing a column of bounties. Opens into gold, Blood Shards, " + cache[4] + ", gems, Death's Breath "
            "and rare items" + ("; legendaries: " + legendaries if legendaries else "") + ".")


def render_caches(directory=None):
    found = caches(directory)
    ids = ",".join(str(c[1]) for c in found)
    items = ",\n".join(
        f"  ({entry}, {CLASS_MISC}, {SUBCLASS_JUNK}, {quote(name)}, {DISPLAY_ID}, {QUALITY_GREEN}, {HAS_LOOT_FLAG}, 1, 0, 0, 0, 0, "
        f"1, 0, {MATERIAL}, 0, 1, {quote(description_of((column, entry, name, reagent, reagent_name, pool)))})"
        for column, entry, name, reagent, reagent_name, pool in found)
    rows = ",\n".join(f"({column}, {entry}, {reagent})" for column, entry, _, reagent, _, _ in found)
    pools = ",\n".join(f"({column}, {item})" for column, _, _, _, _, pool in found for item, _ in pool)
    out = f"""-- Generated by generate_bounties.py from bounty_caches.csv and bounty_cache_legendaries.csv (diablocraft-dm9vg.4); never edit.
-- Bounties W4: the Horadric Cache of each column (an act), its act reagent and its act-only legendary pool. A column with no
-- pool rows rolls no legendaries. Delivered when a column completes, opened by the module (src/bounties/dc_bounty_cache.cpp).
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_bounties_cache` (
  `col` TINYINT UNSIGNED NOT NULL COMMENT '1 to 5, dc_bounties.col',
  `entry` INT UNSIGNED NOT NULL COMMENT 'item_template of the cache',
  `reagent_entry` INT UNSIGNED NOT NULL COMMENT 'the act reagent, an account material (account_economy.csv)',
  PRIMARY KEY (`col`),
  UNIQUE KEY `dc_bounties_cache_entry` (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS `dc_bounties_cache_legendary` (
  `col` TINYINT UNSIGNED NOT NULL,
  `item_entry` INT UNSIGNED NOT NULL COMMENT 'dc_base_item of a legendary',
  PRIMARY KEY (`col`, `item_entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `dc_bounties_cache_legendary`;
DELETE FROM `dc_bounties_cache`;
DELETE FROM `item_template` WHERE `entry` IN ({ids});
INSERT INTO `item_template`
  (`entry`, `class`, `subclass`, `name`, `displayid`, `Quality`, `Flags`, `BuyCount`, `BuyPrice`, `SellPrice`,
   `InventoryType`, `maxcount`, `stackable`, `BagFamily`, `Material`, `bonding`, `ItemLevel`, `description`)
VALUES
{items};
INSERT INTO `dc_bounties_cache` (`col`, `entry`, `reagent_entry`) VALUES
{rows};
"""
    if pools:
        out += f"INSERT INTO `dc_bounties_cache_legendary` (`col`, `item_entry`) VALUES\n{pools};\n"
    return out


def world_map_areas(path=WORLD_MAP_AREA):
    """{(map id, area id): [WorldMapArea row ids]} of the client's WorldMapArea.dbc (3.3.5a: id, map, area first)."""
    import struct
    raw = Path(path).read_bytes()
    magic, count, _fields, size, _strings = struct.unpack_from("<4s4I", raw)
    if magic != b"WDBC":
        raise ValueError(f"{path}: not a DBC")
    out = {}
    for n in range(count):
        row, map_id, area = struct.unpack_from("<3I", raw, 20 + n * size)
        out.setdefault((map_id, area), []).append(row)
    return out


def quests(directory=None, areas_path=WORLD_MAP_AREA):
    """[(quest id, bounty id, n, target, (title, quest text, objective text), zone row, world map area)]: a Kill bounty's one
    quest per named target it can draw (diablocraft-hyoic.2; target is the creature entry), a Click bounty's n = 1 to its
    spots (target 0)."""
    areas = world_map_areas(areas_path)
    out, ids = [], iter(QUEST_ENTRIES)
    named = targets(directory)
    # Numbered in the zone sheet's order, then the target sheet's, not the bounty id's (diablocraft-hyoic.1: the columns
    # became acts): the client caches a quest by id, and a zone added at the sheet's end takes the next ones.
    # ponytail: zones x targets quests in a block of 100; widen QUEST_ENTRIES (the generator refuses past it) as acts fill.
    order = [z["key"] for z in read("rift_open_zones.csv", Path(directory or D3))]
    for bid, row, zone, anchors in sorted(catalogue(directory), key=lambda b: (order.index(b[2]["key"]), b[0])):
        found = areas.get((int(zone["map_id"]), int(zone["zone_id"])), [])
        if len(found) != 1:
            raise ValueError(f"bounty {bid}: WorldMapArea.dbc has {len(found)} rows for map {zone['map_id']} zone "
                             f"{zone['zone_id']}; the map marks need exactly one")
        if row["type"] == "kill":
            each = [(1, int(t["entry"]), kill_words(t, zone)) for t in named]
        else:
            each = [(n, 0, (row["title"], row["quest_text"], row["objective_text"])) for n in range(1, len(anchors) + 1)]
        for n, target, words in each:
            quest = next(ids, None)
            if quest is None:
                raise ValueError(f"the bounty quests outgrow {QUEST_ENTRIES.start}-{QUEST_ENTRIES.stop - 1}")
            out.append((quest, bid, n, target, words, zone, found[0]))
    return out


def render_quests(directory=None, areas_path=WORLD_MAP_AREA):
    rows = quests(directory, areas_path)
    ids = ", ".join(str(q[0]) for q in rows)
    templates = ",\n".join(
        f"  ({quest}, 2, -1, 0, {int(zone['zone_id'])}, 0, 0, 0, 0, {QUEST_FLAGS}, 0, 0, 0, {quote(title)}, "
        f"{quote(text)}, {quote(text)}, '', {CREDIT_CREATURE}, {n}, {quote(objective)})"
        for quest, _bid, n, _target, (title, text, objective), zone, _area in rows)
    addons = ",\n".join(f"  ({quest}, 1)" for quest, *_ in rows)
    links = ",\n".join(f"({bid}, {n}, {target}, {quest}, {area})" for quest, bid, n, target, _words, _zone, area in rows)
    return f"""-- Generated by generate_bounties.py from bounties.csv, bounty_targets.csv and client-patch/dbc/WorldMapArea.dbc (diablocraft-dm9vg.17); never edit.
-- Bounties as quests: the bounty of the zone you stand in shows in the quest log and tracker (src/bounties/dc_bounty_quests.cpp).
-- One quest a bounty, count and named target (a Kill's, drawn per board from bounty_targets.csv, diablocraft-hyoic.2); zero
-- rewards (the Horadric Cache is the bounty's reward, W4), not sharable, repeatable. The table is the generator's alone, so
-- it is rebuilt whole.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_bounties_quest`;
CREATE TABLE `dc_bounties_quest` (
  `bounty_id` INT UNSIGNED NOT NULL,
  `need` TINYINT UNSIGNED NOT NULL COMMENT 'the count the quest asks: 1 for a Kill, the drawn objectives for a Click',
  `target` INT UNSIGNED NOT NULL COMMENT 'a Kill''s named target (dc_bounties_target.entry); 0 for a Click',
  `quest_id` INT UNSIGNED NOT NULL,
  `poi_area` INT UNSIGNED NOT NULL COMMENT 'WorldMapArea row the map marks go on (the copy''s clone of the zone)',
  PRIMARY KEY (`bounty_id`, `need`, `target`),
  UNIQUE KEY `quest_id` (`quest_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
DELETE FROM `quest_template_addon` WHERE `ID` BETWEEN {QUEST_ENTRIES.start} AND {QUEST_ENTRIES.stop - 1};
DELETE FROM `quest_template` WHERE `ID` BETWEEN {QUEST_ENTRIES.start} AND {QUEST_ENTRIES.stop - 1};
INSERT INTO `quest_template`
  (`ID`, `QuestType`, `QuestLevel`, `MinLevel`, `QuestSortID`, `QuestInfoID`,
   `SuggestedGroupNum`, `TimeAllowed`, `AllowableRaces`, `Flags`, `RewardXPDifficulty`,
   `RewardMoney`, `RewardMoneyDifficulty`, `LogTitle`, `LogDescription`, `QuestDescription`,
   `QuestCompletionLog`, `RequiredNpcOrGo1`, `RequiredNpcOrGoCount1`, `ObjectiveText1`)
VALUES
{templates};
INSERT INTO `quest_template_addon` (`ID`, `SpecialFlags`) VALUES
{addons};
INSERT INTO `dc_bounties_quest` (`bounty_id`, `need`, `target`, `quest_id`, `poi_area`) VALUES
{links};
-- quest ids: {ids}
"""


def render_quest_credit():
    first, last = QUEST_ENTRIES.start, QUEST_ENTRIES.stop - 1
    return f"""-- Generated by generate_bounties.py (diablocraft-dm9vg.20); never edit.
-- The bounty quests' own credit creature: bounties_0005 put them on the rifts' 910015, and dc_rifts.cpp reads every quest on
-- 910015 as a rift bar (exactly one untimed, one timed), so loading threw and rifts went off. Never spawned; the module
-- writes the counts itself (src/bounties/dc_bounty_quests.cpp). A copy of stock {CREDIT_CLONE_OF}, as rifts_0011 makes 910015.
DELETE FROM `creature_template` WHERE `entry` = {CREDIT_CREATURE};
CREATE TEMPORARY TABLE `dc_bounty_credit_template` LIKE `creature_template`;
INSERT INTO `dc_bounty_credit_template` SELECT * FROM `creature_template` WHERE `entry` = {CREDIT_CLONE_OF};
UPDATE `dc_bounty_credit_template` SET
  `entry` = {CREDIT_CREATURE}, `name` = 'Bounty Progress', `subname` = '',
  `npcflag` = 0, `ScriptName` = '', `AIName` = '', `gossip_menu_id` = 0,
  `lootid` = 0, `pickpocketloot` = 0, `skinloot` = 0,
  `KillCredit1` = 0, `KillCredit2` = 0;
INSERT INTO `creature_template` SELECT * FROM `dc_bounty_credit_template`;
DROP TEMPORARY TABLE `dc_bounty_credit_template`;
DELETE FROM `creature_template_model` WHERE `CreatureID` = {CREDIT_CREATURE};
UPDATE `quest_template` SET `RequiredNpcOrGo1` = {CREDIT_CREATURE} WHERE `ID` BETWEEN {first} AND {last};
"""


def render_cache_binding(directory=None):
    ids = ",".join(str(c[1]) for c in caches(directory))
    return f"""-- Generated by generate_bounties.py from bounty_caches.csv (diablocraft-dm9vg.9); never edit.
-- The Horadric Caches are account-bound, like D3's (the designer, decisions 2026-10-12 (2), reversing bonding 0): the core's
-- bind-to-account flag and bind on pickup. Trade is gold only already (dc_trade_rule.h); this keeps mail to the account.
UPDATE `item_template` SET `Flags` = `Flags` | {ITEM_FLAG_IS_BOUND_TO_ACCOUNT}, `bonding` = {BIND_ON_PICKUP} WHERE `entry` IN ({ids});
"""


def generate():
    for name, sql in ((NAME, render()), (OBJECTIVES, render_objectives()), (CACHES, render_caches()),
                      (BOUND, render_cache_binding()), (QUESTS, render_quests()),
                      (CREDIT, render_quest_credit())):
        target = MODULE / "data/sql/db-world/updates" / name
        write_migration(MODULE, target, sql)
        write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / name, sql)], label="bounty rows")
        print(f"Generated {name}")


if __name__ == "__main__":
    generate()
