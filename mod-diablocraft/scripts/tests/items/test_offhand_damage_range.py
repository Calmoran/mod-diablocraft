"""A Source, a Mojo, a Phylactery and the Shaman's Totem carry D3's required +X-Y Damage; a shield and a quiver roll none.

What runs:
  * the sheet: the offhand `wpnphy` rows of data/d3/affix_pools.csv against slots.js's damageOffhand
    (reference/d3planner/slots.js:39 rare, :146 legendary, :239 ancient; :270 primal is a copy of ancient), and the
    same rows in the generated pool the server loads;
  * which types: the slots.js item types whose `required` names `wpnphy: "damageOffhand"`, against the module's own
    DamageOffhand over every offhand type of data/d3/base_items.csv (a quiver's required line is attack speed);
  * the roll plan: the module's own PlanRoll and its pool helpers (Shield, BlockAffix, DamageOffhand,
    OffhandDamageAffix), cut out of the dc_items*.cpp files and compiled, run over the sheet's offhand pool per type and bracket
    the way StageRoll filters it: the damage line is taken first, outside the budget, on the three types only, and a
    ring's wpnphy stays an ordinary pool row;
  * the two parts: RollValue and RollWeaponDelta over the four offhand rows: the min in [a,b], the max in [c,d].
Not covered: StageRoll itself (it needs a Player); its filter and its flag are pinned by text (Wiring). The sheet
side (Apply sends a non-weapon two-part wpnphy as WeaponFlatDamage + WeaponFlatDamageDelta) is
test_jewelry_damage_range.py's; an offhand is ITEM_CLASS_ARMOR (generate_sql.py), so it takes that path. The Blacksmith
preview's Lua mirror (dc_tooltip.lua) is the UI lane's.
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


def slots_offhand():
    """{bracket: (min, max, min2, max2)} from slots.js statLimits; primal is ancient's copy (:270)."""
    text = SLOTS.read_text(encoding="utf-8")
    assert "DiabloCalc.statLimits.primal = $.extend({}, DiabloCalc.statLimits.ancient);" in text
    out = {}
    for bracket in ("rare", "legendary", "ancient"):
        block = text[text.index(f"\n  {bracket}: {{"):]
        block = block[:block.index("\n  },")]
        found = re.search(r"damageOffhand: \{min: (\d+), max: (\d+), min2: (\d+), max2: (\d+)\}", block)
        assert found, bracket
        out[bracket] = tuple(int(v) for v in found.groups())
    out["primal"] = out["ancient"]
    return out


def slots_damage_types():
    """The display names of the slots.js item types whose required lines include wpnphy: damageOffhand."""
    text = SLOTS.read_text(encoding="utf-8")
    names = set()
    for found in re.finditer(r"\n  (\w+): \{\n    slot: \"offhand\",(.*?)\n  \},", text, re.S):
        body = found.group(2)
        required = re.search(r"required: \{(.*?)\}", body, re.S)
        if required and re.search(r"\bwpnphy: \"damageOffhand\"", required.group(1)):
            names.add(re.search(r'name: "([^"]+)"', body).group(1))
    return names


def offhand_types():
    with BASES_CSV.open(encoding="utf-8", newline="") as stream:
        return sorted({r["type"] for r in csv.DictReader(stream) if r["slot"] == "offhand"})


def pool_rows(slot):
    with POOLS_CSV.open(encoding="utf-8", newline="") as stream:
        return [r for r in csv.DictReader(stream) if r["slot"] == slot]


