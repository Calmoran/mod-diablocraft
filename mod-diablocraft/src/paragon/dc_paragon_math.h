#ifndef DC_PARAGON_MATH_H
#define DC_PARAGON_MATH_H
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (800): rows the paragon XP table must have; Row-count assertion.
// Constant (10000, 100000000): fixed-point scale for hundredths of a percent; Integer arithmetic.
// Constant (1, 10, 100): allowed bulk allocation steps; D3's bulk steps; UI-facing.
namespace DC::Paragon
{
using XP = std::uint64_t;
inline void Need(bool ok, char const* error) { if (!ok) throw std::runtime_error(error); }
// security.md G1: a respec is free (D3), so the only brake on a client that
// sends it in a loop is a short per-player gap. `last` is the time of the
// previous attempt, or nothing on the first; a cooldown of 0 means no gap.
inline bool RespecCooling(std::uint64_t nowMs, bool hasLast, std::uint64_t lastMs, std::uint64_t cooldownMs)
{
    return hasLast && nowMs >= lastMs && nowMs - lastMs < cooldownMs;
}
// security.md G1 gaps: the module lock is not held while a database commit is awaited.
// Releases `lock`, runs `wait`, and takes it again on every exit, a throw included.
template<class Lock, class Wait> auto WithoutLock(Lock& lock, Wait&& wait)
{
    struct Relock
    {
        Lock& held;
        ~Relock() { held.lock(); }
    };
    lock.unlock();
    Relock relock{lock};
    return wait();
}
inline XP Add(XP a, XP b)
{
    Need(b <= std::numeric_limits<XP>::max() - a, "Paragon XP capacity exceeded.");
    return a + b;
}
inline XP Multiply(XP a, XP b)
{
    Need(!b || a <= std::numeric_limits<XP>::max() / b, "Paragon XP capacity exceeded.");
    return a * b;
}
// Percentages are integer hundredths of a percent. Divide once, rounding down.
inline XP KillXP(XP base, XP tierPct, unsigned members, unsigned perMember, unsigned partyCap)
{
    XP party = std::min<XP>(Multiply(members ? members - 1 : 0, perMember), partyCap);
    return Multiply(Multiply(base, Add(10000, tierPct)), Add(10000, party)) / 100000000;
}
// #55. What the stat sheet's Experience Bonus does to one award.
//
// stats.csv: "Increases experience gained from monster kills", "% XP bonus is
// additive across gear and gems", "Flat XP per kill adds directly per slain
// monster". The sheet has already divided the percentage by the level-70
// penalty when it publishes it (dc_common.cpp:207, `xp_divisor`), so what
// arrives here is the effective percentage and nothing further is applied to
// it.
//
// Percent first, then the flat add. D3's source is silent on the order and
// the rule is percent then flat; it matters, because a flat add multiplied
// by the percentage would pay the bonus on a number the bonus is not for.
//
// Hundredths of a percent, the same fixed point KillXP uses, so the arithmetic
// stays integer and the overflow guards still hold. Two roundings, both
// bounded, and they do not round the same way: the sheet's percentage goes to
// the NEAREST hundredth of a percent, up or down, and is out by at most 0.005%
// of the award either way; the product then floors, which only ever loses, and
// at most 1 XP. Flat XP is whole XP and is not rounded at all.
inline XP Hundredths(double percent)
{
    if (!(percent > 0.0))
        return 0;
    double const scaled = percent * 100.0 + 0.5;
    Need(scaled < 1e18, "XP bonus percentage is out of range.");
    return XP(scaled);
}

inline XP AwardXP(XP base, XP bonusHundredths, XP flatPerKill)
{
    return Add(Multiply(base, Add(10000, bonusHundredths)) / 10000, flatPerKill);
}

// Pylons and shrines P1 (docs/proposals/pylons.md 4.3): the Enlightened Shrine's percent more
// experience from the wearer's own kills is "multiplicative with items giving a +% bonus to EXP" (Fandom), so it
// multiplies the finished award, the sheet's gear bonus and flat XP already in.
inline XP Enlightened(XP award, XP pctHundredths)
{
    return Multiply(award, Add(10000, pctHundredths)) / 10000;
}

// 10 P2: points cycle Core/Offense/Defense/Utility until the
// paragon level `coreOnlyAfterLevel`, after which every further point is Core.
// The number is published (data/d3/character_rules.csv, dc_tunables row
// paragon/core_only_after_level) and is passed in rather than read here: this
// header is pure arithmetic and is compiled on its own by
// scripts/tests/paragon/, with no database and no core behind it.
inline std::array<unsigned, 4> Earned(unsigned level, unsigned coreOnlyAfterLevel)
{
    unsigned cycling = std::min(level, coreOnlyAfterLevel);
    std::array<unsigned, 4> result{};
    for (unsigned i = 0; i < 4; ++i) result[i] = (cycling + 3 - i) / 4;
    result[0] += level - cycling;
    return result;
}
struct Progress { unsigned level = 0; XP xp = 0; };
inline XP NextXP(unsigned level, std::vector<XP> const& table)
{
    Need(table.size() >= 800, "Paragon XP table is incomplete.");
    if (level < table.size()) return table[level];
    // 10 P5: continue the last per-level step, derived from the CSV, beyond 800.
    XP step = table.back() - table[table.size() - 2];
    return Add(table.back(), Multiply(step, XP(level) - table.size() + 1));
}
inline Progress Grant(Progress state, XP amount, std::vector<XP> const& table)
{
    state.xp = Add(state.xp, amount);
    for (XP next = NextXP(state.level, table); state.xp >= next; next = NextXP(state.level, table))
    {
        Need(state.level < std::numeric_limits<unsigned>::max(), "Paragon level capacity exceeded.");
        state.xp -= next;
        ++state.level;
    }
    return state;
}
// The stock XP bar draws PLAYER_XP / PLAYER_NEXT_LEVEL_XP,
// which are 32-bit update fields (core UpdateFields.h: "Size: 1, Type: INT"), and
// the only setter is SetUInt32Value, so a 64-bit XP handed to it truncates modulo
// 2^32 and makes the bar wrap backwards. Per-level thresholds in paragon_xp.csv
// pass 2^32 at level 585 (4,300,320,000) and keep growing, so both numbers are
// divided by the same power of two: the smallest one that makes the threshold fit.
// Levels 1-584 therefore use shift 0 and the client's own XP digits are the exact
// Paragon digits; beyond that the pair stays proportional and only low bits are
// lost. The exact decimal strings remain on the Paragon screen either way.
struct Displayed { std::uint32_t xp = 0, next = 0; };
inline Displayed Display(XP xp, XP next)
{
    Need(next > 0, "Paragon XP threshold must be positive.");
    // Grant() keeps xp below the threshold, so this only guards the display: a
    // full bar, never an exception thrown from the per-tick player update hook.
    if (xp > next) xp = next;
    unsigned shift = 0;
    XP const limit = std::numeric_limits<std::uint32_t>::max();
    while ((next >> shift) > limit) ++shift;
    return {std::uint32_t(xp >> shift), std::uint32_t(next >> shift)};
}
inline unsigned Change(unsigned current, unsigned amount, bool allocate, unsigned available, unsigned cap)
{
    Need(amount == 1 || amount == 10 || amount == 100, "Choose 1, 10, or 100 points.");
    if (!allocate) { Need(amount <= current, "Not enough allocated points to remove that amount."); return current - amount; }
    Need(amount <= available, "Not enough unspent points in this category.");
    Need(amount <= std::numeric_limits<unsigned>::max() - current && (!cap || current + amount <= cap),
         "That allocation exceeds the stat's point cap.");
    return current + amount;
}
}
#endif
