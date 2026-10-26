#pragma once
// Laws of Valor's rules that need no core type, header-only so tests/crusader_laws compiles this exact code: which rune
// is which and when Frozen in Terror's roll stuns. The production half is dc_crusader_laws_of_valor.cpp; the state and
// the mechanism every Law shares are dc_crusader_laws.h and .cpp.
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::LawsOfValor
{
    enum class Rune
    {
        None,
        Invincible,       // the empowered Law also raises Life on Hit
        FrozenInTerror,   // empowering may stun the enemies around
        Critical,         // the empowered Law also raises Critical Hit Damage
        UnstoppableForce, // empowering cuts the Wrath cost of all skills for a time
        AnsweredPrayer    // each kill while empowered lengthens the window
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Invincible")
            return Rune::Invincible;
        if (rune == "Frozen in Terror")
            return Rune::FrozenInTerror;
        if (rune == "Critical")
            return Rune::Critical;
        if (rune == "Unstoppable Force")
            return Rune::UnstoppableForce;
        if (rune == "Answered Prayer")
            return Rune::AnsweredPrayer;
        return Rune::None;
    }

    // A chance in percent against a roll in [0, 100): Frozen in Terror's "{proc_chance_pct} chance to Stun".
    inline bool Stuns(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // The production half (dc_crusader_laws_of_valor.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The Law deals no damage of its own on the cast: 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The press: the Law is empowered; Frozen in Terror's stun and Unstoppable Force's cost cut happen now.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // Hands the Law to the always-on hook (once, at startup).
    void Register();
} // namespace DC::Combat::Crusader::LawsOfValor
