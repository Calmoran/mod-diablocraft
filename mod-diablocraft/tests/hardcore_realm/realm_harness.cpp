/*
 * 11 H4 (2026-09-21): the realm writes the mode, nobody answers a prompt.
 *
 * Every case below runs the module's own `EnsureMode`, extracted from
 * src/hardcore/dc_hardcore.cpp by scripts/tests/hardcore/test_hardcore_realm.py and included
 * here as dc_hardcore_extract.h. The assertions are what the brief asks for:
 * the setting at 0 writes `normal`, at 1 writes `hardcore`, and a character
 * that already has a row is not touched by either.
 */

#include "realm_shim.h"
#include "dc_hardcore_extract.h"

#include <cstdio>

namespace
{
void Reset(bool hardcoreRealm)
{
    CharacterDatabase.rows.clear();
    CharacterDatabase.statements.clear();
    CharacterDatabase.accepts = true;
    configMgr.hardcore = hardcoreRealm;
    configMgr.reads = 0;
    modes.clear();
}

std::string Stored(std::uint32_t guid)
{
    auto found = CharacterDatabase.rows.find(guid);
    return found == CharacterDatabase.rows.end() ? std::string("<none>") : found->second;
}
}

int main()
{
    // 1. A Normal realm starts a new character normal, and says the kit may go.
    Reset(false);
    Player first{{11}};
    assert(EnsureMode(&first));
    assert(Stored(11) == "normal");
    assert(CharacterDatabase.Writes() == 1);
    assert(modes[11] == Mode::Normal);
    assert(configMgr.reads == 1);

    // 2. A Hardcore realm starts the same character hardcore. Same code, same
    //    call, one setting apart - which is the whole of H4 now.
    Reset(true);
    Player second{{12}};
    assert(EnsureMode(&second));
    assert(Stored(12) == "hardcore");
    assert(CharacterDatabase.Writes() == 1);
    assert(modes[12] == Mode::Hardcore);

    // 3. A character that already has a row is untouched, and the realm setting
    //    is not even read: the row outlives a config edit (H4 is permanent).
    Reset(false);
    CharacterDatabase.rows[13] = "hardcore";
    Player third{{13}};
    assert(EnsureMode(&third));
    assert(Stored(13) == "hardcore");
    assert(CharacterDatabase.Writes() == 0);
    assert(configMgr.reads == 0);
    assert(modes[13] == Mode::Hardcore);

    // 4. The same, reached through the cache rather than the table: a login that
    //    has already read the mode must not make the writer write again.
    Reset(true);
    CharacterDatabase.rows[14] = "normal";
    assert(Load(14) == Mode::Normal);
    unsigned const before = CharacterDatabase.Writes();
    Player fourth{{14}};
    assert(EnsureMode(&fourth));
    assert(CharacterDatabase.Writes() == before);
    assert(Stored(14) == "normal");

    // 5. A write that does not land refuses the kit rather than handing it to a
    //    character with no mode - what the unanswered prompt used to do.
    Reset(false);
    CharacterDatabase.accepts = false;
    Player fifth{{15}};
    assert(!EnsureMode(&fifth));
    assert(Stored(15) == "<none>");
    assert(modes[15] == Mode::Unchosen);

    // 6. No player, no row.
    Reset(false);
    assert(!EnsureMode(nullptr));
    assert(CharacterDatabase.Writes() == 0);

    // 7. The setting is read at the moment of writing, not cached: the same
    //    binary writes both modes when the realm is restarted the other way.
    Reset(false);
    Player sixth{{16}};
    assert(EnsureMode(&sixth));
    assert(Stored(16) == "normal");
    configMgr.hardcore = true;
    Player seventh{{17}};
    assert(EnsureMode(&seventh));
    assert(Stored(17) == "hardcore");
    assert(Stored(16) == "normal");

    std::printf("ok\n");
    return 0;
}
