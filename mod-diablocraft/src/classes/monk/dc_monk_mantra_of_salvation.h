#pragma once
// Mantra of Salvation's rules that need no core type, header-only so
// tests/monk_mantra_of_salvation compiles this exact code: the passive's resistance, the timed numbers its aura hands
// out and Divine Protection's trigger. The "only one Mantra" state is dc_monk_mantras.h's.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>

namespace DC::Combat::Monk::Salvation
{
    // Perseverance: "Increases the resistance to all elements bonus to {resistance_pct}" - the rune's number replaces
    // the passive's, it is not added to it. Every other rune keeps the skill's.
    inline double PassivePct(double skillPct, std::optional<double> runePct)
    {
        return runePct ? *runePct : skillPct;
    }

    // "increased resistance to all elements": that percent of what the holder resists without it (a flat number per
    // element, the way the Barbarian's Impunity does it). Nothing to increase, nothing gained.
    inline double ResistanceGain(double baseline, double pct)
    {
        return baseline > 0 && pct > 0 ? baseline * pct / 100.0 : 0.0;
    }

    // The passive's and the active's resistance are separate increases, "an additional" one for the active's seconds.
    inline double TotalResistancePct(double passivePct, double activePct)
    {
        return std::max(0.0, passivePct) + std::max(0.0, activePct);
    }

    inline std::uint64_t Millis(double seconds)
    {
        return seconds > 0 ? static_cast<std::uint64_t>(std::llround(seconds * 1000.0)) : 0;
    }

    // A number worn until a time (ms): the aura hands it out again every pulse, so it lapses when the Monk stops.
    inline bool Live(std::uint64_t now, std::uint64_t until)
    {
        return now < until;
    }

    struct Timed
    {
        double pct = 0;
        std::uint64_t until = 0;

        double Of(std::uint64_t now) const
        {
            return Live(now, until) ? pct : 0.0;
        }
    };

    // Divine Protection: "when reduced below {life_threshold_pct} Life ... Each target may be protected by this effect
    // once every {internal_cooldown_seconds} seconds": strictly below, and not again before `readyAt` (ms).
    inline bool ShieldOpens(double lifePct, double thresholdPct, std::uint64_t now, std::uint64_t readyAt)
    {
        return lifePct < thresholdPct && now >= readyAt;
    }
} // namespace DC::Combat::Monk::Salvation
