/*
 * World of DiabloCraft - mod-diablocraft
 *
 * loot: the declarations the loot files share
 *
 * Internal to src/loot: declarations only, no logic. What dc_loot.cpp (the roll, the loaded data, the hooks) and
 * dc_loot_delivery.cpp (the bags, the buffer, the claim) call across files. Other folders include dc_loot.h.
 */

#ifndef DC_LOOT_INTERNAL_H
#define DC_LOOT_INTERNAL_H

#include "dc_loot.h"

#include <cstdint>
#include <string>

namespace DC::Loot::Detail
{
    // dc_loot.cpp
    std::string D3Class(Player const* player);
    bool ShellFor(std::uint32_t baseItem, std::string& rarity, std::uint32_t& shellEntry);
    // dc_loot_delivery.cpp
    bool CorpseDelivery(Creature const* deathSource);
    bool DeliverShell(Player* player, std::uint32_t baseItem, unsigned itemLevel, std::string const& rarity,
                      std::uint32_t shellEntry, char const* source, unsigned tier, std::string const& rollClass,
                      std::string const& quality = "normal");
    bool DeliverItem(Player* player, std::uint32_t baseItem, unsigned itemLevel, char const* source, unsigned tier,
                     std::string const& rollClass, std::string const& quality = "normal");
    void Buffer(Player* player, std::uint32_t baseItem, unsigned itemLevel, char const* source, unsigned tier,
                std::string const& rollClass, std::string const& quality = "normal");
    void DeliverGemDrop(Player* player, std::uint32_t gem, unsigned level, char const* source, unsigned tier,
                        Creature* deathSource, bool corpse, bool ground, Position const& at);
    std::uint32_t BrokenCrownGem(Player* player, std::uint32_t dropped);
    void DeliverBuffered(Player* player);
    void FirstBossKill(Player* player, std::uint32_t creatureEntry, unsigned monsterLevel, Creature* deathSource);
} // namespace DC::Loot::Detail

#endif // DC_LOOT_INTERNAL_H
