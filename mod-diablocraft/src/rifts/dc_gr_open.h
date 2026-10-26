/*
 * World of DiabloCraft - opening a Greater Rift.
 *
 * The obelisk's menu, the opener's level and Keystone, the party ready check and the start.
 * The decisions are in dc_gr_ready.h; this is the half that reads players, groups and the
 * Keystone balance. Internal to the rifts folder.
 */

#ifndef DC_GR_OPEN_H
#define DC_GR_OPEN_H

#include "Define.h"

#include <cstdint>

class GameObject;
class Player;

namespace DC::Rifts
{
    // The obelisk's menu: Nephalem Rift or Greater Rift. A party that already has a run goes
    // straight to the quest offer, which says what that run allows.
    void OpenObeliskMenu(Player* player, GameObject* obelisk);

    // A choice made on that menu. Greater Rift sends the opening window its levels (the item has no
    // code box any more; `code` is ignored). True when the menu item was ours.
    bool ObeliskSelect(Player* player, GameObject* obelisk, uint32 sender, uint32 action, char const* code);

    // `.dc rift accept <id>` / `.dc rift decline <id>`: the player's answer to the ready check.
    // Says its own result to the player.
    void RespondGreaterRift(Player* player, std::uint64_t proposalId, bool accept);

    void RegisterGreaterRiftOpenScripts();
} // namespace DC::Rifts

#endif // DC_GR_OPEN_H
