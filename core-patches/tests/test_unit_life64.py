"""Core patches 0027 (Life in 64 bits), 0028 (hits in 64 bits) and 0029 (the Life tripwire): the Life arithmetic, run.

`Unit.h` and `Unit.cpp` are taken from the core's git at the pinned commit (core-commit.txt) and every numbered patch in
core-patches/ is applied to them in scratch, in number order, the way the core is built. The functions that carry the
rules are cut out of the patched text and compiled as they are: the helpers of Unit.h (`LifeToUInt32`, `CalculateLifePct`,
`ApplyThroughView` ...), `Unit::WriteHealthFields`, the clamp at the head of `Unit::SetHealth`, `Unit::ModifyHealth`,
`Unit::GetHealthGain`, `Unit::ExpectedLife` and `Unit::CheckLifeAfter`. A small `Unit` stand-in supplies only what those
bodies call (the two 32-bit update fields, the death state, the log), so nothing here models the arithmetic: the answers
come from a Python oracle in whole numbers and are compared with what the compiled functions return, over Life values on
both sides of 2^31, 2^32, 1e9 and 2^63.

The unpatched pin is run through the same harness (`Unit::ModifyHealth` with its `int32` casts) and must be wrong above
2,147,483,647 and right below it: that is the red the patch turns green, and it shows the stand-in is a fair host.

The tripwire is run twice: with the patched `ModifyHealth` it stays silent over every case, and with a narrowing put back
into that function (`curHealth` cut to 32 bits) it warns, which is how a missed narrowing shows. Then every single-rule
mutant of the extracted text must be caught (a mutant that survives fails the test).

TORMENT_CORE overrides the core repo the pinned files are read from. Nothing in the core is written; scratch is under
build/_agent-scratch.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get('TORMENT_CORE') or REPO / 'azerothcore-wotlk')
PIN = (REPO / 'core-commit.txt').read_text(encoding='utf-8').split()[0]
STACK = sorted((REPO / 'core-patches').glob('[0-9][0-9][0-9][0-9]-*.patch'))
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/unit-life64'
sys.path.insert(0, str(REPO / 'mod-diablocraft/scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

UNIT_H = 'src/server/game/Entities/Unit/Unit.h'
UNIT_CPP = 'src/server/game/Entities/Unit/Unit.cpp'
FILES = (UNIT_H, UNIT_CPP)
U32, I32, U64, I64 = 2**32 - 1, 2**31 - 1, 2**64 - 1, 2**63 - 1


# ---------------------------------------------------------------------------------------------------- the patched text
def pristine(path):
    shot = subprocess.run(['git', '-C', str(CORE), 'show', f'{PIN}:{path}'], capture_output=True)
    assert shot.returncode == 0, f'{path} at {PIN} is not in the core repo:\n' + shot.stderr.decode()
    return shot.stdout


def replay(stack):
    """{path: text} of Unit.h and Unit.cpp at the pin with the patches of `stack` applied in the order given."""
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
        for path in FILES:
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            (tree / path).write_bytes(pristine(path))
        include = [f'--include={path}' for path in FILES]
        for patch in stack:
            done = subprocess.run(['git', 'apply', *include, str(patch)], cwd=tree, capture_output=True, text=True)
            assert done.returncode == 0, f'{patch.name} does not apply on the patches before it:\n' + done.stderr
        return {path: (tree / path).read_text(encoding='utf-8') for path in FILES}
    finally:
        shutil.rmtree(tree)


def scan_end(text, open_at):
    """Index just past the brace that closes the one at `open_at`, skipping string and character literals and comments."""
    depth, i = 0, open_at
    while i < len(text):
        c = text[i]
        if text.startswith('//', i):
            i = text.index('\n', i)
            continue
        if text.startswith('/*', i):
            i = text.index('*/', i) + 2
            continue
        if c in '"\'':
            i += 1
            while text[i] != c:
                i += 2 if text[i] == '\\' else 1
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise AssertionError('unbalanced braces')


def function(text, signature):
    """The whole definition that starts with `signature`."""
    assert text.count(signature) == 1, f'{signature!r} occurs {text.count(signature)} times'
    start = text.index(signature)
    return text[start:scan_end(text, text.index('{', start))]


def pieces(files, pin_cpp):
    header, cpp = files[UNIT_H], files[UNIT_CPP]
    helpers = header[header.index('// Native 64-bit Life (core patch 0027)'):header.index('class Unit : public WorldObject')]
    set_health = function(cpp, 'void Unit::SetHealth(uint64 val)')
    cut = set_health.index('    m_health64 = val;\n    WriteHealthFields();\n') + len('    m_health64 = val;\n    WriteHealthFields();\n')
    return {
        'HELPERS': helpers,
        'WRITE': function(cpp, 'void Unit::WriteHealthFields()'),
        'SETHEALTH': set_health[:cut] + '}\n',
        'MODIFY': function(cpp, 'int64 Unit::ModifyHealth(int64 dVal)'),
        'GAIN': function(cpp, 'int64 Unit::GetHealthGain(int64 dVal)'),
        'EXPECTED': function(cpp, 'uint64 Unit::ExpectedLife(uint64 before, uint64 maximum, int64 change)'),
        'CHECK': function(cpp, 'void Unit::CheckLifeAfter(Unit const* source, SpellInfo const* spell, uint64 before, int64 change)'),
        'PINMODIFY': function(pin_cpp, 'int32 Unit::ModifyHealth(int32 dVal)').replace('Unit::ModifyHealth', 'Unit::ModifyHealthPin'),
        'PINGAIN': function(pin_cpp, 'int32 Unit::GetHealthGain(int32 dVal)').replace('Unit::GetHealthGain', 'Unit::GetHealthGainPin'),
    }


# ---------------------------------------------------------------------------------------------------- the oracle
GRID = sorted({0, 1, 2, 3, 100, 12345, I32 - 1, I32, I32 + 1, U32 - 1, U32, U32 + 1, 10**9 - 1, 10**9, 10**9 + 1,
               5 * 10**9, 10**12, 5 * 10**12, 2**53, 2**53 + 1, 10**17, I64 - 1, I64, I64 + 1, U64 - 1, U64})
MAXES = [m for m in GRID if m >= 1]


def lives(maximum):
    out = {0, 1, maximum - 1, maximum, maximum // 2, maximum // 3, (maximum * 999) // 1000}
    out |= {v for v in GRID if v <= maximum}
    return sorted(v for v in out if 0 <= v <= maximum)


def deltas(maximum):
    base = {1, 2, 7, 1000, I32 - 1, I32, I32 + 1, U32, 5 * 10**9, 10**12, maximum // 2, maximum // 3, maximum, maximum - 1, maximum + 1, I64}
    out = set()
    for d in base:
        if d <= I64:
            out |= {d, -d}
    out |= {-I64 - 1}
    return sorted(out)


def fields(maximum, cur):
    """The four update-field dwords: max low, max high, Life low, Life high."""
    return maximum & U32, maximum >> 32, cur & U32, cur >> 32


def moved(maximum, cur, delta):
    return max(0, min(maximum, cur + delta))


def mul_div(value, numerator, denominator, up):
    return min((value * numerator + (denominator - 1 if up else 0)) // denominator, U64)


def cases():
    proj, mod, pct, muldiv, expected = [], [], [], [], []
    for maximum in MAXES:
        for cur in lives(maximum):
            proj.append((maximum, cur) + fields(maximum, cur))
            for delta in deltas(maximum):
                after = moved(maximum, cur, delta)
                mod.append((maximum, cur, delta, after, after - cur))
                expected.append((cur, maximum, delta, after))
    for base in GRID:
        for p in (-5, 0, 1, 7, 10, 33, 35, 50, 100, 200, 1000):
            pct.append((base, p, 0 if p <= 0 else min(base * p // 100, U64)))
        for n, d in ((1, 1), (3, 7), (1000000000, 7), (U64, 3), (100, 100), (U32, U32 - 1)):
            for up in (False, True):
                muldiv.append((base, n, d, up, mul_div(base, n, d, up)))
    return proj, mod, pct, muldiv, expected


def literal(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value < 0:
        return f'(-{-value - 1}LL - 1)' if value == -2**63 else f'(-{-value}LL)'
    return f'{value}ULL'


def table(name, ctype, rows):
    body = ',\n'.join('    {' + ', '.join(literal(v) for v in row) + '}' for row in rows)
    return f'static {ctype} {name}[] = {{\n{body}\n}};\n'


# ---------------------------------------------------------------------------------------------------- the harness
HARNESS = r'''
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <sstream>
#include <string>
#include <vector>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
using int8 = std::int8_t; using int16 = std::int16_t; using int32 = std::int32_t; using int64 = std::int64_t;

enum UnitField : uint16 { UNIT_FIELD_HEALTH = 1, UNIT_FIELD_MAXHEALTH = 2, UNIT_FIELD_HEALTH_HI = 3, UNIT_FIELD_MAXHEALTH_HI = 4 };
enum class DeathState : uint8 { Alive, JustDied, Corpse, Dead };
struct SpellInfo { uint32 Id; };
struct ObjectGuid { uint64 value; std::string ToString() const { return std::to_string(value); } };

static std::vector<std::vector<std::string>> g_warnings;
template <class T> std::string text_of(T const& v) { std::ostringstream o; o << v; return o.str(); }
template <class... A> void warn_sink(char const*, char const*, A const&... a) { g_warnings.push_back({text_of(a)...}); }
#define LOG_WARN(category, ...) warn_sink(category, __VA_ARGS__)

@HELPERS@

class Unit
{
public:
    bool creature = true, controlled = false, player = false;
    DeathState death = DeathState::Alive;
    uint32 fieldHealth = 0, fieldMax = 0, fieldHealthHi = 0, fieldMaxHi = 0;
    uint64 m_health64 = 0, m_maxHealth64 = 0;
    uint32 entry = 7;

    bool IsCreature() const { return creature; }
    bool IsPlayer() const { return player; }
    bool IsControlledByPlayer() const { return controlled; }
    bool IsAlive() const { return death == DeathState::Alive; }
    DeathState getDeathState() const { return death; }
    uint64 GetHealth() const { return m_health64; }
    uint64 GetMaxHealth() const { return m_maxHealth64; }
    float GetHealthPct() const { return 0.0f; }
    uint32 GetEntry() const { return entry; }
    ObjectGuid GetGUID() const { return {entry}; }
    void SetUInt32Value(uint16 index, uint32 value)
    {
        switch (index)
        {
            case UNIT_FIELD_HEALTH: fieldHealth = value; break;
            case UNIT_FIELD_MAXHEALTH: fieldMax = value; break;
            case UNIT_FIELD_HEALTH_HI: fieldHealthHi = value; break;
            case UNIT_FIELD_MAXHEALTH_HI: fieldMaxHi = value; break;
        }
    }

    void WriteHealthFields();
    void SetHealth(uint64 val);
    int64 ModifyHealth(int64 dVal);
    int64 GetHealthGain(int64 dVal);
    static uint64 ExpectedLife(uint64 before, uint64 maximum, int64 change);
    void CheckLifeAfter(Unit const* source, SpellInfo const* spell, uint64 before, int64 change);
    int32 ModifyHealthPin(int32 dVal);
    int32 GetHealthGainPin(int32 dVal);
};

@WRITE@
@SETHEALTH@
@MODIFY@
@GAIN@
@EXPECTED@
@CHECK@
@PINMODIFY@
@PINGAIN@

@TABLES@

static int bad = 0;
#define FAIL(...) do { ++bad; if (bad <= 20) { std::printf("FAIL " __VA_ARGS__); std::printf("\n"); } } while (0)
#define U(v) static_cast<unsigned long long>(v)
#define S(v) static_cast<long long>(v)

int main()
{
    for (auto const& c : PROJ)
    {
        for (int kind = 0; kind < 3; ++kind)     // a creature, a player-owned creature and a player all get the real Life
        {
            Unit u; u.creature = kind != 2; u.player = kind == 2; u.controlled = kind == 1; u.m_maxHealth64 = c.max; u.m_health64 = c.cur;
            u.WriteHealthFields();
            if (u.fieldMax != c.expMax || u.fieldMaxHi != c.expMaxHi || u.fieldHealth != c.expCur || u.fieldHealthHi != c.expCurHi)
                FAIL("fields max=%llu cur=%llu kind=%d -> %u/%u %u/%u, want %llu/%llu %llu/%llu", U(c.max), U(c.cur), kind, u.fieldMaxHi, u.fieldMax, u.fieldHealthHi, u.fieldHealth, U(c.expMaxHi), U(c.expMax), U(c.expCurHi), U(c.expCur));
        }
    }
    for (auto const& c : MOD)
    {
        Unit u; u.m_maxHealth64 = c.max; u.m_health64 = c.cur;
        int64 gain = u.ModifyHealth(c.delta);
        if (u.m_health64 != c.after || gain != c.gain)
            FAIL("ModifyHealth max=%llu cur=%llu delta=%lld -> %llu/%lld, want %llu/%lld", U(c.max), U(c.cur), S(c.delta), U(u.m_health64), S(gain), U(c.after), S(c.gain));
        Unit g; g.m_maxHealth64 = c.max; g.m_health64 = c.cur;
        int64 would = g.GetHealthGain(c.delta);
        if (would != c.gain || g.m_health64 != c.cur)
            FAIL("GetHealthGain max=%llu cur=%llu delta=%lld -> %lld, want %lld", U(c.max), U(c.cur), S(c.delta), S(would), S(c.gain));
    }
    for (auto const& c : PCT)
        if (CalculateLifePct(c.base, c.pct) != c.want)
            FAIL("CalculateLifePct(%llu, %lld) = %llu, want %llu", U(c.base), S(c.pct), U(CalculateLifePct(c.base, c.pct)), U(c.want));
    for (auto const& c : MULDIV)
        if (LifeMulDiv(c.value, c.numerator, c.denominator, c.up) != c.want)
            FAIL("LifeMulDiv(%llu, %llu, %llu, %d) = %llu, want %llu", U(c.value), U(c.numerator), U(c.denominator), c.up, U(LifeMulDiv(c.value, c.numerator, c.denominator, c.up)), U(c.want));
    for (auto const& c : EXPECTED)
        if (Unit::ExpectedLife(c.before, c.max, c.change) != c.want)
            FAIL("ExpectedLife(%llu, %llu, %lld) = %llu, want %llu", U(c.before), U(c.max), S(c.change), U(Unit::ExpectedLife(c.before, c.max, c.change)), U(c.want));

    // the saturating casts
    for (uint64 v : {0ULL, 1ULL, 2147483646ULL, 2147483647ULL, 2147483648ULL, 4294967294ULL, 4294967295ULL, 4294967296ULL, 18446744073709551615ULL})
    {
        uint32 wantU = v > 4294967295ULL ? 4294967295u : static_cast<uint32>(v);
        int32 wantI = v > 2147483647ULL ? 2147483647 : static_cast<int32>(v);
        if (LifeToUInt32(v) != wantU) FAIL("LifeToUInt32(%llu) = %u", U(v), LifeToUInt32(v));
        if (LifeToInt32(v) != wantI) FAIL("LifeToInt32(%llu) = %d", U(v), LifeToInt32(v));
        if (LifeOverkill(v, 10) != (v > 10 ? v - 10 : 0)) FAIL("LifeOverkill(%llu, 10)", U(v));
    }

    // the view: a consumer that leaves its view alone leaves the exact amount; one that changes it replaces the amount
    { uint64 a = 5000000000ULL; ApplyThroughView(a, [](uint32&) {}); if (a != 5000000000ULL) FAIL("a consumer that touched nothing changed the amount to %llu", U(a)); }
    { uint64 a = 5000000000ULL; ApplyThroughView(a, [](uint32& v) { if (v != 4294967295u) v = 1; }); if (a != 5000000000ULL) FAIL("the view was not the saturated amount"); }
    { uint64 a = 5000000000ULL; ApplyThroughView(a, [](uint32& v) { v = 7; }); if (a != 7) FAIL("a changed view did not replace the amount: %llu", U(a)); }
    { uint64 a = 5000000000ULL; ApplyThroughView(a, [](uint32& v) { v = 0; }); if (a != 0) FAIL("a view set to 0 did not zero the amount"); }
    { uint64 a = 5000000000ULL; ApplyThroughView(a, [](uint32& v) { v = 4294967295u; }); if (a != 5000000000ULL) FAIL("a view set to what it was changed the amount"); }
    { uint64 a = 100; ApplyThroughView(a, [](uint32& v) { v = 100; }); if (a != 100) FAIL("an unchanged small amount moved"); }
    { uint64 a = 100; ApplyThroughView(a, [](uint32& v) { v += 1; }); if (a != 101) FAIL("a small amount was not replaced"); }

    // SetHealth's head: the clamp and the death state
    { Unit u; u.m_maxHealth64 = 1000; u.SetHealth(5000); if (u.m_health64 != 1000) FAIL("SetHealth above the max gave %llu", U(u.m_health64)); }
    { Unit u; u.m_maxHealth64 = 5000000000ULL; u.SetHealth(4000000000ULL); if (u.m_health64 != 4000000000ULL) FAIL("SetHealth cut a 64-bit Life to %llu", U(u.m_health64)); }
    { Unit u; u.m_maxHealth64 = 1000; u.death = DeathState::JustDied; u.SetHealth(500); if (u.m_health64 != 0) FAIL("a unit that just died kept Life"); }
    { Unit u; u.m_maxHealth64 = 1000; u.player = true; u.death = DeathState::Dead; u.SetHealth(500); if (u.m_health64 != 1) FAIL("a dead player did not get 1 Life"); }
    { Unit u; u.m_maxHealth64 = 1000; u.death = DeathState::Dead; u.SetHealth(500); if (u.m_health64 != 500) FAIL("a dead creature was not left alone"); }

    // the pin: ModifyHealth(int32) and GetHealthGain(int32), as they were
    int pinWrongBelow = 0, pinWrongAbove = 0;
    for (auto const& c : MOD)
    {
        if (c.delta > 2147483647LL || c.delta < -2147483647LL) continue;
        // int32 cannot hold the sum itself past 2^31, whatever the Life is: not what this probes
        if (c.max <= 2147483647ULL && (S(c.cur) + c.delta > 2147483647LL || S(c.cur) + c.delta < -2147483647LL)) continue;
        Unit u; u.m_maxHealth64 = c.max; u.m_health64 = c.cur;
        int32 gain = u.ModifyHealthPin(static_cast<int32>(c.delta));
        Unit g; g.m_maxHealth64 = c.max; g.m_health64 = c.cur;
        int32 would = g.GetHealthGainPin(static_cast<int32>(c.delta));
        bool right = u.m_health64 == c.after && gain == c.gain && would == c.gain;
        if (c.max <= 2147483647ULL) { if (!right) ++pinWrongBelow; }
        else if (!right) ++pinWrongAbove;
    }
    std::printf("pin wrong below 2^31: %d\n", pinWrongBelow);
    std::printf("pin wrong above 2^31: %d\n", pinWrongAbove);

    // the tripwire over every case: ModifyHealth, then the check
    g_warnings.clear();
    for (auto const& c : MOD)
    {
        Unit u; u.m_maxHealth64 = c.max; u.m_health64 = c.cur;
        u.ModifyHealth(c.delta);
        u.CheckLifeAfter(nullptr, nullptr, c.cur, c.delta);
    }
    std::printf("tripwire warnings over the grid: %zu\n", g_warnings.size());
    g_warnings.clear();
    { Unit u; u.player = true; u.creature = false; u.m_maxHealth64 = 100; u.m_health64 = 999; u.CheckLifeAfter(nullptr, nullptr, 10, 5);
      std::printf("tripwire warnings on a player: %zu\n", g_warnings.size()); }
    g_warnings.clear();
    { Unit u; u.death = DeathState::Dead; u.m_maxHealth64 = 100; u.m_health64 = 999; u.CheckLifeAfter(nullptr, nullptr, 10, 5);
      std::printf("tripwire warnings on a corpse: %zu\n", g_warnings.size()); }
    g_warnings.clear();
    { Unit u; u.m_maxHealth64 = 100; u.m_health64 = 999; SpellInfo spell{42}; Unit src; src.entry = 9;
      u.CheckLifeAfter(&src, &spell, 10, 5);
      std::printf("tripwire warnings on a creature: %zu\n", g_warnings.size());
      if (g_warnings.size() == 1)
      {
          auto const& w = g_warnings[0];
          // entry, guid, Life after, expected, before, change, max, source, spell, times
          std::printf("tripwire line: %s\n", [&] { std::string s; for (auto const& x : w) s += x + "|"; return s; }().c_str());
      } }

    std::printf("mismatches=%d\n", bad);
    return bad ? 1 : 0;
}
'''


def build_harness(tag, parts, rows):
    proj, mod, pct, muldiv, expected = rows
    tables = (
        'struct ProjRow { uint64 max, cur; uint64 expMax, expMaxHi, expCur, expCurHi; };\n' + table('PROJ', 'ProjRow const', proj) +
        'struct ModRow { uint64 max, cur; int64 delta; uint64 after; int64 gain; };\n' + table('MOD', 'ModRow const', mod) +
        'struct PctRow { uint64 base; int64 pct; uint64 want; };\n' + table('PCT', 'PctRow const', pct) +
        'struct MulDivRow { uint64 value, numerator, denominator; bool up; uint64 want; };\n' + table('MULDIV', 'MulDivRow const', muldiv) +
        'struct ExpRow { uint64 before, max; int64 change; uint64 want; };\n' + table('EXPECTED', 'ExpRow const', expected))
    source = HARNESS
    for key, value in parts.items():
        source = source.replace(f'@{key}@', value)
    source = source.replace('@TABLES@', tables)
    OUT.mkdir(parents=True, exist_ok=True)
    cpp, binary = OUT / f'{tag}.cpp', OUT / f'{tag}.bin'
    cpp.write_text(source, encoding='utf-8')
    done = subprocess.run(['g++', '-std=c++20', '-O1', '-Wno-narrowing', '-o', str(binary), str(cpp)], capture_output=True, text=True)
    return done, binary


def run(tag, parts, rows):
    done, binary = build_harness(tag, parts, rows)
    assert done.returncode == 0, f'{tag} does not compile:\n' + done.stderr[-3000:]
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode, ran.stdout


def number(output, label):
    return int(re.search(re.escape(label) + r': (\d+)', output)[1])


# ---------------------------------------------------------------------------------------------------- the test
class Life64(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = replay(STACK)
        cls.pin_cpp = pristine(UNIT_CPP).decode('utf-8')
        cls.parts = pieces(cls.files, cls.pin_cpp)
        cls.rows = cases()

    def test_the_functions_answer_the_oracle_and_the_tripwire_is_quiet(self):
        code, out = run('clean', self.parts, self.rows)
        self.assertEqual(0, code, out)
        self.assertIn('mismatches=0', out)
        self.assertEqual(0, number(out, 'tripwire warnings over the grid'))
        self.assertEqual(0, number(out, 'tripwire warnings on a player'))
        self.assertEqual(0, number(out, 'tripwire warnings on a corpse'))
        self.assertEqual(1, number(out, 'tripwire warnings on a creature'))
        # the warning names the creature entry, its guid, Life after, expected, before, change, max, the source and the spell
        self.assertRegex(out, r'tripwire line: 7\|7\|999\|15\|10\|5\|100\|9\|42\|1\|')

    def test_the_pin_is_wrong_above_two_to_the_31_and_right_below(self):
        _, out = run('clean-pin', self.parts, self.rows)
        self.assertEqual(0, number(out, 'pin wrong below 2^31'), 'the stand-in is not a fair host for the pin')
        self.assertGreater(number(out, 'pin wrong above 2^31'), 100, 'the pin was not wrong above 2,147,483,647')

    def test_a_narrowing_put_back_is_caught_by_the_tripwire(self):
        parts = dict(self.parts)
        parts['MODIFY'] = parts['MODIFY'].replace('uint64 const curHealth = GetHealth();', 'uint64 const curHealth = static_cast<uint32>(GetHealth());')
        self.assertNotEqual(parts['MODIFY'], self.parts['MODIFY'])
        code, out = run('narrowed', parts, self.rows)
        self.assertGreater(number(out, 'tripwire warnings over the grid'), 100, out)
        # and the oracle fails too: the warning is the tripwire's own find, not the only line of defence
        self.assertNotEqual(0, code)

    def test_every_single_rule_mutant_is_caught(self):
        def swap(key, old, new, label):
            self.assertEqual(1, self.parts[key].count(old), f'{label}: {old!r} is not in {key} exactly once')
            return label, key, old, new
        mutants = [
            swap('WRITE', 'SetUInt32Value(UNIT_FIELD_MAXHEALTH, static_cast<uint32>(m_maxHealth64));', 'SetUInt32Value(UNIT_FIELD_MAXHEALTH, LifeToUInt32(m_maxHealth64));', 'the low max dword saturates'),
            swap('WRITE', 'SetUInt32Value(UNIT_FIELD_HEALTH, static_cast<uint32>(m_health64));', 'SetUInt32Value(UNIT_FIELD_HEALTH, LifeToUInt32(m_health64));', 'the low Life dword saturates'),
            swap('WRITE', 'static_cast<uint32>(m_maxHealth64 >> 32)', 'static_cast<uint32>(m_maxHealth64 >> 31)', 'the high max dword is shifted wrong'),
            swap('WRITE', 'static_cast<uint32>(m_health64 >> 32)', '0', 'the high Life dword is not written'),
            swap('WRITE', 'SetUInt32Value(UNIT_FIELD_HEALTH_HI,', 'SetUInt32Value(UNIT_FIELD_MAXHEALTH_HI,', 'the high Life goes in the high max field'),
            swap('WRITE', 'SetUInt32Value(UNIT_FIELD_MAXHEALTH_HI, static_cast<uint32>(m_maxHealth64 >> 32));', '', 'the high max dword is not written'),
            swap('MODIFY', 'uint64 const curHealth = GetHealth();', 'uint64 const curHealth = static_cast<uint32>(GetHealth());', 'Life cut to 32 bits'),
            swap('MODIFY', 'if (loss >= curHealth)', 'if (loss < curHealth)', 'a hit that kills does not'),
            swap('MODIFY', 'static_cast<uint64>(dVal) < room', 'true', 'a heal past the max is not held to it'),
            swap('MODIFY', 'SetHealth(curHealth - loss);', 'SetHealth(curHealth + loss);', 'a hit heals'),
            swap('GAIN', 'return loss >= curHealth ? -static_cast<int64>(curHealth) : dVal;', 'return dVal;', 'the gain of a killing hit is the whole hit'),
            swap('HELPERS', 'value > std::numeric_limits<uint32>::max() ? std::numeric_limits<uint32>::max() : static_cast<uint32>(value)',
                 'static_cast<uint32>(value)', 'LifeToUInt32 wraps'),
            swap('HELPERS', 'static_cast<uint64>(std::numeric_limits<int32>::max()) ? std::numeric_limits<int32>::max()',
                 'static_cast<uint64>(std::numeric_limits<int32>::max()) ? std::numeric_limits<int32>::max() - 1', 'LifeToInt32 stops one short'),
            swap('HELPERS', 'return pct <= 0 ? 0 : LifeMulDiv(base, static_cast<uint64>(pct), 100);',
                 'return pct <= 0 ? 0 : static_cast<uint64>(base * static_cast<float>(pct) / 100.0f);', 'the percent is float math'),
            swap('HELPERS', '(roundUp ? denominator - 1 : 0)', '(roundUp ? 0 : denominator - 1)', 'the rounding is swapped'),
            swap('HELPERS', 'return damage > health ? damage - health : 0;', 'return damage - health;', 'overkill wraps'),
            swap('HELPERS', 'if (after != before)\n        amount = after;', 'amount = after;', 'a consumer that touched nothing narrows the amount'),
            swap('SETHEALTH', 'if (maxHealth < val)', 'if (maxHealth > val)', 'Life is not held to the max'),
            swap('SETHEALTH', 'if (getDeathState() == DeathState::JustDied)\n        val = 0;', 'if (false)\n        val = 0;', 'a unit that just died keeps Life'),
            swap('EXPECTED', 'return loss >= before ? 0 : before - loss;', 'return loss >= before ? 0 : before + loss;', 'the tripwire expects a hit to heal'),
            swap('EXPECTED', 'static_cast<uint64>(change) < room ? before + static_cast<uint64>(change) : maximum', 'before + static_cast<uint64>(change)',
                 'the tripwire expects a heal past the max'),
            swap('CHECK', 'if (!IsCreature() || !IsAlive())\n        return;', 'if (!IsAlive())\n        return;', 'the tripwire watches players'),
            swap('CHECK', 'if (!IsCreature() || !IsAlive())\n        return;', 'if (!IsCreature())\n        return;', 'the tripwire watches corpses'),
            swap('CHECK', 'if (GetHealth() == expected)\n        return;', 'if (GetHealth() != expected)\n        return;', 'the tripwire is inverted'),
            swap('CHECK', 'if (times > 100 && times % 1000 != 0)\n        return;', 'return;', 'the tripwire never speaks'),
        ]
        survived = []
        for index, (label, key, old, new) in enumerate(mutants):
            parts = dict(self.parts)
            parts[key] = parts[key].replace(old, new)
            done, binary = build_harness(f'mutant-{index}', parts, self.rows)
            if done.returncode != 0:
                survived.append(f'{label}: does not compile ({done.stderr[-200:]})')
                continue
            ran = harness_env.run([str(binary)], capture_output=True, text=True)
            warned = number(ran.stdout, 'tripwire warnings over the grid') != 0 or number(ran.stdout, 'tripwire warnings on a player') != 0 \
                or number(ran.stdout, 'tripwire warnings on a corpse') != 0 or number(ran.stdout, 'tripwire warnings on a creature') != 1
            if ran.returncode == 0 and not warned:
                survived.append(label)
        self.assertEqual([], survived, 'mutants nothing noticed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
