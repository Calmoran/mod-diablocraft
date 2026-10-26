#pragma once
// The rules of Big Bad Voodoo's ritual that need no core type, header-only so tests/witch_doctor_big_bad_voodoo
// compiles this exact code: how long an ally keeps the ritual's gifts after a look, what Ghost Trance heals each look
// and takes off a blow, whether a corpse rises as a Zombie Dog, whether an ally stands in the ritual. The production
// half is dc_witch_doctor_big_bad_voodoo.cpp.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::WitchDoctor::BigBadVoodoo
{
    // "Buff Duration" = the search's tick rate and a little over: how long, in milliseconds, an ally keeps the gifts
    // after a look found it in the ritual.
    inline std::uint64_t GiftMs(double tickSeconds, double lingerSeconds)
    {
        return tickSeconds > 0 ? static_cast<std::uint64_t>((tickSeconds + std::max(0.0, lingerSeconds)) * 1000.0 + 0.5)
                               : 0u;
    }

    // Whether the gifts given until `untilMs` still hold at `nowMs`.
    inline bool Holds(std::uint64_t untilMs, std::uint64_t nowMs)
    {
        return nowMs < untilMs;
    }

    // Ghost Trance: "heals all nearby allies for {heal_pct} of their maximum Life per second": what one look every
    // `tickSeconds` heals.
    inline double TickHeal(double maxLife, double pctPerSecond, double tickSeconds)
    {
        return maxLife > 0 && pctPerSecond > 0 && tickSeconds > 0 ? maxLife * pctPerSecond / 100.0 * tickSeconds : 0.0;
    }

    // Ghost Trance: "reduces all damage taken by {damage_reduction_pct}": a blow of `damage` after it.
    inline double Taken(double damage, double reductionPct)
    {
        return damage > 0 ? damage * (1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0) : damage;
    }

    // Whether something `distance` yards from the ritual's middle is within its `radius`.
    inline bool Inside(double distance, double radius)
    {
        return distance <= radius;
    }

    // Boogie Man: "a {proc_chance_pct} chance to resurrect as a Zombie Dog": a roll of 0 to 100 against the chance.
    inline bool Rises(double roll, double chancePct)
    {
        return chancePct > 0 && roll < chancePct;
    }
} // namespace DC::Combat::WitchDoctor::BigBadVoodoo
