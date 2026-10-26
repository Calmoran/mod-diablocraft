#pragma once
// Punish's rules that need no core type, header-only so tests/crusader_punish compiles this exact code: which answer a
// rune gives to a block, and Fury's one-shot critical chance. The production half is dc_crusader_punish.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Crusader::Punish
{
    // "When you block with Hardened Senses active ...": what each rune does at that moment. The base skill answers
    // nothing, and neither does a rune this table does not know.
    enum class Answer
    {
        None,
        Retaliate, // weapon damage as Holy to the attacker
        Celerity,  // attack speed for a few seconds
        Rebirth,   // Life regeneration for a few seconds
        Roar,      // weapon damage as Fire to the enemies around
        Fury       // the next attack's critical hit chance
    };

    inline Answer AnswerOf(std::string_view rune)
    {
        if (rune == "Retaliate")
            return Answer::Retaliate;
        if (rune == "Celerity")
            return Answer::Celerity;
        if (rune == "Rebirth")
            return Answer::Rebirth;
        if (rune == "Roar")
            return Answer::Roar;
        if (rune == "Fury")
            return Answer::Fury;
        return Answer::None;
    }

    // Fury: "gain {crit_chance_pct} increased Critical Hit Chance for your next attack": the bonus while it waits for
    // that attack, nothing once it has been used or before a block armed it.
    inline double FuryCrit(bool armed, double pct)
    {
        return armed ? pct : 0.0;
    }

    // The production half (dc_crusader_punish.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The skill's hit: 335%, which every rune inherits (a rune's own damage_pct is its answer's, not the hit's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The attack connected: Hardened Senses starts, and an armed Fury has been used up.
    void Connected(Player* player, std::uint32_t spellId);
    // The Crusader blocked a hit of `attacker`.
    void Blocked(Player* player, Unit* attacker);
    double CritBonus(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Crusader::Punish
