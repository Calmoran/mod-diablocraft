#pragma once
// Breath of Heaven's rules that need no core type, header-only so
// tests/monk_breath_of_heaven compiles this exact code: the heal, Infused with Light's window and extra Spirit,
// Zephyr's speed amount.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::Breath
{
    // "heals you and all allies within {radius_yards} yards for {heal_min_life} - {heal_max_life} Life. Heal amount is
    // increased by {healing_bonus_share_pct} of your Health Globe Healing Bonus": a value between the two (Power/
    // Monk_BreathOfHeaven.pow SF_2 'Heal min' + SF_3 'Heal delta' x a roll of 0 to 1) and that share of the bonus,
    // which is a flat Life number. Torment has no Health Globe Healing Bonus stat (stats: "not stats we roll"), so it
    // is 0 for now.
    inline double HealAmount(double minLife, double maxLife, double roll, double sharePct, double globeBonusLife)
    {
        double const spread = std::clamp(roll, 0.0, 1.0);
        return minLife + spread * (maxLife - minLife) + sharePct / 100.0 * globeBonusLife;
    }

    // Infused with Light: "Gain {gain_resource} additional Spirit from Spirit generating attacks for {duration_seconds}
    // seconds after using Breath of Heaven": the window runs from the cast to `until` (ms).
    inline bool InWindow(std::uint64_t now, std::uint64_t until)
    {
        return now < until;
    }

    // The extra Spirit of one attack: only a Spirit generating attack inside the window pays it.
    inline double ExtraSpirit(bool inWindow, bool generates, double gain)
    {
        return inWindow && generates && gain > 0 ? gain : 0.0;
    }

    // The core's aura amount for a speed increase of `pct` percent (positive: it speeds up).
    inline int SpeedAmount(double pct)
    {
        return static_cast<int>(std::lround(pct));
    }
} // namespace DC::Combat::Monk::Breath
