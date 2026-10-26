"""diablocraft-7f36: Paragon XP without the stall, compiled from production.

The harness cuts the save machinery (Save, StartSave, Settle, FlushNow, SaveTick, ApplyProgress, AddXP), the account
load, the player hooks OnPlayerUpdate and OnPlayerLogout, the world hooks OnUpdate and OnShutdown and GrantXP and EnsureStartingLevel out of
src/paragon/dc_paragon.cpp and runs them against a database double that keeps a table, queues commits on a worker
(optionally a slow one, on a real thread) and counts every call. Every rule is then removed one at a time from the
production text and the run must go red: a test that cannot fail proves nothing.

What it does not cover: Hooks::Kill itself (group walk, party bonus; pinned as text to hold no database, snapshot or chat
call and to end in AddXP), the real database, the addon.
"""
import unittest
from pathlib import Path
import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import host_cmake

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "mod-diablocraft/src/paragon"
MAIN = ROOT / "mod-diablocraft/tests/paragon_save/main.cpp"
PARAGON = (SRC / "dc_paragon.cpp").read_text(encoding="utf-8")


def definition(source, marker):
    """The full brace-balanced definition that starts at `marker`, as it stands in the file."""
    start = source.index(marker)
    end, depth = source.index("{", start) + 1, 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end].replace(" override", "")


def line(source, pattern):
    return re.search(pattern, source, re.M).group(0)


def mutate(source, old, new):
    assert source.count(old) == 1, f"mutation anchor not unique: {old!r}"
    return source.replace(old, new)


class Cut:
    """The production text the harness compiles, in four pieces."""

    def __init__(self, source=PARAGON):
        a = source.index("using Points = std::array<unsigned, 16>;")
        b = source.index("std::array<Rule, 16> rules;")
        self.types = source[a:b]
        self.basics = "\n".join([
            line(source, r"^char const\* PoolName\(Pool pool\).*$"),
            line(source, r"^AccountKey Key\(Player\* player\).*$"),
            line(source, r"^uint32 Guid\(Player\* player\).*$"),
            definition(source, "Progress ReadAccount("),
            definition(source, "Progress& Account("),
        ])
        a = source.index("// Paragon XP lives in `accounts`")
        b = source.index("class World final : public WorldScript")
        region = source[a:b]
        clock = definition(region, "std::uint64_t ClockMs()")
        self.region = region.replace(clock, "std::uint64_t ClockMs() { return clockNow; }")
        self.hooks = "\n".join(definition(source, marker) for marker in (
            "void OnPlayerUpdate(Player* player, uint32)", "void OnPlayerLogout(Player* player)"))
        self.world = "\n".join(definition(source, marker) for marker in ("void OnUpdate(uint32)", "void OnShutdown()"))
        self.grant = definition(source, "bool GrantXP(Player* player")
        self.ensure = definition(source, "bool EnsureStartingLevel(Player* player")


PRELUDE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <future>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <utility>
#include <vector>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;

template <class T> void FmtOne(std::ostringstream& out, T const& v) { out << v; }
inline std::string Fmt(char const* f) { return f; }
template <class A, class... R> std::string Fmt(char const* f, A const& a, R const&... rest)
{
    std::string text(f); std::size_t at = text.find("{}");
    std::ostringstream one; FmtOne(one, a);
    return text.substr(0, at) + one.str() + Fmt(text.substr(at + 2).c_str(), rest...);
}
std::vector<std::string> errors, said;
#define LOG_ERROR(channel, ...) (errors.push_back(Fmt(__VA_ARGS__)))
#define LOG_INFO(...) ((void)0)
std::uint64_t clockNow = 100000;

