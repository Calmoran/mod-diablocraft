#!/usr/bin/env python3
"""Generate the family monsters' rows (monster-families.md Part 1: the look, the numbers and the ability table).

Reads data/d3/monster_family_models.csv (import_monster_picks.py writes it) and the roster, and writes:
the creature_template row, its creature_template_model rows (every skin the picked NPC has, each with
its probability and scale, times the designer's size), its creature_equip_template row (main hand, off hand,
ranged) and, for a monster with a weapon or an aura, its creature_template_addon (sheath state: 1 melee drawn,
2 ranged drawn; auras = the CSV auras column, spell ids). Every roster monster gets rows: a monster the designer has not
picked (picked = no) stands in with its family's first candidate, the placeholder the sheet already holds
(monster-families.md section 4: "until a pick lands, a family plays on dev with a placeholder"), except the monsters
in HELD_BACK, which wait for a ruling.

The entry is FAMILY_ENTRY_BASE plus the monster's place in monster_roster.csv (1 to 65), so a monster
keeps its entry whatever batch picks it and Part 1's generator finds the same rows. The range keeps
the champion and rare clone offsets (8000000 and 9000000 + entry) clear of the stock clones of
generate_rift_elites.py: those go up to 9925052, this range is 950001 and up.

Part 1 (diablocraft-uole) adds the numbers, with no game change on its own: HealthModifier is the roster's Life
multiplier (a monster the roster leaves NOT PUBLISHED reads its `monsters.csv` `family_life_<monster>` row),
DamageModifier the `family_damage_<monster>` row, speed_run the monster's speed class (`family_speed_*` rows;
the roster's word "slow", "average", "fast" or "very fast", any other qualifier is Normal), BaseAttackTime 1000
(Blizzard's AttSpd 1.00 s), RegenHealth 0 and flags_extra NO_PARRY | NO_BLOCK | NO_CRUSHING_BLOWS (conformance
D4). Every monster also gets a champion (8000000 + entry, rank 1) and a rare (9000000 + entry, rank 2)
row with the same models, equipment and addon (B3), and `dc_family_ability` holds the ability table of
`data/tunables/monster_abilities.csv` for all 65 roster monsters, picked or not.

Still placeholders for Part 2 and Part 3: level 80, friendly (faction 35, so a monster added with `.npc add`
does not fight), no loot, no AI. `dc_monster_family` lists the entries by family for `.dc lineup`.

Makes no database read; run from the repo root:

    python mod-diablocraft/scripts/generate/monsters/generate_monster_models.py
"""

import csv
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import tunables_csv
from applied_migrations import write_migration
from generate_area_copies import insert

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
GENERATED = MODULE_ROOT / "data/generated"
UPDATES = MODULE_ROOT / "data/sql/db-world/updates"
MODELS = MODULE_ROOT / "data/d3/monster_family_models.csv"
ROSTER = MODULE_ROOT / "data/d3/monster_roster.csv"
ABILITIES = MODULE_ROOT / "data/tunables/monster_abilities.csv"
# monsters_0001 is applied on dev and monsters_0002 (batch 1's tweak round) and monsters_0003 (the roster renames,
# diablocraft-ibrp) may be: Part 1's numbers, clones and ability table are a new migration that deletes the
# ranges and inserts them again.
MIGRATION = "monsters_0004_family_data.sql"
# rifts_0006_elite_clones.sql (applied, frozen) still deletes every creature_template from 8000000 up, which on a FRESH
# database wipes the family clones monsters_0004 made (it sorts first). This migration sorts after rifts_0006 and
# inserts the clone rows again, rendered by the same code as monsters_0004 (diablocraft-bilc, the PM's ruling on mapz).
CLONES_MIGRATION = "rifts_0023_family_clones.sql"

