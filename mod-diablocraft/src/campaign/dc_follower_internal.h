/*
 * World of DiabloCraft - the followers, what dc_followers.cpp (who is hired, the companion's life) shares with
 * dc_follower_creature.cpp (the creature's AI and its gossip).
 */

#ifndef DC_FOLLOWER_INTERNAL_H
#define DC_FOLLOWER_INTERNAL_H

#include "dc_campaign.h"
#include "ObjectGuid.h"

#include <cstdint>
#include <string>

namespace DC::Campaign::Followers
{
    // One row of dc_follower (data/d3/followers_roster.csv).
    struct Row
    {
        Id id = Id::None;
        std::uint32_t entry = 0;
        std::string name;
    };

    // The row of a creature entry or of an id; null when the roster is not loaded or the entry is not a follower's.
    Row const* ByEntry(std::uint32_t entry);
    Row const* ById(Id id);

    // The rules of dc_follower_rule, valid once the roster is loaded.
    Rules const& CurrentRules();

    // Whether the follower of this creature entry, hired by `viewer`, stands beside them as their companion now. The
    // hub copy of that follower is then hidden from this player (FollowerAI::CanBeSeen) and from no one else.
    bool OutFor(Player const* viewer, std::uint32_t entry);

    // Whether this creature is the companion the owner's state holds. A companion that is not it (left behind on a
    // map the player came back to) leaves.
    bool IsCompanionOf(ObjectGuid owner, ObjectGuid companion);

    // The companion fell: its follower comes back after the revive rule.
    void OnCompanionFell(ObjectGuid owner);

    // The level the next follower summoned on this thread takes: its owner's. 0 clears it.
    void SetNextSummonLevel(std::uint8_t level);

    void RegisterCreatureScripts();
} // namespace DC::Campaign::Followers

#endif
