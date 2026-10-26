#!/usr/bin/env python3
"""Checks for client-extension/wowdecomp/patches/0008-class-power-tokens-and-smooth-regen.patch.

Applies the series at the pin to a throwaway clone, copies in mod-diablocraft/data/generated/class_power_tokens.h as
the workflows do (copy-generated.ps1), lifts the patched functions out of the tree (GetClassPowerString and
GetUnitPowerString from Spell_C.cpp; the three CGUnit_C::DoPowerRegen and the stock CGUnit::GetPowerRegen and
GetPowerRegenBase from Unit_C.cpp and Unit.cpp) and compiles them with g++ against a small stand-in for the unit,
then drives them:

  * the token: a player whose class has a row reports the row's token on that slot; a creature of the same class
    id, a stock class and every other slot report the stock token;
  * the rate: a class power's slot moves at its field alone (no stock base), decays at a negative rate down to 0,
    in combat reads the interrupted field; a stock class keeps the stock base plus field;
  * the display divide: a player's class power is divided by its row's storage scale (Fury 10 today, 1 once its P2
    lands), so it shows its true points (UnitPower, UnitPowerMax, the tooltip and
    GetSpellInfo costs); a creature, a stock class and every other slot keep the stock divide (Rage and Runic Power
    a tenth);
  * the second slot: a class with a row off the drawn bar regenerates that slot too, each slot with its own
    fraction of a point (run with a test copy of the table that adds a second row, as the Demon Hunter's
    Discipline will be once live).

Also checks every reader the patch changes and the copy steps in both workflows. Nothing here builds the client;
the bar on screen is the designer's check. Needs reference/wowdecomp at the pin and g++; skips without them.

Run: python3 client-extension/tests/test_class_power_tokens.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WOWDECOMP_DIR = HERE.parent / "wowdecomp"
PATCHES = WOWDECOMP_DIR / "patches"
PATCH = PATCHES / "0008-class-power-tokens-and-smooth-regen.patch"
HEADER = REPO / "mod-diablocraft" / "data" / "generated" / "class_power_tokens.h"
WORKFLOWS = [REPO / ".github" / "workflows" / "client-rebuild.yml", REPO / ".github" / "workflows" / "client-rebuild-probe.yml"]

ROW = re.compile(r'\{(\d+), (\d+), "([A-Z_]+)"\}')
SCALE = re.compile(r'^    \{(\d+), (\d+), (\d+)\},', re.M)
STOCK = ["MANA", "RAGE", "FOCUS", "ENERGY", "HAPPINESS", "RUNES", "RUNIC_POWER"]


def find_reference() -> Path | None:
    for root in (REPO, Path.home() / "diablocraft"):
        candidate = root / "reference" / "wowdecomp"
        if (candidate / ".git").exists():
            return candidate
    return None


def function(text: str, signature: str) -> str:
    """The definition that starts with signature, through its closing brace."""
    start = text.index(signature)
    depth = 0
    for i in range(text.index("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise AssertionError(f"unbalanced {signature}")


STAND_IN = r"""
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "Torment/class_power_tokens.h"
#define __stdcall

