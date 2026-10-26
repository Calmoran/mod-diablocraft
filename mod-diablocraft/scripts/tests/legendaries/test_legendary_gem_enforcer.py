"""diablocraft-ml7y (Legendary gems): Enforcer, wired from the sourced pet list.

  * the pet list is data (data/legendary_gem_pets.csv, one row per skill with its source and how well it is sourced) and
    is the list of docs/research/enforcer-pets-web-sources.md section 2 (rows that say Yes): Hydra, Mirror Image and
    Call of the Ancients; Familiar and Teleport - Fracture are not on it; Mirror Image is marked as one source;
  * the creature entries it lists are the ones the summon tables hold (the Ancients' constants, wizard_summons.csv), and
    no entry is a Hydra's or a Familiar's (cannot be targeted, so the 90% has nothing to act on);
  * generate_legendary_gem_pets.py emits dc_legendary_gem_pet from it and refuses a row it cannot stand behind;
  * the production math (src/combat/dc_gem_power_math.h: Resolve, the two factors, the pet list tests) is compiled and
    driven with the generated rows. Every expected number comes from d3planner's text and the sheet, not from the code
    under test; a class with no pets (an empty list) gets nothing;
  * mutants of the math fail the same driver;
  * source-text guards that the hooks call it, and that no pet skill is named in the gem code (they prove the call is
    there, not that it runs; the C++ is compile-checked by syntax_check.sh and the in-game steps are in
    docs/test-enforcer.md).
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import test_legendary_gem_group_c as groupc
import test_legendary_gem_rank25 as rank25
import test_legendary_gems as numbers

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_gem_power_math.h"
HARNESS = MODULE / "tests/legendary_gem_enforcer/harness.cpp"
PETS = MODULE / "data/legendary_gem_pets.csv"
RESEARCH = REPO / "docs/research/enforcer-pets-web-sources.md"
SCRATCH = numbers.SCRATCH
RANKS = (0, 1, 24, 25, 26, 50, 100, 150, 300)


def read_pets():
    with PETS.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def entries_of(row):
    return [int(x) for x in row["creature_entries"].split("|")] if row["creature_entries"] else []


def sourced_yes():
    """The skills the research marks as boosted by Enforcer (section 2: the `Enforcer applies?` verdict starts **Yes**)."""
    out = set()
    for line in RESEARCH.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) > 5 and cells[1] in ("Wizard", "Barbarian"):
            # the pet-source cell can hold a `|` of its own (a wiki link), so the verdict is the first **Yes**/**No cell
            verdict = next(c for c in cells[3:] if c.startswith(("**Yes**", "**No")))
            if verdict.startswith("**Yes**"):
                out.add(cells[2].strip("*").split(" — ")[0])
    return out


def build(header_text, name):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {**{rel: (SRC / rel).read_text(encoding="utf-8") for rel in ("common/dc_legendary_gem.h", "items/dc_legendary_gem_item.h")}, "combat/dc_gem_power_math.h": header_text}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O0"], files=files)
    work = Path(tempfile.mkdtemp(prefix="gemenforcer-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def run(lines, header_text=None, name="real"):
    work, binary = build(header_text or MATH.read_text(encoding="utf-8"), name)
    try:
        (work / "cases.txt").write_text("\n".join(lines) + "\n")
        return harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def enforcer_id():
    return {r["gem_name"]: r["gem_id"] for r in numbers.read(numbers.CSV)}["Enforcer"]


def pet_lines(rows=None):
    """`pet` lines as the table would hold them: one per (skill, entry), entry 0 when the skill has none."""
    lines = []
    for r in (read_pets() if rows is None else rows):
        for entry in entries_of(r) or [0]:
            lines.append("pet %d %s" % (entry, r["skill"]))
    return lines


class PetList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_pets()
        cls.by_skill = {r["skill"]: r for r in cls.rows}

    def test_the_list_is_the_researchs_yes_rows_and_nothing_else(self):
        self.assertEqual({"Hydra", "Mirror Image", "Call of the Ancients"}, sourced_yes())
        self.assertEqual(sourced_yes(), set(self.by_skill))
        self.assertEqual(len(self.rows), len(self.by_skill))  # one row a skill
        for left_out in ("Familiar", "Teleport"):  # a pet by the wiki's list, not shown to be boosted (section 5)
            self.assertNotIn(left_out, self.by_skill)

    def test_every_row_is_enforcers_names_a_real_skill_of_its_class_and_has_a_source(self):
        for r in self.rows:
            self.assertEqual(enforcer_id(), r["gem_id"])
            skills = {s["skill_name"] for s in numbers.read(MODULE / ("data/d3/%s_skills.csv" % r["class"].lower()))}
            self.assertIn(r["skill"], skills, r)
            self.assertTrue(r["source"].startswith("https://"), r)
            self.assertIn(r["evidence"], ("corroborated", "wiki-only"), r)

    def test_mirror_image_is_marked_as_resting_on_one_source_and_no_other_is(self):
        # section 5: one wiki page states it, nothing corroborates it
        self.assertEqual({"Mirror Image"}, {r["skill"] for r in self.rows if r["evidence"] == "wiki-only"})

    def test_the_creature_entries_are_the_summon_tables(self):
        header = (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.h").read_text(encoding="utf-8")
        first = int(re.search(r"FirstEntry = (\d+)", header).group(1))
        count = int(re.search(r"Count = (\d+)", header).group(1))
        self.assertEqual(list(range(first, first + count)), entries_of(self.by_skill["Call of the Ancients"]))
        summons = numbers.read(MODULE / "data/d3/wizard_summons.csv")
        image = [int(s["entry"]) for s in summons if s["summon"] == "Mirror Image"]
        self.assertEqual(image, entries_of(self.by_skill["Mirror Image"]))
        # Hydra cannot be targeted (research section 2): no creature of it is listed, and neither is the Familiar's
        self.assertEqual([], entries_of(self.by_skill["Hydra"]))
        untargetable = {int(s["entry"]) for s in summons if s["skill"] in ("Hydra", "Familiar")}
        listed = {e for r in self.rows for e in entries_of(r)}
        self.assertEqual(set(), listed & untargetable)


class Generator(unittest.TestCase):
    def render(self, module=MODULE):
        import generate_legendary_gem_pets as generator
        return generator.render(module)

    def sandbox(self, change):
        """A module folder with just the sheets the generator reads, the pet sheet changed by `change(rows)`."""
        root = Path(tempfile.mkdtemp(prefix="gempets-", dir=str(numbers.SCRATCH)))
        self.addCleanup(shutil.rmtree, root, True)
        for rel in ("data/d3/legendary_gems.csv", "data/d3/wizard_skills.csv", "data/d3/barbarian_skills.csv"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(MODULE / rel, root / rel)
        rows = read_pets()
        change(rows)
        with (root / "data/legendary_gem_pets.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(read_pets()[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return root

    def test_the_table_holds_one_row_per_skill_and_entry(self):
        numbers.SCRATCH.mkdir(parents=True, exist_ok=True)
        sql = self.render()
        self.assertIn("CREATE TABLE `dc_legendary_gem_pet`", sql)
        rows = re.findall(r"^\('(Unique_Gem_\d+_x1)','((?:[^']|'')*)',(NULL|\d+)\)[,;]$", sql, re.M)
        want = []
        for r in read_pets():
            for entry in entries_of(r) or [None]:
                want.append((r["gem_id"], r["skill"], "NULL" if entry is None else str(entry)))
        self.assertEqual(sorted(want), sorted(rows))
        self.assertEqual(5, len(rows))  # Hydra 1, Mirror Image 1, the three Ancients

    def test_an_empty_sheet_is_a_valid_list_with_no_pets(self):
        # The designer can drop every row: the gem then does nothing, as for a class with no pets (card q-1006-04)
        numbers.SCRATCH.mkdir(parents=True, exist_ok=True)
        sql = self.render(self.sandbox(lambda rows: rows.clear()))
        self.assertIn("CREATE TABLE `dc_legendary_gem_pet`", sql)
        self.assertNotIn("INSERT", sql)

    def test_a_row_it_cannot_stand_behind_is_refused(self):
        numbers.SCRATCH.mkdir(parents=True, exist_ok=True)
        bad = {
            "a skill the class does not have": lambda rows: rows[0].update(skill="Magic Mirror"),
            "a skill of another class": lambda rows: rows[0].update(**{"class": "Barbarian"}),
            "a gem that is not one of the 21": lambda rows: rows[0].update(gem_id="Unique_Gem_999_x1"),
            "no source": lambda rows: rows[0].update(source=""),
            "no evidence mark": lambda rows: rows[0].update(evidence=""),
            "a non-numeric entry": lambda rows: rows[0].update(creature_entries="abc"),
            "a skill twice": lambda rows: rows.append(dict(rows[0])),
        }
        for what, change in bad.items():
            with self.assertRaises(ValueError, msg=what):
                self.render(self.sandbox(change))

    def test_the_generated_files_are_the_render(self):
        sql = self.render()
        for path in (MODULE / "data/generated/legendary_gems_0003_pets.sql",
                     MODULE / "data/sql/db-world/updates/legendary_gems_0003_pets.sql"):
            self.assertEqual(sql, path.read_text(encoding="utf-8"), path.name)


class Math(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = rank25.Model()
        cls.rows = groupc.rows()
        cls.gem = enforcer_id()
        cls.planner = cls.model.d3p["Enforcer"]

    def base(self, rank):
        """The planner's own: 15% + 0.3% a rank, the text of the first effect."""
        return self.planner[1][0] + self.planner[2][0] * rank

    def drive(self, header_text, name):
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()] + pet_lines()
        cases = [[(self.gem, rank)] for rank in RANKS]
        cases += [[], [(self.gem, 60)], [(self.gem, 5), (self.gem, 60)], [(self.gem, 60), (self.gem, 5)], [("Unique_Gem_019_x1", 50)]]
        lines += ["case %d %s" % (len(w), " ".join("%s %d" % g for g in w)) for w in cases]
        done = run(lines, header_text, name)
        self.assertEqual(0, done.returncode, done.stderr)
        got = [[float(x) for x in line.split()] for line in done.stdout.splitlines()]
        return cases, got

    def want(self, worn):
        ranks = [rank for gem_id, rank in worn if gem_id == self.gem]
        best = max(ranks) if ranks else None
        if best is None:
            return [0, 0, 1, 1, 1, 1]
        damage = self.base(best)
        defence = self.model.r25("Enforcer")[0] if best >= 25 else 0.0
        return [damage, defence, 1 + damage / 100, 1, 1 - defence / 100, 1]

    def test_the_numbers_at_every_rank_are_the_planners(self):
        cases, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        want = [self.want(w) for w in cases]
        self.assertTrue(rank25.agrees(got, want), (got, want))
        by = {tuple(w): g for w, g in zip(map(tuple, cases), got)}
        self.assertEqual([15.0, 0.0], by[((self.gem, 0),)][:2])    # "Increase the damage of your pets by 15%"
        self.assertEqual([22.2, 0.0], by[((self.gem, 24),)][:2])   # 15 + 0.3 x 24: no 90% below rank 25
        self.assertEqual([22.5, 90.0], by[((self.gem, 25),)][:2])  # "(Requires Rank 25)": 90% less damage
        self.assertEqual([60.0, 90.0], by[((self.gem, 150),)][:2])  # "Max: 60% damage at Rank 150"
        # Unique Equipped: the higher rank counts, whatever the order
        self.assertEqual(by[((self.gem, 60),)], by[((self.gem, 5), (self.gem, 60))])
        self.assertEqual(by[((self.gem, 60),)], by[((self.gem, 60), (self.gem, 5))])
        # nothing worn, or another gem worn: every factor is 1
        self.assertEqual([0.0, 0.0, 1.0, 1.0, 1.0, 1.0], by[()])
        self.assertEqual([0.0, 0.0, 1.0, 1.0, 1.0, 1.0], by[(("Unique_Gem_019_x1", 50),)])
        # the pets get the factor and nothing else does
        got25 = by[((self.gem, 25),)]
        self.assertAlmostEqual(1.225, got25[2])
        self.assertEqual(1.0, got25[3])
        self.assertAlmostEqual(0.1, got25[4])
        self.assertEqual(1.0, got25[5])

    def test_the_list_decides_who_is_a_pet(self):
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()] + pet_lines()
        names = ["Hydra", "Mirror Image", "Call of the Ancients", "Familiar", "Teleport", "Magic Missile", "hydra", "Call of the"]
        lines += ["skill %s" % n for n in names] + ["entry %d" % e for e in (900100, 900101, 900102, 900110, 900111, 900112, 0)]
        done = run(lines)
        self.assertEqual(0, done.returncode, done.stderr)
        got = [int(x) for x in done.stdout.split()]
        self.assertEqual([1, 1, 1, 0, 0, 0, 0, 0] + [1, 1, 1, 1, 0, 0, 0], got)

    def test_a_class_with_no_pets_gets_nothing(self):
        # no row at all: no skill and no creature is a pet, whatever gem is worn
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()]
        lines += ["skill %s" % r["skill"] for r in read_pets()] + ["entry %d" % e for e in (900100, 900110)]
        done = run(lines)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([0] * (len(read_pets()) + 2), [int(x) for x in done.stdout.split()])

    def test_a_dropped_row_drops_that_pet_only(self):
        rows = [r for r in read_pets() if r["skill"] != "Mirror Image"]
        lines = [groupc.row_line(g, c) for g, c in self.rows.items()] + pet_lines(rows)
        lines += ["skill Mirror Image", "skill Hydra", "entry 900110", "entry 900100"]
        done = run(lines)
        self.assertEqual([0, 1, 0, 1], [int(x) for x in done.stdout.split()])

    def test_the_rank_25_number_is_the_sheets_first_and_a_missing_one_is_an_error(self):
        gem = self.gem
        lines = ["row %s 15 0.3 none none none none none none none none" % gem, "case 1 %s 30" % gem]
        self.assertNotEqual(0, run(lines).returncode)  # rank 25 asked for its number: an error, not a zero
        self.assertEqual(0, run(lines[:1] + ["case 1 %s 24" % gem]).returncode)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        mutants = {
            "damage_is_additive_in_the_wrong_unit": ("return pet ? 1.0 + powers.petDamagePct / 100.0 : 1.0;",
                                                   "return pet ? powers.petDamagePct / 100.0 : 1.0;"),
            "everyone_gets_the_damage": ("return pet ? 1.0 + powers.petDamagePct / 100.0 : 1.0;",
                                         "return 1.0 + powers.petDamagePct / 100.0;"),
            "defence_is_the_reduction_added": ("return targetablePet ? 1.0 - powers.petDefencePct / 100.0 : 1.0;",
                                               "return targetablePet ? 1.0 + powers.petDefencePct / 100.0 : 1.0;"),
            "everyone_gets_the_defence": ("return targetablePet ? 1.0 - powers.petDefencePct / 100.0 : 1.0;",
                                          "return 1.0 - powers.petDefencePct / 100.0;"),
            "gate_is_26": ("bool const rank25 = gem.rank >= Rank25;", "bool const rank25 = gem.rank > Rank25;"),
            "no_gate": ("bool const rank25 = gem.rank >= Rank25;", "bool const rank25 = true;"),
            "damage_ignores_rank": ("powers.petDamagePct = value;", "powers.petDamagePct = row->base;"),
            "defence_is_the_damage": ("powers.petDefencePct = Rank25Number(*row, 0);", "powers.petDefencePct = value;"),
            "skill_test_is_a_prefix": ("return pets.skills.count(skill) != 0;",
                                       "return !skill.empty() && std::any_of(pets.skills.begin(), pets.skills.end(), [&](std::string const& s) { return s.rfind(skill, 0) == 0 || skill.rfind(s, 0) == 0; });"),
            "every_entry_is_a_pet": ("return pets.entries.count(entry) != 0;", "return entry != 0;"),
        }
        for name, (old, new) in mutants.items():
            self.assertEqual(1, real.count(old), "the %s mutation no longer applies to the header" % name)
            mutated = real.replace(old, new)
            cases, got = self.drive(mutated, name)
            killed = not rank25.agrees(got, [self.want(w) for w in cases])
            if not killed:  # the list tests are the other half of the driver
                lines = [groupc.row_line(g, c) for g, c in self.rows.items()] + pet_lines()
                lines += ["skill %s" % n for n in ("Hydra", "Mirror Image", "Familiar", "Hyd", "Hydra Extra")]
                lines += ["entry %d" % e for e in (900110, 900111, 0)]
                done = run(lines, mutated, name)
                killed = [int(x) for x in done.stdout.split()] != [1, 1, 0, 0, 0, 1, 0, 0]
            self.assertTrue(killed, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
