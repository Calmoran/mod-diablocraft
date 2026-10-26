/*
 * Doubles for diablocraft-barbarian-skills B (GitHub #44), Bash - Punish.
 *
 * What is REAL here, cut out of dc_barbarian_primaries.cpp by
 * scripts/tests/classes/test_barbarian_skills.py and not copied: the Buffs state, Alive,
 * PunishAura, PunishRow, Punish, Given, Effect and DamageBonus (Given asks ItemPowers::GrantsRune, doubled below: no power gives a rune here). The generated headers are
 * included as they are: dc_barbarian_primary_data.h (the Punish row: 4% a stack, 3
 * stacks, 5000 ms) and dc_spell_shells.h (the "Punish" helper record's id).
 *
 * What is a double and proves nothing about the core: the player, its aura
 * list, the aura's stack and timer fields and the clock. Nothing here runs
 * Aura::SetStackAmount, the aura's own expiry or the client's buff bar;
 * docs/test-diablocraft-barbarian-skills.md checks those live.
 */

#ifndef DC_BARBARIAN_PUNISH_SHIM_H
#define DC_BARBARIAN_PUNISH_SHIM_H

#include <algorithm>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

using int32 = std::int32_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using uint8 = std::uint8_t;

inline uint32 fakeNow = 100000;
inline uint32 getMSTime()
{
    return fakeNow;
}
inline uint32 getMSTimeDiff(uint32 then, uint32 now)
{
    return now - then;
}

class Player;
namespace DC::Combat::ItemPowers
{
inline bool GrantsRune(Player const*, std::string const&, std::string const&)
{
    return false;
}
}

struct ObjectGuid
{
    uint64 raw = 0;
    uint64 GetRawValue() const
    {
        return raw;
    }
};

struct Aura
{
    uint32 id = 0;
    uint8 stacks = 1;
    int32 duration = 0, maxDuration = 0;
    uint8 GetStackAmount() const
    {
        return stacks;
    }
    void SetStackAmount(uint8 amount)
    {
        stacks = amount;
    }
    void SetDuration(int32 value)
    {
        duration = value;
    }
    void SetMaxDuration(int32 value)
    {
        maxDuration = value;
    }
};

class Player
{
public:
    ObjectGuid guid{7};
    std::map<uint32, std::unique_ptr<Aura>> auras;
    int adds = 0;
    ObjectGuid GetGUID() const
    {
        return guid;
    }
    Aura* GetAura(uint32 id) const
    {
        auto found = auras.find(id);
        return found == auras.end() ? nullptr : found->second.get();
    }
    // Stock AddAura on a fresh aura: one stack; the caller sets the timer.
    Aura* AddAura(uint32 id, Player*)
    {
        ++adds;
        auto& aura = auras[id];
        aura = std::make_unique<Aura>();
        aura->id = id;
        return aura.get();
    }
    void Expire(uint32 id)
    {
        auras.erase(id);
    }
};

#endif
