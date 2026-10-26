#pragma once
// Ghost Wolf's rules that need no core type, header-only so tests/shaman_ghost_wolf compiles this exact code: which
// rune is which, how long the form lasts, what the rune does when the form begins and when it ends, and how many
// patches a trail of lightning lays. The production half is dc_shaman_ghost_wolf.cpp, called from dc_shaman.cpp.
#include "../../combat/dc_charge_store.h"

#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::GhostWolf
{
    enum class Rune
    {
        None,
        SpiritWalk,       // lasts longer and strips every control effect when cast
        WindRush,         // two charges in place of the cooldown
        ThunderousPaws,   // Lightning; a trail of lightning behind the wolf
        SpectralRecovery, // Cold; a heal when the form ends
        BlazingSpirit     // Fire; an explosion when the form ends
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Spirit Walk")
            return Rune::SpiritWalk;
        if (name == "Wind Rush")
            return Rune::WindRush;
        if (name == "Thunderous Paws")
            return Rune::ThunderousPaws;
        if (name == "Spectral Recovery")
            return Rune::SpectralRecovery;
        if (name == "Blazing Spirit")
            return Rune::BlazingSpirit;
        return Rune::None;
    }

    // The seconds the form lasts: the skill's, or Spirit Walk's own. Thunderous Paws' `duration_seconds` is its
    // trail's, not the form's.
    inline double FormSeconds(Rune rune, double skill, double own)
    {
        return rune == Rune::SpiritWalk ? own : skill;
    }

    // What a rune does at the two ends of the form.
    inline bool StripsControl(Rune rune)
    {
        return rune == Rune::SpiritWalk;
    }
    inline bool HealsAtEnd(Rune rune)
    {
        return rune == Rune::SpectralRecovery;
    }
    inline bool ExplodesAtEnd(Rune rune)
    {
        return rune == Rune::BlazingSpirit;
    }
    inline bool LaysTrail(Rune rune)
    {
        return rune == Rune::ThunderousPaws;
    }

    // The patches a trail lays over a form of `formSeconds` dropping one every `dropSeconds`.
    inline unsigned Patches(double formSeconds, double dropSeconds)
    {
        return formSeconds > 0 && dropSeconds > 0 ? static_cast<unsigned>(std::floor(formSeconds / dropSeconds + 1e-9))
                                                  : 0u;
    }

    // "{damage_pct} weapon damage per second" for a patch that pulses every `tickSeconds`: the percent of one pulse.
    inline double PulsePct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct * tickSeconds;
    }

    // The Life a Spectral Recovery heals: the percent of the maximum.
    inline double HealOf(double maxLife, double pct)
    {
        return maxLife * pct / 100.0;
    }

    // Whether a cast of a skill other than Ghost Wolf ends a form that stands ("Casting any other skill ends the
    // form"); Ghost Wolf's own cast starts a new one over the old.
    inline bool EndsForm(bool formStands, bool castIsGhostWolf)
    {
        return formStands && !castIsGhostWolf;
    }

    // The production half (dc_shaman_ghost_wolf.cpp).
    bool Is(std::uint32_t spellId);
    // The cast's own hit: none (the skill is a form; its runes' damage is their trail's and their explosion's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // A cast of `spellId` began: another skill ends the form; Ghost Wolf puts one on.
    void Casting(Player* player, std::uint32_t spellId);
    // Ghost Wolf's cast resolved (after the core installed the cooldown): Wind Rush's charges.
    void Cast(Player* player, std::uint32_t spellId);
    // The form's timers; called from the class's upkeep.
    void Upkeep(Player* player);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::GhostWolf
