/*
 * The scaffolding the core's own chain-target path needs to compile outside
 * the server (spell rewrite step 6, Ricochet).
 *
 * The 2026-09-20 ruling "Spell rewrite step 6 Ricochet and frozen-test
 * contract" says D3's `target_count = 3` for Weapon Throw - Ricochet means
 * THREE ADDITIONAL enemies, and that the generated record therefore carries
 * `EffectChainTargets_1 = 4`, "because the core's ChainTarget includes the
 * primary". That last clause is a claim about the core's own arithmetic, and a
 * claim about the core is only worth what the core's code says. So nothing on
 * that path is modelled here. `scripts/tests/combat/test_chain_targets.py` takes the
 * following out of the core at pin 9d9b604 and writes them beside this header
 * for it to include, verbatim except where a line says otherwise:
 *
 *   chain_enums.inc            SharedDefines.h: SpellEffIndex, SpellAttr2,
 *                              SpellAttr4, SpellDmgClass, the Targets enum
 *                              (for TARGET_UNIT_TARGET_CHAINHEAL_ALLY);
 *                              SpellInfo.h: SpellTargetSelectionCategories,
 *                              SpellTargetReferenceTypes,
 *                              SpellTargetObjectTypes, SpellTargetCheckTypes;
 *                              DBCStructure.h: MAX_SPELL_EFFECTS;
 *                              Spell.h: WorldObjectSpellAreaTargetSearchReason;
 *                              ModelIgnoreFlags.h: ModelIgnoreFlags
 *   position_getters.inc       Position.h:121-123, GetPositionX/Y/Z
 *   distance_order.inc         Object.cpp:1441, WorldObject::GetDistanceOrder,
 *                              whole. This is the ordering the chain walks by
 *                              and it is the core's, not a stub - see below.
 *   spell_info_attribute.inc   SpellInfo.h:443 and :445, the two HasAttribute
 *                              overloads this path reads
 *   spell_info_fields.inc      SpellInfo.cpp:788, 792, 794, 796, 805, 857 -
 *                              the record reads that put a generated column
 *                              into the object the extracted code questions
 *   effect_chain_target.inc    SpellInfo.cpp:346,
 *                              `ChainTarget = spellEntry->EffectChainTarget[effIndex];`
 *                              This one line is the whole reason the suite
 *                              exists: it is how the generated
 *                              EffectChainTargets_1 column becomes the number
 *                              Spell::SelectImplicitChainTargets reads.
 *   select_implicit_nearby.inc      Spell.cpp:1110-1230, whole
 *   select_implicit_target_object.inc Spell.cpp:1855-1875, whole
 *   select_implicit_chain.inc       Spell.cpp:1877-1902, whole
 *   search_chain_targets.inc        Spell.cpp:2151-2246, whole
 *   spell_mod_enums.inc        SpellDefines.h SpellModOp and MAX_SPELLMOD,
 *                              Player.h SpellModType and SpellModifier
 *   calculate_pct.inc          Util.h CalculatePct
 *   apply_spell_mod.inc        Player.cpp Player::ApplySpellMod, with
 *                              core-patches/0014 applied, because that is the
 *                              arithmetic the running server uses
 *   spell_mgr_lookup.inc       SpellMgr.h: SpellInfoMap, GetSpellInfo,
 *                              GetSpellInfoStoreSize and mSpellInfoMap, which
 *                              is where ApplySpellMod looks the modifier's
 *                              spell up
 *
 * `distance_order.inc` is included AFTER `class WorldObject` rather than
 * inside it, so that the core's `bool WorldObject::GetDistanceOrder(...)` can
 * be taken with its qualifier intact and not retyped; the class only declares
 * it. The other .inc files are in-class inline definitions or plain
 * statements in the core too, so they go where the core puts them.
 *
 * The two call sites are extracted WHOLE and not paraphrased, because the
 * "+1" in the ruling is entirely their doing. Spell.cpp:1866 adds the primary
 * with `AddUnitTarget(unit, 1 << effIndex, true, false)` and Spell.cpp:1870
 * only then calls `SelectImplicitChainTargets`; Spell.cpp:1192 adds the
 * primary and Spell.cpp:1229 chains afterwards. That ordering, plus
 * Spell.cpp:1892's `SearchChainTargets(targets, maxTargets - 1, ...)` and the
 * comment at :1895, "Chain primary target is added earlier", is the evidence.
 * It is executed here, not quoted.
 *
 * Everything is one translation unit; that is why the .inc files are included
 * rather than compiled on their own.
 *
 * WHAT IS STUBBED, and why each one cannot affect the answer. The answer under
 * test is a COUNT - how many units end up in the unit-target list - and the
 * order they were added in. A stub that could move either would be a hole.
 *
 *   uint8/uint16/uint32/int32   the core's Define.h typedefs, nothing more.
 *   ASSERT                      aborts instead of going through the core's
 *                               logging crash handler. It still fires.
 *   LOG_DEBUG                   a no-op. Both extracted call sites log when
 *                               they give up early; the tests that reach those
 *                               branches assert the returned target list, not
 *                               the log line.
 *   Spell::SearchAreaTargets    TEST-OWNED, AND THIS IS THE LOUD ONE. The real
 *                               function runs a grid search with
 *                               WorldObjectSpellAreaTargetCheck: it decides
 *                               WHICH units are nearby, which needs a Map, a
 *                               grid, factions, auras and phasing. That
 *                               SELECTION is not what is under test. What is
 *                               under test is how many of a given candidate
 *                               set survive `while (chainTargets)`, so the
 *                               stub hands the real loop exactly the list the
 *                               driver wrote, in the driver's order, and the
 *                               real loop does the rest. The stub mirrors the
 *                               server in one way that matters: it puts the
 *                               PRIMARY at the head of the list, because a
 *                               unit is always within range of itself and the
 *                               real search returns it too. That is what
 *                               `tempTargets.remove(target)` at Spell.cpp:2193
 *                               exists for, and a test mutates that line away
 *                               to show the primary would otherwise be chained
 *                               to twice.
 *   Spell::SearchNearbyTarget   TEST-OWNED: the same grid search, for the
 *                               nearby route's primary. It answers with the
 *                               primary the driver named.
 *   Spell::AddUnitTarget        TEST-OWNED: appends to a vector. The real one
 *                               (Spell.cpp:2341) also runs CheckTarget, effect
 *                               immunity, miss rolls, travel time and script
 *                               hooks, and - the part worth naming - it
 *                               DEDUPLICATES by ObjectGuid, merging a repeat
 *                               into the existing TargetInfo. The stub
 *                               deliberately does NOT deduplicate, so that a
 *                               failure of `tempTargets.remove(target)` shows
 *                               up as a duplicate instead of being silently
 *                               swallowed. The harness is therefore STRICTER
 *                               than the server here, never looser.
 *   Spell::AddGOTarget / AddItemTarget
 *                               the same, into their own vectors. No test
 *                               casts at a gameobject or an item; they exist
 *                               because the extracted call sites name them.
 *   CallScriptObjectTargetSelectHandlers,
 *   CallScriptObjectAreaTargetSelectHandlers,
 *   CallScriptDestinationTargetSelectHandlers
 *                               no-ops. They are the SpellScript hooks that
 *                               let a script rewrite the target list. No
 *                               Torment spell script touches Ricochet's, and
 *                               a script that did would be the thing under
 *                               test rather than the arithmetic.
 *   WorldObject::IsWithinLOSInMap
 *                               TEST-OWNED, per-unit and settable from the
 *                               case file. The real one is a VMap/Map ray
 *                               cast; there is no map here. Every candidate
 *                               has line of sight unless the driver says
 *                               otherwise, and one test blocks it on purpose
 *                               to reach the `foundItr == tempTargets.end()`
 *                               break by the other road.
 *   WorldObject::IsWithinDist   TEST-OWNED: the squared-distance comparison
 *                               from the non-transport tail of
 *                               WorldObject::_IsWithinDist (Object.cpp:1256),
 *                               written out here because that function's head
 *                               needs m_transport, m_movementInfo and
 *                               GetObjectSize. Test units have no transport
 *                               and an object size of 0, so the comparison is
 *                               the core's own minus the two bounding radii it
 *                               would add - which makes the range gate
 *                               slightly TIGHTER here than on the server, not
 *                               looser.
 *   Position::HasInArc          returns true. It is only read when
 *                               `isBouncingFar` is false, and every record the
 *                               suite drives through that branch is placed in
 *                               front of the caster by construction. The arc
 *                               is a facing question, not a counting one.
 *   Unit::GetMaxHealth/GetHealth
 *                               constants. They are read only by the
 *                               `isChainHeal` branch, which needs
 *                               TARGET_UNIT_TARGET_CHAINHEAL_ALLY; no Torment
 *                               record is a chain heal and the suite asserts
 *                               the branch is not entered.
 *   Unit::GetSpellModOwner      answers a Player the driver may install, and
 *                               nullptr otherwise. NULLPTR IS THE HONEST
 *                               DEFAULT: a Torment skill cast by a creature,
 *                               or by a player with no SPELLMOD_JUMP_TARGETS
 *                               modifier, never enters Spell.cpp:1881 at all.
 *                               One test installs an owner so that the
 *                               extracted ApplySpellMod line is executed
 *                               rather than assumed dead.
 *   SpellInfo::GetMaxRange / IsPositive
 *                               constants. They set `range` for
 *                               SearchNearbyTarget, which is the stub above,
 *                               so no number they return reaches the count.
 *   SpellCastTargets, SpellDestination, WorldLocation, ObjectGuid, Item,
 *   GameObject, Condition
 *                               shells. The destination and item branches of
 *                               the two call sites are the ones a unit-target
 *                               cast never takes, and the suite asserts the
 *                               unit-target list, which they do not touch.
 *   Player::IsAffectedBySpellmod, HasSpellModApplied, ApplyModToSpell,
 *   Aura::IsUsingCharges / GetCharges
 *                               as in tests/cost_math/core_shim.h and
 *                               tests/spell_categories/category_shim.h: the
 *                               one modifier a test makes is one the record is
 *                               affected by, on an aura with charges to spare.
 *                               Whether a family mask matches is a different
 *                               question and a different suite's.
 *
 * WHAT IS TEST-OWNED RATHER THAN EXTRACTED, named explicitly so nobody has to
 * go looking:
 *
 *   struct SpellEntry           a shell with the seven generated spell_dbc
 *                               columns the extracted constructor lines read.
 *                               The real one is 234 DBC fields; the values are
 *                               the generated spell_shells.sql rows either way.
 *   class SpellInfo             a shell holding the members those same lines
 *                               assign, plus `Effects` and `JumpDistance`.
 *                               JumpDistance is not a DBC column at all: the
 *                               core fills it from the `spell_jump_distance`
 *                               world table in SpellMgr, so the driver hands
 *                               it over separately, read out of the
 *                               `INSERT INTO spell_jump_distance` rows the
 *                               generator writes. It is a real generated
 *                               number and one test turns on it.
 *   struct SpellEffectInfo      a shell with ChainTarget and
 *                               ImplicitTargetConditions. The ChainTarget
 *                               assignment inside it is extracted.
 *   class SpellImplicitTargetInfo
 *                               a shell with the five getters the extracted
 *                               code calls. The real one decodes a Targets
 *                               enumerator through a static table; the driver
 *                               sets the five answers directly, and the suite
 *                               drives TARGET_UNIT_TARGET_ENEMY's - object
 *                               type UNIT, check type ENEMY, category
 *                               DEFAULT, reference type CASTER.
 *   class Spell                 a shell holding m_caster, m_spellInfo,
 *                               m_targets, m_damageMultipliers,
 *                               m_applyMultiplierMask and focusObject. Every
 *                               one of those members is written or read by an
 *                               extracted line. The four target-selection
 *                               methods have extracted bodies.
 *   class Unit / WorldObject / Position
 *                               shells carrying a position and an identity.
 *                               GetPositionX/Y/Z and GetDistanceOrder are the
 *                               core's; the rest is named in the stub list.
 */

