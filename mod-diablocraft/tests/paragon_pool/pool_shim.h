/*
 * Doubles for PoolFor's one dependency, plus the core types its extracted
 * code touches (10-paragon P3 / GitHub #77).
 *
 * Pool and AccountKey are the header's and the module's own, repeated rather
 * than included: dc_paragon.h and dc_paragon.cpp drag in Player and the whole
 * core with them (same reasoning as tests/hardcore_realm/realm_shim.h).
 *
 * Hardcore::IsHardcore is doubled, not extracted: 11-hardcore's own answer is
 * proven in tests/hardcore_realm, so this suite only has to prove that
 * PoolFor, and the account key every read and write is keyed by, follow
 * whatever that answer is.
 */

#ifndef DC_PARAGON_POOL_SHIM_H
#define DC_PARAGON_POOL_SHIM_H

#include <cstdint>
#include <utility>

using uint32 = std::uint32_t;

enum class Pool
{
    Normal,
    Hardcore
};
using AccountKey = std::pair<uint32, Pool>;

struct Session
{
    uint32 accountId = 0;
    uint32 GetAccountId() const
    {
        return accountId;
    }
};

struct Player
{
    Session session;
    Session* GetSession()
    {
        return &session;
    }
};

namespace Hardcore
{
    inline bool testIsHardcore = false;
    inline bool IsHardcore(Player const*)
    {
        return testIsHardcore;
    }
} // namespace Hardcore

#endif // DC_PARAGON_POOL_SHIM_H
