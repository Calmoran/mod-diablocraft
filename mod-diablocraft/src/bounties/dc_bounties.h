/*
 * World of DiabloCraft - bounties (docs/research/bounties.md, contract
 * docs/contracts/bounty-messages.md).
 *
 * The board a player plays is their party's (the leader's board, copied when the party forms) or, solo, their own. The
 * objectives (W2, dc_bounty_objectives.cpp: the named Unique's kill, the Click channel) credit it through the calls
 * below; every online member of the board's owner then gets the board again on DCBOUNTY.
 */
#ifndef DC_BOUNTIES_H
#define DC_BOUNTIES_H

#include "dc_bounty_board.h"

#include <cstdint>
#include <utility>
#include <vector>

class Player;

namespace DC::Bounties
{
    void RegisterScripts();
    void RegisterObjectiveScripts(); // dc_bounty_objectives.cpp (W2)
    void RegisterCacheScripts();     // dc_bounty_cache.cpp (W4)
    void RegisterQuestScripts();     // dc_bounty_quests.cpp

    // W4: `member` is owed column `column`'s Horadric Cache at their tier of this moment; their own next update (or their
    // logout) delivers it: bags, else the account stash, else lost with a chat line. Safe from any thread.
    void OweCache(Player* member, unsigned column);

    // Complete bounty `id` on the board `player` plays. False when that board does not hold it open.
    bool Complete(Player* player, std::uint32_t id);
    // Count `amount` towards its need (a Kill's monsters, a Click's objectives); never completes it.
    bool AddProgress(Player* player, std::uint32_t id, std::uint32_t amount);
    // A Click objective of bounty `id` (`spot` 0 up, dc_bounties_spot.spot - 1) done on the board `player` plays; the
    // last one completes the bounty. False when that board does not hold that objective to do.
    bool Click(Player* player, std::uint32_t id, unsigned spot);

    // W2: what the objectives need from the board.
    // Whose board `player` plays, as one number: their party's, else their own. A bounty's monsters and objects belong
    // to it, and only players with the same key see them. No database, no lock: safe on the visibility path.
    std::uint64_t OwnerKey(Player const* player);
    // An open bounty of that board in this map and zone: a Kill's Unique on its one spot, or a Click's spots still to
    // click, each with its number (0 up).
    struct Open
    {
        std::uint32_t bounty = 0, uniqueEntry = 0, objectiveEntry = 0;
        std::vector<std::pair<unsigned, Spot>> spots;
    };
    std::vector<Open> OpenIn(Player* player, std::uint32_t mapId, std::uint32_t zoneId);
    // Moves on every change to a board or to who plays which; a player whose last look was at another epoch looks again.
    std::uint64_t Epoch();
    // A map some bounty stands on (the catalogue's map ids).
    bool IsBountyMap(std::uint32_t mapId);

    // Bounties as quests: what `player`'s quest log needs from the board they play (SyncQuests; `here`: they
    // are in the world on a bounty map, their own map and zone).
    QuestSync QuestsFor(Player* player, std::vector<QuestRow> const& rows, std::vector<std::uint32_t> const& held, bool here);
    // Logout loses the board: at `player`'s login, the boards they play that BoardExpired says are gone (their
    // own; their party's, with every member's own) are deleted, and the next look draws a new one.
    void ExpireBoardsOnLogin(Player* player);
} // namespace DC::Bounties

#endif
