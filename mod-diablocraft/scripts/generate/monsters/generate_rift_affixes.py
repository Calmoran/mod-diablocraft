#!/usr/bin/env python3
"""Generate dc_rift_affix and dc_rift_guardian (09-rifts section 2 step 2, F5).

Two tables, both derived and neither hand-written:

  * dc_rift_affix from data/d3/elite_affixes.csv. Every one of the 28 rows goes
    in, so the pack rolls from the real D3 pool; the four with an implemented
    behaviour carry a shell id and the rest are name-only in stage 1 (`behaviour`
    says which). appears_on and the level gate parsed out of min_difficulty are
    the CSV's own restrictions, not ours. The roll columns come from two more
    verified files: `pool`, `level_60_limited` and `rollable` from
    elite_affix_pools.csv, and `minion_inherits` from elite_affix_eligibility.csv
    (13-elite-affixes section 4).
  * dc_rift_guardian from data/d3/rift_guardian_models.csv, restricted to the
    three guardians the designer picked for stage 1 (09 section 7 open item). Both of
    each guardian's mapped abilities become shells; the WoW creature and spell
    ids are the CSV's.

Shell ids are resolved from data/generated/spell_shells.csv, so this script can
never invent one: run generate_spells.py first.

Run from the repo root:

    python mod-diablocraft/scripts/generate/monsters/generate_rift_affixes.py

This script does not touch generate_sql.py or the dc_ tables it produces.
"""

import csv
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 125, 5, 6, 7, 8, 9, 10): difficulty names mapped to tier numbers; Mirrors 03-difficulty's ordering (section B).
# Constant (audit 126, 10, 6): bounds that reject a typo in an elite scale or champion pack size; Sanity checks on the designer's CSV values.

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
DATA = MODULE_ROOT / "data/d3"
# Phase 2 (Architect, 2026-09-19): loot_tuning.csv moved to data/tunables/ and
# out of data/d3/. Its runtime home is unchanged - still dc_loot_tuning.
TUNABLES = MODULE_ROOT / "data/tunables"
GENERATED = MODULE_ROOT / "data/generated"
UPDATES = MODULE_ROOT / "data/sql/db-world/updates"

# 09 section 7: the designer picks the stage 1 guardians from rift_guardians.csv.
STAGE_ONE_GUARDIANS = ("Bloodmaw", "Agnidox", "Cold Snap")

# How each stage-1 guardian ability is fought, from what the CSV's notes say it
# does: a nova bursts around the guardian, a leap closes on the current target
# and hits it, and frenzy is the self buff Lord Marrowgar's own Frenzy is.
GUARDIAN_ABILITY_BEHAVIOUR = {
    "Fireball Volley": "nova",
    "Flame Nova": "nova",
    "Cold Nova": "nova",
    "Leap Rage": "leap",
    "Charge": "leap",
    "Frenzy": "frenzy",
}

# The four affixes with an implemented behaviour in stage 1. Everything else in
# elite_affixes.csv is rolled and named but has no effect yet.
IMPLEMENTED = {
    # Stage 1.
    "Molten": "trail",       # ground damage under the elite, plus a death explosion
    "Frozen": "cluster",     # ice cluster at a player, arms, then explodes
    "Electrified": "reflect",  # discharges when the elite is struck
    "Plagued": "pool",       # poison pool under the elite
    # Stage 2. One behaviour name per affix; dc_rifts.cpp dispatches on it.
    "Arcane Enchanted": "beam",
    "Avenger": "avenger",
    "Desecrator": "desecrator",
    "Fast": "fast",
    "Fire Chains": "chains",
    "Frozen Pulse": "pulse",
    "Health Link": "healthlink",
    "Horde": "horde",
    "Illusionist": "illusionist",
    "Jailer": "jailer",
    "Juggernaut": "juggernaut",
    "Knockback": "knockback",
    "Mortar": "mortar",
    "Nightmarish": "nightmarish",
    "Orbiter": "orbiter",
    "Poison Enchanted": "poisonenchanted",
    "Reflects Damage": "reflectsdamage",
    "Shielding": "shielding",
    "Teleporter": "teleporter",
    "Thunderstorm": "thunderstorm",
    "Vortex": "vortex",
}

