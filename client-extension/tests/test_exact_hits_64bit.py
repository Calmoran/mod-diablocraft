#!/usr/bin/env python3
"""Checks for client-extension/wowdecomp/patches/0011-exact-hits-in-64-bits.patch (diablocraft-jbeef, K4 of the client 64-bit numbers).

The server's core patch 0028 (docs/contracts/life-64bit-wire.md) writes the hit and its overkill of SMSG_SPELLNONMELEEDAMAGELOG
and of the damage ticks of SMSG_PERIODICAURALOG as 64 bits, with no cap. The rebuilt client has to read exactly those bytes and
carry the hit whole to the floating number, the combat text, the portrait and the log. Nothing here builds or runs the client (the
build is the client-rebuild workflow); the evidence is the client's own code, compiled on Linux:

  * the two parsers (`CombatLog::HandleSpellNonMeleeDamageLog`, `CombatLog::HandlePeriodicAuraLog`), `SendToCombatText` and
    `CGGameUI::SignalUnitCombat` are cut out of the patched tree (the series applied at the pin) and compiled with g++ against
    small stand-ins for the engine (the data store, the GUIDs, the spell database, the units), and fed packets built from the
    contract's field lists, with hits of 0, 4,294,967,295 (the old clamp), 4,294,967,296, 10,000,000,000 and 2^53; what the
    parsers hand on, and what the Lua events carry (read the way the engine's event formatter reads its arguments), must be the
    hit;
  * the field lists themselves are the contract's, from docs/contracts/life-64bit-wire.md and core patch 0028 when they are in
    the tree (they arrive with Part 1, diablocraft-sbxl), else the frozen copy below, which must equal them once they are.

Run: python3 client-extension/tests/test_exact_hits_64bit.py
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PATCHES = HERE.parent / "wowdecomp" / "patches"
CONTRACT = REPO / "docs" / "contracts" / "life-64bit-wire.md"
CORE_PATCH = REPO / "core-patches" / "0028-hits-64bit.patch"

# The contract's layouts after the packed target and attacker guids (and, for the periodic log, the spell id, the tick count and each
# tick's aura type), frozen from docs/contracts/life-64bit-wire.md at diablocraft-sbxl bcfa7e638. "u64 damage" is a field name after
# its type.
SPELL_DAMAGE_LOG = "uint32 spell; uint64 damage; uint64 overkill; uint8 school; uint32 absorbed; uint32 resisted; uint8 physicalLog; uint8 unused; uint32 blocked; uint32 hitInfo; uint8 debugFlags"
PERIODIC_DAMAGE_TICK = "uint64 damage; uint64 overkill; uint32 school; uint32 absorbed; uint32 resisted; uint8 critical"
STRUCT = {"uint8": "B", "uint32": "I", "uint64": "Q"}

HITS = [0, 4_294_967_295, 4_294_967_296, 10_000_000_000, 2 ** 53]


def fields(spec: str) -> list[tuple[str, str]]:
    return [tuple(part.split()) for part in spec.split(";") if part.strip()]


def pack(spec: str, **values: int) -> bytes:
    out = b""
    for kind, name in fields(spec):
        out += struct.pack("<" + STRUCT[kind], values.get(name, 0))
    return out


def packed_guid(guid: int) -> bytes:
    mask, body = 0, b""
    for i in range(8):
        byte = (guid >> (8 * i)) & 0xFF
        if byte:
            mask |= 1 << i
            body += bytes([byte])
    return bytes([mask]) + body


class Contract(unittest.TestCase):
    def test_the_contract_agrees_with_the_frozen_layouts(self):
        if not CONTRACT.exists():
            self.skipTest("docs/contracts/life-64bit-wire.md is not in this tree yet (diablocraft-sbxl)")
        text = " ".join(CONTRACT.read_text().split())
        for spec in (SPELL_DAMAGE_LOG, PERIODIC_DAMAGE_TICK):
            sequence = ", ".join(f"`{kind} {name}`" for kind, name in fields(spec) if name != "spell")
            self.assertIn(sequence, text)

    def test_core_patch_0028_writes_those_amounts_as_64_bits(self):
        if not CORE_PATCH.exists():
            self.skipTest("core-patches/0028-hits-64bit.patch is not in this tree yet (diablocraft-sbxl)")
        text = CORE_PATCH.read_text()
        self.assertGreaterEqual(len(re.findall(r"^\+\s+data << uint64\(damage\);", text, re.M)), 2)  # the spell log and the periodic tick
        self.assertGreaterEqual(len(re.findall(r"^\+\s+data << uint64\(LifeOverkill\(", text, re.M)), 2)


CPP = r"""
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

