"""Legendary rest, bead diablocraft-sjdct: Countess Julia's Cameo (an amulet, list row 57, K3), and the piece it builds, N-PREVENT.

  "Prevent all Arcane damage taken and heal yourself for [20 - 25]% of the amount prevented."
  * the numbers are read from d3planner (item_neck.js, Unique_Amulet_103_x1: the 20-25) and from the item's power file (ItemPassive_Unique_Ring_519_x1.pow
    SF_0 'Damage Type Prevent Percent' = 1, through decode_pow.py); the table (data/legendary_powers.csv) holds TWO `element` rows for the amulet:
    arcane `damage_prevented_pct` 100 (fixed) and arcane `heal_of_prevented_pct` 20-25 (rolled once per item);
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses a
    bad prevention row;
  * the production rules (src/combat/dc_item_power_math.h: PreventDamage and PreventFor, with Owned / ElementSum / RollPowers) are compiled and driven
    with the generated rows: while the amulet is worn all of an Arcane hit is prevented and the rolled share of it heals, rounded down; another element, a
    hit of 0, another owner's item or an unworn amulet changes nothing; a Primal rolls 25;
  * mutants of the rows and the rules fail the same driver; source-text guards that the defence step calls ItemPowers::Prevent on what is left after
    the mitigation, that the reader looks only when some row prevents, maps the hit's school to its element and heals through a stock heal record. The
    C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-sjdct.md.
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

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_countess_julias_cameo/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Amulet_103_x1"
PREVENT = "damage_prevented_pct"
HEAL = "heal_of_prevented_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return sorted((r for r in (all_rows() if rows is None else rows) if r[0] == OWNER), key=lambda r: r[4])


def words():
    """(the heal's low, its high) from d3planner's amulet."""
    text = (REPO / "reference/d3planner/item_neck.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Prevent all Arcane damage taken and heal yourself for %d%% of the amount prevented\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_say_arcane_and_20_to_25(self):
        self.assertEqual((20.0, 25.0), words())
        text = (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8")
        self.assertIn("Prevent all Arcane damage taken and heal yourself for [20-25]% of the amount prevented.", text)

    def test_the_power_file_prevents_all_of_it(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        out = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "ItemPassive_Unique_Ring_519_x1"],
                              capture_output=True, text=True).stdout
        self.assertRegex(out, r"'Damage Type Prevent Percent' = 1\b")
        item = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "item", OWNER], capture_output=True, text=True).stdout
        self.assertIn("ItemPassive_Unique_Ring_519_x1.pow: 0.2-0.25", item)

    def test_two_element_rows_on_arcane(self):
        low, high = words()
        self.assertEqual([(OWNER, 0, "element", "arcane", PREVENT, 100.0, 100.0, *BLANK), (OWNER, 0, "element", "arcane", HEAL, low, high, *BLANK)], mine())

    def test_the_tooltip_says_it(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertIn("Prevent all Arcane damage taken and heal yourself for 20–25% of the amount prevented.", m[1])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0064_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "element", "skill": "arcane", "stat": PREVENT, "value_min": "100", "value_max": "100", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="cameo-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + list(edits))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        heal = {**self.BASE, "stat": HEAL, "value_min": "20", "value_max": "25"}
        self.assertEqual(2, len([r for r in self.render_with(self.BASE, heal) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        heal = {**self.BASE, "stat": HEAL, "value_min": "20", "value_max": "25"}
        refused = {
            "a range of the prevented share": ([{**self.BASE, "value_min": "90"}], "is an item's percent above 0"),
            "more than all": ([{**self.BASE, "value_min": "101", "value_max": "101"}], "is an item's percent above 0|needs 0 < value_min"),
            "zero": ([{**self.BASE, "value_min": "0", "value_max": "0"}], "is an item's percent above 0|needs 0 < value_min"),
            "a heal above 100": ([self.BASE, {**heal, "value_max": "101"}], "is an item's percent above 0"),
            "an element with no hit school": ([{**self.BASE, "skill": "poison"}], "is an item's percent above 0"),
            "a condition": ([{**self.BASE, "cond": "triggered", "cond_arg": "3", "fire_on": "cast", "fire_skills": "Rend"}], "is an item's percent above 0|an event fires"),
            "a set level": ([{**self.BASE, "pieces": "2"}], "is an item's percent above 0|not a set"),
            "a heal with no prevention": ([heal], "needs its damage_prevented_pct row"),
            "a heal for another element": ([self.BASE, {**heal, "skill": "fire"}], "needs its damage_prevented_pct row"),
        }
        for name, (edits, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(*edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="itemcameo-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, not from the code."""
        low, high = words()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = lambda roll=None: [(T("wears", OWNER), None)] + ([(T("value", OWNER, "arcane", HEAL, roll), None)] if roll is not None else [])  # noqa: E731
        # not worn: the hit is taken whole
        out += clear + [(T("prevent", "arcane", 1000), "1000 0"), (T("prevent", "arcane", 0), "0 0")]
        # worn and rolled: all of an Arcane hit is prevented and the rolled share of it heals, rounded down
        for roll in (low, 22, high):
            out += clear + wear(roll)
            for damage in (1000, 1001, 333, 7, 1, 0):
                heal = int(damage * roll / 100 + 1e-9)
                out += [(T("prevent", "arcane", damage), "0 %d" % heal)]
        # worn, nothing rolled yet: the prevention is whole, the heal is not on
        out += clear + wear() + [(T("prevent", "arcane", 1000), "0 0")]
        # the other elements, and a school with no element, are taken whole
        out += clear + wear(22)
        for element in ("fire", "cold", "lightning", "physical", "poison", "holy", "", "Arcane", "arcanes"):
            out += [(T("prevent", element, 1000), "1000 0")]
        # another owner's item prevents nothing
        out += clear + [(T("wears", "Other Amulet"), None), (T("value", "Other Amulet", "arcane", HEAL, 22), None), (T("prevent", "arcane", 1000), "1000 0")]
        # a roll stored but the amulet in the bag
        out += clear + [(T("value", OWNER, "arcane", HEAL, 22), None), (T("prevent", "arcane", 1000), "1000 0")]
        # the share itself: clamped to 0..100, whole numbers rounded down
        for damage, pct, heal, taken, healed in ((1000, 100, 25, 0, 250), (1000, 50, 20, 500, 100), (1000, 150, 25, 0, 250), (1000, -5, 25, 1000, 0),
                                                 (999, 33, 50, 670, 164), (1000, 100, 150, 0, 1000), (1000, 100, -3, 0, 0), (0, 100, 25, 0, 0),
                                                 (4294967295, 100, 25, 0, 1073741823)):
            out += [(T("share", damage, pct, heal), "%d %d" % (taken, healed))]
        # one roll stored under the element's name: a Primal stores the top of the range
        out += [(T("roll", OWNER, 1), "power:arcane:%s=%g;" % (HEAL, high)), (T("roll", OWNER, 0), "power:arcane:%s=%g;" % (HEAL, (low + high) / 2))]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(real, rows, "want")
        prevent, heal = rows
        row_mutants = {
            "the_element_lost": [prevent[:3] + ("fire",) + prevent[4:], heal],
            "half_prevented": [prevent[:5] + (50.0, 50.0) + prevent[7:], heal],
            "the_heal_of_the_wrong_range": [prevent, heal[:5] + (1.0, 5.0) + heal[7:]],
            "the_heal_on_another_element": [prevent, heal[:3] + ("fire",) + heal[4:]],
            "no_heal_row": [prevent],
            "no_prevent_row": [heal],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline Prevented PreventDamage("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "the_share_is_not_clamped": ("std::min(100.0, std::max(0.0, preventedPct)) / 100.0", "std::max(0.0, preventedPct) / 100.0"),
            "a_negative_share_prevents": ("std::min(100.0, std::max(0.0, preventedPct)) / 100.0", "std::min(100.0, preventedPct) / 100.0"),
            "the_heal_is_not_clamped": ("std::min(100.0, std::max(0.0, healPct)) / 100.0", "std::max(0.0, healPct) / 100.0"),
            "the_heal_is_of_the_damage": ("std::floor(prevented * heal + 1e-9)", "std::floor(damage * heal + 1e-9)"),
            "the_prevented_is_rounded_up": ("std::floor(damage * share + 1e-9)", "std::ceil(damage * share)"),
            "the_heal_is_rounded_up": ("std::floor(prevented * heal + 1e-9)", "std::ceil(prevented * heal)"),
            "the_damage_is_not_cut": ("return {damage - prevented,", "return {damage,"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, body.count(old), name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        sums = real[real.index("inline Prevented PreventFor("):]
        sums = sums[:sums.index("\n    }\n") + 7]
        for name, (old, new) in {
            "the_wrong_stat": ('"damage_prevented_pct"', '"damage_pct"'),
            "the_heal_reads_the_prevented_stat": ('"heal_of_prevented_pct"', '"damage_prevented_pct"'),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, sums.count(old), name + " does not apply")
                _, got = self.drive(real.replace(sums, sums.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def hook_failures(hooks, reader, loader, internal, header):
    """What is wrong with the defence step's use of the prevention in the texts given ([] when it is right)."""
    flat = re.sub(r"\s+", " ", hooks)
    flat_reader = re.sub(r"\s+", " ", reader)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    step = flat[flat.index("bool ApplyPlayerDefence("):]
    step = step[:step.index("return true;")]
    mitigated = step.find("damage = static_cast<Amount>(std::max(0.0, *mitigated));")
    called = step.find("ItemPowers::Prevent(player, schoolMask, left);")
    need("the step prevents what is left after the mitigation", 0 <= mitigated < called)
    need("it hands the reader the school mask and the amount", "std::uint32_t left = static_cast<std::uint32_t>(damage); ItemPowers::Prevent(player, schoolMask, left); damage = static_cast<Amount>(left);" in step)
    need("the reader looks only when some row prevents", "if (!player || !damage || !Data().prevents) return;" in flat_reader)
    need("the reader maps the school to its element", "char const* element = Detail::ElementOfSchool(schoolMask); if (!element) return;" in flat_reader)
    need("the reader sums the worn rows under its lock", "ItemPower::PreventFor(Data().rows, CountsOf(guid), element, damage, SituationOf(guid, std::move(seen)))" in flat_reader)
    need("the damage becomes what is still taken", "damage = result.taken;" in flat_reader)
    need("the heal is a stock heal record's, to the player", "HealInfo healing(player, player, result.healed, info, SpellSchoolMask(info->SchoolMask)); player->HealBySpell(healing, false);" in flat_reader)
    need("the flag is set from a prevention row", 'loaded.prevents = loaded.prevents || row.stat == "damage_prevented_pct";' in loader)
    need("the flag is declared", "bool prevents = false;" in internal)
    need("the reader is declared", "void Prevent(Player*, unsigned schoolMask, std::uint32_t& damage);" in header)
    return wrong


class Hooks(unittest.TestCase):
    texts = None

    @classmethod
    def setUpClass(cls):
        cls.texts = [(SRC / "combat" / n).read_text(encoding="utf-8") for n in
                     ("dc_combat_hooks.cpp", "dc_item_powers_elements.cpp", "dc_item_powers.cpp", "dc_item_powers_internal.h", "dc_item_powers.h")]

    def test_the_defence_step_and_the_reader(self):
        self.assertEqual([], hook_failures(*self.texts))

    def test_the_source_guards_fail_their_mutants(self):
        hooks, reader, loader, internal, header = self.texts
        mutants = {
            "before_the_mitigation": (0, "damage = static_cast<Amount>(std::max(0.0, *mitigated));\n            // What the worn powers prevent of what is left, and heal (N-PREVENT).",
                                      "// What the worn powers prevent of what is left, and heal (N-PREVENT)."),
            "the_wrong_school": (0, "ItemPowers::Prevent(player, schoolMask, left);", "ItemPowers::Prevent(player, 0, left);"),
            "no_flag_check": (1, "!Data().prevents", "false"),
            "the_element_is_fixed": (1, "Detail::ElementOfSchool(schoolMask)", '"arcane"'),
            "the_damage_stays": (1, "damage = result.taken;", ""),
            "no_heal": (1, "player->HealBySpell(healing, false);", ""),
            "the_flag_is_never_set": (2, 'loaded.prevents = loaded.prevents || row.stat == "damage_prevented_pct";', ""),
        }
        for name, (index, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, self.texts[index].count(old), name + " does not apply")
                changed = list(self.texts)
                changed[index] = self.texts[index].replace(old, new, 1)
                self.assertNotEqual([], hook_failures(*changed), name + " survived")


if __name__ == "__main__":
    unittest.main()
