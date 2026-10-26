#pragma once
// Iron Skin's rules that need no core type, header-only so tests/crusader_iron_skin compiles this exact code: which rune is
// which, how long the skin lasts, when it has really run out, and when Charged Up's roll stuns. The production half is
// dc_crusader_iron_skin.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Crusader::IronSkin
{
    enum class Rune
    {
        None,
        ChargedUp,     // being hit may stun the enemies around
        SteelSkin,     // the skin lasts longer
        ExplosiveSkin, // the skin explodes off when it ends
        ReflectiveSkin, // Thorns rises while it lasts
        Flash          // being hit makes the Crusader faster
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Charged Up")
            return Rune::ChargedUp;
        if (rune == "Steel Skin")
            return Rune::SteelSkin;
        if (rune == "Explosive Skin")
            return Rune::ExplosiveSkin;
        if (rune == "Reflective Skin")
            return Rune::ReflectiveSkin;
        if (rune == "Flash")
            return Rune::Flash;
        return Rune::None;
    }

    // "Increase the duration to {duration_seconds} seconds": Steel Skin's number replaces the skill's; no other rune's
    // `duration_seconds` is the skin's (Flash's is the speed's).
    inline double Seconds(Rune rune, double skillSeconds, double steelSeconds)
    {
        return rune == Rune::SteelSkin ? steelSeconds : skillSeconds;
    }

    // "When Iron Skin expires": the skin explodes only when nothing holds it any more; a cast that renewed it has moved the end
    // and the earlier end's check finds it held.
    inline bool Expired(unsigned stacksHeld)
    {
        return stacksHeld == 0;
    }

    // A chance in percent against a roll in [0, 100): Charged Up's "{proc_chance_pct} chance to stun".
    inline bool Procs(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_crusader_iron_skin.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The skin deals no damage of its own on the cast: 0 for the skill and every rune, so Explosive Skin's 1400% is not read as
    // the cast's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The skin put on: the damage it takes off, and what the rune adds for its time.
    void Cast(Player* player, std::uint32_t spellId);
    // `victim` took a hit while the skin lasts: Charged Up's stun, Flash's speed.
    void Taken(Player* victim);
} // namespace DC::Combat::Crusader::IronSkin
