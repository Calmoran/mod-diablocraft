#pragma once
// Bolas' rules that need no core type, header-only so tests/demon_hunter_bolas compiles this exact code: which rune is
// which and when each bola of a volley explodes. The production half is dc_demon_hunter_bolas.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::Bolas
{
    enum class Rune
    {
        None,
        VolatileExplosives, // a larger explosion and Fire
        FreezingStrike,     // three bolas that freeze, no explosion
        ThunderBall,        // more Hatred (paid by the class's Connected) and Lightning
        BitterPill,         // a chance of Discipline when the bola explodes
        ImminentDoom        // a bigger hit, a longer fuse
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Volatile Explosives")
            return Rune::VolatileExplosives;
        if (name == "Freezing Strike")
            return Rune::FreezingStrike;
        if (name == "Thunder Ball")
            return Rune::ThunderBall;
        if (name == "Bitter Pill")
            return Rune::BitterPill;
        if (name == "Imminent Doom")
            return Rune::ImminentDoom;
        return Rune::None;
    }

    // The seconds after the shot that the bola of place `index` (0 for the first) explodes: Freezing Strike's bolas
    // leave `perShot` seconds apart and each takes the same fuse.
    inline double ExplodesAfter(double fuseSeconds, double perShot, unsigned index)
    {
        return fuseSeconds + perShot * index;
    }

    // The production half (dc_demon_hunter_bolas.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The bola's own hit when it lands, which every rune inherits: next to nothing, the explosion carries the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The bola landed on `target`: it wraps the enemy and explodes after its fuse.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter::Bolas
