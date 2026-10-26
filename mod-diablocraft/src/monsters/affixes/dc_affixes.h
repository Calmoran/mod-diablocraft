/*
 * World of DiabloCraft - elite packs and their affixes.
 *
 * What the rest of the rifts folder needs from the elite half. Split out of
 * dc_rifts.cpp; every name kept its spelling and signature.
 *
 * Internal to the rifts folder. Other modules include dc_rifts.h.
 */

#ifndef DC_RIFT_ELITES_H
#define DC_RIFT_ELITES_H

#include "../../rifts/dc_rifts_internal.h"

#include <string>
#include <vector>

class Creature;
class Map;
class Player;
class Position;
class WorldObject;

namespace DC::Rifts
{
// 09 section 2 step 2. Turns a native spawn into a champion or rare pack on the
// map's own update; the creature script decides, this does the swap.
void Promote(Map* map, Promotion const& promotion, unsigned tier);

// A champion pack (a champion and its identical companions) or a rare with its minions, standing at `at`: the clone of `entry`,
// its look, affixes, nameplate row and companions. Promote() feeds it a native's entry and spot; the spawner (dc_rift_spawner.cpp)
// feeds it a set monster at an anchor; `.dc elite` feeds it a harness body. Returns the pack leader, null when `entry` has no clone.
Creature* SpawnElitePack(Map* map, std::uint32_t entry, Position const& at, bool rare, unsigned tier, unsigned level,
                         bool rollAffixes, std::vector<Affix> const& preset, std::uint32_t instanceId,
                         WorldObject* summoner);

// Rebuilds the affix numbers from dc_affix_tunables. `.dc affix reload` is the
// only caller; false leaves the previous numbers in place with `error` set.
bool ReloadAffixNumbers(std::string& error);

// Rolls a pack's affixes for a tier and level (elite_affix_count.csv).
std::vector<Affix> RollAffixes(bool rare, unsigned tier, unsigned level);

// True when this map holds a `.dc elite` harness pack, so the rules that only
// apply to real spawns can step aside for it.
bool HarnessOnMap(Map const* map);

// Removes this player's harness packs; returns how many went.
unsigned ClearHarness(Player const* player);

// `.dc elite` spawns a pack in front of the player with the given affixes.
// `where` is null for "in front of me", which is what the command passes.
Creature* SpawnHarness(Player* player, bool rare, std::vector<Affix> const& affixes,
                       Position const* where);

// Resolves a partial affix name for the harness command; `names` carries the
// candidates when the match is ambiguous.
bool FindAffix(std::string const& wanted, Affix& chosen, std::string& names);

// Frees anything an affix took hold of on this player (roots, fears, the
// Jailer debuff), called when they leave the rift or log out.
void ReleasePlayerControls(Player* player);

// Reached from dc_rifts.cpp: the map update, the obelisk harness and the
// player hooks all still call these.
void PublishElite(Creature const* elite, EliteState const& state, std::uint32_t instanceId);
void UnpublishElite(std::uint32_t instanceId, std::uint64_t creatureGuid);
void ApplyPassiveAffixes(Creature* elite, EliteState const& state);
// A control hold (fear, freeze, root) as a stock aura from `donor`, `ms` long, cast by `source`; false when the
// player is immune to it. See the definition for the donors.
bool ApplyHold(Unit* source, Player* player, std::uint32_t donor, std::uint32_t ms);
// Issue #54: an affix slow for `ms`, as the stock negative speed aura, cast by
// `caster` so the core keeps it separate from every other elite's. Each runs its
// own clock and the core applies the strongest one still running.
// `spell` is the slowing affix's OWN record (Combat::Shells::AffixSlows):
// the debuff the player is shown is named after the affix, so the caller
// has to say which affix is slowing, not just by how much.
void ApplySlow(Unit* caster, Player* player, std::uint32_t spell, double rate,
               std::uint32_t ms);
double SwingDamage(Unit const* unit);

// A monster's speed and haste are stock auras, never a direct SetSpeed or SetAttackTime that the
// next speed effect to land or leave would rebuild away (Unit::UpdateSpeed). Multiplies the unit's pace by the ratios
// (1.0 leaves one alone); the ratios compose with each other and with anything else that speeds or slows it.
void AddPace(Unit* unit, double speedRatio, double hasteRatio);

// A lasting ground effect for the family AI: a pool at an anchor point that hurts whoever stands in it
// every `tickMs` for `durationMs`, on the hazard subsystem. The caster is a creature and the anchor is a position, so an
// invisible trigger creature can be either later. It is drained on any map, rift or not.
struct GroundEffect
{
    float x = 0, y = 0, z = 0, radius = 0;
    std::uint32_t shell = 0;            // a spell id: its school and combat-log name
    double damage = 0;                  // per tick, already the monster's own number
    std::uint32_t tickMs = 1000, durationMs = 0, armMs = 0;
};
void SpawnGroundEffect(Creature* source, GroundEffect const& effect);

// The elite half of the map tick. dc_rifts.cpp's OnMapUpdate calls this after
// its own closure drain; `rift` says whether this map is a live run, which
// decides whether promotions are drained at all.
void DrainEliteWork(Map* map, bool rift, unsigned tier);

std::string AffixPerformance(Map const* map);
void RegisterEliteScripts();
}

#endif // DC_RIFT_ELITES_H
