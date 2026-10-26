#pragma once
// Chakram's rules that need no core type, header-only so tests/demon_hunter_chakram compiles this exact code: which
// rune is which and what one tick of Shuriken Cloud is worth. The production half is dc_demon_hunter_chakram.cpp.
#include "dc_demon_hunter_clock.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::Chakram
{
    enum class Rune
    {
        None,
        TwinChakrams, // a second chakram along the same path, Fire
        Boomerang,    // a loop, Lightning
        Serpentine,   // a slow curve, Cold
        RazorDisk,    // a spiral out from the target, Physical
        ShurikenCloud // a cloud round the Demon Hunter that lasts
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Twin Chakrams")
            return Rune::TwinChakrams;
        if (name == "Boomerang")
            return Rune::Boomerang;
        if (name == "Serpentine")
            return Rune::Serpentine;
        if (name == "Razor Disk")
            return Rune::RazorDisk;
        if (name == "Shuriken Cloud")
            return Rune::ShurikenCloud;
        return Rune::None;
    }

    // "dealing {damage_pct} weapon damage per second": what one tick of the cloud, `tickSeconds` long, carries.
    inline double CloudTickPct(double perSecondPct, double tickSeconds)
    {
        return tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;
    }

    // "Lasts {duration_minutes} minutes": the milliseconds a cloud cast at game time `nowMs` lasts until.
    inline std::uint64_t CloudEndsAt(std::uint64_t nowMs, double minutes)
    {
        return nowMs + std::uint64_t(minutes > 0 ? minutes * 60000.0 : 0.0);
    }

    // The production half (dc_demon_hunter_chakram.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The Chakram's own hit along its path is each rune's own damage; the cloud has none of its own.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A chakram hit `target` (`critical` when it was a critical hit): Twin Chakrams' second one.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The cast resolved: Shuriken Cloud begins and starts its cooldown.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Chakram