struct WOWGUID {
    uint64_t m_guid = 0;
    WOWGUID() = default;
    WOWGUID(uint64_t g) : m_guid(g) {}
    bool operator==(const WOWGUID& o) const { return m_guid == o.m_guid; }
};
struct SmartGUID : public WOWGUID {};

struct CDataStore {
    const uint8_t* m_buf = nullptr;
    uint32_t m_read = 0;
    uint32_t m_size = 0;
    template <typename T> CDataStore& Take(T& v) { std::memcpy(&v, m_buf + m_read, sizeof(T)); m_read += sizeof(T); return *this; }
    CDataStore& Get(uint8_t& v) { return Take(v); }
    CDataStore& Get(uint16_t& v) { return Take(v); }
    CDataStore& Get(uint32_t& v) { return Take(v); }
    CDataStore& Get(int32_t& v) { return Take(v); }
    CDataStore& Get(uint64_t& v) { return Take(v); }
    CDataStore& Get(float& v) { return Take(v); }
};
CDataStore& operator>>(CDataStore& msg, SmartGUID& guid) {
    uint8_t mask;
    msg.Get(mask);
    guid.m_guid = 0;
    for (int i = 0; i < 8; i++) {
        if (mask & (1 << i)) {
            uint8_t byte;
            msg.Get(byte);
            guid.m_guid |= static_cast<uint64_t>(byte) << (8 * i);
        }
    }
    return msg;
}

#define TYPEMASK_UNIT 8
struct SpellRec { int32_t m_attributes = 0; };
struct SpellDB { bool GetRecord(int32_t, SpellRec* rec) { rec->m_attributes = 0; return true; } } g_spellDB;
struct CGObject_C {};
struct CGUnit_C : CGObject_C {
    void AddWorldDamageText(const WOWGUID&, uint64_t amount, const SpellRec*, bool, bool, bool);
    void AddWorldText(const WOWGUID&, int32_t, const SpellRec*, bool) {}
};
CGUnit_C g_unit;
CGObject_C* ClntObjMgrObjectPtr(const WOWGUID&, int, const char*, int) { return &g_unit; }

std::vector<std::string> g_calls;
std::string fmt(const char* f, ...) { char b[256]; va_list a; va_start(a, f); vsnprintf(b, sizeof b, f, a); va_end(a); return b; }

void CGUnit_C::AddWorldDamageText(const WOWGUID&, uint64_t amount, const SpellRec*, bool crit, bool periodic, bool) {
    g_calls.push_back(fmt("worldtext %llu crit=%d periodic=%d", (unsigned long long)amount, crit, periodic));
}
void UnitCombatLogSpellDamage(const WOWGUID&, const WOWGUID&, int32_t, uint64_t damage, uint64_t overkill, uint32_t school, int32_t absorbed, int32_t resisted, int32_t blocked, uint32_t hitInfo, bool periodic, uint32_t) {
    g_calls.push_back(fmt("spelldamage %llu overkill=%llu school=%u absorbed=%d resisted=%d blocked=%d hitinfo=%u periodic=%d", (unsigned long long)damage, (unsigned long long)overkill, school, absorbed, resisted, blocked, hitInfo, periodic));
}
void UnitCombatLogSplitDamage(const WOWGUID&, const WOWGUID&, int32_t, uint64_t damage, uint64_t overkill, uint32_t school, int32_t absorbed, int32_t resisted, int32_t blocked, uint32_t hitInfo, uint32_t) {
    g_calls.push_back(fmt("splitdamage %llu overkill=%llu school=%u absorbed=%d resisted=%d blocked=%d hitinfo=%u", (unsigned long long)damage, (unsigned long long)overkill, school, absorbed, resisted, blocked, hitInfo));
}
struct CGGameUI {
    static void ShowCombatFeedback(const WOWGUID&, uint64_t amount, uint32_t schoolMask, uint32_t flags);
    static void SignalUnitCombat(const WOWGUID& guid, const char* action, uint64_t amount, uint32_t schoolMask, uint32_t flags);
    static void ShowHealingFeedback(const WOWGUID&, uint32_t, bool) {}
    static void ShowEnergizeFeedback(const WOWGUID&, uint32_t, uint32_t) {}
};
void CGGameUI::ShowCombatFeedback(const WOWGUID& guid, uint64_t amount, uint32_t schoolMask, uint32_t flags) {
    g_calls.push_back(fmt("feedback %llu school=%u flags=%u", (unsigned long long)amount, schoolMask, flags));
    SignalUnitCombat(guid, "WOUND", amount, schoolMask, flags);
}
void UnitCombatLogHeal(const WOWGUID&, const WOWGUID&, int32_t, uint32_t, uint32_t, uint32_t, bool, bool, uint32_t) {}
void UnitCombatLogEnergize(const WOWGUID&, const WOWGUID&, int32_t, uint32_t, uint32_t, bool, uint32_t) {}
void UnitCombatLogPowerDrain(const WOWGUID&, const WOWGUID&, int32_t, uint32_t, uint32_t, float, bool, uint32_t) {}

