"""Legendary 051, bead diablocraft-lm3ka: Storm Crow (Wizard hat), and the piece it builds, N-WPROC.

  "[20-40]% chance to cast a fiery ball when attacking."
  * the words and the [20-40] are d3planner's (item_head.js, leg_stormcrow) and the catalogue's. The item's number is the CHANCE, rolled
    once per item. No source gives the ball's damage (the Power file list has no Storm Crow, docs/research/legendary-pow-data.csv): it is
    the combat tunable storm_crow_fireball_damage_pct, the value the designer's 150 (card q-1016-20; a blank would read 0: the
    ball is not cast until he sets it);
  * N-WPROC: an item proc that deals a percentage of weapon damage as an element at the enemy a hit struck, without a skill. The table
    holds ONE `effect` row, `proc_damage` [20-40] on `hit` with no fire_skills (every hit of every skill); the generator refuses a bad one;
    the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the ball's damage is dealt under the hit record 83560 'Fiery Ball' (data/legendary_power_buffs.csv `hit`, element fire,
    generate_spells.py), in the spell header, the shell manifest and the combat migration;
  * the production rules (dc_item_power_math.h Fire; dc_item_proc_math.h Pct) are compiled and driven with the generated rows; mutants fail
    the same driver;
  * source-text guards hold the executor (outside the lock, the item's rolled chance and the hit's coefficient), the proc file (the
    tunable by name, ComputeHit/DealHit, never Strike so the ball cannot proc itself) and the shell load in dc_combat.cpp; mutants fail
    them. The C++ is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-lm3ka.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402
import generate_tunables

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
PROC = SRC / "combat/dc_proc_math.h"
HARNESS = MODULE / "tests/item_power_storm_crow/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
# The newest full spell render (combat_0083 brought the record; a later full render carries it on).
SPELL_MIGRATION = sorted((p for p in (MODULE / "data/sql/db-world/updates").glob("combat_*.sql")
                          if "DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 81000 AND" in p.read_text(encoding="utf-8")))[-1]
OWNER = "Unique_WizardHat_004_x1"
RECORD = 83560
TUNABLE = "storm_crow_fireball_damage_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
WANT_ROW = (OWNER, 0, "effect", "", "proc_damage", 20.0, 40.0, "", 0.0, "", 0.0, 0, "hit", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv_path(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def read_csv(name):
    return read_csv_path(MODULE / name)


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


def source(name):
    """A server file's text; empty when it does not exist yet (a branch without the proc file reads red, not a crash)."""
    path = SRC / "combat" / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class Table(unittest.TestCase):
    def test_the_words_are_the_planners_and_the_item_is_a_pool_legendary(self):
        text = (REPO / "reference/d3planner/item_head.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n", text.index("preset", start))]
        self.assertIn('id: "leg_stormcrow"', item)
        self.assertIn('format: "%d%% chance to cast a fiery ball when attacking.", min: 20, max: 40', item)
        row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("[20-40]% chance to cast a fiery ball when attacking.", "K3", "wizard"), (row["power_text"], row["kind"], row["class"]))
        base = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Storm Crow", "legendary", "yes"), (base["d3_name"], base["rarity"], base["pool_version"]))

    def test_the_ball_has_no_source_so_its_damage_is_alexs_number(self):
        pow_data = (REPO / "docs/research/legendary-pow-data.csv").read_text(encoding="utf-8")
        self.assertNotIn("Storm Crow", pow_data)
        sheet = {r["name"]: r for r in read_csv("data/tunables/combat.csv")}
        row = sheet[TUNABLE]
        self.assertEqual(("", "150", "percent"), (row["d3_value"], row["value"], row["unit"]))   # card q-1016-20
        self.assertIn("q-1016-20", row["notes"])
        self.assertIn("Storm Crow", row["notes"])
        migration = (MODULE / "data/sql/db-world/updates" / generate_tunables.CURRENT_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("('combat', '%s', NULL, 150.0, 'percent', " % TUNABLE, migration)

    def test_one_effect_row_on_every_hit_rolled_per_item(self):
        self.assertEqual([WANT_ROW], mine())

    def test_the_row_carries_no_chance_and_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertEqual(("", "", ""), (rows[0]["chance_pct"], rows[0]["icd_seconds"], rows[0]["fire_skills"]))
        for need in ("item_head.js", "leg_stormcrow", "combat.csv", "diablocraft-lm3ka"):
            self.assertIn(need, rows[0]["source"])
        self.assertTrue(rows[0]["note"])

    def test_the_hit_record(self):
        record = next(r for r in read_csv("data/legendary_power_buffs.csv") if r["owner"] == OWNER)
        self.assertEqual((str(RECORD), "proc_damage", "hit", "Fiery Ball", "", "fire"),
                         (record["spell_id"], record["stat"], record["aura"], record["name"], record["text"], record["element"]))
        # every other record keeps the physical school it always had (Fire Walkers' burning ground is the other fire record)
        self.assertEqual({""}, {r["element"] for r in read_csv("data/legendary_power_buffs.csv") if r["owner"] not in (OWNER, "Unique_Boots_007_p2")})
        self.assertIn('{%d, "%s", "proc_damage"},' % (RECORD, OWNER), (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        self.assertIn("%d,Fiery Ball,fire," % RECORD, (MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8"))
        sql = SPELL_MIGRATION.read_text(encoding="utf-8")
        self.assertEqual(sql, (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"))
        self.assertRegex(sql, r"\(%d,0,0,0,\d+," % RECORD)
        found = sorted(p.name for p in (MODULE / "data/sql/db-world/updates").glob("combat_*.sql"))
        self.assertEqual(SPELL_MIGRATION.name, found[-1])

    def test_the_generator_refuses_a_bad_row(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        refused = {
            "another event": dict(base, fire_on="kill"),
            "a cast": dict(base, fire_on="cast", fire_skills="Magic Missile"),
            "only some skills": dict(base, fire_skills="Magic Missile"),
            "a chance of its own in the row": dict(base, chance_pct="50"),
            "an internal cooldown in the row": dict(base, icd_seconds="3"),
            "a chance of nothing": dict(base, value_min="0", value_max="0"),
            "a chance over 100": dict(base, value_min="90", value_max="101"),
            "a skill": dict(base, skill="Magic Missile"),
            "a condition": dict(base, cond="triggered", cond_arg="3"),
            "a set level": dict(base, pieces="2"),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        with self.subTest("no hit record"), self.assertRaises(ValueError):
            self.rows_of([base], buffs=False)
        self.assertEqual(1, len(self.rows_of([base])))

    @staticmethod
    def rows_of(sheet_rows, buffs=True):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            records = read_csv("data/legendary_power_buffs.csv")
            with (module / "data/legendary_power_buffs.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(records[0]))
                writer.writeheader()
                writer.writerows(r for r in records if buffs or r["owner"] != OWNER)
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, headers, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/" + file: text for file, text in headers.items()}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemstormcrow-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def headers(**changed):
        out = {"dc_item_power_math.h": MATH.read_text(encoding="utf-8"), "dc_item_proc_math.h": source("dc_item_proc_math.h"),
               "dc_proc_math.h": PROC.read_text(encoding="utf-8")}
        out.update({k.replace("__", "."): v for k, v in changed.items()})
        return out

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # the row fires on a hit of any skill, only with the item worn; the executor rolls the chance, so Fire never does
        out += clear + [(T("now", 1000), None), (T("fire", "hit", "Magic Missile", 1, 0), "")]                      # not worn
        out += clear + [(T("now", 1000), None), (T("wears", "Unique_Gloves_003_x1", 0), None), (T("fire", "hit", "Magic Missile", 1, 0), "")]
        out += clear + [(T("now", 1000), None), (T("wears", OWNER, 0), None), (T("fire", "hit", "Magic Missile", 1, 0), "")]   # worn, no roll stored
        out += clear + [(T("now", 1000), None), (T("wears", OWNER, 0), None), (T("rolled", OWNER, "", "proc_damage", 33), None)]
        for skill in ("Magic Missile", "Meteor", "Arcane Orb", "Frost Nova", "Energy Twister", ""):
            for scale, draw in ((1, 0), (0.13, 99.99), (0, 50)):
                out += [(T("fire", "hit", skill, scale, draw), "proc_damage=33;")]    # the item's stored roll
        out += [(T("now", 1001), None), (T("fire", "hit", "Magic Missile", 1, 0), "proc_damage=33;")]         # every hit, no cooldown in the row
        for event in ("cast", "kill", "kill_elite", "taken", "hit_spender", "hit_generator", "image_death", "life_below", "resource_spent", ""):
            out += [(T("fire", event, "Magic Missile", 1, 0), "")]
        # the ball: the item's chance (percent) times the hit's coefficient falls when the draw is under it, and only with a damage set
        out += [(T("pct", 30, 1, 400, 29.99), "400"), (T("pct", 30, 1, 400, 30), "0"),
                (T("pct", 20, 1, 400, 19.99), "400"), (T("pct", 40, 1, 400, 39.99), "400"), (T("pct", 40, 1, 400, 40), "0"),
                (T("pct", 30, 0.5, 400, 14.99), "400"), (T("pct", 30, 0.5, 400, 15), "0"),     # the hit's proc coefficient scales it
                (T("pct", 30, 0, 400, -1), "0"), (T("pct", 30, -1, 400, -1), "0"),            # a hit that states none never procs
                (T("pct", 0, 1, 400, -1), "0"), (T("pct", -5, 1, 400, -1), "0"),               # no chance
                (T("pct", 30, 1, 0, 0), "0"), (T("pct", 30, 1, -50, 0), "0"),                  # a blank damage tunable reads 0: no ball
                (T("pct", 30, 0.13, 250, 3.89), "250"), (T("pct", 30, 0.13, 250, 3.91), "0"),
                (T("pct", 100, 1, 125.5, 99.99), "125.5")]
        return out

    def drive(self, headers, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(headers, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item(self):
        want, got = self.drive(self.headers(), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_wrong_event": [r[:12] + ("kill",) + r[13:] for r in rows],
            "only_one_skill": [r[:13] + ("Meteor",) + r[14:] for r in rows],
            "the_wrong_effect": [r[:4] + ("resource_refund",) + r[5:] for r in rows],
            "a_chance_in_the_row": [r[:14] + (50.0,) + r[15:] for r in rows],
            "a_cooldown_in_the_row": [r[:15] + (3.0,) + r[16:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(), mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        proc = source("dc_item_proc_math.h")
        power = MATH.read_text(encoding="utf-8")
        header_mutants = {
            "the_coefficient_ignored": dict(dc_item_proc_math__h=mutate(proc, "Proc::Rolls(coefficient, chancePct, roll)", "Proc::Rolls(1.0, chancePct, roll)")),
            "no_roll": dict(dc_item_proc_math__h=mutate(proc, "Proc::Rolls(coefficient, chancePct, roll)", "(chancePct > 0 && coefficient > 0)")),
            "the_roll_inverted": dict(dc_item_proc_math__h=mutate(proc, "Proc::Rolls(coefficient, chancePct, roll)", "!Proc::Rolls(coefficient, chancePct, roll)")),
            "a_blank_damage_still_casts": dict(dc_item_proc_math__h=mutate(proc, "damagePct > 0 && ", "")),
            "the_damage_ignored": dict(dc_item_proc_math__h=mutate(proc, "? damagePct : 0.0", "? 100.0 : 0.0")),
            "no_fire_skills_fires_nothing": dict(dc_item_power_math__h=mutate(power, "if (!row.fireSkills.empty() && std::find(", "if (std::find(")),
            "the_event_ignored": dict(dc_item_power_math__h=mutate(power, "if (row.fireOn != fireOn || !Owned(row, counts, situation, number))", "if (!Owned(row, counts, situation, number))")),
        }
        for name, changed in header_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(**changed), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