// The database: a table, a worker that applies commits (at once, or after delayMs on a real thread), and a count of every call.
struct Field { std::string s; template <class T> T Get() const { return T(std::stoull(s)); } };
struct Row { std::vector<std::string> v; Field operator[](int i) const { return {v[i]}; } };
struct Tx { std::vector<std::string> statements; template <class... A> void Append(char const* f, A const&... a) { statements.push_back(Fmt(f, a...)); } };
using CharacterDatabaseTransaction = std::shared_ptr<Tx>;
struct Callback { std::future<bool> m_future; };
struct Database {
    std::mutex lock;
    std::map<std::pair<uint32, std::string>, std::pair<uint32, uint64>> table;
    int queries = 0, direct = 0, async = 0, delayMs = 0;
    bool failNext = false;
    std::vector<std::thread> threads;
    ~Database() { for (auto& t : threads) t.join(); }
    void reset() { queries = direct = async = 0; }
    void apply(std::string const& sql) {
        unsigned level, account; unsigned long long xp; char pool[16];
        std::lock_guard<std::mutex> hold(lock);
        if (std::sscanf(sql.c_str(), "UPDATE dc_account_paragon SET level=%u,xp=%llu WHERE account_id=%u AND pool='%15[a-z]'", &level, &xp, &account, pool) == 4)
            table[{account, pool}] = {level, xp};
        else if (std::sscanf(sql.c_str(), "INSERT IGNORE INTO dc_account_paragon(account_id,pool) VALUES(%u,'%15[a-z]')", &account, pool) == 2)
            table.emplace(std::make_pair(account, std::string(pool)), std::make_pair(0u, 0ull));
        else assert(!"an SQL statement the double does not know");
    }
    std::pair<uint32, uint64> at(uint32 account, char const* pool) { std::lock_guard<std::mutex> hold(lock); return table[{account, pool}]; }
    template <class... A> std::shared_ptr<Row> Query(char const* f, A const&... a) {
        ++queries;
        unsigned account; char pool[16];
        std::string sql = Fmt(f, a...);
        assert(std::sscanf(sql.c_str(), "SELECT level,xp FROM dc_account_paragon WHERE account_id=%u AND pool='%15[a-z]'", &account, pool) == 2);
        std::lock_guard<std::mutex> hold(lock);
        auto found = table.find({account, pool});
        if (found == table.end()) return nullptr;
        return std::make_shared<Row>(Row{{std::to_string(found->second.first), std::to_string(found->second.second)}});
    }
    template <class... A> void DirectExecute(char const* f, A const&... a) { ++direct; apply(Fmt(f, a...)); }
    CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Tx>(); }
    Callback AsyncCommitTransaction(CharacterDatabaseTransaction tx) {
        ++async;
        auto promise = std::make_shared<std::promise<bool>>();
        Callback callback{promise->get_future()};
        bool const fail = failNext; failNext = false;
        int const delay = delayMs;
        auto work = [this, tx, promise, fail, delay] {
            if (delay) std::this_thread::sleep_for(std::chrono::milliseconds(delay));
            if (!fail) for (auto const& sql : tx->statements) apply(sql);
            promise->set_value(!fail);
        };
        if (delay) threads.emplace_back(work); else work();
        return callback;
    }
} CharacterDatabase;
using QueryResult = std::shared_ptr<Row>;

