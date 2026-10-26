#pragma once
// Akarat's Champion's rules that need no core type, header-only so tests/crusader_akarats_champion compiles this exact
// code: which rune is which, whether the transformation is still on, how often the Wrath comes in, when Fire Starter
// may burn the same enemy again, what Rally takes off a running cooldown, and when Prophet saves a life. The production
// half is dc_crusader_akarats_champion.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Crusader::AkaratsChampion
{
    enum class Rune
    {
        None,
        FireStarter,       // dealing damage burns the enemy
        EmbodimentOfPower, // more Wrath regeneration
        Rally,             // the other abilities' cooldowns are cut when it is used
        Prophet,           // more Armor, and one fatal blow answered with full Life
        Hasteful           // more attack speed
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Fire Starter")
            return Rune::FireStarter;
        if (rune == "Embodiment of Power")
            return Rune::EmbodimentOfPower;
        if (rune == "Rally")
            return Rune::Rally;
        if (rune == "Prophet")
            return Rune::Prophet;
        if (rune == "Hasteful")
            return Rune::Hasteful;
        return Rune::None;
    }

    // The transformation lasts until its time is over.
    inline bool Active(std::uint64_t now, std::uint64_t until)
    {
        return until > now;
    }

    // "increasing your damage by {damage_bonus_pct}": the bonus while it lasts, nothing after.
    inline double DamageBonusPct(bool active, double bonusPct)
    {
        return active && bonusPct > 0 ? bonusPct : 0.0;
    }

    // "increasing your Wrath regeneration by {regen_per_second_resource}": a rate a second, paid in whole seconds, one
    // payment for each second the transformation lasts.
    inline unsigned Payments(double durationSeconds)
    {
        return durationSeconds > 0 ? static_cast<unsigned>(std::floor(durationSeconds + 1e-9)) : 0u;
    }

    // Fire Starter: the milliseconds that must pass before the same enemy burns again, `factor` over the attacks a
    // second (Power/X1_Crusader_AkaratsChampion.pow SF_40: 0.9 / Attacks_Per_Second_Total). None without a speed or a
    // factor.
    inline std::uint64_t BurnGapMs(double attacksPerSecond, double factor)
    {
        return attacksPerSecond > 0 && factor > 0
                   ? static_cast<std::uint64_t>(std::llround(factor / attacksPerSecond * 1000.0))
                   : 0;
    }

    inline bool BurnDue(bool burnedBefore, std::uint64_t now, std::uint64_t last, std::uint64_t gapMs)
    {
        return !burnedBefore || now >= last + gapMs;
    }

    // Rally: "reduces the remaining cooldown of your other abilities by {cooldown_reduction_seconds} seconds": the
    // milliseconds taken off a cooldown with `remainingMs` left, never more than is left.
    inline std::uint32_t CutMs(std::uint32_t remainingMs, double seconds)
    {
        return seconds > 0 ? std::min(remainingMs, static_cast<std::uint32_t>(std::llround(seconds * 1000.0))) : 0u;
    }

    // Prophet: "The first time you take fatal damage while Akarat's Champion is active, you will be returned to full
    // health": a blow that takes all the Life there is, the first one only, for this rune only.
    inline bool Saves(Rune rune, bool alreadySaved, std::uint32_t damage, std::uint32_t health)
    {
        return rune == Rune::Prophet && !alreadySaved && health > 0 && damage >= health;
    }

    // The production half (dc_crusader_akarats_champion.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The cast deals no damage of its own: 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast: the transformation begins, and what its rune gives.
    void Cast(Player* player, std::uint32_t spellId);
    // A hit of `spellId` landed on `target`: Fire Starter's burn.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The multiplier the transformation gives every hit of the Crusader.
    void Multipliers(Player* player, DC::Combat::Factors& out);
    // A blow of `damage` is about to land on `player`: Prophet turns a fatal one into nothing and full Life.
    void Fatal(Player* player, std::uint32_t& damage);
} // namespace DC::Combat::Crusader::AkaratsChampion
