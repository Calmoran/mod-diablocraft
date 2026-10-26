#!/usr/bin/env python3
"""A class the stock tables do not hold: the rows a new WoW class id needs at creation (diablocraft-1cuvw, the Monk).

data/d3/class_creation.csv names each created class (d3_class), the stock class it is copied from (parent_wow_class_id)
and the migration that carries the server rows. Everything else is read: the id, the power slot and the name from
class_map.csv, the races from client-patch/dbc/build_charbaseinfo.py (every race, as the Barbarian and Wizard), the
parent's rows from the stock DBC files extracted for the server (azerothcore-wotlk/build/server/data/dbc) or, for
the SQL tables, from the live world database when the migration runs. The parent is copied once, at creation; the new
class keeps no link to it (ruling 2026-10-12).

What it writes, following docs/research/custom-class-inventory.md section 5 and docs/contracts/monk-class.md:

  server (one migration per created class, world database)
    chrclasses_dbc            the ChrClasses row: the parent's, with the id, file token, name and power slot
    playercreateinfo          one row per race, at the parent's spawn (the hub; later hub moves update every class)
    playercreateinfo_action   the stock Attack button the parent's bar shares with every class; the class start
                              rewrites the skill buttons at login (dc_classes.cpp WriteActionBar)
    player_class_stats        the parent's rows for every level (the core exits when a class has none)
    charstartoutfit_dbc       the parent's outfit rows, one per race and sex
    skillraceclassinfo_dbc    the new class's bit on the skills every stock class but the Death Knight shares
                              (Defense, Unarmed, languages, racials, professions); its weapons are
                              generate_class_proficiencies.py's
    gt*_dbc                   a slice per class-indexed Gt table, copied from the parent's slice
  client (client-patch/dbc)
    ChrClasses.dbc, CharBaseInfo.dbc, CharStartOutfit.dbc, SkillRaceClassInfo.dbc and the nine Gt files, each the
    same rows as the server's, so the client and the core agree; ChrClasses' SpellClassSet alone differs, the client's being
    the family of the class's records (the server keeps the parent's, see render).

Preview outfits (diablocraft-mb9fn, ruling 2026-10-12): data/d3/class_start_outfits.csv, one row per class and slot,
rewrites the CLIENT's CharStartOutfit.dbc rows of those classes for every race and both sexes, so the create screen's
model wears the sheet's items. The server's table, its migration and real starting gear never change. A row with an
enchant_id wears a new ItemDisplayInfo row (ids OUTFIT_DISPLAY_FIRST up) copying the item's look with that
SpellItemEnchantment's ItemVisual, so the glow shows without an enchant field.

A parent with no stock start row for some races (the Necromancer's Warlock has races 1, 2, 5, 7 and 10 only) gives
those races their playercreateinfo row at the hub, as world_0028 placed the Wizard's (the start moves every new
character to the hub anyway, dc_world.cpp Start). Their bar is the class start's alone, as the Wizard's added races'
(world_0028): the login rewrites buttons 0-7 (dc_classes.cpp WriteActionBar), and a parent with no stock Attack
button (the Warlock) copies none above. A SkillRaceClassInfo row two created classes share is written with both
bits by the later class's migration.

A class on a stock slot (the Crusader on the Paladin's, the Demon Hunter on the Hunter's; its row's parent is its own id) keeps every stock row: its
migration carries only the playercreateinfo rows of the races the stock CharBaseInfo pairs lack, at the hub as above,
and the stock Attack button its native races' bars share. Its client rows are CharBaseInfo's alone
(build_charbaseinfo.py); ChrClasses' power slot and name for it are generate_class_resources.py's.

Playercreateinfo skills, spells and items have nothing to copy: the stock rows are class 0 (every class) or the
parent's own class skills, and the one item row is unused. A class a stock class mask cannot hold (id above the
core's limit) is core patch 0024's; these rows are skipped by the core until it lands.

Run from the repo root after generate_class_resources.py:

    python mod-diablocraft/scripts/generate/classes/generate_class_creation.py
"""
import csv
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from class_names import sheet_stem
from applied_migrations import require_companion_migration, write_coupled_outputs, write_migration
from dbc_store import Store, schema, sql_value
import generate_class_proficiencies as proficiencies
import generate_class_resources as resources
import generate_spells as spells
import generate_sql

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
DATA = MODULE / "data/d3"
UPDATES = MODULE / "data/sql/db-world/updates"
STOCK = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CLIENT = ROOT / "client-patch/dbc"
sys.path.insert(0, str(CLIENT))
import build_charbaseinfo   # noqa: E402  (the race list and CharBaseInfo's own layout check)

