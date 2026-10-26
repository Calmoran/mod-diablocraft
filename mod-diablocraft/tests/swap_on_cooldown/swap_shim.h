/*
 * Doubles for the core types DC::Classes::SetSlot touches (diablocraft-7sh0: a skill
 * on cooldown cannot be changed).
 *
 * Nothing of the module is restated here. scripts/tests/classes/test_swap_on_cooldown.py cuts the
 * module's own SetSlot, its catalogue lookups (ShellFor, Entry, Key, LabelFor,
 * SkillUnlocked ...) and the catalogue's own data declarations out of
 * src/classes/dc_classes.cpp and compiles them against these doubles; the harness
 * fills the catalogue the way ClassWorld::OnStartup does, from the rows the
 * generator wrote. What is doubled is only what lives in the core:
 *
 *   Player             combat state, the map, the level, and the cooldown map that
 *                      Player::GetSpellCooldownDelay answers from (spell id -> ms left)
 *   CharacterDatabase  a transaction that records its statements, and a commit that
 *                      applies the two dc_character_skillbar statements SetSlot writes
 *                      to a table the harness reads back
 */

#ifndef DC_SWAP_SHIM_H
#define DC_SWAP_SHIM_H

#include <algorithm>
#include <cstdint>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

struct ObjectGuid
{
    uint64 raw = 0;

    uint64 GetRawValue() const
    {
        return raw;
    }
};

struct Map
{
    bool instanceable = false;

    bool Instanceable() const
    {
        return instanceable;
    }
};

class Player
{
public:
    unsigned wowClass = 8; // Mage, the Wizard's WoW class; the Barbarian's Warrior is 1
    unsigned level = 100;
    bool inCombat = false;
    bool onMap = true;
    Map map;
    uint64 guid = 4242;
    // Player::GetSpellCooldownDelay at the pin answers from one map, per spell id:
    // the milliseconds left, 0 when there is no entry or it has run out.
    std::map<uint32, uint32> cooldownLeft;

    unsigned getClass() const
    {
        return wowClass;
    }

    unsigned GetLevel() const
    {
        return level;
    }

    bool IsInCombat() const
    {
        return inCombat;
    }

    Map* GetMap()
    {
        return onMap ? &map : nullptr;
    }

    ObjectGuid GetGUID() const
    {
        return ObjectGuid{guid};
    }

    uint32 GetSpellCooldownDelay(uint32 spellId) const
    {
        auto found = cooldownLeft.find(spellId);
        return found == cooldownLeft.end() ? 0 : found->second;
    }
};

struct Transaction
{
    struct Statement
    {
        std::string format;
        std::vector<std::string> args;
    };

    std::vector<Statement> statements;

    // The core's Append is fmt-based ({} placeholders); this keeps the format and the
    // arguments apart so the commit can read them back by position.
    template<typename... Args>
    void Append(char const* format, Args const&... args)
    {
        Statement statement{format, {}};
        (statement.args.push_back(Text(args)), ...);
        statements.push_back(std::move(statement));
    }

private:
    template<typename T>
    static std::string Text(T const& value)
    {
        std::ostringstream out;
        out << value;
        return out.str();
    }
};

using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;

struct Commit
{
    std::future<bool> m_future;
};

struct Database
{
    unsigned commits = 0;

    void EscapeString(std::string& text) const
    {
        std::string escaped;
        for (char c : text)
            escaped += c == '\'' ? std::string("\\'") : std::string(1, c);
        text = escaped;
    }

    CharacterDatabaseTransaction BeginTransaction() const
    {
        return std::make_shared<Transaction>();
    }

    // Defined in swap_harness.cpp, where the bar's table is.
    Commit AsyncCommitTransaction(CharacterDatabaseTransaction const& transaction);
};

inline Database CharacterDatabase;

// The Greater Rift answer SetSlot asks (rifts/dc_rifts.h): no Greater Rift here, so an instance refuses.
namespace DC::Rifts
{
    inline bool GreaterRiftGuardianDead(Player const*)
    {
        return false;
    }
}

// The module's own header: the public surface (Slot, SetSlot, Bar ...) as production declares it.
#include "classes/dc_classes.h"

#endif // DC_SWAP_SHIM_H
