"""GitHub #109: jewelry's +X-Y Physical Damage rolls D3's two parts and reaches the sheet as min + delta.

What runs:
  * the sheet: every neck and finger `wpnphy` row of data/d3/affix_pools.csv against slots.js's damageJewelry
    (reference/d3planner/slots.js:38 rare, :145 legendary, :238 ancient; :270 primal is a copy of ancient), and the
    same rows in the generated pool the server loads;
  * the roll: StageRoll's own `take` lambda, RollValue and RollWeaponDelta, cut out of the dc_items*.cpp files and compiled,
    rolled over the generated Ancient and Primal ring rows: the min in [88,105], the max (value2) in [168,210];
  * the sheet side: Apply's weapon-routing condition and its jewelry delta block, cut out and compiled against the
    real Mappings() and dc_common.h: a ring's two parts land as value on WeaponFlatDamage and value2 - value on
    WeaponFlatDamageDelta (docs/contracts/weapon-flat-damage.md), a weapon's stay its elemental range, a gem's
    one-number flat damage gets no delta, and unequip takes the delta off.
Not covered: the hit itself (Combat's half reads the two stats), the tooltip (dc_tooltip.lua already prints any
value2 > 0 as "+X-Y").
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import csv
import harness_env
import re
import shutil
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
ITEMS_H = MODULE / "src/items/dc_items.h"
COMMON = MODULE / "src/common"
POOLS_CSV = MODULE / "data/d3/affix_pools.csv"
POOLS_SQL = MODULE / "data/generated/affix_pools.sql"
SLOTS = ROOT / "reference/d3planner/slots.js"
CXX = shutil.which("c++") or shutil.which("g++")
ROLLS = 4000


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def slots_jewelry():
    """{bracket: (min, max, min2, max2)} from slots.js statLimits; primal is ancient's copy (:270)."""
    text = SLOTS.read_text(encoding="utf-8")
    assert "DiabloCalc.statLimits.primal = $.extend({}, DiabloCalc.statLimits.ancient);" in text
    out = {}
    for bracket in ("rare", "legendary", "ancient"):
        block = text[text.index(f"\n  {bracket}: {{"):]
        block = block[:block.index("\n  },")]
        found = re.search(r"damageJewelry: \{min: (\d+), max: (\d+), min2: (\d+), max2: (\d+)\}", block)
        assert found, bracket
        out[bracket] = tuple(int(v) for v in found.groups())
    out["primal"] = out["ancient"]
    return out


def generated_rows():
    """The neck/finger wpnphy rows of the generated pool: {(slot, bracket): (min, max, min2, max2, weapon_class)}."""
    rows = {}
    pattern = re.compile(r"^\('(neck|finger)', 'wpnphy', 'Physical Damage', 'primary', (\S+), (\S+), \S+, '(\w+)', "
                         r"\S+, 'slots\.js', \S+, (\S+), (\S+), '([^']*)'\),?;?$", re.M)
    for slot, low, high, bracket, low2, high2, weapon in pattern.findall(POOLS_SQL.read_text(encoding="utf-8")):
        number = lambda v: None if v == "NULL" else float(v)  # noqa: E731
        rows[(slot, bracket)] = (number(low), number(high), number(low2), number(high2), weapon)
    return rows


