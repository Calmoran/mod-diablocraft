#pragma once
// Purge's rules that need no core type, header-only so tests/shaman_purge compiles this exact code: which rune is
// which, what a rune does to each enemy the shock reaches (given how many empowered states came off it), and the
// Maelstrom the removals pay. The production half is dc_shaman_purge.cpp, called from dc_shaman.cpp.
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::Purge
{
    enum class Rune
    {
        None,
        WindShear,      // interrupts the cast and stuns what is not a boss
        GreaterPurge,   // a purged elite deals less damage for seconds
        CleanseSpirit,  // Cold; control effects and damage over time come off the Shaman
        ConsumingPurge, // Fire; an enemy that lost an effect burns
        EarthenPurge    // Physical; the shock reaches a cone (the cast's targets), not one enemy
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Wind Shear")
            return Rune::WindShear;
        if (name == "Greater Purge")
            return Rune::GreaterPurge;
        if (name == "Cleanse Spirit")
            return Rune::CleanseSpirit;
        if (name == "Consuming Purge")
            return Rune::ConsumingPurge;
        if (name == "Earthen Purge")
            return Rune::EarthenPurge;
        return Rune::None;
    }

    // What the rune does to one enemy the shock reached; `removed` is how many empowered states the purge took off it,
    // `elite` whether it is an elite or a boss, `boss` whether it is a boss.
    struct Effect
    {
        bool interrupt = false;
        bool stun = false;
        bool weaken = false;
        bool burn = false;
    };

    inline Effect EffectOf(Rune rune, unsigned removed, bool elite, bool boss)
    {
        Effect effect;
        switch (rune)
        {
            case Rune::WindShear:
                effect.interrupt = true;
                effect.stun = !boss;
                break;
            case Rune::GreaterPurge:
                effect.weaken = removed > 0 && elite;
                break;
            case Rune::ConsumingPurge:
                effect.burn = removed > 0;
                break;
            case Rune::None:
            case Rune::CleanseSpirit:
            case Rune::EarthenPurge:
                break;
        }
        return effect;
    }

    // Whether the rune's record keeps the skill's own hit by a claim of the class: Consuming Purge (its `damage_pct` is the burn's) and
    // Greater Purge (its `duration_seconds` would read as a damage that waits).
    inline bool ClaimsHit(Rune rune)
    {
        return rune == Rune::ConsumingPurge || rune == Rune::GreaterPurge;
    }

    // "Removing an effect generates {gain_resource} Maelstrom": for each state taken off, over every enemy the shock
    // reached.
    inline double Maelstrom(unsigned removed, double perEffect)
    {
        return removed * perEffect;
    }

    // "{damage_pct} weapon damage as Fire over {dot_duration_seconds} seconds" in ticks of `tickSeconds`: the ticks and
    // the percent of one.
    inline unsigned Ticks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? static_cast<unsigned>(seconds / tickSeconds + 1e-9) : 0u;
    }

    // The production half (dc_shaman_purge.cpp).
    bool Is(std::uint32_t spellId);
    // The hit of the cast itself: Consuming Purge's own `damage_pct` is its burn's and Greater Purge's `duration_seconds` would make the loader
    // hold the damage back, so the shock keeps the skill's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The shock is aimed at `targets`, before any of them is hit: what it purges comes off first, so a shield does not
    // eat the hit.
    void Aim(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The shock landed on `targets`: the rune's part.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::Purge