namespace DC::Tunables { std::map<std::string, double> rows; double Get(std::string const& c, std::string const& n) { auto f = rows.find(c + "/" + n); return f == rows.end() ? 0 : f->second; } }
struct Session { uint32 account = 7; uint32 GetAccountId() const { return account; } };
struct ObjectGuid { uint32 id; uint32 GetCounter() const { return id; } };
struct Player {
    uint32 guid = 5; Session session; unsigned level = 70;
    Session* GetSession() { return &session; }
    ObjectGuid GetGUID() const { return {guid}; }
    unsigned GetLevel() const { return level; }
};
struct ChatHandler {
    explicit ChatHandler(Session*) {}
    template <class... A> void PSendSysMessage(char const* f, A const&... a) { said.push_back(Fmt(f, a...)); }
};
'''

NAMESPACE = r'''
#include "dc_paragon_math.h"
namespace DC::Hardcore { enum class Mode { Unchosen, Normal, Hardcore }; Mode ModeOf(Player const*) { return Mode::Normal; } }
namespace DC::Paragon {
enum class Pool { Normal, Hardcore };
Pool PoolFor(Player const*) { return Pool::Normal; }
namespace {
std::vector<XP> xpTable;
bool ready = true;
struct Character;
Character& State(Player* player);
void Check(Player*) { }
namespace Stats { bool ReplaceParagon(Player*, std::vector<int> const&) { return true; } }
'''


def program(cut, body, grant=None):
    code = PRELUDE + NAMESPACE + cut.types + "\n"
    code += "std::vector<int> Contributions(Player const*, Points const&) { return {}; }\n"
    code += "int snapshots = 0, headers = 0, bars = 0; Progress lastHeader;\n"
    code += "void PublishBar(Player*, XP, XP) { ++bars; }\n"
    code += "void SendHeader(Player*, Character const&, Progress const& account, bool) { ++headers; lastHeader = account; }\n"
    code += cut.basics + "\n" + cut.region + "\n"
    code += "Character& State(Player* player) { return characters.at(Guid(player)); }\n"
    code += "void Snapshot(Player* player, bool, bool) { ++snapshots; State(player).progressDirty = false; }\n"
    code += "struct Hooks {\n" + cut.hooks + "\n};\nstruct WorldHooks {\n" + cut.world + "\n};\n}\n"
    code += (grant if grant is not None else cut.grant) + "\n" + cut.ensure + "\n}\n"
    code += r'''
using namespace DC::Paragon;
Hooks hooks; WorldHooks world;
void login(Player& p) {
    std::lock_guard<std::mutex> hold(mutex);
    auto key = Key(&p); Account(key);
    characters[Guid(&p)] = Character{key};
}
void kill(Player& p, XP amount) { std::lock_guard<std::mutex> hold(mutex); AddXP(&p, amount); }
void tick(std::uint64_t at) { clockNow = at; world.OnUpdate(0); }
auto stored = [](uint32 account = 7) { return CharacterDatabase.at(account, "normal"); };
int main() {
    for (int i = 0; i < 800; ++i) xpTable.push_back(1000);          // every level is 1000 XP
    DC::Tunables::rows["paragon/paragon_save_interval_ms"] = 10000;
    CharacterDatabase.table[{7, "normal"}] = {0, 0};
    Player p;
''' + body + "\n    return 0;\n}\n"
    return code


def run(code):
    binary = harness_env.build([MAIN], flags=["-std=gnu++17", host_cmake.undebug(), "-pthread"], files={"program.h": code}, includes=[SRC])
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout + ran.stderr


def both(test, body, old, new, which="region"):
    """Green on production; red on the production text with one rule taken out."""
    ok, out = run(program(Cut(), body))
    test.assertTrue(ok, out)
    mutated = PARAGON
    anchor = old
    assert PARAGON.count(anchor) == 1, f"mutation anchor not unique: {anchor!r}"
    mutated = PARAGON.replace(old, new)
    ok, out = run(program(Cut(mutated), body))
    test.assertFalse(ok, "mutation survived: " + new)


class Kill(unittest.TestCase):
    def test_a_kill_touches_no_database_and_a_hundred_make_one_write_in_the_interval(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    for (int i = 0; i < 100; ++i) kill(p, 7);                          // no level-up: 700 of the 1000
    assert(CharacterDatabase.queries == 0 && CharacterDatabase.direct == 0 && CharacterDatabase.async == 0);
    assert(accounts.at({7, Pool::Normal}).xp == 700 && stored().second == 0);   // memory is ahead of the database
    tick(100000);                                                       // the next server tick starts the one write
    assert(CharacterDatabase.async == 1 && stored().second == 700);
    for (int i = 0; i < 100; ++i) kill(p, 1);
    tick(105000); tick(109999);                                         // inside the interval: nothing more
    assert(CharacterDatabase.async == 1 && stored().second == 700);
    tick(110000);                                                       // and one when it has passed
    assert(CharacterDatabase.async == 2 && stored().second == 800);
    assert(CharacterDatabase.queries == 0 && CharacterDatabase.direct == 0);   // never a read-back, never a wait
''', "(it->second.urgent || now - it->second.lastMs >= interval)", "(it->second.urgent || true)")

