"""What a landed hit pays or heals scales with the attack's proc coefficient (diablocraft-iqsk8): D3 scales Mortal Enemy's Hatred and
Death Toll's heal (Marked for Death's runes) by the proc coefficient of the attack that landed, and the engine read none for a class
effect, so every direct hit paid or healed in full.

What this proves, and how:

  * **The rule.** tests/proc_scaling/harness.cpp compiles the real Proc::Scaled of src/combat/dc_proc_math.h with the sheet's own numbers
    (Mortal Enemy's 4 Hatred, Death Toll's 3% of Life) and the Demon Hunter's coefficients: a 0.5-coefficient hit pays half the Hatred and
    heals half, a hit that states none pays nothing. Planted mutations must each turn it red.
  * **The numbers.** The Demon Hunter sheet states each attack's proc_coefficient (before this the sheet carried none, so no Demon
    Hunter hit could proc anything): each row is the expression in its power file's ProcCoefficient tag evaluated for the rune, and
    (where the client data is installed) the expression is the file's own. A skill whose coefficients are all 0 (Caltrops, Marked for
    Death) and the skills that deal no hit have no rows.
  * **It is wired.** Marked for Death's Landed is given the landing spell and scales both effects by it; the dispatch passes it.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/combat/test_proc_scaling.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/combat/dc_proc_math.h"
HARNESS = MODULE / "tests/proc_scaling/harness.cpp"
MARKED = MODULE / "src/classes/demon_hunter/dc_demon_hunter_marked_for_death.cpp"
DISPATCH = MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp"
SHEET = "demon_hunter_skill_values.csv"
WITH_ROWS = {"Hungering Arrow", "Entangling Shot", "Bolas", "Evasive Fire", "Grenade", "Impale", "Rapid Fire", "Chakram", "Elemental Arrow",
             "Fan of Knives", "Spike Trap", "Sentry", "Vengeance", "Strafe", "Multishot", "Cluster Arrow", "Rain of Vengeance"}
NO_ROWS = {"Caltrops", "Smoke Screen", "Shadow Power", "Vault", "Preparation", "Companion", "Marked for Death"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def value(skill, rune, token):
    rows = [r for r in read(D3 / SHEET) if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, "")]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return float(rows[0]["value"])


def rune_at(skill, letter):
    rows = [r["rune_name"] for r in read(D3 / "demon_hunter_runes.csv") if (r["skill_name"], r["rune_slot"]) == (skill, letter)]
    assert len(rows) == 1, (skill, letter)
    return rows[0]


def coefficient_rows():
    return [r for r in read(D3 / SHEET) if r["token"] == "proc_coefficient"]


def evaluate(expression, letter):
    """The power file's ProcCoefficient expression for the rune of that slot letter ('' = the skill)."""
    text = expression.strip()
    if not text.startswith("("):
        text = "(" + text + ")"
    text = re.sub(r"Rune_([A-E])", lambda m: "1" if letter == m.group(1) else "0", text)
    for _ in range(12):
        reduced = re.sub(r"\((\d)\s*\?\s*([\d.]+)\s*:\s*([\d.]+)\)", lambda m: m.group(2) if m.group(1) == "1" else m.group(3), text)
        if reduced == text:
            break
        text = reduced
    return float(text.strip("() "))


