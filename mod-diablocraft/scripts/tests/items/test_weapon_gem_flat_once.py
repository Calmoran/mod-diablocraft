"""diablocraft-eg5j8: a weapon gem's flat damage (a Ruby's "+X Damage", `wpnphy`) reaches the swing once.

D3 puts a Ruby's damage on the weapon it sits in (the gem is weapon-local, as G1's per-item cache keeps it), so a gem
of value X adds X to that weapon's low and high and nothing to the other hand.

What runs: the real `Apply` (equip, then unequip), `Mappings`, `ContributionId`, `WeaponDamageAffix` and
`WeaponExtraDamageOf`, cut out of the dc_items*.cpp files, the hit's `WeaponRange` cut out of dc_combat*.cpp, the real
`WithFlatDamage` (dc_weapon_flat.h), compiled against doubles for the server. The sheet's two flat stats are the sum
of their live contributions (both are plain Flat stats; `Calculate` itself needs the database's numeric rules).
Every weapon `wpnphy` row of the generated dc_gem_effect (data/generated/crafting.sql) is socketed into a 100-200
sword in turn; the hit range must be (100 + X, 200 + X) and, after unequip, the sheet must hold no flat damage.
Before the fix the gem landed in both the per-weapon cache and the sheet's WeaponFlatDamage, so the hit read 100 + 2X.
Not covered: the sheet summary (`AverageWeaponDamage` reads the same cache and `FlatDamageAverage` the same sheet).
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env  # noqa: E402
import os
import re
import shutil
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[3]
# DC_ITEMS_CPP lets a mutant copy (the dc_items*.cpp files joined into one) run through the same test; unset, the
# folder's own files are read.
ITEMS = Path(os.environ["DC_ITEMS_CPP"]) if os.getenv("DC_ITEMS_CPP") else None


def items_text():
    return ITEMS.read_text(encoding="utf-8") if ITEMS else items_source.source()
ITEMS_H = MODULE / "src/items/dc_items.h"
COMBAT = MODULE / "src/combat"
COMMON = MODULE / "src/common"
GEMS_SQL = MODULE / "data/generated/crafting.sql"
CXX = shutil.which("c++") or shutil.which("g++")


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def weapon_gems():
    """[(entry, value)] for every weapon wpnphy row the server loads."""
    rows = re.findall(r"INSERT INTO `dc_gem_effect` VALUES \((\d+),'weapon','wpnphy',([\d.]+)\);",
                      GEMS_SQL.read_text(encoding="utf-8"))
    assert len(rows) >= 5, "the generated dc_gem_effect lost its weapon wpnphy rows: %r" % rows
    return [(int(entry), float(value)) for entry, value in rows]


def program(gems):
    items = items_text()
    header = ITEMS_H.read_text(encoding="utf-8")
    combat = "".join(p.read_text(encoding="utf-8")
                     for p in [COMBAT / "dc_combat_internal.h", *sorted(COMBAT.glob("dc_combat*.cpp"))])
    elemental = items_source.lists(items)
    mapping = items_source.stat_map(items)
    # Apply's class gate: a gem's code names no class resource, so Applies() is true here; Signed()
    # is the source's own line.
    if "\nbool Applies(StatMapping const& mapping, Player const* player)" in items:
        mapping += "bool Applies(StatMapping const&, Player const*) { return true; }\n"
        mapping += next(line for line in items.splitlines() if line.startswith("double Signed(StatMapping const& mapping")) + "\n"
    cases = "\n".join("    Run(%d, %r);" % gem for gem in gems)
    return ('#include "dc_common.h"\n#include "../combat/dc_weapon_flat.h"\n'
            "#include <cstdio>\n#include <map>\n#include <mutex>\n#include <optional>\n#include <string>\n"
            "#include <unordered_map>\n#include <vector>\n"
            "using uint32 = std::uint32_t;\n"
            "enum { INVENTORY_SLOT_BAG_0 = 255, EQUIPMENT_SLOT_MAINHAND = 15, EQUIPMENT_SLOT_OFFHAND = 16, ITEM_CLASS_WEAPON = 2 };\n"
            "enum WeaponAttackType { BASE_ATTACK, OFF_ATTACK };\n"
            "struct Guid { std::uint64_t raw; std::uint64_t GetRawValue() const { return raw; } std::uint64_t GetCounter() const { return raw; } };\n"
            "struct ItemTemplate { unsigned Class = ITEM_CLASS_WEAPON; struct { double DamageMin = 100, DamageMax = 200; } Damage[1]; };\n"
            "struct Item { ItemTemplate t; Guid g{77}; bool IsBroken() const { return false; } Guid GetGUID() const { return g; }\n"
            "    ItemTemplate const* GetTemplate() const { return &t; } int GetBagSlot() const { return INVENTORY_SLOT_BAG_0; }\n"
            "    int GetSlot() const { return EQUIPMENT_SLOT_MAINHAND; } };\n"
            "struct Player { Item* weapon = nullptr; Guid GetGUID() const { return {5}; }\n"
            "    Item* GetWeaponForAttack(int attack, bool) { return attack == BASE_ATTACK ? weapon : nullptr; } };\n"
            "namespace DC::Stats\n{\n"
            "std::vector<DC::Contribution> live;\n"
            "bool AddContribution(std::uint64_t, DC::Contribution const& c)\n"
            "{ for (auto& o : live) if (o.source == c.source && o.stat == c.stat && o.id == c.id) { o = c; return true; }\n"
            "  live.push_back(c); return true; }\n"
            "bool RemoveContribution(std::uint64_t, DC::Source s, DC::Stat stat, std::uint64_t id)\n"
            "{ auto before = live.size(); std::erase_if(live, [&](auto const& o) { return o.source == s && o.stat == stat && o.id == id; });\n"
            "  return live.size() != before; }\n"
            "void Recompute(Player*) {}\n"
            "DC::StatSheet Sheet()\n"
            "{ DC::StatSheet sheet; for (auto const& c : live) sheet.values[DC::Index(c.stat)] += c.value; return sheet; }\n"
            "}\n"
            "namespace DC::GrantedPassive { constexpr char const* Kind = \"passive\"; }\n"
            "namespace DC::Items {\n"
            + definition("struct Affix\n", header) + ";\n"
            + definition("struct Instance\n", header) + ";\n"
            + definition("struct WeaponExtraDamage\n", (MODULE / "src/items/dc_items.h").read_text(encoding="utf-8")) + ";\n"
            "}\n"
            "namespace DC::GrantedPassive { std::string Granted(std::vector<DC::Items::Affix> const&) { return {}; } }\n"
            "namespace DC::Combat {\n"
            "namespace GemPowers { void Refresh(Player*, Item*, bool, DC::Items::Instance const&) {} }\n"
            "namespace ItemPowers { void Refresh(Player*, Item*, bool, DC::Items::Instance const&) {} }\n"
            "namespace Passives { void Invalidate(Player*) {} void RefreshModifiers(Player*) {} }\n"
            "}\n"
            "namespace DC::Items {\nusing namespace DC;\n"
            "struct BaseItem { std::string slot; };\n"
            "struct SkillAffix { std::uint32_t skillId = 0; };\n"
            "struct SkillBonuses { void Set(std::uint64_t, std::uint32_t, double) {} void Remove(std::uint64_t) {} };\n"
            "std::mutex dataMutex, bonusMutex;\n"
            "std::unordered_map<std::uint32_t, BaseItem> baseItems{{900, {\"onehand\"}}};\n"
            "std::unordered_map<std::string, SkillAffix> skillAffixes;\n"
            "std::unordered_map<std::uint64_t, SkillBonuses> skillBonuses;\n"
            "std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, WeaponExtraDamage>> weaponExtra;\n"
            "std::unordered_map<std::uint64_t, std::unordered_map<std::uint64_t, std::string>> grantedPassive;\n"
            "struct GemEffect { std::string stat, name; double value = 0; };\n"
            "std::unordered_map<uint32, std::unordered_map<std::string, GemEffect>> gemEffects;\n"
            "std::optional<Instance> socketed;\n"
            "bool Sheeted(Player*) { return true; }\n"
            "std::optional<Instance> Load(std::uint64_t) { return socketed; }\n"
            "void RefreshCubedStats(Player*) {}\n"
            + elemental + mapping
            + definition("std::uint64_t ContributionId(std::uint64_t itemGuid, unsigned seq)", items) + "\n"
            + definition("bool WeaponDamageAffix(std::string const& id)", items) + "\n"
            + definition("WeaponExtraDamage WeaponExtraDamageOf(std::uint64_t playerGuid, std::uint64_t itemGuid)", items) + "\n"
            + definition("void Apply(Player* player, Item* item, bool equipping)", items) + "\n"
            "}\n"
            "namespace DC::Combat {\n"
            + definition("std::pair<double, double> WeaponRange(Player* player, bool offHand)", combat) + "\n"
            "}\n"
            "using namespace DC;\n"
            "void Run(std::uint32_t entry, double value)\n{\n"
            "    Items::gemEffects = {{entry, {{\"weapon\", {\"wpnphy\", \"Ruby\", value}}}}};\n"
            "    Items::Instance sword; sword.itemGuid = 77; sword.baseItem = 900;\n"
            "    Items::Affix socket; socket.seq = 1; socket.kind = \"socket\";\n"
            "    Items::Affix gem; gem.seq = 2; gem.kind = \"gem\"; gem.affixId = \"ruby\"; gem.gemEntry = entry; gem.parentSeq = 1;\n"
            "    sword.affixes = {socket, gem};\n"
            "    Items::socketed = sword;\n"
            "    Player player; Item item; player.weapon = &item;\n"
            "    Items::Apply(&player, &item, true);\n"
            "    StatSheet worn = Stats::Sheet();\n"
            "    auto range = Combat::WithFlatDamage(Combat::WeaponRange(&player, false), worn);\n"
            "    Items::Apply(&player, &item, false);\n"
            "    StatSheet bare = Stats::Sheet();\n"
            "    std::printf(\"GEM %u %.9g %.9g %.9g %.9g %.9g\\n\", entry, value, range.first, range.second,\n"
            "                bare[Stat::WeaponFlatDamage], bare[Stat::WeaponFlatDamageDelta]);\n"
            "}\n"
            "int main()\n{\n" + cases + "\n    return 0;\n}\n")


def run():
    if not CXX:
        raise unittest.SkipTest("no C++ compiler")
    gems = weapon_gems()
    with tempfile.TemporaryDirectory(prefix="dc-weapon-gem-") as folder:
        work = Path(folder)
        (work / "common").mkdir()
        (work / "combat").mkdir()
        for header in COMMON.glob("*.h"):
            shutil.copy(header, work / "common" / header.name)
        shutil.copy(COMBAT / "dc_weapon_flat.h", work / "combat/dc_weapon_flat.h")
        cpp = work / "common/t.cpp"
        cpp.write_text(program(gems), encoding="utf-8")
        binary = work / "t"
        built = subprocess.run([CXX, "-std=c++20", "-O1", "-I", str(work / "common"), "-o", str(binary), str(cpp)], capture_output=True, text=True)
        assert built.returncode == 0, "the Apply extract did not compile:\n" + built.stderr[-4000:]
        out = harness_env.run([str(binary)], capture_output=True, text=True, check=True).stdout
    rows = [tuple(float(x) for x in line.split()[1:]) for line in out.splitlines() if line.startswith("GEM ")]
    assert len(rows) == len(gems), out
    wrong = [r for r in rows if (r[2], r[3]) != (100 + r[1], 200 + r[1])]
    assert not wrong, "a weapon gem must add its value once to the hit (entry, value, low, high): %r" % (
        [r[:4] for r in wrong],)
    left = [r for r in rows if r[4] or r[5]]
    assert not left, "unequip must leave no flat damage on the sheet: %r" % (left,)
    print("PASS weapon gem flat damage once: %d weapon wpnphy gems (%s) each add their value once to a 100-200 "
          "sword's hit, and unequip leaves the sheet's flat damage at 0"
          % (len(rows), ", ".join("%g" % r[1] for r in rows)))


class WeaponGemFlatOnce(unittest.TestCase):
    def test_once(self):
        run()


if __name__ == "__main__":
    run()
