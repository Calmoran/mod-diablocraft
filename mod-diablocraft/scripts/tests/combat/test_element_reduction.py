#!/usr/bin/env python3
"""diablocraft-508ry: damage taken from one element reduced by gear (D3's Damage_Type_Percent_Reduction#<element>).

Ice Climbers' "Reduces damage from Cold attacks by X%" (reference/d3planner/item_feet.js:84, colddef 7-10) needs a stat.
D3 keeps it as one attribute keyed by element, so Torment's is one stat keyed by element too: Stat::ElementReduction.

Checked here:
  * tests/element_reduction/harness.cpp on the real dc_common.cpp: the reduction multiplies that element's
    damageTaken and nothing else's, two sources multiply, Validate bounds it, the sheet save keeps it and a
    version-6 save still loads (with mutants of dc_common.cpp);
  * Mappings() cut out of dc_items_data.cpp and compiled: "colddef" is ElementReduction of Cold, the reference's own id;
  * both damage-taken paths read damageTaken (FactorOf), the DCSHEET block sends def0..def6, Toughness and
    `.dc stats` read the reduction (text, with mutants).
It does not run the server or the addon: drawing the def keys on the sheet is the UI lane's.
"""
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
SRC = MODULE / "src"
COMMON = SRC / "common/dc_common.cpp"
HARNESS = MODULE / "tests/element_reduction/harness.cpp"
INVENTORY = SRC / "items/dc_inventory.cpp"
STATS = SRC / "stats/dc_stats.cpp"
SUMMARY = SRC / "stats/dc_sheet_summary.h"   # Toughness: the formula the player and a follower share
COMBAT = SRC / "combat/dc_combat.cpp"
REFERENCE = ROOT / "reference/d3planner"


def run_harness(common_text):
    """0 when every check in the harness holds; anything else is a failure or a build error."""
    try:
        binary = harness_env.build([HARNESS, MODULE / "tests/element_reduction/common_main.cpp"], flags=["-std=c++17", "-O1"],
                                   files={"common_source.h": common_text}, includes=[SRC, SRC / "common"])
    except harness_env.BuildError as error:
        return "build: " + error.stderr[-1500:]
    done = harness_env.run([str(binary)], capture_output=True, text=True)
    return done.returncode if done.returncode else 0


def mapping_program(source):
    body = items_source.stat_map(source)
    head = items_source.lists(source)
    return ('#include "dc_common.h"\n#include <cassert>\n#include <string>\n#include <unordered_map>\n'
            "namespace DC::Items {\n" + head + body + "}\nusing namespace DC; using namespace DC::Items;\n"
            "int main() {\n"
            '  auto const& colddef = Mappings().at("colddef");\n'
            "  assert(colddef.stat == Stat::ElementReduction && colddef.element == Element::Cold);\n"
            "  assert(colddef.bucket == Bucket::Flat);\n"
            "  return 0;\n}\n")


SOURCE_GUARDS = [
    (INVENTORY, "block.Add(ReductionKeys[element], sheet.elementReduction[element]);"),
    (INVENTORY, 'char const* ReductionKeys[] = {"def0", "def1", "def2", "def3", "def4", "def5", "def6"};'),
    (SUMMARY, "* specific * elementFactor;"),
    (SUMMARY, "elementFactor *= 1 - sheet.elementReduction[Index(element)] / 100 / 6;"),
    (STATS, '<< "% Reduction=" << s.elementReduction[element]'),
    (COMBAT, "return sheet.damageTaken[Index(ElementEnum(ElementOfSchool(schoolMask)))];"),
]


class ElementReduction(unittest.TestCase):
    def test_the_reference_has_colddef_as_damage_type_reduction(self):
        stats = (REFERENCE / "data_stats.js").read_text(encoding="utf-8")
        self.assertRegex(stats, r'colddef: \{name: "Cold Damage Reduction", .*id: "Damage_Type_Percent_Reduction#Cold"')
        self.assertIn("colddef: {min: 7, max: 10}", (REFERENCE / "item_feet.js").read_text(encoding="utf-8"))
        # The reference has no other element's reduction row; the stat still holds all seven.
        self.assertEqual(re.findall(r"Damage_Type_Percent_Reduction#(\w+)", stats), ["Cold"])

    def test_the_sheet_maths(self):
        text = COMMON.read_text(encoding="utf-8")
        self.assertEqual(run_harness(text), 0)
        mutants = [
            ("            elementTaken[element];", "            1.0;"),
            ("elementTaken[Index(c.element)] *= 1 - c.value / 100;", "elementTaken[Index(c.element)] -= c.value / 100;"),
            ("elementTaken[Index(c.element)] *= 1 - c.value / 100;", "elementTaken[Index(Element::Cold)] *= 1 - c.value / 100;"),
            ("sheet.elementReduction[element] = (1 - elementTaken[element]) * 100;", ""),
            ("Require(c.value >= -100 && c.value <= 100, \"Element reduction", "Require(c.value >= -100, \"Element reduction"),
            ("&& c.stat != Stat::SingleResistance && c.stat != Stat::ElementReduction)", "&& c.stat != Stat::SingleResistance)"),
            ("        for (double& value : sheet.elementReduction) Read(in, value);", "        ;"),
            ("        : version == 6 ? Index(Stat::ElementReduction)\n", ""),
        ]
        for old, new in mutants:
            with self.subTest(mutation=old):
                self.assertEqual(text.count(old), 1, old)
                self.assertNotEqual(run_harness(text.replace(old, new)), 0, f"survived: {old!r}")

    def test_colddef_maps_to_cold(self):
        source = items_source.source()

        def run(text):
            try:
                binary = harness_env.build([MODULE / "tests/element_reduction/mapping_program.cpp"], flags=["-std=c++20", "-UNDEBUG"],
                                           files={"program.h": mapping_program(text)}, includes=[SRC / "common"])
            except harness_env.BuildError as error:
                return "build: " + error.stderr[-1500:]
            return harness_env.run([str(binary)]).returncode

        self.assertEqual(run(source), 0)
        old = '{"colddef", {Stat::ElementReduction, Bucket::Flat, Element::Cold}}'
        for new in ('{"colddef", {Stat::ElementReduction, Bucket::Flat, Element::Fire}}',
                    '{"colddef", {Stat::SpecificReduction}}', '{"coldef", {Stat::ElementReduction, Bucket::Flat, Element::Cold}}'):
            with self.subTest(mutation=new):
                self.assertEqual(source.count(old), 1)
                self.assertNotEqual(run(source.replace(old, new)), 0, f"survived: {new!r}")

    def test_the_sheet_and_both_paths_read_it(self):
        for path, line in SOURCE_GUARDS:
            with self.subTest(path=path.name, line=line):
                self.assertEqual(path.read_text(encoding="utf-8").count(line), 1)
        # Both damage-taken paths take the factor from FactorOf, so the reduction folded into damageTaken reaches both.
        combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        for name in ("std::optional<double> DamageTakenFactor(", "std::optional<double> Mitigate("):
            body = combat[combat.index(name):]
            body = body[:body.index("\n    }\n")]
            self.assertIn("FactorOf(", body, name)


if __name__ == "__main__":
    unittest.main()