def roll_program(source, header, rows):
    take = source[source.index("    auto take = [&](PoolEntry const& entry, char const* kind)\n"):]
    take = take[:take.index("\n    };\n") + len("\n    };\n")]
    rolls = "\n".join(f'    Roll("{slot} {bracket}", {low}, {high}, {low2}, {high2}, {str(bracket == "primal").lower()});'
                      for (slot, bracket), (low, high, low2, high2, _) in sorted(rows.items()))
    return ("#include <algorithm>\n#include <cmath>\n#include <cstdint>\n#include <iostream>\n#include <map>\n"
            "#include <optional>\n#include <random>\n#include <string>\n#include <vector>\nnamespace DC::Items\n{\n"
            + definition("struct Affix\n", header) + ";\n"
            + definition("struct PoolEntry\n", header) + ";\n"
            + "std::mt19937& Engine() { static std::mt19937 engine(20261016u); return engine; }\n"
            + definition("double RollValue(PoolEntry const& entry)", source) + "\n"
            + definition("double RollWeaponDelta(PoolEntry const& entry)", source) + "\n"
            + "struct ElementalAffix { char const* id; char const* name; };\n"
              "constexpr char const* ELEMENTAL_POOL_ID = \"elemental\";\n"
              "constexpr char const* RESIST_POOL_ID = \"resist\";\n"
              "ElementalAffix const& RollElemental() { static ElementalAffix a{\"fire\", \"Fire\"}; return a; }\n"
              "ElementalAffix const& RollResist() { static ElementalAffix a{\"resfire\", \"Fire Resistance\"}; return a; }\n"
              "struct Choice { std::string id, name; };\n"
              "template<class... A> std::string PrimaryStat(A const&...) { return \"str\"; }\n"
              "std::string PrimaryName(std::string const& id) { return id; }\n"
              "void Roll(char const* tag, double a, double b, double c, double d, bool atTop)\n{\n"
              "    PoolEntry entry;\n"
              "    entry.affixId = \"wpnphy\"; entry.name = \"Physical Damage\"; entry.kind = \"primary\";\n"
              "    entry.min = a; entry.max = b; entry.min2 = c; entry.max2 = d;\n"
              f"    for (int i = 0; i < {ROLLS}; ++i)\n"
              "    {\n"
              "        std::vector<Affix> rolled;\n"
              "        std::vector<std::string> used;\n"
              "        std::map<std::string, std::vector<Choice>> groups;\n"
              "        int base = 0, mainStats = 0;\n"
              "        std::string affixClass, mainStat;\n"
              "        bool weaponDamageTaken = false;\n"
              "        auto valueOf = [&](PoolEntry const& entry) { return atTop ? entry.max : RollValue(entry); };\n"
            + take
            + "        take(entry, \"primary\");\n"
              "        for (Affix const& affix : rolled)\n"
              "            std::cout << \"ROLL \" << tag << \" \" << affix.value << \" \" << affix.value2 << \" \"\n"
              "                      << affix.rangeMin2 << \" \" << affix.rangeMax2 << \" \" << weaponDamageTaken << \"\\n\";\n"
              "        (void)base; (void)mainStats;\n"
              "    }\n"
              "}\n"
              "}\nusing namespace DC::Items;\nint main()\n{\n" + rolls + "\n    return 0;\n}\n")


