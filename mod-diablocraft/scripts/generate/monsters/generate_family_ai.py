#!/usr/bin/env python3
"""Monster families Part 3 (diablocraft-l5ge): the data the family AI runs on.

Part 1's `dc_family_ability` holds each ability's kind, trigger text, timers, range, donor spell and tunable key. This
adds `dc_family_ability_ai`, one row per ability (same entry and seq) with what the AI needs beyond that:

  trigger_code   the trigger text as a code the AI evaluates (TRIGGERS below);
  kind           the kind it runs as (monster_ability_ai.csv can change one, e.g. a spawn-on-death that Part 1 read as a bomb);
  summon_entry   the family monster a summon brings (monster_ability_ai.csv `summon_monster`);
  count          how many (monster_ability_ai.csv), else the kind's default tunable;
  built          0 for an ability the AI does not run yet, with `held_reason`.

An ability is held back when its kind is not built (shields, heals, teleports and burrows are Part 8; the passives are
behaviours, not abilities), its trigger needs state nobody tracks yet, it has a `held` reason in monster_ability_ai.csv,
a summon has no monster to bring, or a kind that casts has no donor spell. A roster monster with any held ability stays
out of the spawn table (monster-families.md 3.10); `--held` prints them and the test pins the list.

Numbers are not here: the cooldown, range and wind-up come from Part 1's cells, then the ability's blank tunable row,
then the kind's default (`monsters.csv` `ability_default_<kind>_<param>`, PLACEHOLDER rows), read by the AI.

Makes no database read; run from the repo root:

    python mod-diablocraft/scripts/generate/monsters/generate_family_ai.py [--held]
"""

import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_monster_models as models
from applied_migrations import write_migration
from generate_area_copies import insert

MODULE_ROOT = models.MODULE_ROOT
GENERATED = models.GENERATED
UPDATES = models.UPDATES
AI_CSV = MODULE_ROOT / "data/tunables/monster_ability_ai.csv"
MIGRATION = "monsters_0005_family_ai.sql"

# Constants of the AI, not game numbers. The kinds the AI builds in Part 3 (monster-families.md section 5: melee, heavy
# slams, bolts, volleys, beams, breaths, ground pools and detonations, charges, leaps, summons, suicide bombs, buffs and
# traps); the rest wait for Part 8 or are guardians'.
BUILT_KINDS = ("melee_swing melee_heavy_slam ranged_bolt projectile_volley channeled_beam cone_breath ground_hazard_dot "
               "ground_detonation charge_rush leap_slam summon_minions suicide_bomb buff_roar crowd_control_trap").split()
# The kinds that cast a stock donor spell (Part 1's wow_spell cell) to be built; the swing, the charge, the leap and the
# summon move or spawn and need none.
NEEDS_DONOR = {"melee_heavy_slam", "ranged_bolt", "projectile_volley", "channeled_beam", "cone_breath",
               "ground_hazard_dot", "ground_detonation", "suicide_bomb", "buff_roar", "crowd_control_trap"}

# The trigger text of Part 1's table -> the code the AI evaluates. A text that is not listed stops the generator, so a
# new trigger gets a decision rather than a silent default.
#   melee      the victim is within the ability's range (its reach)
#   range      a target is within [min, max] yards and in line of sight
#   gap        like range, for an ability that closes the distance (a charge or a leap)
#   proximity  a player is within the ability's radius
#   death      the monster dies (a fatal hit counts)
#   combat     the monster is in combat; the cooldown paces it
#   hit        after one of its swings lands
#   none       needs state the AI does not track yet: the ability is held back
TRIGGERS = {
    "In melee range": "melee", "In close combat": "melee",
    "Target at range": "range", "Target at distance": "range", "Target distant": "range",
    "Target in line of sight": "range", "Target in frontal arc": "range", "Target in front": "range",
    "Target in close range": "range",
    "Target outside melee": "gap",
    "Target in proximity": "proximity", "Player in proximity": "proximity",
    "On death": "death", "On fatal hit": "death", "Legs severed": "death",
    "Combat default": "combat", "Combat engagement": "combat", "Spawning / entering combat": "combat",
    "Allies in combat": "combat", "Under attack": "combat",
    "On melee hit": "hit", "On heavy fist hit": "hit",
}
NONE_TRIGGERS = {
    "Constant passive", "not found", "Repositioning", "Out of combat / disengaging", "Emerging near target",
    "Beneath target", "Frontal attack", "Enemies close into melee", "Enemy closes into melee", "On ally death",
    "Fleeing allies present", "Fallen corpse in range", "Injured with corpse nearby", "In ritual group",
    "Egg sac disturbed", "In melee range / low HP",
}


def trigger_code(text, where):
    if text in TRIGGERS:
        return TRIGGERS[text]
    if text in NONE_TRIGGERS:
        return "none"
    raise SystemExit(f"{where}: trigger {text!r} has no code; add it to TRIGGERS or NONE_TRIGGERS in generate_family_ai.py")


