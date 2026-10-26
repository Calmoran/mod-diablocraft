#pragma once
// 'Requires Bow' means any ranged weapon, as in D3: the rule that needs no core type, header-only
// so tests/demon_hunter_ranged_weapon compiles this exact code. Which skills carry the line is the sheet's: a row of
// demon_hunter_skill_values.csv with the token requires_ranged_weapon. The production half is
// dc_demon_hunter_ranged_weapon.cpp.
#include <cstdint>

class Player;

namespace DC::Combat::DemonHunter::RangedWeapon
{
    // The item subclass of a slot with no weapon in it.
    inline constexpr std::uint32_t NoWeapon = 0xFFFFFFFFu;
    // The weapon subclasses the Demon Hunter's ranged weapons have: a bow, and a crossbow, which is every kind of
    // crossbow the item generator makes (Crossbow, Hand Crossbow, Repeating Crossbow). The .cpp checks these against
    // the core's ITEM_SUBCLASS_WEAPON_BOW and _CROSSBOW.
    inline constexpr std::uint32_t Bow = 2;
    inline constexpr std::uint32_t Crossbow = 18;

    inline bool IsRanged(std::uint32_t subclass)
    {
        return subclass == Bow || subclass == Crossbow;
    }

    // Whether a skill may be cast: one that does not require a ranged weapon always may; one that does needs one in the
    // main hand or the off hand (a Demon Hunter may carry a hand crossbow in either).
    inline bool Allowed(bool requiresRanged, std::uint32_t mainHand, std::uint32_t offHand)
    {
        return !requiresRanged || IsRanged(mainHand) || IsRanged(offHand);
    }

    // The production half (dc_demon_hunter_ranged_weapon.cpp), called from dc_demon_hunter.cpp: whether `player` may
    // cast `spellId` with what they wield.
    bool Permitted(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter::RangedWeapon