DEATH_KNIGHT = 6
ATTACK = 6603   # the stock Attack spell: the one button every class's default bar shares
OUTFIT_BYTES = 296   # CharStartOutfit.dbc: ID, four byte fields, then 72 ints
# class_start_outfits.csv slots in ItemID_n order, with the Item.dbc InventoryTypes each may hold.
OUTFIT_SLOTS = {"Head": {1}, "Shoulder": {3}, "Chest": {5, 20}, "Waist": {6}, "Legs": {7}, "Feet": {8},
                "Wrist": {9}, "Hands": {10}, "Weapon": {13, 15, 17, 21, 26}}
OUTFIT_DISPLAY_FIRST, OUTFIT_DISPLAY_LAST = 90400, 90499   # after the potions' 90300-90310
# The Gt tables indexed by class, with their rows per class: (client file, server table or None, rows, has an id column).
# Player.cpp:5284-5430 and StatSystem.cpp index them (class - 1) * rows + position; gtOCTRegenMP is read by the
# client only (DBCStructure.h:1089-1092).
GT_TABLES = (
    ("gtChanceToMeleeCrit", "gtchancetomeleecrit_dbc", 100, False),
    ("gtChanceToSpellCrit", "gtchancetospellcrit_dbc", 100, False),
    ("gtChanceToMeleeCritBase", "gtchancetomeleecritbase_dbc", 1, False),
    ("gtChanceToSpellCritBase", "gtchancetospellcritbase_dbc", 1, False),
    ("gtOCTRegenHP", "gtoctregenhp_dbc", 100, False),
    ("gtOCTRegenMP", None, 100, False),
    ("gtRegenHPPerSpt", "gtregenhpperspt_dbc", 100, False),
    ("gtRegenMPPerSpt", "gtregenmpperspt_dbc", 100, False),
    ("gtOCTClassCombatRatingScalar", "gtoctclasscombatratingscalar_dbc", 32, True),
)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def created_classes(module=MODULE):
    """class_creation.csv joined to class_map.csv, in class id order."""
    mapped = {row["d3_class"].strip(): row for row in read_csv(module / "data/d3/class_map.csv")}
    out, seen = [], set()
    for line, row in enumerate(read_csv(module / "data/d3/class_creation.csv"), 2):
        name = row["d3_class"].strip()
        where = f"class_creation.csv:{line}"
        if name not in mapped:
            raise SystemExit(f"{where}: {name!r} is not in class_map.csv")
        if not row["source"].strip():
            raise SystemExit(f"{where}: {name} needs its source")
        if not re.fullmatch(r"world_\d{4}_class_[a-z_]+\.sql", row["migration"].strip()):
            raise SystemExit(f"{where}: migration {row['migration']!r} is not world_NNNN_class_<name>.sql")
        entry = mapped[name]
        wow_id, parent = int(entry["wow_class_id"]), int(row["parent_wow_class_id"])
        if name in seen or wow_id in {c["id"] for c in out}:
            raise SystemExit(f"{where}: {name} appears twice")
        seen.add(name)
        out.append(dict(name=name, id=wow_id, parent=parent, migration=row["migration"].strip(),
                        power=entry["wow_power_type"].strip(), token=resources.class_token(entry["wow_class"])))
    return sorted(out, key=lambda c: c["id"])


def stock(name):
    return (STOCK / name).read_bytes()


def stock_races(klass):
    """The races the stock CharBaseInfo.dbc pairs with a class: the races the stock tables hold rows for."""
    raw = stock("CharBaseInfo.dbc")
    _, count, _, size, _ = struct.unpack_from("<4s4I", raw)
    return {raw[20 + n * size] for n in range(count) if raw[21 + n * size] == klass}


