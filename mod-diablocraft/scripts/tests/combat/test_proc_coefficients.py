"""diablocraft-proc-coefficients-wiring: a crit's procs roll the skill's own
D3 proc coefficient (ruling 2026-09-29, q-0929-11).

Three things are proved here, none of them by restating the arithmetic:
  * every Barbarian and Wizard skill and rune resolves to a coefficient, and
    each is the one in docs/research/proc-coefficients.csv, with its source;
  * the production roll (src/combat/dc_proc_math.h) is compiled and driven
    with the value the generator emitted into spell_shells.sql, so Whirlwind
    (0.13) procs less than Bash (1.0) and a hit with no coefficient never
    procs;
  * a mutant of that function (the coefficient ignored; a missing one read as
    1) makes the same driver fail.
"""
import csv
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source  # noqa: E402
import harness_env
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
DATA = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
HEADER = MODULE / "src" / "combat" / "dc_proc_math.h"
HARNESS = MODULE / "tests" / "proc_coefficients" / "harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch"
CLASSES = ("Barbarian", "Wizard")


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def research():
    """(class, skill, rune) -> (coefficient, verdict); rune '' is the skill."""
    table = {}
    for row in read(REPO / "docs/research/proc-coefficients.csv"):
        rune = "" if row["rune"] == "None" else row["rune"].split(" - ", 1)[1]
        table[(row["class"], row["skill"], rune)] = (float(row["coefficient"]), row["verdict"])
    return table


def sheet(cls):
    """(skill, rune) -> the sheet's proc_coefficient row."""
    rows = {}
    for row in read(DATA / ("%s_skill_values.csv" % cls.lower())):
        if row["token"] == "proc_coefficient" and not row["qualifier"]:
            assert (row["skill"], row["rune"]) not in rows, row
            rows[(row["skill"], row["rune"])] = row
    return rows


def resolved(rows, skill, rune):
    """What Numbers::Get answers: the rune's own row, else its skill's."""
    return rows.get((skill, rune)) or rows.get((skill, ""))


def generated_coefficients():
    """spell name -> the value the generator wrote for that spell id."""
    names = {int(row["spell_id"]): row["name"] for row in read(GENERATED / "spell_shells.csv")}
    text = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    return {names[int(spell)]: float(value) for spell, value in
            re.findall(r"\((\d+),'proc_coefficient','',([0-9.]+)\)", text) if int(spell) in names}


