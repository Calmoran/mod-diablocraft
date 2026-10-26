#pragma once
// Seven-Sided Strike and its five runes. The cast deals nothing itself: Monk::Delayed
// takes it, and the strikes come one at a time on the core's own event queue (Player::m_Events), the series shape of
// the Wizard's Meteor Shower (a hit at delay + i x interval). The rules that need no core type are inline here, so
// tests/monk_seven_sided_strike compiles this exact code; the cast itself is dc_monk_seven_sided_strike.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk::SevenSided
{
    // "dealing {damage_pct} weapon damage over {hit_count} strikes": the total split evenly over the strikes
    // (Power/Monk_SevenSidedStrike.pow SF_3 8.11 a strike = 5677 / 7; Sudden Assault's 8285 / 7 is SF_3 x SF_11).
    inline double StrikePct(double totalPct, double strikes)
    {
        return strikes >= 1 ? totalPct / std::floor(strikes) : 0.0;
    }

    // How many strikes a cast lands: the sheet's `hit_count` and the whole strikes the worn item adds (Lion's Claw, `extra_strikes`, 0 with
    // none). Each strike keeps the size StrikePct gave it from the sheet's count alone, so the extra strikes are extra damage.
    inline unsigned Strikes(double sheetCount, double extra)
    {
        return static_cast<unsigned>(std::floor(std::max(0.0, sheetCount))) + static_cast<unsigned>(std::floor(std::max(0.0, extra)));
    }

    // When strike `i` (0-based) lands, in ms after the cast: the first after `firstMs`, each next `intervalMs` later.
    inline std::uint64_t StrikeAtMs(unsigned i, double firstMs, double intervalMs)
    {
        return static_cast<std::uint64_t>(std::max(0.0, firstMs) + i * std::max(0.0, intervalMs) + 0.5);
    }

    // The enemy the next strike goes to: the first one still standing after the one struck last, wrapping round the
    // list, so seven strikes on one enemy all hit it and on three go 3, 2, 2 (d3planner simulator monk.js:889-899 at
    // the pin, the tick's "next target after data.target"). `last` is -1 before the first strike. -1 when none stands.
    inline int NextTarget(int last, std::vector<bool> const& standing)
    {
        int const n = static_cast<int>(standing.size());
        for (int step = 1; step <= n; ++step)
        {
            int const i = ((last < 0 ? -1 : last) + step) % n;
            if (standing[i])
                return i;
        }
        return -1;
    }

    // Incinerate's burn: whole ticks of `tickSeconds` in `seconds`, each dealing its share of the total. 0 ticks for an
    // open tick length (a blank tunable): no burn.
    inline unsigned BurnTicks(double seconds, double tickSeconds)
    {
        return tickSeconds > 0 && seconds > 0 ? static_cast<unsigned>(std::floor(seconds / tickSeconds + 1e-9)) : 0;
    }

    inline double TickPct(double totalPct, unsigned ticks)
    {
        return ticks ? totalPct / ticks : 0.0;
    }

    // The cast side (dc_monk_seven_sided_strike.cpp).
    bool Is(std::uint32_t spellId);
    // One strike's percentage, the shell's own hit (the loader's and `.dc hit`'s): the skill's total over its strikes,
    // Fulminating Onslaught's 877% a strike as it is, Incinerate's strike the skill's (its own 630% is the burn).
    std::optional<double> BasePct(std::uint32_t spellId);
    // Whether the press may cast (Combat's OnSpellCheckCast, before the cost and the cooldown): an enemy within the
    // sheet's 25 yards, or Sudden Assault's target within its teleport. True for every other spell.
    bool CanCast(Player* player, std::uint32_t spellId);
    // The cast resolved with `targets` (the enemies within the sheet's 25 yards) and the unit it was aimed at, if any:
    // Sudden Assault's teleport, then the strikes on the event queue, the Monk immune until the last. True for every Seven-Sided Strike spell.
    bool Start(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, Unit* aimed);
} // namespace DC::Combat::Monk::SevenSided
