#!/usr/bin/env python3
"""diablocraft-1t1yx: readers for the legendary affix stats the items code maps but nothing outside it read.

d3planner (reference/d3planner/data_stats.js) rolls apoc, lifefury, spiritregen, manaregen and damage_beasts/demons/undead/humans;
each needs a reader in Combat's paths, as colddef (508ry) and edef (5ozrm) did. Beasts, Demons and Undead read the creature
template's type; Humans read the D3 type column of gr_monster_progress.csv (the designer, q-1016-16), since 3.3.5's Humanoid also holds
orcs, trolls and murlocs. The table that column becomes is tests/stats/test_monster_types.py's.

Checked here, each against the production code and with mutants that must turn it red:
  * tests/stat_readers/harness.cpp on the real dc_stat_readers.h, dc_resource_pulse.h (RateFor over the generated rows) and
    dc_common.cpp: the sums, the Life per Fury Spent, Arcane Power per crit with its carry, the step 6 factor of each kind, the
    Spirit and Mana regeneration through the pulse's rate (Mana on a stub row: the Witch Doctor has none yet), the sheet save;
  * Combat::CriticalResource, Stats::FurySpent and KindOf cut out of their files and compiled on stubs of the core: only a
    Wizard is paid Arcane Power, only a Barbarian is paid Life for Fury, a creature's type reads its own stat, a Humanoid reads Humans only when the sheet types it Human;
  * the call sites: a critical hit, a Fury payment, the resource pulse's rate and ComputeHit's step 6 reach the readers.
It does not run the server: whether a given legendary rolls the stat is the items mapping's (a0avr).
"""
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

HERE = Path(__file__).resolve().parents[2]
MODULE = HERE.parent
ROOT = MODULE.parent
SRC = MODULE / "src"
HARNESS = MODULE / "tests/stat_readers/harness.cpp"
PROGRAM = MODULE / "tests/stat_readers/program.cpp"   # includes the program.h a test writes, so the text is staged and cached
READERS = "src/stats/dc_stat_readers.h"
PULSE_H = "src/stats/dc_resource_pulse.h"
COMMON_CPP = "src/common/dc_common.cpp"
COMBAT = SRC / "combat/dc_combat.cpp"
INTERNAL = SRC / "combat/dc_combat_internal.h"
SUSTAIN = SRC / "stats/dc_sustain.cpp"
PULSE_CPP = SRC / "stats/dc_resource_pulse.cpp"
BARBARIAN = SRC / "classes/barbarian/dc_barbarian.cpp"
REFERENCE = ROOT / "reference/d3planner"


def build_and_run(sources, files, includes):
    try:
        binary = harness_env.build(sources, flags=["-std=c++20", "-O1", "-UNDEBUG"], files=files, includes=includes)
    except harness_env.BuildError as error:
        return "build: " + error.stderr[-1500:]
    return harness_env.run([str(binary)], capture_output=True, text=True).returncode


def run_harness(overrides=None):
    """0 when every check in the harness holds on the tree with `overrides` ({path under mod-diablocraft: text}) put in."""
    files = {path[len("src/"):]: text for path, text in (overrides or {}).items()}
    return build_and_run([HARNESS, SRC / "common/dc_common.cpp"], files, [SRC, SRC / "stats"])


def run_program(source):
    return build_and_run([PROGRAM], {"program.h": source}, [SRC / "common", SRC / "stats"])


def cut(text, start, end):
    """text from `start` to the first `end` after it, end included."""
    begin = text.index(start)
    return text[begin:text.index(end, begin) + len(end)]


# What the core gives the cut-out code: a player with a guid and a class, a sheet by guid, the class registry, the spell numbers.
CORE_STUBS = r"""
#include "dc_common.h"
#include "dc_stat_readers.h"
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <optional>
#include <unordered_map>
using uint64 = std::uint64_t;
using uint32 = std::uint32_t;
struct ObjectGuid { uint64 v; uint64 GetRawValue() const { return v; } };
struct Player { uint64 guid; uint32 classId; ObjectGuid GetGUID() const { return {guid}; } };
namespace DC
{
    std::optional<StatSheet> theSheet;
    std::optional<double> theCoefficient;
    namespace Classes { uint32 ClassIdOf(Player const* p) { return p->classId; } bool Playable(Player const*) { return true; } }
    namespace Resources { struct R { uint32 classId; }; inline constexpr R ArcanePower{2}; inline constexpr R Fury{1}; }
    namespace Numbers { std::optional<double> Get(uint32, char const*) { return theCoefficient; } }
    namespace Stats { std::optional<StatSheet> Get(uint64) { return theSheet; } }
}
int failures = 0;
void Check(bool ok, char const* what) { if (!ok) { std::printf("FAIL: %s\n", what); ++failures; } }
using namespace DC;
StatSheet SheetWith(Stat stat, double value) { StatSheet s; s.values[Index(stat)] = value; return s; }
"""

