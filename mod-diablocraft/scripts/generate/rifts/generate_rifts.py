#!/usr/bin/env python3
"""Generate dc_rift_dungeon from rift_dungeons.csv (09-rifts F1, section 3), and
the rift quest data from rift_quests.csv (09-rifts section 7, Phase A).

Only the 30 rows marked recommended go in: the other 29 are out for locked
doors, keys, vehicles or wave-defence layouts and would strand a party (09
section 3). Rerunning is safe; the migration drops and recreates the table.

Rift floors Part F5 (docs/proposals/rift-floors.md 4.14, 6.4): an open zone (rift_open_zones.csv, today Un'Goro Crater on the rift copy
of Kalimdor, map 751) joins the pool as one more floor map, in its own migration (rifts_0024: rifts_0001 is applied and frozen). Its
arrival point is the designer's entrance, rifts.csv open_rift_entry_x/y/z/o, the one place that holds it; the row is named as the zone is,
because the spawner and the exit spots find a map's sheets by that name. Its dungeon_id is OPEN_ZONE_ID_BASE plus its place in the
sheet, so a later dungeon row never takes it. Its exit is its farthest anchor by walk (generate_open_zone_survey.py,
diablocraft-yh7el), or the designer's `.dc floor exit here` spot where he placed one.

kills_required is a tunable, not a published D3 number - see the note in the CSV. Since monster
spawning S3 nothing reads it any more (the bar is D3's progress points); the column stays in the table.

The quest half was written once, as rifts_0011_rift_quests.sql: six quest templates (three
Nephalem, three Greater), the unspawned credit creature the synthetic objective needs, the questgiver
relations, the entrance portal POOL, and the two hub flag changes described
below. That migration is applied and frozen (applied_migrations.csv); this generator no longer renders it.
Monster spawning S3 (docs/proposals/monster-spawning.md 3.9.4) keeps one quest per mode, counting hundredths
of a D3 progress point and ships the change as rifts_0019_one_bar.sql: it sets the two counts (65,000, D3's 650 points)
and retires the four other variants. That migration is applied and frozen at 65,000. Ruling 2026-10-16 (diablocraft-owe7u) moved
the target to 30,000 (rift_quests.csv bar_hundredths: 300 points = the whole bar), which ships as rifts_0032_bar_target.sql, a
count change only. Every id comes from rift_quests.csv or rift_portals.csv; none is allocated here.

The portal pool is rift_portals.csv, one row per look (ruling 2026-09-17): a
gameobject_template per row wearing that row's display and scale, plus the
dc_rift_portal table the module rolls from. The single-display 910014 "Rift
Entrance" is retired and this migration deletes it, so a world database that
already has it does not keep a template nothing points at any more.

rifts_0011 owns two rows it did not create, because their own source cannot be
regenerated here:

  gameobject_template 910011 type 22 -> 2 (QUESTGIVER). The obelisk's type is
  set by hand-written world_0006_hub_object_use.sql, which no generator emits.
  Note that world_0006's clickability finding was specific to GOOBER (10):
  ObjectMgr::LoadGameObjectForQuests marks every type-2 template IsForQuests
  unconditionally, so type 2 does not reintroduce the GM-only click.

  creature_template 910003 npcflag 1 -> 3 (GOSSIP|QUESTGIVER). The source of
  truth is the npcflag cell of world_hub_services.csv, already raised, but
  regenerating world_0005 through generate_hub_relocation.py needs a world DB
  connection this script deliberately does not take.

Both are idempotent UPDATEs, so re-applying the migration after a future hub
regeneration simply reasserts them.

Run from the repo root:

    python mod-diablocraft/scripts/generate/rifts/generate_rifts.py

This script does not touch generate_sql.py or the dc_ tables it produces.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import tunables_csv
from applied_migrations import write_migration

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 128, 910011, 910003, 910014, 22, 2840): obelisk, Keeper, retired portal entry, gameobject type and the credit clone source; Identifiers.
# Constant (910060, 5): the Greater Rift progress orb's gameobject entry and its type (GAMEOBJECT_TYPE_GENERIC); Identifiers.
# Constant (910061, 35, 1): Urshi's creature entry, the friendly faction and UNIT_NPC_FLAG_GOSSIP the hub artisans use; Identifiers.

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
SOURCE = MODULE_ROOT / "data/d3/rift_dungeons.csv"
QUEST_SOURCE = MODULE_ROOT / "data/d3/rift_quests.csv"
PORTAL_SOURCE = MODULE_ROOT / "data/d3/rift_portals.csv"
GENERATED = MODULE_ROOT / "data/generated"
UPDATES = MODULE_ROOT / "data/sql/db-world/updates"

# Hub entries this migration reasserts; see the module docstring.
OBELISK_ENTRY = 910011
KEEPER_ENTRY = 910003
OBELISK_QUESTGIVER_TYPE = 2   # GAMEOBJECT_TYPE_QUESTGIVER
KEEPER_NPCFLAG = 3            # UNIT_NPC_FLAG_GOSSIP(1) | UNIT_NPC_FLAG_QUESTGIVER(2)

# The pool's templates, and the one they replace. go_type 22 (SPELLCASTER) is
# what the retired 910014 used and what world_0006_hub_object_use.sql moved the
# town portal halves to: a type-10 goober with questId 0 fails ActivateToQuest()
# and is then clickable only by a GM. The name is the same on every row because
# it is what a PLAYER reads on the portal; the look's own name is the designer's label
# and lives in dc_rift_portal, not in gameobject_template.
RETIRED_PORTAL_ENTRY = 910014
PORTAL_GO_TYPE = 22
PORTAL_NAME = "Rift Entrance"

# Rift floors Part F2 (docs/proposals/rift-floors.md 4.4, 6.12): each floor's exit portal wears one of the entrance looks, on a
# template of its own so a click runs the exit's code. Look entry + 40 is the exit entry (EXIT_ENTRY_OFFSET in
# src/rifts/dc_rift_exit.h; test_rift_exit.py reads both). The designer's own exit spots live in dc_rift_exit_spot.
EXIT_ENTRY_OFFSET = 40
EXIT_NAME = "Rift Exit"
EXIT_MIGRATION = "rifts_0021_floor_exit.sql"
# The exit portal is named for the floor it leads to ('Floor N', ruling 2026-10-09, diablocraft-zuia). The client reads a
# gameobject's name from its template, so each (look, floor led to) pair has a template of its own: entry = look entry + 40
# + 1000 * (N - 2), N = 2 .. rift_max_floors (the last floor has no exit). Floor 2 keeps rifts_0021's entries. EXIT_FLOOR_STRIDE
# and EXIT_LOOK_BLOCK are in src/rifts/dc_rift_exit.h (test_rift_exit.py reads both).
EXIT_FLOOR_STRIDE = 1000
EXIT_LOOK_BLOCK = 910000
EXIT_NAMES_MIGRATION = "rifts_0025_floor_exit_names.sql"

# Rift floors Part F5: the open zones in the pool. Constant (1000): the dungeon_id the first open zone takes in dc_rift_dungeon, far
# above the sheet's 30 dungeons (1 to 30), so a dungeon row added later never meets it; Identifiers. Constant (0, 'open'): the
# kills_required and approximate_length of a zone's row; since monster spawning S3 nothing reads either column (the bar is D3's progress
# points) and a zone has no length.
OPEN_ZONE_SOURCE = MODULE_ROOT / "data/d3/rift_open_zones.csv"
# rifts_0024 is applied (update 9) and frozen: the pool render ships as rifts_0028 (a whole render, DELETE then INSERT).
OPEN_ZONE_MIGRATION = "rifts_0028_open_zone_pool.sql"
OPEN_ZONE_ID_BASE = 1000
# The bounty acts (docs/research/bounty-acts.md 2.3, diablocraft-hyoic.1): D3's five, a constant, one a board column.
ACTS = ("1", "2", "3", "4", "5")
# diablocraft-hmnei: every zone of the sheet, entrance or not, for dc_open_rift.cpp (the copy's zone, the command's words, the entrance's
# tunables). The pool (rifts_0024) holds only the zones with an entrance; a zone's dungeon_id is OPEN_ZONE_ID_BASE + its sheet row, so a
# zone that gets its entrance later keeps the id it was always going to have.
OPEN_ZONE_TABLE_MIGRATION = "rifts_0026_open_zones.sql"

# Greater Rift part 4: the progress orb a promoted pack drops when its last member dies. A GENERIC
# (type 5) object has no use, so nothing can be clicked or looted from it; the module walks players
# into it. Its look is the rifts/gr_orb_display_id tunable, so the designer can swap it after he looks on dev
# by rerunning this generator and applying rifts_0016_gr_orb.sql. Same entry as ORB_ENTRY in
# dc_gr_progress.cpp.
ORB_ENTRY = 910060
ORB_GO_TYPE = 5
ORB_NAME = "Progress Orb"
ORB_DISPLAY = int(tunables_csv.value("rifts", "gr_orb_display_id"))

# Monster spawning S3: the orange orb a Nephalem Rift's elite packs drop (ruling 2026-10-08, decisions.md b4171f62),
# beside the purple one above. Its look is the rifts/nr_orb_display_id tunable, PLACEHOLDER until he picks it on dev
# (card q-1008-11); while the row is blank the template wears the purple look so the drop can be tried, and
# the generator says so. Same entry as NR_ORB_ENTRY in dc_gr_progress.cpp.
NR_ORB_ENTRY = 910062
NR_ORB_NAME = "Nephalem Progress Orb"
# rifts_0020 (the orb with the purple stand-in look) is applied and frozen: the whole render, with the picked look, ships as rifts_0031.
NR_ORB_MIGRATION = "rifts_0031_nr_orb_look.sql"
# Ruling 2026-10-16 (diablocraft-owe7u): the bar is 30,000 hundredths (rift_quests.csv). rifts_0019 set 65,000 and is applied, so
# it is rendered from this constant, not from the sheet; rifts_0032 carries the sheet's count.
BAR_TARGET_MIGRATION = "rifts_0032_bar_target.sql"
FIRST_BAR_HUNDREDTHS = 65000

# Monster spawning S3: the quest variants the one-bar quests replace (rift_quests.csv kept 910020 and 910023).
# Constant (910021, 910022, 910024, 910025): quest ids rifts_0011 wrote; Identifiers.
RETIRED_QUESTS = (910021, 910022, 910024, 910025)
# Constant (65535): the core's 16-bit quest counter, QuestDef.h CreatureOrGOCount.
QUEST_COUNTER_MAX = 65535

# Greater Rift part 11: Urshi, who stands where an in-time Guardian died. A gossip NPC whose script
# (dc_urshi, dc_gr_urshi.cpp) opens the upgrade window; her look is the rifts/gr_urshi_display_id tunable, a
# ghostly WoW model the designer judges on dev and swaps there by rerunning this generator and applying
# rifts_0017_urshi.sql. Same entry as URSHI_ENTRY in dc_gr_urshi.cpp.
URSHI_ENTRY = 910061
URSHI_NAME = "Urshi"
URSHI_SUBNAME = "Gem Upgrades"
URSHI_FACTION = 35            # friendly to all, as the hub artisans
URSHI_NPCFLAG = 1             # UNIT_NPC_FLAG_GOSSIP
URSHI_SCRIPT = "dc_urshi"
URSHI_DISPLAY = int(tunables_csv.value("rifts", "gr_urshi_display_id"))

# The credit template is cloned from this stock row so the INSERT cannot depend
# on which of creature_template's columns carry a DEFAULT. 2840 is the same
# stock source generate_hub.py clones the hub Blacksmith from, so it is known to
# exist in the world database this migration runs against. Nothing of it is
# kept but the column shape: identity, flags, loot and scripts are all cleared.
CREDIT_CLONE_SOURCE = 2840

# Verified in the pinned core, src/server/game/Quests/QuestDef.h:
QUEST_FLAGS_NO_MONEY_FROM_XP = 0x100   # max-level XP is not converted to gold
QUEST_SPECIAL_FLAGS_REPEATABLE = 0x001  # quest_template_addon.SpecialFlags
# Deliberately NOT set: QUEST_FLAGS_TRACKING (hides the quest and auto-rewards
# it, 7.5), QUEST_FLAGS_STAY_ALIVE (death would fail the quest, 7.6),
# QUEST_FLAGS_SHARABLE and QUEST_FLAGS_PARTY_ACCEPT (7.9.7 shares server-side
# and silently; no stock share popup is wanted), QUEST_FLAGS_DAILY/WEEKLY.

# QuestLevel -1 scales the log entry to the reader. No level gate is decided
# anywhere in 09-rifts, so MinLevel stays 0 and SuggestedGroupNum stays 0
# rather than invent one; party size four is enforced by the module, not shown
# as a quest suggestion.
QUEST_LEVEL = -1

NUMERIC = {"map_id": "INT", "entry_x": "DOUBLE", "entry_y": "DOUBLE", "entry_z": "DOUBLE",
           "entry_o": "DOUBLE", "kills_required": "INT", "boss_count": "INT"}
TEXT = ["name", "approximate_length", "layout", "path_note"]


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def read_open_zone_rows(path=None):
    """rift_open_zones.csv, checked: one key, name and zone each; the entrance's tunable prefix named; the zone's act 1 to 5 (the
    bounty board's column, diablocraft-hyoic.1)."""
    with Path(path or OPEN_ZONE_SOURCE).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit(f"{OPEN_ZONE_SOURCE}: no zones")
    for column in ("key", "name", "zone_id", "entry_tunable"):
        values = [row[column].strip() for row in rows]
        if not all(values) or len(set(values)) != len(values):
            raise SystemExit(f"{OPEN_ZONE_SOURCE}: every zone needs its own {column}: {values}")
    for row in rows:
        if not row["key"].isalnum() or row["key"] != row["key"].lower():
            raise SystemExit(f"{OPEN_ZONE_SOURCE}: key {row['key']!r} is the command's word: lowercase letters and digits only")
        int(row["map_id"]), int(row["zone_id"])
        if row.get("act", "") not in ACTS:
            raise SystemExit(f"{OPEN_ZONE_SOURCE}: {row['key']}'s act is one of {', '.join(ACTS)}: {row.get('act')!r}")
    return rows


def entrance_of(row):
    """The zone's entrance (x, y, z, o) from rifts.csv <entry_tunable>_x/_y/_z/_o, or None while all four are blank (the zone is off).
    Some but not all set is refused: half an entrance is no entrance."""
    point = {}
    for axis in "xyzo":
        try:
            point[axis] = tunables_csv.value("rifts", f"{row['entry_tunable']}_{axis}")
        except tunables_csv.MissingTunable:
            pass
    if not point:
        return None
    if len(point) != 4:
        raise SystemExit(f"rifts.csv {row['entry_tunable']}_*: {sorted(point)} set, the rest blank; a zone's entrance is all four or none")
    return point


def read_open_zones():
    """The pool rows of the zones with an entrance: [{dungeon_id, map_id, name, x, y, z, o}], the arrival point from rifts.csv."""
    zones = []
    for index, row in enumerate(read_open_zone_rows(), start=1):
        point = entrance_of(row)
        if point:
            zones.append({"dungeon_id": OPEN_ZONE_ID_BASE + index, "map_id": int(row["map_id"]), "name": row["name"], **point})
    if not zones:
        raise SystemExit(f"{OPEN_ZONE_SOURCE}: no zone has an entrance in rifts.csv")
    return zones


def open_zone_table_sql(rows):
    """rifts_0026: every zone of the sheet for dc_open_rift.cpp, entrance or not (diablocraft-hmnei)."""
    values = ",\n".join("({}, {}, {}, {}, {}, {}, {})".format(quote(r["key"]), quote(r["name"]), int(r["map_id"]), int(r["zone_id"]),
                                                             quote(r["entry_tunable"]), int(r["act"]), seq)
                         for seq, r in enumerate(rows, start=1))
    return "\n".join([
        "-- Generated from data/d3/rift_open_zones.csv by generate_rifts.py (diablocraft-hmnei); edit the sheet and rerun. Apply to the world",
        "-- database. The open zones of the rift copy: the zone a copy is sealed to, the word `.dc openrift` takes, and the rifts.csv prefix of",
        "-- the zone's entrance (<entry_tunable>_x/_y/_z/_o; blank: the zone is off), and its bounty act (the board's column, 1 to 5;",
        "-- diablocraft-hyoic.1). Sheet order is the order the command lists them in. The table is the sheet's alone, so it is rebuilt whole.",
        "SET NAMES utf8mb4;",
        "DROP TABLE IF EXISTS `dc_rift_open_zone`;",
        "CREATE TABLE `dc_rift_open_zone` (`key` VARCHAR(32) NOT NULL, `name` VARCHAR(64) NOT NULL, `map_id` INT UNSIGNED NOT NULL, "
        "`zone_id` INT UNSIGNED NOT NULL, `entry_tunable` VARCHAR(64) NOT NULL, `act` TINYINT UNSIGNED NOT NULL, `seq` INT UNSIGNED NOT NULL, "
        "PRIMARY KEY (`key`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "INSERT INTO `dc_rift_open_zone` (`key`, `name`, `map_id`, `zone_id`, `entry_tunable`, `act`, `seq`) VALUES",
        values + ";",
        ""])


def open_zone_sql(zones):
    """rifts_0024: the open zones' rows of dc_rift_dungeon (rift floors Part F5), after the dungeons'."""
    values = ",\n".join(
        "({}, {}, {}, {}, {}, {}, {}, 0, 'open')".format(z["dungeon_id"], z["map_id"], quote(z["name"]), z["x"], z["y"], z["z"], z["o"])
        for z in zones)
    return "\n".join([
        "-- Generated from data/d3/rift_open_zones.csv and data/tunables/rifts.csv (open_rift_entry_*) by generate_rifts.py; edit the",
        "-- sheets and rerun. Apply to the world database.",
        "-- Rift floors Part F5 (docs/proposals/rift-floors.md 4.14): an open zone joins the rift pool as one more floor map. The name is the",
        "-- zone's, as the spawner's and the exit spots' rows name it; the arrival point is the designer's entrance. Nothing reads kills_required.",
        "SET NAMES utf8mb4;",
        f"DELETE FROM `dc_rift_dungeon` WHERE `dungeon_id` >= {OPEN_ZONE_ID_BASE};",
        "INSERT INTO `dc_rift_dungeon` (`dungeon_id`, `map_id`, `name`, `entry_x`, `entry_y`, `entry_z`, `entry_o`, `kills_required`, "
        "`approximate_length`) VALUES",
        values + ";",
        ""])


def read_quests():
    """rift_quests.csv split into its three kinds, validated.

    The CSV is the only source of quest ids, text, the portal display and the
    credit template. A kill baseline in the dungeon pool with no matching quest
    row would leave those dungeons unrunnable, so the two are cross-checked.
    """
    with QUEST_SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit(f"{QUEST_SOURCE}: empty")

    quests, credit = [], None
    seen = set()
    for row in rows:
        kind = row["kind"].strip()
        entry = row["entry_id"].strip()
        if not entry.isdigit():
            raise SystemExit(f"rift_quests.csv: entry_id {entry!r} is not a number")
        entry = int(entry)
        if entry in seen:
            raise SystemExit(f"rift_quests.csv: entry_id {entry} appears twice")
        seen.add(entry)

        if kind == "quest":
            mode = row["mode"].strip()
            if mode not in ("nr", "gr"):
                raise SystemExit(f"rift_quests.csv: quest {entry} mode {mode!r} is not nr or gr")
            bar = row["bar_hundredths"].strip()
            if not bar.isdigit() or not 0 < int(bar) <= QUEST_COUNTER_MAX:
                raise SystemExit(f"rift_quests.csv: quest {entry} bar_hundredths {bar!r} is not 1 to {QUEST_COUNTER_MAX} "
                                 "(the core's 16-bit quest counter)")
            if entry in RETIRED_QUESTS:
                raise SystemExit(f"rift_quests.csv: quest {entry} was retired by monster spawning S3; delete the row")
            timer = row["time_allowed_seconds"].strip() or "0"
            if not timer.isdigit():
                raise SystemExit(f"rift_quests.csv: quest {entry} time_allowed_seconds {timer!r} is not a number")
            if mode == "nr" and int(timer):
                raise SystemExit(f"rift_quests.csv: quest {entry} is nr and must have no timer (7.4)")
            for column in ("title", "objective_text", "description", "completion_text"):
                if not row[column].strip():
                    raise SystemExit(f"rift_quests.csv: quest {entry} has no {column}")
            quests.append({"id": entry, "mode": mode, "units": int(bar), "timer": int(timer),
                           "title": row["title"].strip(),
                           "objective": row["objective_text"].strip(),
                           "description": row["description"].strip(),
                           "completion": row["completion_text"].strip()})
        elif kind == "credit_creature":
            if credit is not None:
                raise SystemExit("rift_quests.csv: more than one credit_creature row")
            credit = {"id": entry, "name": row["title"].strip()}
        elif kind == "portal":
            # The single-display portal moved out on 2026-09-17 and became the
            # 17-row pool. A leftover row here would emit a template nothing
            # rolls, so it is an error rather than something to ignore.
            raise SystemExit("rift_quests.csv: the portal row moved to rift_portals.csv; delete it")
        else:
            raise SystemExit(f"rift_quests.csv: unknown kind {kind!r}")

    if credit is None:
        raise SystemExit("rift_quests.csv: a credit_creature row is required")
    for mode in ("nr", "gr"):
        if len([q for q in quests if q["mode"] == mode]) != 1:
            raise SystemExit(f"rift_quests.csv: exactly one {mode} quest row (one bar per mode, monster spawning S3)")
    return quests, credit


def read_portals():
    """rift_portals.csv: the entrance looks, one row per gameobject_template.

    Every look carries its own scale so a portal that sits too large is a data
    change and not a code change (ruling 2026-09-17). Nothing is defaulted here:
    a row with no scale is a CSV to fix, not a 1.0 to invent.
    """
    with PORTAL_SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit(f"{PORTAL_SOURCE}: empty")

    portals, entries, displays = [], set(), set()
    for row in rows:
        entry, display = row["entry_id"].strip(), row["display_id"].strip()
        if not entry.isdigit() or not display.isdigit():
            raise SystemExit(f"rift_portals.csv: entry_id {entry!r} and display_id {display!r} must be numbers")
        entry, display = int(entry), int(display)
        if entry == RETIRED_PORTAL_ENTRY:
            raise SystemExit(f"rift_portals.csv: {RETIRED_PORTAL_ENTRY} is the retired single-display portal")
        if entry in entries:
            raise SystemExit(f"rift_portals.csv: entry_id {entry} appears twice")
        # Two rows on one display would make the same look twice as likely as
        # the rest, which is not a pool of seventeen any more.
        if display in displays:
            raise SystemExit(f"rift_portals.csv: display_id {display} appears twice")
        entries.add(entry)
        displays.add(display)
        name = row["name"].strip()
        if not name:
            raise SystemExit(f"rift_portals.csv: portal {entry} has no name")
        try:
            scale = float(row["scale"].strip())
        except ValueError:
            raise SystemExit(f"rift_portals.csv: portal {entry} scale {row['scale']!r} is not a number")
        if scale <= 0:
            raise SystemExit(f"rift_portals.csv: portal {entry} scale must be positive")
        portals.append({"id": entry, "display": display, "name": name, "scale": scale})
    return portals


def exit_sql(portals):
    """rifts_0021: one exit-portal template per entrance look, and the table `.dc floor exit here` writes (rift floors F2)."""
    lines = [
        "-- Generated by generate_rifts.py from data/d3/rift_portals.csv; edit the sheet and rerun. Apply to the world database.",
        "-- Rift floors Part F2 (docs/proposals/rift-floors.md 4.4, 6.12): the exit portal of a floor wears a look rolled from the",
        "-- obelisk entrance's list, on a template of its own so a click runs the exit's code (entry = look entry + 40). Type 22",
        "-- like the entrance, so the Greater Rift rule 3 exception names these entries. dc_rift_exit_spot holds the spots the designer",
        "-- placed with `.dc floor exit here`; where a dungeon has none, the survey's far point (dc_rift_exit_point) stands.",
        "SET NAMES utf8mb4;",
        "DELETE FROM `gameobject_template` WHERE `entry` IN (" + ", ".join(str(p["id"] + EXIT_ENTRY_OFFSET) for p in portals) + ");",
        "INSERT INTO `gameobject_template`",
        "  (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, `size`,",
        "   `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`,",
        "   `Data10`, `Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`,",
        "   `Data19`, `Data20`, `Data21`, `Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`)",
        "VALUES",
    ]
    rows = [f"  -- {p['name']}\n  ({p['id'] + EXIT_ENTRY_OFFSET}, {PORTAL_GO_TYPE}, {p['display']}, {quote(EXIT_NAME)}, '', '', '', "
            f"{p['scale']}, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340)" for p in portals]
    lines.append(",\n".join(rows) + ";")
    lines += [
        "CREATE TABLE IF NOT EXISTS `dc_rift_exit_spot` (",
        "  `dungeon` VARCHAR(64) NOT NULL,",
        "  `x` DOUBLE NOT NULL,",
        "  `y` DOUBLE NOT NULL,",
        "  `z` DOUBLE NOT NULL,",
        "  `o` DOUBLE NOT NULL,",
        "  PRIMARY KEY (`dungeon`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='the designer''s exit spot per rift dungeon (.dc floor exit here); --export of generate_rift_survey.py writes them into the sheet';",
        "",
    ]
    return "\n".join(lines)


def exit_names_sql(portals, cap):
    """rifts_0025: the exit portal templates of every floor led to, named 'Floor N' (rifts_0021 named the 17 of floor 2 'Rift Exit')."""
    floors = range(2, cap + 1)
    entries = [p["id"] + EXIT_ENTRY_OFFSET + EXIT_FLOOR_STRIDE * (n - 2) for n in floors for p in portals]
    lines = [
        "-- Generated by generate_rifts.py from data/d3/rift_portals.csv and the rifts/rift_max_floors tunable; edit the sheets and rerun. Apply to the world database.",
        "-- Rift exit portals named for the floor they lead to (diablocraft-zuia, ruling 2026-10-09): the client reads a gameobject's name",
        "-- from its template, so every (entrance look, floor led to) pair has one: entry = look entry + 40 + 1000 * (N - 2), N = 2 to",
        f"-- rift_max_floors ({cap}), named 'Floor N'. Floor 2 replaces rifts_0021's 17 'Rift Exit' rows (same entries).",
        "SET NAMES utf8mb4;",
        "DELETE FROM `gameobject_template` WHERE `entry` IN (" + ", ".join(map(str, entries)) + ");",
        "INSERT INTO `gameobject_template`",
        "  (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, `size`,",
        "   `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`,",
        "   `Data10`, `Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`,",
        "   `Data19`, `Data20`, `Data21`, `Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`)",
        "VALUES",
    ]
    rows = [f"  -- Floor {n}, {p['name']}\n  ({p['id'] + EXIT_ENTRY_OFFSET + EXIT_FLOOR_STRIDE * (n - 2)}, {PORTAL_GO_TYPE}, {p['display']}, "
            f"{quote(f'Floor {n}')}, '', '', '', {p['scale']}, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340)"
            for n in floors for p in portals]
    lines.append(",\n".join(rows) + ";")
    lines.append("")
    return "\n".join(lines)


def orb_sql():
    """rifts_0016: the Greater Rift progress orb's gameobject template (part 4)."""
    return "\n".join([
        "-- Generated by generate_rifts.py from the rifts/gr_orb_display_id tunable; edit the sheet and",
        "-- rerun. Apply to the world database.",
        "-- Greater Rift part 4 (diablocraft-del2, card q-1006-02): the progress orb a promoted pack drops",
        "-- when its last member dies. A GENERIC object: nothing to click or loot; the module takes it",
        "-- when a run member walks within the pickup radius.",
        "SET NAMES utf8mb4;",
        f"DELETE FROM `gameobject_template` WHERE `entry` = {ORB_ENTRY};",
        "INSERT INTO `gameobject_template`",
        "  (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, `size`,",
        "   `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`,",
        "   `Data10`, `Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`,",
        "   `Data19`, `Data20`, `Data21`, `Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`)",
        "VALUES",
        f"  ({ORB_ENTRY}, {ORB_GO_TYPE}, {ORB_DISPLAY}, {quote(ORB_NAME)}, '', '', '', 1, "
        "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340);",
        "",
    ])


def urshi_sql():
    """rifts_0017: Urshi's creature template and model (part 11)."""
    return "\n".join([
        "-- Generated by generate_rifts.py from the rifts/gr_urshi_display_id tunable; edit the sheet and",
        "-- rerun. Apply to the world database.",
        "-- Greater Rift part 11 (diablocraft-z94g): Urshi, the NPC who stands where an in-time Guardian died.",
        "-- Cloned from the same stock row as the hub artisans (generate_hub.py), so the INSERT does not depend",
        "-- on which creature_template columns carry a DEFAULT; identity, faction, gossip flag and script are",
        "-- overridden. The module summons her (dc_gr_urshi.cpp); she is never spawned from the `creature` table.",
        "SET NAMES utf8mb4;",
        f"DELETE FROM `creature_template` WHERE `entry` = {URSHI_ENTRY};",
        "CREATE TEMPORARY TABLE `dc_urshi_template` LIKE `creature_template`;",
        f"INSERT INTO `dc_urshi_template` SELECT * FROM `creature_template` WHERE `entry` = {CREDIT_CLONE_SOURCE};",
        "UPDATE `dc_urshi_template` SET",
        f"  `entry` = {URSHI_ENTRY}, `name` = {quote(URSHI_NAME)}, `subname` = {quote(URSHI_SUBNAME)},",
        f"  `faction` = {URSHI_FACTION}, `npcflag` = {URSHI_NPCFLAG}, `ScriptName` = {quote(URSHI_SCRIPT)}, `AIName` = '',",
        "  `gossip_menu_id` = 0, `lootid` = 0, `pickpocketloot` = 0, `skinloot` = 0, `KillCredit1` = 0, `KillCredit2` = 0;",
        "INSERT INTO `creature_template` SELECT * FROM `dc_urshi_template`;",
        "DROP TEMPORARY TABLE `dc_urshi_template`;",
        f"DELETE FROM `creature_template_model` WHERE `CreatureID` = {URSHI_ENTRY};",
        "INSERT INTO `creature_template_model` (`CreatureID`, `Idx`, `CreatureDisplayID`, `DisplayScale`, `Probability`, `VerifiedBuild`)",
        f"  VALUES ({URSHI_ENTRY}, 0, {URSHI_DISPLAY}, 1, 1, 0);",
        "",
    ])


def keeper_sql(quests):
    """rifts_0018: the Rift Keeper ends the Greater Rift quests too (diablocraft-b3wi).

    rifts_0011 related only the Nephalem variants to the Keeper, so the core refused a Greater Rift
    turn-in (Object::hasInvolvedQuest) and the 30 second countdown 09-rifts 2 step 6 and 7.9.7 hang on
    the turn-in never started. Only the Greater rows are touched here; the Nephalem ones stay 0011's.

    This migration is applied (b3wi) and stays as it shipped: the three Greater variants rifts_0011 made. Monster spawning S3
    kept one of them in the sheet, and rifts_0019 deletes the questender rows of the other two."""
    gr = [q for q in quests if q["mode"] == "gr"]
    ids = ", ".join(str(i) for i in sorted({q["id"] for q in gr} | {q for q in RETIRED_QUESTS if q > gr[0]["id"]}))
    return "\n".join([
        "-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the CSV and rerun.",
        "-- Apply to the world database.",
        "-- Greater Rift: the Rift Keeper ends the Greater Rift quests as it ends the Nephalem ones",
        "-- (09-rifts 7.2, 7.9.7; diablocraft-b3wi). The obelisk still starts none of them: the ready check",
        "-- gives the quest.",
        f"DELETE FROM `creature_questender` WHERE `id` = {KEEPER_ENTRY} AND `quest` IN ({ids});",
        "INSERT INTO `creature_questender` (`id`, `quest`) VALUES",
        ",\n".join(f"  ({KEEPER_ENTRY}, {i})" for i in ids.split(", ")) + ";",
        "",
    ])


def bar_sql(quests):
    """rifts_0019: one quest per mode, counting the whole bar (monster spawning S3, 3.9.4).

    rifts_0011 (applied, frozen) wrote six variants counting 20 units per kill of a dungeon's kills_required. The bar is
    D3's progress points now, in hundredths, the same for every dungeon: the two kept quests take the new count and the
    four others, with every relation that offers or ends them, go. It is applied at 65,000 (D3's 650 points) and stays so:
    the count here is FIRST_BAR_HUNDREDTHS, not the sheet's, which moved to 30,000 in rifts_0032 (bar_target_sql)."""
    retired = ", ".join(str(q) for q in RETIRED_QUESTS)
    lines = [
        "-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the CSV and rerun.",
        "-- Apply to the world database, after rifts_0011 and rifts_0018.",
        "-- Monster spawning S3 (docs/proposals/monster-spawning.md 3.9.4): one rift quest per mode, counting",
        "-- hundredths of a D3 progress point; 65,000 = the 650 points that fill the bar, inside the core's",
        "-- 16-bit quest counter. The kills_required variants are retired.",
        "SET NAMES utf8mb4;",
        f"DELETE FROM `quest_template_addon` WHERE `ID` IN ({retired});",
        f"DELETE FROM `quest_template` WHERE `ID` IN ({retired});",
        f"DELETE FROM `gameobject_queststarter` WHERE `id` = {OBELISK_ENTRY} AND `quest` IN ({retired});",
        f"DELETE FROM `creature_questender` WHERE `id` = {KEEPER_ENTRY} AND `quest` IN ({retired});",
    ]
    for quest in quests:
        lines.append(f"UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = {FIRST_BAR_HUNDREDTHS} WHERE `ID` = {quest['id']};")
    return "\n".join(lines) + "\n"


def bar_target_sql(quests):
    """rifts_0032: the rift progress target, from 65,000 to the sheet's count (ruling 2026-10-16, diablocraft-owe7u).

    rifts_0019 (applied, frozen) set 65,000 on the two bar quests. The sheet's bar_hundredths is 30,000 now (300 D3 points fill
    the bar): the same two rows take it. Count only: no template, addon or relation row is added or removed. The server reads
    the count from quest_template when it starts, so a restart picks it up."""
    lines = [
        "-- Generated from data/d3/rift_quests.csv by generate_rifts.py; edit the CSV and rerun.",
        "-- Apply to the world database, after rifts_0019.",
        "-- ruling 2026-10-16 (diablocraft-owe7u): the rift progress target is " + ", ".join(sorted({f"{q['units']:,}" for q in quests})) + " hundredths of a",
        "-- D3 progress point (300 points fill the bar), down from the 65,000 rifts_0019 set. Both bar quests.",
    ]
    for quest in quests:
        lines.append(f"UPDATE `quest_template` SET `RequiredNpcOrGoCount1` = {quest['units']} WHERE `ID` = {quest['id']};")
    return "\n".join(lines) + "\n"


def nr_orb_display():
    """The orange orb's display: the nr_orb_display_id row, else the purple look as a stand-in; (display, is_placeholder)."""
    try:
        return int(tunables_csv.value("rifts", "nr_orb_display_id")), False
    except tunables_csv.MissingTunable:
        return ORB_DISPLAY, True


def nr_orb_scale():
    """The orange orb's size: the nr_orb_scale row (the Flame Sphere is 4.6 yards across at 1)."""
    return tunables_csv.value("rifts", "nr_orb_scale")


def nr_orb_sql(display, scale):
    """rifts_0031: the Nephalem Rift's progress orb, the orange one (monster spawning S3), with the look the designer picked."""
    return "\n".join([
        "-- Generated by generate_rifts.py from the rifts/nr_orb_display_id tunable; edit the sheet and",
        "-- rerun. Apply to the world database.",
        "-- Monster spawning S3 (docs/proposals/monster-spawning.md 3.9.4): the progress orb a Nephalem Rift's elite",
        "-- pack drops (ruling 2026-10-08, decisions.md b4171f62), a second object beside the purple Greater Rift one",
        "-- (rifts_0016). A GENERIC object: nothing to click or loot; the module takes it when a run member walks",
        "-- within the pickup radius. The designer picked its look on dev (2026-10-16, diablocraft-ivtf5): display 9701, the",
        "-- Flame Sphere, at the size the nr_orb_scale row gives it. rifts_0020 made the first template wearing the purple",
        "-- stand-in at size 1; this is the whole render again.",
        "SET NAMES utf8mb4;",
        f"DELETE FROM `gameobject_template` WHERE `entry` = {NR_ORB_ENTRY};",
        "INSERT INTO `gameobject_template`",
        "  (`entry`, `type`, `displayId`, `name`, `IconName`, `castBarCaption`, `unk1`, `size`,",
        "   `Data0`, `Data1`, `Data2`, `Data3`, `Data4`, `Data5`, `Data6`, `Data7`, `Data8`, `Data9`,",
        "   `Data10`, `Data11`, `Data12`, `Data13`, `Data14`, `Data15`, `Data16`, `Data17`, `Data18`,",
        "   `Data19`, `Data20`, `Data21`, `Data22`, `Data23`, `AIName`, `ScriptName`, `VerifiedBuild`)",
        "VALUES",
        f"  ({NR_ORB_ENTRY}, {ORB_GO_TYPE}, {display}, {quote(NR_ORB_NAME)}, '', '', '', {scale:g}, "
        "0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', '', 12340);",
        "",
    ])


def main():
    with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit(f"{SOURCE}: empty")
    recommended = [row for row in rows if row["recommended"].strip().lower() == "yes"]
    if not recommended:
        raise SystemExit(f"{SOURCE}: no rows marked recommended")

    # The pool is keyed on a synthetic id, not on map_id: Scarlet Monastery's
    # Graveyard and Library are separate rift destinations that share map 189,
    # each with its own entrance. Two parties picking different wings simply get
    # two instances of the same map, which is ordinary WoW behaviour.
    seen = set()
    for row in recommended:
        map_id = row["map_id"].strip()
        if not map_id.isdigit():
            raise SystemExit(f"{row['name']}: map_id {map_id!r} is not a number")
        entrance = (map_id, row["entry_x"], row["entry_y"], row["entry_z"])
        if entrance in seen:
            raise SystemExit(f"{row['name']}: duplicate map and entrance in the pool")
        seen.add(entrance)
        for column in ("entry_x", "entry_y", "entry_z", "entry_o", "kills_required"):
            try:
                float(row[column])
            except ValueError:
                raise SystemExit(f"{row['name']}: {column} {row[column]!r} is not a number")
        if int(row["kills_required"]) <= 0:
            raise SystemExit(f"{row['name']}: kills_required must be positive")

    lines = [
        "-- Generated from data/d3/rift_dungeons.csv by generate_rifts.py; edit the",
        "-- CSV and rerun. Apply to the world database.",
        "-- 09-rifts F1: the stage 1 rift pool, recommended rows only.",
        "SET NAMES utf8mb4;",
        "DROP TABLE IF EXISTS `dc_rift_dungeon`;",
        "CREATE TABLE `dc_rift_dungeon` (",
        "  `dungeon_id` INT NOT NULL,",
        "  `map_id` INT NOT NULL,",
        "  `name` LONGTEXT NOT NULL,",
        "  `entry_x` DOUBLE NOT NULL,",
        "  `entry_y` DOUBLE NOT NULL,",
        "  `entry_z` DOUBLE NOT NULL,",
        "  `entry_o` DOUBLE NOT NULL,",
        "  `kills_required` INT NOT NULL COMMENT 'Tunable; derived from approximate_length',",
        "  `approximate_length` LONGTEXT NOT NULL,",
        "  PRIMARY KEY (`dungeon_id`),",
        "  KEY `idx_dc_rift_dungeon_map` (`map_id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "INSERT INTO `dc_rift_dungeon` (`dungeon_id`, `map_id`, `name`, `entry_x`, `entry_y`, "
        "`entry_z`, `entry_o`, `kills_required`, `approximate_length`) VALUES",
    ]
    records = []
    for index, row in enumerate(recommended, start=1):
        records.append("({}, {}, {}, {}, {}, {}, {}, {}, {})".format(
            index, int(row["map_id"]), quote(row["name"]),
            float(row["entry_x"]), float(row["entry_y"]), float(row["entry_z"]), float(row["entry_o"]),
            int(row["kills_required"]), quote(row["approximate_length"])))
    lines.append(",\n".join(records) + ";")
    sql = "\n".join(lines) + "\n"

    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "rift_dungeons.sql").write_bytes(sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0001_dungeon_pool.sql", sql)
    print(f"dc_rift_dungeon: {len(recommended)} dungeons "
          f"(of {len(rows)} in the CSV; the rest are not recommended)")
    print(f"  handled {(UPDATES / 'rifts_0001_dungeon_pool.sql').relative_to(REPO_ROOT)}")

    zones = read_open_zones()
    zone_text = open_zone_sql(zones)
    (GENERATED / "rift_open_zone_pool.sql").write_bytes(zone_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / OPEN_ZONE_MIGRATION, zone_text)
    print(f"  handled {(UPDATES / OPEN_ZONE_MIGRATION).relative_to(REPO_ROOT)} (open zones in the pool: {', '.join(z['name'] for z in zones)})")
    zone_rows = read_open_zone_rows()
    table_text = open_zone_table_sql(zone_rows)
    (GENERATED / "rift_open_zones.sql").write_bytes(table_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / OPEN_ZONE_TABLE_MIGRATION, table_text)
    print(f"  handled {(UPDATES / OPEN_ZONE_TABLE_MIGRATION).relative_to(REPO_ROOT)} ({len(zone_rows)} open zones; "
          f"off until their entrance is set: {', '.join(r['name'] for r in zone_rows if not entrance_of(r)) or 'none'})")

    quests, credit = read_quests()
    portals = read_portals()
    bar_text = bar_sql(quests)
    (GENERATED / "rift_one_bar.sql").write_bytes(bar_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0019_one_bar.sql", bar_text)
    target_text = bar_target_sql(quests)
    (GENERATED / "rift_bar_target.sql").write_bytes(target_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / BAR_TARGET_MIGRATION, target_text)
    orb_text = orb_sql()
    (GENERATED / "rift_orb.sql").write_bytes(orb_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0016_gr_orb.sql", orb_text)
    print(f"  handled {(UPDATES / 'rifts_0016_gr_orb.sql').relative_to(REPO_ROOT)} (orb {ORB_ENTRY}, display {ORB_DISPLAY})")
    exit_text = exit_sql(portals)
    (GENERATED / "rift_floor_exit.sql").write_bytes(exit_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / EXIT_MIGRATION, exit_text)
    print(f"  handled {(UPDATES / EXIT_MIGRATION).relative_to(REPO_ROOT)} ({len(portals)} exit portal templates "
          f"{portals[0]['id'] + EXIT_ENTRY_OFFSET}-{portals[-1]['id'] + EXIT_ENTRY_OFFSET}, dc_rift_exit_spot)")
    names_text = exit_names_sql(portals, int(tunables_csv.value("rifts", "rift_max_floors")))
    (GENERATED / "rift_floor_exit_names.sql").write_bytes(names_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / EXIT_NAMES_MIGRATION, names_text)
    print(f"  handled {(UPDATES / EXIT_NAMES_MIGRATION).relative_to(REPO_ROOT)} (exit portals named 'Floor N', N = 2 to rift_max_floors)")
    urshi_text = urshi_sql()
    (GENERATED / "rift_urshi.sql").write_bytes(urshi_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0017_urshi.sql", urshi_text)
    print(f"  handled {(UPDATES / 'rifts_0017_urshi.sql').relative_to(REPO_ROOT)} (Urshi {URSHI_ENTRY}, display {URSHI_DISPLAY})")
    keeper_text = keeper_sql(quests)
    (GENERATED / "rift_keeper.sql").write_bytes(keeper_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0018_gr_keeper_turnin.sql", keeper_text)
    print(f"  handled {(UPDATES / 'rifts_0018_gr_keeper_turnin.sql').relative_to(REPO_ROOT)} (Keeper {KEEPER_ENTRY} ends the Greater quests)")
    nr_display, placeholder = nr_orb_display()
    nr_orb_text = nr_orb_sql(nr_display, nr_orb_scale())
    (GENERATED / "rift_nr_orb.sql").write_bytes(nr_orb_text.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / NR_ORB_MIGRATION, nr_orb_text)
    print(f"  handled {(UPDATES / NR_ORB_MIGRATION).relative_to(REPO_ROOT)} (Nephalem orb {NR_ORB_ENTRY}, display {nr_display}"
          + (", PLACEHOLDER: nr_orb_display_id is blank, wearing the purple look)" if placeholder else ")"))
    print(f"rift quests: {len(quests)} templates, one bar each: "
          f"{', '.join(f'{q['mode']} {q['id']} = {q['units']} hundredths' for q in quests)}")
    print(f"  credit creature {credit['id']}; entrance portal pool: {len(portals)} looks, "
          f"entries {portals[0]['id']}-{portals[-1]['id']}, type {PORTAL_GO_TYPE} "
          f"(retiring {RETIRED_PORTAL_ENTRY})")
    print(f"  handled {(UPDATES / 'rifts_0019_one_bar.sql').relative_to(REPO_ROOT)} (retiring quests {list(RETIRED_QUESTS)}; counts stay {FIRST_BAR_HUNDREDTHS})")
    print(f"  handled {(UPDATES / BAR_TARGET_MIGRATION).relative_to(REPO_ROOT)} (the bar moves to {', '.join(sorted({str(q['units']) for q in quests}))})")

if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
