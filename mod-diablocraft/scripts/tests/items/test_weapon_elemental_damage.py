"""G1 (diablocraft-weapon-elemental-build): the weapon elemental roll.

Compiles the module's own `RollValue`, `RollWeaponDelta` and `WeaponDamageAffix` from
dc_items_roll.cpp and runs them over the SOURCED level-70 brackets, then compiles the real `PlanRoll`
over a generic-weapon pool. It fails on the code before G1: those symbols do not exist yet.

Sourced ranges (reference/d3planner/slots.js:89-91 rare, :196-198 legendary, :248-250 ancient):
each is a pair of endpoint brackets [a,b] and [c,d]; the roller rolls min in [a,b] and a delta in
[c-a, d-b], so value2 = min + delta lands in [c,d] and stays above the min (q-1003-18).
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
ROOT = HERE.parents[1]
# DC_ITEMS_CPP/DC_ITEMS_H let a mutant copy be run through the same test.
ITEMS = Path(os.getenv("DC_ITEMS_CPP", ROOT / "mod-diablocraft/src/items/dc_items_roll.cpp"))
ITEMS_H = Path(os.getenv("DC_ITEMS_H", ROOT / "mod-diablocraft/src/items/dc_items.h"))
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/weapon-elemental"
CXX = shutil.which("c++") or shutil.which("g++")
ROLLS = 4000

# bracket -> the two endpoint brackets, from the cited slots.js lines.
BRACKETS = {
    "damage1HNormal": {"rare": (853, 1043, 1022, 1296), "legendary": (981, 1199, 1175, 1490),
                       "ancient": (1318, 1560, 1609, 1940)},
    "damage1HFast": {"rare": (747, 912, 895, 1134), "legendary": (858, 1049, 1028, 1304),
                     "ancient": (1155, 1365, 1410, 1700)},
    "damage2H": {"rare": (1024, 1252, 1227, 1556), "legendary": (1177, 1439, 1410, 1788),
                 "ancient": (1582, 1870, 1932, 2325)},
}


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


affix = load("affix_budget_tunables", HERE / "tests/monsters/test_affix_budget_tunables.py")


def build_program() -> str:
    header = ITEMS_H.read_text(encoding="utf-8")
    source = ITEMS.read_text(encoding="utf-8")
    parts = [affix.definition("struct PoolEntry", header) + ";\n"]
    for name in ("struct Counts", "struct RollPlanFixed", "struct RollPlanInput", "struct RollPlan\n"):
        parts.append(affix.definition(name, header) + ";\n")
    # The functions under test, plus the RNG and the shield helper PlanRoll needs.
    parts.append("std::mt19937& Engine() { static std::mt19937 engine(20261003u); return engine; }\n")
    parts.append(affix.definition("double RollValue(PoolEntry const& entry)", source))
    parts.append(affix.definition("double RollWeaponDelta(PoolEntry const& entry)", source))
    parts.append(affix.definition("bool WeaponDamageAffix(std::string const& id)", source))
    parts.append("bool RequiredShieldAffix(std::string const& affixId)\n{\n"
                 '    return affixId == "baseblock" || affixId == "blockamount" || affixId == "blockamountdelta";\n}\n')
    parts.append(affix.definition("RollPlan PlanRoll(RollPlanInput const& in)", source))
    rolls = []
    for bracket, tiers in sorted(BRACKETS.items()):
        for tier, (a, b, c, d) in sorted(tiers.items()):
            rolls.append(f'    roll("{bracket}", "{tier}", {a}, {b}, {c}, {d});')
    plan = """
    {
        // A generic weapon's pool: the seven elemental rows (one exclusive group) plus only TWO
        // ordinary primaries, so the exclusive group is visible in the fill count (the budget wants
        // three more primaries, and the group may contribute none of them).
        auto pool = [](RollPlanInput& in)
        {
            for (char const* id : {"wpnphy", "wpnfir", "wpncol", "wpnpsn", "wpnarc", "wpnlit", "wpnhol"})
                in.primary.push_back(PoolEntry{id, "", "primary", "", 981, 1199, 1175, 1490, "damage1HNormal", 0, false});
            for (char const* id : {"mainstat", "chc"})
                in.primary.push_back(PoolEntry{id, "", "primary", "", 5, 8, 0, 0, "", 0, false});
            for (char const* id : {"resall", "gf", "laek"})
                in.secondary.push_back(PoolEntry{id, "", "secondary", "", 30, 40, 0, 0, "", 0, false});
        };
        auto report = [](char const* tag, RollPlan const& plan)
        {
            unsigned elements = 0;
            std::cout << tag << " fixed=";
            for (auto const& f : plan.fixed) { std::cout << f.entry.affixId << "|"; if (WeaponDamageAffix(f.entry.affixId)) ++elements; }
            std::cout << " random=" << plan.randomPrimary << ":" << plan.randomSecondary
                      << " elements=" << elements << "\\n";
        };
        RollPlanInput generic;
        generic.counts = Counts{4, 2};
        pool(generic);
        generic.presets.push_back("wpnfir");          // StageRoll's mandatory one-of-seven
        report("PLAN", PlanRoll(generic));
        RollPlanInput authored;                        // the Flying Axe shape: three authored elements
        authored.counts = Counts{4, 2};
        pool(authored);
        authored.presets.insert(authored.presets.end(), {"wpncol", "wpnfir", "wpnlit"});
        report("AUTHORED", PlanRoll(authored));
    }
    return 0;
}
"""
    code = ("#include <algorithm>\n#include <cmath>\n#include <iostream>\n#include <random>\n"
            "#include <string>\n#include <vector>\nnamespace DC::Items\n{\n"
            + "\n".join(parts)
            + "void roll(char const* bracket, char const* tier, double a, double b, double c, double d)\n{\n"
            "    PoolEntry entry;\n"
            '    entry.affixId = "wpnfir"; entry.kind = "primary"; entry.weaponClass = bracket;\n'
            "    entry.min = a; entry.max = b; entry.min2 = c; entry.max2 = d;\n"
            f"    for (int i = 0; i < {ROLLS}; ++i)\n"
            "    {\n"
            "        double const min = RollValue(entry);\n"
            "        double const delta = RollWeaponDelta(entry);\n"
            '        std::cout << "ROLL " << bracket << " " << tier << " " << min << " " << delta\n'
            '                  << " " << (min + delta) << "\\n";\n'
            "    }\n"
            "}\n"
            "}\nusing namespace DC::Items;\nint main()\n{\n"
            + "\n".join(rolls) + "\n" + plan)
    return code


def run() -> None:
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="g1-", dir=SCRATCH))
    source = folder / "g1.cpp"
    source.write_text(build_program(), encoding="utf-8")
    binary = folder / "g1"
    built = subprocess.run([CXX, "-std=c++17", "-O1", "-o", str(binary), str(source)],
                           capture_output=True, text=True)
    assert built.returncode == 0, "the roller did not compile:\n" + built.stderr[-4000:]
    out = harness_env.run([str(binary)], capture_output=True, text=True, check=True).stdout

    seen: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for bracket, tier, low, delta, high in re.findall(
            r"^ROLL (\S+) (\S+) (\S+) (\S+) (\S+)$", out, re.M):
        seen.setdefault((bracket, tier), []).append((float(low), float(delta), float(high)))
    generic = re.search(r"^PLAN fixed=(\S*) random=(\d+):(\d+) elements=(\d+)$", out, re.M)
    authored = re.search(r"^AUTHORED fixed=(\S*) random=(\d+):(\d+) elements=(\d+)$", out, re.M)
    assert generic and authored, out[-2000:]

    failures = []
    for (bracket, tier), samples in sorted(seen.items()):
        a, b, c, d = BRACKETS[bracket][tier]
        loDelta, hiDelta = c - a, d - b
        for low, delta, high in samples:
            if not (a <= low <= b):
                failures.append(f"{bracket}/{tier}: min {low} outside [{a},{b}]")
            if not (loDelta <= delta <= hiDelta):
                failures.append(f"{bracket}/{tier}: delta {delta} outside the sourced [{loDelta},{hiDelta}]")
            if not (c <= high <= d):
                failures.append(f"{bracket}/{tier}: max {high} outside [{c},{d}]")
            if not high > low:
                failures.append(f"{bracket}/{tier}: max {high} not above min {low}")
        # The spread must reach both ends of the delta range over many rolls, or the roll is not
        # the sourced one (a fixed or clamped delta would pass the containment check alone).
        deltas = [s[1] for s in samples]
        if min(deltas) > loDelta + (hiDelta - loDelta) * 0.1 or max(deltas) < hiDelta - (hiDelta - loDelta) * 0.1:
            failures.append(f"{bracket}/{tier}: delta range {min(deltas)}..{max(deltas)} does not span {loDelta}..{hiDelta}")
    assert not failures, "the weapon elemental roll is wrong:\n" + "\n".join(failures[:12])

    g_fixed, g_p, g_s, g_e = generic.group(1), int(generic.group(2)), int(generic.group(3)), int(generic.group(4))
    assert g_e == 1, f"a generic weapon must take exactly one elemental affix, got {g_e} (fixed={g_fixed})"
    assert "wpnfir" in g_fixed.split("|"), f"the injected element preset must be taken, got {g_fixed}"
    assert (g_p, g_s) == (2, 2), \
        f"the element consumes one primary and the fill cannot add another, got {g_p}:{g_s}"
    a_fixed, a_p, a_s, a_e = authored.group(1), int(authored.group(2)), int(authored.group(3)), int(authored.group(4))
    assert a_fixed == "wpncol|", f"three authored elements must take only the first, got {a_fixed}"
    assert a_e == 1 and (a_p, a_s) == (2, 2), \
        f"the authored group takes one and blocks the fill, got elements={a_e} random={a_p}:{a_s}"

    print(f"PASS weapon elemental roll: {sum(len(v) for v in seen.values())} rolls over "
          f"{len(seen)} bracket/tier pairs stay inside the sourced brackets and delta ranges; "
          f"PlanRoll takes exactly one of the seven (generic and three-authored) and the fill adds none")


if __name__ == "__main__":
    run()
