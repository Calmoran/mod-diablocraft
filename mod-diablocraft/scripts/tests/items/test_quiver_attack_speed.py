"""A Quiver carries D3's required Attack Speed Increase; no other offhand rolls it.

What runs:
  * the sheet: the offhand `ias` rows of data/d3/affix_pools.csv against slots.js's iasQuiver
    (reference/d3planner/slots.js:15 rare, :122 legendary; ancient copies legendary's (:262-265) and primal ancient's
    (:270)), and the same rows in the generated pool the server loads;
  * which types: the slots.js item types whose `required` names `ias: "iasQuiver"`, against the module's own
    SpeedQuiver over every offhand type of data/d3/base_items.csv;
  * the roll plan: the module's own PlanRoll and its pool helpers (Shield, BlockAffix, DamageOffhand,
    OffhandDamageAffix, SpeedQuiver, OffhandSpeedAffix), cut out of the dc_items*.cpp files and compiled, run over the sheet's
    offhand pool per type and bracket the way StageRoll filters it: the speed line is taken first, outside the budget,
    on the Quiver only, and a ring's ias stays an ordinary pool row;
  * the roll: RollValue over the four rows stays in [min, max].
Not covered: StageRoll itself (it needs a Player); its filter and its flag are pinned by text (Wiring), as are the
Mystic's two exclusions (mystic.csv:4: a Quiver's attack speed is the unalterable line). Apply sends `ias` as
Stat::AttackSpeed for every slot (dc_items_data.cpp's stat map), unchanged. The Blacksmith preview's Lua mirror
(dc_tooltip.lua) is the UI lane's.
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
POOLS_CSV = MODULE / "data/d3/affix_pools.csv"
POOLS_SQL = MODULE / "data/generated/affix_pools.sql"
BASES_CSV = MODULE / "data/d3/base_items.csv"
MYSTIC_CSV = MODULE / "data/d3/mystic.csv"
SLOTS = ROOT / "reference/d3planner/slots.js"
CXX = shutil.which("c++") or shutil.which("g++")
BRACKETS = ("rare", "legendary", "ancient", "primal")
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


def slots_quiver():
    """{bracket: (min, max)} from slots.js statLimits; a key missing from rare or ancient is legendary's (:262-268),
    and primal is ancient's copy (:270)."""
    text = SLOTS.read_text(encoding="utf-8")
    assert "DiabloCalc.statLimits.primal = $.extend({}, DiabloCalc.statLimits.ancient);" in text
    assert "DiabloCalc.statLimits.ancient[stat] = DiabloCalc.statLimits.legendary[stat];" in text
    found = {}
    for bracket in ("rare", "legendary", "ancient"):
        block = text[text.index(f"\n  {bracket}: {{"):]
        block = block[:block.index("\n  },")]
        hit = re.search(r"\biasQuiver: \{min: (\d+), max: (\d+)\}", block)
        if hit:
            found[bracket] = tuple(int(v) for v in hit.groups())
    for bracket in ("rare", "ancient"):
        found.setdefault(bracket, found["legendary"])
    found["primal"] = found["ancient"]
    return found


def slots_speed_types():
    """The display names of the slots.js offhand types whose required lines include ias: iasQuiver."""
    text = SLOTS.read_text(encoding="utf-8")
    names = set()
    for found in re.finditer(r"\n  (\w+): \{\n    slot: \"offhand\",(.*?)\n  \},", text, re.S):
        body = found.group(2)
        required = re.search(r"required: \{(.*?)\}", body, re.S)
        if required and re.search(r"\bias: \"iasQuiver\"", required.group(1)):
            names.add(re.search(r'name: "([^"]+)"', body).group(1))
    return names


def offhand_types():
    with BASES_CSV.open(encoding="utf-8", newline="") as stream:
        return sorted({r["type"] for r in csv.DictReader(stream) if r["slot"] == "offhand"})


def pool_rows(slot):
    with POOLS_CSV.open(encoding="utf-8", newline="") as stream:
        return [r for r in csv.DictReader(stream) if r["slot"] == slot]