# Behaviours that deal no damage, so they need no shell. Everything else in
# IMPLEMENTED must have a shell of its own name in spell_shells.csv.
# Missile Dampening, Waller and Wormhole are deliberately absent from
# IMPLEMENTED: see docs/test-elite-affixes.md for why each is still name-only.
NO_SHELL = {"avenger", "fast", "healthlink", "horde", "illusionist", "juggernaut",
            "knockback", "nightmarish", "shielding", "teleporter", "vortex"}

# 01-stats S9. The CSV's damage_type spelling, lowercased, to our element name.
ELEMENTS = {"physical": "physical", "fire": "fire", "cold": "cold",
            "lightning": "lightning", "poison": "poison", "arcane": "arcane",
            "holy": "holy", "none": "physical", "same as player attack": "physical"}

# difficulty_tiers.csv order: tiers 1-4 are Normal, Hard, Expert, Master and
# 5 upward are Torment I onward. min_difficulty only ever names Normal or a
# Torment rank, so this covers every value in the CSV.
TIERS = {"normal": 1, "hard": 2, "expert": 3, "master": 4,
         "torment i": 5, "torment ii": 6, "torment iii": 7, "torment iv": 8,
         "torment v": 9, "torment vi": 10}
DIFFICULTY = re.compile(r"^\s*(?P<tier>[A-Za-z ]+?)\s*\(Level\s*(?P<level>\d+)\+\)\s*$")


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def read_csv(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def shell_ids():
    """name -> spell id, from generate_spells.py's own manifest."""
    manifest = GENERATED / "spell_shells.csv"
    if not manifest.is_file():
        raise SystemExit(f"{manifest}: run generate_spells.py first")
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        return {row["name"]: int(row["spell_id"]) for row in csv.DictReader(stream)}


def yes_no(value, where):
    text = value.strip().lower()
    if text in ("yes", "can"):
        return 1
    if text in ("no", "cannot"):
        return 0
    raise SystemExit(f"{where}: expected yes/no or can/cannot, got {value!r}")


def roll_rules():
    """affix -> (pool, level_60_limited, rollable, minion_inherits).

    13-elite-affixes section 4. Pool membership and the level-60 list are
    maxroll's and the wiki's; minion inheritance is per affix and comes from
    elite_affix_eligibility.csv, which is the authority on it.
    """
    pools = {}
    for row in read_csv("elite_affix_pools.csv"):
        name = row["affix_name"].strip()
        pool = row["pool"].strip().lower()
        if pool not in ("offensive", "defensive", "crowd_control"):
            raise SystemExit(f"{name}: unexpected pool {pool!r}")
        pools[name] = (pool,
                       yes_no(row["level_60_limited"], f"{name} level_60_limited"),
                       yes_no(row["rollable"], f"{name} rollable"))
    minions = {row["affix_name"].strip(): yes_no(row["minion"], f"{row['affix_name']} minion")
               for row in read_csv("elite_affix_eligibility.csv")
               if row["affix_name"].strip()}
    rules = {}
    for name, (pool, limited, rollable) in pools.items():
        if name not in minions:
            raise SystemExit(f"{name}: not in elite_affix_eligibility.csv")
        rules[name] = (pool, limited, rollable, minions[name])
    return rules


def affixes(shells):
    rows = read_csv("elite_affixes.csv")
    if not rows:
        raise SystemExit("elite_affixes.csv: empty")
    rules = roll_rules()
    out = []
    for row in rows:
        name = row["affix_name"].strip()
        match = DIFFICULTY.match(row["min_difficulty"])
        if not match:
            raise SystemExit(f"{name}: cannot parse min_difficulty {row['min_difficulty']!r}")
        tier = TIERS.get(match["tier"].strip().lower())
        if tier is None:
            raise SystemExit(f"{name}: unmapped difficulty {match['tier']!r}")
        appears = row["appears_on"].strip().lower()
        if appears not in ("both", "champion", "rare"):
            raise SystemExit(f"{name}: unexpected appears_on {appears!r}")
        element = ELEMENTS.get(row["damage_type"].strip().lower())
        if element is None:
            raise SystemExit(f"{name}: unmapped damage_type {row['damage_type']!r}")
        behaviour = IMPLEMENTED.get(name, "")
        shell = 0
        if behaviour and behaviour not in NO_SHELL:
            if name not in shells:
                raise SystemExit(f"{name}: no shell in spell_shells.csv; rerun generate_spells.py")
            shell = shells[name]
        if name not in rules:
            raise SystemExit(f"{name}: not in elite_affix_pools.csv")
        pool, limited, rollable, minion = rules[name]
        out.append((name, appears, tier, int(match["level"]), element, behaviour, shell,
                    pool, limited, rollable, minion, row["effect"].strip()))
    if len(out) != len({row[0] for row in out}):
        raise SystemExit("elite_affixes.csv: duplicate affix_name")
    missing = set(IMPLEMENTED) - {row[0] for row in out}
    if missing:
        raise SystemExit(f"implemented affixes missing from the CSV: {sorted(missing)}")
    unknown = set(rules) - {row[0] for row in out}
    if unknown:
        raise SystemExit(f"elite_affix_pools.csv names affixes the CSV does not: {sorted(unknown)}")
    return out


def guardians(shells):
    rows = {row["guardian"]: row for row in read_csv("rift_guardian_models.csv")}
    out = []
    for name in STAGE_ONE_GUARDIANS:
        row = rows.get(name)
        if row is None:
            raise SystemExit(f"{name}: not in rift_guardian_models.csv")
        abilities = []
        for slot in ("1", "2"):
            ability = row[f"ability_{slot}"].strip()
            shell_name = f"{name} - {ability}"
            if shell_name not in shells:
                raise SystemExit(f"{shell_name}: no shell in spell_shells.csv; "
                                 "add it to RIFT_SHELLS in generate_spells.py and rerun")
            behaviour = GUARDIAN_ABILITY_BEHAVIOUR.get(ability)
            if behaviour is None:
                raise SystemExit(f"{shell_name}: no behaviour in GUARDIAN_ABILITY_BEHAVIOUR")
            abilities.append((ability, shells[shell_name], int(row[f"ability_{slot}_spell_id"]),
                              behaviour))
        out.append((name, int(row["wow_creature_id"]), int(row["wow_display_id"]),
                    abilities[0], abilities[1]))
    return out


# 03-difficulty section 5 elite look. The three scale tunables live in
# loot_tuning.csv beside elite_promotion_pct, but 0001_dc_loot_tuning.sql is
# frozen once it has shipped (generate_sql.py keeps it immutable so an applied
# migration is never rewritten), so a new column reaches the table the way
# paragon's base_monster_xp does: an additive migration that adds it if it is
# missing and then writes the CSV's value.
ELITE_SCALES = ("elite_scale_champion", "elite_scale_rare", "elite_scale_minion")


def elite_scales():
    """The elite row's scale tunables, from loot_tuning.csv."""
    with (TUNABLES / "loot_tuning.csv").open(encoding="utf-8-sig") as handle:
        rows = {row["source"]: row for row in csv.DictReader(handle)}
    if "elite" not in rows:
        raise SystemExit("loot_tuning.csv has no elite row")
    values = {}
    for column in ELITE_SCALES:
        if column not in rows["elite"]:
            raise SystemExit(f"loot_tuning.csv has no {column} column")
        values[column] = float(rows["elite"][column])
        if not 0 < values[column] < 10:
            raise SystemExit(f"{column} is {values[column]}; a creature scale outside 0-10 is a typo")
    lines = [
        # The generated header below still says data/d3 on purpose: these deltas
        # have been applied, and an applied delta must stay byte-identical.
        "-- Generated from data/d3/loot_tuning.csv by generate_rift_affixes.py;",
        "-- edit the CSV and rerun. Apply to the world database.",
        "-- 03-difficulty section 5: how much larger a promoted pack is than the",
        "-- creature it was made from. The designer's tunables.",
        "SET NAMES utf8mb4;",
    ]
    for index, column in enumerate(ELITE_SCALES):
        # One prepared statement per column; MySQL has no ADD COLUMN IF NOT EXISTS.
        lines += [
            f"SET @dc_has_{index}=(SELECT COUNT(*) FROM information_schema.columns "
            f"WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' AND column_name='{column}');",
            f"SET @dc_ddl_{index}=IF(@dc_has_{index}=0,"
            f"'ALTER TABLE dc_loot_tuning ADD COLUMN {column} DECIMAL(4,2) NULL','DO 0');",
            f"PREPARE dc_stmt_{index} FROM @dc_ddl_{index};",
            f"EXECUTE dc_stmt_{index};",
            f"DEALLOCATE PREPARE dc_stmt_{index};",
        ]
    assignments = ", ".join(f"{column}={values[column]:.2f}" for column in ELITE_SCALES)
    lines.append(f"UPDATE dc_loot_tuning SET {assignments} WHERE source='elite';")
    return "\n".join(lines) + "\n", values


def champion_pack():
    """How many champions a champion pack holds, from loot_tuning.csv.

    decisions.md 2026-09-07: 3 identical champions in total, itself plus two.
    Its own migration rather than a column bolted onto rifts_0008, which has
    already shipped and describes scale only.
    """
    with (TUNABLES / "loot_tuning.csv").open(encoding="utf-8-sig") as handle:
        rows = {row["source"]: row for row in csv.DictReader(handle)}
    if "elite" not in rows or "champion_pack_size" not in rows["elite"]:
        raise SystemExit("loot_tuning.csv has no champion_pack_size column on the elite row")
    size = int(rows["elite"]["champion_pack_size"])
    # One champion is the promoted spawn itself, so a pack of 1 is a lone
    # champion and anything above 6 is a typo, not a tuning choice.
    if not 1 <= size <= 6:
        raise SystemExit(f"champion_pack_size is {size}; expected 1-6")
    lines = [
        # The generated header below still says data/d3 on purpose: these deltas
        # have been applied, and an applied delta must stay byte-identical.
        "-- Generated from data/d3/loot_tuning.csv by generate_rift_affixes.py;",
        "-- edit the CSV and rerun. Apply to the world database.",
        "-- 03-difficulty section 5 / decisions.md 2026-09-07: how many champions a",
        "-- champion pack holds in total, the promoted spawn included. The designer's tunable.",
        "SET NAMES utf8mb4;",
        "SET @dc_has_pack=(SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' "
        "AND column_name='champion_pack_size');",
        "SET @dc_ddl_pack=IF(@dc_has_pack=0,"
        "'ALTER TABLE dc_loot_tuning ADD COLUMN champion_pack_size INT NULL','DO 0');",
        "PREPARE dc_stmt_pack FROM @dc_ddl_pack;",
        "EXECUTE dc_stmt_pack;",
        "DEALLOCATE PREPARE dc_stmt_pack;",
        f"UPDATE dc_loot_tuning SET champion_pack_size={size} WHERE source='elite';",
    ]
    return "\n".join(lines) + "\n", size


def main():
    shells = shell_ids()
    affix_rows = affixes(shells)
    guardian_rows = guardians(shells)

    lines = [
        "-- Generated from data/d3/elite_affixes.csv by generate_rift_affixes.py;",
        "-- edit the CSV and rerun. Apply to the world database.",
        "-- 09-rifts section 2 step 2: the elite affix pool for rift packs.",
        "-- behaviour is empty for the affixes that are name-only in stage 1.",
        "SET NAMES utf8mb4;",
        "DROP TABLE IF EXISTS `dc_rift_affix`;",
        "CREATE TABLE `dc_rift_affix` (",
        "  `affix_name` VARCHAR(64) NOT NULL,",
        "  `appears_on` VARCHAR(16) NOT NULL COMMENT 'both | champion | rare',",
        "  `min_tier` INT NOT NULL COMMENT 'From min_difficulty; 1=Normal, 5=Torment I',",
        "  `min_hero_level` INT NOT NULL COMMENT 'From min_difficulty',",
        "  `element` VARCHAR(16) NOT NULL COMMENT 'damage_type mapped by 01-stats S9',",
        "  `behaviour` VARCHAR(16) NOT NULL COMMENT 'Empty when the affix is name-only',",
        "  `shell_spell` INT NOT NULL COMMENT '0 when name-only',",
        "  `pool` VARCHAR(16) NOT NULL COMMENT 'offensive | defensive | crowd_control (13 S4.2)',",
        "  `level_60_limited` TINYINT NOT NULL COMMENT 'One of the eleven a level 60+ pack may take at most three of',",
        "  `rollable` TINYINT NOT NULL COMMENT '0 keeps the affix out of the roll pool',",
        "  `minion_inherits` TINYINT NOT NULL COMMENT 'elite_affix_eligibility.csv minion column; 0 is leader-only',",
        "  `effect` LONGTEXT NOT NULL,",
        "  PRIMARY KEY (`affix_name`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "INSERT INTO `dc_rift_affix` (`affix_name`, `appears_on`, `min_tier`, `min_hero_level`, "
        "`element`, `behaviour`, `shell_spell`, `pool`, `level_60_limited`, `rollable`, "
        "`minion_inherits`, `effect`) VALUES",
    ]
    lines.append(",\n".join(
        "({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
            quote(name), quote(appears), tier, level, quote(element), quote(behaviour), shell,
            quote(pool), limited, rollable, minion, quote(effect))
        for name, appears, tier, level, element, behaviour, shell, pool, limited, rollable,
        minion, effect in affix_rows) + ";")
    affix_sql = "\n".join(lines) + "\n"

    lines = [
        "-- Generated from data/d3/rift_guardian_models.csv by generate_rift_affixes.py;",
        "-- edit the CSV and rerun. Apply to the world database.",
        "-- 09-rifts F5 / section 4: the three stage-1 guardians and the two mapped",
        "-- abilities each, as shell ids the module casts in place of the stock AI.",
        "SET NAMES utf8mb4;",
        "DROP TABLE IF EXISTS `dc_rift_guardian`;",
        "CREATE TABLE `dc_rift_guardian` (",
        "  `guardian` VARCHAR(64) NOT NULL,",
        "  `creature_id` INT NOT NULL COMMENT 'wow_creature_id from the CSV',",
        "  `display_id` INT NOT NULL,",
        "  `ability_1` VARCHAR(64) NOT NULL,",
        "  `ability_1_shell` INT NOT NULL,",
        "  `ability_1_wow_spell` INT NOT NULL COMMENT 'The spell the shell clones',",
        "  `ability_1_behaviour` VARCHAR(16) NOT NULL COMMENT 'nova | leap | frenzy',",
        "  `ability_2` VARCHAR(64) NOT NULL,",
        "  `ability_2_shell` INT NOT NULL,",
        "  `ability_2_wow_spell` INT NOT NULL,",
        "  `ability_2_behaviour` VARCHAR(16) NOT NULL,",
        "  PRIMARY KEY (`guardian`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "INSERT INTO `dc_rift_guardian` (`guardian`, `creature_id`, `display_id`, `ability_1`, "
        "`ability_1_shell`, `ability_1_wow_spell`, `ability_1_behaviour`, `ability_2`, "
        "`ability_2_shell`, `ability_2_wow_spell`, `ability_2_behaviour`) VALUES",
    ]
    lines.append(",\n".join(
        "({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
            quote(name), creature, display,
            quote(first[0]), first[1], first[2], quote(first[3]),
            quote(second[0]), second[1], second[2], quote(second[3]))
        for name, creature, display, first, second in guardian_rows) + ";")
    guardian_sql = "\n".join(lines) + "\n"

    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "rift_affixes.sql").write_bytes(affix_sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0003_elite_affixes.sql", affix_sql)
    (GENERATED / "rift_guardians.sql").write_bytes(guardian_sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0004_guardians.sql", guardian_sql)
    scale_sql, scales = elite_scales()
    (GENERATED / "rift_elite_scale.sql").write_bytes(scale_sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0008_elite_scale.sql", scale_sql)
    pack_sql, pack_size = champion_pack()
    (GENERATED / "rift_champion_pack.sql").write_bytes(pack_sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / "rifts_0009_champion_pack.sql", pack_sql)
    print(f"champion pack size: {pack_size} champions in total")

    implemented = sum(1 for row in affix_rows if row[5])
    print(f"dc_rift_affix: {len(affix_rows)} affixes ({implemented} with a behaviour, "
          f"{len(affix_rows) - implemented} name-only)")
    print(f"dc_rift_guardian: {len(guardian_rows)} guardians, "
          f"{2 * len(guardian_rows)} ability shells")
    print("dc_loot_tuning elite scale: champion x{elite_scale_champion}, rare x{elite_scale_rare}, "
          "minion x{elite_scale_minion}".format(**scales))
    for path in ("rifts_0003_elite_affixes.sql", "rifts_0004_guardians.sql",
                 "rifts_0008_elite_scale.sql", "rifts_0009_champion_pack.sql"):
        print(f"  handled {(UPDATES / path).relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
