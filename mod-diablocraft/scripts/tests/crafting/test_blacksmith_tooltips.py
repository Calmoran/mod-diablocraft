"""diablocraft-blacksmith-tooltips, server side: the preview's budget and preset rule are the
roller's, proved against the module's own code.

What runs, in one process: the module's own `CountsFor` and its planning step `PlanRoll`
(dc_items_roll.cpp and dc_items.h), cut out of the source and compiled against a `Tunables::Get` that answers
from the rows `generate_tunables.read_all` produces, and the real preview builder in
dc_tooltip.lua, run by lua over its fixtures in test_blacksmith_tooltips.lua. The Lua prints one
`FIXTURE` line per fixture - the eligible pools, the presets, the shield flag, the budget, the
skill groups and what the preview decided - and the compiled `PlanRoll` is run over that exact
input. Fixed ids and per-kind random counts must match for every fixture (all four catalogue
rarities, a preset outside the pool, a preset in the secondary pool, a duplicate preset, a shield,
a class-only item crafted by another class, and presets outside the pool that the item's own
dc_item_preset_range rows serve, one a block line on a helm that the pool's eligibility gate would
refuse, and the rare Mojo, Source, Phylactery and Quiver whose offhand pool's wpnphy is the
caster offhands' required damage and no quiver's, diablocraft-j0xsb, and whose ias is the Quiver's
required attack speed and no caster offhand's, diablocraft-7175z). StageRoll calls `PlanRoll`, so the roll and the
preview cannot drift (PM return 2026-10-03; the old tie was three source-text asserts).

Mutation evidence, both ways: a mutant planner and a mutant Lua mirror each fail the comparison.

What it does not run: `StageRoll` itself (it needs a Player and a live item). Its preset/fill
section is `PlanRoll`, which this test compiles and runs for real.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
ITEMS_CPP = MODULE / "src/items/dc_items_roll.cpp"
ITEMS_H = MODULE / "src/items/dc_items.h"
TOOLTIP = MODULE / "lua/aio/dc_tooltip.lua"
TEST = HERE / "tests/crafting/test_blacksmith_tooltips.lua"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/blacksmith-tooltips"
FIXTURE = re.compile(
    r"^FIXTURE (\S+) rarity=(\S+) presets=(\S*) shield=(\d) offhand=(\d) quiver=(\d) counts=(\d+):(\d+) skills=(\S*) "
    r"primary=(\S*) secondary=(\S*) own=(\S*) fixed=(\S*) random=(\d+):(\d+)$", re.M)


def load(name: str, path: Path):
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


affix = load("affix_budget_tunables", HERE / "tests/monsters/test_affix_budget_tunables.py")
CXX = shutil.which("c++") or shutil.which("g++")


def rows(field: str) -> list[tuple[str, str, float, float, bool, str]]:
    out = []
    for row in field.split("|"):
        if not row:
            continue
        affix_id, kind, low, high, percent, weapon_class = row.split(":")
        out.append((affix_id, kind, float(low), float(high), percent == "1", weapon_class))
    return out


def own_rows(field: str) -> list[tuple[str, str, float, float, bool]]:
    """diablocraft-wtxig: dc_item_preset_range rows the Lua printed - id:kind:min:max:percent."""
    out = []
    for row in field.split("|"):
        if not row:
            continue
        affix_id, kind, low, high, percent = row.split(":")
        out.append((affix_id, kind, float(low), float(high), percent == "1"))
    return out


def fixtures(stdout: str) -> dict[str, dict]:
    found = {}
    for (name, rarity, presets, shield, offhand, quiver, cp, cs, skills, primary, secondary, own, fixed,
         rp, rs) in FIXTURE.findall(stdout):
        found[name] = {"rarity": rarity, "presets": [p for p in presets.split(";") if p], "shield": shield == "1",
                       "offhand": offhand == "1", "quiver": quiver == "1",
                       "counts": (int(cp), int(cs)), "skills": [s for s in skills.split("|") if s],
                       "primary": rows(primary), "secondary": rows(secondary), "own": own_rows(own),
                       "fixed": sorted(a for a in fixed.split("|") if a), "random": (int(rp), int(rs))}
    assert found, "test_blacksmith_tooltips.lua printed no FIXTURE lines:\n" + stdout
    return found


def run_lua(tooltip: Path = TOOLTIP) -> str:
    interpreter = shutil.which("lua5.2") or shutil.which("lua5.1") or "lua"
    done = subprocess.run([interpreter, str(TEST)], cwd=ROOT, text=True, capture_output=True,
                          env=dict(**__import__("os").environ, DC_TOOLTIP_LUA=str(tooltip)))
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def cuts(items_cpp: Path = ITEMS_CPP, items_h: Path = ITEMS_H) -> str:
    """The planner's source: its structs from the header, the function and the shield helper."""
    header = items_h.read_text(encoding="utf-8")
    source = items_cpp.read_text(encoding="utf-8")
    parts = []
    for name in ("struct PoolEntry", "struct Counts", "struct RollPlanFixed", "struct RollPlanInput", "struct RollPlan\n"):
        parts.append(affix.definition(name, header) + ";\n")
    parts.append("bool RequiredShieldAffix(std::string const& affixId)\n{\n"
                 "    return affixId == \"baseblock\" || affixId == \"blockamount\" || affixId == \"blockamountdelta\";\n}\n")
    parts.append(affix.definition("RollPlan PlanRoll(", source))
    return "\n".join(parts)


