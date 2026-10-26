/*
 * World of DiabloCraft - the rules of a legendary gem item that need no core: which base items
 * it may be socketed into, which of the socketed gems count, and whether a copy is already worn. Contract
 * docs/contracts/legendary-gems.md. No core dependency, so the test compiles this exact file.
 */

#ifndef DC_LEGENDARY_GEM_ITEM_H
#define DC_LEGENDARY_GEM_ITEM_H

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace DC::LegendaryGemItem
{
    // socketSlots is dc_legendary_gem_item.socket_slots, base-item slots joined by '|' ("neck|finger");
    // baseSlot is dc_base_item.slot. Gem of Ease takes a weapon, every other
    // legendary gem takes jewelry; the sheet (legendary_gem_items.csv) says which, not this function.
    inline bool SlotAllowed(std::string const& socketSlots, std::string const& baseSlot)
    {
        if (baseSlot.empty() || baseSlot.find('|') != std::string::npos)
            return false;
        std::string const padded = "|" + socketSlots + "|";
        return padded.find("|" + baseSlot + "|") != std::string::npos;
    }

    // Unique Equipped: a legendary gem cannot be socketed, and an item
    // holding one cannot be worn, while the same gem is socketed in what the character wears. A gem socketed
    // in worn gear, with the item it sits in and its own row (affix seq) in that item.
    struct WornGem
    {
        std::string gemId;
        std::uint64_t item = 0;
        unsigned seq = 0;
    };

    // The first worn copy of `gemId` that is not about to go: not in an item in `leaving` (an item being taken
    // off, or the one this equip replaces), and not the row `replaced` (a swap takes that gem out). nullptr when
    // none stays, so the new one may go in. Callers name the item from the row it returns.
    inline WornGem const* WornCopy(std::vector<WornGem> const& worn, std::string const& gemId,
                                   std::vector<std::uint64_t> const& leaving = {},
                                   std::optional<std::pair<std::uint64_t, unsigned>> replaced = std::nullopt)
    {
        for (WornGem const& gem : worn)
        {
            if (gem.gemId != gemId)
                continue;
            if (std::find(leaving.begin(), leaving.end(), gem.item) != leaving.end())
                continue;
            if (replaced && replaced->first == gem.item && replaced->second == gem.seq)
                continue;
            return &gem;
        }
        return nullptr;
    }

    struct Socketed
    {
        std::string gemId;
        std::uint32_t rank = 0;
    };

    // Unique Equipped: one of each gem counts at a time. WornCopy keeps a second
    // from being socketed or worn, so this stays as the backstop for a pair saved before WornCopy refused it. Given the legendary gems socketed on
    // everything the character wears, in any order, the ones whose powers apply: one per gem_id, the
    // highest rank, so the choice never depends on which slot is walked first. Sorted by gem_id.
    inline std::vector<Socketed> Counted(std::vector<Socketed> const& worn)
    {
        std::vector<Socketed> counted;
        for (Socketed const& gem : worn)
        {
            auto found =
                std::find_if(counted.begin(), counted.end(), [&](Socketed const& c) { return c.gemId == gem.gemId; });
            if (found == counted.end())
                counted.push_back(gem);
            else if (gem.rank > found->rank)
                found->rank = gem.rank;
        }
        std::sort(counted.begin(), counted.end(),
                  [](Socketed const& a, Socketed const& b) { return a.gemId < b.gemId; });
        return counted;
    }
} // namespace DC::LegendaryGemItem

#endif