enum TypeMask { TYPEMASK_UNIT = 8, TYPEMASK_PLAYER = 16 };
struct CGObjectData { uint64_t m_guid; int m_type; };
// Patch 0010 saturates Life shown as a power (power type -2) in the 32-bit predicted-power code; the stand-in's Life is 32 bits already.
inline int32_t UnitLifeAsPower(int64_t life) { return static_cast<int32_t>(life); }
// An out-of-range party member has no unit, only the name cache's record (its class) and the party state's slot.
struct WOWGUID { uint64_t m_guid = 0; WOWGUID() = default; WOWGUID(uint64_t g) : m_guid(g) {} };
struct NameCache { uint32_t m_class; };
static NameCache g_cachedName = {0};
static bool g_nameCached = false;
struct NameDB { NameCache* GetRecord(uint64_t, const WOWGUID&, void*, void*, bool) { return g_nameCached ? &g_cachedName : nullptr; } } g_nameDBCache;
uint32_t Spell_C_GetClassPowerDisplayMod(uint32_t classId, uint32_t powerType);
struct CGUnitData {
    uint8_t m_unitFieldBytes0[4];
    uint32_t m_unitFieldFlags;
    uint32_t m_unitFieldFlags2;
    int32_t m_unitChannelSpell;
    int32_t m_unitFieldMaxhealth;
    int32_t m_unitFieldMaxpower[7];
    float m_unitFieldPowerRegenFlatModifier[7];
    float m_unitFieldPowerRegenInterruptedFlatModifier[7];
};
struct CGPlayerData { uint32_t m_playerFieldBytes2; };
namespace FrameTime { uint32_t s_curTimeMs = 0; }
static uint64_t g_activePlayer = 0;
uint64_t ClntObjMgrGetActivePlayer() { return g_activePlayer; }
struct SpellRec { uint32_t m_attributesExB; int32_t m_powerType; };
struct SpellDB { bool GetRecord(int32_t, SpellRec*) { return false; } } g_spellDB;
struct CGUnit_C;
int32_t Spell_C_GetPowerCost(const SpellRec*, const CGUnit_C*) { return 0; }
namespace CMath {
    int32_t fint_(float f) { return static_cast<int32_t>(lrintf(f)); }
    int32_t ftrunc(float f) { return static_cast<int32_t>(f); }
}
struct CGRuneInfo {
    static uint32_t m_predictedRunes;
    static uint32_t GetRuneRechargeTime(int32_t) { return 0; }
    static void SetPredictedRunes(uint32_t, uint32_t, void*) {}
};
uint32_t CGRuneInfo::m_predictedRunes = 0xFF;

struct CGUnit_C {
    CGObjectData* m_obj;
    CGUnitData* m_unit;
    uint32_t m_auraEffectMask[32] = {};
    uint32_t m_powerRegenRemainder = 0;
    uint32_t m_manaRegenInterruptTime = 0;
    int32_t m_predictedPower[7] = {};
    bool IsDeadOrGhost() const { return false; }
    static float __stdcall GetPowerRegenBase(int32_t powerType, uint8_t inCombat);
    float GetPowerRegen(int32_t powerType, bool inCombat) const;
    int32_t GetPredictedPower(int32_t powerType) const { return m_predictedPower[powerType]; }
    void SetPredictedPower(int32_t powerType, int32_t value) {
        if (value > m_unit->m_unitFieldMaxpower[powerType]) value = m_unit->m_unitFieldMaxpower[powerType];
        m_predictedPower[powerType] = value;
    }
    void DoPowerRegen(int32_t powerType, uint32_t elapsed);
    void DoPowerRegen(int32_t powerType, uint32_t elapsed, uint32_t& remainder);
    void DoPowerRegen(uint32_t elapsed);
};
struct CGPlayer_C : CGUnit_C { CGPlayerData* m_player; };
const char* GetPowerString(uint32_t powerType) {
    const char* tokens[7] = { "MANA", "RAGE", "FOCUS", "ENERGY", "HAPPINESS", "RUNES", "RUNIC_POWER" };
    return powerType < 7 ? tokens[powerType] : "";
}
"""

DRIVER = r"""
static CGPlayerData s_playerData = {};

struct Unit {
    CGObjectData obj;
    CGUnitData data;
    CGPlayer_C unit;
    Unit(int type, int classId, int drawn) : obj{type == TYPEMASK_PLAYER ? 1u : 2u, TYPEMASK_UNIT | type}, data{} {
        data.m_unitFieldBytes0[1] = static_cast<uint8_t>(classId);
        data.m_unitFieldBytes0[3] = static_cast<uint8_t>(drawn);
        data.m_unitFieldFlags2 = 0x800;
        for (int i = 0; i < 7; i++) data.m_unitFieldMaxpower[i] = 1000;
        unit.m_obj = &obj;
        unit.m_unit = &data;
        unit.m_player = &s_playerData;
    }
    void Run(int ticks) { for (int i = 0; i < ticks; i++) unit.DoPowerRegen(100u); }
};

