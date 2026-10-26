"""Kanai's Cube: the object and the recipe rows (diablocraft-wpt7l.4; plan docs/research/kanais-cube.md 6.1 and 7 row 4).

Two sheets:

* data/d3/cube_object.csv: the Cube's own gameobject template (type 22, so a player can click it; stock display 6896, the
  Magtheridon cube model) and the designer's placement at guid 8001659 in the Sanctum. His dev row keeps its spot: only its entry moves
  from stock 181713 (which carries Magtheridon's script) to ours. An install without the row gets it at the sheet's position.
* data/d3/cube_rules.csv: one row per cost line of a recipe (as mystic_rules.csv does): what it spends from the account ledger
  and, for a `convert` recipe, what it makes for each rarity of the controlling item. No number is typed in C++. A
  `set_convert` (Skill of Nilfur), `rare_upgrade` (Hope of Cain), `reforge` (Law of Kulle) or `primal_upgrade` (Curiosity of
  Lorath Nahr) recipe consumes the item and rolls a new one, so it makes no material (diablocraft-wpt7l.7, .9, .6); what each
  takes is dc_cube_rule.h's. An `extract` recipe (Archive of Tal Rasha, diablocraft-wpt7l.10) consumes a legendary item and
  rolls nothing: the account learns the item's power (dc_cube_power), so it makes no material either. An `augment` recipe (Caldesann's Despair, diablocraft-wpt7l.8) keeps the item and consumes bag
  gems: its `take` lines name them (the line's rarity column is the gem class, `legendary_gem` or a normal gem's tier from
  gems.csv, the amount how many; no ledger entry), and data/d3/cube_augment.csv says what the gems add.
* data/d3/cube_slots.csv: the Cube's power slots (Weapon, Armor, Jewelry) and the base item slots each one takes (the
  legendary power lists are read from dc_base_item by these; no slot is named in C++). data/d3/cube_pages.csv: one recipe
  page's text (subtitle, the item line, the red note, the quote and its source) for the Recipes panel
  (diablocraft-g0t7i; docs/contracts/cube-messages.md). data/d3/cube_augment.csv: what Caldesann's Despair adds
  (the attribute of each gem colour, the amount a rank gives, the smallest Legendary Gem rank for each power slot).

    python3 mod-diablocraft/scripts/generate/crafting/generate_cube.py [--migration data/sql/db-world/updates/<new>.sql]

Writes cube_0001_pages.sql (the slots and the pages), world_0042_kanais_cube.sql (and its data/generated mirror), which is applied with the three Iben Fahd conversions and keeps
them, and world_0044_cube_recipes.sql, which rewrites every recipe row from the sheet (diablocraft-wpt7l.7). The file is a world_ migration on purpose: guid 8001659 was
one of the Sanctum's retired tier copies, and world_0037 refuses to run while a retired guid holds another entry, so the Cube's
row must come after it in filename order.

Once world_0044 is applied (applied_migrations.py: on live or on dev), a changed cube_rules.csv ships as a new numbered world
migration carrying the same full rewrite: --migration names it, and its data/generated mirror takes its name, as
generate_wings.py does. world_0053_cube_recipe_order.sql is the first (the page order, decisions.md 2026-10-16).
"""
import argparse
import csv
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import require_companion_migration, write_coupled_outputs, write_migration  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
DATA = MODULE / "data/d3"
NAME = "world_0042_kanais_cube.sql"
RECIPES = "world_0044_cube_recipes.sql"
PAGES = "cube_0001_pages.sql"
AUGMENT = "cube_0002_augment.sql"
EXCLUDED = "cube_0003_excluded.sql"
APPLIED_0042 = ("iben_pleasure", "iben_regret", "iben_wrath")  # world_0042 as applied on dev; world_0044 carries the rest
STOCK_ENTRY = 181713  # the stock Manticron Cube the designer placed (gameobject_template.sql: type 10, go_manticron_cube)
SPELLCASTER = 22  # GAMEOBJECT_TYPE_SPELLCASTER: clickable by type with no quest (world_0006_hub_object_use.sql)
RULES = ("convert", "set_convert", "rare_upgrade", "reforge", "primal_upgrade", "augment", "extract")
KINDS = ("spend", "make", "take")
LEGENDARY_GEM = "legendary_gem"  # a take line's class for the 21 legendary gems; any other class is a normal gem's tier (gems.csv)
AUGMENT_STATS = ("str", "dex", "int", "vit")  # the main-stat affix ids dc_items_data.cpp Mappings() knows
RARITIES = ("normal", "magic", "rare", "legendary", "set")
# The window bridge's limits (docs/contracts/window-bridge.md): a recipe id travels as a Request::Token (letters, digits, _),
# and a recipe's record must stay under the 255-byte cap with its name in it.
TOKEN = re.compile(r"^[a-z0-9_]{1,24}$")
MAX_NAME = 64
FORBIDDEN = set("|\t")
PLACEHOLDER = "PLACEHOLDER"
# A page's P and Q records must stay under the wire cap with the prefix and the record letter (window-bridge.md): the longest
# text the sheet may hold, in bytes, counting the fields and their separators.
MAX_PAGE_RECORD = 240
MAX_LABEL = 16
# The grid is 3x3 and the item takes one cell: a recipe has at most this many reagents (dc_cube_window.h CubeReagentCells).
MAX_REAGENTS = 8


