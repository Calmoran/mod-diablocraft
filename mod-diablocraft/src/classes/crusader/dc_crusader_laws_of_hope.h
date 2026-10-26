#pragma once
// Laws of Hope's rules that need no core type, header-only so tests/crusader_laws_of_hope compiles this exact code:
// which rune is which, what a pulse heals, what Wrath spent heals, and which elements a damage reduction rune covers.
// The production half is dc_crusader_laws_of_hope.cpp; the state and the mechanism every Law shares are
// dc_crusader_laws.h and .cpp.
#include "../../common/dc_common.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::LawsOfHope
{
    enum class Rune
    {
        None,
        WingsOfAngels, // movement speed for the Crusader and its group
        EternalHope,   // maximum Life for them
        HopefulCry,    // Physical damage taken reduced
        FaithsReward,  // Wrath spent heals them
        PromiseOfFaith // non-Physical damage taken reduced
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Wings of Angels")
            return Rune::WingsOfAngels;
        if (rune == "Eternal Hope")
            return Rune::EternalHope;
        if (rune == "Hopeful Cry")
            return Rune::HopefulCry;
        if (rune == "Faith's Reward")
            return Rune::FaithsReward;
        if (rune == "Promise of Faith")
            return Rune::PromiseOfFaith;
        return Rune::None;
    }

    // "Recite the Law, healing you and your allies for {heal_per_second_life} Life per second": the Life one pulse
    // heals, the rate for the seconds the pulse stands for.
    inline double HealPerPulse(double perSecond, double pulseSeconds)
    {
        return perSecond > 0 && pulseSeconds > 0 ? perSecond * pulseSeconds : 0.0;
    }

    // "heals you and your allies for {heal_per_hit_life} Life for every point of Wrath that you spend": the Life a cast
    // heals.
    inline double HealForWrath(double perPoint, double wrathSpent)
    {
        return perPoint > 0 && wrathSpent > 0 ? perPoint * wrathSpent : 0.0;
    }

    // Whether the rune's damage reduction covers damage of `element`: Hopeful Cry the Physical, Promise of Faith every
    // other element, no other rune any.
    inline bool ReducesElement(Rune rune, Element element)
    {
        if (rune == Rune::HopefulCry)
            return element == Element::Physical;
        if (rune == Rune::PromiseOfFaith)
            return element != Element::Physical;
        return false;
    }

    // The production half (dc_crusader_laws_of_hope.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The Law deals no damage of its own on the cast: 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The press: the Law is empowered; the shield goes on the Crusader and its group now.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // Hands the Law to the always-on hook (once, at startup).
    void Register();
} // namespace DC::Combat::Crusader::LawsOfHope
