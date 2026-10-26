#pragma once
// The rules of six Monk passives that need no core type (The Guardian's Path, Sixth
// Sense, Determination, Relentless Assault, Beacon of Ytar, Alacrity), header-only so tests/monk_passives_guardians_path
// compiles this exact code. dc_monk_passives_guardians_path.cpp reads the numbers from monk_passive_values.csv and hands them
// in.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::Passives242
{
    // The Guardian's Path: "While dual-wielding, you gain a {dodge_pct} chance to dodge incoming attacks."
    inline double GuardianDodge(bool dualWielding, double pct)
    {
        return dualWielding && pct > 0 ? pct : 0.0;
    }

    // The Guardian's Path: "While using a two-handed weapon, all Spirit generation is increased by {regen_pct}": the
    // factor a generated amount is multiplied by.
    inline double GenerationFactor(bool twoHanded, double pct)
    {
        return twoHanded && pct > 0 ? 1.0 + pct / 100.0 : 1.0;
    }

    // Sixth Sense: "Reduce all non-Physical damage taken by {damage_reduction_pct}": every element but Physical.
    inline bool SixthSenseReduces(bool physical)
    {
        return !physical;
    }

    // Determination: "Each enemy within {radius_yards} yards increases your damage by {damage_bonus_pct}, up to a
    // maximum of {max_bonus_pct}".
    inline double Determination(unsigned enemies, double perEnemyPct, double maxPct)
    {
        return std::clamp(perEnemyPct * double(enemies), 0.0, std::max(0.0, maxPct));
    }

    // Relentless Assault: "You deal {damage_bonus_pct} more damage to enemies that are Blind, Frozen or Stunned."
    inline double RelentlessAssault(bool blind, bool frozen, bool stunned, double pct)
    {
        return (blind || frozen || stunned) && pct > 0 ? pct : 0.0;
    }

    // Alacrity: "Increase the attack speed of Spirit Generators by {attack_speed_pct}". Attack speed bonuses add to
    // each other (D3: the sheet's speed is the weapon's times one plus the sum), so the passive's share goes into the
    // sum the hand's speed was built from: `aps` is the hand's attacks per second with `iasPct` already in it. The
    // result keeps to the attack speed cap and never falls below what it was.
    inline double AlacrityAps(double aps, double iasPct, double bonusPct, double cap)
    {
        if (aps <= 0 || bonusPct <= 0 || 1.0 + iasPct / 100.0 <= 0)
            return aps;
        double const sped = aps * (1.0 + (iasPct + bonusPct) / 100.0) / (1.0 + iasPct / 100.0);
        return std::max(aps, std::min(cap, sped));
    }

    // Beacon of Ytar: "Reduce all cooldowns by {cooldown_reduction_pct}": the contribution it puts on the sheet, held
    // to the 0 to 100 the sheet takes.
    inline double CooldownContribution(double pct)
    {
        return std::clamp(pct, 0.0, 100.0);
    }
} // namespace DC::Combat::Monk::Passives242