class CubeError(ValueError):
    pass


def read(name, directory=None):
    with (Path(directory or DATA) / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def whole(text, what, low=0):
    try:
        value = int(text)
    except ValueError:
        raise CubeError(f"{what}: {text!r} is not a whole number") from None
    if value < low:
        raise CubeError(f"{what}: {value} is below {low}")
    return value


def gem_tiers(directory=None):
    return {r["tier"] for r in read("gems.csv", directory) if r["is_legendary"] == "0"}


def materials(directory=None):
    """Entries of the account ledger's materials (account_economy.csv kind material)."""
    return {int(r["item_entry"]) for r in read("account_economy.csv", directory) if r["kind"] == "material"}


def recipes(directory=None):
    """[(recipe id, sort, rule, name, [lines])], checked, in sort order; a line is (line, kind, rarity, entry, amount)."""
    ledger = materials(directory)
    tiers = gem_tiers(directory)
    found = {}
    for row in read("cube_rules.csv", directory):
        rid = row["recipe_id"]
        if not TOKEN.match(rid):
            raise CubeError(f"cube_rules.csv: recipe id {rid!r} must be 1-24 of a-z, 0-9 and _")
        name = row["name"].strip()
        if not name or len(name.encode()) > MAX_NAME or FORBIDDEN & set(name):
            raise CubeError(f"cube_rules.csv {rid}: the name must be 1-{MAX_NAME} bytes with no '|' or tab")
        if row["rule"] not in RULES:
            raise CubeError(f"cube_rules.csv {rid}: rule {row['rule']!r} is not one of {RULES}")
        head = (whole(row["sort"], f"{rid} sort", 1), row["rule"], name)
        recipe = found.setdefault(rid, (head, []))
        if recipe[0] != head:
            raise CubeError(f"cube_rules.csv {rid}: every line of a recipe repeats its sort, rule and name")
        kind, rarity = row["kind"], row["rarity"]
        if kind not in KINDS:
            raise CubeError(f"cube_rules.csv {rid}: kind {kind!r} is not one of {KINDS}")
        if (kind == "make") != (rarity in RARITIES) and kind != "take" or (kind == "spend" and rarity):
            raise CubeError(f"cube_rules.csv {rid}: a make line names the controlling item's rarity, a spend line none")
        if kind == "take":
            if rarity != LEGENDARY_GEM and rarity not in tiers:
                raise CubeError(f"cube_rules.csv {rid}: a take line names {LEGENDARY_GEM} or a normal gem tier of gems.csv, not {rarity!r}")
            entry = whole(row["item_entry"], f"{rid} item_entry")
            if entry:
                raise CubeError(f"cube_rules.csv {rid}: a take line names a class of bag item, so its item_entry is 0")
        else:
            entry = whole(row["item_entry"], f"{rid} item_entry")
            if entry not in ledger:
                raise CubeError(f"cube_rules.csv {rid}: {entry} is not an account ledger material (account_economy.csv)")
        recipe[1].append((whole(row["line"], f"{rid} line", 1), kind, rarity, entry, whole(row["amount"], f"{rid} amount", 1)))
    out = []
    for rid, ((sort, rule, name), lines) in found.items():
        if len({line[0] for line in lines}) != len(lines):
            raise CubeError(f"cube_rules.csv {rid}: two lines share a number")
        spends = [line[3] for line in lines if line[1] == "spend"]
        makes = [line[2] for line in lines if line[1] == "make"]
        takes = [line[2] for line in lines if line[1] == "take"]
        if not spends and not takes:
            raise CubeError(f"cube_rules.csv {rid}: a recipe spends or takes something")
        if bool(takes) != (rule == "augment"):
            raise CubeError(f"cube_rules.csv {rid}: an augment recipe takes bag gems, and no other recipe takes bag items")
        if len(set(takes)) != len(takes):
            raise CubeError(f"cube_rules.csv {rid}: one take line a gem class")
        if rule == "convert" and not makes:
            raise CubeError(f"cube_rules.csv {rid}: a convert recipe makes something")
        if rule != "convert" and makes:
            raise CubeError(f"cube_rules.csv {rid}: a {rule} recipe makes no material: it rolls an item")
        if len(set(spends)) != len(spends) or len(set(makes)) != len(makes):
            raise CubeError(f"cube_rules.csv {rid}: one spend line a material, one make line a rarity")
        cells = len(spends) + sum(line[4] for line in lines if line[1] == "take")  # a gem is a cell of its own
        if cells > MAX_REAGENTS:
            raise CubeError(f"cube_rules.csv {rid}: a recipe has at most {MAX_REAGENTS} reagents, the grid's cells less the item's")
        out.append((rid, sort, rule, name, sorted(lines)))
    if len({r[1] for r in out}) != len(out):
        raise CubeError("cube_rules.csv: two recipes share a sort")
    # The grid names no recipe: the server finds the one whose reagents it holds (dc_cube_rule.h Match), so two recipes never
    # spend the same materials, or take the same gems, in the same amounts.
    spent = [frozenset((line[1], line[2], line[3], line[4]) for line in lines if line[1] != "make") for _, _, _, _, lines in out]
    if len(set(spent)) != len(spent):
        raise CubeError("cube_rules.csv: two recipes spend the same reagents, so the grid could not tell them apart")
    return sorted(out, key=lambda r: r[1])


def cube_object(directory=None):
    """The one row of cube_object.csv, checked, as a dict of typed values; orientation 0 when it is a PLACEHOLDER."""
    rows = read("cube_object.csv", directory)
    if len(rows) != 1:
        raise CubeError("cube_object.csv: exactly one row, the Cube")
    row = rows[0]
    taken = {int(r["entry"]) for r in read("world_objects.csv", directory)}
    out = {k: whole(row[k], k) for k in ("entry", "display_id", "guid", "map", "zone", "area")}
    if out["entry"] in taken or out["entry"] == STOCK_ENTRY:
        raise CubeError(f"cube_object.csv: entry {out['entry']} is taken")
    name = row["name"].strip()
    if not name or FORBIDDEN & set(name):
        raise CubeError("cube_object.csv: a name with no '|' or tab")
    out["name"] = name
    for key in ("size", "x", "y", "z"):
        try:
            out[key] = float(row[key])
        except ValueError:
            raise CubeError(f"cube_object.csv: {key} {row[key]!r} is not a number") from None
        if not math.isfinite(out[key]):
            raise CubeError(f"cube_object.csv: {key} is not finite")
    if out["size"] <= 0:
        raise CubeError("cube_object.csv: the size is above 0")
    out["orientation"] = 0.0 if row["orientation"] == PLACEHOLDER else float(row["orientation"])
    return out


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def number(value):
    return format(value, ".9g")


def recipe_inserts(rows):
    recipe_rows = ",\n".join(f"({quote(rid)},{sort},{quote(rule)},{quote(name)})" for rid, sort, rule, name, _ in rows)
    line_rows = ",\n".join(f"({quote(rid)},{line},{quote(kind)},{quote(rarity)},{entry},{amount})"
                           for rid, _, _, _, lines in rows for line, kind, rarity, entry, amount in lines)
    return f"""INSERT INTO `dc_cube_recipe` (`recipe_id`,`sort`,`rule`,`name`) VALUES
{recipe_rows};
INSERT INTO `dc_cube_rule` (`recipe_id`,`line`,`kind`,`rarity`,`item_entry`,`amount`) VALUES
{line_rows};"""


def render(directory=None):
    cube = cube_object(directory)
    rows = [r for r in recipes(directory) if r[0] in APPLIED_0042]
    o = cube["orientation"]
    rotation = (0.0, 0.0, math.sin(o / 2), math.cos(o / 2))  # a turn about the vertical axis only, as the Sanctum's rows are
    data = [0] * 24
    data[3] = 1  # allowMounted: a UI click never dismounts (world_0006); Data0 spellId 0, the module answers the click first
    template = ([cube["entry"], SPELLCASTER, cube["display_id"], quote(cube["name"]), "''", "''", "''", number(cube["size"])]
                + data + ["''", "''", 12340])
    spot = [cube["guid"], cube["entry"], cube["map"], cube["zone"], cube["area"], 1, 1, number(cube["x"]), number(cube["y"]),
            number(cube["z"]), number(o)] + [number(r) for r in rotation] + [300, 0, 1, "''", "NULL", "NULL"]
    columns = ",".join(f"`{c}`" for c in ["entry", "type", "displayId", "name", "IconName", "castBarCaption", "unk1", "size"]
                       + [f"Data{i}" for i in range(24)] + ["AIName", "ScriptName", "VerifiedBuild"])
    spawn_columns = ",".join(f"`{c}`" for c in ("guid", "id", "map", "zoneId", "areaId", "spawnMask", "phaseMask", "position_x",
                                                 "position_y", "position_z", "orientation", "rotation0", "rotation1", "rotation2",
                                                 "rotation3", "spawntimesecs", "animprogress", "state", "ScriptName",
                                                 "VerifiedBuild", "Comment"))
    guid = cube["guid"]
    return f"""-- Generated by generate_cube.py from data/d3/cube_object.csv and data/d3/cube_rules.csv (diablocraft-wpt7l.4); never edit.
-- Kanai's Cube: its own clickable template on the model the designer placed, his placement moved onto it, and the recipe rows the Cube
-- window reads (docs/contracts/cube-messages.md). Apply to the world database.
SET NAMES utf8mb4;
CREATE TEMPORARY TABLE dc_cube_guard (ok INT NOT NULL CHECK(ok=1));

DROP TABLE IF EXISTS `dc_cube_rule`;
DROP TABLE IF EXISTS `dc_cube_recipe`;
CREATE TABLE `dc_cube_recipe` (
  `recipe_id` VARCHAR(24) NOT NULL,
  `sort` INT UNSIGNED NOT NULL,
  `rule` VARCHAR(16) NOT NULL,
  `name` VARCHAR({MAX_NAME}) NOT NULL,
  PRIMARY KEY (`recipe_id`),
  UNIQUE KEY (`sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Kanai''s Cube recipes (cube_rules.csv)';
CREATE TABLE `dc_cube_rule` (
  `recipe_id` VARCHAR(24) NOT NULL,
  `line` INT UNSIGNED NOT NULL,
  `kind` ENUM('spend','make') NOT NULL,
  `rarity` VARCHAR(16) NOT NULL DEFAULT '',
  `item_entry` INT UNSIGNED NOT NULL,
  `amount` BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (`recipe_id`,`line`),
  FOREIGN KEY (`recipe_id`) REFERENCES `dc_cube_recipe` (`recipe_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Kanai''s Cube cost lines (cube_rules.csv)';
{recipe_inserts(rows)}

-- The template: type 22 with no spell, so the click reaches the module and nothing else (stock {STOCK_ENTRY} would run
-- go_manticron_cube, Magtheridon's fight).
DELETE FROM `gameobject_template` WHERE `entry` = {cube["entry"]};
INSERT INTO `gameobject_template` ({columns}) VALUES
({",".join(str(v) for v in template)});

-- The designer's row keeps its place; only its entry moves to the Cube's own. An install without that row gets one at the sheet's spot.
UPDATE `gameobject` SET `id` = {cube["entry"]} WHERE `guid` = {guid} AND `id` = {STOCK_ENTRY};
INSERT INTO `gameobject` ({spawn_columns})
SELECT {",".join(str(v) for v in spot)} FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `gameobject` WHERE `guid` = {guid});
-- Stops here if that guid holds something else: the Cube would be missing, so say so.
INSERT INTO dc_cube_guard VALUES ((EXISTS(SELECT 1 FROM `gameobject` WHERE `guid` = {guid} AND `id` = {cube["entry"]})));
DROP TEMPORARY TABLE dc_cube_guard;
"""


def render_recipes(directory=None):
    return f"""-- Generated by generate_cube.py from data/d3/cube_rules.csv (diablocraft-wpt7l.7); never edit.
-- Every Kanai's Cube recipe, rewritten from the sheet: world_0042 made the tables with the three Iben Fahd conversions, and
-- this adds Skill of Nilfur, Hope of Cain, Law of Kulle, Curiosity of Lorath Nahr, Caldesann's Despair and the Archive of Tal Rasha (docs/contracts/cube-messages.md).
-- Apply to the world database.
SET NAMES utf8mb4;
-- Caldesann's Despair takes bag gems: its `take` lines (world_0042 made the column with spend and make only; MODIFY to the same type is a no-op).
ALTER TABLE `dc_cube_rule` MODIFY COLUMN `kind` ENUM('spend','make','take') NOT NULL;
DELETE FROM `dc_cube_rule`;
DELETE FROM `dc_cube_recipe`;
{recipe_inserts(recipes(directory))}
"""


def slots(directory=None):
    """{slot number: (label, [base item slots])}, checked: numbered 1.. with no gap, each item slot in one Cube slot only."""
    known = {r["slot"] for r in read("base_items.csv", directory)}
    found, owner = {}, {}
    for row in read("cube_slots.csv", directory):
        number = whole(row["slot"], "cube_slots.csv slot", 1)
        label = row["label"].strip()
        if not label or len(label.encode()) > MAX_LABEL or FORBIDDEN & set(label) or ":" in label:
            raise CubeError(f"cube_slots.csv: the label {label!r} must be 1-{MAX_LABEL} bytes with no '|', ':' or tab")
        if found.setdefault(number, (label, []))[0] != label:
            raise CubeError(f"cube_slots.csv slot {number}: every row of a slot repeats its label")
        item = row["item_slot"].strip()
        if item not in known:
            raise CubeError(f"cube_slots.csv: {item!r} is not an item slot of base_items.csv")
        if item in owner:
            raise CubeError(f"cube_slots.csv: {item!r} is in two Cube slots")
        owner[item] = number
        found[number][1].append(item)
    if not found or sorted(found) != list(range(1, len(found) + 1)):
        raise CubeError("cube_slots.csv: the slots are numbered 1 upward with no gap")
    return found


def excluded(directory=None):
    """[(d3_id, reason)] of cube_excluded.csv, checked: each a legendary pool item of base_items.csv, listed once."""
    items = {r["d3_id"]: r for r in read("base_items.csv", directory)}
    out, seen = [], set()
    for row in read("cube_excluded.csv", directory):
        d3_id, reason = row["d3_id"].strip(), row["reason"].strip()
        if items.get(d3_id, {}).get("rarity") != "legendary":
            raise CubeError(f"cube_excluded.csv: {d3_id!r} is not a legendary item of base_items.csv")
        if d3_id in seen:
            raise CubeError(f"cube_excluded.csv: {d3_id} is listed twice")
        if not reason or not row["source"].strip():
            raise CubeError(f"cube_excluded.csv {d3_id}: a reason and its source")
        seen.add(d3_id)
        out.append((d3_id, reason))
    return out


def render_excluded(directory=None):
    rows = ",\n".join(f"({quote(d3_id)})" for d3_id, _ in sorted(excluded(directory)))
    return f"""-- Generated by generate_cube.py from data/d3/cube_excluded.csv (diablocraft-rclu6); never edit.
-- The legendary items whose power Kanai's Cube never lists, extracts or lets a slot hold (D3 marks them cube: false): the Cube's
-- power query (dc_cube.cpp CubePowerItems) skips them. Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_cube_excluded`;
CREATE TABLE `dc_cube_excluded` (
  `d3_id` VARCHAR(48) NOT NULL,
  PRIMARY KEY (`d3_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Items whose power the Cube refuses (cube_excluded.csv)';
INSERT INTO `dc_cube_excluded` (`d3_id`) VALUES
{rows};
"""


AUGMENT_PARTS = ("colour", "per_rank", "min_rank")


def augment(directory=None):
    """[(part, key, value)] of cube_augment.csv, checked: every colour row is a gem colour of gems.csv with an attribute (a main stat the stat
    read knows), no two the same, one amount per rank, and every power slot of cube_slots.csv a smallest Legendary Gem rank."""
    colours = {r["colour"] for r in read("gems.csv", directory) if r["is_legendary"] == "0"}
    labels = {label for label, _ in slots(directory).values()}
    out, seen = [], set()
    for row in read("cube_augment.csv", directory):
        part, key, value = row["part"], row["key"].strip(), row["value"].strip()
        if part not in AUGMENT_PARTS:
            raise CubeError(f"cube_augment.csv: part {part!r} is not one of {AUGMENT_PARTS}")
        if (part, key) in seen:
            raise CubeError(f"cube_augment.csv: two rows for {part} {key!r}")
        seen.add((part, key))
        if part == "colour" and (key not in colours or value not in AUGMENT_STATS):
            raise CubeError(f"cube_augment.csv: colour {key!r} must be a gem colour of gems.csv with an attribute of {AUGMENT_STATS}")
        if part == "min_rank" and key not in labels:
            raise CubeError(f"cube_augment.csv: min_rank {key!r} is not a power slot label of cube_slots.csv")
        if part == "per_rank" and key:
            raise CubeError("cube_augment.csv: per_rank has no key")
        if part != "colour":
            whole(value, f"cube_augment.csv {part} {key}", 1)
        out.append((part, key, value))
    if len({v for p, _, v in out if p == "colour"}) != len([1 for p, _, _ in out if p == "colour"]):
        raise CubeError("cube_augment.csv: two colours add the same attribute")
    if sum(p == "per_rank" for p, _, _ in out) != 1:
        raise CubeError("cube_augment.csv: exactly one per_rank row")
    if {k for p, k, _ in out if p == "min_rank"} != labels:
        raise CubeError(f"cube_augment.csv: a min_rank row for each power slot {sorted(labels)}")
    return out


def render_augment(directory=None):
    rows = ",\n".join(f"({quote(part)},{quote(key)},{quote(value)})" for part, key, value in augment(directory))
    return f"""-- Generated by generate_cube.py from data/d3/cube_augment.csv (diablocraft-wpt7l.8); never edit.
-- Caldesann's Despair: the attribute each gem colour adds, the amount a rank gives and the smallest Legendary Gem rank for each
-- Cube power slot (docs/contracts/cube-messages.md). Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_cube_augment`;
CREATE TABLE `dc_cube_augment` (
  `part` ENUM('colour','per_rank','min_rank') NOT NULL,
  `key` VARCHAR({MAX_LABEL}) NOT NULL,
  `value` VARCHAR(8) NOT NULL,
  PRIMARY KEY (`part`,`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Caldesann''s Despair (cube_augment.csv)';
INSERT INTO `dc_cube_augment` (`part`,`key`,`value`) VALUES
{rows};
"""


def pages(directory=None):
    """{recipe id: (subtitle, item, note, quote, quote source)}, one row for every recipe of cube_rules.csv, each text checked
    for the wire: no '|' or tab, and the P and Q records under MAX_PAGE_RECORD bytes."""
    ids = {r[0] for r in recipes(directory)}
    out = {}
    for row in read("cube_pages.csv", directory):
        rid = row["recipe_id"]
        if rid not in ids:
            raise CubeError(f"cube_pages.csv: {rid!r} is not a recipe of cube_rules.csv")
        if rid in out:
            raise CubeError(f"cube_pages.csv: {rid} has two rows")
        text = tuple(row[k].strip() for k in ("subtitle", "item", "note", "quote", "quote_source"))
        if any(FORBIDDEN & set(part) for part in text):
            raise CubeError(f"cube_pages.csv {rid}: no '|' or tab in a text")
        if not text[0] or not text[1]:
            raise CubeError(f"cube_pages.csv {rid}: a page has a subtitle and an item line")
        if bool(text[3]) != bool(text[4]):
            raise CubeError(f"cube_pages.csv {rid}: a quote and its source go together")
        head = "|".join(("P", rid) + text[:3])
        quote = "|".join(("Q", rid) + text[3:])
        if max(len(head.encode()), len(quote.encode())) > MAX_PAGE_RECORD:
            raise CubeError(f"cube_pages.csv {rid}: a page record is over {MAX_PAGE_RECORD} bytes")
        out[rid] = text
    missing = ids - set(out)
    if missing:
        raise CubeError(f"cube_pages.csv: no page for {sorted(missing)}")
    return out


def render_pages(directory=None):
    slot_rows = ",\n".join(f"({n},{quote(label)},{quote(item)})" for n, (label, items) in sorted(slots(directory).items())
                           for item in items)
    page_rows = ",\n".join(f"({quote(rid)},{','.join(quote(part) for part in text)})"
                           for rid, text in sorted(pages(directory).items()))
    return f"""-- Generated by generate_cube.py from data/d3/cube_slots.csv and data/d3/cube_pages.csv (diablocraft-g0t7i); never edit.
-- Kanai's Cube: the power slots and the base item slots each takes, and the text of each recipe page
-- (docs/contracts/cube-messages.md). Apply to the world database.
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `dc_cube_slot_item`;
DROP TABLE IF EXISTS `dc_cube_page`;
CREATE TABLE `dc_cube_slot_item` (
  `slot` TINYINT UNSIGNED NOT NULL,
  `label` VARCHAR({MAX_LABEL}) NOT NULL,
  `item_slot` VARCHAR(16) NOT NULL,
  PRIMARY KEY (`item_slot`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Kanai''s Cube power slots (cube_slots.csv)';
CREATE TABLE `dc_cube_page` (
  `recipe_id` VARCHAR(24) NOT NULL,
  `subtitle` VARCHAR(64) NOT NULL,
  `item` VARCHAR(96) NOT NULL,
  `note` VARCHAR(96) NOT NULL,
  `quote` VARCHAR(256) NOT NULL,
  `quote_source` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`recipe_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Kanai''s Cube recipe page text (cube_pages.csv)';
INSERT INTO `dc_cube_slot_item` (`slot`,`label`,`item_slot`) VALUES
{slot_rows};
INSERT INTO `dc_cube_page` (`recipe_id`,`subtitle`,`item`,`note`,`quote`,`quote_source`) VALUES
{page_rows};
"""


def generate(migration=None):
    updates = MODULE / "data/sql/db-world/updates"
    recipes = Path(migration) if migration else updates / RECIPES
    # Before any write: a migration the updater never reads would publish the mirror without a DB change.
    recipes = require_companion_migration(MODULE, recipes, updates)
    for target, sql in ((updates / NAME, render()), (recipes, render_recipes()), (updates / PAGES, render_pages()),
                        (updates / AUGMENT, render_augment()), (updates / EXCLUDED, render_excluded())):
        write_migration(MODULE, target, sql)
        write_coupled_outputs(MODULE, target, sql, [(MODULE / "data/generated" / target.name, sql)], label="Kanai's Cube rows")
        print(f"Generated {target.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration", type=Path, help="the new world migration for a changed cube_rules.csv")
    generate(parser.parse_args().migration)