def overrides(abilities, roster_names):
    """{(monster, ability): row} of monster_ability_ai.csv, each checked against the ability table and the roster."""
    known = {(row["monster"], row["ability"]) for row in abilities}
    out = {}
    for line, row in enumerate(models.read_csv(AI_CSV), 2):
        where = f"{AI_CSV.name} line {line} ({row['monster']}: {row['ability']})"
        key = (row["monster"], row["ability"])
        if key not in known:
            raise SystemExit(f"{where}: not a row of monster_abilities.csv")
        if key in out:
            raise SystemExit(f"{where}: a second override for the same ability")
        if row["kind"] and row["kind"] not in models.KINDS:
            raise SystemExit(f"{where}: kind {row['kind']!r} is none of the 20")
        if row["summon_monster"] and row["summon_monster"] not in roster_names:
            raise SystemExit(f"{where}: summon_monster {row['summon_monster']!r} is not a roster monster")
        if row["count"] and not row["count"].isdigit():
            raise SystemExit(f"{where}: count {row['count']!r} is not a whole number")
        if not row["source"].strip():
            raise SystemExit(f"{where}: no source text")
        out[key] = row
    return out


def ability_ai_rows():
    ids = models.entries()
    abilities = models.read_csv(models.ABILITIES)
    changes = overrides(abilities, set(ids))
    unused = set(changes)
    seen = {}
    rows = []
    for line, row in enumerate(abilities, 2):
        where = f"monster_abilities.csv line {line} ({row['monster']}: {row['ability']})"
        key = (row["monster"], row["ability"])
        change = changes.get(key, {})
        unused.discard(key)
        entry = ids[row["monster"]]
        seen[entry] = seen.get(entry, 0) + 1
        kind = change.get("kind") or row["kind"]
        trigger = trigger_code(row["trigger"], where)
        if kind == "melee_swing" and trigger != "hit":
            trigger = "melee"                  # the plain swing, whatever the sheet says about when it lands
        summon = ids[change["summon_monster"]] if change.get("summon_monster") else 0
        held = ""
        if kind not in BUILT_KINDS:
            held = f"kind {kind} is not built"
        elif change.get("held"):
            held = change["held"]
        elif trigger == "none":
            held = f"trigger {row['trigger']!r} needs state the AI does not track yet"
        elif kind == "summon_minions" and not summon:
            held = "no monster to bring"
        elif kind in NEEDS_DONOR and not row["wow_spell"]:
            held = "no donor spell"
        rows.append({"entry": entry, "seq": seen[entry], "kind": kind, "trigger_code": trigger,
                     "summon_entry": summon, "count": int(change["count"]) if change.get("count") else None,
                     "built": 0 if held else 1, "held_reason": held or None})
    if unused:
        raise SystemExit(f"unused overrides: {sorted(unused)}")
    return rows


def held_monsters(rows):
    """{monster name: [held reasons]}: roster monsters the spawn table must leave out until the rest is built."""
    names = {entry: name for name, entry in models.entries().items()}
    out = {}
    for row in rows:
        if not row["built"]:
            out.setdefault(names[row["entry"]], []).append(row["held_reason"])
    return out


def render():
    rows = ability_ai_rows()
    lines = [
        "-- Generated by mod-diablocraft/scripts/generate_family_ai.py from data/tunables/monster_abilities.csv and",
        "-- monster_ability_ai.csv; rerun it rather than hand-editing. Apply to the world DB.",
        "-- monster-families.md Part 3: what the family AI runs on, one row per dc_family_ability row.",
        "SET NAMES utf8mb4;",
        "CREATE TABLE IF NOT EXISTS `dc_family_ability_ai` (",
        "  `entry` INT UNSIGNED NOT NULL, `seq` TINYINT UNSIGNED NOT NULL, `kind` VARCHAR(32) NOT NULL,",
        "  `trigger_code` VARCHAR(16) NOT NULL, `summon_entry` INT UNSIGNED NOT NULL DEFAULT 0,",
        "  `count` TINYINT UNSIGNED NULL, `built` TINYINT UNSIGNED NOT NULL, `held_reason` VARCHAR(160) NULL,",
        "  PRIMARY KEY (`entry`, `seq`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;",
        f"DELETE FROM `dc_family_ability_ai` WHERE `entry` BETWEEN {models.FAMILY_ENTRY_BASE + 1} AND "
        f"{models.FAMILY_ENTRY_BASE + models.FAMILY_ENTRY_SPAN - 1};",
    ]
    lines += [insert("dc_family_ability_ai", row) for row in rows]
    return "\n".join(lines) + "\n", rows


def main():
    sql, rows = render()
    GENERATED.mkdir(parents=True, exist_ok=True)
    (GENERATED / "family_ai.sql").write_bytes(sql.encode("utf-8"))
    write_migration(MODULE_ROOT, UPDATES / MIGRATION, sql)
    built = sum(row["built"] for row in rows)
    print(f"dc_family_ability_ai: {len(rows)} abilities, {built} built, {len(rows) - built} held")
    print(f"  handled {(UPDATES / MIGRATION).relative_to(models.REPO_ROOT)}")
    if "--held" in sys.argv:
        for name, reasons in sorted(held_monsters(rows).items()):
            print(f"  {name}: {'; '.join(sorted(set(reasons)))}")


if __name__ == "__main__":
    main()
