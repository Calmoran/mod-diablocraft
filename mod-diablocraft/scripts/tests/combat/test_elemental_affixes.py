#!/usr/bin/env python3
"""The armor "Elemental Damage" line is one of seven, the secondary "Elemental Resistance" line is one of six.

hcwjv part 7 (ruling 2026-10-11, decisions 9a2969fd): the amulet and bracers pool keeps its one `elemental` row; the roll turns it
into one of D3's seven (reference/d3planner/data_stats.js statGroups "elemental", every class rolls all seven), each one a percent
bonus to its own element on the stat sheet, which Combat already reads per element.

fjutd (ruling 2026-10-12): the pool keeps its one `resist` row per slot and bracket (same weight, same range); the roll turns it into
one of D3's six single resistances (resphy..reslit, statGroups "resist"), evenly, the way RollElemental does for the armor elemental
line. `resall` stays its own row. Each id maps to SingleResistance of its element on the stat sheet; `resist` itself maps to nothing,
so an old item's `resist` row is inert. (test_resist_affixes.py was merged in here: one cut of Mappings(), one compiled program.)

Checked here, for each of the two lines:
  * the ids, names and elements in dc_items_data.cpp are the reference's, in its group order;
  * ElementalAffixes / ResistAffixes, the roll and Mappings() cut out of dc_items_data.cpp and compiled once: each id maps to its stat
    and element, the pool id itself maps to nothing, the other line and `resall` are untouched, and the roll reaches every id;
  * the roll, the load, and the Mystic's pool id and expansion use the list (text, with mutants);
  * the pool still has its one row per bracket, and the Mystic's exclusion group holds the ids (test_mystic_enchant.py checks the rest).
It does not run the server, the AIO tooltip or a client; the tooltip and Mystic window names are the UI lane's bead (z9ya2).
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
ENCHANT = MODULE / "src/items/dc_enchant_rule.h"
REFERENCE = ROOT / "reference/d3planner/data_stats.js"
POOLS = MODULE / "data/d3/affix_pools.csv"
ELEMENT = {"phy": "Physical", "fir": "Fire", "col": "Cold", "psn": "Poison", "arc": "Arcane", "lit": "Lightning", "hol": "Holy"}


def reference():
    text = REFERENCE.read_text(encoding="utf-8")
    group = re.search(r'"elemental": \[([^\]]*)\]', text).group(1)
    ids = re.findall(r'"(\w+)"', group)
    names = {i: re.search(rf'^\s*{i}: {{name: "([^"]+)"', text, re.M).group(1) for i in ids}
    return [(i, names[i], ELEMENT[i[3:]]) for i in ids]


def resist_reference():
    """(id, name, element) of the six, in the reference's own group order."""
    text = REFERENCE.read_text(encoding="utf-8")
    ids = re.findall(r'"(\w+)"', re.search(r'"resist": \[([^\]]*)\]', text).group(1))
    out = []
    for i in ids:
        line = re.search(rf'^\s*{i}: {{(.*)}},?$', text, re.M).group(1)
        name = re.search(r'format: "\+%d ([^"]+)"', line) or re.search(r'name: "([^"]+)"', line)
        out.append((i, name.group(1), re.search(r'id: "Resistance#(\w+)"', line).group(1)))
    return out


def items_text():
    """The items code and its internal header: the one text the wiring checks and their mutants run on."""
    return items_source.source() + "\n" + items_source.header()


def cpp_list(source):
    block = items_source.table("ElementalAffixes", source)
    return re.findall(r'\{"(\w+)", "([^"]+)", Element::(\w+)\}', block)


def resist_cpp_list(source):
    block = items_source.table("ResistAffixes", source)
    return re.findall(r'\{"(\w+)", "([^"]+)", Element::(\w+)\}', block)


