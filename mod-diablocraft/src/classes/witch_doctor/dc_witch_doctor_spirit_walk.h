#pragma once
// Spirit Walk's rules that need no core type, header-only so tests/witch_doctor_spirit_walk compiles this exact code:
// which rune is which, the run speed a walk gives, the share of a maximum a rune returns and the cooldown that starts
// only after the walk ends. The production half is dc_witch_doctor_spirit_walk.cpp.
#include <algorithm>
#include <cstdint>
#include <string_view>

class Player;

namespace DC::Combat::WitchDoctor::SpiritWalk
{
    enum class Rune
    {
        None,
        Severance,     // more run speed while in the spirit realm
        Jaunt,         // a longer walk
        UmbralShock,   // the body left behind erupts when the walk ends
        HonoredGuest,  // Mana when the walk begins
        HealingJourney // Life when the walk begins
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Severance")
            return Rune::Severance;
        if (rune == "Jaunt")
            return Rune::Jaunt;
        if (rune == "Umbral Shock")
            return Rune::UmbralShock;
        if (rune == "Honored Guest")
            return Rune::HonoredGuest;
        if (rune == "Healing Journey")
            return Rune::HealingJourney;
        return Rune::None;
    }

    // The run speed (percent) of a walk: the power file's base increase for every walk, and Severance's "additional"
    // percent on top of it.
    inline double RunSpeedPct(Rune rune, double basePct, double severancePct)
    {
        return std::max(0.0, basePct) + (rune == Rune::Severance ? std::max(0.0, severancePct) : 0.0);
    }

    // "Gain {gain_pct} of your maximum Mana" and "Gain {heal_pct} of your maximum Life": `pct` percent of `maximum`,
    // nothing for a negative number.
    inline double ShareOf(double maximum, double pct)
    {
        return maximum > 0 && pct > 0 ? maximum * pct / 100.0 : 0.0;
    }

    // "This ability does not start its cooldown until after its effects expire": the cooldown the core installed at the
    // cast is pushed back by the whole time the walk lasts, in milliseconds.
    inline std::uint64_t CooldownDelayMs(double walkSeconds)
    {
        return std::uint64_t(std::max(0.0, walkSeconds) * 1000.0 + 0.5);
    }

    // The production half (dc_witch_doctor_spirit_walk.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast of Spirit Walk or one of its runes (after the core installed the cooldown): the unhindered walk, its run
    // speed, what the rune adds, and the cooldown pushed back by the walk.
    void Cast(Player* player, std::uint32_t spellId);
    // The kind of the body Spirit Walk leaves behind; at startup.
    void Register();
} // namespace DC::Combat::WitchDoctor::SpiritWalk