def generated_rows():
    """The offhand wpnphy rows of the generated pool: {bracket: (min, max, min2, max2, weapon_class, kind)}."""
    rows = {}
    pattern = re.compile(r"^\('offhand', 'wpnphy', 'Physical Damage', '(\w+)', (\S+), (\S+), \S+, '(\w+)', "
                         r"\S+, 'slots\.js', \S+, (\S+), (\S+), '([^']*)'\)[,;]$", re.M)
    for kind, low, high, bracket, low2, high2, weapon in pattern.findall(POOLS_SQL.read_text(encoding="utf-8")):
        rows[bracket] = (float(low), float(high), float(low2), float(high2), weapon, kind)
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
                   "double RollValue(PoolEntry const& entry)", "double RollWeaponDelta(PoolEntry const& entry)",
                   "RollPlan PlanRoll(RollPlanInput const& in)"):
        parts.append(definition(marker, source) + "\n")
    pools = []
    for slot in ("offhand", "finger"):
        for bracket in BRACKETS:
            rows = [r for r in pool_rows(slot) if r["item_level_bracket"] == bracket]
            pools.append('    pools["%s %s"] = {%s};' % (slot, bracket, ", ".join(entry_literal(r) for r in rows)))
    runs = []
    for kind in offhand_types():
        for bracket in BRACKETS:
            runs.append(f'    Plan("offhand", "{kind}", "{bracket}");')
    for bracket in BRACKETS:
        runs.append(f'    Plan("finger", "Ring", "{bracket}");')
    return ("#include <algorithm>\n#include <cmath>\n#include <cstdint>\n#include <iostream>\n#include <map>\n"
            "#include <random>\n#include <string>\n#include <vector>\nnamespace DC::Items\n{\n"
            + "\n".join(parts)
            + "std::map<std::string, std::vector<PoolEntry>> pools;\n"
              "// StageRoll's eligibility for a base, then PlanRoll with StageRoll's two flags.\n"
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
              "        if (entry.affixId == \"wpnphy\")\n"
              "            ++pooled;\n"
              "        (entry.kind == \"secondary\" ? in.secondary : in.primary).push_back(entry);\n"
              "    }\n"
              "    in.shield = Shield(base);\n"
              "    in.damageOffhand = DamageOffhand(base);\n"
              "    in.counts = Counts{4, 2};\n"
              "    RollPlan const plan = PlanRoll(in);\n"
              "    std::cout << \"PLAN \" << slot << \"|\" << type << \"|\" << bracket << \"|pooled=\" << pooled << \"|fixed=\";\n"
              "    for (auto const& f : plan.fixed)\n"
              "        std::cout << f.entry.affixId << \":\" << f.counted << \":\" << f.entry.min << \",\" << f.entry.max << \",\"\n"
              "                  << f.entry.min2 << \",\" << f.entry.max2 << \";\";\n"
              "    std::cout << \"|random=\" << plan.randomPrimary << \":\" << plan.randomSecondary << \"\\n\";\n"
              "    if (std::string(slot) == \"offhand\" && DamageOffhand(base))\n"
              "        for (PoolEntry const& entry : in.primary)\n"
              "            if (entry.affixId == \"wpnphy\")\n"
              f"                for (int i = 0; i < {ROLLS}; ++i)\n"
              "                {\n"
              "                    double const value = RollValue(entry);\n"
              "                    std::cout << \"ROLL \" << type << \" \" << bracket << \" \" << value << \" \"\n"
              "                              << value + RollWeaponDelta(entry) << \"\\n\";\n"
              "                }\n"
              "}\n"
              "}\nusing namespace DC::Items;\nint main()\n{\n" + "\n".join(pools) + "\n" + "\n".join(runs)
            + "\n    return 0;\n}\n")


def build_and_run(code):
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    with tempfile.TemporaryDirectory(prefix="dc-offhand-damage-") as folder:
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


# slots.js names three types; the Shaman's Totem (diablocraft-xnrvn.3) is built like a Source and takes the same line.
TORMENT_DAMAGE = {"Totem"}


def check_plans(out):
    """Every assertion on a plan; raises AssertionError on the first one that fails."""
    sourced = slots_offhand()
    damage = slots_damage_types() | TORMENT_DAMAGE
    plans = parse_plans(out)
    assert len(plans) == len(offhand_types()) * 4 + 4, (len(plans), out[-500:])
    for (slot, kind, bracket), plan in plans.items():
        lines = [line for line in plan["fixed"] if line[0] == "wpnphy"]
        if slot == "finger":
            assert plan["pooled"] == 1 and not lines, ("a ring's wpnphy is an ordinary pool row", bracket, plan)
            continue
        if kind in damage:
            assert plan["pooled"] == 1, (kind, bracket, plan)
            assert len(lines) == 1, ("the damage line is taken once", kind, bracket, plan)
            affix, counted, ranges = lines[0]
            assert not counted, ("the damage line is outside the budget", kind, bracket)
            assert ranges == tuple(float(v) for v in sourced[bracket]), (kind, bracket, ranges)
            assert plan["random"] == (4, 2), ("the rolled affixes keep their whole budget", kind, bracket, plan)
        else:
            assert plan["pooled"] == 0 and not lines, ("no damage on a %s" % kind, bracket, plan)


