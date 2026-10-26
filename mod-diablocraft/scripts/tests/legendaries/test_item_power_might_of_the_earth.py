"""Legendary rest, bead diablocraft-aa9tm: the Might of the Earth 6-piece bonus.

  * the current set text (reference/d3planner/data.json itemSets, the catalogue's source rule for set bonuses) words the bonus once:
    "Increase the damage of Earthquake, Avalanche, Leap, Ground Stomp, Ancient Spear and Seismic Slam by 37500%." (barbarian_sets.csv
    holds the same text since diablocraft-bmyff; test_d3_set_bonuses.py checks the whole sheet against data.json: its skills are checked here). The table
    (data/legendary_powers.csv) holds one `skill` `damage_increase_pct` row per named skill at pieces 6, its number and skills read out
    of that text, each skill a skill of barbarian_skills.csv, each a spell shell the hit resolves to (dc_spell_shells.h), the owner a
    six-piece set whose pieces drop;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table;
  * the production rules (src/combat/dc_item_power_math.h: CountSets, BonusActive, SkillFactor) are compiled and driven with the
    generated rows and the set's real pieces: the multiplier is 1 + 37500/100 on each of the six skills from the 6th piece and not
    before, two copies of a piece count once, a seventh skill and the Wastes set's own skills take nothing from it;
  * mutants fail the same driver (the rows lose a skill, the number is wrong, the level is wrong; the level test is off by one);
  * a source-text guard that the hit's legendary term reads the base skill name, so every rune of a skill gets the bonus (the code
    is compile-checked by syntax_check.sh; the in-game steps are in docs/test-diablocraft-aa9tm.md).
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
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_counter/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
# The newest full table (each legendary-rest bead takes the next number): it holds these rows beside the later beads'.
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))
FIRST = MODULE / "data/sql/db-world/updates/legendary_powers_0012_table.sql"   # this bead's own render, left as written once later ones exist
SET = "Might of the Earth"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


BONUS = re.compile(r"Increase the damage of ([\w' ,]+?) and ([\w' ]+?) by (\d+)%")


def sheet_text():
    """The 6-piece bonus as the set sheet words it: the same on all six pieces."""
    texts = {r["bonus_6pc"] for r in read_csv("data/d3/barbarian_sets.csv") if r["set_name"] == SET}
    assert len(texts) == 1, texts
    return texts.pop()


def current_text():
    """The 6-piece bonus in d3planner's data.json, the current text (the catalogue's source rule for set bonuses)."""
    found = {m[0] for m in re.finditer(r"Increase the damage of Earthquake, [^\"]*? by \d+%", (REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))}
    assert len(found) == 1, found
    return found.pop()


def sheet_numbers():
    """(the skills, the percent) the current set text names, read apart from the table; the sheet must name the same skills."""
    m = BONUS.match(current_text())
    assert m, current_text()
    skills = [s.strip() for s in m[1].split(",")] + [m[2]]
    old = BONUS.match(sheet_text())
    assert old and [s.strip() for s in old[1].split(",")] + [old[2]] == skills, sheet_text()
    return skills, float(m[3])


def pieces():
    return [r["d3_name"] for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET and r["pool_version"] == "yes"]


def generated_rows(text=None):
    text = GENERATED.read_text(encoding="utf-8") if text is None else text
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(text)]


def mine(text=None):
    """The 6-piece's rows (the 2- and 4-piece are test_item_power_might_of_the_earth_set.py's, diablocraft-tydva)."""
    return [r for r in generated_rows(text) if r[0] == SET and r[1] == 6]


class Table(unittest.TestCase):
    def test_the_sheet_names_six_skills_and_a_number(self):
        skills, pct = sheet_numbers()
        self.assertEqual(["Earthquake", "Avalanche", "Leap", "Ground Stomp", "Ancient Spear", "Seismic Slam"], skills)
        self.assertEqual(37500.0, pct)

    def test_one_skill_row_per_named_skill_at_six_pieces(self):
        skills, pct = sheet_numbers()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        want = {(SET, 6, "skill", s, "damage_increase_pct", pct, pct, *blank) for s in skills}
        self.assertEqual(want, set(mine()))
        self.assertEqual(6, len(mine()))

    def test_each_skill_is_a_skill_and_a_shell(self):
        skills, _ = sheet_numbers()
        sheet = {r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")}
        shells = (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8")
        for skill in skills:
            self.assertIn(skill, sheet)
            # a shell of the skill itself (rune ""), the one the hit resolves to when no rune is chosen
            self.assertRegex(shells, r'\{\d+, "%s", "", ' % re.escape(skill))

    def test_the_owner_is_a_six_piece_set_whose_pieces_drop(self):
        rows = [r for r in read_csv("data/d3/base_items.csv") if r["set_name"] == SET]
        self.assertEqual(6, len(rows))
        self.assertEqual(6, len(pieces()))
        self.assertTrue(all(r["pool_version"] == "yes" for r in rows))

    def test_every_row_has_its_source(self):
        for r in read_csv("data/legendary_powers.csv"):
            if r["owner"] == SET and r["pieces"] == "6":
                self.assertIn("barbarian_sets.csv", r["source"])
                self.assertIn("37500%", r["source"])
                self.assertIn("data.json", r["source"])
                self.assertTrue(r["note"])

    def test_the_migration_is_the_newest_full_table(self):
        found = sorted(p.name for p in (MODULE / "data/sql/db-world/updates").glob("legendary_powers_*_table.sql"))
        self.assertEqual(GENERATED.name, found[-1])
        self.assertGreaterEqual(found[-1], "legendary_powers_0012_table.sql")
        fixture = (MODULE / "scripts/fixture_mysql.sh").read_text(encoding="utf-8")
        self.assertIn(GENERATED.stem, fixture)
        self.assertIn("legendary_powers_0012_table", fixture)
        self.assertEqual(6, len(mine(FIRST.read_text(encoding="utf-8"))), "0012 is this bead's render: its six rows")


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itempower-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output)]: the expectations come from the set sheet and the rules of the game, not from the code."""
        skills, pct = sheet_numbers()
        factor = 1 + pct / 100
        names = pieces()
        out = [("\t".join(["row", *map(str, (r[0], r[1], r[2], r[3], r[4], "%g" % r[5], "%g" % r[6]))]), None) for r in rows]
        for n in range(0, 8):
            for skill in skills:
                out.append(("factor\t%s\tdamage_increase_pct\t1\t%s\t%d" % (skill, SET, n), "%g" % (factor if n >= 6 else 1)))
            out.append(("active\t%s\t6\t%d" % (SET, n), "1" if n >= 6 else "0"))
            # the 2-, 3- and 4-piece levels of this set have no row in this bead: never active
            out.append(("active\t%s\t4\t%d" % (SET, n), "0"))
        # the real pieces, counted: six distinct names are 6, two copies of one are one
        line = ["count", "6"] + [x for p in names for x in (SET, p)]
        out.append(("\t".join(line), "%s=6;" % SET))
        line = ["count", "7"] + [x for p in names + names[:1] for x in (SET, p)]
        out.append(("\t".join(line), "%s=6;" % SET))
        line = ["count", "6"] + [x for p in names[:5] + names[:1] for x in (SET, p)]
        out.append(("\t".join(line), "%s=5;" % SET))
        # a skill the bonus does not name, and the Wastes set's skills, take nothing from it
        for other in ("Rend", "Whirlwind", "Hammer of the Ancients", "Furious Charge", "Cleave"):
            out.append(("factor\t%s\tdamage_increase_pct\t1\t%s\t6" % (other, SET), "1"))
        out.append(("factor\tEarthquake\tattack_speed_pct\t1\t%s\t6" % SET, "1"))
        # beside another set, each its own multiplier
        out.append(("factor\tLeap\tdamage_increase_pct\t2\t%s\t6\tOther Set\t6" % SET, "%g" % factor))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            got = run.stdout.split("\n")[:-1]
            want = [w for _, w in cases if w is not None]
            return got, want
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_set_sheet(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 70)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(6, len(rows))
        dropped = rows[:-1]
        wrong_number = [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows]
        wrong_level = [(r[0], 4) + r[2:] for r in rows]
        wrong_stat = [r[:4] + ("attack_speed_pct",) + r[5:] for r in rows]
        mutants = {
            "a_skill_lost": (real, dropped),
            "the_number_halved": (real, wrong_number),
            "the_level_is_four": (real, wrong_level),
            "the_stat_is_speed": (real, wrong_stat),
            "level_needs_one_more": (real.replace("if (worn < pieces || !pieces)", "if (worn <= pieces || !pieces)"), rows),
            "a_bonus_needs_no_row": (real.replace("            if (row.owner == set && row.pieces == pieces)\n                return true;\n        return false;",
                                                  "            if (row.owner == set)\n                return true;\n        return true;"), rows),
            "duplicates_count": (real.replace("names[piece.set].insert(piece.name);",
                                              "names[piece.set].insert(piece.name + std::to_string(names[piece.set].size()));"), rows),
        }
        for name, (header, mutant_rows) in mutants.items():
            if name in ("level_needs_one_more", "a_bonus_needs_no_row", "duplicates_count"):
                self.assertNotEqual(real, header, name + " did not apply")
            with self.subTest(mutant=name):
                got, want = self.drive(header, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
