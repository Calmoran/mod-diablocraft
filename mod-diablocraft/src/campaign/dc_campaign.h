/*
 * World of DiabloCraft - mod-diablocraft
 *
 * campaign: acts, quest phasing, bounties, followers
 *
 * Public surface of the campaign folder. Other folders include only this header.
 * Today that is the followers: the three companions a player hires at the hub (contract
 * docs/contracts/followers.md).
 */

#ifndef DC_CAMPAIGN_H
#define DC_CAMPAIGN_H

#include "dc_follower_rules.h"

class Creature;
class Player;

namespace DC::Campaign
{
    void RegisterScripts();

    namespace Followers
    {
        // The creature entry of a follower; 0 when the roster is not loaded.
        std::uint32_t EntryOf(Id follower);

        // The follower this player has hired (Id::None when none).
        Id Hired(Player const* player);

        // Hires one follower for this player, replacing the one hired before; its companion stands beside the player
        // when the player is alone. False when the roster is not loaded.
        bool Hire(Player* player, Id follower);

        // Dismisses the hired follower, if any.
        void Dismiss(Player* player);

        // The companion standing beside the player now, or null (nothing hired, down, a party, mid-teleport).
        Creature* Companion(Player* player);
    } // namespace Followers
} // namespace DC::Campaign

#endif // DC_CAMPAIGN_H
