#!/usr/bin/env python3
"""diablocraft-5ozrm (N-ELITEDR): damage taken from elites reduced by gear (D3's Damage_Percent_Reduction_From_Elites,
d3planner "edef"), and the two set levels that carry it: Aughild's Authority 3-piece (edef 30, edmg 30) and Blackthorne's
Battlegear 3-piece (edef 10, gf 25).

D3 keeps edef as a plain stat (data_stats.js, an item affix too), a `dr` one: sources multiply (stats_full.js). So it is a sheet stat,
Stat::EliteReduction, appended to the enum, mapped from "edef" in Items' Mappings(), and read by Combat::Mitigate when the hit's attacker
is an elite: the same IsElite that gates Elite Damage on the hit dealt, so both directions agree.

Checked here:
  * the reference: edef is a `dr` stat, and `dr` stats multiply;
  * tests/elite_damage_reduction/harness.cpp on the real dc_common.cpp: two sources multiply, no damage-taken factor moves, Validate
    bounds it, the save (version 10) keeps it and a version-7 save still loads (with mutants of dc_common.cpp);
  * Mappings() cut out of dc_items_data.cpp and compiled: "edef" is EliteReduction;
  * IsElite and Mitigate's elite line cut out of dc_combat.cpp and compiled: an elite's or a rift elite's hit is reduced, a normal
    one, a player's and an unknown attacker's are not; Elite Damage reads the same IsElite (with mutants of dc_combat.cpp);
  * diablocraft-cu5r3: a rift pack's members (a rare's minions, the champions beside the leader) are elites there too, as D3 counts
    them, through Rifts::IsElitePack cut out of dc_rifts.cpp with IsPromotedElite, which still says no for a member (the loot rule);
  * diablocraft-jnu2o (decisions.md 2026-10-14 "Two Combat readings" (1)): Bane of the Powerful's rank-25 cut from elites, the block of
    GemPowers::Incoming cut out of dc_gem_powers.cpp and compiled with the real rift tests, reads the same pack: a rare's minion is cut,
    a normal monster is not; its kill buff and the kill_elite event stay on IsPromotedElite (text);
  * every caller of Mitigate passes its attacker (text);
  * the two levels' rows are d3planner's, and the generator takes edef as a set stat and refuses the table without it.
It does not run the server: the in-game check is docs/test-diablocraft-5ozrm.md.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import item_powers_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator
import test_item_power_ashearas_vestments as asheara
import test_item_power_stat_set_levels as levels

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
SRC = MODULE / "src"
COMMON = SRC / "common/dc_common.cpp"
HARNESS = MODULE / "tests/elite_damage_reduction/harness.cpp"
STATS = SRC / "stats/dc_stats.cpp"
COMBAT = SRC / "combat/dc_combat.cpp"
RIFTS = SRC / "rifts/dc_rifts.cpp"
GEMS = SRC / "combat/dc_gem_powers.cpp"
REFERENCE = ROOT / "reference/d3planner"
LEVELS = [("Aughild's Authority", 3), ("Blackthorne's Battlegear", 3)]


def compiler():
    found = shutil.which("g++") or shutil.which("c++")
    if not found:
        raise unittest.SkipTest("no C++ compiler")
    return found


def build_and_run(cpp_text, *extra):
    """0 when the program's checks hold; anything else is a failure or a build error."""
    with tempfile.TemporaryDirectory(prefix="dc-elite-dr-") as folder:
        cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
        cpp.write_text(cpp_text, encoding="utf-8")
        built = subprocess.run([compiler(), "-std=c++20", "-UNDEBUG", *extra, "-o", str(binary), str(cpp)], capture_output=True, text=True)
        if built.returncode:
            return "build: " + built.stderr[-1500:]
        return harness_env.run([str(binary)], capture_output=True, text=True).returncode