CRITICAL_MAIN = r"""
int main()
{
    using namespace DC;
    Player wizard{1, 2}, barbarian{2, 1};
    theCoefficient = 0.5;
    theSheet = SheetWith(Stat::ResourceOnCrit, 5);
    Combat::CriticalResource(&wizard, 100);
    Check(Combat::gained == 2, "a Wizard's crit at 5 x 0.5 pays 2");
    Player other{3, 2};
    Combat::CriticalResource(&other, 100);
    Check(Combat::gained == 4, "a second Wizard has a carry of their own: 2, not the first one's 3");
    Combat::CriticalResource(&wizard, 100);
    Check(Combat::gained == 7, "the half carried joins the next crit: 3 more");
    Combat::gained = 5;
    Combat::CriticalResource(&barbarian, 100);
    Check(Combat::gained == 5, "a Barbarian's crit pays no Arcane Power");
    Combat::CriticalResource(&wizard, 0);
    Check(Combat::gained == 5, "a hit with no spell pays nothing");
    Combat::CriticalResource(nullptr, 100);
    Check(Combat::gained == 5, "no player pays nothing");
    theCoefficient = std::nullopt;
    Combat::CriticalResource(&wizard, 100);
    Check(Combat::gained == 5, "a spell with no coefficient pays nothing");
    theCoefficient = 1.0;
    theSheet = SheetWith(Stat::ResourceOnCrit, 0);
    Combat::CriticalResource(&wizard, 100);
    Check(Combat::gained == 5, "nothing on the sheet pays nothing");
    theSheet = std::nullopt;
    Combat::CriticalResource(&wizard, 100);
    Check(Combat::gained == 5, "no sheet pays nothing");
    theSheet = SheetWith(Stat::LifePerFury, 9);
    Combat::CriticalResource(&wizard, 100);
    Check(Combat::gained == 5, "another stat on the sheet pays nothing");
    return failures != 0;
}
"""

FURY_MAIN = r"""
int main()
{
    using namespace DC;
    Player barbarian{1, 1}, wizard{2, 2};
    theSheet = SheetWith(Stat::LifePerFury, 12);
    Stats::FurySpent(&barbarian, 30);
    Check(Stats::healed == 360, "30 Fury at 12 Life per Fury heals 360");
    Stats::FurySpent(&wizard, 30);
    Check(Stats::healed == 360, "a Wizard has no Fury to spend");
    Stats::FurySpent(&barbarian, 0);
    Stats::FurySpent(&barbarian, -4);
    Check(Stats::healed == 360, "no Fury spent heals nothing");
    Stats::FurySpent(nullptr, 30);
    Check(Stats::healed == 360, "no player heals nothing");
    theSheet = SheetWith(Stat::ResourceOnCrit, 12);
    Stats::FurySpent(&barbarian, 30);
    Check(Stats::healed == 360, "another stat on the sheet heals nothing");
    theSheet = std::nullopt;
    Stats::FurySpent(&barbarian, 30);
    Check(Stats::healed == 360, "no sheet heals nothing");
    return failures != 0;
}
"""