def scratch_tree(mutate=None):
    key = HEADER[len("src/"):]
    files = {key: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Marked for Death", "Mortal Enemy", "gain_resource"), value("Marked for Death", "Death Toll", "heal_pct"), 100000.0,
               1.0, value("Hungering Arrow", "", "proc_coefficient"), value("Rapid Fire", rune_at("Rapid Fire", "B"), "proc_coefficient")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rule_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the coefficient is ignored", ("return amount * *coefficient;", "return amount;")),
            ("the coefficient divides", ("return amount * *coefficient;", "return amount / *coefficient;")),
            ("a hit that states none pays in full", ("if (!coefficient || *coefficient <= 0 || amount <= 0)", "if ((coefficient && *coefficient <= 0) || amount <= 0)")),
            ("a hit that states none is read as one", ("if (!coefficient || *coefficient <= 0 || amount <= 0)\n            return 0.0;\n        return amount * *coefficient;",
                                                       "if (amount <= 0)\n            return 0.0;\n        return amount * coefficient.value_or(1.0);")),
            ("a negative coefficient drains", ("if (!coefficient || *coefficient <= 0 || amount <= 0)", "if (!coefficient || amount <= 0)")),
            ("a pet's blow rolls its skill's", ("return petBlow ? petCoefficient : spellCoefficient;", "return spellCoefficient;")),
            ("a pet rolls its skill's when its attack states none", ("return petBlow ? petCoefficient : spellCoefficient;", "return petBlow && petCoefficient ? petCoefficient : spellCoefficient;")),
            ("every hit rolls the pet's", ("return petBlow ? petCoefficient : spellCoefficient;", "return petCoefficient;")),
            ("a negative amount drains", ("if (!coefficient || *coefficient <= 0 || amount <= 0)", "if (!coefficient || *coefficient <= 0)")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")

    def test_the_rule_names_no_class(self):
        text = (MODULE / HEADER).read_text(encoding="utf-8")
        for name in ("Demon Hunter", "DemonHunter", "Hatred", "Mortal Enemy", "Death Toll", "Marked for Death"):
            self.assertNotIn(name, text)


class Sheet(unittest.TestCase):
    def test_a_row_for_each_skill_that_hits_and_none_for_the_rest(self):
        rows = coefficient_rows()
        self.assertEqual({r["skill"] for r in rows}, WITH_ROWS)
        names = {r["skill_name"] for r in read(D3 / "demon_hunter_skills.csv")}
        self.assertEqual(names - WITH_ROWS, NO_ROWS)
        runes = {}
        for r in read(D3 / "demon_hunter_runes.csv"):
            runes.setdefault(r["skill_name"], []).append(r["rune_name"])
        for skill in WITH_ROWS:
            have = {r["rune"] for r in rows if r["skill"] == skill}
            self.assertEqual(have, {""} | set(runes[skill]), skill)

    def test_each_row_is_its_power_files_expression_for_the_rune(self):
        letters = {(r["skill_name"], r["rune_name"]): r["rune_slot"] for r in read(D3 / "demon_hunter_runes.csv")}
        for row in coefficient_rows():
            with self.subTest(skill=row["skill"], rune=row["rune"]):
                found = re.search(r"Power/(\w+)\.pow \(ProcCoefficient = '([^']*)'; decode_pow\.py power (\w+)\)", row["source"])
                self.assertIsNotNone(found, row["source"])
                self.assertEqual(found.group(1), found.group(3))
                letter = letters[(row["skill"], row["rune"])] if row["rune"] else ""
                self.assertAlmostEqual(float(row["value"]), evaluate(found.group(2), letter), places=9)

    def test_the_expressions_are_the_client_datas_own(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the client data is not installed")
        seen = set()
        for row in coefficient_rows():
            found = re.search(r"Power/(\w+)\.pow \(ProcCoefficient = '([^']*)'", row["source"])
            if found.group(1) in seen:
                continue
            seen.add(found.group(1))
            power = decode_pow.parse_power(decode_pow.extract(f"Power/{found.group(1)}.pow"))
            self.assertEqual(str(power["tags"][decode_pow.TAG_PROC_COEFFICIENT]), found.group(2), found.group(1))
        self.assertEqual(len(seen), len(WITH_ROWS))

    def test_the_known_numbers(self):
        for skill, rune, number in (("Hungering Arrow", "", 0.65), ("Hungering Arrow", "Shatter Shot", 0.216), ("Bolas", "", 0.5),
                                    ("Evasive Fire", "", 1.0), ("Evasive Fire", rune_at("Evasive Fire", "B"), 0.333),
                                    ("Rapid Fire", "", 0.1667), ("Rapid Fire", rune_at("Rapid Fire", "B"), 0.0556),
                                    ("Strafe", "", 0.25), ("Multishot", "", 0.1667)):
            self.assertAlmostEqual(value(skill, rune, "proc_coefficient"), number, places=6, msg=(skill, rune))

    def test_the_engine_can_read_each_row(self):
        mapped = {(r["skill"], r["rune"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["token"] == "proc_coefficient"}
        for row in coefficient_rows():
            self.assertIn((row["skill"], row["rune"]), mapped)

    def test_the_migration_carries_the_rows(self):
        sql = (MODULE / "data/sql/db-world/updates/combat_0120_demon_hunter_proc_coefficients.sql").read_text(encoding="utf-8")
        generated = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        # the render of its day: every row it holds is still in the newest render (test_pet_proc_coefficients.py holds the newest)
        self.assertLessEqual(sql.count("proc_coefficient"), generated.count("proc_coefficient"))
        self.assertGreater(sql.count("'proc_coefficient'"), 100)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.marked = squeeze(MARKED.read_text(encoding="utf-8"))
        self.dispatch = squeeze(DISPATCH.read_text(encoding="utf-8"))

    def test_both_effects_scale_by_the_landing_attack(self):
        landed = self.marked[self.marked.index("void Landed("):self.marked.index("void RegisterScripts(")]
        self.assertIn("void Landed(Player* player, Unit* target, std::uint32_t spellId)", landed)
        self.assertIn('auto const coefficient = Numbers::Get(spellId, "proc_coefficient");', landed)
        self.assertEqual(landed.count("Proc::Scaled(coefficient,"), 2)
        self.assertIn('#include "../../combat/dc_proc_math.h"', MARKED.read_text(encoding="utf-8"))

    def test_the_dispatch_passes_the_spell(self):
        self.assertEqual(self.dispatch.count("MarkedForDeath::Landed(player, target, spellId);"), 1)


if __name__ == "__main__":
    unittest.main()