def run_harness(common_text):
    with tempfile.TemporaryDirectory(prefix="dc-elite-dr-sheet-") as folder:
        tree = Path(folder) / "mod"
        shutil.copytree(SRC / "common", tree / "src/common", ignore=shutil.ignore_patterns("*.cpp"))
        (tree / "src/common/dc_common.cpp").write_text(common_text, encoding="utf-8")
        (tree / "tests/elite_damage_reduction").mkdir(parents=True)
        shutil.copy(HARNESS, tree / "tests/elite_damage_reduction/harness.cpp")
        binary = Path(folder) / "harness"
        built = subprocess.run([compiler(), "-std=c++17", "-O1", str(tree / "tests/elite_damage_reduction/harness.cpp"),
                                str(tree / "src/common/dc_common.cpp"), "-o", str(binary)], capture_output=True, text=True)
        if built.returncode:
            return "build: " + built.stderr[-1500:]
        return harness_env.run([str(binary)], capture_output=True, text=True).returncode


def mapping_program(source):
    body = items_source.stat_map(source)
    head = items_source.lists(source)
    return ('#include "dc_common.h"\n#include <cassert>\n#include <string>\n#include <unordered_map>\n'
            "namespace DC::Items {\n" + head + body + "}\nusing namespace DC; using namespace DC::Items;\n"
            "int main() {\n"
            '  auto const& edef = Mappings().at("edef");\n'
            "  assert(edef.stat == Stat::EliteReduction && edef.bucket == Bucket::Flat && edef.element == Element::Physical);\n"
            '  assert(Mappings().at("edmg").stat == Stat::EliteDamage);\n'
            "  return 0;\n}\n")


def body_of(text, signature):
    start = text.index(signature)
    return text[start:text.index("\n    }\n", start)]


def rift_tests(rifts):
    """IsPromotedElite and IsElitePack as dc_rifts.cpp has them (adjacent there)."""
    start = rifts.index("    bool IsPromotedElite(Creature const* creature)\n")
    end = rifts.index("\n    }\n", rifts.index("    bool IsElitePack(Creature const* creature)\n", start)) + 7
    return rifts[start:end]


def combat_program(combat, rifts=None):
    """IsElite, Mitigate's elite statement and the dealt side's elite line, as dc_combat.cpp has them, on stub units, with the
    rift's two elite tests as dc_rifts.cpp has them on a stub of the creature's rift elite state."""
    rifts = RIFTS.read_text(encoding="utf-8") if rifts is None else rifts
    start = combat.index("        inline bool IsElite(Unit const* unit)\n")
    is_elite = combat[start:combat.index("\n        }\n", start) + 10]
    mitigate = body_of(combat, "std::optional<double> Mitigate(")
    taken = re.search(r"\n(        if \(IsElite\(attacker\)\)\n.*?;)\n", mitigate, re.S)[1]
    dealt = re.search(r"\n(        hit\.elite = .*?;)\n", combat, re.S)[1]
    return ("#include <cstdio>\n#include <map>\n"
            "enum class Stat { EliteDamage, EliteReduction };\n"
            "struct EliteState { bool member; };\n"
            "struct Data { EliteState* state; template <class T> T* Get(char const*) const { return state; } };\n"
            "struct Creature { bool elite; Data CustomData; bool isElite() const { return elite; } };\n"
            "struct Unit { Creature* creature; Creature const* ToCreature() const { return creature; } };\n"
            "namespace DC::Rifts {\n" + rift_tests(rifts) + "\n}\n"
            "namespace Stats::Readers { enum class MonsterKind { Other }; template <class S> double MonsterTypeFactor(S const&, MonsterKind) { return 1; } }\n"
            "using Stats::Readers::MonsterKind; MonsterKind KindOf(Unit const*) { return MonsterKind::Other; }\n"
            "struct Sheet { double damage, reduction; double operator[](Stat s) const { return s == Stat::EliteDamage ? damage : reduction; } };\n"
            + is_elite + "\n"
            "double Taken(Unit* attacker, Sheet const& s) { double result = 100;\n" + taken + "\n return result; }\n"
            "double Dealt(Unit* target, Sheet const* sheet) { struct { double elite; } hit;\n" + dealt + "\n return hit.elite; }\n"
            "int main() {\n"
            "  Sheet const s{30, 30};\n"
            "  EliteState leader{false}, member{true};\n"
            "  Creature normal{false, {nullptr}}, elite{true, {nullptr}}, rift{false, {&leader}}, minion{false, {&member}};\n"
            "  Unit n{&normal}, e{&elite}, r{&rift}, m{&minion}, player{nullptr};\n"
            "  int bad = 0;\n"
            "  auto check = [&](bool ok, char const* what) { if (!ok) { std::printf(\"FAIL: %s\\n\", what); ++bad; } };\n"
            "  check(Taken(&e, s) == 70, \"an elite's hit is reduced by 30%\");\n"
            "  check(Taken(&r, s) == 70, \"a rift champion's or rare's hit is reduced\");\n"
            "  check(Taken(&m, s) == 70, \"a rift pack member's hit is reduced (a rare's minion, a champion beside the leader)\");\n"
            "  check(Taken(&n, s) == 100, \"a normal monster's hit is not reduced\");\n"
            "  check(Taken(&player, s) == 100, \"a player's hit is not reduced\");\n"
            "  check(Taken(nullptr, s) == 100, \"a hit from no known attacker is not reduced\");\n"
            "  check(Dealt(&e, &s) == 1.3 && Dealt(&r, &s) == 1.3 && Dealt(&m, &s) == 1.3 && Dealt(&n, &s) == 1, \"Elite Damage reads the same elites\");\n"
            "  check(DC::Rifts::IsPromotedElite(&rift) && !DC::Rifts::IsPromotedElite(&minion) && !DC::Rifts::IsPromotedElite(&normal),\n"
            "        \"loot: the leader is an elite kill, a member and a normal monster are not\");\n"
            "  return bad != 0;\n}\n")


