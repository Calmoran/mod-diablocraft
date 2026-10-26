/*
 * World of DiabloCraft - account stash (11-hardcore §4).
 *
 * Public surface of the stash. The stash is keyed by (account, mode) only: no
 * character key, no guild row, no leader guid. The native guild bank and core
 * patch 0006 are closed; this is our own storage over our
 * own dc_ tables, drawn by the Diablocraft addon and bridged by AIO.
 *
 * Everything that decides - eligibility, item legality, slot legality, payment -
 * lives here in C++. Lua asks and draws, it never decides.
 */

#ifndef DC_STASH_H
#define DC_STASH_H

#include <cstdint>
#include <functional>
#include <string>
// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (70): SlotsPerTab, stash slots per tab (7x10 grid); structural, the storage layout the DB rows, dc_stash.h and dc_stash.lua share.
// Constant (5.5): OpenRange, the range the stash window opens at; engine value, changing it would desync from the core's own gossip gate.
// Constant (910002): stash NPC entry; identifier.

class Player;

namespace DC::Stash
{
    // 70 slots per tab in a 7x10 grid as in D3, one tab free
    // and four more purchasable at dc_stash_tuning.price_gold, five tabs maximum.
    //
    // Audit row 29, a constant:
    // structural: the 7x10 stash grid is the storage layout shared by the DB
    // rows, dc_stash.h and dc_stash.lua; changing it live would orphan stored
    // items. It is not a tunable and has no dc_tunables row; larger tabs are a
    // migration, not a `.dc tunables set`.
    constexpr std::uint8_t SlotsPerTab = 70;
    // tunables:economy.
    std::uint8_t MaxTabs();
    std::uint8_t LaunchTabs();

    // 08-world hub Stash. Range, map and phase are all checked through it.
    constexpr std::uint32_t StashEntry = 910002;

    // The window opens at INTERACTION_DISTANCE, the range the
    // core gates the NPC gossip on, but every action and the auto-close allow a
    // yard more. The slack is deliberate and one-directional: an open window never
    // refuses, and it shuts before the player reaches a distance that could not
    // have opened it. Lua carries the same two numbers (dc_stash.lua).
    // OpenRange is a constant: it is the core's own INTERACTION_DISTANCE, pinned
    // by a static_assert in dc_stash.cpp, not a number to tune.
    constexpr float OpenRange = 5.5f;   // == INTERACTION_DISTANCE
    // tunables:ui. dc_stash.lua reads the same row.
    float ActionRange();

    // Frees the cached container when the last character of an (account, mode) logs
    // out. The rows themselves are never deleted here: A5 keeps the stash alive
    // across character deletion, guild disband and restart. Only deleting the ACCOUNT
    // deletes the stash and its parked items (AccountSweep in dc_stash.cpp).
    void ReleaseFor(Player const* player);

    // A new item of `entry` straight into the first free slot of the player's (account, mode) stash, from the server: no
    // window, no Stash object, no range (bounties W4, the cache delivery: bags, else the stash, else lost). `also` is the
    // caller's own statement for the new item, given its guid, written in the same transaction ("" for none). Durable
    // before it returns true; false writes nothing:
    // a character with no mode yet or a fallen Hardcore one, an unknown entry, a full stash, or a commit that failed.
    // On the player's own thread, like every stash operation.
    bool DeliverNew(Player* player, std::uint32_t entry,
                    std::function<std::string(std::uint32_t itemGuid)> const& also = nullptr);

    void RegisterScripts();
} // namespace DC::Stash

#endif // DC_STASH_H
