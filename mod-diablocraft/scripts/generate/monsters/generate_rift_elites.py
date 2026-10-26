#!/usr/bin/env python3
"""Generate the champion and rare creature_template clones rift packs promote to.

09-rifts section 2 step 2 promotes native rift spawns to champion or rare packs.
On 3.3.5a a creature's name and rank travel in SMSG_CREATURE_QUERY_RESPONSE,
keyed by entry, so neither can be changed for one spawn
(docs/research/engine-facts.md Q3). The native way to get a named, ranked
individual is a cloned creature_template row, which is what this writes: for
every promotable creature spawned in the stage 1 rift pool, a "Champion <name>"
clone at rank 1 and a "Rare <name>" clone at rank 2, plus their
creature_template_model rows so the clone keeps the original's model and scale.

The module swaps a native spawn for its clone when promotion rolls; nothing here
spawns anything by itself.

Reads the world database (read-only) the same way generate_hub.py does, because
creature_template is the source, not a CSV. Makes no database changes.

Run from the repo root with the world DB up:

    python mod-diablocraft/scripts/generate/monsters/generate_rift_elites.py \
        --mysql "C:/Program Files/MySQL/MySQL Server 8.4/bin/mysql.exe" \
        --defaults-file azerothcore-wotlk/build/mysql/root-client.ini

This script does not touch generate_sql.py or the dc_ tables it produces.
"""

import argparse
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_coupled_outputs, write_migration
from generate_area_copies import Database, insert
from generate_monster_models import FAMILY_ENTRY_BASE

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 127, 8000000, 9000000, 8, 10, 11, 35, 31, 7, 12, 113-116): clone id bases and the creature type/faction exclusions for promotion; Identifiers and engine enums.

MODULE_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = MODULE_ROOT.parent
GENERATED = MODULE_ROOT / "data/generated"
UPDATES = MODULE_ROOT / "data/sql/db-world/updates"

# Nothing in creature_template is anywhere near these, so a clone entry can
# never collide with a stock one. Checked against MAX(entry) before writing.
CHAMPION_BASE = 8000000
RARE_BASE = 9000000
# The clones are CHAMPION_BASE/RARE_BASE plus a stock creature's entry, and the family monsters (generate_monster_models.py)
# start at FAMILY_ENTRY_BASE with their own clones above the same two bases. So this generator owns the clone entries
# BELOW the family range, and its DELETEs stop there; `>= CHAMPION_BASE` wiped the family clones at 8950001+ and 9950001+
# (diablocraft-mapz). main() refuses a native at or above the family range.
NATIVE_LIMIT = FAMILY_ENTRY_BASE

# Which native spawns may be promoted. Critters, totems and the "not specified"
# type (triggers and props) are never monsters; bosses and rare elites are
# already special; a friendly or neutral faction is a quest giver or a guard,
# not a rift monster; NOT_SELECTABLE is a trigger.
#
# The last two clauses are lessons L3 and L18, counted against this world DB in
# docs/research/elite-pool-audit.md (2026-09-14): a vehicle or chair is ridden,
# not fought, and a template whose only model is display 0, has no
# creature_model_info row, or has a zero bounding radius or combat reach is
# invisible or unhittable once promoted. 48 of 573 entries go, leaving 525.
PROMOTABLE = """
    t.rank IN (0, 1)
    AND t.type NOT IN (8, 10, 11)
    AND t.faction NOT IN (35, 31, 7, 12, 113, 114, 115, 116)
    AND t.npcflag = 0
    AND (t.unit_flags & 0x100) = 0
    AND t.VehicleId = 0
    AND NOT EXISTS (
        SELECT 1
        FROM creature_template_model ctm
        LEFT JOIN creature_model_info cmi ON cmi.DisplayID = ctm.CreatureDisplayID
        WHERE ctm.CreatureID = t.entry
          AND (ctm.CreatureDisplayID = 0 OR cmi.DisplayID IS NULL
               OR cmi.BoundingRadius <= 0 OR cmi.CombatReach <= 0))
"""

# creature_template columns the clone must not inherit: a stock dungeon script
# would run the original encounter, and a difficulty entry would redirect the
# clone back to a heroic version of the original.
CLEARED = {"ScriptName": "", "AIName": "", "difficulty_entry_1": 0,
           "difficulty_entry_2": 0, "difficulty_entry_3": 0}