def hub_rows_sql(cid, missing):
    """playercreateinfo at the hub for the races the parent has no stock row for."""
    race_rows = " UNION ALL ".join(f"SELECT {r}" + (" AS `race`" if n == 0 else "") for n, r in enumerate(missing))
    return [
        "INSERT INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)\n"
        f"SELECT r.`race`,{cid},h.`map_id`,h.`area_id`,h.`x`,h.`y`,h.`z`,h.`o` FROM ({race_rows}) r "
        "JOIN `dc_world_hub` h ON h.`id`=1\n"
        "ON DUPLICATE KEY UPDATE `map`=VALUES(`map`),`zone`=VALUES(`zone`),`position_x`=VALUES(`position_x`),"
        "`position_y`=VALUES(`position_y`),`position_z`=VALUES(`position_z`),`orientation`=VALUES(`orientation`);"]


def stock_slot_sql(c, races):
    """A class on a stock slot: start rows for the races stock lacks, at the hub, with the stock Attack button."""
    cid, missing = c["id"], [r for r in build_charbaseinfo.RACES if r not in races]
    if not missing:
        raise SystemExit(f"class_creation.csv: {c['name']} is on a stock slot every race already has; it needs no row")
    native = min(races)
    race_rows = " UNION ALL ".join(f"SELECT {r}" + (" AS `race`" if n == 0 else "") for n, r in enumerate(missing))
    race_list = ",".join(str(r) for r in missing)
    return "\n".join([
        f"-- Generated by generate_class_creation.py from class_creation.csv, class_map.csv and the stock CharBaseInfo.dbc:",
        f"-- every race can create a {c['name']} (WoW class {cid}, a stock slot). Stock has no row for races {race_list}; the core",
        "-- refuses a pair with no playercreateinfo row. Each new row is at the hub, as world_0028's; the class start",
        "-- (dc_class_start, class-keyed) gives the kit and skills to every race alike. Racial stats are per race in the",
        "-- pinned core, so no stats rows are needed. Idempotent.",
        "SET NAMES utf8mb4;",
        *hub_rows_sql(cid, missing),
        f"DELETE FROM `playercreateinfo_action` WHERE `class`={cid} AND `race` IN ({race_list});",
        "INSERT INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)",
        f"SELECT r.`race`, {cid}, a.`button`, a.`action`, a.`type` FROM ({race_rows}) r",
        f"JOIN `playercreateinfo_action` a ON a.`class`={cid} AND a.`race`={native} AND a.`action`={ATTACK};",
        ""])


class Outfits:
    """CharStartOutfit.dbc rows by the schema's own column kinds (the Store reader needs four-byte fields)."""

    def __init__(self, raw, columns):
        magic, count, fields, size, strings = struct.unpack_from("<4s4I", raw)
        self.columns = columns
        self.format = "<" + "".join("B" if kind == "tinyint" else "i" for _, kind, _ in columns)
        if magic != b"WDBC" or fields != len(columns) or size != OUTFIT_BYTES or struct.calcsize(self.format) != size:
            raise SystemExit("CharStartOutfit.dbc: not the stock 3.3.5a layout")
        self.rows = [dict(zip((c[0] for c in columns), struct.unpack_from(self.format, raw, 20 + n * size)))
                     for n in range(count)]
        self.tail = raw[20 + count * size:]

    def bytes(self):
        body = b"".join(struct.pack(self.format, *(row[c[0]] for c in self.columns)) for row in self.rows)
        return struct.pack("<4s4I", b"WDBC", len(self.rows), len(self.columns), OUTFIT_BYTES, len(self.tail)) + body + self.tail


def start_outfits(module):
    """{wow class id: [(slot, item id, enchant id or 0)]} from class_start_outfits.csv, in slot order."""
    ids = {row["d3_class"].strip(): int(row["wow_class_id"]) for row in read_csv(module / "data/d3/class_map.csv")}
    by_class = {}
    for line, row in enumerate(read_csv(module / "data/d3/class_start_outfits.csv"), 2):
        where, name, slot = f"class_start_outfits.csv:{line}", row["d3_class"].strip(), row["slot"].strip()
        if name not in ids or slot not in OUTFIT_SLOTS:
            raise SystemExit(f"{where}: {name!r} must be in class_map.csv and {slot!r} one of {', '.join(OUTFIT_SLOTS)}")
        slots = by_class.setdefault(ids[name], {})
        if slot in slots:
            raise SystemExit(f"{where}: {name} {slot} appears twice")
        slots[slot] = (slot, int(row["item_id"]), int(row["enchant_id"] or 0))
    return {cid: [slots[s] for s in OUTFIT_SLOTS if s in slots] for cid, slots in by_class.items()}


