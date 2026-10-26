/*
 * World of DiabloCraft - Nephalem Rifts, stage 1 (09-rifts F1-F5, F7).
 *
 * Public surface of the rifts folder.
 */

#ifndef DC_RIFTS_H
#define DC_RIFTS_H

#include "ObjectGuid.h"

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

class Player;
class Unit;
class Creature;
class CreatureAI;
class Map;
class WorldLocation;

namespace DC::Rifts
{
    double EliteDamageMultiplier(Unit const* source);
    // One open rift, mirroring dc_rift. A Rift is a RUN (rift floors Part F1, dc_rift_floors.h): `id` names it.
    // The copies the lookups hand out are the run seen from one floor, so instanceId, mapId and dungeonId are that
    // floor's and `floor` is its number (1 is where the run starts); the run's own row keeps floor 1's. Code that means
    // "this map" reads those three; code that means "the run" (membership, closure, deaths, progress) reads `id`.
    struct Rift
    {
        std::uint64_t id = 0;
        std::uint32_t instanceId = 0, mapId = 0, dungeonId = 0;
        unsigned floor = 1;
        // The instance the Guardian spawned in, 0 until it has (rift floors 6.9: the Greater Rift clear and its sweep
        // belong to that floor only). Memory only, like the rest of the live run.
        std::uint32_t guardianInstance = 0;
        // The persisted OWNER, not the current group leader. 7.9.7: the owner
        // leaving no longer closes the run, and leadership moves as WoW moves it,
        // so this is cleanup bookkeeping only. The column keeps its old name.
        std::uint64_t leaderGuid = 0;
        unsigned tier = 1;
        unsigned players = 1; // enrolled headcount; Nephalem Rifts rescale when it moves (7.9.7)
        unsigned kills = 0, required = 0; // required: retired by S3 (no kill count any more), always 0
        // 7.3's progress units, since S3 hundredths of a D3 progress point (monster-spawning.md 3.9.4).
        // progress is capped at requiredUnits (the quest's count, 65,000 for the 650 points that fill the
        // bar), and is what the quest counter and the AIO bar both read. Raw kills stay for the model and
        // diagnostics; guardian spawning is on progress.
        unsigned progress = 0, requiredUnits = 0;
        std::uint32_t questId = 0;  // the fixed variant every enrolled member holds
        std::string mode = "nr";    // nr | gr (gr opens through dc_gr_open.cpp)
        unsigned grRank = 0;        // the Greater Rift level of this run; read only when mode is gr (dc_rift.gr_rank)
        std::int64_t deadline = 0;  // gr only: the shared deadline, unix seconds (dc_rift.deadline); 0 for nr
        // gr only: pending until the Guardian dies or the clock runs out, then `success` (beaten:
        // the Guardian died before 0:00) or `expired` (failed). timeLeft is the whole seconds left when
        // the Guardian died, 0 for a failed run. Both mirror dc_rift.outcome and dc_rift.time_left.
        std::string outcome = "pending";
        unsigned timeLeft = 0;
        std::string state = "open"; // open | guardian | complete | closed
    };

    // One entrance-portal look, as rift_portals.csv writes it and dc_rift_portal
    // carries it. A rift rolls one of these when it opens, so each rift entrance
    // differs. `scale` is a per-look tunable, which is why a
    // portal that sits too large is a CSV change and not a code change. `name` is
    // the look's label for the GM preview and is never shown to a player:
    // every template is called "Rift Entrance" in game.
    struct PortalLook
    {
        std::uint32_t entry = 0, display = 0;
        float scale = 1.0f;
        std::string name;
    };

    // The loaded pool in entry order, empty if startup failed. It is on the public
    // surface only because `.dc shatter` has to preview the same looks the real
    // open path rolls, and that preview is its own translation unit; nothing
    // outside mod-diablocraft/src/rifts/ has any business calling it.
    std::vector<PortalLook> PortalPool();

    // 7.9.8: the rift opening sequence is PRIVATE to the party running it. Every hub
    // object it puts in the world - rubble, portal, and the invisible stalker that
    // casts the explosion - answers `CanBeSeen(seer)` for itself, and the shared hub
    // obelisk answers it too so it is hidden from that party and left standing for
    // everyone else.
    //
    // The AI that answers is built by the core inside `GameObject::Create` /
    // `Creature::AddToWorld`, which is deep inside the summon call and long before
    // the summon returns a pointer we could configure. So a claim is declared around
    // the summon instead, and the AI the core builds is already bound to its owner:
    // that is the only way the FIRST create packet is correct, and a create packet
    // that goes out wrong cannot be taken back without the outsider seeing a flicker.
    //
    // Whatever is created with no spawn id while a claim is live belongs to that
    // claim. The window is one summon call, so nothing else can fall into it; a grid
    // load inside it only ever creates rows from the database, and those have spawn
    // ids.
    class HubObjectClaim
    {
    public:
        // Everything summoned in this scope belongs to that run's party.
        explicit HubObjectClaim(std::uint64_t runId);
        // Everything summoned in this scope belongs to that one player. This is the
        // `.dc shatter` preview: a preview that everyone can see is not a preview of
        // something private.
        explicit HubObjectClaim(Player const* onlyFor);
        // The same, for a player who is not at hand (the town portal's hub half is
        // placed on the hub map's own update, from the owner's guid alone).
        explicit HubObjectClaim(ObjectGuid onlyFor);
        ~HubObjectClaim();
        HubObjectClaim(HubObjectClaim const&) = delete;
        HubObjectClaim& operator=(HubObjectClaim const&) = delete;
    };

