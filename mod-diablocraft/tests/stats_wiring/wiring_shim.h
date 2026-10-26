/*
 * Doubles for the production wiring of Issues #54 and #55.
 *
 * What is REAL here, compiled from the module's own files and not copied:
 * `PublishMovement` (dc_stats.cpp), `ApplySlow`
 * (dc_rift_elites.cpp), `SheetAward` and the levelling hook body
 * (dc_paragon.cpp), the two arithmetic headers, the generated shell ids, and
 * `dc_common.cpp` itself, so the stat sheet these tests hand around is the
 * server's own sheet with its own caps.
 *
 * What is a double, and therefore proves nothing about the core: the player and
 * its aura list, the cast, and `Stats::Get`. The aura model is deliberately
 * thin - it records which spell id is applied, with what amount and what
 * duration, and nothing else. It does NOT model Unit::UpdateSpeed, so no test
 * here says what speed the player ends up running at; what they say is which
 * aura the module asks for, with what amount, and when it takes it away again.
 * The live check for the speed itself is docs/test-stats-wiring.md.
 */

#ifndef DC_STATS_WIRING_SHIM_H
#define DC_STATS_WIRING_SHIM_H

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include "../../../../azerothcore-wotlk/src/common/Utilities/DataMap.h"

using int32 = std::int32_t;
using uint32 = std::uint32_t;
using uint8 = std::uint8_t;

enum AuraEffectIndex { EFFECT_0 = 0 };

// SpellInfo's target table at the pin: 1 is the caster and 6 is the explicit
// enemy target. Which one a record carries is what decides where its aura
// lands, whoever the cast was handed. Filled in from the generated SQL by
// scripts/tests/stats/test_stats_wiring.py - see dc_spell_records_extract.h.
constexpr int TARGET_UNIT_CASTER = 1;
constexpr int TARGET_UNIT_TARGET_ENEMY = 6;
int RecordTargetOf(uint32 spell);

// The same two records' attribute words, also filled in from the generated SQL.
// They decide whether two casters' copies of one spell coexist, which is the
// difference between one elite ending another's slow and each keeping its own.
uint32 RecordAttributesOf(uint32 spell);
uint32 RecordAttributesEx3Of(uint32 spell);
// And each record's aura type, so the speed model below reads "every slow on
// this player" out of the records rather than out of a list kept here. There
// is one slow record per affix now, so a hard-coded id would be wrong.
constexpr int SPELL_AURA_MOD_INCREASE_SPEED = 31;
constexpr int SPELL_AURA_MOD_DECREASE_SPEED = 33;
int RecordAuraOf(uint32 spell);

constexpr uint32 SPELL_ATTR0_PASSIVE = 0x40;
constexpr uint32 SPELL_ATTR3_DOT_STACKING_RULE = 0x80;

// `Aura::CanStackWith` at the pin, cut down to the one question these records
// ever ask it: may an arriving aura sit beside the same spell from a DIFFERENT
// caster? Two clauses answer yes for them and they are both here.
//
//   * `IsMultiSlotAura() && !IsArea()` - and `IsMultiSlotAura()` is
//     `IsPassive() || Id == 40075`, so a passive record stacks across casters
//     without asking for anything.
//   * `HasAttribute(SPELL_ATTR3_DOT_STACKING_RULE)`, inside the `!sameCaster`
//     branch: "Stack separately for each caster".
//
// With neither, the function reaches "same spell with same caster should not
// stack" and returns false - and `Unit::_ApplyAura` removes every owned aura
// the arriving one cannot stack with, which is the other elite's slow. That is
// the removal this model performs below, and it is why the visible slow has to
// carry the attribute.
inline bool RecordStacksAcrossCasters(uint32 spell)
{
    return (RecordAttributesOf(spell) & SPELL_ATTR0_PASSIVE)
        || (RecordAttributesEx3Of(spell) & SPELL_ATTR3_DOT_STACKING_RULE);
}

// (SetControlled records the state it was asked for.)
using UnitState = unsigned;

// --- the aura list ---------------------------------------------------------
//
// Keyed by (spell, caster), because that is how the core keys one
// (Unit::_TryStackingOrRefreshingExistingAura looks an existing aura up by
// casterGUID, Unit.cpp:4656) and it is the whole point of the slow fix. An
// empty caster matches any, as it does in Unit::GetAura.

class AuraEffect
{
public:
    int32 amount = 0;
    int32 GetAmount() const { return amount; }
};