def preview_outfits(outfits, next_outfit, module, client_dir):
    """Rewrite the sheet's classes' client outfit rows (every race, both sexes); return the ItemDisplayInfo.dbc bytes."""
    items = Store((client_dir / "Item.dbc").read_bytes(), schema(ROOT, "item_dbc"))
    displays = Store((client_dir / "ItemDisplayInfo.dbc").read_bytes(), schema(ROOT, "itemdisplayinfo_dbc"))
    enchants = Store(stock("SpellItemEnchantment.dbc"), schema(ROOT, "spellitemenchantment_dbc"))
    next_display = OUTFIT_DISPLAY_FIRST
    for cid, wanted in sorted(start_outfits(module).items()):
        gear = []   # (item id, display id, inventory type)
        for slot, item, enchant in wanted:
            if item not in items.rows:
                raise SystemExit(f"class_start_outfits.csv: item {item} is not in Item.dbc")
            row = items.decode(item)
            if row["InventoryType"] not in OUTFIT_SLOTS[slot]:
                raise SystemExit(f"class_start_outfits.csv: item {item} (inventory type {row['InventoryType']}) is not a {slot}")
            display = row["DisplayInfoID"]
            if enchant:
                if enchant not in enchants.rows or next_display > OUTFIT_DISPLAY_LAST:
                    raise SystemExit(f"class_start_outfits.csv: enchant {enchant} is not in SpellItemEnchantment.dbc "
                                     f"or the {OUTFIT_DISPLAY_FIRST}-{OUTFIT_DISPLAY_LAST} displays are used up")
                displays.encode(dict(displays.decode(display), ID=next_display,
                                     ItemVisual=enchants.decode(enchant)["ItemVisual"]))
                display, next_display = next_display, next_display + 1
            gear.append((item, display, row["InventoryType"]))
        have = {(r["RaceID"], r["SexID"]): r for r in outfits.rows if r["ClassID"] == cid and r["OutfitID"] == 0}
        for race in build_charbaseinfo.RACES:
            for sex in (0, 1):
                row = have.get((race, sex))
                if row is None:
                    row = dict.fromkeys((c[0] for c in outfits.columns), 0)
                    row.update(ID=next_outfit, RaceID=race, ClassID=cid, SexID=sex)
                    outfits.rows.append(row)
                    next_outfit += 1
                for n in range(1, 25):
                    item, display, kind = gear[n - 1] if n <= len(gear) else (0, 0, 0)
                    row.update({f"ItemID_{n}": item, f"DisplayItemID_{n}": display, f"InventoryType_{n}": kind})
    return displays.bytes()


def gt_floats(raw, has_id):
    """(ids, values) of a Gt file; a file without an id column is indexed by record number."""
    magic, count, fields, size, strings = struct.unpack_from("<4s4I", raw)
    if magic != b"WDBC" or (fields, size) != ((2, 8) if has_id else (1, 4)):
        raise SystemExit("a Gt file is not the stock layout")
    if has_id:
        pairs = [struct.unpack_from("<If", raw, 20 + n * 8) for n in range(count)]
        return [p[0] for p in pairs], [p[1] for p in pairs]
    return list(range(count)), [struct.unpack_from("<f", raw, 20 + n * 4)[0] for n in range(count)]


def gt_bytes(ids, values, has_id, tail):
    if has_id:
        body = b"".join(struct.pack("<If", i, v) for i, v in zip(ids, values))
        return struct.pack("<4s4I", b"WDBC", len(values), 2, 8, len(tail)) + body + tail
    body = b"".join(struct.pack("<f", v) for v in values)
    return struct.pack("<4s4I", b"WDBC", len(values), 1, 4, len(tail)) + body + tail


