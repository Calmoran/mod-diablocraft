#pragma once
// Steed Charge's rules that need no core type, header-only so tests/crusader_steed_charge compiles this exact code:
// which rune is which, what a tick of the ride deals or heals, where a fire pool falls, and which enemies the war horse
// drags. The production half is dc_crusader_steed_charge.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;

namespace DC::Combat::Crusader::SteedCharge
{
    enum class Rune
    {
        None,
        SpikedBarding, // the enemies the horse rides through take a share of the Crusader's Thorns
        Endurance,     // a longer ride
        Rejuvenation,  // Life while riding
        Nightmare,     // a trail of fire behind the horse
        DrawAndQuarter // enemies bound and dragged along
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Spiked Barding")
            return Rune::SpikedBarding;
        if (rune == "Endurance")
            return Rune::Endurance;
        if (rune == "Rejuvenation")
            return Rune::Rejuvenation;
        if (rune == "Nightmare")
            return Rune::Nightmare;
        if (rune == "Draw and Quarter")
            return Rune::DrawAndQuarter;
        return Rune::None;
    }

    // A per-second sheet number paid in ticks of `tickSeconds`: "every second" is a tick's share of it. Nothing for a
    // number or a tick of 0.
    inline double PerTick(double perSecond, double tickSeconds)
    {
        return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;
    }

    // Rejuvenation: "you recover {heal_pct} of your maximum Life" is the whole ride's heal, paid in equal ticks. Nothing
    // for a ride with no tick.
    inline double HealPerTick(double maxLife, double healPct, unsigned ticks)
    {
        return maxLife > 0 && healPct > 0 && ticks > 0 ? maxLife * healPct / 100.0 / ticks : 0.0;
    }

    // The movement speed the ride gives: the power file's multiplier ("Movement Speed Bonus" 1.5) as a percentage.
    inline double SpeedPct(double bonus)
    {
        return bonus > 0 ? bonus * 100.0 : 0.0;
    }

    // Nightmare: a pool is dropped where the horse is when it is `spacing` yards or more from the last one, and for
    // the first.
    inline bool DropsPool(bool hasLast, double distanceFromLast, double spacing)
    {
        return !hasLast || distanceFromLast >= spacing;
    }

    // Draw and Quarter: an enemy farther than `keep` yards from the Crusader is drawn in to that distance; one already
    // within it stays where it is.
    inline bool Dragged(double distance, double keep)
    {
        return keep > 0 && distance > keep;
    }

    // The share of the way from the Crusader to the enemy at which the dragged enemy is set down: `keep` yards out.
    inline double DragFraction(double distance, double keep)
    {
        return Dragged(distance, keep) ? keep / distance : 1.0;
    }

    // The production half (dc_crusader_steed_charge.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // Steed Charge deals no damage on the cast: 0 for the skill and every rune, so Nightmare's 550% is not read as the
    // cast's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast: the mount, the speed, and the ticks of the ride with what each rune does in them.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::SteedCharge