def program(source):
    """One program for both lines: the cut of dc_items_data.cpp with every assert the two files made."""
    start = source.index("std::mt19937_64& Engine()")
    body = source[start:source.index("std::vector<std::string> Split(", start)] + items_source.sheet(source)
    return ('#include "dc_common.h"\n#include <cassert>\n#include <iterator>\n#include <random>\n#include <set>\n'
            '#include <string>\n#include <unordered_map>\nnamespace DC::Items {\n' + body + "}\n"
            "using namespace DC; using namespace DC::Items;\n"
            "int main() {\n"
            "  auto const& map = Mappings();\n"
            "  assert(!map.count(\"elemental\"));   // the pool id is not a stat; the rolled id is\n"
            + "".join(f'  assert(map.at("{i}").stat == Stat::ElementalDamage && map.at("{i}").element == Element::{e});\n'
                      for i, _, e in reference()) +
            "  assert(map.at(\"resall\").stat == Stat::AllResistance);   // Resistance to All Elements is its own row\n"
            "  assert(ElementalAffixOf(\"dmgfir\") && !ElementalAffixOf(\"elemental\") && !ElementalAffixOf(\"wpnfir\"));\n"
            "  std::set<std::string> seen;\n"
            "  for (int n = 0; n < 2000; ++n) seen.insert(RollElemental().id);\n"
            "  assert(seen.size() == 7);   // every class, all seven\n"
            "  assert(!map.count(\"resist\"));   // the pool id is not a stat; the rolled id is\n"
            + "".join(f'  assert(map.at("{i}").stat == Stat::SingleResistance && map.at("{i}").element == Element::{e}'
                      f' && map.at("{i}").bucket == Bucket::Flat);\n' for i, _, e in resist_reference()) +
            "  assert(map.at(\"dmgfir\").stat == Stat::ElementalDamage);   // and so is the elemental line\n"
            "  assert(ResistAffixOf(\"resfir\") && !ResistAffixOf(\"resist\") && !ResistAffixOf(\"resall\") && !ResistAffixOf(\"dmgfir\"));\n"
            "  assert(!ElementalAffixOf(\"resfir\"));\n"
            "  std::set<std::string> seenResist;\n"
            "  for (int n = 0; n < 2000; ++n) seenResist.insert(RollResist().id);\n"
            "  assert(seenResist.size() == 6);   // all six, evenly drawn from the list\n"
            "  return 0;\n}\n")


class ElementalAffixes(unittest.TestCase):
    def test_the_list_is_the_references(self):
        want = reference()
        self.assertEqual(len(want), 7)
        self.assertEqual(cpp_list(items_text()), want)

    def test_the_pool_keeps_one_row_and_the_mystic_groups_the_seven(self):
        with POOLS.open(encoding="utf-8", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["affix_id"] == "elemental"]
        self.assertEqual(sorted((r["slot"], r["item_level_bracket"]) for r in rows),
                         sorted((s, b) for s in ("neck", "wrists") for b in ("rare", "legendary", "ancient", "primal")))
        with POOLS.open(encoding="utf-8", newline="") as handle:
            self.assertFalse([r for r in csv.DictReader(handle) if r["affix_id"].startswith("dmg")])
        members = dict(re.findall(r'\{"(\w+)", "(\w+)"\}', ENCHANT.read_text(encoding="utf-8")))
        self.assertEqual({i for i, g in members.items() if g == "elemental"}, {i for i, _, _ in reference()})

    def test_the_roll_load_and_mystic_use_the_list(self):
        text = items_text()
        self.assertEqual(problems(text), [])
        for old, new in MUTATIONS:
            with self.subTest(mutation=old):
                self.assertEqual(text.count(old), 1, old)
                self.assertNotEqual(problems(text.replace(old, new)), [], f"survived: {old!r}")


