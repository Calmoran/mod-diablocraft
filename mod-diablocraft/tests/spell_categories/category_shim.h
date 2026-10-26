/*
 * The scaffolding the core's own category-cooldown path needs to compile
 * outside the server (spell rewrite step 6, PM correction).
 *
 * Step 6 gave a base skill and its five runes one shared timer by putting a
 * category id in the spell record. A category id only exists as far as the
 * core is concerned if SpellCategory.dbc has a row for it, and the proof the
 * Architect asked for on 2026-09-20 is that two runes of one skill really do
 * share a cooldown "through the real core category store". So nothing on that
 * path is modelled here. `scripts/tests/classes/test_spell_categories.py` takes the
 * following out of the core at pin 9d9b604 and writes them beside this header
 * for it to include, verbatim except where a line says otherwise:
 *
 *   DBCFileLoader.h / DBCFileLoader.cpp   src/common/DataStores/, whole files:
 *                                         the parser that has to accept the
 *                                         generated client-patch/dbc file
 *   DBCStorageIterator.h                  src/server/shared/DataStores/, whole
 *   DBCStore.h                            src/server/shared/DataStores/, whole
 *   dbc_store_base.inc                    DBCStore.cpp: DBCStorageBase's
 *                                         constructor, destructor and
 *                                         Load(char const*, char**&)
 *   dbc_structure.inc                     DBCStructure.h: SpellCategorySet,
 *                                         SpellCategoryStore, SpellCategoryEntry
 *   dbc_fmt.inc                           DBCfmt.h: SpellCategoryfmt ("ni")
 *   dbc_stores.inc                        DBCStores.cpp: the two store
 *                                         definitions and the loop that fills
 *                                         sSpellsByCategoryStore after the
 *                                         spell store loads
 *   spell_constants.inc                   the enums and constants the path
 *                                         reads: SpellAttr0/2/6,
 *                                         SpellCustomAttributes,
 *                                         SpellCategoryFlags, IN_MILLISECONDS,
 *                                         MAX_ITEM_SPELLS, WeaponAttackType,
 *                                         SpellCooldownFlags,
 *                                         SPELL_AURA_MOD_COOLDOWN,
 *                                         SPECTATOR_COOLDOWN_MIN/MAX,
 *                                         infinityCooldownDelay, PacketCooldowns
 *   spell_info_fields.inc                 SpellInfo.cpp:788-855, the record
 *                                         reads this proof turns on, the
 *                                         CategoryEntry line at :789 first
 *   spell_info_methods.inc                SpellInfo.cpp: GetCategory,
 *                                         IsCooldownStartedOnEvent,
 *                                         IsAutoRepeatRangedSpell
 *   spell_mgr_lookup.inc                  SpellMgr.h: SpellInfoMap,
 *                                         GetSpellInfo, GetSpellInfoStoreSize
 *   spell_cooldown_types.inc              Player.h: SpellCooldown and the
 *                                         SpellCooldowns map
 *   player_cooldowns.inc                  Player.cpp:11083-11257,
 *                                         AddSpellAndCategoryCooldowns and
 *                                         _AddSpellCooldown
 *   apply_spell_mod.inc                   Player.cpp Player::ApplySpellMod
 *   spell_mod_enums.inc                   SpellDefines.h SpellModOp and
 *                                         MAX_SPELLMOD, Player.h SpellModType
 *                                         and SpellModifier
 *   calculate_pct.inc                     Util.h CalculatePct
 *
 * The last three are the same pieces `tests/cost_math/core_shim.h` compiles,
 * extracted by the same helpers with `core-patches/0014` applied, because a
 * cooldown modifier reaches the record through this path and the suite has to
 * show it still lands.
 *
 * The extractor also drops one-line `Define.h`, `Errors.h`, `Common.h` and
 * `Utilities/ByteConverter.h` beside them, each of which is nothing but
 * `#include "category_shim.h"`, so the core files' own include lines resolve
 * to what is declared below without a single one of them being edited.
 * Everything is one translation unit; that is why the .cpp is included rather
 * than compiled on its own.
 *
 * WHAT IS STUBBED, and why each one is off the path under test. Nothing here
 * is consulted by the sharing proof; a stub that mattered would be a hole.
 *
 *   uint8/uint16/uint32/int32   the core's Define.h typedefs, nothing more.
 *   ASSERT / ASSERT_NOTNULL     abort on failure instead of the core's logging
 *                               crash handler. They still fire.
 *   EndianConvert               a no-op. The core's own ByteConverter is a
 *                               no-op on a little-endian host too, and the
 *                               tests only run on one.
 *   AC_GAME_API                 empty: an export attribute, not behaviour.
 *   DBCStorageBase::LoadStringsFrom / ::LoadFromDB
 *                               inert. LoadFromDB is the server's own route
 *                               for the eleven rows - the spellcategory_dbc
 *                               world table - but running it would need
 *                               DBCDatabaseLoader, QueryResult, Field and a
 *                               live WorldDatabase. The harness installs those
 *                               rows with the core's own DBCStorage::SetEntry
 *                               instead, and the overlay test's docstring
 *                               quotes DBCDatabaseLoader::Load's merge and
 *                               says plainly what that does and does not
 *                               prove. LoadStringsFrom is the locale pass and
 *                               nothing reaches it.
 *   WorldPacket, BuildCooldownPacket, SendDirectMessage, ArenaSpectator::
 *   SendCommand_Cooldown, NeedSendSpectatorData, HasActiveSpell, FindMap,
 *   GetGUID, ObjectGuid, Map
 *                               the client and spectator traffic the path
 *                               emits. What is under test is which records end
 *                               up on cooldown and for how long, which is
 *                               m_spellCooldowns, not what is sent.
 *   GetTotalAuraModifier        returns 0. SPELL_AURA_MOD_COOLDOWN is the
 *                               stock aura on one Wyrmcult spell; Torment's
 *                               cooldown reduction is SPELLMOD_COOLDOWN, which
 *                               is real here. At 0 the branch is not entered,
 *                               which is what a Torment character does.
 *   HasSpell                    returns false; only read inside that branch.
 *   GetAttackTime               returns 0; only read when a record has no
 *                               cooldown at all AND is category 76 or an auto
 *                               repeat ranged spell. No Torment record is
 *                               either, and the suite asserts that.
 *   sObjectMgr->GetItemTemplate returns nullptr, and ItemTemplate is a shell.
 *                               Every cast under test is itemId 0; the item
 *                               branch is the one the record path replaces.
 *   Aura::IsUsingCharges / GetCharges, IsAffectedBySpellmod,
 *   HasSpellModApplied, ApplyModToSpell
 *                               as in tests/cost_math/core_shim.h: every
 *                               modifier a test makes is one the record is
 *                               affected by, on an aura with charges to spare.
 *                               Whether a family mask matches is a different
 *                               question and the record suite is what proves
 *                               it.
 *   GameTime::GetGameTimeMS     a frozen clock, so a printed remaining time is
 *                               exactly the cooldown that was installed.
 *   sWorld                      absent entirely: nothing on this path reads a
 *                               config value.
 *
 * TWO THINGS ARE TEST-OWNED RATHER THAN EXTRACTED, and the report says so:
 *
 *   struct SpellEntry           a shell with the nine columns the extracted
 *                               constructor lines read. The real one is 234
 *                               DBC fields; the values are the generated
 *                               spell_shells.sql rows either way.
 *   class SpellInfo             a shell holding the members those same lines
 *                               assign. GetCategory, IsCooldownStartedOnEvent
 *                               and IsAutoRepeatRangedSpell are extracted; the
 *                               four HasAttribute overloads are transcribed
 *                               from SpellInfo.h:441-449 rather than
 *                               extracted, because they are inline in the
 *                               class and there is no block to lift. They are
 *                               `(field & attribute) != 0` and nothing else.
 *   SpellMgr                    holds the core's own mSpellInfoMap and its
 *                               GetSpellInfo line; only the filling is ours.
 *   BuildSpellsByCategory       a wrapper. Its three-line body is the
 *                               DBCStores.cpp loop, extracted; the function it
 *                               sits in is ours because the core runs those
 *                               lines inside LoadDBCStores.
 */