def bane_program(gems, rifts=None):
    """The rank-25 block of GemPowers::Incoming (the elite-incoming factor), as dc_gem_powers.cpp has it, on stub units, with the rift's
    two elite tests as dc_rifts.cpp has them."""
    rifts = RIFTS.read_text(encoding="utf-8") if rifts is None else rifts
    block = re.search(r"\n( {12}if \(mine\.powerfulEliteDefencePct > 0\)\n {12}\{\n.*?\n {12}\})\n", body_of(gems, "void Incoming(Player* player"), re.S)[1]
    return ("#include <cstdio>\n"
            "struct EliteState { bool member; };\n"
            "struct Data { EliteState* state; template <class T> T* Get(char const*) const { return state; } };\n"
            "struct Creature { bool elite; Data CustomData; bool isElite() const { return elite; } };\n"
            "struct Unit { Creature* creature; Creature* ToCreature() const { return creature; } };\n"
            "namespace DC::Rifts {\n" + rift_tests(rifts) + "\n}\n"
            "struct Powers { double powerfulEliteDefencePct; };\n"
            "namespace GemPower { double EliteIncomingFactor(Powers const& p, bool elite) { return elite ? 1.0 - p.powerfulEliteDefencePct / 100.0 : 1.0; } }\n"
            "double Incoming(Unit* attacker, Powers const& mine) { double factor = 1.0;\n if (attacker) {\n" + block + "\n }\n return factor; }\n"
            "int main() {\n"
            "  Powers const worn{15}, bare{0};\n"
            "  EliteState leader{false}, member{true};\n"
            "  Creature normal{false, {nullptr}}, elite{true, {nullptr}}, rift{false, {&leader}}, minion{false, {&member}};\n"
            "  Unit n{&normal}, e{&elite}, r{&rift}, m{&minion}, player{nullptr};\n"
            "  int bad = 0;\n"
            "  auto check = [&](bool ok, char const* what) { if (!ok) { std::printf(\"FAIL: %s\\n\", what); ++bad; } };\n"
            "  check(Incoming(&e, worn) == 0.85, \"an elite's hit is cut by 15%\");\n"
            "  check(Incoming(&r, worn) == 0.85, \"a rift champion's or rare's hit is cut\");\n"
            "  check(Incoming(&m, worn) == 0.85, \"a rift pack member's hit is cut (a rare's minion, a champion beside the leader)\");\n"
            "  check(Incoming(&n, worn) == 1.0, \"a normal monster's hit is not cut\");\n"
            "  check(Incoming(&player, worn) == 1.0, \"a player's hit is not cut\");\n"
            "  check(Incoming(nullptr, worn) == 1.0, \"a hit from no known attacker is not cut\");\n"
            "  check(Incoming(&m, bare) == 1.0, \"without the gem at rank 25 nothing is cut\");\n"
            "  return bad != 0;\n}\n")