KIND_MAIN = r"""
int main()
{
    using namespace DC::Combat::Internal;
    using DC::Stats::Readers::MonsterKind;
    auto of = [](int type, std::string_view d3 = {}) { Creature c{type}; Unit u{&c}; DC::Combat::MonsterTypes::theType = d3; return KindOf(&u); };
    Check(of(CREATURE_TYPE_BEAST) == MonsterKind::Beast, "a Beast is a Beast");
    Check(of(CREATURE_TYPE_DEMON) == MonsterKind::Demon, "a Demon is a Demon");
    Check(of(CREATURE_TYPE_UNDEAD) == MonsterKind::Undead, "an Undead is Undead");
    Check(of(CREATURE_TYPE_HUMANOID) == MonsterKind::Other, "a Humanoid (orcs, trolls, murlocs) is none of them");
    Check(of(CREATURE_TYPE_HUMANOID, "Human") == MonsterKind::Human, "a monster the sheet types Human is a Human");
    Check(of(0, "Human") == MonsterKind::Human, "a Human needs no template type");
    Check(of(CREATURE_TYPE_HUMANOID, "Beast") == MonsterKind::Other && of(CREATURE_TYPE_HUMANOID, "Undead") == MonsterKind::Other &&
              of(CREATURE_TYPE_HUMANOID, "Reaper") == MonsterKind::Other, "only the Human type is read from the sheet's column");
    Check(of(CREATURE_TYPE_HUMANOID, "human") == MonsterKind::Other, "the type is matched as the sheet spells it");
    Check(of(CREATURE_TYPE_BEAST, "Human") == MonsterKind::Beast, "the template's Beast, Demon and Undead stay as planned");
    Check(of(CREATURE_TYPE_UNDEAD, "Human") == MonsterKind::Undead, "an Undead template stays Undead whatever the sheet says");
    Check(of(CREATURE_TYPE_DRAGONKIN) == MonsterKind::Other && of(0) == MonsterKind::Other, "any other type is none");
    Unit player{nullptr};
    DC::Combat::MonsterTypes::theType = "Human";
    Check(KindOf(&player) == MonsterKind::Other && KindOf(nullptr) == MonsterKind::Other, "a player or no unit is none");
    return failures != 0;
}
"""


def critical_program(combat):
    code = cut(combat, "    namespace\n    {\n        std::mutex critResourceMutex;", "        GainArcanePower(player, spellId, points);\n    }\n")
    return (CORE_STUBS + "namespace DC::Combat\n{\n    double gained = 0;\n"
            "    inline void GainArcanePower(Player*, uint32, double points) { gained += points; }\n" + code + "}\n" + CRITICAL_MAIN)


def fury_program(sustain):
    code = cut(sustain, "void FurySpent(Player* player, double fury)\n{", "\n}\n")
    return (CORE_STUBS + "namespace DC::Stats\n{\n    double healed = 0;\n    constexpr uint32 LIFE_PER_HIT_SHELL = 1;\n"
            "    bool Sheeted(Player const* player) { return player && Classes::Playable(player); }\n"
            "    void Restore(Player*, double life, uint32, char const*) { healed += life; }\n" + code + "}\n" + FURY_MAIN)


def kind_program(internal):
    code = cut(internal, "        inline Stats::Readers::MonsterKind KindOf(Unit const* unit)\n", "\n        }\n")
    return (CORE_STUBS +
            "enum { CREATURE_TYPE_BEAST = 1, CREATURE_TYPE_DRAGONKIN = 2, CREATURE_TYPE_DEMON = 3, CREATURE_TYPE_UNDEAD = 6,"
            " CREATURE_TYPE_HUMANOID = 7 };\n"
            "struct Template { int type; };\n"
            "struct Creature { int type; Template t() const { return {type}; } Template const* GetCreatureTemplate() const"
            " { static thread_local Template cache; cache = t(); return &cache; } };\n"
            "struct Unit { Creature* creature; Creature const* ToCreature() const { return creature; } };\n"
            "namespace DC::Combat::MonsterTypes\n{\n    std::string_view theType;\n"
            "    std::string_view D3TypeOf(Creature const* creature) { return creature ? theType : std::string_view{}; }\n}\n"
            "namespace DC::Combat::Internal\n{\n" + code + "\n}\n" + KIND_MAIN)


def read(path):
    return Path(path).read_text(encoding="utf-8")


def swap_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


class Reference(unittest.TestCase):
    def test_the_reference_has_the_eight_stats(self):
        stats = read(REFERENCE / "data_stats.js")
        for key, ident in [("apoc", "Resource_On_Crit#Arcanum"), ("lifefury", "Spending_Resource_Heals_Percent#Fury"),
                           ("spiritregen", "Resource_Regen_Per_Second#Spirit"), ("manaregen", "Resource_Regen_Per_Second#Mana"),
                           ("damage_beasts", "Damage_Percent_Bonus_Vs_Monster_Type#Beast"),
                           ("damage_demons", "Damage_Percent_Bonus_Vs_Monster_Type#Demon"),
                           ("damage_undead", "Damage_Percent_Bonus_Vs_Monster_Type#Undead"),
                           ("damage_humans", "Damage_Percent_Bonus_Vs_Monster_Type#Human")]:
            with self.subTest(key=key):
                self.assertRegex(stats, r'\b%s: \{[^\n]*id: "%s"' % (key, re.escape(ident)))