# Constants, not tunables: FAMILY_ENTRY_BASE and FAMILY_ENTRY_SPAN are identifiers (the range this generator
# owns); the sheath states are engine enums (SHEATH_STATE_MELEE, SHEATH_STATE_RANGED); PLACEHOLDER's level, expansion,
# faction and unit class are marked placeholders until Part 1 sets them.
FAMILY_ENTRY_BASE = 950000
FAMILY_ENTRY_SPAN = 1000
SHEATH_MELEE = 1
SHEATH_RANGED = 2
# Constants too: the champion and rare clone bases are generate_rift_elites.py's (identifiers); the ranks are the
# engine's (1 elite, 2 rare elite); ATTACK_MS is Blizzard's AttSpd 1.00 s for every monster (diiis-catalogue.md 2.2,
# MonsterLevels.gam); FLAGS_EXTRA is CREATURE_FLAG_EXTRA_NO_PARRY (0x4) | NO_BLOCK (0x10) | NO_CRUSHING_BLOWS (0x20),
# chosen on purpose (creature-conformance.md D4): D3's monsters neither parry nor block, and WoW's crushing blow for a
# level gap has no D3 counterpart.
CHAMPION_BASE = 8000000
RARE_BASE = 9000000
RANK_CHAMPION = 1
RANK_RARE = 2
ATTACK_MS = 1000
FLAGS_EXTRA = 0x4 | 0x10 | 0x20
# The roster's movement word -> the speed class (3.7 (b)); an unlisted qualifier ("fast charge", "flying/phase")
# describes an ability, not the run, so it is Normal.
SPEED_CLASSES = {"slow": "slow", "average": "normal", "fast": "fast", "very fast": "very_fast"}

# Plain placeholder columns of creature_template; the look and the name are the only real ones.
PLACEHOLDER = {
    "difficulty_entry_1": 0, "difficulty_entry_2": 0, "difficulty_entry_3": 0, "KillCredit1": 0, "KillCredit2": 0,
    "subname": None, "IconName": None, "gossip_menu_id": 0, "minlevel": 80, "maxlevel": 80, "exp": 2,
    "faction": 35, "npcflag": 0, "speed_walk": 1, "speed_run": 1.14286, "speed_swim": 1, "speed_flight": 1,
    "detection_range": 20, "rank": 0, "dmgschool": 0, "DamageModifier": 1, "BaseAttackTime": 2000,
    "RangeAttackTime": 2000, "BaseVariance": 1, "RangeVariance": 1, "unit_class": 1, "unit_flags": 0,
    "unit_flags2": 0, "dynamicflags": 0, "family": 0, "type": 0, "type_flags": 0, "lootid": 0,
    "pickpocketloot": 0, "skinloot": 0, "PetSpellDataId": 0, "VehicleId": 0, "mingold": 0, "maxgold": 0,
    "AIName": "", "MovementType": 0, "HoverHeight": 1, "HealthModifier": 1, "ManaModifier": 1,
    "ArmorModifier": 1, "ExperienceModifier": 1, "RacialLeader": 0, "movementId": 0, "RegenHealth": 1,
    "CreatureImmunitiesId": 0, "flags_extra": 0, "ScriptName": "", "VerifiedBuild": None,
}


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def entries():
    """{monster name: entry}, from the roster's order."""
    roster = read_csv(ROSTER)
    if len(roster) >= FAMILY_ENTRY_SPAN:
        raise SystemExit("the roster outgrew the family entry range")
    return {row["name"]: FAMILY_ENTRY_BASE + index for index, row in enumerate(roster, 1)}


def displays(text):
    """'id:scale:probability;...' -> [(id, scale, probability)]."""
    out = []
    for part in text.split(";"):
        display, scale, probability = part.split(":")
        out.append((int(display), float(scale), float(probability)))
    return out


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def tunable(name):
    return tunables_csv.value("monsters", name)


def speed_class(word):
    """'NOT PUBLISHED (very fast)' -> 'very_fast'."""
    found = re.search(r"\(([^)]*)\)", word)
    return SPEED_CLASSES.get(found.group(1).strip() if found else "", "normal")


def numbers(roster_row):
    """(HealthModifier, DamageModifier, speed_run) of one roster monster."""
    name = roster_row["name"]
    life = roster_row["life_multiplier"].strip()
    health = float(life) if re.fullmatch(r"[0-9.]+", life) else tunable(f"family_life_{slug(name)}")
    return (health, tunable(f"family_damage_{slug(name)}"),
            tunable("family_speed_" + speed_class(roster_row["movement_speed"])))