struct ObjectGuid
{
    std::uint64_t raw = 0;
    std::uint64_t GetRawValue() const { return raw; }
    std::uint32_t GetCounter() const { return std::uint32_t(raw); }
    bool operator==(ObjectGuid const& other) const { return raw == other.raw; }
    bool operator!=(ObjectGuid const& other) const { return raw != other.raw; }
    explicit operator bool() const { return raw != 0; }
};
using Guid = ObjectGuid;

class Aura
{
public:
    uint32 id = 0;
    ObjectGuid caster;
    AuraEffect effect;
    int32 duration = -1, maxDuration = -1;

    AuraEffect const* GetEffect(unsigned index) const { return index == EFFECT_0 ? &effect : nullptr; }
    int32 GetDuration() const { return duration; }
    void SetDuration(int32 value) { duration = value; }
    void SetMaxDuration(int32 value) { maxDuration = value; }
};

// Every call the extracted production code makes, and a record of it, so a test
// can say "one cast, that id, that amount" rather than inspecting state alone.
struct Call
{
    std::string what;
    uint32 spell = 0;
    int32 amount = 0;
};

class Player;
class Creature;
class Group;
constexpr uint32 PLAYER_FLAGS_NO_XP_GAIN = 1;
constexpr uint32 PLAYER_FLAGS_NO_PLAY_TIME = 2;
constexpr uint32 CONFIG_MAX_PLAYER_LEVEL = 0;
constexpr uint32 CONFIG_TRIAL_LEVEL_CAP = 1;
struct TestSession
{
    bool trial = false;
    bool IsTrialAccount() const { return trial; }
};
struct TestWorld
{
    uint32 cap = 80, trialCap = 20;
    uint32 getIntConfig(uint32 key) const { return key == CONFIG_MAX_PLAYER_LEVEL ? cap : trialCap; }
};
inline TestWorld world;
inline TestWorld* sWorld = &world;
struct TestScripts
{
    void OnPlayerBeforeGetLevelForXPGain(Player*, uint8&) { }
};
inline TestScripts scripts;
inline TestScripts* sScriptMgr = &scripts;
struct ChatHandler
{
    explicit ChatHandler(TestSession*) { }
    void SendSysMessage(char const*) { }
};
#define LOG_ERROR(...) ((void)0)

class Unit
{
public:
    ObjectGuid guid;
    DataMap CustomData;
    Creature* creature = nullptr;
    Creature* ToCreature() { return creature; }
    std::vector<Aura> auras;
    std::vector<Call> calls;

    ObjectGuid GetGUID() const { return guid; }
    char const* GetName() const { return "Caster"; }
    void CastCustomSpell(Player* target, uint32 spell, int32* basePoints, void*, void*, bool);

    Aura* GetAura(uint32 spell, ObjectGuid from = {})
    {
        for (Aura& aura : auras)
            if (aura.id == spell && (!from || aura.caster == from))
                return &aura;
        return nullptr;
    }

    void RemoveAurasDueToSpell(uint32 spell, ObjectGuid from = {})
    {
        auto before = auras.size();
        for (auto it = auras.begin(); it != auras.end();)
            it = (it->id == spell && (!from || it->caster == from)) ? auras.erase(it) : it + 1;
        if (auras.size() != before)
            calls.push_back({"remove", spell, 0});
    }

    // --- test helpers, never called by production code ---------------------

    // A model of Unit::UpdateSpeed's two reads, and NOT of the speed itself:
    // the core applies the largest positive MOD_INCREASE_SPEED and the largest
    // negative MOD_DECREASE_SPEED among the auras still running.
    int32 StrongestSlow()
    {
        int32 worst = 0;
        for (Aura const& aura : auras)
            if (RecordAuraOf(aura.id) == SPELL_AURA_MOD_DECREASE_SPEED && aura.effect.amount < worst)
                worst = aura.effect.amount;
        return worst;
    }

    // Every slow still running, whichever affix cast it.
    unsigned Slows() const
    {
        unsigned n = 0;
        for (Aura const& aura : auras)
            if (RecordAuraOf(aura.id) == SPELL_AURA_MOD_DECREASE_SPEED)
                ++n;
        return n;
    }

    // A model of the core's aura clock: durations count down and an aura that
    // reaches zero is removed. Permanent auras carry -1 and are left alone.
    void Elapse(int32 ms)
    {
        for (auto it = auras.begin(); it != auras.end();)
        {
            if (it->duration < 0) { ++it; continue; }
            it->duration -= ms;
            it = it->duration <= 0 ? auras.erase(it) : it + 1;
        }
    }

