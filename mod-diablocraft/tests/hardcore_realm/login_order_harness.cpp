/*
 * The login, in the order the core runs it (11 H4 / 08 §5, 2026-09-21).
 *
 * Two pieces of the module are the real thing here, compiled from their own
 * files by scripts/tests/hardcore/test_hardcore_realm.py: `EnsureMode` (dc_hardcore.cpp),
 * which writes the mode, and `StartOwed` (dc_world.cpp), which decides whether
 * a login still owes the character its start. Everything else below is a model
 * and is named as one.
 *
 * What the model is, exactly, so no one reads more into a pass than is there:
 *
 *   * `Login` transcribes the core's order from the pin - every OnPlayerLogin
 *     hook at CharacterHandler.cpp:1136, AT_LOGIN_FIRST cleared at :1139, then
 *     OnPlayerFirstLogin at :1141 - and the module's two hooks inside it. The
 *     order of the module's own OnPlayerLogin hooks against each other is NOT
 *     asserted anywhere: every case runs both ways round and has to give the
 *     same answer, which is the property the fix actually relies on.
 *
 *   * `Economy` is a model of four behaviours of DC::AccountEconomy that the
 *     owner review cited, not of the economy: a resolution taken while the mode
 *     is Unchosen names the contribution `pending` (dc_account_economy.cpp:866-
 *     867), claims nothing (:500-501), leaves the money mirror at 0 and skips
 *     FinalizeLoad (:905-907); a resolution under a real mode claims the
 *     character's pending contribution exactly once into that mode's account
 *     pool. The ledger itself is untouched by this task and is not modelled.
 *
 *   * The kit is not modelled at all. `Start` here runs the two gates and then
 *     records that the start completed; that the production `Start` has those
 *     gates in that order, before it gives the character anything, is a source
 *     assertion in the Python suite.
 */

#include "realm_shim.h"
#include "dc_hardcore_extract.h"
#include "dc_world_extract.h"

#include <cstdio>
#include <map>
#include <utility>

namespace
{
// --- a model of the four cited account-economy behaviours ------------------
struct Economy
{
    struct Contribution
    {
        std::uint32_t account = 0;
        std::string mode = "pending";
        std::uint64_t copper = 0;
        bool credited = false;
    };

    bool enabled = true;
    bool healthy = true;
    std::map<std::uint32_t, Contribution> migration;
    std::map<std::pair<std::uint32_t, bool>, std::uint64_t> pool;
    std::uint64_t mirror = 0;
    bool finalized = false;
    unsigned claims = 0;
    unsigned resolutions = 0;