def rows_for(row, entry, roster_row):
    """(creature_template, [model rows], equip row, addon row or None) of one picked monster."""
    size = float(row["scale"]) if row["scale"] else 1.0
    template = {"entry": entry, "name": row["monster"], **PLACEHOLDER}
    health, damage, speed = numbers(roster_row)
    template.update(HealthModifier=health, DamageModifier=damage, speed_run=speed, BaseAttackTime=ATTACK_MS,
                    RegenHealth=0, flags_extra=FLAGS_EXTRA)
    models = [{"CreatureID": entry, "Idx": index, "CreatureDisplayID": display,
               "DisplayScale": round(scale * size, 4), "Probability": probability, "VerifiedBuild": None}
              for index, (display, scale, probability) in enumerate(displays(row["displays"]))]
    items = [int(row[column] or 0) for column in ("mainhand", "offhand", "ranged")]
    equip = {"CreatureID": entry, "ID": 1, "ItemID1": items[0], "ItemID2": items[1], "ItemID3": items[2],
             "VerifiedBuild": None}
    addon = None
    if any(items) or row["auras"]:
        # A bow is drawn as ranged; any hand item is drawn as melee. Both when a monster has both.
        addon = {"entry": entry, "path_id": 0, "mount": 0, "bytes1": 0,
                 "bytes2": (SHEATH_RANGED if items[2] and not (items[0] or items[1]) else SHEATH_MELEE) if any(items) else 0,
                 "emote": 0, "visibilityDistanceType": 0, "auras": row["auras"] or None}
    return template, models, equip, addon


def clones(template, models, equip, addon):
    """The champion and the rare of one family monster: the same rows under the clone entries (B3)."""
    for base, rank, prefix in ((CHAMPION_BASE, RANK_CHAMPION, "Champion"), (RARE_BASE, RANK_RARE, "Rare")):
        entry = base + template["entry"]
        yield ({**template, "entry": entry, "rank": rank, "name": f"{prefix} {template['name']}"[:100]},
               [{**model, "CreatureID": entry} for model in models], {**equip, "CreatureID": entry},
               {**addon, "entry": entry} if addon else None)


# A roster monster that gets no rows until the PM rules (diablocraft-o18f): the designer's note on the sheet doubts that the
# monster exists ("this does not appear to exist as an NPC? D3 Wiki does not find anything"), and the brief does not
# settle whether a doubted monster is built, dropped or renamed. Its ability rows stay in dc_family_ability.
HELD_BACK = {"Decaying Cryptstalker"}

# Where an ability cell comes from. A number comes with game_data (Blizzard's client data), roster (the roster sheet)
# or donor (the WoW spell the ability borrows: its cast time, range and recovery, monster-families.md 3.1 (c)); a blank
# cell is `tunable` (an unpublished number: a blank, PLACEHOLDER row of monsters.csv, yours to set on dev) or n/a
# (nothing to time).
SOURCES = {"game_data", "roster", "donor", "tunable", "n/a"}
CELLS = (("cooldown_s", "cooldown_source"), ("range_min_yd", "range_source"), ("range_max_yd", "range_source"),
         ("windup_s", "windup_source"), ("projectiles", "projectiles_source"), ("wow_spell", "wow_spell_source"))
TUNABLES_CSV = MODULE_ROOT / "data/tunables/monsters.csv"
KINDS = ("melee_swing melee_heavy_slam ranged_bolt projectile_volley channeled_beam cone_breath ground_hazard_dot "
         "ground_detonation charge_rush leap_slam summon_minions suicide_bomb buff_roar shield_deflection "
         "heal_cannibalize teleport_reposition burrow_submerge pull_vortex wall_barrier crowd_control_trap").split()


def tunable_key(row):
    """The name every tunable row of one ability starts with: ability_<monster>_<ability>."""
    return f"ability_{slug(row['monster'])}_{slug(row['ability'])}"


