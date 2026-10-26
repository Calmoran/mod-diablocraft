// World of DiabloCraft - what dc_rifts.cpp, dc_rift_open.cpp and dc_rift_scripts.cpp share: constants, the hub types and state.

#ifndef DC_RIFTS_SHARED_H
#define DC_RIFTS_SHARED_H

#include "dc_rifts_internal.h"
#include "../common/dc_tunables.h"

#include "ObjectGuid.h"

#include <cstdint>
#include <functional>
#include <mutex>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

class Creature;
class GameObject;
class Map;
class Player;


// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (0.1): portal Z offset above the rubble; Keeps the portal ring on top of the rubble.
// Constant (55759, 190386, 12999, 11686, 35, 1000): shatter spell, rubble object, trigger template, its invisible display, its faction, its lifetime; Identifiers and a lifetime that only has to outlive the cast.
// Constant (30.0): OBELISK_SEARCH_YARDS; Lookup radius, not gameplay.
// Constant (200.0): ABILITY_SCAN_RANGE for .dc rift abilities; GM command sweep.
// Constant (6): how many offenders .dc rift abilities names before it stops; Output limit.
// Constant (17301, 8000000, 9000000, 910003, 910011, 910015): harness template, champion/rare clone bases, Keeper, obelisk, credit creature; Identifiers.

namespace DC::Rifts
{
    // The hub's rift obelisk, placed by 08-world's generate_hub.py as
    // "Rift Obelisk (inactive)". This module is what makes it active.
    constexpr std::uint32_t OBELISK_ENTRY = 910011;
    // rift_quests.csv, emitted by rifts_0011. The credit template is never spawned:
    // it exists so the synthetic objective has a real creature entry to point at
    // (7.3).
    constexpr std::uint32_t CREDIT_CREATURE = 910015;
    // The single-display entrance 910014 is gone: the run-owned
    // party-only portal beside the obelisk (7.9.7) now has a POOL of looks in
    // rift_portals.csv, one rolled per rift. There is no ENTRANCE_OBJECT constant
    // any more on purpose - the entry a rift used is on its own Entrance row, and
    // what the obelisk script recognises as A portal is the loaded pool.
    // 7.3, since monster spawning S3: the quest denominator is the whole bar in hundredths of a D3
    // progress point (65,000), the same for every dungeon; each kill adds its monster's own points.
    constexpr float ABILITY_SCAN_RANGE = 200.0f; // `.dc rift abilities` sweep

