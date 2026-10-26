#pragma once
// Smoke Screen's rules that need no core type, header-only so tests/demon_hunter_smoke_screen compiles this exact code:
// which rune is which, the speed the Demon Hunter gains, the Life Healing Vapors gives a tick and how long the cooldown
// is held back. The production half is dc_demon_hunter_smoke_screen.cpp.
#include <algorithm>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::SmokeScreen
{
    enum class Rune
    {
        None,
        VanishingPowder, // no cost, a longer cooldown (sheet numbers)
        LingeringFog,    // a longer invisibility (a sheet number)
        HealingVapors,   // Life while invisible
        SpecialRecipe,   // a cheaper cast (a sheet number)
        Displacement     // more movement speed while invisible
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Vanishing Powder")
            return Rune::VanishingPowder;
        if (name == "Lingering Fog")
            return Rune::LingeringFog;
        if (name == "Healing Vapors")
            return Rune::HealingVapors;
        if (name == "Special Recipe")
            return Rune::SpecialRecipe;
        if (name == "Displacement")
            return Rune::Displacement;
        return Rune::None;
    }

    // "Gain {movement_speed_pct} movement speed while invisible": Displacement's own number, the power file's 0.15 for
    // every other rune.
    inline double SpeedPct(Rune rune, double runePct, double basePct)
    {
        return rune == Rune::Displacement ? runePct : basePct;
    }

    // "Regenerate {life_regen_pct} Life while invisible": a percent of the maximum Life for each second invisible, so a
    // tick of `tickSeconds` gives its share.
    inline double RegenPerTick(double maxLife, double pctPerSecond, double tickSeconds)
    {
        return maxLife > 0 && pctPerSecond > 0 && tickSeconds > 0 ? maxLife * pctPerSecond / 100.0 * tickSeconds : 0.0;
    }

    // "This ability does not start its cooldown until after its effects expire": the cooldown the core installed at the
    // cast is pushed back by the whole time the Demon Hunter is invisible, in milliseconds.
    inline std::uint64_t CooldownDelayMs(double invisibleSeconds)
    {
        return std::uint64_t(std::max(0.0, invisibleSeconds) * 1000.0 + 0.5);
    }

    // The production half (dc_demon_hunter_smoke_screen.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast resolved: the Demon Hunter vanishes.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::DemonHunter::SmokeScreen