int main(int argc, char** argv) {
    const char* what = argv[1];
    if (!strcmp(what, "token")) {
        // token <player 1|0> <class> <slot>
        Unit u(atoi(argv[2]) ? TYPEMASK_PLAYER : 0, atoi(argv[3]), 0);
        const char* own = GetClassPowerString(&u.unit, atoi(argv[4]));
        printf("%s %s\n", GetUnitPowerString(&u.unit, atoi(argv[4])), own ? own : "-");
        return 0;
    }
    if (!strcmp(what, "mod")) {
        // mod <player 1|0> <class> <slot>
        Unit u(atoi(argv[2]) ? TYPEMASK_PLAYER : 0, atoi(argv[3]), 0);
        printf("%u\n", Spell_C_GetUnitPowerDisplayMod(&u.unit, atoi(argv[4])));
        return 0;
    }
    if (!strcmp(what, "party")) {
        // party <class cached 1|0> <class> <slot>: an out-of-range party member's divide
        g_nameCached = atoi(argv[2]) != 0;
        g_cachedName.m_class = atoi(argv[3]);
        printf("%u\n", PartyMemberPowerDisplayMod(WOWGUID(7), atoi(argv[4])));
        return 0;
    }
    if (!strcmp(what, "regen")) {
        // regen <player 1|0> <class> <drawn> <start> <field> <interrupted field> <in combat 1|0> <ticks> [<slot> <start> <field>]
        Unit u(atoi(argv[2]) ? TYPEMASK_PLAYER : 0, atoi(argv[3]), atoi(argv[4]));
        g_activePlayer = u.obj.m_guid;
        int drawn = atoi(argv[4]);
        u.unit.m_predictedPower[drawn] = atoi(argv[5]);
        u.data.m_unitFieldPowerRegenFlatModifier[drawn] = static_cast<float>(atof(argv[6]));
        u.data.m_unitFieldPowerRegenInterruptedFlatModifier[drawn] = static_cast<float>(atof(argv[7]));
        if (atoi(argv[8])) u.data.m_unitFieldFlags |= 0x80000;
        int second = -1;
        if (argc > 10) {
            second = atoi(argv[10]);
            u.unit.m_predictedPower[second] = atoi(argv[11]);
            u.data.m_unitFieldPowerRegenFlatModifier[second] = static_cast<float>(atof(argv[12]));
            u.data.m_unitFieldPowerRegenInterruptedFlatModifier[second] = static_cast<float>(atof(argv[12]));
        }
        u.Run(atoi(argv[9]));
        printf("%d %d\n", u.unit.m_predictedPower[drawn], second >= 0 ? u.unit.m_predictedPower[second] : -1);
        return 0;
    }
    return 2;
}
"""


class ClassPowerTokens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch = PATCH.read_text()
        cls.rows = [(int(c), int(p), t) for c, p, t in ROW.findall(HEADER.read_text())]
        cls.scales = {(int(c), int(p)): int(n) for c, p, n in SCALE.findall(HEADER.read_text())}
        reference = find_reference()
        if reference is None or shutil.which("g++") is None:
            raise unittest.SkipTest("needs reference/wowdecomp at the pin and g++")
        cls.tmp = tempfile.TemporaryDirectory()
        tree = Path(cls.tmp.name) / "wowdecomp"
        subprocess.run(["git", "clone", "-q", "--shared", str(reference), str(tree)], check=True)
        for patch in sorted(PATCHES.glob("*.patch"), key=lambda p: p.name):
            subprocess.run(["git", "-C", str(tree), "apply", str(patch)], check=True)
        spell = (tree / "WoW/Source/Magic/MagicClient/Spell_C.cpp").read_text()
        unit_c = (tree / "WoW/Source/Object/ObjectClient/Unit_C.cpp").read_text()
        unit = (tree / "WoW/Source/Object/Unit.cpp").read_text()
        cls.texts = {
            "Spell_C.cpp": spell,
            "Unit_C.cpp": unit_c,
            "ScriptEvents_Scripts.cpp": (tree / "WoW/Source/Ui/ScriptEvents_Scripts.cpp").read_text(),
            "Tooltip.cpp": (tree / "WoW/Source/UIUtil/Tooltip.cpp").read_text(),
            "SpellBookFrame_Scripts.cpp": (tree / "WoW/Source/Ui/SpellBookFrame_Scripts.cpp").read_text(),
        }
        body = "\n".join([
            STAND_IN,
            function(unit, "float __stdcall CGUnit::GetPowerRegenBase(").replace("CGUnit::", "CGUnit_C::"),
            function(unit, "float CGUnit::GetPowerRegen(").replace("CGUnit::", "CGUnit_C::"),
            function(spell, "const char* GetClassPowerString("),
            function(spell, "const char* GetUnitPowerString("),
            re.search(r"^static uint32_t s_powerDisplayMod\[7\] = .*;$", spell, re.M).group(0),
            function(spell, "uint32_t Spell_C_GetPowerDisplayMod("),
            function(spell, "uint32_t Spell_C_GetUnitPowerDisplayMod("),
            function(spell, "uint32_t Spell_C_GetClassPowerDisplayMod("),
            function(cls.texts["ScriptEvents_Scripts.cpp"], "static uint32_t PartyMemberPowerDisplayMod("),
            function(unit_c, "void CGUnit_C::DoPowerRegen(int32_t powerType, uint32_t elapsed) {"),
            function(unit_c, "void CGUnit_C::DoPowerRegen(int32_t powerType, uint32_t elapsed, uint32_t& remainder) {"),
            function(unit_c, "void CGUnit_C::DoPowerRegen(uint32_t elapsed) {"),
            DRIVER,
        ])
        cls.body = body
        cls.binaries = {}
        tables = (("sheet", HEADER.read_text()), ("second", cls.with_second_row(HEADER.read_text())),
                  ("fury_one", cls.with_fury_scale(HEADER.read_text(), 1)),
                  ("fury_ten", cls.with_fury_scale(HEADER.read_text(), 10)))
        for name, header in tables:
            root = Path(cls.tmp.name) / name
            (root / "Torment").mkdir(parents=True)
            (root / "Torment" / "class_power_tokens.h").write_text(header)
            (root / "harness.cpp").write_text(body)
            exe = root / "harness"
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wno-unused-function", "-I", str(root),
                            str(root / "harness.cpp"), "-o", str(exe)], check=True)
            cls.binaries[name] = exe

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    @staticmethod
    def with_row_after(header: str, pattern: str, added: str) -> str:
        # Adds a line after the one row the pattern finds; the table is found by what the row is, never by a count.
        found = re.findall(pattern, header, re.M)
        assert len(found) == 1, f"expected one row for {pattern}, found {len(found)}"
        return re.sub(pattern, lambda m: m.group(0) + "\n" + added, header, count=1, flags=re.M)

    @classmethod
    def with_second_row(cls, header: str) -> str:
        # The Monk (12, Spirit on Runic Power 6) given a second power on Mana (0), as a second slot will be.
        assert not re.search(r"^\s*\{12, 0, ", header, re.M), "the Monk already has a Mana row"
        changed = cls.with_row_after(header, r'^\s*\{12, 6, "[A-Z_]+"\},.*$', '    {12, 0, "SECOND_SLOT"},')
        return cls.with_row_after(changed, r"^\s*\{12, 6, \d+\},.*$", "    {12, 0, 1},")

    @staticmethod
    def with_fury_scale(header: str, units: int) -> str:
        # The Barbarian's Fury (1, Rage 1) stored `units` slot units a point: the sheet's storage_scale.
        pattern = r"^(\s*\{1, 1, )\d+(\},.*)$"
        assert len(re.findall(pattern, header, re.M)) == 1, "the sheet's Fury scale row moved"
        return re.sub(pattern, lambda m: f"{m.group(1)}{units}{m.group(2)}", header, flags=re.M)

    def run_harness(self, *args, table="sheet") -> list[str]:
        out = subprocess.run([str(self.binaries[table]), *map(str, args)], check=True, capture_output=True, text=True)
        return out.stdout.split()

    # The token

    def test_every_row_reports_its_token_for_a_player(self):
        self.assertTrue(self.rows)
        for class_id, power, token in self.rows:
            self.assertEqual(self.run_harness("token", 1, class_id, power), [token, token], f"class {class_id} slot {power}")

    def test_a_creature_of_a_row_class_keeps_the_stock_token(self):
        for class_id, power, _ in self.rows:
            self.assertEqual(self.run_harness("token", 0, class_id, power), [STOCK[power], "-"], f"class {class_id}")

    def test_other_slots_and_stock_classes_keep_the_stock_token(self):
        row_slots = {(c, p) for c, p, _ in self.rows}
        for class_id in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13):
            for power in range(7):
                if (class_id, power) not in row_slots:
                    self.assertEqual(self.run_harness("token", 1, class_id, power), [STOCK[power], "-"], f"class {class_id} slot {power}")

    # The display divide: stock shows Rage (1) and Runic Power (6) a tenth

    def test_a_class_power_divides_by_its_rows_scale(self):
        for (class_id, power), scale in self.scales.items():
            self.assertEqual(self.run_harness("mod", 1, class_id, power), [str(scale)], f"class {class_id} slot {power}")

    def test_a_scale_ten_row_divides_by_ten(self):
        # The Barbarian's Fury on Rage stored x10, as before its P2: true points, as the stock tenth gives.
        self.assertEqual(self.run_harness("mod", 1, 1, 1, table="fury_ten"), ["10"])

    def test_a_scale_one_row_divides_by_one(self):
        # The Wizard's Arcane Power (Energy) and the Crusader's Wrath, stored one unit a point.
        self.assertEqual(self.run_harness("mod", 1, 8, 3), ["1"])
        self.assertEqual(self.run_harness("mod", 1, 2, 3), ["1"])

    def test_a_row_moved_to_one_drops_the_tenth(self):
        # Fury once stored 1:1: Rage's stock tenth no longer applies.
        self.assertEqual(self.run_harness("mod", 1, 1, 1, table="fury_one"), ["1"])
        self.assertEqual(self.run_harness("mod", 0, 1, 1, table="fury_one"), ["10"])

    def test_a_class_without_a_row_keeps_the_stock_divide(self):
        # A Death Knight's Runic Power and a Rogue's Energy.
        self.assertEqual(self.run_harness("mod", 1, 6, 6), ["10"])
        self.assertEqual(self.run_harness("mod", 1, 4, 3), ["1"])

    def test_creatures_stock_classes_and_other_slots_keep_the_stock_divide(self):
        row_slots = {(c, p) for c, p, _ in self.rows}
        stock = [1, 10, 1, 1, 1000, 1, 10]
        for class_id, power, _ in self.rows:
            self.assertEqual(self.run_harness("mod", 0, class_id, power), [str(stock[power])], f"creature class {class_id}")
        for class_id in (1, 4, 6, 12, 13):
            for power in range(7):
                if (class_id, power) not in row_slots:
                    self.assertEqual(self.run_harness("mod", 1, class_id, power), [str(stock[power])], f"class {class_id} slot {power}")

    # An out-of-range party member: no unit, the class from the name cache, the slot from the party state

    def test_an_out_of_range_party_member_divides_like_the_same_unit_in_range(self):
        for table in ("sheet", "second", "fury_one", "fury_ten"):
            for class_id in range(1, 16):
                for power in range(7):
                    in_range = self.run_harness("mod", 1, class_id, power, table=table)
                    out_of_range = self.run_harness("party", 1, class_id, power, table=table)
                    self.assertEqual(out_of_range, in_range, f"{table}: class {class_id} slot {power}")

    def test_an_out_of_range_class_power_divides_by_its_rows_scale(self):
        for (class_id, power), scale in self.scales.items():
            self.assertEqual(self.run_harness("party", 1, class_id, power), [str(scale)], f"class {class_id} slot {power}")
        # Fury stored one unit a point shows its true number out of range; stored at ten a point it keeps the tenth.
        self.assertEqual(self.run_harness("party", 1, 1, 1, table="fury_one"), ["1"])
        self.assertEqual(self.run_harness("party", 1, 1, 1, table="fury_ten"), ["10"])

    def test_an_out_of_range_member_without_a_row_or_a_cached_class_keeps_the_stock_divide(self):
        self.assertEqual(self.run_harness("party", 1, 6, 6), ["10"])    # a Death Knight's Runic Power
        self.assertEqual(self.run_harness("party", 1, 4, 3), ["1"])     # a Rogue's Energy
        for class_id, power, _ in self.rows:
            stock = [1, 10, 1, 1, 1000, 1, 10][power]
            self.assertEqual(self.run_harness("party", 0, class_id, power), [str(stock)], f"class {class_id} not cached")

    def test_the_party_readers_use_the_class_divide_and_the_pet_reader_keeps_the_stock_one(self):
        script = self.texts["ScriptEvents_Scripts.cpp"]
        self.assertIn("power = state->m_power / PartyMemberPowerDisplayMod(unitGuid, state->m_powerType);", script)
        self.assertIn("power = state->m_maxPower / PartyMemberPowerDisplayMod(unitGuid, state->m_powerType);", script)
        self.assertIn("power = petState->m_power / Spell_C_GetPowerDisplayMod(petState->m_powerType);", script)
        self.assertIn("power = petState->m_maxPower / Spell_C_GetPowerDisplayMod(petState->m_powerType);", script)
        self.assertNotIn("state->m_power / Spell_C_GetPowerDisplayMod(state->m_powerType)", script)

    def test_a_party_divide_that_skips_the_row_is_noticed(self):
        # The broken copy: the helper falls back to the stock divide always. The Fury-at-one table then gives the tenth.
        old = "return Spell_C_GetClassPowerDisplayMod(name->m_class, powerType);"
        self.assertEqual(self.body.count(old), 1)
        root = Path(self.tmp.name) / "mutant"
        (root / "Torment").mkdir(parents=True)
        (root / "Torment" / "class_power_tokens.h").write_text(self.with_fury_scale(HEADER.read_text(), 1))
        (root / "harness.cpp").write_text(self.body.replace(old, "return Spell_C_GetPowerDisplayMod(powerType);"))
        subprocess.run(["g++", "-std=c++17", "-Wall", "-Wno-unused-function", "-I", str(root), str(root / "harness.cpp"), "-o", str(root / "harness")], check=True)
        out = subprocess.run([str(root / "harness"), "party", "1", "1", "1"], check=True, capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["10"])
        self.assertNotEqual(out, self.run_harness("party", 1, 1, 1, table="fury_one"))

    def test_unit_power_max_and_costs_use_the_unit_divide(self):
        script = self.texts["ScriptEvents_Scripts.cpp"]
        self.assertIn("unit->GetPredictedPower(powerType)) / Spell_C_GetUnitPowerDisplayMod(unit, powerType);", script)
        self.assertIn("m_unitFieldMaxpower[powerType] / Spell_C_GetUnitPowerDisplayMod(unit, powerType);", script)
        self.assertEqual(self.texts["Tooltip.cpp"].count("Spell_C_GetUnitPowerDisplayMod(caster, spell->m_powerType)"), 2)
        self.assertEqual(self.texts["SpellBookFrame_Scripts.cpp"].count("Spell_C_GetUnitPowerDisplayMod(caster, spell.m_powerType)"), 2)

    # The rate: player, class, drawn slot, start, field, interrupted field, in combat, ticks of 100 ms

    def test_a_class_power_moves_at_its_field_alone(self):
        # The Wizard on Energy: stock would add Energy's 10 a second to the field.
        self.assertEqual(self.run_harness("regen", 1, 8, 3, 0, 7.5, 7.5, 0, 10)[0], "7")

    def test_a_class_power_decays_at_a_negative_rate_to_zero(self):
        self.assertEqual(self.run_harness("regen", 1, 12, 6, 100, -20, 0, 0, 10)[0], "80")
        self.assertEqual(self.run_harness("regen", 1, 12, 6, 100, -20, 0, 0, 60)[0], "0")

    def test_in_combat_a_class_power_reads_the_interrupted_field(self):
        # Rage's stock in-combat base is 0 and its out-of-combat base decays: the Barbarian in combat moves at the
        # interrupted field, out of combat at the other one, never at Rage's decay.
        self.assertEqual(self.run_harness("regen", 1, 1, 1, 50, -10, 4, 1, 10)[0], "54")
        self.assertEqual(self.run_harness("regen", 1, 1, 1, 50, 0, 4, 0, 10)[0], "50")

    def test_a_stock_class_keeps_the_stock_base(self):
        # A Rogue on Energy: Energy's 10 a second plus its field.
        self.assertEqual(self.run_harness("regen", 1, 4, 3, 0, 0, 0, 0, 10)[0], "10")
        self.assertEqual(self.run_harness("regen", 1, 4, 3, 0, 2, 2, 0, 10)[0], "12")

    def test_a_creature_of_a_row_class_keeps_the_stock_base(self):
        # A warrior creature (class 1) out of combat: Rage's stock decay of 12.5 a second.
        self.assertEqual(self.run_harness("regen", 0, 1, 1, 100, 0, 0, 0, 10)[0], "87")

    def test_a_second_slot_regenerates_with_its_own_fraction(self):
        # Spirit at 3 a second on the drawn bar, the second slot at 5 a second: one second gives 3 and 5. A shared
        # fraction gives the drawn slot the second slot's leftovers.
        self.assertEqual(self.run_harness("regen", 1, 12, 6, 0, 3, 3, 0, 10, 0, 0, 5, table="second"), ["3", "5"])

    def test_a_second_slot_decays(self):
        self.assertEqual(self.run_harness("regen", 1, 12, 6, 0, 0, 0, 0, 10, 0, 50, -10, table="second"), ["0", "40"])

    def test_no_second_slot_without_a_row(self):
        # On the sheet's own table the Monk has no second row: Mana stays where it was.
        self.assertEqual(self.run_harness("regen", 1, 12, 6, 0, 3, 3, 0, 10, 0, 50, -10), ["3", "50"])

    # The readers

    def test_unit_power_type_reports_the_class_token(self):
        self.assertIn("lua_pushstring(L, GetUnitPowerString(unit, unit->m_unit->m_unitFieldBytes0[3]));", self.texts["ScriptEvents_Scripts.cpp"])

    def test_the_tooltip_cost_line_reads_the_class_token_with_the_stock_fallback(self):
        text = self.texts["Tooltip.cpp"]
        self.assertIn("GetClassPowerString(caster, spell->m_powerType)", text)
        self.assertIn('"%s_COST", classPower', text)
        self.assertIn('"%s_COST_PER_TIME", classPower', text)
        self.assertIn("*text ? text : FrameScript_GetText(token, -1, GENDER_NOT_APPLICABLE)", text)

    def test_the_not_enough_power_message_falls_back_to_the_stock_name(self):
        text = self.texts["Spell_C.cpp"]
        named = text.index("FrameScript_GetText(GetUnitPowerString(player, powerType)")
        fallback = text.index("power = FrameScript_GetText(GetPowerString(powerType)", named)
        self.assertLess(named, fallback)

    def test_get_power_string_itself_is_stock(self):
        self.assertNotIn("GetPowerString(uint32_t powerType) {", "".join(l for l in self.patch.splitlines() if l[:1] in "+-"))

    def test_both_workflows_copy_the_table_in(self):
        for workflow in WORKFLOWS:
            self.assertIn("copy-generated.ps1", workflow.read_text(), workflow.name)
        self.assertIn("mod-diablocraft/data/generated/class_power_tokens.h", (WOWDECOMP_DIR / "copy-generated.ps1").read_text())
        self.assertIn("'mod-diablocraft/data/generated/class_power_tokens.h'", WORKFLOWS[0].read_text())


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