class ResistAffixes(unittest.TestCase):
    def test_the_list_is_the_references(self):
        want = resist_reference()
        self.assertEqual(len(want), 6)
        self.assertEqual(resist_cpp_list(items_text()), want)

    def test_the_pool_keeps_its_one_row_and_the_mystic_groups_the_six(self):
        with POOLS.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        resist = [r for r in rows if r["affix_id"] == "resist"]
        slots = {r["slot"] for r in resist}
        self.assertTrue(slots)
        self.assertEqual(sorted((r["slot"], r["item_level_bracket"]) for r in resist),
                         sorted((s, b) for s in slots for b in ("rare", "legendary", "ancient", "primal")))
        self.assertTrue(all(r["kind"] == "secondary" for r in resist))
        self.assertFalse([r for r in rows if r["affix_id"] in {i for i, _, _ in resist_reference()}])
        members = dict(re.findall(r'\{"(\w+)", "(\w+)"\}', ENCHANT.read_text(encoding="utf-8")))
        self.assertEqual({i for i, g in members.items() if g == "resistany"},
                         {"resall", "resist"} | {i for i, _, _ in resist_reference()})

    def test_the_roll_load_and_mystic_use_the_list(self):
        text = items_text()
        self.assertEqual(resist_problems(text), [])
        for old, new in RESIST_MUTATIONS:
            with self.subTest(mutation=old):
                self.assertEqual(text.count(old), 1, old)
                self.assertNotEqual(resist_problems(text.replace(old, new)), [], f"survived: {old!r}")


class CutCompiles(unittest.TestCase):
    def test_the_cut_compiles_and_maps_and_rolls_both_lines(self):
        source = items_text()

        def run(text):
            try:
                binary = harness_env.build([MODULE / "tests/elemental_affixes/program.cpp"], flags=["-std=c++20", "-UNDEBUG"],
                                           files={"program.h": program(text)}, includes=[MODULE / "src/common"])
            except harness_env.BuildError as error:
                return "build: " + error.stderr[-1500:]
            return harness_env.run([str(binary)]).returncode

        self.assertEqual(run(source), 0)
        for old, new in (("table[affix.id] = {Stat::ElementalDamage, Bucket::Flat, affix.element};",
                          "table[affix.id] = {Stat::ElementalDamage, Bucket::Flat, Element::Fire};"),
                         ("table[affix.id] = {Stat::ElementalDamage, Bucket::Flat, affix.element};", ""),
                         ("std::size(ElementalAffixes) - 1)(Engine())", "std::size(ElementalAffixes) - 2)(Engine())"),
                         ('{"dmgcol", "Cold Damage Increase", Element::Cold}', '{"dmgcol", "Cold Damage Increase", Element::Fire}'),
                         ("table[affix.id] = {Stat::SingleResistance, Bucket::Flat, affix.element};",
                          "table[affix.id] = {Stat::SingleResistance, Bucket::Flat, Element::Fire};"),
                         ("table[affix.id] = {Stat::SingleResistance, Bucket::Flat, affix.element};", ""),
                         ("table[affix.id] = {Stat::SingleResistance, Bucket::Flat, affix.element};",
                          "table[affix.id] = {Stat::AllResistance, Bucket::Flat, affix.element};"),
                         ("std::size(ResistAffixes) - 1)(Engine())", "std::size(ResistAffixes) - 2)(Engine())"),
                         ('{"rescol", "Cold Resistance", Element::Cold}', '{"rescol", "Cold Resistance", Element::Fire}'),
                         ('{"resall", {Stat::AllResistance}},', '{"resall", {Stat::AllResistance}}, {"resist", {Stat::SingleResistance}},')):
            with self.subTest(mutation=old):
                self.assertEqual(source.count(old), 1, old)
                self.assertNotEqual(run(source.replace(old, new)), 0, f"survived: {old!r}")