    def test_a_kill_writes_nothing_by_itself(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    kill(p, 5);
    assert(CharacterDatabase.async == 0 && CharacterDatabase.direct == 0);
''', "    if (writeNow || updated.level != previous.level)\n        StartSave(state.account);", "    StartSave(state.account);")

    def test_the_kill_path_holds_no_database_snapshot_or_chat_call(self):
        kill = definition(PARAGON, "static void Kill(Creature* victim)")
        kill = kill.split("catch")[0]     # the catch reports an error, which is not a kill's award
        for forbidden in ("CharacterDatabase", "DirectExecute", "Query(", "Snapshot(", "SendSysMessage", "PSendSysMessage", "SaveProgress", "StartSave"):
            self.assertNotIn(forbidden, kill)
        self.assertIn("AddXP(member,SheetAward(member,amount,true,bonus));", kill)
        self.assertNotIn("SaveProgress", PARAGON)
        self.assertNotIn("Paragon +{} XP", PARAGON)


class Writes(unittest.TestCase):
    def test_a_level_up_is_written_at_once_not_at_the_interval(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    kill(p, 1500);                                                      // crosses level 1 (1000): level 1, 500 in
    assert(CharacterDatabase.async == 1 && stored().first == 1 && stored().second == 500);   // no tick needed
''', "    if (writeNow || updated.level != previous.level)\n        StartSave(state.account);", "    if (writeNow)\n        StartSave(state.account);")

    def test_a_level_up_during_a_write_in_flight_waits_its_turn_and_lands_after(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    CharacterDatabase.delayMs = 60;                                     // a slow database
    kill(p, 1500);                                                      // write 1: level 1, 500
    kill(p, 1000);                                                      // level 2, 500: owed, but one write at a time
    assert(CharacterDatabase.async == 1);
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    tick(100001);                                                       // takes the first, starts the second at once (urgent)
    assert(CharacterDatabase.async == 2);
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    tick(100002);
    assert(stored().first == 2 && stored().second == 500);              // the later state wins: they never land out of order
''', "|| !found->second.dirty || found->second.flying)", "|| !found->second.dirty)")

    def test_a_rifts_closing_xp_is_written_at_once(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    std::string error;
    assert(GrantXP(&p, 300, error) && error.empty());
    assert(CharacterDatabase.async == 1 && stored().second == 300);     // not waiting for a tick or the interval
    assert(GrantXP(&p, 0, error) && CharacterDatabase.async == 1);       // nothing owed, nothing written
''', "try { AddXP(player, amount, true); return true; }", "try { AddXP(player, amount); return true; }")

    def test_a_failed_write_is_logged_and_tried_again_never_lost(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    CharacterDatabase.failNext = true;
    kill(p, 1500);                                                      // the urgent write fails
    tick(100010);                                                       // the tick takes the failure
    assert(errors.size() == 1 && errors[0].find("could not be saved") != std::string::npos);
    assert(stored().first == 0 && accounts.at({7, Pool::Normal}).level == 1);   // still only in memory
    assert(CharacterDatabase.async == 1);
    tick(100011);                                                       // owed again, but the interval since the last try has not passed
    assert(CharacterDatabase.async == 1);
    tick(120000);                                                       // now it has
    assert(CharacterDatabase.async == 2 && stored().first == 1 && stored().second == 500);
    assert(errors.size() == 1);
''', "        save.dirty = true;\n        LOG_ERROR(", "        LOG_ERROR(")

    def test_a_failed_write_is_logged(self):
        both(self, '''
    login(p); CharacterDatabase.failNext = true;
    kill(p, 1500); tick(100010);
    assert(errors.size() == 1 && errors[0].find("account 7") != std::string::npos);
''', '        LOG_ERROR("server", "[DC paragon] Paragon XP could not be saved', '        LOG_INFO("server", "[DC paragon] Paragon XP could not be saved')


class LogoutAndShutdown(unittest.TestCase):
    def test_the_last_logout_writes_and_waits_so_a_relog_reads_the_last_xp(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    CharacterDatabase.delayMs = 40;                                     // slow: only a wait makes this pass
    for (int i = 0; i < 50; ++i) kill(p, 9);                            // 450, in memory only
    hooks.OnPlayerLogout(&p);
    assert(stored().second == 450);                                     // written AND landed before the logout returned
    assert(accounts.empty() && saves.empty() && characters.empty());
    Player again; login(again);                                         // the relog: reads the database
    assert(accounts.at({7, Pool::Normal}).xp == 450);
''', "if (FlushNow(key)) { accounts.erase(key); saves.erase(key); }", "if (StartSave(key) || true) { accounts.erase(key); saves.erase(key); }")

