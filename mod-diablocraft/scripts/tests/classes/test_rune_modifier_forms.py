"""Rune modifier forms (diablocraft-kx9t5): a rune sheet's modified_cost_cooldown_damage names its class's resource.

  "Cost reduced to N <resource>", "<resource> cost removed" and "Cooldown reduced|increased to N seconds" are read by
  generate_spells.py (RUNE_MODIFIERS) and by dc_combat.cpp (ParseRuneModifiers) for every resource of
  data/d3/class_resources.csv, not for Fury alone, so the Monk's Spirit rows parse and anything else stays an error:
  * the clauses of the barbarian, wizard and monk rune sheets all parse, and the Barbarian's and Wizard's give the kinds
    they gave before (their records regenerate byte for byte; checked by regenerating and comparing, see the bead);
  * the forms are driven with every resource name of a live class the CSV holds (cross-source: the names come from the sheet, not the
    generator), a name the CSV does not hold and an increased cost are errors;
  * the C++ side builds its cost forms from the generated registry's names and takes `increased`;
  * mutants of the generator's forms fail the same driver.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as gs

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def resource_names():
    """The resources of the classes that are live (class_map.csv): the ones a rune sheet can name."""
    live = {r["d3_class"].strip() for r in read_csv("data/d3/class_map.csv")}
    return sorted({r["d3_name"] for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] in live})


def sheet_clauses(stem):
    return [c.strip() for r in read_csv("data/d3/%s_runes.csv" % stem)
            for c in r.get("modified_cost_cooldown_damage", "").split("|") if c.strip()]


def forms_of(source):
    """RUNE_MODIFIERS as `source` (the generator's text, possibly mutated) defines it."""
    start = source.index("RESOURCE_NAMES = ")
    block = source[start:source.index("def rune_modifiers", start)]
    scope = {"re": re, "RESOURCES": gs.RESOURCES}
    exec(block, scope)  # noqa: S102 - the repo's own generator text
    return scope["RUNE_MODIFIERS"]


def parse(forms, clause):
    for pattern, kind in forms:
        match = pattern.match(clause)
        if match:
            return kind, float(match.group(1)) if match.groups() else 0.0
    return None


class Forms(unittest.TestCase):
    def test_every_sheet_clause_parses(self):
        for stem in ("barbarian", "wizard", "monk", "necromancer", "crusader"):
            for clause in sheet_clauses(stem):
                with self.subTest(stem=stem, clause=clause):
                    gs.rune_modifiers(clause)

    def test_the_barbarians_and_the_wizards_kinds_are_unchanged(self):
        kinds = lambda stem: sorted(next(iter(gs.rune_modifiers(c))) for c in sheet_clauses(stem)  # noqa: E731
                                    if not c.endswith("damage"))
        self.assertEqual(["cooldown", "cooldown", "cost", "no_cost"], kinds("barbarian"))
        self.assertEqual(["cooldown", "cooldown"], kinds("wizard"))

    def test_the_monks_forms(self):
        self.assertEqual({"cost": 25.0}, gs.rune_modifiers("Cost reduced to 25 Spirit"))
        self.assertEqual({"no_cost": 0.0}, gs.rune_modifiers("Spirit cost removed"))
        self.assertEqual({"cooldown": 12.0}, gs.rune_modifiers("Cooldown increased to 12 seconds"))
        self.assertEqual({"cooldown": 1.0}, gs.rune_modifiers("Cooldown increased to 1 second"))
        self.assertEqual({"cost": 26.0, "cooldown": 30.0}, gs.rune_modifiers("Cost reduced to 26 Spirit | Cooldown reduced to 30 seconds"))

    def test_the_necromancers_forms(self):
        # Life costs and "changed to" (PM ruling on diablocraft-im7mr.5); the C++ mirror reads the Barbarian's runes only
        self.assertEqual({"health_cost": 10.0, "damage": 650.0}, gs.rune_modifiers("650% weapon damage | Health cost 10%"))
        self.assertEqual({"no_health_cost": 0.0}, gs.rune_modifiers("Health cost removed"))
        self.assertEqual({"health_cost_doubled": 0.0}, gs.rune_modifiers("Health cost doubled"))
        self.assertEqual({"cooldown": 45.0}, gs.rune_modifiers("Cooldown changed to 45 seconds"))

    def test_the_crusaders_forms(self):
        # Heaven's Fury - Fires of Heaven (PM ruling on diablocraft-qulab): a cost on a skill that had none, its cooldown gone
        self.assertEqual({"cost": 40.0, "no_cooldown": 0.0, "damage": 960.0},
                         gs.rune_modifiers("960% weapon damage | Cost changed to 40 Wrath | Cooldown removed"))
        self.assertEqual({"cost": 40.0}, gs.rune_modifiers("Cost changed to 40 Wrath"))
        self.assertEqual({"no_cooldown": 0.0}, gs.rune_modifiers("Cooldown removed"))
        clauses = sheet_clauses("crusader")
        self.assertIn("Cost changed to 40 Wrath", clauses)
        self.assertIn("Cooldown removed", clauses)

    def test_every_resource_of_the_sheet_works_in_both_forms(self):
        names = resource_names()
        self.assertIn("Spirit", names)
        self.assertIn("Fury", names)
        self.assertIn("Arcane Power", names)
        for name in names:
            with self.subTest(name=name):
                self.assertEqual({"cost": 5.5}, gs.rune_modifiers("Cost reduced to 5.5 %s" % name))
                self.assertEqual({"no_cost": 0.0}, gs.rune_modifiers("%s cost removed" % name))
                self.assertEqual({"cost": 5.5}, gs.rune_modifiers("Cost changed to 5.5 %s" % name))

    def test_anything_else_stays_an_error(self):
        for clause in ("Cost reduced to 25 Mana of Doom", "Cost reduced to 25 Furies", "Cost reduced to 25", "Cost removed",
                       "Rage cost removed", "Cost increased to 25 Fury", "Cooldown increased by 5 seconds", "Health cost 10",
                       "Health cost tripled", "Spirit costs removed", "Cost reduced to 25 Fury Spirit",
                       "Cost changed to 40", "Cost changed to 40 Mana of Doom", "Cooldown removed entirely", "Cooldowns removed",
                       "Wrath cooldown removed"):
            with self.subTest(clause=clause), self.assertRaises(SystemExit):
                gs.rune_modifiers(clause)


class Mutants(unittest.TestCase):
    def test_the_driver_kills_mutants_of_the_forms(self):
        source = Path(gs.__file__).read_text(encoding="utf-8")
        real = forms_of(source)
        cases = ["Cost reduced to 25 Spirit", "Spirit cost removed", "Cost reduced to 25 Fury", "Fury cost removed",
                 "Cooldown increased to 12 seconds", "Cooldown reduced to 12 seconds", "Cost reduced to 25 Mana of Doom",
                 "Cost increased to 25 Fury", "Cooldown increased by 5 seconds", "Cost reduced to 25", "Cooldown changed to 5 seconds",
                 "Cooldown lowered to 5 seconds", "Cost changed to 40 Wrath", "Cooldown removed", "Cost changed to 40 Mana of Doom"]
        want = [parse(real, c) for c in cases]
        self.assertEqual([("cost", 25.0), ("no_cost", 0.0), ("cost", 25.0), ("no_cost", 0.0), ("cooldown", 12.0), ("cooldown", 12.0),
                          None, None, None, None, ("cooldown", 5.0), None, ("cost", 40.0), ("no_cooldown", 0.0), None], want)
        mutants = {
            "fury_only_cost": source.replace('(?:%s)$" % RESOURCE_NAMES), "cost")', 'Fury$"), "cost")', 1),
            "fury_only_removed": source.replace('r"^(?:%s) cost removed$" % RESOURCE_NAMES', 'r"^Fury cost removed$"', 1),
            "no_increased": source.replace("(?:reduced|increased|changed)", "(?:reduced|changed)", 1),
            "no_changed": source.replace("(?:reduced|increased|changed)", "(?:reduced|increased)", 1),
            "any_word_is_a_resource": source.replace("RESOURCE_NAMES = \"|\".join(", "RESOURCE_NAMES = \".+\" or \"|\".join(", 1),
            "reduced_or_anything": source.replace("(?:reduced|increased|changed)", "[a-z]+", 1),
            "a_cost_that_is_increased": source.replace("Cost reduced to", "Cost (?:reduced|increased) to", 1),
            "no_cost_changed": source.replace('r"^Cost changed to', 'r"^Cost altered to', 1),
            "cost_changed_any_word": source.replace('r"^Cost changed to ([0-9]+(?:\\.[0-9]+)?) (?:%s)$" % RESOURCE_NAMES',
                                                    'r"^Cost changed to ([0-9]+(?:\\.[0-9]+)?) .+$"', 1),
            "no_cooldown_removed": source.replace('(re.compile(r"^Cooldown removed$"), "no_cooldown"),', '', 1),
            "cooldown_removed_is_a_cost": source.replace('(re.compile(r"^Cooldown removed$"), "no_cooldown"),',
                                                         '(re.compile(r"^Cooldown removed$"), "no_cost"),', 1),
        }
        for name, text in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(source, text, name + " did not apply")
                self.assertNotEqual(want, [parse(forms_of(text), c) for c in cases], name + " survived")


class Cpp(unittest.TestCase):
    """dc_combat.cpp cannot be compiled alone here (syntax_check.sh compiles it); these pin the lines the forms live in."""
    cpp = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])

    def test_the_cost_forms_name_the_registry_resources(self):
        self.assertIn("for (DC::Resources::Data::Row const& row : DC::Resources::Data::Rows)", self.cpp)
        self.assertIn("names += (names.empty() ? \"\" : \"|\") + std::string(row.d3Name);", self.cpp)
        self.assertIn('std::regex("^Cost reduced to ([0-9]+(?:\\\\.[0-9]+)?) (?:" + resourceNames + ")$"),', self.cpp)
        self.assertIn('std::regex("^(?:" + resourceNames + ") cost removed$"),', self.cpp)
        self.assertNotIn("Fury$)", self.cpp)
        self.assertNotIn("R\"(^Fury cost removed$)\"", self.cpp)

    def test_the_crusaders_forms_are_mirrored(self):
        self.assertIn('std::regex("^Cost changed to ([0-9]+(?:\\\\.[0-9]+)?) (?:" + resourceNames + ")$"),', self.cpp)
        self.assertIn('std::regex(R"(^Cooldown removed$)"),', self.cpp)
        self.assertIn("std::regex_match(clause, match, forms[6]) ||", self.cpp)
        self.assertIn("std::regex_match(clause, forms[7])", self.cpp)

    def test_the_cooldown_form_takes_increased(self):
        self.assertIn('std::regex(R"(^Cooldown (?:reduced|increased) to ([0-9]+(?:\\.[0-9]+)?) seconds?$)"),', self.cpp)

    def test_the_registry_holds_every_class_the_sheets_do(self):
        text = (SRC / "classes/dc_resource_data.h").read_text(encoding="utf-8")
        for row in read_csv("data/d3/class_map.csv"):
            primary = next(r for r in read_csv("data/d3/class_resources.csv") if r["d3_class"] == row["d3_class"] and r["role"] == "primary")
            self.assertIn('"%s"' % primary["d3_name"], text, row["d3_class"])


if __name__ == "__main__":
    unittest.main()