def ability_rows(ids):
    """One dc_family_ability row per line of monster_abilities.csv, numbered per monster in file order.

    Every cell names its source (the *_source columns) and a cell and its source agree: a number comes with
    game_data, roster or donor; a blank is `tunable` (and its row is in monsters.csv, blank and marked PLACEHOLDER) or
    n/a (a passive has nothing to time)."""
    seen = {}
    keys = set()
    sheet = {row["name"]: row for row in read_csv(TUNABLES_CSV)}
    for line, row in enumerate(read_csv(ABILITIES), 2):
        where = f"{ABILITIES.name} line {line} ({row['monster']}: {row['ability']})"
        if row["monster"] not in ids:
            raise SystemExit(f"{where}: not a roster monster")
        if row["kind"] not in KINDS and row["kind"] != "passive":
            raise SystemExit(f"{where}: kind {row['kind']!r} is none of the 20 archetypes or passive")
        if row["kind"] != "passive":
            tunable(f"ability_damage_{row['kind']}")                        # the kind's damage row exists
        key = tunable_key(row)
        if key in keys:
            raise SystemExit(f"{where}: another ability of this monster has the same tunable name {key}")
        keys.add(key)
        cells = {}
        half = bool(row["range_min_yd"] or row["range_max_yd"])
        for column, source in CELLS:
            if row[source] not in SOURCES:
                raise SystemExit(f"{where}: {source} {row[source]!r} is none of {sorted(SOURCES)}")
            if row[column] and row[source] not in ("game_data", "roster", "donor"):
                raise SystemExit(f"{where}: {column} holds a number but its source is {row[source]}")
            if not row[column] and row[source] in ("game_data", "roster", "donor") and not (half and column.startswith("range_")):
                raise SystemExit(f"{where}: {column} is blank but its source is {row[source]}")
            if not row[column] and row[source] == "tunable":
                # A blank cell the sheet leaves to the designer: its tunable row exists, is blank and says PLACEHOLDER.
                name = f"{key}_{column}"
                found = sheet.get(name)
                if not found or found["value"] or found["d3_value"] or "PLACEHOLDER" not in found["notes"]:
                    raise SystemExit(f"{where}: {column} is tunable but monsters.csv has no blank PLACEHOLDER row {name}")
            cells[column] = float(row[column]) if row[column] else None
        if row["wow_spell_source"] == "donor" and not cells["wow_spell"]:
            raise SystemExit(f"{where}: wow_spell has the source donor and no spell id")
        if not row["source"].strip():
            raise SystemExit(f"{where}: no source text")
        entry = ids[row["monster"]]
        seen[entry] = seen.get(entry, 0) + 1
        yield {"entry": entry, "seq": seen[entry], "ability": row["ability"], "kind": row["kind"],
               "trigger_text": row["trigger"], "cooldown_s": cells["cooldown_s"],
               "range_min_yd": cells["range_min_yd"], "range_max_yd": cells["range_max_yd"],
               "windup_s": cells["windup_s"],
               "projectiles": None if cells["projectiles"] is None else int(cells["projectiles"]),
               "wow_spell": int(cells["wow_spell"] or 0), "cooldown_source": row["cooldown_source"],
               "range_source": row["range_source"], "windup_source": row["windup_source"],
               "projectiles_source": row["projectiles_source"], "wow_spell_source": row["wow_spell_source"],
               "tunable_key": key}


def template_lines(template, models, equip, addon):
    """The INSERTs of one creature entry: its template, models, equipment and addon (shared by both migrations)."""
    lines = [insert("creature_template", template)]
    lines += [insert("creature_template_model", model) for model in models]
    lines.append(insert("creature_equip_template", equip))
    if addon:
        lines.append(insert("creature_template_addon", addon))
    return lines


def picked_monsters():
    return [row for row in read_csv(MODELS) if row["monster"] not in HELD_BACK]


def render_clones():
    """rifts_0023: the champion and rare clone rows of monsters_0004, deleted and inserted again."""
    ids = entries()
    roster = {row["name"]: row for row in read_csv(ROSTER)}
    low, high = FAMILY_ENTRY_BASE + 1, FAMILY_ENTRY_BASE + FAMILY_ENTRY_SPAN - 1
    lines = [
        "-- Generated by mod-diablocraft/scripts/generate_monster_models.py from data/d3/monster_family_models.csv,",
        "-- data/d3/monster_roster.csv and data/tunables/monsters.csv; rerun it rather than hand-editing. Apply to the world DB.",
        "-- diablocraft-bilc: the champion and rare clones of the family monsters, the same rows monsters_0004 writes.",
        "-- rifts_0006_elite_clones.sql (applied, frozen) deletes every creature_template from 8000000 up, so on a fresh",
        "-- database it removes the clones monsters_0004 made before it; this file sorts after it and puts them back.",
        "SET NAMES utf8mb4;",
    ]
    for table, column in (("creature_template_addon", "entry"), ("creature_equip_template", "CreatureID"),
                          ("creature_template_model", "CreatureID"), ("creature_template", "entry")):
        for base in (CHAMPION_BASE, RARE_BASE):
            lines.append(f"DELETE FROM `{table}` WHERE `{column}` BETWEEN {base + low} AND {base + high};")
    for row in picked_monsters():
        built = rows_for(row, ids[row["monster"]], roster[row["monster"]])
        for clone in clones(*built):
            lines += template_lines(*clone)
    return "\n".join(lines) + "\n"