    bool Resolve(Player const& player)
    {
        if (!enabled)
            return true;
        ++resolutions;
        if (!healthy)
            return false;
        Mode const mode = Load(player.guid.counter);
        std::string const name = mode == Mode::Unchosen ? "pending"
                               : mode == Mode::Hardcore ? "hardcore" : "normal";
        auto found = migration.find(player.guid.counter);
        if (found == migration.end())
            found = migration.emplace(player.guid.counter,
                                      Contribution{player.account, name, player.money, false}).first;
        else if (found->second.account != player.account ||
                 (found->second.mode != "pending" && found->second.mode != name))
            return false;
        if (name == "pending")
        {
            // ClaimPending returns without crediting; the mirror stays 0 and
            // FinalizeLoad never runs.
            mirror = 0;
            return true;
        }
        auto& row = found->second;
        if (!row.credited)
        {
            pool[{player.account, name == "hardcore"}] += row.copper;
            row.credited = true;
            row.mode = name;
            ++claims;
        }
        mirror = pool[{player.account, name == "hardcore"}];
        finalized = true;
        return true;
    }
};

Economy economy;
// dc_character_start: guid -> complete.
std::map<std::uint32_t, bool> startRows;
unsigned starts = 0;

QueryResult StartRow(std::uint32_t guid)
{
    auto found = startRows.find(guid);
    if (found == startRows.end())
        return QueryResult();
    return std::make_shared<Row>(Row{{Field{found->second ? "1" : "0"}}});
}

// DC::World::Start, gates only - see the header comment.
void Start(Player& player)
{
    ++starts;
    if (!EnsureMode(&player))
        return;
    if (!economy.Resolve(player))
        return;
    startRows[player.guid.counter] = true;
}

// CharacterHandler::HandlePlayerLogin, from the pin.
void Login(Player& player, bool economyHookFirst)
{
    auto ours = [&] {
        if (StartOwed(&player, StartRow(player.guid.counter)))
            Start(player);
    };
    if (economyHookFirst)
    {
        economy.Resolve(player);            // AccountPlayer::OnPlayerLogin
        ours();                             // HubPlayer::OnPlayerLogin
    }
    else
    {
        ours();
        economy.Resolve(player);
    }
    if (player.HasAtLoginFlag(AT_LOGIN_FIRST))
    {
        player.atLogin &= ~unsigned(AT_LOGIN_FIRST);
        Start(player);                      // HubPlayer::OnPlayerFirstLogin
    }
}

void Reset(bool hardcoreRealm)
{
    CharacterDatabase.rows.clear();
    CharacterDatabase.statements.clear();
    CharacterDatabase.accepts = true;
    configMgr.hardcore = hardcoreRealm;
    configMgr.reads = 0;
    modes.clear();
    economy = Economy();
    startRows.clear();
    starts = 0;
}

bool Started(std::uint32_t guid)
{
    auto found = startRows.find(guid);
    return found != startRows.end() && found->second;
}

std::string Stored(std::uint32_t guid)
{
    auto found = CharacterDatabase.rows.find(guid);
    return found == CharacterDatabase.rows.end() ? std::string("<none>") : found->second;
}

// Every case runs both ways round: the module must not depend on which of the
// two OnPlayerLogin hooks the core reaches first.
void BothOrders(void (*body)(bool))
{
    body(true);
    body(false);
}

// 1. A Normal realm: the mode is written, the account is resolved AFTER it, and
//    the character's own money is credited exactly once.
void NewCharacterOnANormalRealm(bool economyFirst)
{
    Reset(false);
    Player player{{21}, 7, 2500};
    Login(player, economyFirst);
    assert(Stored(21) == "normal");
    assert(Started(21));
    assert(economy.claims == 1);
    assert(economy.mirror == 2500);
    assert((economy.pool[{7, false}] == 2500));
    assert(economy.finalized);
    // The start ran once, from the first-login hook: StartOwed held the other
    // one back while AT_LOGIN_FIRST was still set.
    assert(starts == 1);
}

// 2. A Hardcore realm credits the hardcore pool and leaves the normal one alone.
void NewCharacterOnAHardcoreRealm(bool economyFirst)
{
    Reset(true);
    Player player{{22}, 7, 2500};
    Login(player, economyFirst);
    assert(Stored(22) == "hardcore");
    assert(Started(22));
    assert(economy.claims == 1);
    assert((economy.pool[{7, true}] == 2500));
    assert(economy.pool.find({7, false}) == economy.pool.end());
}

// 3. An account that already has a balance keeps it and gains the new
//    character's contribution; the mirror is the shared balance, not the seed.
void ExistingSharedBalance(bool economyFirst)
{
    Reset(false);
    economy.pool[{7, false}] = 100000;
    Player player{{23}, 7, 2500};
    Login(player, economyFirst);
    assert((economy.pool[{7, false}] == 102500));
    assert(economy.mirror == 102500);
    assert(economy.claims == 1);
}

// 4. Exactly once, however many logins: a relogin resolves again and credits
//    nothing more.
void PendingCreditedExactlyOnce(bool economyFirst)
{
    Reset(false);
    Player player{{24}, 7, 2500};
    Login(player, economyFirst);
    Login(player, economyFirst);
    Login(player, economyFirst);
    assert(economy.claims == 1);
    assert((economy.pool[{7, false}] == 2500));
    assert(economy.resolutions > 3);
    // Later logins sweep bags; they do not start the character again.
    assert(starts == 1);
}

// 5. A resolution that fails takes the whole start with it, and the next login
//    recovers it - the mode is already durable, so only the rest is retried.
void FailedResolutionRecoversNextLogin(bool economyFirst)
{
    Reset(false);
    economy.healthy = false;
    Player player{{25}, 7, 2500};
    Login(player, economyFirst);
    assert(Stored(25) == "normal");     // the mode was written before the failure
    assert(!Started(25));               // and nothing was granted
    assert(startRows.find(25) == startRows.end());
    assert(economy.claims == 0);
    assert(!player.HasAtLoginFlag(AT_LOGIN_FIRST));  // the core consumed it

    economy.healthy = true;
    unsigned const writes = CharacterDatabase.Writes();
    Login(player, economyFirst);
    assert(Started(25));
    assert(economy.claims == 1);
    assert((economy.pool[{7, false}] == 2500));
    assert(CharacterDatabase.Writes() == writes);    // no second mode row
    assert(Stored(25) == "normal");
}

// 6. The same for a mode write that does not land: nothing is granted, and the
//    next login writes the mode and starts the character.
void FailedModeWriteRecoversNextLogin(bool economyFirst)
{
    Reset(false);
    CharacterDatabase.accepts = false;
    Player player{{26}, 7, 2500};
    Login(player, economyFirst);
    assert(Stored(26) == "<none>");
    assert(!Started(26));
    assert(economy.claims == 0);
    assert(!player.HasAtLoginFlag(AT_LOGIN_FIRST));

    CharacterDatabase.accepts = true;
    Login(player, economyFirst);
    assert(Stored(26) == "normal");
    assert(Started(26));
    assert(economy.claims == 1);
}

// 7. A character that already has a mode keeps it on a realm set the other way,
//    and its credit follows the mode it has, not the realm it logged into.
void ExistingModeIsImmutable(bool economyFirst)
{
    Reset(false);
    CharacterDatabase.rows[27] = "hardcore";
    Player player{{27}, 7, 2500};
    player.atLogin = 0;                 // not a first login; the row is old
    Login(player, economyFirst);
    assert(Stored(27) == "hardcore");
    assert(configMgr.reads == 0);       // the realm setting was never consulted
    assert(Started(27));
    assert((economy.pool[{7, true}] == 2500));
    assert(economy.pool.find({7, false}) == economy.pool.end());
}

// 8. A completed character is not started again and is not re-credited.
void CompletedStartIsLeftAlone(bool economyFirst)
{
    Reset(false);
    Player player{{28}, 7, 2500};
    Login(player, economyFirst);
    unsigned const before = starts;
    Login(player, economyFirst);
    assert(starts == before);
    assert(economy.claims == 1);
}
}

int main()
{
    BothOrders(NewCharacterOnANormalRealm);
    BothOrders(NewCharacterOnAHardcoreRealm);
    BothOrders(ExistingSharedBalance);
    BothOrders(PendingCreditedExactlyOnce);
    BothOrders(FailedResolutionRecoversNextLogin);
    BothOrders(FailedModeWriteRecoversNextLogin);
    BothOrders(ExistingModeIsImmutable);
    BothOrders(CompletedStartIsLeftAlone);
    std::printf("ok\n");
    return 0;
}
