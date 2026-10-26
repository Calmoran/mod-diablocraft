#pragma once
// Flame Shock's rules that need no core type, header-only so tests/shaman_flame_shock compiles this exact code: which rune is which,
// where the cast's own hit takes its number from, which casts burn, what Primal Shock does for each Attunement and the mark it
// leaves. The production half is dc_shaman_flame_shock.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::FlameShock
{
    enum class Rune
    {
        None,
        LavaShock,   // a Burning target erupts on the enemies around it, Fire
        FrostShock,  // chills instead of burning, and generates more against a chilled enemy, Cold
        EarthShock,  // stuns instead of burning, Physical
        StaticShock, // arcs to nearby enemies instead of burning, Lightning
        PrimalShock  // deals the Attunement's element and adds a small effect of it
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Lava Shock")
            return Rune::LavaShock;
        if (name == "Frost Shock")
            return Rune::FrostShock;
        if (name == "Earth Shock")
            return Rune::EarthShock;
        if (name == "Static Shock")
            return Rune::StaticShock;
        if (name == "Primal Shock")
            return Rune::PrimalShock;
        return Rune::None;
    }

    // Where the cast's own hit takes its weapon damage from: the skill's "hit" number (the base and Lava Shock), the rune's
    // number of its own (Frost and Earth Shock state one) or the rune's "hit" number (Static and Primal Shock state two).
    enum class HitFrom
    {
        Skill,
        RuneOnly,
        RuneHit
    };

    inline HitFrom HitOf(Rune rune)
    {
        switch (rune)
        {
            case Rune::FrostShock:
            case Rune::EarthShock:
                return HitFrom::RuneOnly;
            case Rune::StaticShock:
            case Rune::PrimalShock:
                return HitFrom::RuneHit;
            default:
                return HitFrom::Skill;
        }
    }

    // What Primal Shock adds, by the Attunement it deals: Fire burns, Cold chills, Physical marks, Lightning arcs.
    enum class Small
    {
        Burn,
        Chill,
        Mark,
        Arc
    };

    // `attuned` is the Attunement's element as the engine names it ("fire", "cold", "physical", "lightning").
    inline std::optional<Small> SmallOf(std::string_view attuned)
    {
        if (attuned == "fire")
            return Small::Burn;
        if (attuned == "cold")
            return Small::Chill;
        if (attuned == "physical")
            return Small::Mark;
        if (attuned == "lightning")
            return Small::Arc;
        return std::nullopt;
    }

    // Whether the cast leaves the skill's burn: the base and Lava Shock; the other runes replace it (Primal Shock's Fire burn is its
    // own).
    inline bool Burns(Rune rune)
    {
        return rune == Rune::None || rune == Rune::LavaShock;
    }

    // Whether a Lava Shock cast erupts: the target was already Burning before the hit.
    inline bool Erupts(Rune rune, bool wasBurning)
    {
        return rune == Rune::LavaShock && wasBurning;
    }

    // Frost Shock: "Generates {gain_resource} extra Maelstrom against enemies that are already Chilled".
    inline double ChilledGain(bool chilled, double gain)
    {
        return chilled && gain > 0 ? gain : 0.0;
    }

    // Primal Shock's Physical mark: "the target takes {damage_taken_pct} more damage from you": the percent a hit of the Shaman
    // adds, none for an enemy that is not marked.
    inline double MarkBonus(bool marked, double pct)
    {
        return marked && pct > 0 ? pct : 0.0;
    }

    // Whether a mark that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_flame_shock.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of a Flame Shock record deals (the loader's, dc_combat.cpp).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The element a Primal Shock hit deals: the Shaman's Attunement. nullptr for any other spell.
    char const* Element(Player* player, std::uint32_t spellId);
    // A hit of the skill landed on `target`: the burn, the eruption, the chill, the stun, the arcs and Primal Shock's small effect.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The hit of `spellId` on `target` being computed: Primal Shock's mark raises every hit of the Shaman who made it.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::FlameShock