#ifndef DC_TEST_CHAIN_SHIM_H
#define DC_TEST_CHAIN_SHIM_H

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <list>
#include <string>
#include <unordered_set>
#include <vector>

using int32 = std::int32_t;
using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

// The core aborts through its crash handler; a test aborts. Either way the
// check is still made, which is the point of keeping the call sites verbatim.
#define ASSERT(cond)                                                                                                   \
    do                                                                                                                 \
    {                                                                                                                  \
        if (!(cond))                                                                                                   \
        {                                                                                                              \
            std::fprintf(stderr, "ASSERT failed: %s\n", #cond);                                                        \
            std::abort();                                                                                              \
        }                                                                                                              \
    } while (0)

// Inert: both extracted call sites log when they give up early. The tests that
// reach those branches assert the target list instead.
#define LOG_DEBUG(...) ((void) 0)

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// --- the core's own enums and constants ------------------------------------

#include "chain_enums.inc"

// --- the world the chain walks through -------------------------------------

class Unit;
class GameObject;
class Spell;
class Player;
class SpellInfo;

// Test-owned: only the three coordinates the extracted GetDistanceOrder reads.
class Position
{
public:
#include "position_getters.inc"

    // Test-owned: the arc check is a facing question, and the one branch that
    // reads it is driven only with candidates placed in front of the caster.
    template<class T>
    bool HasInArc(float, T const*) const
    {
        return true;
    }

    float m_positionX = 0.0f;
    float m_positionY = 0.0f;
    float m_positionZ = 0.0f;
};

struct WorldLocation : public Position
{
};

struct ObjectGuid
{
};

// Test-owned: what a case file line becomes. `Tag` is how the driver names a
// unit in the answer it reads back; the core has no such thing.
class WorldObject : public Position
{
public:
    virtual ~WorldObject() = default;

    [[nodiscard]] virtual Unit* ToUnit()
    {
        return nullptr;
    }
    [[nodiscard]] virtual GameObject* ToGameObject()
    {
        return nullptr;
    }

    // Declared here and DEFINED BELOW out of the class, so that the core's
    // own `bool WorldObject::GetDistanceOrder(...)` can be included exactly as
    // Object.cpp writes it, qualifier and all. This is the ordering the chain
    // walks by, and it is not a stub.
    [[nodiscard]] bool GetDistanceOrder(WorldObject const* obj1, WorldObject const* obj2, bool is3D = true) const;

    // Test-owned: the squared-distance comparison from the non-transport tail
    // of WorldObject::_IsWithinDist, without the two bounding radii the core
    // adds. See the header's stub list.
    [[nodiscard]] bool IsWithinDist(WorldObject const* obj, float dist2compare, bool is3D = true) const
    {
        float dx = GetPositionX() - obj->GetPositionX();
        float dy = GetPositionY() - obj->GetPositionY();
        float distsq = dx * dx + dy * dy;
        if (is3D)
        {
            float dz = GetPositionZ() - obj->GetPositionZ();
            distsq += dz * dz;
        }
        return distsq < dist2compare * dist2compare;
    }

    // Test-owned: the real one is a VMap ray cast and there is no map here.
    template<class T>
    [[nodiscard]] bool IsWithinLOSInMap(WorldObject const* obj, T) const
    {
        return obj->DCTestHasLineOfSight;
    }

    [[nodiscard]] ObjectGuid GetGUID() const
    {
        return ObjectGuid();
    }

    // Test-owned bookkeeping, not a core field.
    uint32 DCTestTag = 0;
    bool DCTestHasLineOfSight = true;
};

// The core's own, out of Object.cpp at the pin.
#include "distance_order.inc"

class Unit : public WorldObject
{
public:
    [[nodiscard]] Unit* ToUnit() override
    {
        return this;
    }

    // Answers the Player the driver installed, and nullptr otherwise. See the
    // header: nullptr is the honest default.
    [[nodiscard]] Player* GetSpellModOwner() const
    {
        return DCTestSpellModOwner;
    }

    // Read only inside the isChainHeal branch, which no Torment record enters.
    [[nodiscard]] uint32 GetMaxHealth() const
    {
        return 100;
    }
    [[nodiscard]] uint32 GetHealth() const
    {
        return 100;
    }

    Player* DCTestSpellModOwner = nullptr;
};

class GameObject : public WorldObject
{
public:
    [[nodiscard]] GameObject* ToGameObject() override
    {
        return this;
    }
};

class Item
{
};

// Test-owned: the conditions list is passed straight through the extracted
// code to SearchAreaTargets, which is the stub, so nothing ever reads it.
struct Condition
{
};
typedef std::list<Condition*> ConditionList;

namespace VMAP
{
#include "model_ignore_flags.inc"
} // namespace VMAP

namespace Acore
{
#include "search_reason.inc"
} // namespace Acore

// --- the record, and what the core makes of it -----------------------------

// Test-owned: the generated spell_shells.sql columns the extracted
// constructor lines read. Field names are the core's.
struct SpellEntry
{
    uint32 Id = 0;
    uint32 Attributes = 0;
    uint32 AttributesEx2 = 0;
    uint32 AttributesEx4 = 0;
    uint32 RequiresSpellFocus = 0;
    uint32 DmgClass = 0;
    uint32 EffectChainTarget[MAX_SPELL_EFFECTS] = {0, 0, 0};
};

// Test-owned shell. The one assignment inside it is the core's, and it is the
// line that turns a generated column into the number under test.
struct SpellEffectInfo
{
    SpellEffectInfo() = default;
    SpellEffectInfo(SpellEntry const* spellEntry, uint8 effIndex)
    {
#include "effect_chain_target.inc"
    }

    uint32 ChainTarget = 0;
    ConditionList* ImplicitTargetConditions = nullptr;
};

// Test-owned shell. Every member below is either assigned by an extracted line
// of SpellInfo's constructor or, in JumpDistance's case, filled by SpellMgr
// from a world table - see the header.
class SpellInfo
{
public:
    explicit SpellInfo(SpellEntry const* spellEntry)
    {
#include "spell_info_fields.inc"
        for (uint8 effIndex = 0; effIndex < MAX_SPELL_EFFECTS; ++effIndex)
            Effects[effIndex] = SpellEffectInfo(spellEntry, effIndex);
    }

    // SpellInfo.h at the pin, the two overloads this path reads.
#include "spell_info_attribute.inc"

    // Stubs: both only feed `range`, which only reaches SearchNearbyTarget,
    // which is the stub that answers with the primary the driver named.
    [[nodiscard]] float GetMaxRange(bool = false, Unit* = nullptr, Spell* = nullptr) const
    {
        return 100.0f;
    }
    [[nodiscard]] bool IsPositive() const
    {
        return false;
    }

    uint32 Id = 0;
    uint32 Attributes = 0;
    uint32 AttributesEx2 = 0;
    uint32 AttributesEx4 = 0;
    uint32 RequiresSpellFocus = 0;
    uint32 DmgClass = 0;
    // Not a DBC column: SpellMgr fills it from the `spell_jump_distance` world
    // table, and the driver sets it the same way.
    float JumpDistance = 0.0f;
    SpellEffectInfo Effects[MAX_SPELL_EFFECTS];
};

// The record store the extracted Player::ApplySpellMod looks a modifier's
// spell up in: SpellMgr.h's own SpellInfoMap and its GetSpellInfo line. Only
// the filling below is ours.
#include "spell_mgr_lookup.inc"

inline void RegisterSpellInfo(SpellInfo* info)
{
    if (info->Id >= sSpellMgr->mSpellInfoMap.size())
        sSpellMgr->mSpellInfoMap.resize(info->Id + 1, nullptr);
    sSpellMgr->mSpellInfoMap[info->Id] = info;
}

// Test-owned shell: the five answers the extracted code asks a target type
// for. The real one decodes a Targets enumerator through a static table.
class SpellImplicitTargetInfo
{
public:
    [[nodiscard]] SpellTargetObjectTypes GetObjectType() const
    {
        return _objectType;
    }
    [[nodiscard]] SpellTargetCheckTypes GetCheckType() const
    {
        return _checkType;
    }
    [[nodiscard]] SpellTargetSelectionCategories GetSelectionCategory() const
    {
        return _category;
    }
    [[nodiscard]] SpellTargetReferenceTypes GetReferenceType() const
    {
        return _referenceType;
    }
    [[nodiscard]] Targets GetTarget() const
    {
        return _target;
    }

    SpellTargetObjectTypes _objectType = TARGET_OBJECT_TYPE_UNIT;
    SpellTargetCheckTypes _checkType = TARGET_CHECK_ENEMY;
    SpellTargetSelectionCategories _category = TARGET_SELECT_CATEGORY_DEFAULT;
    SpellTargetReferenceTypes _referenceType = TARGET_REFERENCE_TYPE_CASTER;
    Targets _target = TARGET_UNIT_TARGET_ENEMY;
};

// Shells: the destination and item branches a unit-target cast never takes.
struct SpellDestination
{
    SpellDestination() = default;
    explicit SpellDestination(WorldObject const&) {}

    WorldLocation _position;
};

class SpellCastTargets
{
public:
    [[nodiscard]] WorldObject* GetObjectTarget() const
    {
        return _objectTarget;
    }
    [[nodiscard]] Item* GetItemTarget() const
    {
        return nullptr;
    }
    [[nodiscard]] Unit* GetUnitTarget() const
    {
        return _unitTarget;
    }
    void SetUnitTarget(Unit* unit)
    {
        _unitTarget = unit;
    }
    void SetDst(SpellDestination const&) {}

    WorldObject* _objectTarget = nullptr;
    Unit* _unitTarget = nullptr;
};

// --- the modifier the extracted ApplySpellMod line goes through ------------

struct flag96
{
};

class Aura
{
public:
    [[nodiscard]] bool IsUsingCharges() const
    {
        return false;
    }
    [[nodiscard]] uint8 GetCharges() const
    {
        return 0;
    }
};

#include "spell_mod_enums.inc"
#include "calculate_pct.inc"

class Player : public Unit
{
public:
    template<class T>
    void ApplySpellMod(uint32 spellId, SpellModOp op, T& basevalue, Spell* spell = nullptr, bool temporaryPet = false);

    // Stubs, each one off the path: see the header's stub list.
    bool IsAffectedBySpellmod(SpellInfo const*, SpellModifier*, Spell*)
    {
        return true;
    }
    bool HasSpellModApplied(SpellModifier*, Spell*)
    {
        return true;
    }
    void ApplyModToSpell(SpellModifier*, Spell*) {}

    Spell* m_spellModTakingSpell = nullptr;
    std::unordered_set<SpellModifier*> m_spellMods[MAX_SPELLMOD];
};

// --- the cast ---------------------------------------------------------------

// Test-owned shell. Every member is written or read by an extracted line; the
// four target-selection methods below have extracted bodies.
class Spell
{
public:
    Spell(Unit* caster, SpellInfo const* spellInfo)
        : m_spellInfo(spellInfo)
        , m_caster(caster)
    {
        for (uint32 index = 0; index < MAX_SPELL_EFFECTS; ++index)
            m_damageMultipliers[index] = 0.0f;
    }

    // Extracted, whole, out of Spell.cpp at the pin.
    void SelectImplicitNearbyTargets(SpellEffIndex effIndex, SpellImplicitTargetInfo const& targetType, uint32 effMask);
    void SelectImplicitTargetObjectTargets(SpellEffIndex effIndex, SpellImplicitTargetInfo const& targetType);
    void SelectImplicitChainTargets(SpellEffIndex effIndex, SpellImplicitTargetInfo const& targetType,
                                    WorldObject* target, uint32 effMask);
    void SearchChainTargets(std::list<WorldObject*>& targets, uint32 chainTargets, WorldObject* target,
                            SpellTargetObjectTypes objectType, SpellTargetCheckTypes selectType,
                            SpellTargetSelectionCategories selectCategory, ConditionList* condList, bool isChainHeal);

    // TEST-OWNED, and the loudest stub in the file. The real function decides
    // WHICH units are nearby; that selection is not under test. This hands the
    // real loop the driver's candidate list, in the driver's order, with the
    // primary at its head exactly as the server's own search would return it.
    void SearchAreaTargets(std::list<WorldObject*>& targets, float /*range*/, Position const* /*position*/,
                           Unit* /*referer*/, SpellTargetObjectTypes /*objectType*/,
                           SpellTargetCheckTypes /*selectionType*/, ConditionList* /*condList*/,
                           Acore::WorldObjectSpellAreaTargetSearchReason /*searchReason*/
                           = Acore::WorldObjectSpellAreaTargetSearchReason::Area,
                           SpellTargetReferenceTypes /*referenceType*/ = TARGET_REFERENCE_TYPE_CASTER)
    {
        if (DCTestPrimary)
            targets.push_back(DCTestPrimary);
        for (WorldObject* candidate : DCTestCandidates)
            targets.push_back(candidate);
    }

    // TEST-OWNED: the same grid search, for the nearby route's primary.
    WorldObject* SearchNearbyTarget(float /*range*/, SpellTargetObjectTypes /*objectType*/,
                                    SpellTargetCheckTypes /*selectionType*/, ConditionList* /*condList*/ = nullptr)
    {
        return DCTestPrimary;
    }

    // TEST-OWNED: appends. The real one deduplicates by ObjectGuid; this one
    // deliberately does not, so a lost `tempTargets.remove(target)` shows up
    // as a duplicate rather than being swallowed.
    void AddUnitTarget(Unit* target, uint32 /*effectMask*/, bool /*checkIfValid*/ = true, bool /*implicit*/ = true)
    {
        DCTestUnitTargets.push_back(target);
    }
    void AddGOTarget(GameObject* target, uint32 /*effectMask*/)
    {
        DCTestGOTargets.push_back(target);
    }
    void AddItemTarget(Item* /*item*/, uint32 /*effectMask*/)
    {
        ++DCTestItemTargets;
    }

    // No-ops: the SpellScript hooks that let a script rewrite the list.
    void CallScriptObjectTargetSelectHandlers(WorldObject*& /*target*/, SpellEffIndex /*effIndex*/,
                                              SpellImplicitTargetInfo const& /*targetType*/)
    {
    }
    void CallScriptObjectAreaTargetSelectHandlers(std::list<WorldObject*>& /*targets*/, SpellEffIndex /*effIndex*/,
                                                  SpellImplicitTargetInfo const& /*targetType*/)
    {
    }
    void CallScriptDestinationTargetSelectHandlers(SpellDestination& /*target*/, SpellEffIndex /*effIndex*/,
                                                   SpellImplicitTargetInfo const& /*targetType*/)
    {
    }

    SpellInfo const* const m_spellInfo;
    Unit* const m_caster;
    SpellCastTargets m_targets;
    GameObject* focusObject = nullptr;
    uint8 m_applyMultiplierMask = 0;
    float m_damageMultipliers[3];

    // Test-owned bookkeeping, not core fields.
    WorldObject* DCTestPrimary = nullptr;
    std::list<WorldObject*> DCTestCandidates;
    std::vector<Unit*> DCTestUnitTargets;
    std::vector<GameObject*> DCTestGOTargets;
    uint32 DCTestItemTargets = 0;
};

#include "apply_spell_mod.inc"
#include "select_implicit_nearby.inc"
#include "select_implicit_target_object.inc"
#include "select_implicit_chain.inc"
#include "search_chain_targets.inc"

namespace DCTest
{
    inline SpellModifier* Modifier(SpellModOp op, SpellModType type, int32 value)
    {
        auto* mod = new SpellModifier(new Aura());
        mod->op = op;
        mod->type = type;
        mod->value = value;
        return mod;
    }
} // namespace DCTest

#endif // DC_TEST_CHAIN_SHIM_H
