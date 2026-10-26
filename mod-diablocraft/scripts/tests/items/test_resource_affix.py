#!/usr/bin/env python3
"""diablocraft-4ruv4: the `resource` preset (Stone of Jordan, Lidless Wall) rolls the wearer's class resource.

D3's `resource` is "Maximum <the wearer's resource>", one range per class (reference/d3planner/item_finger.js:714-720,
item_offhand.js:94-100). The item carries one item_preset_ranges.csv row per class under the stat's own code, and the
roller takes the row named after the roll class's resource (src/items/dc_items_roll.cpp through dc_resource_affix_rule.h),
as `mainstat` takes the class's main stat.

1. The rule header, compiled as it is with the generated class resource registry (dc_resource_data.h), is fed the rows
   parsed out of the generated items_0054 migration: for every live class (class_map.csv), item and bracket it picks
   the code d3planner gives that class (data_stats.js `class:` on the Maximum Resource stats), and that row's range is
   d3planner's (the item's own numbers, or slots.js statLimits legendary for the item type's affix list). A class with
   no row gets nothing. A mutant that takes the first Maximum row whatever the class goes red.
2. The wiring, pinned as text: StageRoll gathers the roll class's resource names primary first, then second, and puts
   the rule's answer in place of the preset before planning.
"""
import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
from test_class_parity import SRC, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

MODULE = SRC.parent
REF = MODULE.parent / "reference/d3planner"
D3 = MODULE / "data/d3"
RULE = (SRC / "items/dc_resource_affix_rule.h").read_text(encoding="utf-8")
DATA = SRC / "classes/dc_resource_data.h"
ITEMS = items_source.source()
MIGRATION = MODULE / "data/sql/db-world/updates/items_0054_item_preset_ranges_mana.sql"
ITEMS_WITH_RESOURCE = {"P69_Unique_Ring_019": ("item_finger.js", 100351), "Unique_Shield_008_x1": ("item_offhand.js", 100957)}
BRACKETS = ("legendary", "ancient", "primal")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def class_of_maximum():
    """data_stats.js: Maximum Resource code -> the d3planner class key it belongs to (maxfury -> barbarian)."""
    text = (REF / "data_stats.js").read_text(encoding="utf-8")
    return dict(re.findall(r'^\s*(max[a-z]+): \{name: "Maximum [^"]+", class: "([a-z]+)".*Resource_Max_Bonus#', text, re.M))


def item_block(js, d3_id):
    text = (REF / js).read_text(encoding="utf-8")
    start = text.index(f'id: "{d3_id}"')
    return text[start:text.index("preset:", start)]


def legendary_limits():
    text = (REF / "slots.js").read_text(encoding="utf-8")
    block = text[text.index("  legendary: {"):text.index("  ancient: {")]
    return {name: (float(lo), float(hi)) for name, lo, hi in
            re.findall(r"(\w+): \{min: ([\d.]+), max: ([\d.]+)", block)}


def d3planner_range(d3_id, code):
    """The item's own range for a Maximum Resource code, or its slots.js legendary limit."""
    js, _ = ITEMS_WITH_RESOURCE[d3_id]
    block = item_block(js, d3_id)
    own = re.search(rf"\b{code}: \{{min: ([\d.]+), max: ([\d.]+)\}}", block)
    if own:
        return float(own.group(1)), float(own.group(2))
    limit = re.search(rf'\b{code}: "(\w+)"', block)
    return legendary_limits()[limit.group(1)] if limit else None


def migration_rows():
    """(entry, affix_id, name, min, max, bracket) for every row the generated migration writes."""
    text = MIGRATION.read_text(encoding="utf-8")
    return [(int(e), a, n.replace("''", "'"), float(lo), float(hi), b) for e, a, n, lo, hi, b in
            re.findall(r"\((\d+), '([^']+)', '((?:[^']|'')*)', '\w+', ([\d.]+), ([\d.]+), [^,]+, '(\w+)'", text)]


def live_classes():
    """class_map.csv: (class_id, d3planner key) of every class that exists today and that d3planner has a Maximum Resource affix for.

    The Shaman is not a D3 class, so d3planner has no affix for Maelstrom: its Maximum Maelstrom row is the items bead's
    (the Shaman build brief, step 1b), and the test takes the class in once that row exists.
    """
    owned = set(class_of_maximum().values())
    return [(int(r["class_id"]), key) for r in read(D3 / "class_map.csv")
            if (key := r["d3_class"].lower().replace(" ", "")) in owned]