def render():
    ids = entries()
    roster = {row["name"]: row for row in read_csv(ROSTER)}
    picked = picked_monsters()
    low, high = FAMILY_ENTRY_BASE + 1, FAMILY_ENTRY_BASE + FAMILY_ENTRY_SPAN - 1
    lines = [
        "-- Generated by mod-diablocraft/scripts/generate_monster_models.py from data/d3/monster_family_models.csv,",
        "-- data/d3/monster_roster.csv, data/tunables/monsters.csv and data/tunables/monster_abilities.csv;",
        "-- rerun it rather than hand-editing. Apply to the world DB.",
        "-- monster-families.md Part 1: one creature_template per family monster (look and numbers) with its",
        "-- champion and rare clones, and the ability table of all 65 roster monsters. Faction and AI are placeholders",
        "-- for Parts 2 and 3.",
        "SET NAMES utf8mb4;",
        "CREATE TABLE IF NOT EXISTS `dc_monster_family` (",
        "  `entry` INT UNSIGNED NOT NULL, `family` VARCHAR(32) NOT NULL, `monster` VARCHAR(64) NOT NULL,",
        "  PRIMARY KEY (`entry`), KEY (`family`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        "CREATE TABLE IF NOT EXISTS `dc_family_ability` (",
        "  `entry` INT UNSIGNED NOT NULL, `seq` TINYINT UNSIGNED NOT NULL, `ability` VARCHAR(64) NOT NULL,",
        "  `kind` VARCHAR(32) NOT NULL, `trigger_text` VARCHAR(64) NOT NULL, `cooldown_s` DECIMAL(6,2) NULL,",
        "  `range_min_yd` DECIMAL(6,1) NULL, `range_max_yd` DECIMAL(6,1) NULL, `windup_s` DECIMAL(6,2) NULL,",
        "  `projectiles` TINYINT UNSIGNED NULL, `wow_spell` INT UNSIGNED NOT NULL DEFAULT 0,",
        "  `cooldown_source` VARCHAR(12) NOT NULL, `range_source` VARCHAR(12) NOT NULL,",
        "  `windup_source` VARCHAR(12) NOT NULL, `projectiles_source` VARCHAR(12) NOT NULL,",
        "  `wow_spell_source` VARCHAR(12) NOT NULL, `tunable_key` VARCHAR(96) NOT NULL,",
        "  PRIMARY KEY (`entry`, `seq`), KEY (`kind`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
    ]
    ranges = [(low, high), (CHAMPION_BASE + low, CHAMPION_BASE + high), (RARE_BASE + low, RARE_BASE + high)]
    for table, column in (("dc_monster_family", "entry"), ("dc_family_ability", "entry"),
                          ("creature_template_addon", "entry"), ("creature_equip_template", "CreatureID"),
                          ("creature_template_model", "CreatureID"), ("creature_template", "entry")):
        for first, last in ranges if table not in ("dc_monster_family", "dc_family_ability") else ranges[:1]:
            lines.append(f"DELETE FROM `{table}` WHERE `{column}` BETWEEN {first} AND {last};")
    for row in picked:
        entry = ids[row["monster"]]
        built = rows_for(row, entry, roster[row["monster"]])
        for template, models, equip, addon in (built, *clones(*built)):
            lines += template_lines(template, models, equip, addon)
        lines.append(insert("dc_monster_family", {"entry": entry, "family": row["family"], "monster": row["monster"]}))
    lines += [insert("dc_family_ability", ability) for ability in ability_rows(ids)]
    return "\n".join(lines) + "\n", picked, ids


def main():
    sql, picked, ids = render()
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "monster_models.sql").write_bytes(sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / MIGRATION, sql)
    write_migration(MODULE_ROOT, UPDATES / CLONES_MIGRATION, render_clones())
    print(f"creature_template: {len(picked)} family monsters, entries {min(ids[r['monster']] for r in picked)} to "
          f"{max(ids[r['monster']] for r in picked)}")
    print(f"  handled {(UPDATES / MIGRATION).relative_to(REPO_ROOT)}")
    print(f"  handled {(UPDATES / CLONES_MIGRATION).relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
