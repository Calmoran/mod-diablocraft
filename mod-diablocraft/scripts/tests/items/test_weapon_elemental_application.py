"""G1 (diablocraft-weapon-elemental-build): the rolled range reaches the sheet and combat.

Compiles the module's own `AverageWeaponDamage` (dc_stats.cpp) and `WeaponRange` (dc_combat.cpp,
factored out of `ComputeHit` for this test) against doubles, and asserts both add the rolled
elemental endpoints to the weapon's low/high. It fails on the code before G1: `WeaponRange` and
`Items::WeaponExtraDamageOf` do not exist there, and the sheet reads `WeaponGemDamage`.
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
# DC_STATS_CPP/DC_COMBAT_CPP let a mutant copy be run through the same test.
STATS = Path(os.getenv("DC_STATS_CPP", ROOT / "mod-diablocraft/src/stats/dc_stats.cpp"))
COMBAT = Path(os.getenv("DC_COMBAT_CPP", ROOT / "mod-diablocraft/src/combat/dc_combat.cpp"))
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/weapon-elemental"
CXX = shutil.which("c++") or shutil.which("g++")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


affix = load("affix_budget_tunables", HERE / "tests/monsters/test_affix_budget_tunables.py")


def build() -> str:
    stats = STATS.read_text(encoding="utf-8")
    combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
    average = affix.definition("static double AverageWeaponDamage(", stats)
    weapon_range = affix.definition("std::pair<double, double> WeaponRange(", combat)
    return f"""#include <cstdint>
#include <iostream>
#include <utility>
namespace DC::Items
{{
struct WeaponExtraDamage {{ double low = 0, high = 0; }};
}}
namespace testdata {{ DC::Items::WeaponExtraDamage extra{{0, 0}}; }}
namespace DC::Items
{{
WeaponExtraDamage WeaponExtraDamageOf(std::uint64_t, std::uint64_t) {{ return testdata::extra; }}
}}
enum WeaponAttackType {{ BASE_ATTACK, OFF_ATTACK }};
struct Guid {{ std::uint64_t GetRawValue() {{ return 1; }} std::uint64_t GetCounter() {{ return 2; }} }};
struct ItemTemplate {{ struct {{ double DamageMin = 0, DamageMax = 0; }} Damage[1]; }};
struct Item {{
    ItemTemplate t;
    ItemTemplate const* GetTemplate() {{ return &t; }}
    Guid GetGUID() {{ return {{}}; }}
}};
struct Player {{
    Item* weapon = nullptr;
    Guid GetGUID() {{ return {{}}; }}
    Item* GetWeaponForAttack(int, bool) {{ return weapon; }}
}};
{ average }
{ weapon_range }
int main()
{{
    Player p;
    Item w;
    w.t.Damage[0].DamageMin = 100;
    w.t.Damage[0].DamageMax = 200;
    p.weapon = &w;
    testdata::extra = {{0, 0}};
    std::cout << "SHEET " << AverageWeaponDamage(&p, BASE_ATTACK) << "\\n";
    testdata::extra = {{981, 1490}};
    std::cout << "SHEET " << AverageWeaponDamage(&p, BASE_ATTACK) << "\\n";
    auto const ranged = WeaponRange(&p, false);
    std::cout << "COMBAT " << ranged.first << " " << ranged.second << "\\n";
    p.weapon = nullptr;
    testdata::extra = {{0, 0}};
    std::cout << "SHEET " << AverageWeaponDamage(&p, BASE_ATTACK) << "\\n";
    auto const bare = WeaponRange(&p, false);
    std::cout << "COMBAT " << bare.first << " " << bare.second << "\\n";
    return 0;
}}
"""


def run() -> None:
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="g1-apply-", dir=SCRATCH))
    source = folder / "apply.cpp"
    source.write_text(build(), encoding="utf-8")
    binary = folder / "apply"
    built = subprocess.run([CXX, "-std=c++17", "-O1", "-o", str(binary), str(source)],
                           capture_output=True, text=True)
    assert built.returncode == 0, "the sheet/combat extract did not compile:\n" + built.stderr[-4000:]
    out = harness_env.run([str(binary)], capture_output=True, text=True, check=True).stdout
    sheets = [float(x) for x in re.findall(r"^SHEET (\S+)$", out, re.M)]
    combats = [(float(a), float(b)) for a, b in re.findall(r"^COMBAT (\S+) (\S+)$", out, re.M)]
    assert sheets == [150.0, 1385.5, 1.5], f"the sheet must add the rolled range: {sheets}"
    assert combats == [(1081.0, 1690.0), (1.0, 2.0)], f"combat must add the rolled range: {combats}"

    # The school is the skill's, and both readers use the one cached accessor.
    assert "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))]).count("hit.school = SchoolOf(shell.element);") == 1, \
        "the weapon element must not change the hit's school"
    for path in (STATS, COMBAT):
        assert "WeaponExtraDamageOf" in path.read_text(encoding="utf-8"), \
            f"{path.name} must read the shared cached accessor"
    print("PASS weapon elemental application: the sheet and combat both add the rolled endpoints "
          "(100/200 weapon + 981/1490 element -> 1385.5 sheet average, 1081..1690 combat), the "
          "bare hand keeps 1..2, and the hit school stays the skill's")


if __name__ == "__main__":
    run()