    // --- the obelisk break-apart sequence (09-rifts 7.9.8) ---------------------
    //
    // Picks from the `.dc shatter` preview: spell
    // 55759 (Earth Revenant Entrance, a radial ground dust nova - NOT the research's
    // 33671), rubble 190386 (Rock Rubble, which is the obelisk's own footprint), and
    // the default timings of 200 ms and 800 ms.
    //
    // The dust and the obelisk leaving are ONE step, at t = 0, rather than the
    // research's hide-at-0 / cast-at-0.1: a 100 ms gap is the obelisk popping out of
    // existence and the dust arriving afterwards to explain it. `.dc shatter` was
    // changed to remove its stand-in on the same tick so the preview and the real
    // path play the same clock.
    // Constants: the shatter spell and the rubble gameobject entry.
    constexpr std::uint32_t OPEN_SPELL = 55759;
    constexpr std::uint32_t OPEN_RUBBLE = 190386;
    // tunables:rifts. `.dc shatter`'s preview reads the
    // same two rows, so the preview and the real path cannot drift apart.
    inline std::uint32_t OpenRubbleMs() { return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "open_rubble_ms")); }
    inline std::uint32_t OpenPortalMs() { return static_cast<std::uint32_t>(DC::Tunables::Get("rifts", "open_portal_ms")); }
    // The research's own offset, so the portal's ground ring sits on the rubble
    // rather than inside it.
    constexpr float OPEN_PORTAL_Z = 0.1f;
    // obelisk-shatter.md 5.2: the 3.3.5a client will not draw a particle effect at
    // bare coordinates, so the explosion is cast by an invisible stalker standing
    // where the obelisk stood. Never by a player and never at one.
    constexpr std::uint32_t OPEN_TRIGGER_ENTRY = 12999;   // World Invisible Trigger
    constexpr std::uint32_t OPEN_TRIGGER_DISPLAY = 11686; // the invisible model on it
    // creature_template 12999 ships with faction 114, a hostile monster faction, and
    // that is what let a previewed spell damage the caster: an enemy-targeting area
    // effect from a hostile caster picks players up. 35 is friendly to everyone, so
    // no such effect has a target here.
    constexpr std::uint32_t OPEN_TRIGGER_FACTION = 35;
    constexpr std::uint32_t OPEN_TRIGGER_MS = 1000; // long enough to outlive the cast
    // The accepter is standing at the obelisk to have taken the quest from it, so
    // interaction range plus slack. Wide enough for a slow client that has drifted,
    // narrow enough that it cannot find a different obelisk - the Sanctum has one,
    // in its one shared phase (dc_world.h SanctumPhase).
    constexpr float OBELISK_SEARCH_YARDS = 30.0f;
    // 7.9.7: ONE portal per party, run-owned, beside the obelisk, party-only, open
    // for the whole run lifetime including the closing countdown. It is not a town
    // portal pair - there is no far end to summon, because the dungeon entrance is
    // a teleport target, not a place we own an object in.
    struct Entrance
    {
        ObjectGuid object; // the hub-side portal
        std::uint32_t instanceId = 0; // floor 1's: the obelisk's portal always leads there (rift floors 6.8)
        std::uint32_t mapId = 0;
        float x = 0.0f, y = 0.0f, z = 0.0f, o = 0.0f; // the dungeon entrance it leads to
        std::uint32_t phase = 1;                      // the Sanctum's shared phase, as the town portal does
        std::uint32_t portalEntry = 0;                // the look this rift rolled out of the pool
        // 7.9.8: the rubble the obelisk left behind, and the obelisk itself, which is
        // hidden for the life of the run and brought back at closure. hubMapId and
        // obeliskSpawnId are kept so both can be found again without a Player - a
        // closure can run from the instance's map thread with nobody in the hub.
        ObjectGuid rubble;
        ObjectGuid obelisk;
        std::uint32_t obeliskSpawnId = 0;
        std::uint32_t hubMapId = 0;
        float ox = 0.0f, oy = 0.0f, oz = 0.0f, oo = 0.0f; // where the obelisk stood
    };
    // 7.9.8's clock. The rubble and the portal land after the explosion has started,
    // so the swap happens under the dust; both steps are queued here at t = 0 and
    // drained on the HUB map's own update, which is the thread that owns the objects.
    struct Opening
    {
        std::uint64_t runId = 0;
        std::uint32_t hubMapId = 0, phase = 1, portalEntry = 0;
        float x = 0.0f, y = 0.0f, z = 0.0f, o = 0.0f;
        std::uint32_t elapsed = 0;
        bool rubbleDone = false, portalDone = false;
        ObjectGuid notify; // the accepter, so a step that fails says so out loud
    };
    // The live claim, read by the AI factories while a summon is in flight. Same
    // pattern and the same reason as `opening` above: the work is synchronous inside
    // one call, so a thread_local is exact and a shared slot would not be.
    struct Claim
    {
        std::uint64_t run = 0;
        ObjectGuid owner;
        bool Active() const
        {
            return run != 0 || bool(owner);
        }
    };

    // Defined in dc_rifts.cpp.
    extern std::vector<PortalLook> portalPool;
    extern std::set<std::uint32_t> portalEntries;
    extern thread_local Rift* opening;
    extern std::vector<Rift> closingRifts;
    extern std::set<std::uint32_t> resetWhenEmpty;
    extern std::unordered_map<std::uint32_t, std::vector<ObjectGuid>> riftMembers;
    extern std::unordered_map<std::uint64_t, Entrance> entrances;
    void RemoveEntrance(std::uint64_t runId);
    extern std::vector<Opening> openings;
    extern thread_local Claim claiming;
    void EraseInstanceWork(std::uint32_t instanceId);
    bool CanSeeHubObject(GameObject const* go, std::uint64_t owningRun, ObjectGuid owner, Player const* seer);
    bool OwnedRift(Player const* player, Rift& result);
    PortalLook RollPortal();
    bool IsEntrancePortal(std::uint32_t entry);
    GameObject* PlaceHubObject(Map* map, std::uint64_t runId, std::uint32_t entry, float x, float y, float z,
                               float o, std::uint32_t phase);

    // Defined in dc_rift_open.cpp.
    void DrainOpenings(Map* map, std::uint32_t diff);
    void UseEntrance(Player* player, GameObject* go);
    void RecordLaterFloor(Rift& rift);
    std::string TrimArgument(std::string text);
}

#endif
