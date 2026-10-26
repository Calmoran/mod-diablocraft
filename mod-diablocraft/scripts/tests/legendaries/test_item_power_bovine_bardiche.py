"""Legendary 055, bead diablocraft-4p9j9: Bovine Bardiche (polearm, any class that wields one), N-SUMMON's first use.

  "Chance on hit to summon a herd of murderous cows."
  * the words are d3planner's (item_twohand.js, leg_bovinebardiche, args 0: no number) and the catalogue's; the Power file
    (ItemPassive_Unique_Ring_520_x1.pow, docs/research/legendary-pow-data.csv) gives the herd 4, the internal cooldown 60 s, the cows'
    15 s and their 4 (+2) x weapon damage, and those are the numbers here (the herd the row's, the rest the combat tunables
    bovine_bardiche_*, each with the Power file's number as its D3 value). The CHANCE is the tunable bovine_bardiche_chance_pct, both
    cells blank and the notes marked PLACEHOLDER for the designer (blank reads 0: the power does nothing until he sets it); the cows' Life is in
    no source, a blank PLACEHOLDER too (blank keeps the donor's);
  * the table holds ONE `effect` row, `summon_herd` 4 on `hit` with no fire_skills (every hit of every skill); the generator refuses a
    bad one; the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the cows' damage is dealt under the hit record 83554 'Cow' (data/legendary_power_buffs.csv `hit`, generate_spells.py), in the spell
    header, the shell manifest and the combat migration; the cow is World's 900120 (the stock Cow 2442, display 1060);
  * the production rules (dc_item_power_math.h Fire; dc_item_summon_math.h HerdComes, SwingPct) are compiled and driven with the
    generated rows; mutants fail the same driver;
  * source-text guards hold the executor (outside the lock, the hit's coefficient), the summon file (tunables by name, the cooldown
    stamped only when a herd comes, the cow entry, the lifetime, the swing registered and dealt through ComputeHit/DealHit) and the
    shell load in dc_combat.cpp; mutants fail them. The C++ is compile-checked by syntax_check.sh; the in-game steps are in
    docs/test-diablocraft-4p9j9.md.
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
from test_control_immunity_gap import insert_rows, newest_spell_render  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
PROC = SRC / "combat/dc_proc_math.h"
HARNESS = MODULE / "tests/item_power_bovine_bardiche/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SPELL_MIGRATION = newest_spell_render(MODULE / "data/sql/db-world/updates")   # the newest full spell render, carrying 0073's Cow on
BROUGHT_BY = MODULE / "data/sql/db-world/updates/combat_0073_bovine_bardiche_cow.sql"   # the migration that brought the record
OWNER = "Unique_Polearm_101_x1"
COW, RECORD = 900120, 83554
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
WANT_ROW = (OWNER, 0, "effect", "", "summon_herd", 4.0, 4.0, "", 0.0, "", 0.0, 0, "hit", "", 100.0, 0.0)
# The combat tunables: (name, the Power file's SF it carries (None: no source), that number as the sheet holds it, unit).
TUNABLES = (("bovine_bardiche_chance_pct", "SF_3 Proc Chance", "100", "percent"),
            ("bovine_bardiche_cooldown_seconds", "SF_1 Internal Cooldown", "60", "seconds"),
            ("bovine_bardiche_cow_seconds", "SF_2 Cow Duration", "15", "seconds"),
            ("bovine_bardiche_cow_damage_pct", "SF_4 Cow Weapon Damage %", "400", "percent"),
            ("bovine_bardiche_cow_damage_delta_pct", "SF_5 Cow Weapon Damage % Delta", "200", "percent"),
            ("bovine_bardiche_cow_life_pct_of_owner", None, "", "percent"))
RULING = "docs/decisions.md:1077"  # the 2026-10-14 line: the designer's card q-1014-13 (a)
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


def power_file():
    """{SF label: number} of the Power file the item links to."""
    row = next(r for r in read_csv_path(REPO / "docs/research/legendary-pow-data.csv") if r[next(iter(r))] == "Bovine Bardiche")
    text = next(v for v in row.values() if "SF_0" in v)
    return {m[1].strip(): m[2] for m in re.finditer(r"(SF_\d+ [^=;]+?)[ =]+([\d.]+)", text)}


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


class Table(unittest.TestCase):
    def test_the_words_are_the_planners_and_the_item_is_a_pool_legendary(self):
        text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n", text.index("preset", start))]
        self.assertIn('id: "leg_bovinebardiche"', item)
        self.assertIn('format: "Chance on hit to summon a herd of murderous cows.", args: 0', item)
        row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Chance on hit to summon a herd of murderous cows.", "K3", "any"), (row["power_text"], row["kind"], row["class"]))
        base = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Bovine Bardiche", "legendary", "yes"), (base["d3_name"], base["rarity"], base["pool_version"]))

    def test_the_power_file_numbers_are_the_tunables_d3_values(self):
        sf = power_file()
        self.assertEqual("4", sf["SF_0 Herd"])
        self.assertEqual("1", sf["SF_3 Proc Chance"])
        sheet = {r["name"]: r for r in read_csv("data/tunables/combat.csv")}
        for name, label, value, unit in TUNABLES:
            with self.subTest(name):
                self.assertIn(name, sheet)
                row = sheet[name]
                self.assertEqual((value, "", unit), (row["d3_value"], row["value"], row["unit"]))
                self.assertIn("diablocraft-4p9j9", row["notes"])
                if label:
                    scale = 100 if unit == "percent" else 1
                    self.assertEqual(float(value), float(sf[label]) * scale)
                    self.assertIn(label.split(" ")[0], row["notes"])
                else:
                    self.assertIn(RULING, row["notes"])

    def test_the_chance_follows_the_ruling_and_reaches_the_migration(self):
        notes = next(r for r in read_csv("data/tunables/combat.csv") if r["name"] == "bovine_bardiche_chance_pct")["notes"]
        self.assertIn("SF_3 Proc Chance = 1", notes)          # the Power file's number is named
        self.assertIn(RULING, notes)                          # and so is the ruling that sets it
        self.assertNotIn("PLACEHOLDER", notes)
        decisions = (REPO / "docs/decisions.md").read_text(encoding="utf-8").splitlines()
        self.assertTrue(any("q-1014-13 (a): Bovine Bardiche follows the power file, 100% on hit once per 60 s" in line
                            for line in decisions))
        migration = (MODULE / "data/sql/db-world/updates" / generate_tunables.CURRENT_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("('combat', 'bovine_bardiche_chance_pct', 100.0, NULL, 'percent', ", migration)
        self.assertIn("('combat', 'bovine_bardiche_cow_life_pct_of_owner', NULL, NULL, 'percent', ", migration)
        self.assertIn("('combat', 'bovine_bardiche_cooldown_seconds', 60.0, NULL, 'seconds', ", migration)

    def test_one_effect_row_on_every_hit(self):
        self.assertEqual([WANT_ROW], mine())
        self.assertEqual(float(power_file()["SF_0 Herd"]), WANT_ROW[5])

    def test_the_row_carries_no_chance_and_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertEqual(("", "", ""), (rows[0]["chance_pct"], rows[0]["icd_seconds"], rows[0]["fire_skills"]))
        for need in ("item_twohand.js", "leg_bovinebardiche", "ItemPassive_Unique_Ring_520_x1.pow", "combat.csv", "diablocraft-4p9j9"):
            self.assertIn(need, rows[0]["source"])
        self.assertTrue(rows[0]["note"])

    def test_the_cow_is_worlds_ally_of_the_stock_cow(self):
        summon = next(r for r in read_csv("data/legendary_summons.csv") if r["item"] == "Bovine Bardiche")
        self.assertEqual((str(COW), "Cow", "2442", "dc_legendary_ally"), (summon["entry"], summon["summon"], summon["donor_creature"], summon["script"]))
        core = (REPO / "azerothcore-wotlk/data/sql/base/db_world/creature_template_model.sql").read_text(encoding="utf-8", errors="replace")
        self.assertIn("(2442,0,1060,", core)

    def test_the_hit_record(self):
        record = next(r for r in read_csv("data/legendary_power_buffs.csv") if r["owner"] == OWNER)
        self.assertEqual((str(RECORD), "summon_herd", "hit", "Cow", ""), (record["spell_id"], record["stat"], record["aura"], record["name"], record["text"]))
        self.assertIn('{%d, "%s", "summon_herd"},' % (RECORD, OWNER), (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        self.assertIn("%d,Cow,physical," % RECORD, (MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8"))
        # the newest full render carries the record unchanged from the migration that brought it; the render's other records are not
        # this test's, so a later render of another record leaves it green
        sql = SPELL_MIGRATION.read_text(encoding="utf-8")
        self.assertRegex(sql, r"\(%d,0,0,0,\d+," % RECORD)
        brought = {int(r["ID"]): r for r in insert_rows(BROUGHT_BY.read_text(encoding="utf-8"), "spell_dbc")}
        rendered = {int(r["ID"]): r for r in insert_rows(sql, "spell_dbc")}
        self.assertIn(RECORD, brought)
        self.assertEqual(brought[RECORD], rendered.get(RECORD))

    def test_the_generator_refuses_a_bad_row(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        refused = {
            "another event": dict(base, fire_on="kill"),
            "a cast": dict(base, fire_on="cast", fire_skills="Bash"),
            "only some skills": dict(base, fire_skills="Bash"),
            "a chance of its own in the row": dict(base, chance_pct="50"),
            "an internal cooldown in the row": dict(base, icd_seconds="60"),
            "a range of cows": dict(base, value_min="3", value_max="4"),
            "a part cow": dict(base, value_min="2.5", value_max="2.5"),
            "no cow": dict(base, value_min="0", value_max="0"),
            "a skill": dict(base, skill="Bash"),
            "a condition": dict(base, cond="triggered", cond_arg="3"),
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
        work = Path(tempfile.mkdtemp(prefix="itembovine-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def headers(**changed):
        out = {"dc_item_power_math.h": MATH.read_text(encoding="utf-8"), "dc_item_summon_math.h": source("dc_item_summon_math.h"),
               "dc_proc_math.h": PROC.read_text(encoding="utf-8")}
        out.update({k.replace("__", "."): v for k, v in changed.items()})
        return out

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the Power file, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # the row fires on a hit of any skill, only with the item worn; the executor rolls the chance, so Fire never does
        out += clear + [(T("now", 1000), None), (T("fire", "hit", "Bash", 1, 0), "")]                      # not worn
        out += clear + [(T("now", 1000), None), (T("wears", "Unique_Gloves_003_x1", 0), None), (T("fire", "hit", "Bash", 1, 0), "")]
        out += clear + [(T("now", 1000), None), (T("wears", OWNER, 0), None)]
        for skill in ("Bash", "Whirlwind", "Fists of Thunder", "Spirit Barrage", "Frenzy", ""):
            for scale, draw in ((1, 0), (0.13, 99.99), (0, 50)):
                out += [(T("fire", "hit", skill, scale, draw), "summon_herd=4;")]
        out += [(T("now", 1001), None), (T("fire", "hit", "Bash", 1, 0), "summon_herd=4;")]          # every hit, no cooldown in the row
        for event in ("cast", "kill", "kill_elite", "taken", "hit_spender", "hit_generator", "image_death", "life_below", "resource_spent", ""):
            out += [(T("fire", event, "Bash", 1, 0), "")]
        # the herd: never before, the chance (percent) times the hit's coefficient falls when the draw is under it
        out += [(T("comes", "-", 0, 60, 1, 100, 99.99), "1"), (T("comes", "-", 0, 60, 1, 100, 100), "0"),
                (T("comes", "-", 0, 60, 1, 0, -1), "0"), (T("comes", "-", 0, 60, 1, -5, -1), "0"),    # blank (0) or below: never
                (T("comes", "-", 0, 60, 0, 100, -1), "0"), (T("comes", "-", 0, 60, -1, 100, -1), "0"),  # no coefficient: never
                (T("comes", "-", 0, 60, 0.5, 100, 49.99), "1"), (T("comes", "-", 0, 60, 0.5, 100, 50), "0"),
                (T("comes", "-", 0, 60, 1, 50, 49.99), "1"), (T("comes", "-", 0, 60, 1, 50, 50), "0"),
                (T("comes", "-", 0, 60, 0.13, 10, 1.29), "1"), (T("comes", "-", 0, 60, 0.13, 10, 1.31), "0")]
        # the internal cooldown since the last herd: 60 s is 60000 ms, none at its end; 0 is none at all
        out += [(T("comes", 1000, 1000, 60, 1, 100, 0), "0"), (T("comes", 1000, 60999, 60, 1, 100, 0), "0"),
                (T("comes", 1000, 61000, 60, 1, 100, 0), "1"), (T("comes", 1000, 900000, 60, 1, 100, 0), "1"),
                (T("comes", 1000, 1000, 0, 1, 100, 0), "1"), (T("comes", 1000, 2500, 1.5, 1, 100, 0), "1"),
                (T("comes", 1000, 2499, 1.5, 1, 100, 0), "0"), (T("comes", 1000, 61000, 60, 1, 0, 0), "0"),
                (T("comes", 4294967000, 100, 60, 1, 100, 0), "0"), (T("comes", 4294967000, 60000, 60, 1, 100, 0), "1")]  # the clock wraps
        # a swing: 400% plus the draw of 200%, times the owner's attacks per second, a swing a second (or the interval's share)
        out += [(T("swing", 400, 200, 0, 1, 1000), "400"), (T("swing", 400, 200, 1, 1, 1000), "600"), (T("swing", 400, 200, 0.5, 1, 1000), "500"),
                (T("swing", 400, 200, 0, 1.5, 1000), "600"), (T("swing", 400, 200, 1, 2, 1000), "1200"), (T("swing", 400, 200, 0, 1, 500), "200"),
                (T("swing", 400, 200, 0.25, 1.2, 2000), "1080"), (T("swing", 0, 0, 0.7, 1.4, 1000), "0"), (T("swing", 400, 200, 0, 0, 1000), "0")]
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
        self.assertGreater(len(want), 50)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_wrong_event": [r[:12] + ("kill",) + r[13:] for r in rows],
            "only_one_skill": [r[:13] + ("Bash",) + r[14:] for r in rows],
            "the_wrong_effect": [r[:4] + ("resource_refund",) + r[5:] for r in rows],
            "three_cows": [r[:5] + (3.0, 3.0) + r[7:] for r in rows],
            "a_chance_in_the_row": [r[:14] + (50.0,) + r[15:] for r in rows],
            "a_cooldown_in_the_row": [r[:15] + (60.0,) + r[16:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(), mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        summon = source("dc_item_summon_math.h")
        power = MATH.read_text(encoding="utf-8")
        cooldown = "if (lastMs && nowMs - *lastMs < cooldownSeconds * 1000.0)"
        header_mutants = {
            "no_cooldown": dict(dc_item_summon_math__h=mutate(summon, cooldown, "if (false)")),
            "the_cooldown_ends_a_millisecond_late": dict(dc_item_summon_math__h=mutate(summon, cooldown, cooldown.replace(" < ", " <= "))),
            "the_cooldown_in_milliseconds": dict(dc_item_summon_math__h=mutate(summon, cooldown, cooldown.replace(" * 1000.0", ""))),
            "the_cooldown_always_runs": dict(dc_item_summon_math__h=mutate(summon, cooldown, "if (true)")),
            "the_coefficient_ignored": dict(dc_item_summon_math__h=mutate(summon, "Proc::Rolls(coefficient, chancePct, roll)", "Proc::Rolls(1.0, chancePct, roll)")),
            "no_roll": dict(dc_item_summon_math__h=mutate(summon, "return Proc::Rolls(coefficient, chancePct, roll);", "return chancePct > 0 && coefficient > 0;")),
            "the_roll_inverted": dict(dc_item_summon_math__h=mutate(summon, "return Proc::Rolls(coefficient, chancePct, roll);", "return !Proc::Rolls(coefficient, chancePct, roll);")),
            "the_delta_ignored": dict(dc_item_summon_math__h=mutate(summon, "(pct + deltaPct * draw)", "pct")),
            "the_whole_delta": dict(dc_item_summon_math__h=mutate(summon, "(pct + deltaPct * draw)", "(pct + deltaPct)")),
            "the_attack_speed_ignored": dict(dc_item_summon_math__h=mutate(summon, " * attacksPerSecond", "")),
            "the_interval_ignored": dict(dc_item_summon_math__h=mutate(summon, " * intervalMs / 1000.0", "")),
            "no_fire_skills_fires_nothing": dict(dc_item_power_math__h=mutate(power, "if (!row.fireSkills.empty() && std::find(", "if (std::find(")),
            "the_event_ignored": dict(dc_item_power_math__h=mutate(power, "if (row.fireOn != fireOn || !Owned(row, counts, situation, number))", "if (!Owned(row, counts, situation, number))")),
        }
        for name, changed in header_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(**changed), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def source(name):
    """A server file's text; empty when it does not exist yet (a branch without the summon file reads red, not a crash)."""
    path = SRC / "combat" / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


if __name__ == "__main__":
    unittest.main()