// The engine's event formatter, vFrameScript_SignalEvent, reads each argument the way its format letter says.
#define SCRIPT_EVENT_COMBAT_TEXT_UPDATE 1
#define SCRIPT_EVENT_UNIT_COMBAT 2
void FrameScript_SignalEvent(uint32_t index, const char* format, ...) {
    va_list args;
    va_start(args, format);
    std::string out = index == SCRIPT_EVENT_UNIT_COMBAT ? "event UNIT_COMBAT" : "event COMBAT_TEXT_UPDATE";
    for (; *format; format++) {
        if (*format != '%') continue;
        switch (format[1]) {
            case 'b': out += fmt(" b=%d", va_arg(args, int32_t)); break;
            case 'd': out += fmt(" d=%d", va_arg(args, int32_t)); break;
            case 'f': out += fmt(" f=%.0f", va_arg(args, double)); break;
            case 's': out += fmt(" s=%s", va_arg(args, const char*)); break;
            case 'u': out += fmt(" u=%u", va_arg(args, uint32_t)); break;
        }
    }
    va_end(args);
    g_calls.push_back(out);
}
const char* s_combatTextTypes[64];
static char* g_tokens[1] = {const_cast<char*>("target")};
char** Script_GetTokenIDsFromGUID(const WOWGUID&, int32_t* count) { *count = 1; return g_tokens; }

struct CombatLog {
    static int32_t HandleSpellNonMeleeDamageLog(CDataStore* msg, int32_t timeOffset);
    static int32_t HandlePeriodicAuraLog(CDataStore* msg, int32_t timeOffset);
};

@CODE@

