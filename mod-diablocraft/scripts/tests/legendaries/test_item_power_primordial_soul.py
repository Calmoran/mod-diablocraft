"""Primordial Soul (diablocraft-tt86k, legendary 005, wizard Source): "Elemental Exposure's damage bonus per stack is increased to 10%."

  * data/legendary_powers.csv gains one row of the new kind `passive`: the item raises the passive Elemental Exposure's own number
    `damage_taken_pct` (wizard_passive_values.csv, 5 per stack) to the item's 10; the 10 is read out of the tooltip text the players see and
    the catalogue row, the 5 and the 4 stacks out of the passive's own sheet, which this bead leaves as it is;
  * the generator refuses a `passive` row it cannot stand behind (a passive or number that does not exist, one the code does not read,
    one that would not raise the number, a range, a condition or an event);
  * the REAL Wizard::TargetFactor (cut out of dc_wizard.cpp) and the REAL ItemPower::PassiveSetTo (dc_item_power_math.h) are compiled against
    doubles and driven with the generated row and the sheet's numbers: 5 per stack without the item, 10 with it, 1 to 4 stacks and a
    fifth and sixth that add nothing, nothing at all without the passive, nothing from another item, a row of another number read as it is;
  * a mutant of each rule the change adds (the item raises it, the item is needed, the passive is needed, the cap stays the passive's
    4, the number comes from the table, a raise never lowers) fails the same driver;
  * source-text guards that the wrapper reads the worn items' state and that TargetFactor takes the number before its lock (they prove the
    calls are there, not that they run; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-diablocraft-tt86k.md).
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
import wizard_source  # noqa: E402
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402
from test_item_power_math import ROW, read_csv  # noqa: E402  (a module, so its test classes are not run twice)

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
WIZARD = wizard_source.CPP
HARNESS = MODULE / "tests/item_power_primordial_soul/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SOUL, GLOVES = "P4_Unique_Orb_001", "P66_Unique_Gloves_007"
EXPOSURE, TOKEN = "Elemental Exposure", "damage_taken_pct"
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def passive_number(token):
    found = [r for r in read_csv("data/d3/wizard_passive_values.csv") if r["skill"] == EXPOSURE and r["token"] == token]
    assert len(found) == 1, token
    return float(found[0]["value"])


def tooltip(d3_id):
    """The power text the players see (dc_item_tooltip, generate_crafting.py); the SQL doubles an apostrophe."""
    m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','((?:[^']|'')*)'" % re.escape(d3_id),
                  (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
    assert m, d3_id
    return m[1].replace("''", "'")


def item_number():
    """The 10, from the text the players see and from the catalogue row the bead was cut from."""
    text = tooltip(SOUL)
    found = re.fullmatch(r"Elemental Exposure's damage bonus per stack is increased to (\d+)%\.", text)
    assert found, text
    catalogue = [r for r in read_csv_repo("docs/research/legendary-catalogue.csv") if r["d3_id"] == SOUL]
    assert len(catalogue) == 1 and text in catalogue[0]["power_text"], catalogue
    return float(found[1])


def read_csv_repo(name):
    with (REPO / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def definition(marker, source):
    """One function, braces balanced, exactly as the module has it."""
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def target_factor(source):
    return definition("double TargetFactor(Player* player, Unit* target)", source)


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


def build(math_text, wizard_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {"combat/dc_item_power_math.h": math_text, "dc_primordial_soul_extract.h": "// cut out of dc_wizard.cpp by test_item_power_primordial_soul.py\n" + target_factor(wizard_text) + "\n"}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
    work = Path(tempfile.mkdtemp(prefix="soul-%s-" % name, dir=str(SCRATCH)))
    return work, binary


class Table(unittest.TestCase):
    def test_the_row_is_the_sources_number(self):
        ten = item_number()
        self.assertEqual(10, ten)
        self.assertEqual({(SOUL, 0, "passive", EXPOSURE, TOKEN, ten, ten, *BLANK)}, {r for r in all_rows() if r[0] == SOUL})

    def test_the_passives_own_number_is_left_alone(self):
        # the sheet keeps 5 per stack for 4 stacks; the item's number is on the item power table, not in the passive's sheet
        self.assertEqual((5, 4), (passive_number(TOKEN), passive_number("max_stacks_count")))
        self.assertNotIn("Primordial Soul", (MODULE / "data/d3/wizard_passive_values.csv").read_text(encoding="utf-8"))
        self.assertLess(passive_number(TOKEN), item_number())

    def test_the_newest_table_is_not_yet_shipped_and_the_earlier_one_stays_as_written(self):
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn(GENERATED.name, applied)
        self.assertNotIn(SOUL, (MODULE / "data/sql/db-world/updates/legendary_powers_0011_table.sql").read_text(encoding="utf-8"))

    def test_the_row_has_a_source_and_a_note(self):
        row = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == SOUL)
        self.assertTrue(row["source"].strip() and row["note"].strip())

    @staticmethod
    def rows_of(sheet_rows):
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv",
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_passive_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]

    def test_the_generator_refuses_a_passive_row_it_cannot_stand_behind(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        good = {"owner": SOUL, "pieces": "", "kind": "passive", "skill": EXPOSURE, "stat": TOKEN, "value_min": "10", "value_max": "10",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "",
                "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        self.assertEqual([(SOUL, 0, "passive", EXPOSURE, TOKEN, 10.0, 10.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], self.rows_of([good]))
        bad = {
            "a passive that does not exist": dict(good, skill="Not A Passive"),
            "a number the passive does not have": dict(good, stat="no_such_token"),
            "a passive number the code does not read": dict(good, skill="Conflagration", stat="duration_seconds"),
            "a number that is the passive's own": dict(good, value_min="5", value_max="5"),
            "a number under the passive's own": dict(good, value_min="3", value_max="3"),
            "a range": dict(good, value_max="12"),
            "no passive named": dict(good, skill=""),
            "a condition": dict(good, cond="triggered", cond_arg="3", fire_on="kill"),
            "an event": dict(good, fire_on="kill"),
            "a passive named by another kind": dict(good, kind="skill"),
            "an item that is not in the pool": dict(good, owner="Not_An_Item"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        self.assertIn("passive", generator.KINDS)


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        base, most, ten = passive_number(TOKEN), int(passive_number("max_stacks_count")), item_number()
        want = lambda pct, stacks: "%.10g" % (1 + pct * min(stacks, most) / 100)  # noqa: E731
        out = [(T("row", *row), None) for row in all_rows()]
        # a row of another number on an item of its own: the number is the table's, not a constant (a what-if, not a built power)
        out += [(T("row", "What_If_Soul", 0, "passive", EXPOSURE, TOKEN, 12, 12, *BLANK), None),
                (T("num", TOKEN, base), None), (T("num", "max_stacks_count", most), None), (T("now", 1000), None)]
        schools = (2, 4, 8, 16, 32, 64)
        for stacks in range(0, 7):
            marks = [(T("mark", 7, school, 9000), None) for school in schools[:stacks]]
            marks += [(T("mark", 8, school, 9000), None) for school in schools]            # another enemy's marks
            clear = [(T("clear"), None)]
            # without the item: the passive's own 5 per stack
            out += clear + marks + [(T("has", 1), None), (T("factor", 7), want(base, stacks))]
            # with the item: 10 per stack, the same cap
            out += clear + marks + [(T("has", 1), None), (T("wears", SOUL), None), (T("factor", 7), want(ten, stacks))]
            # with the item but without the passive: nothing (the item grants nothing)
            out += clear + marks + [(T("wears", SOUL), None), (T("factor", 7), "1")]
            # another item's power is no raise
            out += clear + marks + [(T("has", 1), None), (T("wears", GLOVES), None), (T("factor", 7), want(base, stacks))]
            # the item whose row says 12 reads 12
            out += clear + marks + [(T("has", 1), None), (T("wears", "What_If_Soul"), None), (T("factor", 7), want(12, stacks))]
        # a stack whose clock has run out is no stack, with the item as without it
        out += [(T("clear"), None), (T("mark", 7, 2, 900), None), (T("mark", 7, 4, 1000), None), (T("mark", 7, 8, 1001), None), (T("has", 1), None),
                (T("wears", SOUL), None), (T("factor", 7), want(ten, 1))]
        # the raise itself: from the passive's 5 to 10 with the item, no change without it, never lowered
        out += [(T("clear"), None), (T("raised", base), "%g" % base), (T("raised", 12), "12"),
                (T("wears", SOUL), None), (T("raised", base), "%g" % ten), (T("raised", ten), "%g" % ten), (T("raised", 12), "12"),
                (T("clear"), None), (T("wears", GLOVES), None), (T("raised", base), "%g" % base)]
        return out

    def drive(self, math_text, wizard_text, name):
        cases = self.cases()
        work, binary = build(math_text, wizard_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_production_arithmetic_agrees_with_the_sources(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), WIZARD.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        math, wizard = MATH.read_text(encoding="utf-8"), WIZARD.read_text(encoding="utf-8")
        call = 'ItemPowers::PassiveSetTo(player, "Elemental Exposure", "damage_taken_pct", Num(id, "damage_taken_pct"))'
        walk = 'ActiveValues(rows, counts, "passive", passive, token, situation))\n            if (value > base)\n                base = value;'
        mutants = {
            # the item raises the number
            "the_item_does_not_raise": (math, mutate(wizard, call, 'Num(id, "damage_taken_pct")')),
            # the item must be worn
            "the_item_is_not_needed": (mutate(math, 'ActiveValues(rows, counts, "passive", passive, token, situation))',
                                       '[&] { std::vector<double> all; for (Row const& r : rows) if (r.kind == "passive" && r.skill == passive && r.stat == token) '
                                       'all.push_back(r.min); return all; }())'), wizard),
            # the wizard must have the passive: the item does not grant it
            "the_passive_is_not_needed": (math, mutate(wizard, ' || !Has(player, "Elemental Exposure"))\n            return 1.0;', ')\n            return 1.0;')),
            # the cap stays the passive's own 4
            "the_cap_is_gone": (math, mutate(wizard, 'std::min<std::ptrdiff_t>(stacks, std::ptrdiff_t(Num(id, "max_stacks_count")))', "stacks")),
            "the_cap_is_the_items": (math, mutate(wizard, 'std::ptrdiff_t(Num(id, "max_stacks_count"))', 'std::ptrdiff_t(Num(id, "max_stacks_count") + 1)')),
            # the number comes from the table
            "the_value_is_a_constant": (mutate(math, walk, walk.replace("base = value;", "base = 10;")), wizard),
            # a raise never lowers
            "the_raise_lowers": (mutate(math, walk, walk.replace("value > base", "value != base")), wizard),
        }
        for name, (math_text, wizard_text) in mutants.items():
            self.assertTrue((math_text, wizard_text) != (math, wizard), "the %s mutation no longer applies" % name)
            want, got = self.drive(math_text, wizard_text, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
