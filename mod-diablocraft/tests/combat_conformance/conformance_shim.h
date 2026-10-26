/*
 * Doubles for diablocraft-pre-beta-bugs-b, combat conformance items 1-3.
 *
 * What is REAL here, cut out of the module's own files by
 * scripts/tests/combat/test_combat_conformance.py and not copied: the class gates
 * `Barbarian` and `HitsThroughCombat`, the two auto-attack guards, the melee
 * outcome hook, the shell range constants, `SkillCooldownMilliseconds`,
 * `StartSkillCooldown`, `HandAttacksPerSecond` (dc_combat.cpp) and the primary
 * script's `Finish` (dc_barbarian_primaries.cpp). The set of playable WoW class ids is
 * read out of the generated dc_class_map rows, not written here.
 *
 * What is a double and proves nothing about the core: the player, the session,
 * the packet, the sheet store, the cast bookkeeping and the cooldown packet.
 * Nothing here runs Unit::RollMeleeOutcomeAgainst, the swing timer or the
 * client's cooldown display; docs/test-pre-beta-bugs-b.md checks those live.
 */

#ifndef DC_COMBAT_CONFORMANCE_SHIM_H
#define DC_COMBAT_CONFORMANCE_SHIM_H

#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <unordered_map>

using int32 = std::int32_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using uint8 = std::uint8_t;

constexpr uint32 CLASS_WARRIOR = 1;
enum Opcodes : uint32
{
    CMSG_ATTACKSWING = 0x141,
    CMSG_CAST_SPELL = 0x12E
};
enum UnitState : uint32
{
    UNIT_STATE_MELEE_ATTACKING = 0x00000400
};
enum WeaponAttackType
{
    BASE_ATTACK = 0,
    OFF_ATTACK = 1
};

struct ObjectGuid
{
    uint64 raw = 0;
    uint64 GetRawValue() const
    {
        return raw;
    }
};

class Player;
class Unit
{
public:
    virtual ~Unit() = default;
    virtual Player* ToPlayer()
    {
        return nullptr;
    }
    virtual Player const* ToPlayer() const
    {
        return nullptr;
    }
};

class Player final : public Unit
{
public:
    Player(uint64 guid, uint32 wowClass)
        : guid_{guid}
        , class_(wowClass)
    {
    }
    Player* ToPlayer() override
    {
        return this;
    }
    Player const* ToPlayer() const override
    {
        return this;
    }
    uint32 getClass() const
    {
        return class_;
    }
    ObjectGuid GetGUID() const
    {
        return guid_;
    }
    bool HasUnitState(uint32 state) const
    {
        return (state_ & state) != 0;
    }
    void AddUnitState(uint32 state)
    {
        state_ |= state;
    }
    void AttackStop()
    {
        state_ &= ~uint32(UNIT_STATE_MELEE_ATTACKING);
        ++stops;
    }
    unsigned stops = 0;

private:
    ObjectGuid guid_;
    uint32 class_;
    uint32 state_ = 0;
};

class Creature final : public Unit
{
};

class WorldSession
{
public:
    explicit WorldSession(Player* player)
        : player_(player)
    {
    }
    Player* GetPlayer() const
    {
        return player_;
    }

private:
    Player* player_;
};

class WorldPacket
{
public:
    explicit WorldPacket(uint32 opcode)
        : opcode_(opcode)
    {
    }
    uint32 GetOpcode() const
    {
        return opcode_;
    }

private:
    uint32 opcode_;
};

// Filled from the generated dc_class_map by the harness's main().
namespace DC::Classes
{
    inline std::set<uint32> playableClasses;
    // dc_classes.cpp's Playable: true when this player's WoW class has a row
    // in dc_class_map. The rows are the generated ones; only the lookup is a
    // double.
    inline bool Playable(Player const* player)
    {
        return player && playableClasses.count(player->getClass()) != 0;
    }
} // namespace DC::Classes

// The sheet's Dodge (skill buffs, dc_abilities.cpp). Keyed by guid so a case
// can give one victim Dodge and leave another at zero.
namespace DC::Combat::Abilities
{
    inline std::map<uint64, double> dodge;
    inline double DodgeChance(Player const* player)
    {
        auto found = player ? dodge.find(player->GetGUID().GetRawValue()) : dodge.end();
        return found == dodge.end() ? 0.0 : found->second;
    }
} // namespace DC::Combat::Abilities

// The Monk's own dodge (Dashing Strike - Blinding Speed, dc_monk.cpp), added to the sheet's in the outcome hook: none here, so
// the cases keep reading the sheet's number alone.
namespace DC::Combat::Monk
{
    inline double Dodge(Unit const*)
    {
        return 0.0;
    }
    // Blinding Flash's miss chance for a blinded attacker (dc_monk.cpp), the same way: none.
    inline double MissChance(Unit const*)
    {
        return 0.0;
    }
    // The Monk's passives' share of a hand's attack speed (Alacrity, diablocraft-m6v00, dc_monk_passives_guardians_path.cpp): none, the
    // speed the sheet gives comes back as it was.
    inline double AttackSpeed(Player*, std::uint32_t, double base)
    {
        return base;
    }
} // namespace DC::Combat::Monk

// The Shaman's Sandstorm blind (dc_shaman_thunderstorm.cpp), added to the Monk's in the outcome hook: none here.
namespace DC::Combat::Shaman
{
    inline double MissChance(Unit const*)
    {
        return 0.0;
    }
} // namespace DC::Combat::Shaman

// The Crusader's passives' share of a skill's attack speed (Fanaticism, dc_crusader_passives.cpp): none, the speed comes back as it was.
namespace DC::Combat::Crusader
{
    inline double AttackSpeed(Player*, std::uint32_t, double base)
    {
        return base;
    }
    // Hold Your Ground's end of dodging (dc_crusader_passives.cpp): none, the sheet's dodge stands.
    inline double DodgeFactor(Unit const*)
    {
        return 1.0;
    }
} // namespace DC::Combat::Crusader