def generated_rows():
    """The offhand ias rows of the generated pool: {bracket: (min, max, step, is_percent, kind)}."""
    rows = {}
    pattern = re.compile(r"^\('offhand', 'ias', 'Attack Speed Increase', '(\w+)', (\S+), (\S+), (\S+), '(\w+)', "
                         r"(\S+), 'slots\.js', \S+, \S+, \S+, '[^']*'\)[,;]$", re.M)
    for kind, low, high, step, bracket, percent in pattern.findall(POOLS_SQL.read_text(encoding="utf-8")):
        rows[bracket] = (float(low), float(high), step, percent, kind)
    return rows


def number(text):
    return text if text else "0"


def entry_literal(row):
    return ('PoolEntry{"%s", "%s", "%s", "%s", %s, %s, %s, %s, "%s", %s, %s, %s}'
            % (row["affix_id"], row["affix_name"], row["kind"], row["item_level_bracket"], row["value_min"],
               row["value_max"], number(row["value_min2"]), number(row["value_max2"]), row["weapon_class"],
               number(row["value_step"]), "true" if row["is_percent"] == "1" else "false",
               number(row["display_order"])))


def plan_program(source, header):
    parts = [definition("struct PoolEntry\n", header) + ";\n"]
    for name in ("struct Counts\n", "struct RollPlanFixed\n", "struct RollPlanInput\n", "struct RollPlan\n"):
        parts.append(definition(name, header) + ";\n")
    parts.append(items_source.struct("BaseItem"))
    parts.append("std::mt19937& Engine() { static std::mt19937 engine(20261016u); return engine; }\n")
    for marker in ("bool Shield(BaseItem const& base)", "bool BlockAffix(std::string const& affixId)",
                   "bool RequiredShieldAffix(std::string const& affixId)", "bool DamageOffhand(BaseItem const& base)",
                   "bool OffhandDamageAffix(BaseItem const& base, std::string const& affixId)",
                   "bool SpeedQuiver(BaseItem const& base)",
                   "bool OffhandSpeedAffix(BaseItem const& base, std::string const& affixId)",
                   "double RollValue(PoolEntry const& entry)", "RollPlan PlanRoll(RollPlanInput const& in)"):
        parts.append(definition(marker, source) + "\n")
    pools = []
    for slot in ("offhand", "finger"):
        for bracket in BRACKETS:
            rows = [r for r in pool_rows(slot) if r["item_level_bracket"] == bracket]
            pools.append('    pools["%s %s"] = {%s};' % (slot, bracket, ", ".join(entry_literal(r) for r in rows)))
    runs = [f'    Plan("offhand", "{kind}", "{bracket}");' for kind in offhand_types() for bracket in BRACKETS]
    runs += [f'    Plan("finger", "Ring", "{bracket}");' for bracket in BRACKETS]
    return ("#include <algorithm>\n#include <cmath>\n#include <cstdint>\n#include <iostream>\n#include <map>\n"
            "#include <random>\n#include <string>\n#include <vector>\nnamespace DC::Items\n{\n"
            + "\n".join(parts)
            + "std::map<std::string, std::vector<PoolEntry>> pools;\n"
              "// StageRoll's eligibility for a base, then PlanRoll with StageRoll's flags.\n"
              "void Plan(char const* slot, char const* type, char const* bracket)\n{\n"
              "    BaseItem base;\n"
              "    base.slot = slot; base.type = type;\n"
              "    RollPlanInput in;\n"
              "    unsigned pooled = 0;\n"
              "    for (PoolEntry const& entry : pools[std::string(slot) + \" \" + bracket])\n"
              "    {\n"
              "        if (BlockAffix(entry.affixId) && !Shield(base))\n"
              "            continue;\n"
              "        if (OffhandDamageAffix(base, entry.affixId) && !DamageOffhand(base))\n"
              "            continue;\n"
              "        if (OffhandSpeedAffix(base, entry.affixId) && !SpeedQuiver(base))\n"
              "            continue;\n"
              "        if (entry.affixId == \"ias\")\n"
              "            ++pooled;\n"
              "        (entry.kind == \"secondary\" ? in.secondary : in.primary).push_back(entry);\n"
              "    }\n"
              "    in.shield = Shield(base);\n"
              "    in.damageOffhand = DamageOffhand(base);\n"
              "    in.speedQuiver = SpeedQuiver(base);\n"
              "    in.counts = Counts{4, 2};\n"
              "    RollPlan const plan = PlanRoll(in);\n"
              "    std::cout << \"PLAN \" << slot << \"|\" << type << \"|\" << bracket << \"|pooled=\" << pooled << \"|fixed=\";\n"
              "    for (auto const& f : plan.fixed)\n"
              "        std::cout << f.entry.affixId << \":\" << f.counted << \":\" << f.entry.min << \",\" << f.entry.max << \";\";\n"
              "    std::cout << \"|random=\" << plan.randomPrimary << \":\" << plan.randomSecondary << \"\\n\";\n"
              "    if (std::string(slot) == \"offhand\" && SpeedQuiver(base))\n"
              "        for (PoolEntry const& entry : in.primary)\n"
              "            if (entry.affixId == \"ias\")\n"
              f"                for (int i = 0; i < {ROLLS}; ++i)\n"
              "                    std::cout << \"ROLL \" << type << \" \" << bracket << \" \" << RollValue(entry) << \"\\n\";\n"
              "}\n"
              "}\nusing namespace DC::Items;\nint main()\n{\n" + "\n".join(pools) + "\n" + "\n".join(runs)
            + "\n    return 0;\n}\n")