    int32 AuraAmount(uint32 spell, ObjectGuid from = {})
    {
        Aura* aura = GetAura(spell, from);
        return aura ? aura->effect.GetAmount() : 0;
    }
    bool Has(uint32 spell, ObjectGuid from = {}) { return GetAura(spell, from) != nullptr; }
    unsigned Count(uint32 spell) const
    {
        unsigned n = 0;
        for (Aura const& aura : auras)
            if (aura.id == spell)
                ++n;
        return n;
    }
    unsigned Casts(uint32 spell) const
    {
        unsigned n = 0;
        for (auto const& call : calls)
            if (call.what == "cast" && call.spell == spell)
                ++n;
        return n;
    }
};

class Player : public Unit
{
public:
    uint8 level = 70;
    bool alive = true, sameMap = true, samePhase = true, inRange = true, playable = true;
    uint32 flags = 0;
    TestSession session;
    TestSession* GetSession() { return &session; }
    bool HasPlayerFlag(uint32 flag) const { return flags & flag; }
    bool IsAlive() const { return alive; }
    bool IsInMap(Unit*) const { return sameMap; }
    bool InSamePhase(Unit*) const { return samePhase; }
    bool IsAtGroupRewardDistance(Unit*) const { return sameMap && inRange; }
    std::vector<unsigned> controlsCleared;

    uint8 GetLevel() const { return level; }
    void SetControlled(bool, unsigned state) { controlsCleared.push_back(state); }
};

struct GroupReference
{
    Player* player = nullptr;
    GroupReference* following = nullptr;
    Player* GetSource() { return player; }
    GroupReference* next() { return following; }
};
class Group
{
public:
    std::vector<GroupReference> refs;
    explicit Group(std::vector<Player*> const& players)
    {
        refs.resize(players.size());
        for (std::size_t i = 0; i < refs.size(); ++i)
        {
            refs[i].player = players[i];
            if (i + 1 < refs.size()) refs[i].following = &refs[i + 1];
        }
    }
    GroupReference* GetFirstMember() { return refs.empty() ? nullptr : &refs.front(); }
};
class Creature : public Unit
{
public:
    Group* group = nullptr;
    Player* recipient = nullptr;
    uint8 level = 70;
    bool pet = false, totem = false, critter = false, disabled = false, damageEnough = true;
    Creature() { creature = this; }
    bool IsPet() const { return pet; }
    bool IsTotem() const { return totem; }
    bool IsCritter() const { return critter; }
    bool IsLootRewardDisabled() const { return disabled; }
    bool IsDamageEnoughForLootingAndReward() const { return damageEnough; }
    bool hasLootRecipient() const { return recipient || group; }
    Group* GetLootRecipientGroup() { return group; }
    Player* GetLootRecipient() { return recipient; }
    uint8 GetLevel() const { return level; }
};
class KillRewarder
{
public:
    Player* killer;
    Unit* victim;
    Player* GetKiller() { return killer; }
    Unit* GetVictim() { return victim; }
};
namespace Acore::XP
{
uint8 GetGrayLevel(uint8 level);

}

inline void Unit::CastCustomSpell(Player* target, uint32 spell, int32* basePoints, void*, void*, bool)
{
    // Where the aura lands is the RECORD's decision, not the call's. The core
    // resolves the record's implicit target before it applies anything, so a
    // record that says TARGET_UNIT_CASTER puts the aura on whoever cast it
    // however the cast was addressed. That is exactly the mismatch this models,
    // and it is why the slow's record has to name an explicit target.
    Unit* lands = RecordTargetOf(spell) == TARGET_UNIT_CASTER ? this : static_cast<Unit*>(target);
    if (!lands)
        return;
    // Unit::_ApplyAura: whatever the arriving aura cannot stack with goes.
    // The module removes its own caster's copy before every cast, so the only
    // thing this can reach is another caster's - and only when the record does
    // not say the two may coexist.
    if (!RecordStacksAcrossCasters(spell))
        lands->RemoveAurasDueToSpell(spell);
    Aura aura;
    aura.id = spell;
    aura.caster = guid;
    aura.effect.amount = basePoints ? *basePoints : 0;
    lands->auras.push_back(aura);
    lands->calls.push_back({"cast", spell, aura.effect.amount});
}

#endif // DC_STATS_WIRING_SHIM_H