    def test_the_logout_flush_waits_for_a_write_in_flight_then_writes_the_rest(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    CharacterDatabase.delayMs = 40;
    kill(p, 1100);                                                      // write 1 in flight: level 1, 100
    kill(p, 50);                                                        // 150, owed
    hooks.OnPlayerLogout(&p);
    assert(stored().first == 1 && stored().second == 150);
''', "    Settle(key, found->second, true);\n    if (StartSave(key))", "    if (StartSave(key))")

    def test_a_logout_that_cannot_write_keeps_the_pool_and_the_tick_finishes_it(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    kill(p, 450); CharacterDatabase.failNext = true;
    hooks.OnPlayerLogout(&p);                                           // the write fails
    assert(errors.size() == 1 && stored().second == 0);
    assert(accounts.size() == 1 && accounts.at({7, Pool::Normal}).xp == 450 && saves.size() == 1);   // still owed, still in memory
    tick(110000);                                                       // the tick tries again
    assert(CharacterDatabase.async == 2 && stored().second == 450);
    tick(110001);                                                       // and forgets it once written
    assert(accounts.empty() && saves.empty());
''', "else saves[key].orphan = true;", "else saves.erase(key), accounts.erase(key);")

    def test_shutdown_writes_what_is_owed(self):
        both(self, '''
    login(p); CharacterDatabase.reset();
    kill(p, 450);
    world.OnShutdown();
    assert(stored().second == 450);
''', "        for (auto& entry : saves)\n            FlushNow(entry.first);", "        for (auto& entry : saves)\n            (void)entry;")

    def test_an_orphan_pool_is_kept_while_a_character_of_the_account_is_online_again(self):
        both(self, '''
    login(p); kill(p, 450);
    CharacterDatabase.failNext = true;
    hooks.OnPlayerLogout(&p);                                           // owed, orphan
    login(p);                                                           // back online: the pool is in memory, orphan stays set
    CharacterDatabase.reset();
    tick(120000); tick(120001);                                         // written and settled
    assert(stored().second == 450);
    assert(accounts.count({7, Pool::Normal}) == 1 && saves.count({7, Pool::Normal}) == 1);   // not forgotten while online
    kill(p, 1);                                                         // so the kill path reads nothing
    assert(CharacterDatabase.queries == 0 && CharacterDatabase.direct == 0);
    hooks.OnPlayerLogout(&p);
    assert(stored().second == 451 && accounts.empty() && saves.empty());
''', "\n            && std::none_of(characters.begin(), characters.end(), [&](auto const& entry) { return entry.second.account == it->first; }))", ")")

    def test_shutdown_comment_says_it_runs_before_the_kick(self):
        self.assertNotIn("Every player was logged out and saved before this", PARAGON)
        self.assertIn("Runs before KickAll (Main.cpp)", PARAGON)

    def test_another_character_of_the_account_keeps_the_pool_in_memory(self):
        both(self, '''
    login(p); Player second; second.guid = 6; login(second); CharacterDatabase.reset();
    kill(p, 450);
    hooks.OnPlayerLogout(&p);                                           // the account is still online: nothing waited for
    assert(CharacterDatabase.async == 0 && accounts.count({7, Pool::Normal}) == 1);
    assert(accounts.at({7, Pool::Normal}).xp == 450);
    hooks.OnPlayerLogout(&second);
    assert(stored().second == 450 && accounts.empty());
''', "if (std::none_of(characters.begin(),characters.end(),[&](auto const& entry){return entry.second.account==key;}))\n        {\n            // The last", "if (true)\n        {\n            // The last")