    // Who that party IS. `dc_rift_member` stays the durable store; these keep the
    // in-memory cache the visibility check reads, and each is called from the same
    // function that writes the row, so the two cannot drift. See the RiftMembership
    // comment in dc_rifts.cpp for the closed list of writers.
    //
    // Folder-internal, like PortalPool above: they are on this header rather than
    // dc_rifts_internal.h only because dc_rift_quests.cpp is the caller and this
    // header is the one both sides already include. Nothing outside
    // mod-diablocraft/src/rifts/ has any business calling them.
    // Keyed by the run (dc_rift.id), not by an instance: a run holds one instance per floor.
    void JoinMembership(std::uint64_t runId, ObjectGuid player);
    void LeaveMembership(std::uint64_t runId, ObjectGuid player);
    void ClearMembership(std::uint64_t runId);

    // F3. Rolls a dungeon from the pool, records the rift and sends the opener in.
    // Refused with `error` set when the player is already in one or the pool is
    // unavailable.
    //
    // 7.9.7 moved the player-facing entry to the obelisk's QUEST: the first accepter
    // creates the run, the rest use its portal. This stays as the run-creation
    // primitive behind that, and as the `.dc rift open` harness.
    bool Open(Player* player, std::string& error);

    // The rift the player is standing in, if any.
    bool Current(Player const* player, Rift& rift);

    // Return portals must not rely on a binding alone after a run has closed.
    bool IsLiveInstance(std::uint32_t mapId, std::uint32_t instanceId);

    // True when the player stands in a live rift's instance and is not enrolled in that run. Reads the membership cache, not
    // dc_rift_member: no SQL, and a join is in it the moment EnrollMember runs.
    bool OutsiderInRift(Player const* player);

    // Cached instance context, including closed runs until map destruction so an
    // already-claimed creature never falls back to AutoBalance's dungeon path.
    bool ScalingContext(Map const* map, unsigned& tier, unsigned& players);

    // The Greater Rift level of the run this map is the instance of, 0 when it is not a Greater
    // Rift's (a Nephalem Rift, the open world, no run). Same cache and same lifetime as
    // ScalingContext, so a closed run still answers until the map is destroyed.
    unsigned GreaterRiftLevel(Map const* map);

    // A4: the Life factor an elite affix or an Illusionist copy puts on a creature (Juggernaut, Illusionist), 1.0 for any
    // other. The scaling owner multiplies it into the creature's Life every time it scales it.
    double EliteLifeFactor(Creature const* creature);

    // A monster under a player's charm (not a pet, guardian, totem, critter or trigger). It fights for
    // the player until the charm ends. docs/contracts/legendary-world-pieces.md says what each rift system does with it.
    bool IsCharmedMonster(Creature const* creature);

    // Mark (true) or unmark (false) a player the Desecrator, Molten and Plagued ground effects pass by
    // (Blackthorne's Battlegear 4-piece). Combat's item refresh calls it on every refresh; the mark is by character guid.
    void SetGroundEffectImmune(Player const* player, bool immune);

    // True for one of the loaded rift Guardian creature entries (defined in dc_rift_ai.cpp, also declared in
    // dc_rift_ai.h); the difficulty scaling gives every one of them the same base Life.
    bool IsGuardianEntry(std::uint32_t entry);

    // The Greater Rift rules (dc_gr_rules.cpp). Every one is false or
    // zero outside a Greater Rift, so a caller outside the rifts folder needs no mode test of its own.
    //
    // Rule 1: a creature that must roll no loot (every monster of a Greater Rift but its Guardian).
    bool GreaterRiftNoLoot(Creature const* creature);
    // Rule 6: the player stands in a Greater Rift whose Guardian is still alive, so gear stays as it is.
    bool GreaterRiftGearLocked(Player const* player);
    // Rule 5: the player stands in a live Greater Rift whose Guardian is still alive, where reviving in
    // town is refused (it opens with the kill).
    bool GreaterRiftTownReviveRefused(Player const* player);
    // The player stands in a Greater Rift whose Guardian is dead (the run may be paid or closed). The skill
    // bar's every-instance refusal (04 section 3) gives way there, as D3's does.
    bool GreaterRiftGuardianDead(Player const* player);
    // Rule 5: whole seconds the dead player still waits before any revive in a Greater Rift, 0 when none.
    unsigned GreaterRiftReviveWaitLeft(Player const* player);
    // The XP split: a Greater Rift kill's XP after the monster share or the Guardian multiple.
    // `amount` comes back unchanged outside a Greater Rift and while the number is not set.
    std::uint64_t GreaterRiftXp(Creature const* victim, std::uint64_t amount);

