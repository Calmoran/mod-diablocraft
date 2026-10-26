"""Compile production RewardGuardian against core doubles and check the
guardian_killed_at write: set on the guardian kill, once, never on a failed
reward, and never by any other rift path (rifts_0006_clear_time.sql)."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
# DC_RIFT_CLEAR_TIME_SOURCE lets a mutation run prove the assertions can fail.
PATH = Path(os.environ.get('DC_RIFT_CLEAR_TIME_SOURCE',
                           ROOT / 'mod-diablocraft/src/monsters/dc_monster_ai.cpp'))
SOURCE = PATH.read_text(encoding='utf-8')


def definition(marker: str) -> str:
    start = SOURCE.index(marker)
    opening = SOURCE.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]


# Every other place in the rift sources that writes the column must be absent:
# the brief says one path only.
writers = [p.name for p in (ROOT / 'mod-diablocraft/src').rglob('*.cpp')
           if 'guardian_killed_at' in p.read_text(encoding='utf-8')]
assert writers == ['dc_monster_ai.cpp'] or PATH.name != 'dc_monster_ai.cpp', writers

HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#include <algorithm>
#include <utility>
#include <functional>
#include "FLOORS_HEADER"
#include "CORPSE_RULES_HEADER"
using DC::Rifts::LiveRuns;
using uint32 = std::uint32_t;
#define LOG_ERROR(...) ((void)0)
#define LOG_WARN(...) ((void)0)
constexpr unsigned KEYSTONE_ITEM = 1;

// A recording database: the test reads back what the production code wrote.
struct Db {
    std::vector<std::string> sql;
    template <typename... A> void Fmt(std::string s, A const&...) { sql.push_back(s); }
    template <typename... A> void DirectExecute(char const* s, A const&... a) { Fmt(s, a...); }
    template <typename... A> void Execute(char const* s, A const&... a) { Fmt(s, a...); }
    unsigned Count(char const* needle) const {
        return (unsigned)std::count_if(sql.begin(), sql.end(),
            [&](std::string const& q) { return q.find(needle) != std::string::npos; });
    }
} CharacterDatabase;

struct Rift { std::uint32_t instanceId = 7, mapId = 0, dungeonId = 0; std::uint64_t id = 99; unsigned floor = 1; std::string state, mode = "nr"; unsigned tier = 1, grRank = 0; };
// The production book (dc_rift_floors.h); the one test run is id 99, and live[7] reads it back
struct Book : LiveRuns<Rift> { Rift& operator[](unsigned) { return *Find(99); } };
Book live;
std::mutex riftMutex;
void PersistNow(Rift const& r) { CharacterDatabase.DirectExecute("UPDATE dc_rift SET kills={}, state='{}' WHERE id={}", r.state); }
void Announce(Rift const&, std::string const&) {}

bool rewardCommits = true, scopeFailed = false;
struct Creature { unsigned GetLevel() const { return 70; } };
struct ObjectGuid { unsigned counter = 1; ObjectGuid() = default; ObjectGuid(std::uint64_t raw) : counter((unsigned)raw) {}
    unsigned GetCounter() const { return counter; } std::uint64_t GetRawValue() const { return counter; } };
struct Player;
struct GroupReference { Player* src = nullptr; GroupReference* nxt = nullptr;
    GroupReference* next() { return nxt; } Player* GetSource() { return src; } };
struct Group { GroupReference first; GroupReference* GetFirstMember() { return &first; } };
Group theGroup;
bool grouped = false;
struct WorldSession {};
struct ChatHandler {
    ChatHandler(WorldSession*) {}
    void SendSysMessage(std::string const& line) { chat.push_back(line); }
    static inline std::vector<std::string> chat;
};
struct Player {
    unsigned id = 1;
    ObjectGuid GetGUID() const { return {id}; }
    WorldSession* GetSession() const { static WorldSession session; return &session; }
    Group* GetGroup() const { return grouped ? &theGroup : nullptr; }
    bool IsInMap(Creature*) const { return true; }
    bool IsAtGroupRewardDistance(Creature*) const { return true; }
};
namespace PlayerEconomy {
    struct Scope { Scope(Player*) { scopeFailed = false; } bool Finish() { return rewardCommits && !scopeFailed; } };
    void Fail() { scopeFailed = true; }
}
// Kadala part 2: the shard credit, the pay and the chat line are doubles; their own arithmetic is test_gr_rewards.py's.
struct ShardCredit { unsigned entry; std::uint64_t amount; std::string receipt; };
std::vector<ShardCredit> shardCredits;
std::vector<std::string> keystoneReceipts;
bool economyOn = true, creditRefused = false;
std::uint64_t shardPay = 50, shardCut = 0;
namespace DC::AccountEconomy {
    bool Enabled() { return economyOn; }
    bool CreditMaterial(Player*, unsigned entry, std::uint64_t amount, std::string const& receipt, std::uint64_t* lost) {
        if (lost) *lost = shardCut;
        shardCredits.push_back({entry, amount, receipt});
        return !creditRefused;
    }
}
namespace DC::BloodShards { constexpr std::uint32_t Entry = 102007; }
std::uint64_t GuardianShards(Rift const&) { return shardPay; }
namespace Gr { std::string ShardLine(std::uint64_t paid, std::uint64_t lost) { return "line " + std::to_string(paid) + "/" + std::to_string(lost); } }
// Rift floors F7: the run's enrolled members, and the corpse the Guardian leaves. The double keeps what OweCorpse was handed.
std::vector<ObjectGuid> enrolled;
std::vector<ObjectGuid> EnrolledGuids(std::uint64_t) { return enrolled; }
namespace DC::Loot {
    using OwedPay = std::function<bool(Player*, Creature*)>;
    bool corpseCanHold = true;
    unsigned oweCalls = 0;
    std::vector<ObjectGuid> lastOwed;
    OwedPay lastPay;
    bool OweCorpse(Creature*, std::vector<ObjectGuid> const& owed, OwedPay pay) {
        ++oweCalls; lastOwed = owed; lastPay = pay; return corpseCanHold;
    }
}
namespace DC::Loot {
    enum class Source { RiftGuardian };
    struct GreaterReward { double legendaries = 0; };
    double seenLegendaries = -2;   // what the Guardian roll was handed: the level's average, -1 for no GreaterReward
    void RollLoot(Player*, Source, unsigned, unsigned, bool, std::string, Creature*, void*, GreaterReward const* greater) { seenLegendaries = greater ? greater->legendaries : -1; }
    bool GrantMaterial(Player*, unsigned, unsigned, std::string receipt) { keystoneReceipts.push_back(receipt); return true; }
    unsigned ExtraKeystones(Player const*) { return 0; }   // Cain's Destiny's extra keystone (y3z8a): none here, the clear-time test does not wear it
}
DC::Loot::GreaterReward GuardianReward(Player*, Rift const& rift) { return {double(rift.grRank)}; }

'''

MAIN = r'''
void ShardReset() { shardCredits.clear(); keystoneReceipts.clear(); ChatHandler::chat.clear(); }
int main() {
    Player killer; Creature guardian;
    auto arm = [&](char const* state) {
        live.Clear(); Rift fresh; fresh.state = state; live.Start(fresh);
        CharacterDatabase.sql.clear();
    };
    auto stamps = [&] { return CharacterDatabase.Count("guardian_killed_at=NOW()"); };
    auto guarded = [&] { return CharacterDatabase.Count("guardian_killed_at IS NULL"); };

    // 1. The guardian kill sets it, once, behind the IS NULL guard.
    arm("guardian");
    Rift copy = live[7];
    assert(RewardGuardian(&killer, &guardian, copy));
    assert(stamps() == 1 && guarded() == 1);

    // 2. A second kill / replayed completion does not write again.
    assert(!RewardGuardian(&killer, &guardian, copy));
    assert(stamps() == 1);

    // 3. A rift not in the guardian state (an ordinary kill) writes nothing.
    for (char const* state : {"open", "complete", "closed"}) {
        arm(state);
        Rift r = live[7];
        assert(!RewardGuardian(&killer, &guardian, r));
        assert(stamps() == 0);
    }

    // 4. Rewards that did not commit: the run is not complete, no time recorded.
    arm("guardian");
    rewardCommits = false;
    Rift r2 = live[7];
    assert(!RewardGuardian(&killer, &guardian, r2));
    assert(stamps() == 0);

    // 4b. Part 8: a Greater Rift's Guardian is rolled with the level's reward, a Nephalem Rift's with none.
    rewardCommits = true; grouped = false;
    arm("guardian"); live[7].mode = "gr"; live[7].grRank = 17;
    Rift gr = live[7];
    assert(RewardGuardian(&killer, &guardian, gr) && DC::Loot::seenLegendaries == 17);   // the double echoes grRank
    arm("guardian");
    Rift nr = live[7];
    assert(RewardGuardian(&killer, &guardian, nr) && DC::Loot::seenLegendaries == -1);

    // 4c. Kadala part 2: Blood Shards are one ledger credit per member, under a receipt of their own, and the
    // chat line (the amount, and what the cap cut) comes only after the reward committed.
    auto kill = [&](bool expectDone) {
        arm("guardian"); ShardReset();
        Rift r = live[7];
        assert(RewardGuardian(&killer, &guardian, r) == expectDone);
    };
    rewardCommits = true; grouped = false;
    kill(true);
    assert(shardCredits.size() == 1 && shardCredits[0].entry == 102007 && shardCredits[0].amount == 50);
    assert(shardCredits[0].receipt == "rift:99:guardian:reward:shards:1");
    assert(keystoneReceipts.size() == 1 && keystoneReceipts[0] == "rift:99:guardian:reward:1" && keystoneReceipts[0] != shardCredits[0].receipt);
    assert(ChatHandler::chat == std::vector<std::string>{"line 50/0"});
    shardCut = 20; kill(true);                                       // the cap cut 20: the line carries it
    assert(ChatHandler::chat == std::vector<std::string>{"line 50/20"});
    shardCut = 0; shardPay = 0; kill(true);                          // a tier with no pay: no credit, no line
    assert(shardCredits.empty() && ChatHandler::chat.empty());
    shardPay = 50; economyOn = false; kill(true);                    // no ledger: no shards
    assert(shardCredits.empty() && ChatHandler::chat.empty());
    economyOn = true; creditRefused = true; kill(false);             // a refused credit fails the whole reward, nothing said
    assert(shardCredits.size() == 1 && ChatHandler::chat.empty());
    creditRefused = false; rewardCommits = false; kill(false);       // not committed: nothing said
    assert(shardCredits.size() == 1 && ChatHandler::chat.empty());
    rewardCommits = true;
    {   // two members: each is credited under their own receipt, each told their own line
        Player other; other.id = 2; GroupReference second; second.src = &other;
        grouped = true; theGroup.first.src = &killer; theGroup.first.nxt = &second;
        kill(true);
        assert(shardCredits.size() == 2 && shardCredits[0].receipt == "rift:99:guardian:reward:shards:1");
        assert(shardCredits[1].receipt == "rift:99:guardian:reward:shards:2" && ChatHandler::chat.size() == 2);
        theGroup.first.nxt = nullptr; grouped = false;
    }

    // 4d. Rift floors (F1): the Guardian died on a LATER floor. The reward is paid and the run completes, and the write-back of
    // the copy seen from that floor does not move the run's own row off floor 1.
    rewardCommits = true; grouped = false;
    arm("guardian");
    assert(live.AddFloor(99, 8, 5, 0) == 2);
    Rift seen;
    assert(live.View(8, 5, seen) && seen.instanceId == 8 && seen.floor == 2);
    assert(RewardGuardian(&killer, &guardian, seen) && stamps() == 1);
    assert(live[7].state == "complete" && live[7].instanceId == 7 && live[7].floor == 1);
    assert(live.FloorAt(8, 5) && live.FloorAt(7, 0));              // both floors still stand
    assert(!RewardGuardian(&killer, &guardian, seen));               // and a replay from either floor pays nothing
    Rift again; live.View(7, 0, again);
    assert(!RewardGuardian(&killer, &guardian, again) && stamps() == 1);

    // 4e. Rift floors F7: everyone enrolled whom the kill did not pay is OWED, once, and the pay they are handed later is
    // the kill's own payout. Whoever is not in the run is never owed.
    auto owedIds = [&] { std::vector<unsigned> ids; for (ObjectGuid const& g : DC::Loot::lastOwed) ids.push_back(g.counter); return ids; };
    auto resetOwed = [&] { DC::Loot::oweCalls = 0; DC::Loot::lastOwed.clear(); DC::Loot::lastPay = nullptr; DC::Loot::corpseCanHold = true; };
    rewardCommits = true; grouped = false; economyOn = true; creditRefused = false; shardPay = 50; shardCut = 0;
    resetOwed();
    enrolled = {ObjectGuid(1), ObjectGuid(5), ObjectGuid(6)};       // a solo kill: the killer was paid, two members are elsewhere
    kill(true);
    assert(DC::Loot::oweCalls == 1 && owedIds() == std::vector<unsigned>({5, 6}));
    {   // the pay they are handed pays one member under the kill's own receipts, once the corpse is opened
        Player elsewhere; elsewhere.id = 5; ShardReset();
        assert(DC::Loot::lastPay(&elsewhere, &guardian));
        assert(keystoneReceipts.size() == 1 && keystoneReceipts[0] == "rift:99:guardian:reward:5");
        assert(shardCredits.size() == 1 && shardCredits[0].receipt == "rift:99:guardian:reward:shards:5" && shardCredits[0].amount == 50);
        assert(ChatHandler::chat == std::vector<std::string>{"line 50/0"});
        // the same receipts the kill path writes for that character (the cross-source check: one id, two paths)
        Player at; at.id = 5; GroupReference second; second.src = &at;
        grouped = true; theGroup.first.src = &killer; theGroup.first.nxt = &second; enrolled = {ObjectGuid(1), ObjectGuid(5)};
        kill(true);
        assert(keystoneReceipts.size() == 2 && keystoneReceipts[1] == "rift:99:guardian:reward:5");
        assert(shardCredits.size() == 2 && shardCredits[1].receipt == "rift:99:guardian:reward:shards:5");
        theGroup.first.nxt = nullptr; grouped = false;
        // a payout that did not commit says so, so the corpse keeps them owed and the next open tries again
        arm("guardian"); resetOwed(); enrolled = {ObjectGuid(1), ObjectGuid(5)};
        Rift again2 = live[7]; assert(RewardGuardian(&killer, &guardian, again2));
        rewardCommits = false; ShardReset();
        assert(!DC::Loot::lastPay(&elsewhere, &guardian) && ChatHandler::chat.empty());
        rewardCommits = true;
    }
    // Everyone enrolled was in range and paid: nobody is owed, and the corpse is not asked to hold anything.
    resetOwed(); enrolled = {ObjectGuid(1)}; kill(true);
    assert(DC::Loot::oweCalls == 0);
    // A stranger in range who is not enrolled was paid by the old rule and is not owed twice; an enrolled member out of range is.
    {
        Player stranger; stranger.id = 9; GroupReference second; second.src = &stranger;
        grouped = true; theGroup.first.src = &killer; theGroup.first.nxt = &second;
        resetOwed(); enrolled = {ObjectGuid(1), ObjectGuid(5)}; kill(true);
        assert(owedIds() == std::vector<unsigned>({5}));           // 9 was paid at the kill, 5 is owed, nobody else is
        theGroup.first.nxt = nullptr; grouped = false;
    }
    // A corpse that cannot hold loot: the run still completes (the kill paid its own); nothing is held for the others.
    resetOwed(); DC::Loot::corpseCanHold = false; enrolled = {ObjectGuid(1), ObjectGuid(5)}; kill(true);
    assert(DC::Loot::oweCalls == 1 && live[7].state == "complete");
    // A reward that did not commit owes nobody and a replay owes nobody twice.
    resetOwed(); enrolled = {ObjectGuid(1), ObjectGuid(5)}; rewardCommits = false; kill(false);
    assert(DC::Loot::oweCalls == 0);
    rewardCommits = true; kill(true); { Rift replay = live[7]; assert(!RewardGuardian(&killer, &guardian, replay)); }
    assert(DC::Loot::oweCalls == 1);
    enrolled.clear(); resetOwed();

    // 5. Same guardian kill through the group path still stamps once.
    rewardCommits = true;
    grouped = true; theGroup.first.src = &killer;
    arm("guardian");
    Rift r3 = live[7];
    assert(RewardGuardian(&killer, &guardian, r3));
    assert(stamps() == 1);
}
'''

code = HARNESS + definition('bool PayGuardianMember(') + definition('bool RewardGuardian(') + MAIN


def _toolchain():
    found = shutil.which('cmake')
    if not found:
        raise SystemExit('cmake is not on PATH; this harness compiles a small C++ program')
    windows = os.name == 'nt'
    return (found, ['-G', 'Visual Studio 17 2022', '-A', 'x64'] if windows else [],
            ['--config', 'Release', '--', '-m:1'] if windows else [],
            '/UNDEBUG' if windows else '-UNDEBUG', windows)


cmake, gen, buildargs, undebug, win = _toolchain()
env = {k.upper(): v for k, v in os.environ.items()} if win else dict(os.environ)
with tempfile.TemporaryDirectory(prefix='dc-rift-clear-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code.replace('FLOORS_HEADER', (ROOT / 'mod-diablocraft/src/rifts/dc_rift_floors.h').as_posix()).replace('CORPSE_RULES_HEADER', (ROOT / 'mod-diablocraft/src/loot/dc_corpse_rules.h').as_posix()), encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(rift_clear LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 20)\n'
        'add_executable(rift_clear test.cpp)\n'
        'target_compile_options(rift_clear PRIVATE ' + undebug + ')\n', encoding='utf-8')
    subprocess.run([cmake, '-S', directory, '-B', str(folder / 'build')] + gen, env=env, check=True)
    subprocess.run([cmake, '--build', str(folder / 'build')] + buildargs, env=env, check=True)
    exe = folder / 'build' / ('Release/rift_clear.exe' if win else 'rift_clear')
    harness_env.run([str(exe)], env=env, check=True)
print('PASS: guardian_killed_at written once on the guardian kill, never on other paths.')