class Arithmetic(unittest.TestCase):
    def test_the_readers_and_the_sheet(self):
        self.assertEqual(run_harness(), 0)

    def test_a_wrong_reader_is_caught(self):
        readers = read(SRC / "stats/dc_stat_readers.h")
        pulse = read(SRC / "stats/dc_resource_pulse.h")
        mutants = [
            (READERS, readers, "furySpent * sheet[Stat::LifePerFury]", "sheet[Stat::LifePerFury]"),
            (READERS, readers, "furySpent * sheet[Stat::LifePerFury]", "furySpent * sheet[Stat::ResourceOnCrit]"),
            (READERS, readers, "return furySpent > 0 ? furySpent", "return furySpent != 0 ? furySpent"),
            (READERS, readers, "carry += perCrit * *procCoefficient;", "carry = perCrit * *procCoefficient;"),
            (READERS, readers, "carry += perCrit * *procCoefficient;", "carry += perCrit;"),
            (READERS, readers, "carry -= whole;", ""),
            (READERS, readers, "std::floor(carry)", "std::ceil(carry)"),
            (READERS, readers, "if (perCrit <= 0 || !procCoefficient", "if (!procCoefficient"),
            (READERS, readers, "return sheet[Stat::DamageVsBeast];", "return sheet[Stat::DamageVsDemon];"),
            (READERS, readers, "return sheet[Stat::DamageVsDemon];", "return sheet[Stat::DamageVsBeast];"),
            (READERS, readers, "return sheet[Stat::DamageVsUndead];", "return sheet[Stat::DamageVsBeast];"),
            (READERS, readers, "return sheet[Stat::DamageVsHuman];", "return sheet[Stat::DamageVsUndead];"),
            (READERS, readers, "case MonsterKind::Human:\n                return sheet[Stat::DamageVsHuman];\n", ""),
            (READERS, readers, "default:\n                return 0.0;", "default:\n                return sheet[Stat::DamageVsBeast];"),
            (READERS, readers, "1.0 + DamageVsKind(sheet, kind) / 100.0", "1.0 + DamageVsKind(sheet, kind) / 10.0"),
            (READERS, readers, "1.0 + DamageVsKind(sheet, kind) / 100.0", "DamageVsKind(sheet, kind) / 100.0"),
            (READERS, readers, 'resourceKey == "spirit"', 'resourceKey == "spirits"'),
            (READERS, readers, "return Stat::SpiritRegen;", "return Stat::ManaRegen;"),
            (READERS, readers, "return Stat::ManaRegen;", "return Stat::SpiritRegen;"),
            (READERS, readers, "return stat ? sheet[*stat] : 0.0;", "return stat ? sheet[*stat] : sheet[Stat::SpiritRegen];"),
            (PULSE_H, pulse, "(in.row->regenPerSecond + in.sheetPerSecond) * in.row->scale",
             "in.row->regenPerSecond * in.row->scale"),
            (PULSE_H, pulse, "(in.row->regenPerSecond + in.sheetPerSecond) * in.row->scale",
             "in.row->regenPerSecond * in.row->scale + in.sheetPerSecond"),
        ]
        for path, text, old, new in mutants:
            with self.subTest(mutation=old, to=new):
                self.assertNotEqual(run_harness({path: swap_once(text, old, new)}), 0, f"survived: {old!r} -> {new!r}")