def sheet_program(source, header):
    """Apply's weapon routing and jewelry delta, driven over a ring, a weapon and a gem."""
    body = items_source.stat_map(source)
    head = items_source.lists(source)
    routing = re.search(r"        if (\(affix\.kind != \"gem\" && affix\.value2 > 0 && .*WeaponDamageAffix\(affix\.affixId\)\))\n",
                        source)
    assert routing, "Apply's weapon routing condition moved"
    delta = source[source.index("        // Jewelry's +X-Y Physical Damage is D3's Min + Delta"):]
    delta = delta[:delta.index("\n    }\n    // A legendary gem's always-on power")]
    return ('#include "dc_common.h"\n#include <cstdio>\n#include <optional>\n#include <string>\n#include <unordered_map>\n#include <vector>\n'
            "namespace DC::Stats\n{\n"
            "std::vector<DC::Contribution> added;\n"
            "std::vector<std::pair<DC::Stat, std::uint64_t>> removed;\n"
            "bool AddContribution(std::uint64_t, DC::Contribution const& c) { added.push_back(c); return true; }\n"
            "bool RemoveContribution(std::uint64_t, DC::Source, DC::Stat stat, std::uint64_t id)\n"
            "{ removed.push_back({stat, id}); return true; }\n"
            "}\n"
            "namespace DC::Items {\n" + head + body
            + definition("bool WeaponDamageAffix(std::string const& id)", source) + "\n"
            + definition("std::uint64_t ContributionId(std::uint64_t itemGuid, unsigned seq)", source) + "\n"
            + definition("struct Affix\n", header) + ";\n"
            + "// One affix through Apply's loop: the weapon routing, then the mapped contribution as Apply adds it, then\n"
              "// the jewelry delta block.\n"
              "bool Through(Affix const& affix, bool weapon, bool equipping, std::uint64_t itemGuid)\n{\n"
              "    std::uint64_t const playerGuid = 1;\n"
              "    bool changed = false;\n"
              "    Source source = Source::Items;\n"
              f"    if {routing.group(1)}\n"
              "        return true;\n"
              "    auto mapping = Mappings().find(affix.affixId);\n"
              "    Stat stat = mapping->second.stat;\n"
              "    if (equipping)\n"
              "    {\n"
              "        Contribution contribution;\n"
              "        contribution.stat = stat;\n"
              "        contribution.id = ContributionId(itemGuid, affix.seq);\n"
              "        contribution.value = affix.value;\n"
              "        DC::Stats::AddContribution(playerGuid, contribution);\n"
              "    }\n"
              "    else\n"
              "        DC::Stats::RemoveContribution(playerGuid, source, stat, ContributionId(itemGuid, affix.seq));\n"
            + delta + "\n"
              "    (void)changed;\n"
              "    return false;\n"
              "}\n"
              "}\nusing namespace DC; using namespace DC::Items;\n"
              "int failures = 0;\n"
              "void check(char const* name, bool ok) { std::printf(\"%s %s\\n\", ok ? \"PASS\" : \"FAILED\", name); failures += !ok; }\n"
              "double Sum(Stat stat)\n{\n"
              "    double total = 0;\n"
              "    for (auto const& c : DC::Stats::added) if (c.stat == stat) total += c.value;\n"
              "    return total;\n"
              "}\n"
              "int main()\n{\n"
              "    Affix ring;\n"
              "    ring.seq = 3; ring.affixId = \"wpnphy\"; ring.kind = \"primary\"; ring.value = 95; ring.value2 = 190;\n"
              "    check(\"a ring's two parts are not a weapon's elemental range\", !Through(ring, false, true, 77));\n"
              "    check(\"a ring's min goes to WeaponFlatDamage\", Sum(Stat::WeaponFlatDamage) == 95);\n"
              "    check(\"a ring's max - min goes to WeaponFlatDamageDelta\", Sum(Stat::WeaponFlatDamageDelta) == 95);\n"
              "    check(\"the delta has the line's own contribution id\", DC::Stats::added.size() == 2 &&\n"
              "          DC::Stats::added[1].id == ContributionId(77, 3) && DC::Stats::added[1].source == Source::Items);\n"
              "    DC::Stats::added.clear();\n"
              "    Through(ring, false, false, 77);\n"
              "    bool tookDelta = false;\n"
              "    for (auto const& [stat, id] : DC::Stats::removed)\n"
              "        tookDelta = tookDelta || (stat == Stat::WeaponFlatDamageDelta && id == ContributionId(77, 3));\n"
              "    check(\"unequip takes the delta off\", tookDelta && DC::Stats::added.empty());\n"
              "    Affix sword = ring;\n"
              "    sword.affixId = \"wpnfir\";\n"
              "    check(\"a weapon's two-part row stays its elemental range\", Through(sword, true, true, 78) && DC::Stats::added.empty());\n"
              "    Affix gem;\n"
              "    gem.seq = 4; gem.affixId = \"wpnphy\"; gem.kind = \"gem\"; gem.value = 40;\n"
              "    Through(gem, true, true, 79);\n"
              "    check(\"a one-number flat damage gets no delta\", Sum(Stat::WeaponFlatDamage) == 40 && Sum(Stat::WeaponFlatDamageDelta) == 0);\n"
              "    return failures;\n"
              "}\n")


def build_and_run(code, *extra):
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    with tempfile.TemporaryDirectory(prefix="dc-jewelry-damage-") as folder:
        cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
        cpp.write_text(code, encoding="utf-8")
        built = subprocess.run([CXX, "-std=c++17", "-O1", "-UNDEBUG", *extra, "-o", str(binary), str(cpp)],
                               capture_output=True, text=True)
        if built.returncode:
            return None, "build: " + built.stderr[-3000:]
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
        return ran.returncode, ran.stdout


class Sheet(unittest.TestCase):
    def test_the_jewelry_rows_are_slots_js(self):
        sourced = slots_jewelry()
        with POOLS_CSV.open(encoding="utf-8", newline="") as stream:
            rows = [r for r in csv.DictReader(stream) if r["slot"] in ("neck", "finger") and r["affix_id"] == "wpnphy"]
        self.assertEqual(len(rows), 8)
        for row in rows:
            with self.subTest(slot=row["slot"], bracket=row["item_level_bracket"]):
                got = tuple(int(row[k]) for k in ("value_min", "value_max", "value_min2", "value_max2"))
                self.assertEqual(got, sourced[row["item_level_bracket"]])
                self.assertEqual(row["weapon_class"], "", "jewelry is no weapon bracket")

    def test_the_generated_pool_carries_both_ranges(self):
        sourced = slots_jewelry()
        rows = generated_rows()
        self.assertEqual(len(rows), 8)
        for (slot, bracket), (low, high, low2, high2, weapon) in rows.items():
            with self.subTest(slot=slot, bracket=bracket):
                self.assertEqual((low, high, low2, high2), tuple(float(v) for v in sourced[bracket]))
                self.assertEqual(weapon, "")