def build_and_run(code):
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    with tempfile.TemporaryDirectory(prefix="dc-quiver-speed-") as folder:
        cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
        cpp.write_text(code, encoding="utf-8")
        built = subprocess.run([CXX, "-std=c++17", "-O1", "-UNDEBUG", "-o", str(binary), str(cpp)],
                               capture_output=True, text=True)
        if built.returncode:
            return None, "build: " + built.stderr[-3000:]
        ran = harness_env.run([str(binary)], capture_output=True, text=True)
        return ran.returncode, ran.stdout


def parse_plans(out):
    plans = {}
    for line in re.findall(r"^PLAN (.*)$", out, re.M):
        slot, kind, bracket, pooled, fixed, random = line.split("|")
        lines = []
        for part in filter(None, fixed[len("fixed="):].split(";")):
            affix, counted, ranges = part.split(":")
            lines.append((affix, counted == "1", tuple(float(v) for v in ranges.split(","))))
        plans[(slot, kind, bracket)] = {"pooled": int(pooled[len("pooled="):]), "fixed": lines,
                                        "random": tuple(int(v) for v in random[len("random="):].split(":"))}
    return plans


def check_plans(out):
    """Every assertion on a plan; raises AssertionError on the first one that fails."""
    sourced = slots_quiver()
    speed = slots_speed_types()
    plans = parse_plans(out)
    assert len(plans) == len(offhand_types()) * 4 + 4, (len(plans), out[-500:])
    for (slot, kind, bracket), plan in plans.items():
        lines = [line for line in plan["fixed"] if line[0] == "ias"]
        if slot == "finger":
            assert plan["pooled"] == 1 and not lines, ("a ring's ias is an ordinary pool row", bracket, plan)
            continue
        if kind in speed:
            assert plan["pooled"] == 1, (kind, bracket, plan)
            assert len(lines) == 1, ("the speed line is taken once", kind, bracket, plan)
            affix, counted, ranges = lines[0]
            assert not counted, ("the speed line is outside the budget", kind, bracket)
            assert ranges == tuple(float(v) for v in sourced[bracket]), (kind, bracket, ranges)
            assert plan["random"] == (4, 2), ("the rolled affixes keep their whole budget", kind, bracket, plan)
        else:
            assert plan["pooled"] == 0 and not lines, ("no attack speed on a %s" % kind, bracket, plan)


class Sheet(unittest.TestCase):
    def test_the_offhand_rows_are_slots_js(self):
        sourced = slots_quiver()
        rows = [r for r in pool_rows("offhand") if r["affix_id"] == "ias"]
        self.assertEqual(sorted(r["item_level_bracket"] for r in rows), sorted(BRACKETS))
        for row in rows:
            with self.subTest(bracket=row["item_level_bracket"]):
                got = tuple(int(row[k]) for k in ("value_min", "value_max"))
                self.assertEqual(got, sourced[row["item_level_bracket"]])
                # Percent like every other slot's ias row; iasQuiver names no step, so none.
                self.assertEqual((row["kind"], row["is_percent"], row["value_step"], row["value_min2"],
                                  row["weapon_class"]), ("primary", "1", "", "", ""))

    def test_the_generated_pool_carries_the_rows(self):
        sourced = slots_quiver()
        rows = generated_rows()
        self.assertEqual(sorted(rows), sorted(BRACKETS))
        for bracket, (low, high, step, percent, kind) in rows.items():
            with self.subTest(bracket=bracket):
                self.assertEqual((low, high), tuple(float(v) for v in sourced[bracket]))
                self.assertEqual((step, percent, kind), ("NULL", "1", "primary"))

    def test_the_speed_types_are_slots_js(self):
        speed = slots_speed_types()
        self.assertEqual(speed, {"Quiver"})
        self.assertTrue(speed <= set(offhand_types()), (speed, offhand_types()))

    def test_the_mystic_source_names_the_quiver_line_unalterable(self):
        text = MYSTIC_CSV.read_text(encoding="utf-8")
        self.assertIn("1 unalterable affix (often item-type specific, e.g. Demon Hunter Quiver attack speed)", text)