def clones(db):
    maps = "(SELECT DISTINCT map_id FROM dc_rift_dungeon)"
    where = (f"s.entry IN (SELECT DISTINCT c.id FROM creature c JOIN {maps} d ON d.map_id = c.map) "
             f"AND EXISTS (SELECT 1 FROM creature_template t WHERE t.entry = s.entry AND {PROMOTABLE})")
    rows = db.rows("creature_template", where, "ORDER BY s.entry")
    if not rows:
        raise SystemExit("No promotable creatures found; is dc_rift_dungeon applied?")
    # Stock rows only: once rifts_0006 has been applied the table holds this
    # script's own clones, and a plain MAX(entry) would read them back and
    # refuse every rerun. The guard is about a stock entry reaching the bases.
    highest = int(db.query(f"SELECT MAX(entry) FROM creature_template WHERE entry < {CHAMPION_BASE}")[0])
    if highest >= CHAMPION_BASE:
        raise SystemExit(f"creature_template already reaches {highest}; the clone bases collide")

    models = {}
    for row in db.rows("creature_template_model",
                       f"s.CreatureID IN (SELECT entry FROM creature_template ct WHERE {where.replace('s.entry', 'ct.entry')})",
                       "ORDER BY s.CreatureID, s.Idx"):
        models.setdefault(int(row["CreatureID"]), []).append(row)

    out = []
    for row in rows:
        entry = int(row["entry"])
        for base, rank, prefix in ((CHAMPION_BASE, 1, "Champion"), (RARE_BASE, 2, "Rare")):
            clone = dict(row)
            clone.update(CLEARED)
            clone["entry"] = base + entry
            clone["rank"] = rank
            # 100 chars is the column width; the prefix is what identifies the
            # pack, so the original name is what gets trimmed if it must.
            clone["name"] = (prefix + " " + str(row["name"]))[:100]
            out.append((clone, [dict(model, CreatureID=base + entry)
                                for model in models.get(entry, [])]))
    return out


def native_of(entry):
    """The stock creature a clone entry was made from."""
    return entry - (RARE_BASE if entry >= RARE_BASE else CHAMPION_BASE)


def render(built):
    """The migration text for `built` (clones() output); refuses a native at or above the family range."""
    too_high = [clone["entry"] for clone, _ in built if native_of(clone["entry"]) >= NATIVE_LIMIT]
    if too_high:
        raise SystemExit(f"a promotable native is at or above the family range {NATIVE_LIMIT}: {too_high[:5]}")
    lines = [
        "-- Generated by mod-diablocraft/scripts/generate_rift_elites.py from the",
        "-- world database; rerun it rather than hand-editing. Apply to the world DB.",
        "-- 09-rifts section 2 step 2: champion (rank 1) and rare (rank 2) clones of",
        "-- every promotable creature spawned in the stage 1 rift pool. A 3.3.5a client",
        "-- reads a creature's name and rank per entry, not per spawn, so a promoted",
        "-- pack has to be a different entry (docs/research/engine-facts.md Q3).",
        "SET NAMES utf8mb4;",
    ]
    # Only this generator's own bands: the champion and rare clones of stock entries below NATIVE_LIMIT.
    for first in (CHAMPION_BASE, RARE_BASE):
        last = first + NATIVE_LIMIT - 1
        lines.append(f"DELETE FROM `creature_template_model` WHERE `CreatureID` BETWEEN {first} AND {last};")
        lines.append(f"DELETE FROM `creature_template` WHERE `entry` BETWEEN {first} AND {last};")
    for clone, models in built:
        lines.append(insert("creature_template", clone))
        for model in models:
            lines.append(insert("creature_template_model", model))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysql", required=True)
    parser.add_argument("--defaults-file", required=True)
    parser.add_argument("--database", default="acore_world")
    args = parser.parse_args()

    built = clones(Database(args.mysql, args.defaults_file, args.database))
    sql = render(built)

    GENERATED.mkdir(parents=True, exist_ok=True)
    target = UPDATES / "rifts_0006_elite_clones.sql"
    # rifts_0006 is applied and frozen, so a narrowed render is held back (with a warning) until it ships as a new migration; the
    # mirror follows the migration, never the other way round.
    write_migration(MODULE_ROOT, target, sql)
    write_coupled_outputs(MODULE_ROOT, target, sql, [(GENERATED / "rift_elites.sql", sql)], label="rift elite clones")
    natives = len(built) // 2
    print(f"creature_template: {len(built)} clones of {natives} promotable rift creatures "
          f"({natives} champion, {natives} rare)")
    print(f"  handled {target.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
