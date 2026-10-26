/*
 * GitHub #77 / 10-paragon P3 and section 4: PoolFor must follow the player's
 * Hardcore mode, not always return Normal.
 *
 * Runs the module's own PoolFor, PoolName and Key, extracted from
 * src/paragon/dc_paragon.cpp by scripts/tests/paragon/test_paragon_pool.py and included
 * here as dc_paragon_pool_extract.h, against fixture players.
 * Hardcore::IsHardcore is doubled (pool_shim.h): this proves PoolFor's
 * wiring, not 11-hardcore's own answer, which tests/hardcore_realm already
 * covers. No Hardcore realm exists yet, so this is the offline proof the
 * brief asks for.
 */

#include "pool_shim.h"
#include "dc_paragon_pool_extract.h"

#include <cassert>
#include <cstdio>
#include <string>

int main()
{
    Player hardcorePlayer;
    hardcorePlayer.session.accountId = 101;
    Player normalPlayer;
    normalPlayer.session.accountId = 202;

    // A fixture Hardcore player reads and earns the Hardcore pool.
    Hardcore::testIsHardcore = true;
    assert(PoolFor(&hardcorePlayer) == Pool::Hardcore);
    AccountKey const hcKey = Key(&hardcorePlayer);
    assert(hcKey.first == 101 && hcKey.second == Pool::Hardcore);
    assert(std::string(PoolName(hcKey.second)) == "hardcore");

    // A fixture Normal player reads and earns the Normal pool.
    Hardcore::testIsHardcore = false;
    assert(PoolFor(&normalPlayer) == Pool::Normal);
    AccountKey const normalKey = Key(&normalPlayer);
    assert(normalKey.first == 202 && normalKey.second == Pool::Normal);
    assert(std::string(PoolName(normalKey.second)) == "normal");

    // Every dc_account_paragon read and write (ReadAccount, SaveProgress) is
    // keyed by exactly this pair, so the two pools never collide.
    assert(hcKey != normalKey);

    // An unchosen character (11-hardcore: IsHardcore is false until the first
    // login writes a mode) reads and earns Normal, same as today's default.
    Hardcore::testIsHardcore = false;
    assert(PoolFor(&hardcorePlayer) == Pool::Normal);

    std::printf("ok\n");
    return 0;
}