class Plan(unittest.TestCase):
    def run_plans(self, source):
        return build_and_run(plan_program(source, ITEMS_H.read_text(encoding="utf-8")))

    def test_the_quiver_takes_the_speed_line_and_no_other_offhand_does(self):
        code, out = self.run_plans(items_source.source())
        self.assertEqual(code, 0, out)
        check_plans(out)

    def test_the_roll_stays_inside_slots_js(self):
        code, out = self.run_plans(items_source.source())
        self.assertEqual(code, 0, out)
        sourced = slots_quiver()
        seen = {}
        for kind, bracket, value in re.findall(r"^ROLL (\w+) (\w+) (\S+)$", out, re.M):
            seen.setdefault((kind, bracket), []).append(float(value))
        self.assertEqual(len(seen), 4)
        for (kind, bracket), samples in seen.items():
            low, high = sourced[bracket]
            with self.subTest(kind=kind, bracket=bracket):
                self.assertEqual(len(samples), ROLLS)
                self.assertTrue(all(low <= v <= high for v in samples), (min(samples), max(samples), low, high))
                if high > low:
                    self.assertGreater(len(set(samples)), 1)

    def test_mutants_are_caught(self):
        source = items_source.source()
        for old, new in (('    if (in.speedQuiver)\n', '    if (false)\n'),
                         ('            if (entry.affixId == "ias" && unused(entry))\n                take(entry, false);',
                          '            if (entry.affixId == "ias" && unused(entry))\n                take(entry, true);'),
                         ('bool SpeedQuiver(BaseItem const& base) { return base.type == "Quiver"; }',
                          'bool SpeedQuiver(BaseItem const& base) { return base.type == "Source"; }'),
                         ('bool SpeedQuiver(BaseItem const& base) { return base.type == "Quiver"; }',
                          'bool SpeedQuiver(BaseItem const& base) { return base.slot == "offhand"; }'),
                         ('    return base.slot == "offhand" && affixId == "ias";',
                          '    return affixId == "ias";'),
                         ('    return base.slot == "offhand" && affixId == "ias";',
                          '    return false;')):
            with self.subTest(mutation=new):
                self.assertEqual(source.count(old), 1, old)
                code, out = self.run_plans(source.replace(old, new))
                if code == 0:
                    with self.assertRaises(AssertionError, msg=f"survived: {new!r}"):
                        check_plans(out)


class Wiring(unittest.TestCase):
    """StageRoll and the Mystic need a Player; the lines that hand them the helpers are pinned by text."""

    @classmethod
    def setUpClass(cls):
        cls.source = items_source.source()

    def test_stage_roll_filters_and_flags_the_pool(self):
        stage = self.source[self.source.index("std::unique_ptr<StagedRoll> StageRoll(Player* player"):]
        self.assertIn("if (OffhandSpeedAffix(base, entry.affixId) && !SpeedQuiver(base))\n"
                      "                continue;", stage)
        self.assertIn("planning.speedQuiver = SpeedQuiver(base);", stage)

    def test_the_mystic_leaves_the_speed_line_to_the_item_type(self):
        expand = self.source[self.source.index("std::vector<Enchant::Cand> Expand(Enchant::Cand const& c) const"):]
        expand = expand[:expand.index("\n    }\n")]
        self.assertIn("if (OffhandSpeedAffix(*base, c.id))\n            return {};", expand)
        rows = self.source[self.source.index("    for (Affix const& a : instance.affixes)\n    {\n        // A Source's"):]
        rows = rows[:rows.index("in.rows.push_back({a.seq")]
        self.assertIn("if (OffhandSpeedAffix(base->second, a.affixId))\n            continue;", rows)


if __name__ == "__main__":
    unittest.main()