def render(module=MODULE, client_dir=CLIENT):
    """{class name: (migration sql, {client file: bytes})} for every created class, validated before any write."""
    classes = created_classes(module)
    if not classes:
        raise SystemExit("class_creation.csv: no created class")
    chr_columns = schema(ROOT, "chrclasses_dbc")
    server_chr = Store(stock("ChrClasses.dbc"), chr_columns)
    client_chr = Store((client_dir / "ChrClasses.dbc").read_bytes(), chr_columns)
    srci_columns = schema(ROOT, "skillraceclassinfo_dbc")
    server_srci = Store(stock("SkillRaceClassInfo.dbc"), srci_columns)
    client_srci = Store((client_dir / "SkillRaceClassInfo.dbc").read_bytes(), srci_columns)
    outfit_columns = schema(ROOT, "charstartoutfit_dbc")
    outfits = Outfits(stock("CharStartOutfit.dbc"), outfit_columns)
    next_outfit = max(row["ID"] for row in outfits.rows) + 1
    gts = {}
    for file, _, rows_per, has_id in GT_TABLES:
        raw = stock(file + ".dbc")
        ids, values = gt_floats(raw, has_id)
        tail = raw[20 + len(values) * (8 if has_id else 4):]
        gts[file] = [ids, values, tail]
    races = build_charbaseinfo.RACES
    stock_classes = set(server_chr.rows)
    shared = 0
    for c in stock_classes - {DEATH_KNIGHT}:
        shared |= 1 << (c - 1)
    result, owned, srci_masks = {}, set(), {}
    for c in classes:
        cid, parent, bit = c["id"], c["parent"], 1 << (c["id"] - 1)
        if cid in stock_classes and parent == cid and cid not in owned:
            owned.add(cid)
            result[c["name"]] = (stock_slot_sql(c, stock_races(cid)), c)
            # A class on a stock slot keeps its stock row, the server's whole and the client's but one field: once its
            # records are written (its skill sheet is in data/d3) the client row takes their family, so a spell
            # modifier reaches them, as a created class's does below. Before that it keeps the stock family.
            blocks = spells.CLASS_BLOCKS.get(sheet_stem(c["name"]))
            if blocks and (DATA / ("%s_skills.csv" % sheet_stem(c["name"]))).is_file():
                client_chr.encode(dict(client_chr.decode(cid), SpellClassSet=blocks.family))
            continue
        if cid in stock_classes or cid in owned:
            raise SystemExit(f"class_creation.csv: class {cid} is not new")
        if parent not in stock_classes:
            raise SystemExit(f"class_creation.csv: parent class {parent} is not a stock class")
        if c["power"] not in resources.POWERS:
            raise SystemExit(f"class_map.csv: {c['name']} wow_power_type {c['power']!r} is not a WoW power slot")
        owned.add(cid)
        sql = [f"-- Generated by generate_class_creation.py from class_creation.csv, class_map.csv and the stock",
               f"-- DBC files: WoW class {cid} ({c['name']}, file token {c['token']}) copied from class {parent} at creation",
               "-- (decisions.md 2026-10-12; docs/contracts/monk-class.md). Idempotent: every table's class rows are",
               "-- deleted first. Rows for a class above the core's class limit are skipped with a log line until core",
               "-- patch 0024 raises it.",
               "SET NAMES utf8mb4;"]
        # ChrClasses: the parent's stock row, its own id, token, name and power slot.
        row = server_chr.decode(parent)
        row.update(ID=cid, Filename=c["token"], Name_Lang_enUS=c["name"], DisplayPower=resources.POWERS[c["power"]],
                   Required_Expansion=0)
        names = [col[0] for col in chr_columns]
        # SpellClassSet differs once the class has records: the client applies a spell modifier (SMSG_SET_FLAT/PCT_SPELL_MODIFIER) only to
        # a spell of the player class's own family, so the client row takes the family the class's records carry
        # (generate_spells.CLASS_BLOCKS) and Epiphany's SPELLMOD_RANGE reaches the Monk's skills. The server row keeps the
        # parent's: the core never reads it, and dc_classes.cpp ClassSpellFamily strips the parent's stock spells by it.
        # A class with no records yet (no CLASS_BLOCKS entry) keeps the parent's on the client too: no spell of its
        # family exists to modify, and its records bead registers the family, which this row then takes.
        blocks = spells.CLASS_BLOCKS.get(sheet_stem(c["name"]))
        client_chr.encode(dict(row, SpellClassSet=blocks.family if blocks else row["SpellClassSet"]))
        sql += [f"DELETE FROM `chrclasses_dbc` WHERE `ID`={cid};",
                "INSERT INTO `chrclasses_dbc` (" + ",".join(f"`{n}`" for n in names) + ") VALUES\n("
                + ",".join(sql_value(row[n]) for n in names) + ");"]
        # Player creation: spawn, bar, level stats.
        race_list = ",".join(str(r) for r in races)
        sql += [f"DELETE FROM `playercreateinfo` WHERE `class`={cid};",
                "INSERT INTO `playercreateinfo` (`race`,`class`,`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation`)\n"
                f"SELECT `race`,{cid},`map`,`zone`,`position_x`,`position_y`,`position_z`,`orientation` "
                f"FROM `playercreateinfo` WHERE `class`={parent} AND `race` IN ({race_list});",
                f"DELETE FROM `playercreateinfo_action` WHERE `class`={cid};",
                "INSERT INTO `playercreateinfo_action` (`race`,`class`,`button`,`action`,`type`)\n"
                f"SELECT `race`,{cid},`button`,`action`,`type` FROM `playercreateinfo_action` "
                f"WHERE `class`={parent} AND `action`={ATTACK} AND `race` IN ({race_list});"]
        missing = [r for r in races if r not in stock_races(parent)]
        if missing:
            sql += hub_rows_sql(cid, missing)
        sql += [
                f"DELETE FROM `player_class_stats` WHERE `Class`={cid};",
                "INSERT INTO `player_class_stats` (`Class`,`Level`,`BaseHP`,`BaseMana`,`Strength`,`Agility`,`Stamina`,`Intellect`,`Spirit`)\n"
                f"SELECT {cid},`Level`,`BaseHP`,`BaseMana`,`Strength`,`Agility`,`Stamina`,`Intellect`,`Spirit` "
                f"FROM `player_class_stats` WHERE `Class`={parent};"]
        # Start outfit: the parent's rows, one per race and sex, under new identities.
        new = []
        for source in outfits.rows:
            if source["ClassID"] == parent and source["RaceID"] in races:
                new.append(dict(source, ID=next_outfit, ClassID=cid))
                next_outfit += 1
        # Torment added the Blood Elf Warrior's playercreateinfo row (world_0003) but stock has no outfit for it, so
        # that race gets none, as the Barbarian's has none; the start kit equips every race alike.
        if not new:
            raise SystemExit(f"CharStartOutfit.dbc: class {parent} has no usable outfit rows")
        outfits.rows += new
        onames = [col[0] for col in outfit_columns]
        sql += [f"DELETE FROM `charstartoutfit_dbc` WHERE `ClassID`={cid};",
                "INSERT INTO `charstartoutfit_dbc` (" + ",".join(f"`{n}`" for n in onames) + ") VALUES\n"
                + ",\n".join("(" + ",".join(sql_value(r[n]) for n in onames) + ")" for r in new) + ";"]
        # Skills every stock class but the Death Knight shares: the new class's bit on those rows.
        touched = []
        for key in sorted(server_srci.rows):
            r = server_srci.decode(key)
            if r["ClassMask"] not in (0, -1) and r["ClassMask"] & shared == shared and not r["ClassMask"] & bit:
                touched.append(r)
        # A non-weapon skill its class_starts.csv profile learns that no row above allows yet (Dual Wield, skill 118,
        # is the Warrior's and Hunter's row only; the Barbarian learns it, so the Monk must): the parent's own rows
        # for it. Weapon skills are generate_class_proficiencies.py's.
        profile = generate_sql.class_start_rows(module / "data/d3/class_starts.csv").get(cid, {"class_key": "", "skills": []})
        covered = {server_srci.decode(k)["SkillID"] for k in server_srci.rows
                   if server_srci.decode(k)["ClassMask"] in (0, -1) or server_srci.decode(k)["ClassMask"] & bit}
        covered |= {r["SkillID"] for r in touched}
        missing = {row["skill_id"] for row in profile["skills"]} - covered - set(
            proficiencies.weapon_skills(module, profile["class_key"]) if profile["class_key"] else ())
        for key in sorted(server_srci.rows):
            r = server_srci.decode(key)
            if r["SkillID"] in missing and r["ClassMask"] & (1 << (parent - 1)):
                touched.append(r)
        # Rows are chosen by their stock mask and written with the bits of every class created before this one too:
        # this class's migration runs after theirs and replaces the same rows.
        touched = [dict(r, ClassMask=srci_masks.get(r["ID"], r["ClassMask"]) | bit) for r in touched]
        srci_masks.update((r["ID"], r["ClassMask"]) for r in touched)
        for r in touched:
            client_srci.encode(dict(client_srci.decode(r["ID"]), ClassMask=r["ClassMask"]))
        snames = [col[0] for col in srci_columns]
        if not touched:
            raise SystemExit("SkillRaceClassInfo.dbc: no shared skill rows to give the new class")
        sql += [f"DELETE FROM `skillraceclassinfo_dbc` WHERE `ID` IN ({','.join(str(r['ID']) for r in touched)});",
                "INSERT INTO `skillraceclassinfo_dbc` (" + ",".join(f"`{n}`" for n in snames) + ") VALUES\n"
                + ",\n".join("(" + ",".join(sql_value(r[n]) for n in snames) + ")" for r in touched) + ";"]
        # Gt slices.
        for file, table, per, has_id in GT_TABLES:
            ids, values, _ = gts[file]
            first = (cid - 1) * per
            origin = (parent - 1) * per
            if has_id:
                if ids[:per] != list(range(1, per + 1)) or len(values) != first:
                    raise SystemExit(f"{file}.dbc: class {cid} does not follow the {len(values) // per} stock slices")
                slice_ = values[origin:origin + per]
                new_ids = list(range(first + 1, first + per + 1))
            else:
                if len(values) != first:
                    raise SystemExit(f"{file}.dbc: class {cid} does not follow the {len(values) // per} stock slices")
                slice_ = values[origin:origin + per]
                new_ids = list(range(first, first + per))
            ids += new_ids
            values += slice_
            if table:
                sql += [f"DELETE FROM `{table}` WHERE `ID` BETWEEN {new_ids[0]} AND {new_ids[-1]};",
                        f"INSERT INTO `{table}` (`ID`,`Data`) VALUES\n"
                        + ",\n".join(f"({i},{sql_value(v)})" for i, v in zip(new_ids, slice_)) + ";"]
        result[c["name"]] = ("\n".join(sql) + "\n", c)
    # The create screen's preview outfits are the client's alone: the SQL above never sees them.
    display_dbc = preview_outfits(outfits, next_outfit, module, client_dir)
    # The files come out of the same state the SQL did, after every created class.
    files = {"ItemDisplayInfo.dbc": display_dbc, "ChrClasses.dbc": client_chr.bytes(), "SkillRaceClassInfo.dbc": client_srci.bytes(),
             "CharStartOutfit.dbc": outfits.bytes(),
             "CharBaseInfo.dbc": build_charbaseinfo.build(stock("CharBaseInfo.dbc"), module)}
    for file, _, _, has_id in GT_TABLES:
        ids, values, tail = gts[file]
        files[file + ".dbc"] = gt_bytes(ids, values, has_id, tail)
    return result, files


def generate(module=MODULE, client_dir=CLIENT):
    module = Path(module)
    result, files = render(module, client_dir)
    updates = module / "data/sql/db-world/updates"
    # One migration per created class; the client files follow the newest of them (they hold every created class).
    outputs = [(client_dir / name, data) for name, data in files.items()]
    for name, (sql, c) in result.items():
        migration = require_companion_migration(module, updates / c["migration"], updates)
        write_migration(module, migration, sql)
    last = max(result.values(), key=lambda entry: entry[1]["migration"])
    write_coupled_outputs(module, updates / last[1]["migration"], last[0], outputs,
                          label="class creation client DBCs")
    print(f"class creation: {', '.join(result)} -> {', '.join(c['migration'] for _, c in result.values())}; "
          f"{len(files)} client DBCs")
    return result, files


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    generate()
