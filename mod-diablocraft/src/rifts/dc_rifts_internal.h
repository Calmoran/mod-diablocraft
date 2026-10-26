/*
 * World of DiabloCraft - shared rift state.
 *
 * The rifts folder was once one 5,194-line file. Splitting it into
 * four left a set of names that two or more of them need: the live run map, the
 * affix numbers, the elite bookkeeping and the small helpers. They live here.
 *
 * INTERNAL to mod-diablocraft/src/rifts/. Other modules include dc_rifts.h and
 * see only what that exports; nothing in this header is part of that contract.
 *
 * The split was a pure move: every name below kept its spelling and signature.
 * What changed is linkage - these used to sit in an anonymous namespace inside
 * one translation unit and now have external linkage inside DC::Rifts - and
 * nothing else.
 */

#ifndef DC_RIFTS_INTERNAL_H
#define DC_RIFTS_INTERNAL_H

#include "dc_rifts.h"
#include "dc_rift_floors.h"
#include "dc_gr_progress.h"
#include "../loot/dc_loot.h"

#include "../common/dc_tunables.h"

#include "DataMap.h"
#include "ObjectGuid.h"
#include "Position.h"

#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <random>
#include <set>
#include <string>
#include <utility>
#include <unordered_map>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (31): initial announced value; One above #92's 30 seconds, so the first announcement is not swallowed.
// Constant (17301, 8000000, 9000000, 910003, 910011, 910015): harness template, champion/rare clone bases, Keeper, obelisk, credit creature; Identifiers.

class Creature;
class GameObject;
class Map;
class Player;
class Unit;
class WorldLocation;

namespace DC::Rifts
{
    // --- the dungeon pool and the live runs ------------------------------------

    struct Dungeon
    {
        std::uint32_t dungeonId = 0, mapId = 0;
        std::string name;
        float x = 0, y = 0, z = 0, o = 0;
    };

    extern std::mutex dataMutex;
    extern std::vector<Dungeon> pool;
    extern bool dataReady;

    // The live runs and their floors (rift floors Part F1): runs by id, floors by instance. Guarded by riftMutex.
    extern std::mutex riftMutex;
    extern LiveRuns<Rift> live;

    // --- guardians (dc_rift_ai.cpp) --------------------------------------------

    struct Ability
    {
        std::string name, behaviour;   // nova | leap | frenzy
        std::uint32_t shell = 0;
    };

    struct Guardian
    {
        std::string name;
        std::uint32_t creatureId = 0;
        Ability abilities[2];
    };

    extern std::vector<Guardian> guardians;

