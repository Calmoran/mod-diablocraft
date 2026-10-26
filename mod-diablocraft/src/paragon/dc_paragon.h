/*
 * World of DiabloCraft - mod-diablocraft
 *
 * paragon: account-wide paragon, HC/normal pools
 *
 * Public surface of the paragon folder. Other folders include only this header.
 * Mode selection and module registration; account/character state stays private.
 */

#ifndef DC_PARAGON_H
#define DC_PARAGON_H

#include <cstdint>
#include <string>

class Player;
namespace DC::Paragon
{
// 11-hardcore supplies the authoritative mode: a Hardcore character earns and
// spends the Hardcore account pool, a Normal one the Normal pool (10-paragon P3).
enum class Pool { Normal, Hardcore };
Pool PoolFor(Player const* player);
// Grants Paragon XP from outside this folder, taking the module's own lock.
// The caller supplies the FINAL amount: no tier bonus, party split or any other
// multiplier is applied here, exactly as the kill path computes its own before
// granting. Returns false with `error` set - never throws - so one ineligible
// player (not level 70, state not loaded) cannot abort a batch of grants.
// Zero is a no-op and succeeds. 09-rifts 7.9.7's closing reward is the caller.
bool GrantXP(Player* player, std::uint64_t amount, std::string& error);
// Raise the player's active account pool to at least target, paying the exact
// XP owed through the ordinary award path. Existing allocations stay intact;
// points earned by the new levels remain unspent.
bool TopUpLevel(Player* player, std::uint32_t target, std::uint32_t& before,
                std::uint32_t& after, std::string& error);
// Creation/resume floor for the character's permanent mode pool. No login
// state is required. Raised pools end at zero in-level XP; higher pools retain
// their XP. Per-character allocations are untouched (new points are unspent).
bool EnsureStartingLevel(Player* player, std::uint32_t target, std::string& error);
void RegisterScripts();
}
#endif // DC_PARAGON_H