class ProcCoefficientTests(unittest.TestCase):
    def test_every_skill_and_rune_has_its_coefficient_and_a_source(self):
        want = research()
        for cls in CLASSES:
            rows = sheet(cls)
            skills = [row["skill_name"] for row in read(DATA / ("%s_skills.csv" % cls.lower()))]
            runes = [(row["skill_name"], row["rune_name"])
                     for row in read(DATA / ("%s_runes.csv" % cls.lower()))]
            self.assertTrue(skills and runes)
            for skill, rune in [(s, "") for s in skills] + runes:
                row = resolved(rows, skill, rune)
                self.assertIsNotNone(row, "%s %s / %s has no proc_coefficient" % (cls, skill, rune))
                self.assertAlmostEqual(float(row["value"]), want[(cls, skill, rune)][0], places=6,
                                       msg="%s %s / %s differs from the research" % (cls, skill, rune))
                self.assertTrue(row["source"].strip(), "%s %s / %s has no source" % (cls, skill, rune))
                planner_only = want[(cls, skill, rune)][1] == "D3PLANNER ONLY"
                self.assertEqual("d3planner" in row["source"], planner_only,
                                 "%s %s / %s: MPQ first, d3planner only where the data has no tag"
                                 % (cls, skill, rune))
        # the twelve rows the MPQ has no tag for, and no others
        self.assertEqual(12, sum(1 for v in want.values() if v[1] == "D3PLANNER ONLY"))
        self.assertEqual({"Avalanche", "Black Hole"},
                         {k[1] for k, v in want.items() if v[1] == "D3PLANNER ONLY"})

    def test_the_retired_rows_are_gone_and_superstition_stays_flat(self):
        sheet_rows = {row["name"]: row for row in read(MODULE / "data/tunables/ability_tunables.csv")}
        for name in ("overpower_crit_cdr_chance_pct", "slaughter_eruption_chance_pct"):
            self.assertNotIn(name, sheet_rows)
            self.assertNotIn("INSERT INTO dc_ability_tuning VALUES ('%s'" % name,
                             (GENERATED / "ability_tunables.sql").read_text(encoding="utf-8"))
        flat = sheet_rows["superstition_fury_proc_chance_pct"]
        self.assertEqual(20.0, float(flat["value"]))
        self.assertIn("no proc coefficient for ordinary monster attacks", flat["notes"])

    def test_the_crit_procs_roll_the_hitting_spells_coefficient(self):
        code = barbarian_source.abilities((".cpp",))
        roll = code[code.index("bool Procs(uint32 spellId)"):code.index("uint32 WrathBuff()")]
        self.assertIn('Proc::Rolls(Numbers::Get(spellId, "proc_coefficient")', roll)
        overpower = barbarian_source.named("dc_barbarian_overpower.cpp")
        wrath = barbarian_source.named("dc_barbarian_wrath_of_the_berserker.cpp")
        body = overpower[overpower.index("void OnCritical("):overpower.index("void RegisterScripts")] + wrath[wrath.index("void OnCritical("):]
        self.assertEqual(2, body.count("Procs(spellId)"), "Overpower and Slaughter both roll it")
        self.assertNotIn("chance_pct", body + roll)
        self.assertNotIn("value_or(1", code, "a missing coefficient must never default to 1")

    # --- the production function, driven -----------------------------------

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"dc_proc_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="proc-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def drive(self, header_text, name, cases):
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join("%s %s" % c for c in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return {label: int(hits) / int(rolls) for label, hits, rolls in
                    (line.split() for line in run.stdout.splitlines())}
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def cases(self):
        generated = generated_coefficients()
        for name in ("Whirlwind", "Bash", "Bash - Onslaught"):
            self.assertIn(name, generated, "the generator did not emit %s's coefficient" % name)
        return generated, [("whirlwind", generated["Whirlwind"]), ("bash", generated["Bash"]),
                           ("onslaught", generated["Bash - Onslaught"]), ("none", "none")]

    def outcome(self, rates):
        return (abs(rates["bash"] - 1.0) < 1e-9 and abs(rates["whirlwind"] - 0.13) < 0.01
                and rates["whirlwind"] < rates["bash"] and abs(rates["onslaught"] - 0.333) < 0.01
                and rates["none"] == 0.0)

    def test_whirlwind_procs_less_than_bash_and_no_coefficient_never_procs(self):
        generated, cases = self.cases()
        self.assertEqual(0.13, generated["Whirlwind"])
        self.assertEqual(1.0, generated["Bash"])
        rates = self.drive(HEADER.read_text(encoding="utf-8"), "real", cases)
        self.assertTrue(self.outcome(rates), rates)

    def test_the_mutants_fail_the_same_driver(self):
        real = HEADER.read_text(encoding="utf-8")
        _generated, cases = self.cases()
        ignores = real.replace("return float(*coefficient * 100.0);", "return 100.0f;")
        defaults_to_one = real.replace("if (!coefficient || *coefficient <= 0)\n            return 0.0f;",
                                       "if (!coefficient)\n            return 100.0f;\n"
                                       "        if (*coefficient <= 0)\n            return 0.0f;")
        for name, mutant in (("ignores", ignores), ("one", defaults_to_one)):
            self.assertNotEqual(real, mutant, "the %s mutation no longer applies to the header" % name)
            rates = self.drive(mutant, name, cases)
            self.assertFalse(self.outcome(rates), "mutant %s passed: %s" % (name, rates))


if __name__ == "__main__":
    unittest.main()
