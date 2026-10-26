#pragma once
// Laws of Justice's rules that need no core type, header-only so tests/crusader_laws_of_justice compiles this exact
// code: which rune is which, the share of a hit Protect the Innocent sends to the Crusader and how many stacks Decaying
// Strength holds. The production half is dc_crusader_laws_of_justice.cpp; the state and the mechanism every Law shares
// are dc_crusader_laws.h and .cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::LawsOfJustice
{
    enum class Rune
    {
        None,
        ProtectTheInnocent, // allies' damage goes in part to the Crusader
        ImmovableObject,    // Armor for the Crusader and its group
        FaithsArmor,        // a shield of faith on the Crusader and its group
        DecayingStrength,   // enemies that attack them deal less
        Bravery             // immunity to control impairing effects
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Protect the Innocent")
            return Rune::ProtectTheInnocent;
        if (rune == "Immovable Object")
            return Rune::ImmovableObject;
        if (rune == "Faith's Armor")
            return Rune::FaithsArmor;
        if (rune == "Decaying Strength")
            return Rune::DecayingStrength;
        if (rune == "Bravery")
            return Rune::Bravery;
        return Rune::None;
    }

    // "redirects {damage_share_pct} of the damage taken by your allies to you": the part of one hit that goes to the
    // Crusader. Never more than the hit and never below nothing.
    inline double Redirected(double damage, double sharePct)
    {
        return damage > 0 ? damage * std::clamp(sharePct, 0.0, 100.0) / 100.0 : 0.0;
    }

    // "reduced by {enemy_damage_pct} for {duration_seconds} seconds, stacking up to a maximum of {max_bonus_pct}": how
    // many stacks of the one reduction make the maximum. At least one, and a partial stack does not count.
    inline unsigned MaxStacks(double maxBonusPct, double perStackPct)
    {
        if (perStackPct <= 0)
            return 1;
        return unsigned(std::max(1.0, std::floor(maxBonusPct / perStackPct + 1e-9)));
    }

    // The production half (dc_crusader_laws_of_justice.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The Law deals no damage of its own on the cast: 0 for the skill and every rune.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The press: the Law is empowered; the shield, the armor and the immunity go on the Crusader and its group now.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // `victim` took a hit of `attacker`: Decaying Strength weakens the enemy for every empowered Crusader whose group
    // the victim is in.
    void Taken(Player* victim, Unit* attacker);
    // The damage `victim` is about to take, after its own mitigation: the part Protect the Innocent sends to a Crusader
    // is dealt to that Crusader, the rest is returned.
    double Redirect(Unit* victim, double damage);
    // Hands the Law to the always-on hook (once, at startup).
    void Register();
} // namespace DC::Combat::Crusader::LawsOfJustice
