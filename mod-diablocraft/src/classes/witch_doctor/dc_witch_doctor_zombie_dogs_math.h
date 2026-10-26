#pragma once
// The rules of Summon Zombie Dogs' runes that need no core type, header-only so tests/witch_doctor_zombie_dogs compiles
// this exact code: what one pulse of Burning Dogs deals, how much of a blow Life Link gives the dogs and what each
// takes, what Leeching Beasts heals and how Midnight Feast's raise reaches a rune's damage. The production half is
// dc_witch_doctor_zombie_dogs.cpp.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::WitchDoctor::ZombieDogs
{
    // Burning Dogs: "burning nearby enemies for {damage_pct} of your weapon damage as Fire every second": the weapon
    // damage one pulse deals when a pulse comes every `tickSeconds`.
    inline double PulsePct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;
    }

    // Life Link: "Your Zombie Dogs absorb {absorb_pct} of all damage done to you": the part of a blow of `damage` the
    // dogs take.
    inline double LinkedShare(double damage, double pct)
    {
        return damage > 0 && pct > 0 ? damage * std::min(pct, 100.0) / 100.0 : 0.0;
    }

    // What each of `dogs` dogs takes of that share.
    inline double PerDog(double share, unsigned dogs)
    {
        return dogs ? share / dogs : 0.0;
    }

    // Leeching Beasts: "heal you for {life_per_hit_share_pct} of your Life On Hit with every attack": the Life one
    // attack gives.
    inline double Leeched(double lifePerHit, double sharePct)
    {
        return lifePerHit > 0 && sharePct > 0 ? lifePerHit * sharePct / 100.0 : 0.0;
    }

    // Midnight Feast raises the dogs' blow from `baseBlowPct` to `blowPct`; a rune's own damage follows by the same
    // factor, 1 when nothing raised it.
    inline double Raised(double runePct, double baseBlowPct, double blowPct)
    {
        return baseBlowPct > 0 && blowPct > 0 ? runePct * blowPct / baseBlowPct : runePct;
    }

    // Whether a Zombie Dog raised with the rune of record `raisedWith` still fits the rune on the bar (`slotted`): dogs
    // of another rune are sent away by the next cast and raised anew.
    inline bool KeepsDogs(std::uint32_t raisedWith, std::uint32_t slotted)
    {
        return raisedWith == slotted;
    }
} // namespace DC::Combat::WitchDoctor::ZombieDogs
