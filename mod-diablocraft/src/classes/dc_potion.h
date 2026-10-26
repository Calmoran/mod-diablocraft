#ifndef DC_POTION_H
#define DC_POTION_H

#include "dc_potion_table.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iterator>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (81202, 81205, 102200, 100): potion shell id and the inventory potion slot index; Identifiers.

namespace DC::Potion
{
// The Health Potion: 60% max Life, 30 seconds, key 7.
// Appended after the existing spell manifest; never renumber older shells.
constexpr std::uint32_t BaseSpell = 81202;
constexpr std::uint32_t CooldownMs = 30000;
// The first legendary potion: the item
// (items_0015_bottomless_potion.sql) and its own shell, appended after Identify
// All by generate_spells.py. Every Bottomless potion is a row of Legendaries
// (dc_potion_table.h, generated from legendary_potions.csv and
// potion_icons.csv): its item, its shell (same 60% heal and
// 30 s cooldown) and its power.
constexpr std::uint32_t BottomlessItem = 102200;
constexpr std::uint32_t BottomlessSpell = 81205;
// Virtual inventory slot; outside WoW's equipment/bag slot range.
constexpr std::int32_t InventorySlot = 100;

inline std::uint32_t HealAmount(std::uint32_t maximum, std::uint32_t current)
{
    if (current >= maximum)
        return 0;
    // Integer Life rounds down; widen before multiplying to avoid overflow.
    return static_cast<std::uint32_t>(std::min<std::uint64_t>(
        std::uint64_t(maximum) * 60 / 100, maximum - current));
}

// The catalogue of potion shells: the Health Potion and every legendary potion's own
// shell. Every one heals the same way and every one shares ONE cooldown (as in
// D3): drinking any of them puts all of them on cooldown, so
// swapping potions never gives a second drink. A new legendary potion is a row of
// the sheet; nothing here names one.
constexpr auto Shells = []
{
    std::array<std::uint32_t, std::size(Legendaries) + 1> shells{BaseSpell};
    for (std::size_t i = 0; i < std::size(Legendaries); ++i)
        shells[i + 1] = Legendaries[i].shell;
    return shells;
}();

inline bool IsPotionShell(std::uint32_t spellId)
{
    for (std::uint32_t shell : Shells)
        if (shell == spellId)
            return true;
    return false;
}

// The legendary potion whose shell this is; nullptr for the Health Potion and any other spell.
inline Legendary const* ByShell(std::uint32_t spellId)
{
    for (Legendary const& potion : Legendaries)
        if (potion.shell == spellId)
            return &potion;
    return nullptr;
}

inline std::uint32_t SpellFor(std::uint32_t itemEntry)
{
    // A missing/NULL row and every unmapped entry retain the base heal.
    for (Legendary const& potion : Legendaries)
        if (potion.item == itemEntry)
            return potion.shell;
    return BaseSpell;
}
}
#endif
