#pragma once
// Consecration's rules that need no core type, header-only so tests/crusader_consecration compiles this exact code:
// which rune is which, who stands on the ground, when an enemy has crossed Aegis Purgatory's edge, the share of Thorns
// Bed of Nails deals, and Fearful's roll. The production half is dc_crusader_consecration.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Crusader::Consecration
{
    enum class Rune
    {
        None,
        AegisPurgatory,  // the edge holds enemies in or out
        BedOfNails,      // enemies on the ground take a share of the Crusader's Thorns
        BathedInLight,   // a wider ground and a bigger heal
        ShatteredGround, // enemies on the ground burn
        Fearful          // enemies on the ground may be Feared
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Aegis Purgatory")
            return Rune::AegisPurgatory;
        if (rune == "Bed of Nails")
            return Rune::BedOfNails;
        if (rune == "Bathed in Light")
            return Rune::BathedInLight;
        if (rune == "Shattered Ground")
            return Rune::ShatteredGround;
        if (rune == "Fearful")
            return Rune::Fearful;
        return Rune::None;
    }

    // "standing on the consecrated ground": within its radius of where it was laid.
    inline bool OnGround(double distance, double radius)
    {
        return radius > 0 && distance <= radius;
    }

    // Aegis Purgatory: an enemy that was on one side of the edge and is now on the other has gone through it.
    inline bool Crossed(bool wasInside, double distance, double radius)
    {
        return wasInside != OnGround(distance, radius);
    }

    // Bed of Nails: "{thorns_share_pct} of your Thorns damage every second".
    inline double ThornsShare(double thorns, double sharePct)
    {
        return thorns > 0 && sharePct > 0 ? thorns * sharePct / 100.0 : 0.0;
    }

    // A chance in percent against a roll in [0, 100): Fearful's "{proc_chance_pct} chance to be Feared".
    inline bool Procs(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_crusader_consecration.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The ground deals no damage on the cast: 0 for the skill and every rune, so Shattered Ground's 155% a second is
    // not read as the cast's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The ground laid where the Crusader stands.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::Consecration