def harness(rule, cases):
    """cases: (label, class_id, [(affixId, name)]). Prints `label=<affix id>` per case."""
    calls = []
    for label, class_id, rows in cases:
        literal = ", ".join('{"%s", "%s"}' % (a, n) for a, n in rows)
        calls.append('    std::cout << "%s=" << Pick(%d, {%s}) << "\\n";' % (label, class_id, literal))
    return r'''
#include <iostream>
#include <string>
#include <vector>
#include "%s"
RULE_HERE
struct Row { std::string affixId, name; };
std::string Pick(unsigned classId, std::vector<Row> rows)
{
    // As StageRoll gathers them (dc_items_roll.cpp): the class's resources, primary first, then second.
    std::vector<std::string> resources;
    for (auto role : {DC::Resources::Data::Role::Primary, DC::Resources::Data::Role::Second})
        for (auto const& row : DC::Resources::Data::Rows)
            if (row.classId == classId && row.role == role)
                resources.push_back(row.d3Name);
    return DC::ResourceAffix::For(resources, rows);
}
int main()
{
%s
}
''' .replace("RULE_HERE", rule) % (DATA, "\n".join(calls))


class ResourcePreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = migration_rows()
        cls.owner = class_of_maximum()

    def cases(self, keep=lambda entry, affix: True):
        out = []
        for d3_id, (_, entry) in ITEMS_WITH_RESOURCE.items():
            for bracket in BRACKETS:
                rows = [(a, n) for e, a, n, _, _, b in self.rows if e == entry and b == bracket and keep(e, a)]
                for class_id, key in live_classes():
                    out.append((f"{d3_id}|{bracket}|{key}", class_id, rows))
        return out

    def picked(self, rule=RULE, keep=lambda entry, affix: True):
        ok, output = run(harness(rule, self.cases(keep)))
        self.assertTrue(ok, output)
        return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)

    def check(self, picked):
        problems = []
        for label, code in picked.items():
            d3_id, bracket, key = label.split("|")
            if self.owner.get(code) != key:
                problems.append(f"{label}: rolled {code!r}, d3planner's class for it is {self.owner.get(code)!r}")
                continue
            entry = ITEMS_WITH_RESOURCE[d3_id][1]
            row = [(lo, hi) for e, a, _, lo, hi, b in self.rows if e == entry and a == code and b == bracket]
            if row != [d3planner_range(d3_id, code)]:
                problems.append(f"{label}: {code} rows {row}, d3planner {d3planner_range(d3_id, code)}")
        return problems

    def test_every_live_class_rolls_its_own_resource_in_d3planners_range(self):
        picked = self.picked()
        self.assertEqual(len(picked), len(ITEMS_WITH_RESOURCE) * len(BRACKETS) * len(live_classes()))
        self.assertEqual(self.check(picked), [])

    def test_a_class_with_no_row_rolls_nothing(self):
        picked = self.picked(keep=lambda entry, affix: affix != "maxfury")
        self.assertEqual({v for k, v in picked.items() if k.endswith("|barbarian")}, {""})

    def test_a_rule_that_ignores_the_class_is_caught(self):
        broken = mutate(RULE, 'if (row.name == "Maximum " + name)', 'if (row.name.rfind("Maximum ", 0) == 0)')
        self.assertNotEqual(self.check(self.picked(broken)), [])

    def test_the_roller_resolves_the_preset_before_planning(self):
        gather = ITEMS.index("resourceAffix = DC::ResourceAffix::For(resources, itemPresets);")
        self.assertIn("{DC::Resources::Data::Role::Primary, DC::Resources::Data::Role::Second}",
                      ITEMS[gather - 600:gather])
        self.assertIn("resources.push_back(row.d3Name);", ITEMS[gather - 200:gather])
        planning = ITEMS.index("    planning.presets = base.presets;\n")
        swap = ITEMS.index("        if (preset == DC::ResourceAffix::Preset)\n            preset = resourceAffix;")
        self.assertLess(planning, swap)
        self.assertLess(swap, ITEMS.index("RollPlan const plan = PlanRoll(planning);"))


if __name__ == "__main__":
    unittest.main()