def run_planner(specs: dict[str, dict], items_cpp: Path = ITEMS_CPP, tag: str = "run") -> dict[str, dict]:
    """Compile the module's own PlanRoll and run it over the fixtures the Lua printed."""
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    rows_cpp = []
    for name, spec in specs.items():
        body = [f'    {{\n    RollPlanInput in;\n    in.shield = {"true" if spec["shield"] else "false"};\n'
                f'    in.damageOffhand = {"true" if spec["offhand"] else "false"};\n'
                f'    in.speedQuiver = {"true" if spec["quiver"] else "false"};\n'
                f'    in.counts = Counts{{{spec["counts"][0]}, {spec["counts"][1]}}};']
        for preset in spec["presets"]:
            body.append(f'    in.presets.push_back("{preset}");')
        for skill in spec["skills"]:
            body.append(f'    in.skillGroups.push_back("{skill}");')
        pool_lines = []
        for affix_id, kind, low, high, percent, weapon_class in spec["primary"]:
            pool_lines.append(f'    in.primary.push_back(PoolEntry{{"{affix_id}", "", "{kind}", "", {low}, {high}, 0, 0, '
                              f'"{weapon_class}", 0, {"true" if percent else "false"}}});')
        for affix_id, kind, low, high, percent, weapon_class in spec["secondary"]:
            pool_lines.append(f'    in.secondary.push_back(PoolEntry{{"{affix_id}", "", "{kind}", "", {low}, {high}, 0, 0, '
                              f'"{weapon_class}", 0, {"true" if percent else "false"}}});')
        body += pool_lines
        for affix_id, kind, low, high, percent in spec["own"]:
            body.append(f'    in.itemPresets.push_back(PoolEntry{{"{affix_id}", "", "{kind}", "", {low}, {high}, 0, 0, '
                        f'"", 0, {"true" if percent else "false"}}});')
        body.append("    RollPlan const plan = PlanRoll(in);")
        body.append(f'    std::cout << "PLAN {name} fixed=";')
        body.append("    for (auto const& f : plan.fixed) std::cout << f.entry.affixId << \"|\";")
        body.append(f'    std::cout << " random=" << plan.randomPrimary << ":" << plan.randomSecondary << "\\n";')
        body.append("    }")
        rows_cpp.append("\n".join(body))
    code = f"""#include <algorithm>
#include <iostream>
#include <string>
#include <vector>
namespace DC::Items
{{
{cuts(items_cpp)}
}}
using namespace DC::Items;
int main()
{{
{chr(10).join(rows_cpp)}
    return 0;
}}
"""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=tag + "-", dir=SCRATCH))
    source = folder / "planner.cpp"
    source.write_text(code, encoding="utf-8")
    binary = folder / "planner"
    built = subprocess.run([CXX, "-std=c++17", "-o", str(binary), str(source)], capture_output=True, text=True)
    assert built.returncode == 0, "the planner did not compile:\n" + built.stderr[-5000:]
    done = harness_env.run([str(binary)], capture_output=True, text=True, check=True)
    got = {}
    for name, fixed, rp, rs in re.findall(r"^PLAN (\S+) fixed=(\S*) random=(\d+):(\d+)$", done.stdout, re.M):
        got[name] = {"fixed": sorted(a for a in fixed.split("|") if a), "random": (int(rp), int(rs))}
    assert len(got) == len(specs), f"planner answered {len(got)} of {len(specs)} fixtures:\n{done.stdout}"
    return got