int main() {
    for (int i = 0; i < 64; i++) s_combatTextTypes[i] = "T";
    unsigned which;
    unsigned long long hit;
    char kind[16];
    // Each line: <which> <hit>. which 1 = spell damage log, 2 = periodic log, 3 = SendToCombatText, 4 = SignalUnitCombat.
    // The packet bytes follow on stdin for 1 and 2 as hex on the same line.
    char hex[4096];
    while (std::scanf("%u %llu %4095s", &which, &hit, hex) == 3) {
        g_calls.clear();
        if (which == 1 || which == 2) {
            std::vector<uint8_t> bytes;
            for (size_t i = 0; hex[i] && hex[i + 1]; i += 2) { unsigned b; std::sscanf(hex + i, "%2x", &b); bytes.push_back(b); }
            CDataStore msg;
            msg.m_buf = bytes.data();
            msg.m_size = bytes.size();
            if (which == 1) CombatLog::HandleSpellNonMeleeDamageLog(&msg, 0); else CombatLog::HandlePeriodicAuraLog(&msg, 0);
            g_calls.push_back(fmt("consumed %u of %u", msg.m_read, msg.m_size));
        } else if (which == 3) {
            SendToCombatText(2, (uint64_t)hit);
            SendToCombatText(11, (uint64_t)hit, 7);
        } else {
            CGGameUI::SignalUnitCombat(WOWGUID(1), "WOUND", (uint64_t)hit, 4, 0x200);
        }
        for (auto& c : g_calls) std::printf("%s\n", c.c_str());
        std::printf("--\n");
    }
    return 0;
}
"""


def function(text: str, signature: str) -> str:
    start = text.index(signature)
    end = text.index("\n}\n", start) + 3
    return text[start:end]


def reference_checkout() -> Path | None:
    for root in (REPO, Path.home() / "diablocraft"):
        candidate = root / "reference" / "wowdecomp"
        if (candidate / ".git").exists():
            return candidate
    return None


class ClientCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reference = reference_checkout()
        if reference is None or shutil.which("g++") is None:
            raise unittest.SkipTest("needs reference/wowdecomp at the pin and g++")
        cls.tmp = tempfile.TemporaryDirectory()
        tree = Path(cls.tmp.name) / "wowdecomp"
        subprocess.run(["git", "clone", "-q", "--shared", str(reference), str(tree)], check=True)
        for patch in sorted(PATCHES.glob("*.patch"), key=lambda p: p.name):
            subprocess.run(["git", "-C", str(tree), "apply", str(patch)], check=True)
        combat = (tree / "WoW/Source/Object/ObjectClient/UnitCombatLog_C.cpp").read_text()
        gameui = (tree / "WoW/Source/Ui/GameUI.cpp").read_text()
        cls.code = "\n".join([
            function(combat, "void SendToCombatText(int32_t type, uint64_t amount, int32_t overflow) {"),
            function(combat, "void SendToCombatText(int32_t type, uint64_t amount) {"),
            function(combat, "int32_t CombatLog::HandleSpellNonMeleeDamageLog(CDataStore* msg, int32_t timeOffset) {"),
            function(combat, "int32_t CombatLog::HandlePeriodicAuraLog(CDataStore* msg, int32_t timeOffset) {"),
            function(gameui, "void CGGameUI::SignalUnitCombat(const WOWGUID& guid, const char* action, uint64_t amount, uint32_t schoolMask, uint32_t flags) {"),
        ])
        # The overloads and the parsers reference each other and the stand-ins above; SendToCombatText comes first.
        cls.decls = ("void SendToCombatText(int32_t type, uint64_t amount, int32_t overflow);\n"
                     "void SendToCombatText(int32_t type, uint64_t amount);\n")
        cls.binary = cls.build(cls.code)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def build(cls, code: str, name: str = "harness") -> Path:
        source = Path(cls.tmp.name) / f"{name}.cpp"
        source.write_text(CPP.replace("@CODE@", code).replace("struct CombatLog {", cls.decls + "struct CombatLog {", 1))
        exe = Path(cls.tmp.name) / name
        built = subprocess.run(["g++", "-std=c++17", "-w", "-fsanitize=address,undefined", str(source), "-o", str(exe)], capture_output=True, text=True)
        if built.returncode != 0:
            raise AssertionError("the cut-out client code does not compile:\n" + built.stderr[:3000])
        return exe

    @staticmethod
    def run_cases(exe: Path, lines: list[str]) -> list[list[str]]:
        run = subprocess.run([str(exe)], input="\n".join(lines) + "\n", capture_output=True, text=True)
        if run.returncode != 0:
            raise AssertionError("the harness failed:\n" + run.stderr[:3000])
        return [block.splitlines() for block in run.stdout.split("--\n") if block.strip()]

    # The packets ---------------------------------------------------------------------------------------------------------

    @staticmethod
    def spell_damage_packet(hit: int, overkill: int = 0, absorbed: int = 0, resisted: int = 0, blocked: int = 0, hit_info: int = 2) -> bytes:
        guids = packed_guid(0x1234) + packed_guid(0x5678)  # the target, then the caster
        return guids + pack(SPELL_DAMAGE_LOG, spell=100, damage=hit, overkill=overkill, school=4, absorbed=absorbed, resisted=resisted,
                            blocked=blocked, hitInfo=hit_info)

    @staticmethod
    def periodic_packet(hit: int, overkill: int = 0, absorbed: int = 0, resisted: int = 0) -> bytes:
        guids = packed_guid(0x1234) + packed_guid(0x5678)
        header = struct.pack("<II", 100, 1)  # the spell id and one tick
        return guids + header + struct.pack("<I", 3) + pack(PERIODIC_DAMAGE_TICK, damage=hit, overkill=overkill, school=4, absorbed=absorbed,
                                                              resisted=resisted, critical=1)

    def cases(self, exe: Path | None = None):
        lines = []
        for hit in HITS:
            lines.append(f"1 {hit} " + self.spell_damage_packet(hit, overkill=hit // 2, absorbed=5, resisted=6, blocked=7).hex())
            lines.append(f"2 {hit} " + self.periodic_packet(hit, overkill=hit // 2, absorbed=5, resisted=6).hex())
            lines.append(f"3 {hit} 00")
            lines.append(f"4 {hit} 00")
        return lines, self.run_cases(exe or self.binary, lines)

    def blocks(self, exe: Path | None = None) -> dict[tuple[int, int], list[str]]:
        lines, blocks = self.cases(exe)
        return {(int(line.split()[0]), int(line.split()[1])): block for line, block in zip(lines, blocks)}

    # The checks ----------------------------------------------------------------------------------------------------------

    def test_the_spell_damage_log_hands_the_whole_hit_on(self):
        for hit, block in ((h, self.blocks()[(1, h)]) for h in HITS):
            with self.subTest(hit=hit):
                joined = "\n".join(block)
                self.assertIn(f"spelldamage {hit} overkill={hit // 2} school=4 absorbed=5 resisted=6 blocked=7", joined)
                self.assertIn(f"feedback {hit} school=4", joined)
                if hit:
                    self.assertIn(f"worldtext {hit} crit=1 periodic=0", joined)
                self.assertRegex(joined, r"consumed (\d+) of \1")  # the whole packet, to the last byte

    def test_the_split_damage_form(self):
        # hitInfo bit 0x8: the "split damage" branch takes the same amounts.
        packet = self.spell_damage_packet(10_000_000_000, overkill=3, hit_info=0x8)
        blocks = self.run_cases(self.binary, [f"1 0 {packet.hex()}"])
        self.assertIn("splitdamage 10000000000 overkill=3", "\n".join(blocks[0]))

    def test_the_periodic_log_hands_the_whole_tick_on(self):
        for hit in HITS:
            with self.subTest(hit=hit):
                joined = "\n".join(self.blocks()[(2, hit)])
                self.assertIn(f"spelldamage {hit} overkill={hit // 2} school=4 absorbed=5 resisted=6 blocked=0", joined)
                self.assertIn(f"feedback {hit} school=4", joined)
                self.assertRegex(joined, r"consumed (\d+) of \1")

    def test_the_lua_events_carry_the_hit(self):
        for hit in HITS:
            with self.subTest(hit=hit):
                text = "\n".join(self.blocks()[(3, hit)])
                self.assertIn(f"event COMBAT_TEXT_UPDATE s=T f={hit}\n", text + "\n")
                self.assertIn(f"event COMBAT_TEXT_UPDATE s=T f={hit} d=7", text)
                unit = "\n".join(self.blocks()[(4, hit)])
                self.assertIn(f"event UNIT_COMBAT s=target s=WOUND s={'CRITICAL' if hit else ''} f={hit} d=4", unit)

    def test_the_old_cap_is_not_there(self):
        # 4,294,967,295 was the server's clamp (and -1 on a stock client); one more is a hit now.
        joined = "\n".join(self.blocks()[(1, 4_294_967_296)])
        self.assertIn("spelldamage 4294967296", joined)

    def test_broken_copies_are_caught(self):
        base = self.blocks()
        mutants = {
            "the hit is read as 32 bits": ("uint64_t damage = 0;\n    msg->Get(damage);\n    uint64_t overkill", "uint32_t damage = 0;\n    msg->Get(damage);\n    uint64_t overkill"),
            "the overkill is read as 32 bits": ("    uint64_t overkill = 0;\n    msg->Get(overkill);\n    uint8_t schoolByte", "    uint32_t overkill = 0;\n    msg->Get(overkill);\n    uint8_t schoolByte"),
            "a periodic tick's hit is read as 32 bits": ("                uint64_t damage = 0;\n                msg->Get(damage);\n                uint64_t overkill", "                uint32_t damage = 0;\n                msg->Get(damage);\n                uint64_t overkill"),
            "the portrait event sends the hit as %u": ('"%s%s%s%f%d", tokens[i], action, modifier, static_cast<double>(amount)', '"%s%s%s%u%d", tokens[i], action, modifier, amount'),
            "the combat text sends the hit as %u": ('"%s%f%d", s_combatTextTypes[type], static_cast<double>(amount), overflow', '"%s%u%d", s_combatTextTypes[type], amount, overflow'),
        }
        for index, (name, (old, new)) in enumerate(mutants.items()):
            with self.subTest(mutant=name):
                self.assertEqual(self.code.count(old), 1, f"the text to break is not in the cut-out code exactly once: {old[:50]!r}")
                try:
                    exe = self.build(self.code.replace(old, new), f"mutant{index}")
                    broken = self.blocks(exe)
                except (AssertionError, ValueError):
                    continue  # does not compile, or reads the packet out of step: noticed
                self.assertNotEqual(broken, base, f"{name} was not noticed")


class Series(unittest.TestCase):
    def test_the_header_and_the_definitions_agree(self):
        patch = (PATCHES / "0011-exact-hits-in-64-bits.patch").read_text()
        for needle in ("void SendToCombatText(int32_t type, uint64_t amount, int32_t overflow);",
                       "void SendToCombatText(int32_t type, uint64_t amount);",
                       "uint64_t damage, uint64_t overkill, uint32_t school, int32_t resisted",
                       "static void ShowCombatFeedback(const WOWGUID& guid, uint64_t amount",
                       "static void SignalUnitCombat(const WOWGUID& guid, const char* action, uint64_t amount",
                       "uint64_t amount, const SpellRec* spell, bool crit, bool periodic, bool spellColor);"):
            self.assertIn(needle, patch)


if __name__ == "__main__":
    sys.exit(unittest.main())