#ifndef DC_TEST_CATEGORY_SHIM_H
#define DC_TEST_CATEGORY_SHIM_H

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <chrono>
#include <ctime>
#include <iterator>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using int32 = std::int32_t;
using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
#define AC_GAME_API

// The core aborts through its crash handler; a test aborts. Either way the
// check is still made, which is the point of keeping the parser verbatim.
#define ASSERT(cond)                                                                                                   \
    do                                                                                                                 \
    {                                                                                                                  \
        if (!(cond))                                                                                                   \
        {                                                                                                              \
            std::fprintf(stderr, "ASSERT failed: %s\n", #cond);                                                        \
            std::abort();                                                                                              \
        }                                                                                                              \
    } while (0)
#define ASSERT_NOTNULL(p) (p)

// A no-op, exactly as the core's ByteConverter is on a little-endian host.
template<class T>
inline void EndianConvert(T&)
{
}

// A frozen clock, so "remaining" is the cooldown that was installed and the
// harness prints the same numbers on every run. Not a game value.
constexpr uint32 DC_TEST_FROZEN_NOW_MS = 1000000;

namespace GameTime
{
    inline std::chrono::milliseconds GetGameTimeMS()
    {
        return std::chrono::milliseconds(DC_TEST_FROZEN_NOW_MS);
    }
} // namespace GameTime

// --- the core's DBC parser and index table, verbatim -----------------------

#include "DBCFileLoader.h"
#include "DBCFileLoader.cpp"
#include "dbc_structure.inc"
#include "DBCStore.h"
#include "dbc_store_base.inc"

// The two DBCStorageBase entry points the template overrides but nothing under
// test calls. LoadFromDB needs DBCDatabaseLoader and a world database
// connection; LoadStringsFrom is the locale pass. Both inert, both loud if
// they were ever reached.
bool DBCStorageBase::LoadStringsFrom(char const*, char**)
{
    ASSERT(false && "nothing under test loads a locale string table");
    return false;
}

void DBCStorageBase::LoadFromDB(char const*, char const*, char**&)
{
    ASSERT(false && "nothing under test loads a DBC store from the database");
}

#include "dbc_fmt.inc"
#include "spell_constants.inc"

// --- the record, and what the core makes of it -----------------------------

// Test-owned: the nine columns of the generated spell_shells.sql rows that the
// extracted SpellInfo constructor lines read. Field names are the core's.
struct SpellEntry
{
    uint32 Id = 0;
    uint32 Category = 0;
    uint32 Attributes = 0;
    uint32 AttributesEx2 = 0;
    uint32 AttributesEx6 = 0;
    uint32 RecoveryTime = 0;
    uint32 CategoryRecoveryTime = 0;
    uint32 SpellFamilyName = 0;
};

// Test-owned shell. Every member below is assigned by an extracted line of
// SpellInfo's constructor, and every method the cooldown path calls has an
// extracted body.
class SpellInfo
{
public:
    explicit SpellInfo(SpellEntry const* spellEntry);

    [[nodiscard]] uint32 GetCategory() const;
    [[nodiscard]] bool IsCooldownStartedOnEvent() const;
    [[nodiscard]] bool IsAutoRepeatRangedSpell() const;

    // SpellInfo.h:441-449 at the pin, one overload per attribute field.
    [[nodiscard]] inline bool HasAttribute(SpellAttr0 attribute) const
    {
        return (Attributes & attribute) != 0;
    }
    [[nodiscard]] inline bool HasAttribute(SpellAttr2 attribute) const
    {
        return (AttributesEx2 & attribute) != 0;
    }
    [[nodiscard]] inline bool HasAttribute(SpellAttr6 attribute) const
    {
        return (AttributesEx6 & attribute) != 0;
    }
    [[nodiscard]] inline bool HasAttribute(SpellCustomAttributes customAttribute) const
    {
        return (AttributesCu & customAttribute) != 0;
    }

    uint32 Id = 0;
    SpellCategoryEntry const* CategoryEntry = nullptr;
    uint32 Attributes = 0;
    uint32 AttributesEx2 = 0;
    uint32 AttributesEx6 = 0;
    uint32 RecoveryTime = 0;
    uint32 CategoryRecoveryTime = 0;
    uint32 SpellFamilyName = 0;
    // Not a DBC column: the core loads it from spell_custom_attr in
    // SpellMgr::LoadSpellCustomAttr, and the harness sets it from the same
    // rows the migration carries.
    uint32 AttributesCu = 0;
};

// The stores, and the loop that fills the category multimap, out of
// DBCStores.cpp. sSpellStore is filled with the core's own SetEntry rather
// than loaded from a 49 MB Spell.dbc; sSpellCategoryStore is loaded from the
// generated file by the core's own Load().
#include "dbc_stores.inc"

#include "spell_info_methods.inc"

SpellInfo::SpellInfo(SpellEntry const* spellEntry)
{
#include "spell_info_fields.inc"
}

#include "spell_mgr_lookup.inc"

// Only the filling is ours: the lookup above is SpellMgr.h:742 and :767.
inline void RegisterSpellInfo(SpellInfo* info)
{
    if (info->Id >= sSpellMgr->mSpellInfoMap.size())
        sSpellMgr->mSpellInfoMap.resize(info->Id + 1, nullptr);
    sSpellMgr->mSpellInfoMap[info->Id] = info;
}

// --- the player, and the cooldowns it ends up holding ----------------------

// The modifier's spell-family mask. The combine never reads it; what does is
// IsAffectedBySpellmod, and that is stubbed below for the reason the header
// gives.
struct flag96
{
};

class Aura
{
public:
    bool IsUsingCharges() const
    {
        return false;
    }
    uint8 GetCharges() const
    {
        return 0;
    }
};

class Spell
{
};

// The modifier the record's cooldown goes through, and the cooldown map the
// player ends up holding: the same pieces tests/cost_math/core_shim.h
// compiles, with core-patches/0014 applied.
#include "spell_mod_enums.inc"
#include "calculate_pct.inc"
#include "spell_cooldown_types.inc"

class WorldPacket
{
};
struct Map
{
};
struct ObjectGuid
{
};

namespace ArenaSpectator
{
    // Inert: the spectator command the cooldown would be announced with.
    template<class... Args>
    inline void SendCommand_Cooldown(Args&&...)
    {
    }
} // namespace ArenaSpectator

// Inert: every cast under test is itemId 0, so GetItemTemplate answers
// nullptr and the item branch of AddSpellAndCategoryCooldowns is not entered.
struct ItemTemplateSpell
{
    int32 SpellId = 0;
    uint32 SpellCategory = 0;
    int32 SpellCooldown = 0;
    uint32 SpellCategoryCooldown = 0;
};

struct ItemTemplate
{
    ItemTemplateSpell Spells[MAX_ITEM_SPELLS];
};

struct ObjectMgr
{
    ItemTemplate const* GetItemTemplate(uint32) const
    {
        return nullptr;
    }
};
static ObjectMgr const* const sObjectMgr = new ObjectMgr();

class Player
{
public:
    template<class T>
    void ApplySpellMod(uint32 spellId, SpellModOp op, T& basevalue, Spell* spell = nullptr, bool temporaryPet = false);

    void AddSpellAndCategoryCooldowns(SpellInfo const* spellInfo, uint32 itemId, Spell* spell = nullptr,
                                      bool infinityCooldown = false);
    void _AddSpellCooldown(uint32 spellid, uint16 categoryId, uint32 itemid, uint32 end_time,
                           bool needSendToClient = false, bool forceSendToSpectator = false);

    // Stubs, each one off the path: see the header.
    bool IsAffectedBySpellmod(SpellInfo const*, SpellModifier*, Spell*)
    {
        return true;
    }
    bool HasSpellModApplied(SpellModifier*, Spell*)
    {
        return true;
    }
    void ApplyModToSpell(SpellModifier*, Spell*) {}
    int32 GetTotalAuraModifier(AuraType) const
    {
        return 0;
    }
    bool HasSpell(uint32) const
    {
        return false;
    }
    bool HasActiveSpell(uint32) const
    {
        return false;
    }
    uint32 GetAttackTime(WeaponAttackType) const
    {
        return 0;
    }
    bool NeedSendSpectatorData() const
    {
        return false;
    }
    Map* FindMap() const
    {
        return nullptr;
    }
    ObjectGuid GetGUID() const
    {
        return ObjectGuid();
    }
    void BuildCooldownPacket(WorldPacket&, uint8, uint32, uint32) {}
    void BuildCooldownPacket(WorldPacket&, uint8, PacketCooldowns const&) {}
    void SendDirectMessage(WorldPacket*) {}

    Spell* m_spellModTakingSpell = nullptr;
    std::unordered_set<SpellModifier*> m_spellMods[MAX_SPELLMOD];
    SpellCooldowns m_spellCooldowns;
};

#include "apply_spell_mod.inc"
#include "player_cooldowns.inc"

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

#endif // DC_TEST_CATEGORY_SHIM_H
