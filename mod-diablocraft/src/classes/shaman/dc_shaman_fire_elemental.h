#pragma once
// Fire Elemental's rules that need no core type, header-only so tests/shaman_fire_elemental compiles this exact code:
// which rune is which, how long it lasts, what a tick and an echo deal, the Life the Water Elemental heals and which
// casts it echoes. The production half is dc_shaman_fire_elemental.cpp.
#include "../../combat/dc_periodic_strike.h"

#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::FireElemental
{
    enum class Rune
    {
        None,
        PrimalFireElemental, // lasts longer
        MeteorCall,          // crashes into the target location when summoned
        StormElemental,      // Lightning; the echo chains; attack speed for the Shaman
        WaterElemental,      // Cold; the aura chills and the Shaman heals
        MagmaElemental       // Physical; the echo is a boulder that knocks enemies down
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Primal Fire Elemental")
            return Rune::PrimalFireElemental;
        if (name == "Meteor Call")
            return Rune::MeteorCall;
        if (name == "Storm Elemental")
            return Rune::StormElemental;
        if (name == "Water Elemental")
            return Rune::WaterElemental;
        if (name == "Magma Elemental")
            return Rune::MagmaElemental;
        return Rune::None;
    }

    // How long the elemental lasts: Primal Fire Elemental's own seconds, the skill's for every other rune (Magma
    // Elemental states a `duration_seconds` of its own that is the knock down's).
    inline double Lifetime(Rune rune, double ownSeconds, double baseSeconds)
    {
        return rune == Rune::PrimalFireElemental ? ownSeconds : baseSeconds;
    }

    // The weapon damage percent of one tick of the aura, which the sheet states per second.
    inline double AuraPerTick(double perSecondPct, double tickSeconds)
    {
        return perSecondPct > 0 && tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;
    }

    // Water Elemental: the chill lasts through the next tick, so an enemy that stays in reach stays chilled.
    inline double ChillSeconds(double tickSeconds)
    {
        return tickSeconds > 0 ? tickSeconds * 2.0 : 0.0;
    }

    // Storm Elemental: "the echo chains to {target_count} more enemies at {damage_share_pct} damage": the weapon damage
    // percent of a chained echo.
    inline double ChainedPct(double echoPct, double sharePct)
    {
        return echoPct > 0 && sharePct > 0 ? echoPct * sharePct / 100.0 : 0.0;
    }

    // Water Elemental: "you heal {life_regen_pct} of maximum Life per second": the Life one tick heals.
    inline double HealPerTick(double maxLife, double pct, double tickSeconds)
    {
        return maxLife > 0 && pct > 0 && tickSeconds > 0 ? maxLife * pct / 100.0 * tickSeconds : 0.0;
    }

    // "Each time you cast a Secondary skill, it echoes the cast": whether a cast of a skill of `category` is echoed
    // while an elemental stands.
    inline bool Echoes(std::string_view category, bool up)
    {
        return up && category == "Secondary";
    }

    // Whether an elemental that ends at `untilMs` still stands at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_fire_elemental.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // A cast of `spellId` resolved on `targets`: a Fire Elemental starts (replacing the one that stood), a Secondary is
    // echoed.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // Defines the creature the elemental shows as (at startup).
    void RegisterScripts();
} // namespace DC::Combat::Shaman::FireElemental