    // One dc_rift_affix row. behaviour is empty for the three that are name-only;
// those still roll onto packs and still show in `.dc rift affixes`, so the pool
// a player faces is the real D3 one.
//
// The last four columns are 13-elite-affixes §4 as data: which of maxroll's
// three pools the affix belongs to, whether it is one of the eleven a level 60+
// pack may take at most three of, whether it may roll at all, and whether a
// Rare's minions inherit it (elite_affix_eligibility.csv's own `minion` column,
// which is the authority - ten of the 28 pass down and eighteen are leader-only).
struct Affix
{
    std::string name, appearsOn, element, behaviour, pool;
    unsigned minTier = 1, minLevel = 1;
    std::uint32_t shell = 0;
    bool levelLimited = false, rollable = true, minionInherits = false;
};

// What a promoted spawn carries. Kept on the creature itself rather than in a
// GUID-keyed map, so it dies with the creature and costs one hash miss to rule
// out on the units that are not elites.
struct EliteState : public DataMap::Base
{
    bool rare = false;
    // A pack member rather than the pack leader. Members carry the pack's
    // per-member affixes and run them themselves (09 §2 step 2); the six affixes
    // whose own effect text is about the pack rather than the monster stay on
    // the leader (PackLevelAffix). A member is not an elite kill: 06 asks
    // IsPromotedElite, and the answer for a member is what it always was.
    bool member = false;
    unsigned tier = 1;
    // The Greater Rift level the elite spawned in, 0 outside one: its affix damage follows the
    // level's factor, not the tier's.
    unsigned grLevel = 0;
    std::vector<Affix> affixes;
    std::uint32_t nextTick = 0, nextCluster = 0;
    // Stage 2. pack holds the companions and minions summoned with this leader;
    // the leader itself is not in it.
    std::vector<ObjectGuid> pack;
    std::uint32_t nextCast = 0, nextVolley = 0, nextShield = 0, shieldUntil = 0;
    // Shielding passes to a Rare's minions (elite_affix_eligibility.csv), and
    // maxroll says only one monster in a pack shields at a time, so the window
    // and the monster holding it live on the LEADER's state and every member
    // claims it there. On a lone monster the leader is itself.
    ObjectGuid shieldHolder;
    bool shieldApplied = false;
    // Per-affix cast cadence, keyed by behaviour. D3 publishes no interval for
    // any affix but Mortar, so most of these are tunables in
    // dc_affix_tunables; a behaviour with no row of its own uses _global.
    std::unordered_map<std::string, std::uint32_t> nextCastFor;
    std::uint32_t reflectFrom = 0, reflectUntil = 0;
    ObjectGuid reflectHolder;
    unsigned avengerStacks = 0;
    double avengerDamageFactor = 1.0;
    bool illusionsSpawned = false;
    // A skill purged the Juggernaut's immunity to control and knockback: it stays off, whatever re-applies the passives.
    bool juggernautPurged = false;
    // The pack's head count and its orbs-dropped mark, one object shared by the leader and every
    // member. A lone monster holds its own.
    std::shared_ptr<Gr::PackLife> life = std::make_shared<Gr::PackLife>();
    std::vector<ObjectGuid> illusions;
    bool trailPositionKnown = false;
    float trailX = 0, trailY = 0;
};

// Work that has to happen on a map's own update rather than in the hook that
// decided on it: swapping a spawn for its clone while that spawn is being added
// to the world would recurse, and a delayed blast has to wait by definition.
struct Burst
{
    unsigned tier = 0, grLevel = 0;
    std::string affixName;
    std::uint32_t instanceId = 0, mapId = 0, shell = 0, at = 0;
    ObjectGuid caster;
    float x = 0, y = 0, z = 0, radius = 0;
    double damage = 0;
};

// Ground that keeps hurting rather than hurting once: Desecrator's void, Arcane
// Enchanted's beam sweep, Frozen Pulse, Orbiter and Poison Enchanted. A Burst is
// the single-shot version of the same thing.
struct Zone
{
    std::uint32_t instanceId = 0, mapId = 0, shell = 0;
    ObjectGuid caster;
    float x = 0, y = 0, z = 0, radius = 0, slow = 0;
    // The affix's OWN slow record (one per affix,
    // named after it). 0 with a nonzero `slow` cannot happen - the affix
    // that sets one sets both - and casts nothing if it ever does.
    std::uint32_t slowSpell = 0;
    double damage = 0;
    std::uint32_t nextTick = 0, endsAt = 0, tickMs = 0;
};

// Crowd control that has to come off again: Jailer's root, Nightmarish's fear,
// Knockback's and Frozen Pulse's slow. `debuff` is a client-drawn aura shown
// for the length of the hold and stripped with it (the Jailer debuff); 0 means
// the hold has no visible aura of its own.

// `.dc elite`: one deliberate pack per GM, spawned in the open world so an
// affix can be watched on a pack that carries nothing else. Keyed by the
// owner's guid; members are held here as well as on the leader so the pack can
// still be cleared after the leader has died. The count is atomic because every
// map asks on every update whether it has one.
struct HarnessPack
{
    ObjectGuid leader;
    std::vector<ObjectGuid> members;
    std::uint32_t mapId = 0, instanceId = 0;
    bool rare = false;
    Position spot;
};

// 13-elite-affixes §2. Every affix number lives in dc_affix_tunables and none is
// a constant here, so one can fight a pack with `.dc elite`, change a value
// with `.dc affix set`, and fight it again without a restart. The table holds
// D3's published figure and the tuned one separately and the server reads the tuned one when it
// is set, so regenerating the data can never destroy tuning.
//
// The named fields are the values read on the hot paths; `value` is the whole
// table, which is what the per-affix cadences and `.dc affix` read. One snapshot
// is built per reload and handed out by shared_ptr, so a pack mid-fight either
// sees all of the old numbers or all of the new ones.
struct AffixNumbers
{
    std::unordered_map<std::string, double> value;   // "<affix>|<parameter>"
    std::unordered_map<std::string, std::vector<std::string>> unconfigured;
    bool Enabled(std::string const& affix) const { return !unconfigured.count(affix); }
    double Parameter(std::string const& key) const { return value.at(key); }