// The Necromancer's passives' share of a skill's attack speed (Swift Harvesting, dc_necromancer_passives.cpp): none, the speed comes back as it was.
namespace DC::Combat::Necromancer
{
    inline double AttackSpeed(Player*, std::uint32_t, double base)
    {
        return base;
    }
} // namespace DC::Combat::Necromancer

// The Witch Doctor's share of a skill's attack speed (Rain of Toads, dc_witch_doctor_plague_of_toads.cpp): none, the speed comes back as it was.
namespace DC::Combat::WitchDoctor
{
    inline double AttackSpeed(Player*, std::uint32_t, double base)
    {
        return base;
    }
} // namespace DC::Combat::WitchDoctor

// The two per-hand speeds the sheet stores (dc_common.h StatSheet).
struct StatSheet
{
    double attacksPerSecond = 0, offhandAttacksPerSecond = 0;
};
namespace DC::Stats
{
    inline std::map<uint64, StatSheet> sheets;
    inline std::optional<StatSheet> Get(uint64 guid)
    {
        auto found = sheets.find(guid);
        if (found == sheets.end())
            return std::nullopt;
        return found->second;
    }
} // namespace DC::Stats

// The primary catalogue and the skill's own speed rule. A Frenzy-style rule
// multiplies whichever hand it is handed, so a test that sees the off-hand's
// number scaled has proved the hand reached the rule.
namespace DC::Combat::Primaries
{
    inline double speedRule = 1.0;
    inline double AttackSpeed(Player*, uint32, double base)
    {
        return base * speedRule;
    }
} // namespace DC::Combat::Primaries
// A skill's own attack speed from the item powers (Bracers of the First Men, diablocraft-li0ie): no item is worn here;
// test_item_power_math.py drives the rule.
namespace DC::Combat::ItemPowers
{
    inline double SkillFactor(Player const*, std::string const&, std::string const&)
    {
        return 1.0;
    }
    // Stone Gauntlets' slow (diablocraft-ghb4o): none here; test_item_power_stone_gauntlets.py drives it.
    inline double AttackSpeedFactor(Player*)
    {
        return 1.0;
    }
    // Gesture of Orpheus's cooldown cut (diablocraft-1i52b, N-CD), read by SkillCooldownMilliseconds: none here, so the cooldown
    // cases keep reading the record's number; test_item_power_gesture_of_orpheus.py drives it.
    inline double CooldownFactor(Player const*, std::string const&)
    {
        return 1.0;
    }
} // namespace DC::Combat::ItemPowers
namespace DC::Combat::PrimaryData
{
    inline std::set<uint32> primaries;
    inline void const* Find(uint32 spellId)
    {
        return primaries.count(spellId) ? &primaries : nullptr;
    }
} // namespace DC::Combat::PrimaryData

// A primary's recovery never reaches the record path; anything that does is
// reported as this sentinel so a wrong branch cannot pass as a primary.
struct SpellInfo
{
    uint32 RecoveryTime = 0, CategoryRecoveryTime = 0;
};
// The Wizard's Teleport record for the cooldown case (#72): a 16 s recovery
// on a record above the Barbarian's id block, as the generated one carries.
inline SpellInfo const wizardRecord{16000, 0};
struct SpellMgr
{
    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        return id == 83111 ? &wizardRecord : nullptr;
    }
};
inline SpellMgr spellMgr;
#define sSpellMgr (&spellMgr)

namespace DC::Combat::Shells
{
    // The generated catalogue of every class's skill and rune shells.
    struct Ability
    {
        uint32 id;
        char const* skill;
        char const* rune;
    };
    inline Ability const barbarian{81000, "Frenzy", ""}, wizard{83111, "Teleport", ""};
    inline Ability const* FindAbility(uint32 id)
    {
        if (id >= 81000 && id <= 81137)
            return &barbarian;
        return id == wizard.id ? &wizard : nullptr;
    }
} // namespace DC::Combat::Shells

namespace DC::Combat
{
    struct Shell
    {
        std::string skill;
    };
    inline std::optional<Shell> FindShell(uint32 spellId)
    {
        // The real map also holds every other class's shells (loaded from
        // Shells::Abilities), so it answers for the Wizard's id too.
        if (spellId < 81000 || spellId > 83349)
            return std::nullopt;
        return Shell{"test"};
    }
    inline uint32 ReducedCooldownMilliseconds(Player*, uint32, uint32 ms)
    {
        return ms;
    }

    // The cooldown the module installs, as the packet would carry it.
    inline std::map<uint32, uint32> sent;
    inline void SendSkillCooldown(Player*, uint32 spellId, uint32 ms)
    {
        sent[spellId] = ms;
    }

    double HandAttacksPerSecond(Player* player, std::uint32_t spellId, bool offhand);
    // The main-hand-only read the fix replaced; kept so a mutation that puts it
    // back still compiles and has to be caught by a failing case.
    inline double AttacksPerSecond(Player* player, std::uint32_t spellId = 0)
    {
        auto sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
        return sheet ? Primaries::AttackSpeed(player, spellId, sheet->attacksPerSecond) : 0;
    }
} // namespace DC::Combat

// dc_barbarian_primaries.cpp's cast bookkeeping, reduced to what Finish reads.
struct Spell
{
    bool triggered = false;
    bool IsTriggered() const
    {
        return triggered;
    }
};
struct Cast
{
    bool off = false;
};
struct Caster
{
    Player* player = nullptr;
    Player* ToPlayer() const
    {
        return player;
    }
};

#endif