    // The highest Greater Rift level this character has beaten in time as the only
    // member of its run, 0 for none, in its realm mode. Torment VII to XVI read it (difficulty_tiers.csv
    // unlock_solo_gr).
    unsigned GreaterRiftBeatenSolo(std::uint32_t guid);
    // The best solo level the character's ACCOUNT has beaten in the character's mode (dc_account_gr_solo; it
    // stays when a character is deleted). D3 unlocks Primal Ancients on it; 0 is none.
    unsigned AccountGreaterRiftBeatenSolo(std::uint32_t guid);

    // F3. Leader-only; unbinds the instance so it is not re-entered.
    bool Close(Player* player, std::string& error);

    // True when this creature is standing in a live rift, and the rift's tier, so
    // 06's kill roll can use the rift legendary bonus and the recorded tier rather
    // than assuming the open world.
    bool InRift(Creature const* creature, unsigned& tier);

    // The dungeon entrance the rift dropped the party at, for a player standing in
    // one. 11-hardcore §3 respawns a dead normal-mode character here instead of
    // making it walk back from a graveyard.
    bool EntryPosition(Player const* player, WorldLocation& entry);

    // Bounties: true for an open-zone copy map, where the open world is an instance copy: a map a
    // dc_rift_open_zone row names (751 Kalimdor; 752 and 753 once their zones join).
    bool IsOpenZoneMap(std::uint32_t mapId);
    // _global rift_logout_grace_seconds (dc_affix_tunables), 0 when missing; dc_rift_quests.cpp. Bounties use the same grace
    // for a board's logout.
    unsigned LogoutGraceSeconds();
    // Bounties W5: one teleport of `player` into their party's copy of open zone `zoneKey` (rift_open_zones.csv key):
    // today the core's pick, the party leader's bind on the map (the copy router's call when R0 lands). It lands at
    // `spot` (x, y, z, o), or at the zone's entrance when `spot` is null, and the zone edge then holds the player in that
    // zone. The caller has passed the travel gate. Empty when the teleport ran, else the refusal's text.
    std::string TravelToOpenZone(Player* player, std::string const& zoneKey, float const* spot);
    // The world x and y of open zone `zoneKey`'s entrance, where TravelToOpenZone lands without a spot: the bounty map's
    // waypoint marker. False for a zone off the sheet or with its entrance rows blank.
    bool OpenZoneWaypoint(std::string const& zoneKey, float& x, float& y);

    // True when the rift promoted this spawn to a champion or rare pack (09 §2
    // step 2). The creature's own template rank cannot answer this: promotion
    // swaps the spawn for a generated clone entry, and 06 needs to know that the
    // kill is an elite one.
    bool IsPromotedElite(Creature const* creature);

    // Takes the empowered states off an elite: the pack's Shielding window if this monster holds it, the Reflects Damage window if it holds
    // that, the Juggernaut's immunity to control and knockback (for good), and the Illusionist's standing copies. How many of those it
    // removed (0 for a monster with none, or an ordinary one). A skill that purges asks this before its hit lands, so a shield does not
    // eat the hit.
    unsigned PurgeEmpowered(Creature* creature);

    // A monster of a rift's champion or rare pack, its leader or any member: D3 counts a rare's minions and every
    // champion as elites for Elite Damage and Elite Damage Reduction (Combat's IsElite). Loot keeps IsPromotedElite's answer.
    bool IsElitePack(Creature const* creature);

    // True for an Illusionist duplicate. They are ordinary-looking bodies with no
    // elite state, so 06's kill roll needs this marker to refuse them: copies give
    // no loot (13-elite-affixes §10). The rift kill hook already refuses them for
    // progress; this is the loot half.
    bool IsIllusion(Creature const* creature);

    // Bounties: a monster that fights as rift trash (the rift melee AI: the targeting policy, no
    // reset, no regeneration) for one party only. `owns` says whether a unit is that party's (a player, or a pet or
    // summon through its owner): only they see it (CanBeSeen), it picks only them, and only their damage lands. `died`
    // gets its killer. Return it from an AI factory, so the first create packet already answers CanBeSeen
    // (HubObjectClaim's reason, above).
    CreatureAI* NewOwnedMonsterAI(Creature* creature, std::function<bool(Unit const*)> owns, std::function<void(Unit*)> died);

    void RegisterScripts();
} // namespace DC::Rifts

#endif // DC_RIFTS_H
