#pragma once
// Mantra of Healing's rules that need no core type, header-only so
// tests/monk_mantra_of_healing compiles this exact code: the heal of one pulse, the heal of a hit, the absorb, the
// threshold of Time of Need, who has left the aura, and the "only one Mantra" slot.
#include <algorithm>
#include <cstdint>
#include <set>
#include <vector>

namespace DC::Combat::Monk::Healing
{
    // "Passive: ... gain {heal_per_second_life} increased Life regeneration. The heal amount is increased by
    // {life_per_second_share_pct} of your Life per Second": the Life a holder is healed in `pulseSeconds`.
    inline double PulseHeal(double perSecond, double lifePerSecond, double sharePct, double pulseSeconds)
    {
        if (pulseSeconds <= 0)
            return 0.0;
        return (std::max(perSecond, 0.0) + std::max(lifePerSecond, 0.0) * std::max(sharePct, 0.0) / 100.0) *
               pulseSeconds;
    }

    // Boon of Inspiration: "also heals {heal_per_hit_life} Life when hitting an enemy. Heal amount is increased by
    // {life_per_hit_share_pct} of your Life per Hit."
    inline double HitHeal(double perHit, double lifePerHit, double sharePct)
    {
        return std::max(perHit, 0.0) + std::max(lifePerHit, 0.0) * std::max(sharePct, 0.0) / 100.0;
    }

    // "absorbs up to {absorb_life} damage ... Absorb amount is increased by {healing_bonus_share_pct} of your Health
    // Globe Healing Bonus": the bonus is a percent, the share a percent of it.
    inline double Absorb(double life, double sharePct, double globeBonusPct)
    {
        return std::max(life, 0.0) * (1.0 + std::max(sharePct, 0.0) / 100.0 * std::max(globeBonusPct, 0.0) / 100.0);
    }

    // Time of Need: "reduces damage taken by {damage_reduction_pct} when below {life_threshold_pct} Life": strictly
    // below.
    inline bool BelowThreshold(double lifePct, double thresholdPct)
    {
        return lifePct < thresholdPct;
    }

    // Circular Breathing: "regenerates {regen_per_second_resource} Spirit per second", paid a pulse at a time.
    inline double SpiritPerPulse(double perSecond, double pulseSeconds)
    {
        return perSecond > 0 && pulseSeconds > 0 ? perSecond * pulseSeconds : 0.0;
    }

    // Who held the aura at the last pulse and is not in range of this one.
    inline std::vector<std::uint64_t> Left(std::set<std::uint64_t> const& before, std::set<std::uint64_t> const& now)
    {
        std::vector<std::uint64_t> left;
        for (std::uint64_t guid : before)
            if (!now.count(guid))
                left.push_back(guid);
        return left;
    }
} // namespace DC::Combat::Monk::Healing
