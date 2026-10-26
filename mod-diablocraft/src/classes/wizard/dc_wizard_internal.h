// What the Wizard's mechanic files share: the state kept per player and the lock around it, the sheet and catalogue lookups, and the
// controls every skill puts on an enemy. The definitions are in dc_wizard_helpers.cpp.
#pragma once
#include "dc_wizard.h"
#include "dc_twister_math.h"
#include "../dc_classes.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_damage_buckets.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"
#include "../../stats/dc_stats.h"
#include "Creature.h"
#include "CreatureAI.h"
#include "ObjectGuid.h"
#include "Player.h"
#include "Position.h"
#include "ScriptMgr.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include <functional>
#include <map>
#include <mutex>
#include <optional>
#include <random>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace DC::Combat::Wizard::Shared
{

    using Row = Shells::Ability;

    extern thread_local std::optional<double> procOverride;

    struct ProcAs
    {
        std::optional<double> saved;
        explicit ProcAs(double proc)
            : saved(procOverride)
        {
            procOverride = proc;
        }
        ~ProcAs()
        {
            procOverride = saved;
        }
        ProcAs(ProcAs const&) = delete;
        ProcAs& operator=(ProcAs const&) = delete;
    };

    struct Timer
    {
        uint64 at = 0;
        std::function<void(Player*)> run;
    };

    struct Expiring
    {
        uint64 until = 0;
        double value = 0;
    };

    // What a Wizard's hits left on one enemy.
    struct Marks
    {
        uint64 frozen = 0, chilled = 0, boneChill = 0, conflagration = 0, glacialSpike = 0;
        // Snow Blast (cold), Intensify (arcane), Gale Force (fire).
        std::map<unsigned, Expiring> schoolTaken;
        // Elemental Exposure: one stack per element, each its own clock.
        std::map<unsigned, uint64> exposure;
    };

    // A travelling Energy Twister: its path, its carrier and what each tick deals, fixed at the cast.
    struct LiveTwister
    {
        unsigned serial = 0;
        uint32 id = 0;
        ObjectGuid carrier;
        std::vector<Twister::Point> path;
        double turnSeconds = 0, lifeSeconds = 0, speed = 0, radius = 0, tickPct = 0;
        float z = 0;
        // Raging Storm is on this twister: its rune, or an item that applies it to every Twister (ItemPowers::GrantsRune).
        // The merge of two that meet is not built; it reads this list.
        bool raging = false;
    };

    struct State
    {
        std::vector<Timer> timers;
        // The player's live twisters, oldest first. A twister no longer here deals no more ticks, so a merge
        // (Raging Storm) takes the pair out and starts its tornado.
        std::vector<LiveTwister> twisters;
        unsigned twisterSerial = 0;
        // Ranslor's Folly: when each lesser enemy was last pulled by one of the player's twisters (the creature's guid, the clock's ms), the per-target
        // cooldown of the pull. An entry older than the cooldown is dropped at the next pull.
        std::unordered_map<uint64, std::uint32_t> twisterPulled;
        std::unordered_map<uint64, Marks> marks;
        // Archon's kill stacks, Arcane Dynamo's Flashes of Insight.
        unsigned archonStacks = 0, flashes = 0;
        uint32 empowered = 0, empoweredNow = 0;
        ObjectGuid familiar;
        std::vector<ObjectGuid> images;
        // The Hydras up, the oldest first (Serpent's Sparker's extra Hydra, N-HYDRA: the core's totem slot keeps only the newest).
        std::vector<ObjectGuid> hydras;
        // The Mirror Image cast whose Images are up (Archmage's Vicalyke copies a killed one with its numbers).
        uint32 imageCast = 0;
        uint64 familiarReady = 0, guardianReady = 0, anomalyReady = 0;
        Position mist;
        std::vector<uint64> crystallize;
        std::vector<Expiring> spellsteal, absoluteZero;
        // Flame Blades: when each enemy hit's stack runs out.
        std::vector<uint64> flameBlades;
        // Arcane Attunement's and Spark's bonus for the next Arcane or
        // Lightning spell; Storm Chaser's Lightning Charges.
        double attunement = 0, spark = 0;
        // The enemies those two bonuses were counted on (the buff icons' stacks).
        unsigned attunementHits = 0, sparkHits = 0;
        unsigned stormCharges = 0;
        uint64 deepFreeze = 0, safePassage = 0, scramble = 0, illusionistSpeed = 0;
        std::vector<std::pair<uint64, double>> recentDamage;
        uint64 lastDamaged = 0;
        double still = 0;
        Position lastPosition;
        unsigned dominance = 0;
        uint64 chillingAura = 0, refreshAt = 0;
        // Flame Ward's channel start, Scorch's wall
        // (where the orb set off, which way, and when), Arcane Mines'
        // mines still to explode.
        uint64 flameWard = 0, wallStart = 0;
        Position wallOrigin;
        float wallDirection = 0;
        std::vector<uint64> mines;
        // Wormhole's grace window: when it closes, the recasts left in it,
        // and which window it is (a timer from an older one does nothing).
        uint64 wormholeUntil = 0;
        unsigned wormholeLeft = 0, wormholeWindow = 0;
        // Teleport - Reversal's window (GitHub #94): the rune cast, when
        // the window opened and closes (0 = none), which window it is,
        // where the Wizard stood before the first cast and on which map,
        // and whether the cast now running is the recast inside it.
        uint32 reversalSpell = 0, reversalMap = 0, reversalInstance = 0;
        uint64 reversalSince = 0, reversalUntil = 0;
        unsigned reversalWindow = 0;
        Position reversalFrom;
        // Where the Wizard stood before the Teleport now being cast.
        Position travelFrom;
        bool reversalRecast = false;
        // The sheet contributions this file put on, to take off again.
        std::vector<std::pair<Stat, uint64>> applied;
        std::string signature;
    };

    extern std::recursive_mutex mutex;
    // dc_ability_tuning, read at startup and on a config reload (dc_wizard_upkeep.cpp).
    extern std::map<std::string, double> tuning;
    extern std::unordered_map<uint64, State> states;
    // An enemy's reduced damage, whoever put it there: Debilitating Force and Spellsteal's debuff, keyed by the enemy.
    extern std::unordered_map<uint64, std::map<uint32, Expiring>> weakened;

    double Num(uint32 id, std::string_view token, std::string_view qualifier = {});
    // A placeholder tunable that has not been filled reads zero, and every caller treats zero as "not built yet".
    double Tune(char const* name);
    uint64 Now();
    std::mt19937_64& Engine();
    double Roll();
    double ProcOf(uint32 id);

    Row const* RowOf(uint32 id);
    bool IsSkill(uint32 id, std::string_view skill);
    bool IsRune(uint32 id, std::string_view rune);
    uint32 BaseOf(std::string_view skill);
    uint32 PassiveId(std::string_view name);
    bool Has(Player* player, char const* passive);
    uint32 BuffOf(Unit* unit, std::string_view skill);
    bool BuffRune(Unit* unit, std::string_view skill, std::string_view rune);
    uint32 ArchonAbilityId(std::string_view name);
    char const* ArchonAbilityName(uint32 id);
    bool Signature(uint32 id);
    std::string_view ElementOf(unsigned school);

    State& StateOf(Player* player);
    // Runs `run` on the Wizard's next update after `seconds`.
    void After(Player* player, double seconds, std::function<void(Player*)> run);
    Unit* Find(Player* player, ObjectGuid guid);

    // The controls: the helper record's aura on `target`, for `seconds` (a negative duration keeps the record's own).
    Aura* Apply(Player* player, Unit* target, char const* helper, double seconds, Unit* caster = nullptr);
    bool Freeze(Player* player, Unit* target, double seconds);
    void Stun(Player* player, Unit* target, double seconds);
    bool Slow(Player* player, Unit* target, double pct, double seconds);
    void Chill(Player* player, Unit* target, double seconds, double pct = -1);
    void Shield(Player* player, char const* helper, double lifePct, double seconds);
    bool FrozenMark(Player* player, Unit* target);
    bool Frozen(Player* player, Unit* target);
    bool Chilled(Player* player, Unit* target);
    void Weaken(Unit* enemy, uint32 source, double pct, double seconds);

    void Despawn(Player* player, ObjectGuid guid);
    void ClearSummons(Player* player);
    Player* OwnerOf(Creature* me);
    // Does this record carry the aura a handler is about to bind to? `aura` is SPELL_AURA_ANY for any aura, and `index` EFFECT_ALL for any slot.
    bool HasAuraEffect(uint32 spellId, uint16 aura, uint8 index = EFFECT_ALL);

    template<class AI>
    class Summon final : public CreatureScript
    {
    public:
        explicit Summon(char const* name)
            : CreatureScript(name)
        {
        }

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new AI(creature);
        }
    };

} // namespace DC::Combat::Wizard::Shared