class Roll(unittest.TestCase):
    def run_rolls(self, source):
        return build_and_run(roll_program(source, ITEMS_H.read_text(encoding="utf-8"), generated_rows()))

    def test_an_ancient_ring_rolls_both_parts_inside_slots_js(self):
        code, out = self.run_rolls(items_source.source())
        self.assertEqual(code, 0, out)
        sourced = slots_jewelry()
        seen = {}
        for slot, bracket, value, value2, min2, max2, taken in re.findall(
                r"^ROLL (\w+) (\w+) (\S+) (\S+) (\S+) (\S+) (\d)$", out, re.M):
            seen.setdefault((slot, bracket), []).append((float(value), float(value2), float(min2), float(max2), taken))
        self.assertEqual(len(seen), 8, out[-500:])
        for (slot, bracket), samples in seen.items():
            a, b, c, d = sourced[bracket]
            with self.subTest(slot=slot, bracket=bracket):
                self.assertEqual(len(samples), ROLLS)
                for value, value2, min2, max2, taken in samples:
                    self.assertTrue(a <= value <= b, (value, a, b))
                    self.assertTrue(c <= value2 <= d and value2 > value, (value2, c, d))
                    self.assertEqual((min2, max2), (c, d))
                    self.assertEqual(taken, "0", "jewelry must not take the weapon's exclusive element group")
                if bracket == "primal":
                    self.assertEqual({(s[0], s[1]) for s in samples}, {(b, d)}, "a Primal rolls the top of both")
                else:
                    tops = [s[1] for s in samples]
                    self.assertLess(min(tops), c + (d - c) * 0.25, "the max never reaches the low end")
                    self.assertGreater(max(tops), d - (d - c) * 0.25, "the max never reaches the high end")

    def test_the_two_part_roll_is_keyed_on_the_second_range(self):
        source = items_source.source()
        for old, new in (("        else if (entry.max2 > 0)\n        {\n            // G1: a row with a second range",
                          "        else if (!entry.weaponClass.empty())\n        {\n            // G1: a row with a second range"),
                         ("            affix.value2 = atTop ? entry.max2 : affix.value + RollWeaponDelta(entry);",
                          "            affix.value2 = atTop ? entry.max2 : RollWeaponDelta(entry);"),
                         ("            if (!entry.weaponClass.empty())\n                weaponDamageTaken = true;",
                          "            weaponDamageTaken = true;")):
            with self.subTest(mutation=new):
                self.assertEqual(source.count(old), 1, old)
                code, out = self.run_rolls(source.replace(old, new))
                if code == 0:
                    with self.assertRaises(AssertionError):
                        self.check_output(out)

    def check_output(self, out):
        sourced = slots_jewelry()
        for slot, bracket, value, value2, _, _, taken in re.findall(
                r"^ROLL (\w+) (\w+) (\S+) (\S+) (\S+) (\S+) (\d)$", out, re.M):
            a, b, c, d = sourced[bracket]
            assert c <= float(value2) <= d, (slot, bracket, value2)
            assert taken == "0"


class Contributions(unittest.TestCase):
    def run_sheet(self, source):
        return build_and_run(sheet_program(source, ITEMS_H.read_text(encoding="utf-8")), "-I", str(COMMON))

    def test_a_ring_sends_min_and_delta(self):
        code, out = self.run_sheet(items_source.source())
        self.assertEqual(code, 0, out)
        self.assertNotIn("FAILED", out)

    def test_mutants_are_caught(self):
        source = items_source.source()
        for old, new in (("affix.value2 > 0 && weapon && WeaponDamageAffix(affix.affixId))",
                          "affix.value2 > 0 && true && WeaponDamageAffix(affix.affixId))"),
                         ("                delta.value = affix.value2 - affix.value;",
                          "                delta.value = affix.value2;"),
                         ("                delta.stat = Stat::WeaponFlatDamageDelta;",
                          "                delta.stat = Stat::WeaponFlatDamage;"),
                         ("        if (stat == Stat::WeaponFlatDamage && affix.value2 > 0)\n",
                          "        if (stat == Stat::WeaponFlatDamage && affix.value2 >= 0)\n"),
                         ("                changed = DC::Stats::RemoveContribution(playerGuid, source, Stat::WeaponFlatDamageDelta,",
                          "                changed = DC::Stats::RemoveContribution(playerGuid, source, Stat::WeaponFlatDamage,")):
            with self.subTest(mutation=new):
                self.assertEqual(source.count(old), 1, old)
                code, out = self.run_sheet(source.replace(old, new))
                self.assertNotEqual(code, 0, f"survived: {new!r}\n{out}")


if __name__ == "__main__":
    unittest.main()