class Reference(unittest.TestCase):
    def test_edef_is_a_dr_stat_and_dr_stats_multiply(self):
        stats = (REFERENCE / "data_stats.js").read_text(encoding="utf-8")
        self.assertRegex(stats, r'edef: \{name: "Elite Damage Reduction", .*dr: true, .*id: "Damage_Percent_Reduction_From_Elites"')
        self.assertIn("dst[stat] = 100 - 0.01 * (100 - dst[stat]) * Math.max(0, 100 - amount * factor);",
                      (REFERENCE / "stats_full.js").read_text(encoding="utf-8"))
        self.assertIn('edef: "edefNormal"', (REFERENCE / "item_waist.js").read_text(encoding="utf-8"))


class Sheet(unittest.TestCase):
    def test_the_sheet_maths(self):
        text = COMMON.read_text(encoding="utf-8")
        self.assertEqual(run_harness(text), 0)
        mutants = [
            ("{ elite *= 1 - c.value / 100; continue; }", "{ elite -= c.value / 100; continue; }"),
            ("{ elite *= 1 - c.value / 100; continue; }", "{ specific *= 1 - c.value / 100; continue; }"),
            ("    values[Index(Stat::EliteReduction)] = (1 - elite) * 100;\n", ""),
            ("c.stat == Stat::SpecificReduction ||\n        c.stat == Stat::EliteReduction)", "c.stat == Stat::SpecificReduction)"),
            ('<< "12 " << sheet.level', '<< "9 " << sheet.level'),
            ("version >= 1 && version <= 12,", "version >= 1 && version <= 8,"),
            ("        : version == 7 ? Index(Stat::EliteReduction)\n", "        : version == 7 ? StatCount\n"),
            ("        : version == 9 ? Index(Stat::ResourceOnCrit)\n", "        : version == 9 ? StatCount\n"),
            ("        : version == 10 ? Index(Stat::MaelstromGeneration)\n", "        : version == 10 ? StatCount\n"),
            ("        : version == 11 ? Index(Stat::MaxSecond) : StatCount;", "        : StatCount;"),
        ]
        for old, new in mutants:
            with self.subTest(mutation=old):
                self.assertEqual(text.count(old), 1, old)
                self.assertNotEqual(run_harness(text.replace(old, new)), 0, f"survived: {old!r} -> {new!r}")

    def test_edef_maps_to_the_stat(self):
        source = items_source.source()
        run = lambda text: build_and_run(mapping_program(text), "-I", str(SRC / "common"))  # noqa: E731
        self.assertEqual(run(source), 0)
        old = '{"edef", {Stat::EliteReduction}}'
        for new in ('{"edef", {Stat::SpecificReduction}}', '{"edef", {Stat::EliteDamage}}', '{"edefNormal", {Stat::EliteReduction}}'):
            with self.subTest(mutation=new):
                self.assertEqual(source.count(old), 1)
                self.assertNotEqual(run(source.replace(old, new)), 0, f"survived: {new!r}")

    def test_toughness_and_the_stats_command_read_it(self):
        stats = STATS.read_text(encoding="utf-8")
        summary = (STATS.parent / "dc_sheet_summary.h").read_text(encoding="utf-8")   # the formula the player and a follower share
        for text, line in ((summary, "elementFactor *= 1 - sheet[Stat::EliteReduction] / 100 / 2;"),
                           (stats, '"% Elite DR=" << s[Stat::EliteReduction]')):
            with self.subTest(line=line):
                self.assertEqual(text.count(line), 1)