class Production(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.combat = read(COMBAT)
        cls.internal = read(INTERNAL)
        cls.sustain = read(SUSTAIN)

    def test_arcane_power_on_critical_hit_pays_only_the_wizard(self):
        self.assertEqual(run_program(critical_program(self.combat)), 0)
        for old, new in [
            ("Classes::ClassIdOf(player) != Resources::ArcanePower.classId", "false"),
            ("(*sheet)[Stat::ResourceOnCrit]", "(*sheet)[Stat::LifePerFury]"),
            ("Numbers::Get(spellId, \"proc_coefficient\"), carry)", "std::optional<double>(1.0), carry)"),
            ("GainArcanePower(player, spellId, points);", "GainArcanePower(player, spellId, points + 1);"),
            ("!player || !spellId ||", "!spellId ||"),
            ("critResourceCarry[player->GetGUID().GetRawValue()]", "critResourceCarry[spellId]"),
        ]:
            with self.subTest(mutation=old):
                self.assertEqual(self.combat.count(old), 1, old)
                try:
                    result = run_program(critical_program(self.combat.replace(old, new)))
                except ValueError:
                    result = "cut failed"
                self.assertNotEqual(result, 0, f"survived: {old!r}")

    def test_life_per_fury_spent_heals_only_the_barbarian(self):
        self.assertEqual(run_program(fury_program(self.sustain)), 0)
        for old, new in [
            ("DC::Classes::ClassIdOf(player) != DC::Resources::Fury.classId", "false"),
            ("!Sheeted(player) ||", ""),
            ("Readers::LifeForFurySpent(*sheet, fury)", "Readers::LifeForFurySpent(*sheet, 1)"),
            ("Readers::LifeForFurySpent(*sheet, fury)", "fury"),
        ]:
            with self.subTest(mutation=old):
                self.assertEqual(self.sustain.count(old), 1, old)
                try:
                    result = run_program(fury_program(self.sustain.replace(old, new)))
                except ValueError:
                    result = "cut failed"
                self.assertNotEqual(result, 0, f"survived: {old!r}")

    def test_the_creature_type_picks_the_stat(self):
        self.assertEqual(run_program(kind_program(self.internal)), 0)
        for old, new in [
            ("case CREATURE_TYPE_BEAST: return Stats::Readers::MonsterKind::Beast;", "case CREATURE_TYPE_BEAST: return Stats::Readers::MonsterKind::Demon;"),
            ("case CREATURE_TYPE_DEMON: return Stats::Readers::MonsterKind::Demon;", "case CREATURE_TYPE_DEMON: return Stats::Readers::MonsterKind::Undead;"),
            ("case CREATURE_TYPE_UNDEAD: return Stats::Readers::MonsterKind::Undead;", "case CREATURE_TYPE_UNDEAD: return Stats::Readers::MonsterKind::Beast;"),
            ("default: return MonsterTypes::", "case CREATURE_TYPE_HUMANOID: return Stats::Readers::MonsterKind::Undead;\n                default: return MonsterTypes::"),
            ("creature ? creature->GetCreatureTemplate()->type : 0", "creature->GetCreatureTemplate()->type"),
            ('MonsterTypes::D3TypeOf(creature) == "Human"', 'MonsterTypes::D3TypeOf(creature) != "Human"'),
            ('MonsterTypes::D3TypeOf(creature) == "Human"', 'MonsterTypes::D3TypeOf(creature) == "Beast"'),
            ('MonsterTypes::D3TypeOf(creature) == "Human"', 'MonsterTypes::D3TypeOf(creature) != ""'),
            ("MonsterKind::Human : Stats::Readers::MonsterKind::Other", "MonsterKind::Undead : Stats::Readers::MonsterKind::Other"),
            ("MonsterKind::Human : Stats::Readers::MonsterKind::Other", "MonsterKind::Other : Stats::Readers::MonsterKind::Human"),
        ]:
            with self.subTest(mutation=old):
                self.assertEqual(self.internal.count(old), 1, old)
                self.assertNotEqual(run_program(kind_program(self.internal.replace(old, new))), 0, f"survived: {old!r}")

    def test_each_reader_is_called_from_its_path(self):
        barbarian = read(BARBARIAN)
        spent = cut(barbarian, "    void Spent(Player* p, double fury)\n    {", "\n    }\n")
        critical = cut(barbarian, "    void CriticalHit(Player* p, Unit* target, uint32 spellId, double damage)\n    {", "\n    }\n")
        self.assertIn("Stats::FurySpent(p, fury);", spent)
        self.assertIn("CriticalResource(p, spellId);", critical)
        pulse = read(PULSE_CPP)
        rate = cut(pulse, "Stats::Pulse::Rate RateOf(", "return Stats::Pulse::RateFor(in);")
        self.assertIn("in.sheetPerSecond = Stats::Readers::RegenPerSecond(*sheet, r.key);", rate)
        compute = cut(self.combat, "bool ComputeHit(", "std::string Hit::Describe()")
        self.assertIn("Stats::Readers::MonsterTypeFactor(*sheet, KindOf(target))", cut(compute, "hit.elite = ", ";\n"))
        # Elite Damage stays in the same product: the two multiply (damage_formula.csv step 6).
        self.assertIn("(*sheet)[Stat::EliteDamage]", cut(compute, "hit.elite = ", ";\n"))


if __name__ == "__main__":
    unittest.main()
