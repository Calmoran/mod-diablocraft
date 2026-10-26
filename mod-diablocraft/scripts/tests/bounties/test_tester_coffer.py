"""Compile small harnesses around the production Coffer functions and kill mutations.

No live database or running server is used. C++ cases exercise the extracted
ledger, gem, and Paragon methods against controlled substitutes for core I/O.
"""
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
WORLD = (ROOT / "mod-diablocraft/src/common/dc_world.cpp").read_text()
LEDGER = (ROOT / "mod-diablocraft/src/common/dc_account_economy.cpp").read_text()
PARAGON = (ROOT / "mod-diablocraft/src/paragon/dc_paragon.cpp").read_text()
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch"
sys.path.insert(0, str(ROOT / "mod-diablocraft/scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_tester_coffer as coffer
import harness_env


def stock_chest() -> None:
    models = (ROOT / "azerothcore-wotlk/data/sql/base/db_world/creature_template_model.sql").read_text()
    assert re.search(r"^\(30548,\d+,27106,", models, re.MULTILINE)

    def rows(name: str):
        data = (ROOT / "azerothcore-wotlk/build/server/data/dbc" / name).read_bytes()
        magic, count, _, size, _ = struct.unpack_from("<4s4I", data)
        assert magic == b"WDBC"
        return [data[20 + i * size:20 + (i + 1) * size] for i in range(count)], data[20 + count * size:]

    displays, _ = rows("CreatureDisplayInfo.dbc")
    model = next(struct.unpack_from("<I", row, 4)[0] for row in displays
                 if struct.unpack_from("<I", row)[0] == coffer.CHEST_DISPLAY)
    model_rows, strings = rows("CreatureModelData.dbc")
    offset = next(struct.unpack_from("<I", row, 8)[0] for row in model_rows
                  if struct.unpack_from("<I", row)[0] == model)
    path = strings[offset:strings.index(b"\0", offset)].decode()
    assert path.lower() == r"world\goober\g_chesttitan.mdx"
    assert coffer.CHEST_DONOR == 30548
    placement = coffer.input_row()
    assert (coffer.f32(placement["x"]), coffer.f32(placement["y"]),
            coffer.f32(placement["z"]), coffer.f32(placement["o"])) == tuple(
                coffer.f32(v) for v in (-2084.4683, 5504.3228, 50.597404, 5.964404))
    assert placement["source_guid"] == 8000112
    assert "PM live acore_world collision audit" in placement["guid_source"]
    sql = coffer.generate()
    assert sql.count("INSERT INTO `creature` ") == coffer.launch_tier_count()
    assert "dc_tester_coffer" in sql and "8000108" not in sql
    for tier in range(1, coffer.launch_tier_count() + 1):
        assert f"VALUES ({8000112 + tier - 1},910018,530,3703,3703,1,{tier}," in sql
    assert "source_guid=8000112" in sql and "8000112-8000121" in sql
    assert sql.count("NOT EXISTS(SELECT 1 FROM creature WHERE guid=") == 10
    assert sql.count("NOT EXISTS(SELECT 1 FROM dc_area_spawn WHERE kind='c' AND spawn_guid=") == 9
    print("PASS stock chest display and collision-free sourced ten-GUID placement")


def body(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end].replace("    static ", "    ", 1)


def run_cpp(name: str, source: str, expect_pass: bool = True) -> None:
    with tempfile.TemporaryDirectory(prefix="tester-coffer-", dir=SCRATCH) as folder:
        path = Path(folder)
        (path / "test.cpp").write_text(source)
        built = subprocess.run(["g++", "-std=c++20", "-O0", "-I", str(ROOT / "mod-diablocraft/src/paragon"), "-I", str(ROOT / "mod-diablocraft/src/common"),
                                str(path / "test.cpp"),
                                "-o", str(path / "test")], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(name + " harness did not compile: " + built.stderr[-3000:])
        result = harness_env.run([str(path / "test")], capture_output=True, text=True)
        if (result.returncode == 0) != expect_pass:
            raise AssertionError(name + " unexpectedly " + ("passed" if result.returncode == 0 else "failed")
                                 + ": " + result.stderr[-3000:])
    print("PASS " + name)


LEDGER_SETUP = r'''
#include <cassert>
#include <cstdint>
#include <limits>
#include <map>
#include <string>
#include <tuple>
#include <stdexcept>
#include <algorithm>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
#include "dc_blood_shards.h"
struct Player {};
namespace PlayerEconomy {
bool failed=false;
struct Scope { explicit Scope(Player*) {} bool Finish() { return !failed; } };
void Fail() { failed=true; }
bool Change(Player*, uint64, bool, bool);
}
namespace DC::AccountEconomy {
struct Snapshot { uint32 account=1; std::string mode="normal",gold,revision="0";
    std::map<uint32,std::string> materials; };
uint64 gold=0;
std::map<uint32,uint64> material{{102000,0},{102001,0}};
bool enabled=true;
uint64 shardCap=0; // the account's Blood Shard cap; ShardCap itself is run against a table in test_blood_shards.py
uint64 ShardCap(uint32,bool) { return shardCap; }
struct Operation {
    bool Adjust(std::tuple<uint32,bool,uint32> key,uint64 delta,bool debit) {
        auto& amount=material[std::get<2>(key)];
        if (debit ? delta>amount : delta>std::numeric_limits<uint64>::max()-amount) return false;
        amount=debit ? amount-delta : amount+delta; return true;
    }
} operation;
Operation* Current() { return &operation; }
bool Actor(Player*,uint32& account,bool& hardcore) { account=1; hardcore=false; return true; }
bool ReadSnapshot(Player*,Snapshot& s) {
    s.gold=std::to_string(gold); s.materials.clear();
    for(auto const& [entry,count]:material) s.materials[entry]=std::to_string(count);
    return true;
}
'''
LEDGER_END = r'''
}
bool PlayerEconomy::Change(Player*,uint64 target,bool debit,bool absolute) {
    if (debit || !absolute) return false;
    DC::AccountEconomy::gold=target; return true;
}
int main() {
    using namespace DC::AccountEconomy;
    Player player; Snapshot before,after;
    gold=20; material={{102000,4},{102001,200}};
    assert(TopUp(&player,100,100,before,after));
    assert(before.gold=="20" && after.gold=="100" && gold==100);
    assert(material[102000]==100 && material[102001]==200);
    assert(TopUp(&player,100,100,before,after));
    assert(before.gold==after.gold && material[102001]==200);
    gold=std::numeric_limits<uint64>::max();
    material[102000]=std::numeric_limits<uint64>::max();
    assert(TopUp(&player,100,100,before,after));
    assert(gold==std::numeric_limits<uint64>::max());
    assert(material[102000]==std::numeric_limits<uint64>::max());
    gold=std::numeric_limits<uint64>::max()-1;
    material[102000]=1;
    assert(TopUp(&player,std::numeric_limits<uint64>::max(),
                 std::numeric_limits<uint64>::max(),before,after));
    assert(gold==std::numeric_limits<uint64>::max());
    assert(material[102000]==std::numeric_limits<uint64>::max());
    // Blood Shards: the coffer raises them only to the account's cap, and never lowers a balance above it.
    uint64 const shards=DC::BloodShards::Entry;
    gold=0; shardCap=1250; material={{102000,0},{shards,0}};
    assert(TopUp(&player,0,100,before,after) && material[shards]==100 && material[102000]==100);
    assert(TopUp(&player,0,5000,before,after) && material[shards]==1250 && material[102000]==5000);
    assert(after.materials.at(shards)=="1250");
    material[shards]=1300;
    assert(TopUp(&player,0,5000,before,after) && material[shards]==1300);
    shardCap=0; material[shards]=0;
    assert(TopUp(&player,0,5000,before,after) && material[shards]==0 && material[102000]==5000);
}
'''

GEM_SETUP = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>
using uint32=std::uint32_t; using uint64=std::uint64_t;
constexpr int NULL_BAG=0, NULL_SLOT=0;
using ItemPosCountVec=std::vector<int>;
struct Item {};
struct Transaction {};
using CharacterDatabaseTransaction=std::shared_ptr<Transaction>;
struct Player {
    uint32 bags=0,mail=0,capacity=0,mailCalls=0;
    Item item;
    int CanStoreNewItem(int,int,ItemPosCountVec& dest,uint32,uint32 missing,uint32* noSpace) {
        auto fit=std::min(missing,capacity);
        *noSpace=missing-fit; if(fit) dest.push_back(fit); return 0;
    }
    Item* StoreNewItem(ItemPosCountVec const& dest,uint32,bool) {
        bags+=dest.front(); capacity-=dest.front(); return &item;
    }
    void SendNewItem(Item*,uint32,bool,bool) {}
};
void SendGemMail(Player* player,uint32,uint32 count,CharacterDatabaseTransaction& tx) {
    if(!tx) tx=std::make_shared<Transaction>();
    player->mail+=count; ++player->mailCalls;
}
uint64 CountOwned(Player* player,uint32,uint32) {
    return uint64(player->bags)+player->mail;
}
'''
GEM_END = r'''
int main() {
    Player p; p.capacity=7; CharacterDatabaseTransaction tx;
    assert(TopUpGem(&p,1,103002,20,tx)==0);
    assert(CountOwned(&p,1,103002)==20 && p.bags==7 && p.mail==13 && p.mailCalls==1 && tx);
    assert(TopUpGem(&p,1,103002,20,tx)==20 && p.mailCalls==1);
    Player full; CharacterDatabaseTransaction fullTx;
    assert(TopUpGem(&full,1,103012,20,fullTx)==0);
    assert(CountOwned(&full,1,103012)==20 && full.mail==20 && full.mailCalls==1 && fullTx);
    Player rich; rich.bags=25; CharacterDatabaseTransaction richTx;
    assert(TopUpGem(&rich,1,103022,20,richTx)==25);
    assert(CountOwned(&rich,1,103022)==25 && rich.mailCalls==0 && !richTx);
}
'''

MAIL_SETUP = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
using uint32=std::uint32_t;
constexpr uint32 MAX_MAIL_ITEMS=12, MAIL_CREATURE=3, TesterCofferEntry=910018;
struct Player { uint32 guid=4; struct Guid { uint32 GetCounter() const { return 4; } };
    Guid GetGUID() const { return {}; } };
struct ItemTemplate { uint32 stack=1; uint32 GetMaxStackSize() const { return stack; } } proto;
struct ObjectMgr { ItemTemplate const* GetItemTemplate(uint32) const { return &proto; } } objectMgr;
ObjectMgr* sObjectMgr=&objectMgr;
struct Transaction { uint32 saved=0, mailed=0, drafts=0; };
using CharacterDatabaseTransaction=std::shared_ptr<Transaction>;
struct Future { bool get() const; };
bool commitSucceeds=true;
bool Future::get() const { return commitSucceeds; }
struct Callback { Future m_future; };
struct Database { uint32 begins=0, commits=0; CharacterDatabaseTransaction tx;
    CharacterDatabaseTransaction BeginTransaction() { ++begins; tx=std::make_shared<Transaction>(); return tx; }
    Callback AsyncCommitTransaction(CharacterDatabaseTransaction) { ++commits; return {}; } } CharacterDatabase;
struct Item { uint32 count; static Item* CreateItem(uint32,uint32 count,Player*) { return new Item{count}; }
    void SaveToDB(CharacterDatabaseTransaction tx) { tx->saved+=count; } };
struct MailReceiver { MailReceiver(Player*,uint32) {} };
struct MailSender { MailSender(uint32,uint32) {} };
struct MailDraft {
    uint32 count=0, items=0;
    MailDraft(char const*,char const*) {}
    void AddItem(Item* item) { count+=item->count; ++items; delete item; }
    void SendMailTo(CharacterDatabaseTransaction tx,MailReceiver,MailSender) {
        assert(items>0 && items<=MAX_MAIL_ITEMS); tx->mailed+=count; ++tx->drafts;
    }
};
'''
MAIL_END = r'''
int main() {
    Player p; CharacterDatabaseTransaction tx;
    SendGemMail(&p,103002,20,tx);
    SendGemMail(&p,103012,20,tx);
    assert(CharacterDatabase.begins==1 && CharacterDatabase.commits==0);
    assert(tx->saved==40 && tx->mailed==40 && tx->drafts==4);
    CommitMail(tx);
    assert(CharacterDatabase.commits==1);
    commitSucceeds=false;
    bool refused=false;
    try { CommitMail(tx); } catch(std::runtime_error const&) { refused=true; }
    assert(refused);
}
'''

TARGET_SETUP = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
using uint64=std::uint64_t;
namespace Tunables { double value=200; double Get(char const*,char const*) { return value; } }
'''
TARGET_END = r'''
int main() {
    assert(Target("tester_coffer_paragon",800)==200);
    assert(Target("tester_coffer_gems",200)==200);
    Tunables::value=2000000;
    bool paragonRejected=false, gemsRejected=false;
    try { Target("tester_coffer_paragon",800); } catch(std::runtime_error const&) { paragonRejected=true; }
    try { Target("tester_coffer_gems",200); } catch(std::runtime_error const&) { gemsRejected=true; }
    assert(paragonRejected && gemsRejected);
}
'''

PARAGON_SETUP = r'''
#include <cassert>
#include <cstdint>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include "dc_paragon_math.h"
using uint32=std::uint32_t;
struct Player {};
namespace DC::Paragon {
std::mutex mutex;
struct Character { int account=1; } state;
Progress progress;
std::vector<XP> xpTable(800,100);
unsigned awards=0,barUpdates=0;
Character& State(Player*) { return state; }
Progress& Account(int) { return progress; }
void AddXP(Player*,XP amount,bool writeNow=false) {
    ++awards; progress=Grant(progress,amount,xpTable); ++barUpdates;
}
'''
PARAGON_END = r'''
}
int main() {
    using namespace DC::Paragon;
    Player player; std::string error; uint32 before=0,after=0;
    progress={10,25};
    assert(TopUpLevel(&player,200,before,after,error));
    assert(before==10 && after==200 && progress.level==200 && progress.xp==0);
    assert(awards==1 && barUpdates==1);
    assert(TopUpLevel(&player,200,before,after,error));
    assert(before==200 && after==200 && awards==1);
    progress={205,33};
    assert(TopUpLevel(&player,200,before,after,error));
    assert(before==205 && after==205 && progress.xp==33 && awards==1);
    progress={0,0}; xpTable.assign(800,std::numeric_limits<XP>::max()/2);
    assert(!TopUpLevel(&player,200,before,after,error));
    assert(!error.empty() && progress.level==0 && awards==1);
}
'''

SWITCH_SETUP = r'''
#include <cassert>
#include <optional>
struct Config {
    std::optional<bool> value;
    template<class T> T GetOption(char const*,T fallback) const { return value.value_or(fallback); }
} config;
Config* sConfigMgr=&config;
'''
SWITCH_END = r'''
int main() {
    assert(!Enabled()); // absent configuration stays off
    config.value=false; assert(!Enabled());
    config.value=true; assert(Enabled());
}
'''


def main() -> None:
    stock_chest()
    ledger = body(LEDGER, "    bool TopUp(Player* player")
    run_cpp("ledger top-up and uint64 limits", LEDGER_SETUP + ledger + LEDGER_END)
    mutant = ledger.replace("gold < goldCopper", "gold > goldCopper", 1)
    assert mutant != ledger
    run_cpp("ledger decrease mutation rejected", LEDGER_SETUP + mutant + LEDGER_END, False)
    uncapped = ledger.replace("std::min(materialCount, ShardCap(account, hardcore))", "materialCount", 1)
    assert uncapped != ledger
    run_cpp("coffer filling Blood Shards past the cap rejected", LEDGER_SETUP + uncapped + LEDGER_END, False)

    gem = body(WORLD, "    static uint64 TopUpGem(")
    run_cpp("partial bags overflow to mail; repeated use", GEM_SETUP + gem + GEM_END)
    mutant = gem.replace("if (mailed)", "if (false)", 1)
    assert mutant != gem
    run_cpp("lost mail mutation rejected", GEM_SETUP + mutant + GEM_END, False)

    mail = body(WORLD, "    static void SendGemMail(")
    select = body(WORLD[WORLD.index("class TesterCoffer final"):],
                  "    bool OnGossipSelect(Player* player, Creature* creature, uint32 sender, uint32 action)")
    commit_line = "if (mailTransaction && !CharacterDatabase.AsyncCommitTransaction(mailTransaction).m_future.get())"
    assert commit_line in select
    commit = ("void CommitMail(CharacterDatabaseTransaction& mailTransaction) { " + commit_line +
              " throw std::runtime_error(\"gem mail commit failed\"); }\n")
    run_cpp("all gem colours share one durable mail commit", MAIL_SETUP + mail + commit + MAIL_END)
    mutant = commit.replace(commit_line, "if (false)", 1)
    run_cpp("mail commit mutation rejected", MAIL_SETUP + mail + mutant + MAIL_END, False)

    target = body(WORLD, "    static uint64 Target(")
    assert "SELECT MAX(level) FROM dc_paragon_xp" in select
    assert "Target(\"tester_coffer_paragon\", (*paragonLevels)[0].Get<uint32>())" in select
    assert "Target(\"tester_coffer_gems\", gemStackMaximum)" in select
    run_cpp("domain-limited Paragon and gem targets", TARGET_SETUP + target + TARGET_END)
    mutant = target.replace("value > double(std::min<uint64>(limit, uint64(1) << 53))", "false", 1)
    assert mutant != target
    run_cpp("unbounded target mutation rejected", TARGET_SETUP + mutant + TARGET_END, False)

    paragon = body(PARAGON, "bool TopUpLevel(Player* player")
    run_cpp("Paragon pays XP through normal award", PARAGON_SETUP + paragon + PARAGON_END)
    mutant = paragon.replace("AddXP(player, amount, true);", "Account(state.account).level = target;", 1)
    assert mutant != paragon
    run_cpp("direct Paragon assignment mutation rejected", PARAGON_SETUP + mutant + PARAGON_END, False)

    enabled = body(WORLD, "    static bool Enabled()")
    assert "Diablocraft.TesterCoffer.Enable" in enabled and "false" in enabled
    run_cpp("tester switch defaults off", SWITCH_SETUP + enabled + SWITCH_END)
    mutant_enabled = enabled.replace("false);", "true);", 1)
    assert mutant_enabled != enabled
    run_cpp("switch default-on mutation rejected", SWITCH_SETUP + mutant_enabled + SWITCH_END, False)
    assert "if (!Enabled() || !AccountEconomy::Eligible(player))" in select
    mutant = select.replace("!Enabled() || ", "", 1)
    assert "if (!Enabled() || !AccountEconomy::Eligible(player))" not in mutant
    print("PASS server-side handler refusal guard and failing guard mutation")


if __name__ == "__main__":
    main()