def problems(text):
    out = []
    roll = text[text.index("else if (entry.affixId == ELEMENTAL_POOL_ID)"):text.index("else if (entry.affixId == RESIST_POOL_ID)")]
    if "ElementalAffix const& affix = RollElemental();" not in roll or "affix.id, affix.name, valueOf(entry)" not in roll:
        out.append("the roll does not turn the pool row into one of the seven")
    if "entry.min, entry.max, kind, true, false" not in roll:
        out.append("the rolled line is not a percent")
    load = text[text.index("// Display names live in the world-side pool"):text.index("    return instance;\n}")]
    if "if (ElementalAffix const* element = ElementalAffixOf(affix.affixId))" not in load or "affix.name = element->name;" not in load:
        out.append("a stored line is not named on load")
    mystic = text[text.index("struct MysticCtx"):text.index("void Shuffle(")]
    if "if (ElementalAffixOf(id))\n            return ELEMENTAL_POOL_ID;" not in mystic:
        out.append("the Mystic does not know a line's pool row")
    if "if (c.id == ELEMENTAL_POOL_ID)" not in mystic or "for (ElementalAffix const& affix : ElementalAffixes)" not in mystic:
        out.append("the Mystic does not offer the seven")
    if 'constexpr char const* ELEMENTAL_POOL_ID = "elemental";' not in text:
        out.append("the pool id is not the pool's")
    return out


MUTATIONS = (
    ("ElementalAffix const& affix = RollElemental();", "ElementalAffix const& affix = ElementalAffixes[0];"),
    ("affix.id, affix.name, valueOf(entry),", "entry.affixId, entry.name, valueOf(entry),"),
    ("                              entry.min, entry.max, kind, true, false});\n        }\n        else if (entry.affixId == RESIST_POOL_ID)",
     "                              entry.min, entry.max, kind, false, false});\n        }\n        else if (entry.affixId == RESIST_POOL_ID)"),
    ("            affix.name = element->name;\n", ""),
    ("        if (ElementalAffixOf(id))\n            return ELEMENTAL_POOL_ID;\n", ""),
    ("        if (c.id == ELEMENTAL_POOL_ID)\n", "        if (false)\n"),
    ('constexpr char const* ELEMENTAL_POOL_ID = "elemental";', 'constexpr char const* ELEMENTAL_POOL_ID = "dmgelemental";'),
)


def resist_problems(text):
    out = []
    roll = text[text.index("else if (entry.affixId == RESIST_POOL_ID)"):text.index("else if (auto group = groups.find(entry.affixId); group != groups.end())\n        {\n            auto const& choices")]
    if "ElementalAffix const& pick = RollResist();" not in roll or "pick.id, pick.name, valueOf(entry)" not in roll:
        out.append("the roll does not turn the pool row into one of the six")
    if "entry.min, entry.max, kind, entry.isPercent, false" not in roll:
        out.append("the rolled line is not flat like the pool's row")
    load = text[text.index("// Display names live in the world-side pool"):text.index("    return instance;\n}")]
    if "if (ElementalAffix const* resist = ResistAffixOf(affix.affixId))" not in load or "affix.name = resist->name;" not in load:
        out.append("a stored line is not named on load")
    mystic = text[text.index("struct MysticCtx"):text.index("void Shuffle(")]
    if "if (ResistAffixOf(id))\n            return RESIST_POOL_ID;" not in mystic:
        out.append("the Mystic does not know a line's pool row")
    if "if (c.id == RESIST_POOL_ID)" not in mystic or "for (ElementalAffix const& affix : ResistAffixes)" not in mystic:
        out.append("the Mystic does not offer the six")
    if 'constexpr char const* RESIST_POOL_ID = "resist";' not in text:
        out.append("the pool id is not the pool's")
    return out


RESIST_MUTATIONS = (
    ("ElementalAffix const& pick = RollResist();", "ElementalAffix const& pick = ResistAffixes[0];"),
    ("pick.id, pick.name, valueOf(entry),", "entry.affixId, entry.name, valueOf(entry),"),
    ("                              entry.min, entry.max, kind, entry.isPercent, false});\n        }\n        else if (auto group",
     "                              entry.min, entry.max, kind, true, false});\n        }\n        else if (auto group"),
    ("            affix.name = resist->name;\n", ""),
    ("        if (ResistAffixOf(id))\n            return RESIST_POOL_ID;\n", ""),
    ("        if (c.id == RESIST_POOL_ID)\n", "        if (false)\n"),
    ('constexpr char const* RESIST_POOL_ID = "resist";', 'constexpr char const* RESIST_POOL_ID = "resistsingle";'),
)


if __name__ == "__main__":
    unittest.main(verbosity=2)