class Sheet(unittest.TestCase):
    def test_the_offhand_rows_are_slots_js(self):
        sourced = slots_offhand()
        rows = [r for r in pool_rows("offhand") if r["affix_id"] == "wpnphy"]
        self.assertEqual(sorted(r["item_level_bracket"] for r in rows), sorted(BRACKETS))
        for row in rows:
            with self.subTest(bracket=row["item_level_bracket"]):
                got = tuple(int(row[k]) for k in ("value_min", "value_max", "value_min2", "value_max2"))
                self.assertEqual(got, sourced[row["item_level_bracket"]])
                self.assertEqual((row["kind"], row["weapon_class"], row["is_percent"]), ("primary", "", "0"))

    def test_the_generated_pool_carries_both_ranges(self):
        sourced = slots_offhand()
        rows = generated_rows()
        self.assertEqual(sorted(rows), sorted(BRACKETS))
        for bracket, (low, high, low2, high2, weapon, kind) in rows.items():
            with self.subTest(bracket=bracket):
                self.assertEqual((low, high, low2, high2), tuple(float(v) for v in sourced[bracket]))
                self.assertEqual((weapon, kind), ("", "primary"))

    def test_the_damage_types_are_slots_js(self):
        damage = slots_damage_types()
        self.assertEqual(damage, {"Source", "Mojo", "Phylactery"})
        self.assertTrue(damage | TORMENT_DAMAGE <= set(offhand_types()), (damage, offhand_types()))
        self.assertIn("Quiver", offhand_types())


class Plan(unittest.TestCase):
    def run_plans(self, source):
        return build_and_run(plan_program(source, ITEMS_H.read_text(encoding="utf-8")))

    def test_the_four_types_take_the_damage_line_and_no_other_does(self):
        code, out = self.run_plans(items_source.source())
        self.assertEqual(code, 0, out)
        check_plans(out)

    def test_both_parts_roll_inside_slots_js(self):
        code, out = self.run_plans(items_source.source())
        self.assertEqual(code, 0, out)
        sourced = slots_offhand()
        seen = {}
        for kind, bracket, value, value2 in re.findall(r"^ROLL (\w+) (\w+) (\S+) (\S+)$", out, re.M):
            seen.setdefault((kind, bracket), []).append((float(value), float(value2)))
        self.assertEqual(len(seen), 4 * 4)
        for (kind, bracket), samples in seen.items():
            a, b, c, d = sourced[bracket]
            with self.subTest(kind=kind, bracket=bracket):
                self.assertEqual(len(samples), ROLLS)
                for value, value2 in samples:
                    self.assertTrue(a <= value <= b, (value, a, b))
                    self.assertTrue(c <= value2 <= d and value2 > value, (value, value2, c, d))

    def test_mutants_are_caught(self):
        source = items_source.source()
        for old, new in (('    if (in.damageOffhand)\n', '    if (false)\n'),
                         ('            if (entry.affixId == "wpnphy" && unused(entry))\n                take(entry, false);',
                          '            if (entry.affixId == "wpnphy" && unused(entry))\n                take(entry, true);'),
                         ('base.type == \"Phylactery\" || base.type == \"Totem\";',
                          'base.type == \"Phylactery\" || base.type == \"Quiver\";'),
                         ('base.type == \"Phylactery\" || base.type == \"Totem\";',
                          'base.type == \"Phylactery\";'),
                         ('base.type == \"Mojo\" || base.type == \"Phylactery\"',
                          'base.type == \"Mojo\"'),
                         ('    return base.slot == "offhand" && affixId == "wpnphy";',
                          '    return affixId == "wpnphy";'),
                         ('    return base.slot == "offhand" && affixId == "wpnphy";',
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
        self.assertIn("if (OffhandDamageAffix(base, entry.affixId) && !DamageOffhand(base))\n"
                      "                continue;", stage)
        self.assertIn("planning.damageOffhand = DamageOffhand(base);", stage)

    def test_the_mystic_leaves_the_damage_line_to_the_item_type(self):
        expand = self.source[self.source.index("std::vector<Enchant::Cand> Expand(Enchant::Cand const& c) const"):]
        expand = expand[:expand.index("\n    }\n")]
        self.assertIn("|| OffhandDamageAffix(*base, c.id))\n            return {};", expand)
        rows = self.source[self.source.index("    for (Affix const& a : instance.affixes)\n    {\n        // A Source's"):]
        rows = rows[:rows.index("in.rows.push_back({a.seq")]
        self.assertIn("if (OffhandDamageAffix(base->second, a.affixId))\n            continue;", rows)


if __name__ == "__main__":
    unittest.main()