class Mitigate(unittest.TestCase):
    def test_an_elite_hit_is_reduced_and_a_normal_one_is_not(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        self.assertEqual(build_and_run(combat_program(combat)), 0)
        mutants = [
            ("        if (IsElite(attacker))\n            result *=", "        if (!IsElite(attacker))\n            result *="),
            ("result *= 1 - s[Stat::EliteReduction] / 100;", "result *= 1 - s[Stat::EliteReduction] / 1000;"),
            ("result *= 1 - s[Stat::EliteReduction] / 100;", "result *= 1 + s[Stat::EliteReduction] / 100;"),
            ("creature && (creature->isElite() || DC::Rifts::IsElitePack(creature));", "creature && creature->isElite();"),
            ("creature && (creature->isElite() || DC::Rifts::IsElitePack(creature));", "creature != nullptr;"),
            ("creature && (creature->isElite() || DC::Rifts::IsElitePack(creature));",
             "creature && (creature->isElite() || DC::Rifts::IsPromotedElite(creature));"),
            ("hit.elite = (1.0 + (IsElite(target) ?", "hit.elite = (1.0 + (target ?"),
        ]
        for old, new in mutants:
            with self.subTest(mutation=old):
                self.assertEqual(combat.count(old), 1, old)
                try:
                    result = build_and_run(combat_program(combat.replace(old, new)))
                except (TypeError, ValueError):
                    result = "cut failed"
                self.assertNotEqual(result, 0, f"survived: {old!r} -> {new!r}")

    def test_a_pack_member_is_an_elite_here_and_not_for_loot(self):
        """diablocraft-cu5r3: the rift's two tests, mutated one rule at a time."""
        combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        rifts = RIFTS.read_text(encoding="utf-8")
        self.assertEqual(build_and_run(combat_program(combat, rifts)), 0)
        pack = 'return creature && creature->CustomData.Get<EliteState>("DCRiftElite") != nullptr;'
        get = 'creature->CustomData.Get<EliteState>("DCRiftElite")'
        mutants = [
            (pack, f"return creature && {get} != nullptr && !{get}->member;"),  # members not counted
            (pack, f"return creature && {get} != nullptr && {get}->member;"),  # the leader not counted
            (pack, "return creature != nullptr;"),  # a normal monster counted
            ("return state != nullptr && !state->member;", "return state != nullptr;"),  # the loot rule changed
        ]
        for old, new in mutants:
            with self.subTest(mutation=new):
                self.assertEqual(rifts.count(old), 1, old)
                self.assertNotEqual(build_and_run(combat_program(combat, rifts.replace(old, new))), 0, f"survived: {new!r}")

    def test_bane_of_the_powerful_cuts_a_pack_members_hit_too(self):
        """diablocraft-jnu2o: the rank-25 reduction follows IsElite's pack test; the kill readers stay on the leader."""
        gems = GEMS.read_text(encoding="utf-8")
        self.assertEqual(build_and_run(bane_program(gems)), 0)
        old = "creature && (creature->isElite() || DC::Rifts::IsElitePack(creature))"
        mutants = [
            old.replace("IsElitePack", "IsPromotedElite"),  # the leader only: the reading before the ruling
            "creature && creature->isElite()",  # no rift pack at all
            "creature && (creature->isElite() || DC::Rifts::IsElitePack(creature)) && !creature->CustomData.Get<EliteState>(\"DCRiftElite\")",
            "creature != nullptr",  # a normal monster cut
            "creature && DC::Rifts::IsElitePack(creature)",  # the creature's own rank dropped
        ]
        for new in mutants:
            with self.subTest(mutation=new):
                self.assertEqual(gems.count(old), 1, old)
                self.assertNotEqual(build_and_run(bane_program(gems.replace(old, new))), 0, f"survived: {new!r}")
        rifts = RIFTS.read_text(encoding="utf-8")
        pack = 'return creature && creature->CustomData.Get<EliteState>("DCRiftElite") != nullptr;'
        for new in ("return creature != nullptr;", 'return creature && creature->CustomData.Get<EliteState>("DCRiftElite") != nullptr && !creature->CustomData.Get<EliteState>("DCRiftElite")->member;'):
            with self.subTest(rift_mutation=new):
                self.assertEqual(rifts.count(pack), 1, pack)
                self.assertNotEqual(build_and_run(bane_program(gems, rifts.replace(pack, new))), 0, f"survived: {new!r}")

    def test_the_kill_readers_stay_on_the_pack_leader(self):
        """Bane's kill buff and the kill_elite event are not part of the ruling: the one IsPromotedElite left in the gems file is the kill hook's."""
        gems = GEMS.read_text(encoding="utf-8")
        self.assertEqual(1, gems.count("IsPromotedElite("))
        self.assertEqual(1, gems.count("IsElitePack("))
        self.assertIn("bool const elite = killed->isElite() || DC::Rifts::IsPromotedElite(killed);", gems)
        self.assertIn("killed->isElite() || DC::Rifts::IsPromotedElite(killed)", item_powers_source.CPP.read_text(encoding="utf-8"))

    def test_it_is_a_percentage_layer_before_shield_block(self):
        mitigate = body_of("".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))]), "std::optional<double> Mitigate(")
        self.assertLess(mitigate.index("if (IsElite(attacker))"), mitigate.index("double const chance = ItemBlock::Chance("))

    def test_every_caller_passes_its_attacker(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        self.assertIn("bool melee = false, Unit* attacker = nullptr);", (SRC / "combat/dc_combat.h").read_text(encoding="utf-8"))
        calls = re.findall(r"\bMitigate\((?!Unit\* )(.*?)\)(?:\.value_or|;)", combat, re.S)
        self.assertEqual(2, len(calls), calls)
        for call in calls:
            self.assertTrue(call.rstrip().endswith("attacker"), call)
        defence = re.findall(r"ApplyPlayerDefence\((target.*?)\);", combat, re.S)
        self.assertEqual(3, len(defence), defence)
        for call in defence:
            self.assertTrue(call.rstrip().endswith("attacker"), call)
        # The one elite test: the creature's own rank and the rift's pack are read nowhere else in this file; loot's IsPromotedElite
        # (a pack's leader only) is not the combat one.
        self.assertEqual(1, combat.count("isElite()"))
        self.assertEqual(1, combat.count("IsElitePack("))
        self.assertEqual(0, combat.count("IsPromotedElite("))


class Rows(unittest.TestCase):
    def test_the_two_levels_are_the_planners(self):
        rows = levels.all_rows()
        for name, pieces in LEVELS:
            with self.subTest(level=name):
                self.assertIn("edef", [s for s, _ in levels.planner(name, pieces)])
                self.assertEqual(levels.want(name, pieces), sorted(r for r in rows if (r[0], r[1]) == (name, pieces)))
        self.assertEqual(("aughild_v2", "blackthorne"), tuple(levels.version(n) for n, _ in LEVELS))

    def test_the_generator_takes_edef_and_needs_it(self):
        self.assertIn("edef", generator.SET_STATS)
        case = asheara.Generator("test_the_real_row_passes")
        self.assertEqual(1, len([r for r in case.render_with({"stat": "edef", "value_min": "30", "value_max": "30"}) if r[0] == asheara.SET]))
        with self.assertRaisesRegex(ValueError, "set level's stat"):
            case.render_with({"stat": "edef", "value_min": "10", "value_max": "30"})
        kept = generator.SET_STATS
        try:
            generator.SET_STATS = tuple(s for s in kept if s != "edef")
            with self.assertRaisesRegex(ValueError, "Aughild's Authority.*set level's stat|set level's stat"):
                generator.render(MODULE)
        finally:
            generator.SET_STATS = kept


if __name__ == "__main__":
    unittest.main()