    double Get(std::string const& key, double fallback) const
    {
        auto found = value.find(key);
        return found == value.end() ? fallback : found->second;
    }

    // _global
    std::uint32_t castMs = 0, tickMs = 0;
    double procPct = 0;
    std::unordered_map<unsigned, double> tierDamage;
    float minionSpread = 0, knockbackSpeedZ = 0;
    unsigned rareMinionsMin = 0, rareMinionsMax = 0;
    // §4.2's composition rule and §4.3's level gate, as numbers rather than code.
    unsigned offensiveMin = 0, offensiveMax = 0, defensiveMax = 0, crowdControlMax = 0;
    unsigned levelLimitFrom = 0, levelLimitMax = 0;

    std::uint32_t beamArmMs = 0, beamMs = 0;
    float beamLength = 0;
    double avengerDamage = 0;
    std::uint32_t desecratorArmMs = 0;
    float desecratorRadius = 0;
    float fastMove = 1.0f;
    double fastAttack = 1.0;
    float chainsWidth = 0;
    unsigned chainsMembers = 0;
    std::uint32_t frozenArmMs = 0;
    float frozenRadius = 0;
    std::uint32_t pulseArmMs = 0, pulseMs = 0;
    float pulseRadius = 0, pulseSlow = 1.0f;
    std::uint32_t pulseSlowSpell = 0;
    double healthLinkFloor = 0;
    unsigned hordeMultiplier = 1;
    unsigned illusionMin = 0, illusionMax = 0;
    double illusionLife = 0, illusionTrigger = 0;
    float jailerReach = 0;
    std::uint32_t jailerRootMs = 0;
    float juggernautMove = 1.0f;
    double juggernautTaken = 1.0, juggernautLife = 1.0;
    float knockbackSpeedXY = 0, knockbackSlow = 1.0f;
    std::uint32_t knockbackSlowSpell = 0;
    std::uint32_t knockbackMs = 0;
    float moltenTrailRadius = 0, moltenBlastRadius = 0;
    std::uint32_t moltenFuseMs = 0;
    unsigned mortarShells = 0;
    std::uint32_t mortarVolleyMs = 0, mortarArmMs = 0;
    float mortarDeadZone = 0, mortarSplash = 0;
    std::uint32_t nightmarishMs = 0;
    float orbiterRadius = 0;
    std::uint32_t orbiterMs = 0;
    float plaguedRadius = 0;
    unsigned poisonPools = 0;
    std::uint32_t poisonArmMs = 0, poisonMs = 0;
    float poisonWidth = 0;
    std::uint32_t reflectArmMs = 0, reflectMs = 0;
    std::uint32_t shieldingMs = 0, shieldingGapMs = 0;
    float teleporterRange = 0;
    unsigned thunderstormStrikes = 0;
    float thunderstormRadius = 0;
    float vortexRange = 0;
};
extern double championScale, rareScale, minionScale;
// The body `.dc elite` spawns its deliberate test packs on
// Shattered Hand Executioner, a plain melee
// humanoid from The Shattered Halls: that dungeon is in the stage 1 pool, so
// generate_rift_elites.py has already made its champion (8017301) and rare
// (9017301) clones at rank 1 and 2 and the harness needs no world data of its
// own. It is a harmless body because everything it does in a fight comes from
// the affix under test and nothing from the creature - level 70 like the hero
// it is spawned for, no script, no AI name, unit_class 1 with no spells, and
// MovementType 0 so it stands where it is put.
inline constexpr std::uint32_t HARNESS_ENTRY = 17301;
// Illusionist's duplicates carry no EliteState on purpose - that would make them
// pack members to every other affix check and change their loot source - so this
// marker is the only thing that tells the kill path they are not real. Copies
// give no rift progress and no loot (13-elite-affixes §10).
struct IllusionState : public DataMap::Base {};

// Respawn given to a native spawn that is removed for the rest of the run (promoted away, or cleared when
// a Greater Rift's Guardian spawns): longer than any instance lives. Constant (7 days).
inline constexpr std::uint32_t GONE_FOR_THE_RUN = 7 * DAY;

// --- elite promotion (dc_rift_elites.cpp) ----------------------------------

// The generated clone entry ranges a promoted champion or rare is swapped to.
inline constexpr std::uint32_t CHAMPION_BASE = 8000000, RARE_BASE = 9000000;

// A spawn the creature script decided to promote, handed to the map's own
// update so the swap happens on the map thread that owns the creature.
struct Promotion
{
    std::uint32_t instanceId = 0, mapId = 0;
    ObjectGuid guid;
    bool rare = false;
};

extern double elitePromotionPct;

// Loaded by RiftWorld in dc_rifts.cpp, defined and used in dc_rift_elites.cpp.
extern std::vector<Affix> affixPool;
extern std::vector<std::pair<unsigned, unsigned>> affixCounts;
extern unsigned championPackSize;

// The per-affix work queues. The elite tick fills them; the map update in
// dc_rifts.cpp drains them on the thread that owns the creatures.
extern std::vector<Burst> bursts;
extern std::vector<Zone> zones;

// `.dc elite` harness packs; RiftMap and RiftCommand both reach for these.
extern std::mutex harnessMutex;
extern std::unordered_map<std::uint64_t, HarnessPack> harnessPacks;
extern std::atomic<unsigned> harnessCount;
extern std::mutex workMutex;
extern std::vector<Promotion> promotions;

// --- elite affixes (dc_rift_elites.cpp) ------------------------------------