    def test_a_new_character_settles_a_failed_logout_write_before_the_pool_is_forgotten(self):
        both(self, '''
    login(p); kill(p, 1500); kill(p, 100);                              // level 1 written at once; 600 owed
    CharacterDatabase.failNext = true;
    hooks.OnPlayerLogout(&p);                                           // the logout write fails: owed, orphan
    assert(stored().second == 500 && saves.at({7, Pool::Normal}).orphan);
    Player fresh; std::string error;
    assert(EnsureStartingLevel(&fresh, 1, error) && error.empty());     // the pool is at the floor: no raise, creation runs
    assert(stored().first == 1 && stored().second == 600);              // the owed XP was written, not erased unwritten
    assert(accounts.empty() && saves.empty());
''', "if (raised ? written : FlushNow(key))", "if (written)")

    def test_the_creation_floor_writes_and_waits(self):
        text = definition(PARAGON, "bool EnsureStartingLevel(Player* player")
        self.assertIn("ApplyProgress(key, previous, Grant(previous, amount, xpTable));\n            written = FlushNow(key);", text)
        self.assertIn("saves.erase(key);", text)
        self.assertIn('Need(written, "Paragon XP could not be saved.");', text)


class Bar(unittest.TestCase):
    def test_a_burst_sends_the_bar_once_and_no_chat_line(self):
        both(self, '''
    login(p); Player peer; peer.guid = 6; login(peer);
    for (int i = 0; i < 100; ++i) kill(p, 7);                           // 700: no level-up
    assert(said.empty() && headers == 0 && snapshots == 0);             // a kill sends nothing at all
    hooks.OnPlayerUpdate(&p, 50);
    assert(headers == 1 && snapshots == 0 && lastHeader.xp == 700 && said.empty());
    hooks.OnPlayerUpdate(&p, 50);                                       // nothing changed since: nothing sent
    assert(headers == 1);
    hooks.OnPlayerUpdate(&peer, 50);                                    // the account's other character sees the bar move too
    assert(headers == 2 && snapshots == 0);
''', "            SendHeader(player,found->second,held->second,false);\n            found->second.progressDirty=false;", "            SendHeader(player,found->second,held->second,false);")

    def test_a_level_up_sends_the_whole_snapshot_once_and_one_line_naming_the_last_level(self):
        both(self, '''
    login(p);
    kill(p, 1500); kill(p, 1000); kill(p, 1000);                        // levels 1, 2, 3 in one burst
    assert(said.empty());
    hooks.OnPlayerUpdate(&p, 50);
    assert(snapshots == 1 && headers == 0);                             // C and R moved with the level
    assert(said.size() == 1 && said[0] == "Paragon level 3.");
    hooks.OnPlayerUpdate(&p, 50);
    assert(snapshots == 1 && said.size() == 1);
''', "        state.announce = updated.level;", "        if (!state.announce) state.announce = updated.level;")

    def test_the_old_per_kill_sends_are_gone(self):
        add = definition(PARAGON, "void AddXP(Player* player, XP amount, bool writeNow = false)")
        self.assertNotIn("Snapshot(", add)
        self.assertNotIn("SendSysMessage", add)
        self.assertNotIn("DirectExecute", add)


class Source(unittest.TestCase):
    def test_the_interval_row_is_alexs_ten_seconds_with_its_source(self):
        row = [r for r in (ROOT / "mod-diablocraft/data/tunables/paragon.csv").read_text(encoding="utf-8").splitlines()
               if r.startswith("paragon_save_interval_ms,")]
        self.assertEqual(len(row), 1)
        self.assertTrue(row[0].startswith("paragon_save_interval_ms,,10000,milliseconds,"))
        self.assertIn("ruling 2026-10-09", row[0])
        self.assertNotIn("PLACEHOLDER", row[0])
        self.assertIn('"paragon", "paragon_save_interval_ms"', PARAGON)

    def test_the_world_hooks_are_registered_for_the_tick_and_the_shutdown(self):
        self.assertIn("WORLDHOOK_ON_UPDATE, WORLDHOOK_ON_SHUTDOWN", PARAGON)


if __name__ == "__main__":
    unittest.main()
