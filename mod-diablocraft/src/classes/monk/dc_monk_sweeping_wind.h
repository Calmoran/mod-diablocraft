#pragma once
// Sweeping Wind's rules that need no core type, header-only so
// tests/monk_sweeping_wind compiles this exact code: the damage of one tick, the stacks, when the tornado spawns,
// how many ticks a tornado lasts, the whole-second Spirit pay, and Master of Wind's streak of consecutive damage.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::Wind
{
    // "continuously deals {damage_pct:base} weapon damage" for each stack (Power/Monk_SweepingWind.pow SF_5, SF_14
    // 'Damage Increase Per Second Per Stack'): the sheet's percentage is a second's worth for one stack, so a tick of
    // `tickSeconds` pays that share of it for every stack the vortex holds.
    inline double TickPct(double perStackPct, unsigned stacks, double tickSeconds)
    {
        return perStackPct * stacks * tickSeconds;
    }

    // "Every hit of a Spirit Generator adds a stack, up to {max_stacks_count}" (D3's live text; the sheet's "a Critical Hit has a
    // chance" is the older one): the stacks after an attack, which only an attack that generates Spirit changes.
    inline unsigned StacksAfter(unsigned stacks, unsigned maxStacks, bool generates)
    {
        return generates ? std::min(stacks + 1, maxStacks) : stacks;
    }

    // Vengeful Wind: "Increases the maximum stack count of Sweeping Wind by {raise}": the vortex's
    // maximum is the sheet's max_stacks_count and the worn item's whole stacks on top (0 with none). Every cap of the
    // stacks reads it.
    inline unsigned MaxStacks(double sheetMax, double raise)
    {
        return static_cast<unsigned>(std::lround(std::max(0.0, sheetMax) + std::max(0.0, raise)));
    }

    // Cyclone: the attack of a Spirit Generator that finds the vortex already at its maximum spawns the tornado.
    inline bool SpawnsTornado(unsigned stacks, unsigned maxStacks, bool generates)
    {
        return generates && stacks >= maxStacks;
    }

    // How many ticks of `tickSeconds` fit in `seconds` (a tornado's 3 seconds at its 0.6 second arcs).
    inline unsigned Ticks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? static_cast<unsigned>(std::floor(seconds / tickSeconds + 1e-9)) : 0u;
    }

    // Inner Storm: "you gain {regen_per_second_resource} Spirit per second": paid once a whole second, on the tick that
    // completes it (tick `index` counted from 1).
    inline bool PaysSpirit(unsigned index, double tickSeconds)
    {
        if (index == 0 || tickSeconds <= 0)
            return false;
        return std::floor(index * tickSeconds + 1e-9) > std::floor((index - 1) * tickSeconds + 1e-9);
    }

    // Whether tick `index` (counted from 1) of `tickSeconds` completes a whole second: the clock of Monkey King's Garb 4-piece's decoy.
    inline bool CompletesSecond(unsigned index, double tickSeconds)
    {
        return PaysSpirit(index, tickSeconds);
    }

    // Kyoshiro's Soul (N-SWSTACK): "Sweeping Wind gains {perSecond} stacks every second it does not deal
    // damage to any enemies". One tick of `tickMs`: a tick that damaged an enemy starts the quiet second over; each whole
    // second of quiet ticks gains `perSecond` stacks. `quietMs` is the vortex's run of quiet time; 0 `perSecond` (no item) gains none.
    inline unsigned IdleGain(std::uint64_t& quietMs, bool damaged, std::uint64_t tickMs, unsigned perSecond)
    {
        if (damaged || !perSecond)
        {
            quietMs = 0;
            return 0;
        }
        quietMs += tickMs;
        unsigned const seconds = static_cast<unsigned>(quietMs / 1000);
        quietMs %= 1000;
        return seconds * perSecond;
    }

    // Master of Wind: "enemies damaged by Sweeping Wind for {duration_seconds} consecutive seconds are Frozen ...
    // Enemies cannot be frozen by Sweeping Wind more than once every {internal_cooldown_seconds} seconds". One per
    // enemy. Times in ms, 0 meaning never.
    struct Streak
    {
        std::uint64_t since = 0;  // the first tick of the unbroken run
        std::uint64_t last = 0;   // the latest tick that damaged it
        std::uint64_t frozen = 0; // when it was last frozen

        // The enemy was damaged by the tick at `now`. True when it freezes now. A tick is `tickMs` long, and a gap of
        // more than one and a half ticks since the last damage breaks the run.
        bool Damaged(std::uint64_t now, std::uint64_t tickMs, std::uint64_t needMs, std::uint64_t icdMs)
        {
            if (since == 0 || now > last + tickMs + tickMs / 2)
                since = now;
            last = now;
            if (now - since + tickMs < needMs)
                return false;
            if (frozen != 0 && now < frozen + icdMs)
                return false;
            frozen = now;
            since = now + tickMs; // the next run starts after this tick
            return true;
        }
    };
} // namespace DC::Combat::Monk::Wind