def mismatches(specs: dict[str, dict], planned: dict[str, dict]) -> list[str]:
    out = []
    for name, spec in sorted(specs.items()):
        if name not in planned:
            out.append(f"{name}: no plan")
            continue
        if planned[name]["fixed"] != spec["fixed"]:
            out.append(f"{name}: fixed {planned[name]['fixed']} != preview {spec['fixed']}")
        if planned[name]["random"] != spec["random"]:
            out.append(f"{name}: random {planned[name]['random']} != preview {spec['random']}")
    return out


class BlacksmithTooltips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.counts = affix.run(affix.generated_table(), tag="blacksmith-tooltips")
        cls.specs = fixtures(run_lua())
        cls.planned = run_planner(cls.specs)

    def test_the_preview_count_is_the_rollers_budget(self):
        for name, spec in self.specs.items():
            budget = self.counts[spec["rarity"]]
            self.assertEqual(tuple(spec["counts"]), tuple(int(v) for v in budget),
                             f"{name}: the budget printed is CountsFor({spec['rarity']})")
            self.assertGreater(sum(spec["counts"]), 0, f"{name}: a real budget")

    def test_the_rollers_own_planner_agrees_with_the_preview(self):
        self.assertEqual(mismatches(self.specs, self.planned), [],
                         "the compiled PlanRoll and the Lua preview must decide the same")

    def test_every_catalogue_rarity_is_covered(self):
        got = {spec["rarity"] for spec in self.specs.values()}
        self.assertEqual(got, {"rare", "legendary", "set", "magic"}, "all four catalogue rarities")

    def test_a_mutant_planner_fails_the_comparison(self):
        """Mutate the C++: count every preset as primary, as a real behaviour change would."""
        source = ITEMS_CPP.read_text(encoding="utf-8")
        old = "(primary ? presetPrimaries : presetSecondaries)++;"
        assert source.count(old) == 1
        with tempfile.TemporaryDirectory(prefix="mutant-planner-", dir=SCRATCH) as folder:
            mutant = Path(folder) / "dc_items_roll.cpp"
            mutant.write_text(source.replace(old, "++presetPrimaries;"), encoding="utf-8")
            planned = run_planner(self.specs, items_cpp=mutant, tag="mutant-planner")
        self.assertNotEqual(mismatches(self.specs, planned), [], "a mutated planner must disagree")

    def test_a_mutant_lua_mirror_is_caught(self):
        """Mutate the Lua mirror: count every fixed affix as primary, and drop the pool cap.

        Each mutant must be caught - by the Lua test's own fixture assertions (it exits non-zero,
        which the Python test fails on) or, when those are silent, by the planner comparison. Both
        mutations below are real behaviour changes, so neither may slip through.
        """
        source = TOOLTIP.read_text(encoding="utf-8")
        mutants = {
            "secondary-preset-kind":
                ("if p.kind==\"secondary\" then fixedSecondary=fixedSecondary+1 else fixedPrimary=fixedPrimary+1 end",
                 "fixedPrimary=fixedPrimary+1"),
            "dropped-pool-cap":
                ('local randomPrimary=math.min(math.max(0,totalPrimary-fixedPrimary),free("primary"))',
                 "local randomPrimary=math.max(0,totalPrimary-fixedPrimary)"),
            # diablocraft-wtxig: back to dropping a preset the slot's pool has no row for.
            "dropped-item-presets":
                ("if not p then p=findOwn(id); own=p~=nil end",
                 "if not p then own=false end"),
            # diablocraft-sxj2c: the item's own rows put back behind the pool eligibility gate.
            "own-rows-gated-by-eligible":
                ("if p and (own or eligible(p)) and",
                 "if p and eligible(p) and"),
            # diablocraft-j0xsb: a quiver offered the offhand wpnphy, and the caster offhands' line
            # back inside the budget as an ordinary random primary.
            "quiver-rolls-offhand-damage":
                ('if base.slot=="offhand" and p.id=="wpnphy" and not damageOffhand then return false end\n', ""),
            "offhand-damage-not-required":
                ("local damageOffhand=PREVIEW_DAMAGE_OFFHAND[type]==true", "local damageOffhand=false"),
            # diablocraft-7175z: a caster offhand offered the Quiver's ias, and the Quiver's line
            # back inside the budget as an ordinary random primary.
            "caster-rolls-quiver-speed":
                ('if base.slot=="offhand" and p.id=="ias" and not speedQuiver then return false end\n', ""),
            "quiver-speed-not-required":
                ('local speedQuiver=type=="Quiver"', "local speedQuiver=false"),
            # diablocraft-bi52c: the pool the roller reads (PoolFor) is the slot's rows and then the type's own.
            "type-own-rows-dropped":
                ('for _,key in ipairs({slot,slot..":"..tostring(type or "")}) do', 'for _,key in ipairs({slot}) do'),
            "type-own-rows-wrong-key":
                ('for _,key in ipairs({slot,slot..":"..tostring(type or "")}) do', 'for _,key in ipairs({slot,slot..":"}) do'),
            "type-own-rows-before-slot":
                ('for _,key in ipairs({slot,slot..":"..tostring(type or "")}) do', 'for _,key in ipairs({slot..":"..tostring(type or "")}) do'),
            "totem-not-damage-offhand":
                ("local PREVIEW_DAMAGE_OFFHAND={Source=true,Mojo=true,Phylactery=true,Totem=true}",
                 "local PREVIEW_DAMAGE_OFFHAND={Source=true,Mojo=true,Phylactery=true}"),
        }
        for name, (old, new) in mutants.items():
            assert source.count(old) == 1, f"{name}: anchor not unique"
            with tempfile.TemporaryDirectory(prefix=f"mutant-lua-{name}-", dir=SCRATCH) as folder:
                mutant = Path(folder) / "dc_tooltip.lua"
                mutant.write_text(source.replace(old, new), encoding="utf-8")
                out = subprocess.run([shutil.which("lua5.2") or shutil.which("lua5.1") or "lua", str(TEST)],
                                     cwd=ROOT, text=True, capture_output=True,
                                     env=dict(**__import__("os").environ, DC_TOOLTIP_LUA=str(mutant)))
                if out.returncode != 0:
                    continue   # the Lua test's own fixture assertions caught it
                # The mutant's own printed fixtures, so the planner runs on the very input the
                # mutated preview worked from; comparing the production specs instead could never
                # differ and so could never detect anything.
                mutant = fixtures(out.stdout)
                self.assertNotEqual(mismatches(mutant, run_planner(mutant, tag="mutant-lua")),
                                    [], f"a mutated Lua mirror must be caught: {name}")


if __name__ == "__main__":
    unittest.main()