    struct Affix;
    struct AffixNumbers;
    struct EliteState;

    extern std::shared_ptr<AffixNumbers const> affixNumbers;
    std::shared_ptr<AffixNumbers const> Numbers();
    std::uint32_t Ms(double seconds);

    bool HasAffix(EliteState const& state, std::string const& behaviour);
    std::uint32_t AffixShell(EliteState const& state, std::string const& behaviour);

    // The elite's own average swing, already scaled for tier and party size, which
    // every affix and guardian number is a multiple of.
    double SwingDamage(Unit const* unit);

    void QueueBurst(Unit* source, Rift const& rift, float x, float y, float z, float radius, std::uint32_t shell,
                    double damage, std::uint32_t delayMs);
    void BlastPlayers(Unit* source, Map* map, float x, float y, float z, float radius, std::uint32_t shell,
                      double damage);

    // A dungeon held for a player who is being SHOWN the quest at the obelisk, from
// the moment the menu is built to the moment the accept callback lands. 7.2:
// reserve before adding the quest, and never reroll afterwards. It is not a run
// and nothing persists it; a player who walks away simply loses it.
struct Reservation
{
    Dungeon dungeon;
    std::uint32_t questId = 0;
    uint32 made = 0;
};
// Long enough that a slow client still lands inside it, short enough that an
// abandoned menu does not pin a dungeon choice for the session. Ours, not a
// gameplay number: rerolling on expiry is invisible to the player.
// tunables:rifts.
inline uint32 ReservationMs()
{
    return static_cast<uint32>(DC::Tunables::Get("rifts", "instance_reservation_ms"));
}
// `announced` starts above every possible mark rather than at 31, because the
// marks are tunable now (rifts/close_announce_first_seconds): 31 silently
// swallowed a first mark set higher than 30. With 30/10 it behaves as before.
struct PendingClose { Rift rift; uint32 started; uint32 announced = 0xFFFFFFFFu; };
// tunables:rifts (09-rifts §2 step 6).
inline uint32 RiftCloseMs()
{
    return static_cast<uint32>(DC::Tunables::Get("rifts", "close_countdown_ms"));
}
// Constant: a creature entry, not a game number.
inline constexpr std::uint32_t RIFT_KEEPER_ENTRY = 910003;
// Constant: an item entry, not a game number (09 F7, loot_0002_keystone_item.sql; the account
// material row of account_economy.csv).
inline constexpr std::uint32_t KEYSTONE_ITEM = 102005;
// Constant: generate_spells.py's RIFT_SHELLS.
inline constexpr std::uint32_t TOWN_PORTAL_SHELL = 81167;
// Defined in dc_rifts.cpp; the quest half reaches all three.
extern std::unordered_map<std::uint64_t, PendingClose> pendingCloses; // by run id
extern std::unordered_map<ObjectGuid, Reservation> reservations;
// Loaded by RiftWorld in dc_rifts.cpp, owned by the quest half: the one quest of each mode (monster spawning
// S3, 3.9.4) with the bar it counts, 65,000 hundredths of a D3 progress point, and every rift template
// including the Greater one, which cleanup has to recognise.
struct BarQuest
{
    std::uint32_t id = 0;
    unsigned units = 0; // the quest's RequiredNpcOrGoCount1: the whole bar, in hundredths of a point
};
extern BarQuest nephalemQuest;
// The Greater Rift's, the timed row of the same template table.
extern BarQuest greaterQuest;
extern std::set<std::uint32_t> riftQuests;
void QueueClose(Rift rift);
// A Greater Rift's start: the level and the roster the ready check closed. Every member's
// quest is added and every member is moved in, at once, with the opener's Keystone already paid.
struct GreaterStart
{
    unsigned level = 0;
    std::vector<Player*> roster;
};
bool OpenRun(Player* player, Reservation const* reserved, Rift* created, std::string& error,
             GreaterStart const* greater = nullptr);
void RescaleForHeadcount(std::uint64_t runId);
// Rift floors Part F2 (dc_rifts.cpp). OpenNextFloor makes the run's next floor for one member and binds them to it; the
// caller teleports. BindToFloor binds a member to a floor that stands (false: its instance is gone). ArrivalOf is a pool row
// by dungeon id. IsExitPortal: an exit portal template (a look's entry plus Exit::EXIT_ENTRY_OFFSET).
bool OpenNextFloor(Player* player, Rift const& from, Dungeon const& dungeon, Floor& made, std::string& error);
bool BindToFloor(Player* player, Floor const& floor);
bool ArrivalOf(std::uint32_t dungeonId, Dungeon& out);
bool IsExitPortal(std::uint32_t entry);
// dc_rift_exit.cpp: the exit portal of a floor, the commands that place it, and the click on it.
namespace Exit
{
    void PlaceExit(Map* map);
    void Use(Player* player, GameObject* go);
    // One line for `.dc rift status`: whether the floor's exit portal stands, and where it leads.
    std::string Describe(std::uint32_t instanceId, std::uint32_t mapId);
    // A floor's map is gone: its exit record goes with it.
    void Forget(std::uint32_t instanceId);
    // The pool row a GM standing in a rift floor (or in a listed dungeon) means.
    bool DungeonOf(Player* player, Dungeon& out);
    void RegisterScripts();
} // namespace Exit
// dc_rift_pylon.cpp: pylons and shrines Part P4, where and when they stand, and `.dc pylon spot`.
namespace Pylons
{
    // A live rift floor's map update: the first places a Nephalem floor's objects (or readies a Greater Rift floor's
    // spots); later ones look for a player near a Greater Rift spot every pylon_gr_check_ms.
    void Update(Map* map, uint32 diff);
    // A floor's map is gone; `runEnds` when it was the run's last: what the run has had goes with it.
    void FloorGone(std::uint64_t runId, bool runEnds);
    void RegisterScripts();
} // namespace Pylons
// The six Greater Rift rules and the XP split (dc_gr_rules.cpp).
void RegisterGreaterRiftRuleScripts();
// Greater Rift timer and progress (dc_gr_progress.cpp; decisions in dc_gr_progress.h).
// Progress one kill adds to the run, in hundredths of a D3 progress point: the monster's own points, in both modes.
unsigned KillUnits(Creature* killed, Rift const& rift);
// Reads dc_monster_progress (spawn_sheets_0002); false with `error` set when the table is missing.
bool LoadMonsterProgress(std::string& error);
// A promoted pack member has died: counts the pack's head and, when its orbs fall, drops them (both modes).
void DropGreaterOrbs(Creature* dead);
// dc_gr_rewards.cpp: what this run's Guardian pays one member on top of the Nephalem reward,
// by the run's level; and the XP multiple of a level, level 1 being 1.
DC::Loot::GreaterReward GuardianReward(Player* member, Rift const& rift);
// The Blood Shards one member earns at the Guardian's kill: by tier in a Nephalem Rift, by level in a Greater one.
std::uint64_t GuardianShards(Rift const& rift);
double GuardianXpFactor(unsigned level);
// A rift map's own update: a Greater Rift's clock running out, and a run member walking into an orb (both modes).
void GreaterTick(Map* map);
// The Guardian died: writes the run's beaten or failed result and the time left, once, and says so.
void RecordGuardianResult(Rift& rift);
// An in-time Guardian kill: every enrolled member's Greater Rift numbers rise (dc_gr_progress.cpp).
void GrantGreaterUnlocks(Rift const& rift);
// A map is gone: its orbs go with it.
void ForgetGreaterOrbs(std::uint32_t instanceId);
// Part 11 (dc_gr_urshi.cpp; decisions in dc_gr_urshi.h; contract docs/contracts/urshi-messages.md). An in-time kill: Urshi
// stands where the Guardian died and each enrolled online member gets their tries. Idempotent per run.
void BeginUrshi(Creature* guardian, Rift const& rift);
// The refusal naming every member who still has tries, empty when none does: every way of closing the run asks it.
std::string UrshiBlocksClose(std::uint64_t runId);
// A member left the party, was kicked or logged out: their tries are gone. `notify` (may be null) is told.
void UrshiMemberLeft(std::uint64_t runId, ObjectGuid member, Player* notify);
// The rift map's own update: she leaves when nobody holds a try.
void UrshiTick(Map* map);
// A map is gone: its Urshi state goes with it.
void EndUrshi(std::uint32_t instanceId);
void RegisterUrshiScripts();
// How many times this character died in this Greater Rift run, on any floor (dc_gr_rules.cpp), 0 when it never did.
unsigned GreaterRiftDeaths(std::uint64_t runId, std::uint32_t character);

// --- small shared helpers --------------------------------------------------

    std::mt19937_64& Engine();
    double Roll();
    bool PlayableClass(Player const* player);
    // Party size: dc_party_scaling's open_world rows (dc_rifts.cpp).
    unsigned PartyCap();
    void ForcedTeleport(Player* player, std::function<void(Player*)> const& move);
    // To every player standing on any floor of the run.
    void Announce(Rift const& rift, std::string const& text);
    void Persist(Rift const& rift);
    void PersistNow(Rift const& rift);
    std::string Escape(std::string value);

    // --- quests (dc_rift_quests.cpp) -------------------------------------------

    // Guardian death completes every still-enrolled member's quest (09-rifts 7.4).
    void CompleteRunQuests(std::uint64_t runId);
} // namespace DC::Rifts

#endif // DC_RIFTS_INTERNAL_H
