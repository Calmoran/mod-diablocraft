#pragma once
// Lava Burst's rules that need no core type, header-only so tests/shaman_lava_burst compiles this exact code: which
// rune is which, where each record's hit comes from, who takes the flat Burning bonus, which casts spread a burn and
// the random pick of Volcanic Lightning. The production half is dc_shaman_lava_burst.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::LavaBurst
{
    enum class Rune
    {
        None,
        PathOfFlames,     // a Burning target burns the enemies around it, Fire
        Pyroclasm,        // the lava erupts on impact, Fire
        ObsidianBurst,    // a boulder that knocks the target down, Physical
        SteamBurst,       // freezes the target and counts a chilled enemy for the bonus, Cold
        VolcanicLightning // lightning strikes random enemies after the impact, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Path of Flames")
            return Rune::PathOfFlames;
        if (name == "Pyroclasm")
            return Rune::Pyroclasm;
        if (name == "Obsidian Burst")
            return Rune::ObsidianBurst;
        if (name == "Steam Burst")
            return Rune::SteamBurst;
        if (name == "Volcanic Lightning")
            return Rune::VolcanicLightning;
        return Rune::None;
    }

    // Whether the cast's own hit is the rune's own `damage_pct` (Obsidian Burst's boulder) where every other rune's own
    // number is its burn, eruption or strikes and the lava still hits for the skill's.
    inline bool HitIsRunes(Rune rune)
    {
        return rune == Rune::ObsidianBurst;
    }

    // "Deals {damage_bonus_pct} more damage to Burning enemies": whether a hit of `rune` on an enemy gets the flat
    // bonus. Obsidian Burst's higher damage replaces it; Steam Burst counts a chilled enemy as well.
    inline bool BonusApplies(Rune rune, bool burning, bool chilled)
    {
        if (rune == Rune::ObsidianBurst)
            return false;
        return burning || (rune == Rune::SteamBurst && chilled);
    }

    // Path of Flames: "If the target is Burning, every enemy within {radius_yards} yards also Burns".
    inline bool Spreads(Rune rune, bool targetBurning)
    {
        return rune == Rune::PathOfFlames && targetBurning;
    }

    // Volcanic Lightning: the enemy a strike picks, `roll` (0 to 1) of `count` enemies. None for no enemy.
    inline std::optional<std::size_t> Pick(double roll, std::size_t count)
    {
        if (!count)
            return std::nullopt;
        return std::min(count - 1, std::size_t(std::max(roll, 0.0) * double(count)));
    }

    // The production half (dc_shaman_lava_burst.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of a Lava Burst record deals when the plain loader rule would read
    // the wrong one.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A cast of `spellId` resolved: a Lava Burst cast free spends the free state.
    void Cast(Player* player, std::uint32_t spellId);
    // A hit of the skill landed on `target`: the burn, the eruption, the knock down, the freeze and the strikes.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The hit of `spellId` on `target` being computed: the flat bonus against a Burning enemy.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::LavaBurst
