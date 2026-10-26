"""Compile the installed 0007 context and module ledger against fault-injectable storage.

The money/context/ledger methods are extracted from production sources. SQL and
world objects are doubles; test-account-gold.md separately covers live acceptance.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mod-diablocraft/scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import host_cmake

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/account-economy-tests"


def extract(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def strip_includes(source: str) -> str:
    return re.sub(r'^#include[^\n]*\n', '', source, flags=re.M)


def main() -> None:
    player_dir = ROOT / "azerothcore-wotlk/src/server/game/Entities/Player"
    header = strip_includes((player_dir / "PlayerEconomy.h").read_text(encoding="utf-8"))
    core = strip_includes((player_dir / "PlayerEconomy.cpp").read_text(encoding="utf-8"))
    player = (player_dir / "Player.cpp").read_text(encoding="utf-8")
    methods = "\n".join(extract(player, name) for name in (
        "uint64 Player::GetAccountMoney(", "bool Player::SetMoney(", "bool Player::ModifyMoney("))
    ledger = (ROOT / "mod-diablocraft/src/common/dc_account_economy.cpp").read_text(encoding="utf-8")
    operation = extract(ledger, "class Operation final") + ";"
    opcodes = ','.join(sorted(set(re.findall(r'case (\w+):', core))))
    code = r'''
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <exception>
#include <functional>
#include <future>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>
#include <vector>
using uint8=std::uint8_t;using uint32=std::uint32_t;using uint64=std::uint64_t;
using int32=std::int32_t;using int64=std::int64_t;
#define AC_GAME_API
#define LOG_ERROR(...) ((void)0)
enum {@OPCODES@};
using Key=std::tuple<uint32,bool,uint32>;
struct DbState {uint64 amount=0,revision=0;};
std::map<Key,DbState> durable;
std::map<uint32,std::pair<uint32,uint32>> saved;
bool commitOk=true,throwCommit=false;unsigned commits=0;
struct Statement {std::string sql;std::vector<std::string> args;};
template<class T>std::string str(T const& value){std::ostringstream s;s<<value;return s.str();}
struct Tx {
 std::vector<Statement> statements;
 template<class...T>void Append(std::string const& sql,T const&... args){statements.push_back({sql,{str(args)...}});}
 std::size_t GetSize()const{return statements.size();}
};
using CharacterDatabaseTransaction=std::shared_ptr<Tx>;
struct Future {std::future<bool> m_future;};
struct Database {
 CharacterDatabaseTransaction BeginTransaction(){return std::make_shared<Tx>();}
 Future AsyncCommitTransaction(CharacterDatabaseTransaction const& tx){
  if(throwCommit)throw std::runtime_error("transport failed");
  ++commits;auto next=durable;auto chars=saved;bool ok=commitOk;unsigned affected=0;
  for(auto const& s:tx->statements){auto const& a=s.args;
   auto n=[&](unsigned i){return std::stoull(a.at(i));};
   if(s.sql=="snapshot")chars[uint32(n(0))]={uint32(n(1)),uint32(n(2))};
   else if(s.sql.find("INSERT IGNORE INTO dc_account_")==0){
    bool material=s.sql.find("currency")!=std::string::npos;
    next.try_emplace({uint32(n(0)),a[1]=="hardcore",material?uint32(n(2)):0});
   }else if(s.sql.find("UPDATE dc_account_")==0){
    bool material=s.sql.find("currency")!=std::string::npos;
    Key key{uint32(n(1)),a[2]=="hardcore",material?uint32(n(3)):0};
    auto& row=next[key];affected=row.revision==n(material?4:3);
    if(affected){row.amount=n(0);++row.revision;}
   }else if(s.sql.find("INSERT INTO dc_account_economy_check")==0 && affected!=1)ok=false;
  }
  if(ok){durable=next;saved=chars;}
  std::promise<bool> promise;auto future=promise.get_future();promise.set_value(ok);return {std::move(future)};
 }
 void CommitTransaction(CharacterDatabaseTransaction const& tx){AsyncCommitTransaction(tx).m_future.get();}
} CharacterDatabase;
@HEADER@
struct Guid {uint32 n;uint32 GetCounter()const{return n;}};
struct WorldPacket {uint32 n=0;};
class Player;
class WorldSession {
public:
 Player* player=nullptr;bool aborted=false;unsigned delivered=0;
 bool EconomyAborted()const{return aborted;}
 void AbortEconomy(){aborted=true;}
 bool IsTrialAccount()const{return false;}
 Player* GetPlayer(){return player;}
 void SendPacket(WorldPacket const* p){if(!PlayerEconomy::DeferPacket(this,p))++delivered;}
};
class Player {
public:
 uint32 guid,account,mirror=0,inventory=0;bool hardcore=false,locked=false;WorldSession session;
 Player(uint32 g,uint32 a,bool h=false):guid(g),account(a),hardcore(h){session.player=this;}
 WorldSession* GetSession()const{return const_cast<WorldSession*>(&session);}
 Guid GetGUID()const{return {guid};}
 uint32 GetMoney()const{return mirror;}
 uint32 GetHonorPoints()const{return 0;}void SetHonorPoints(uint32){}
 void SetMoneyMirror(uint32 n){mirror=n;}
 uint64 GetAccountMoney()const;bool SetMoney(uint64);bool ModifyMoney(int64,bool=true);
 bool HasEnoughMoney(uint32 n)const{return GetAccountMoney()>=n;}
 void SendEquipError(int,void*,void*){}
 void SaveToDB(CharacterDatabaseTransaction tx,bool,bool){tx->Append("snapshot",guid,inventory,mirror);}
};
constexpr uint32 MAX_MONEY_AMOUNT=UINT32_MAX;
enum {EQUIP_ERR_NOT_ENOUGH_MONEY,EQUIP_ERR_TOO_MUCH_GOLD,CONFIG_TRIAL_MONEY_CAP,CONFIG_MAX_HONOR_POINTS,CONFIG_MAX_HONOR_POINTS_MONEY_PER_POINT};
struct World {uint32 getIntConfig(int)const{return 0;}} world;auto* sWorld=&world;
struct Scripts {
 unsigned legacy=0,wide=0;
 void OnPlayerMoneyChanged(Player*,int32&){++legacy;}
 void OnPlayerMoneyChangedWide(Player*,int64&){++wide;}
} scripts;auto* sScriptMgr=&scripts;
@CORE@
@METHODS@
namespace TestLedger {
struct State {uint64 amount=0,revision=0;};
struct PendingBalance {State before;uint64 amount=0;bool dirty=false;};
std::recursive_mutex mutex;std::map<Key,State> cache;
std::set<std::pair<uint32,bool>> faultAccounts;
std::map<uint32,Player*> actors;
char const* Mode(bool h){return h?"hardcore":"normal";}
std::string NewId(){static std::atomic<unsigned> n=0;return std::to_string(++n);}
bool Actor(Player const* p,uint32& a,bool& h){if(!p||p->locked||p->session.aborted)return false;a=p->account;h=p->hardcore;return true;}
bool Principal(uint32 g,uint32& a,bool& h){auto p=actors.find(g);return p!=actors.end()&&Actor(p->second,a,h);}
namespace Hardcore {bool IsLocked(uint32 g){return actors.at(g)->locked;}}
State Load(Key const& k){auto it=cache.find(k);if(it!=cache.end())return it->second;auto d=durable[k];return cache[k]={d.amount,d.revision};}
@OPERATION@
class Provider:public PlayerEconomy::Provider {
 std::unique_ptr<PlayerEconomy::Context> Begin()override{return std::make_unique<Operation>();}
 bool ReadOffline(uint32 g,uint64& n)override{uint32 a;bool h;if(!Principal(g,a,h))return false;n=Load({a,h,0}).amount;return true;}
 bool AllowTransfer(uint32 a,uint32 b)override{uint32 aa,bb;bool ha,hb;return Principal(a,aa,ha)&&Principal(b,bb,hb)&&ha==hb;}
} provider;
}
void check(bool ok,char const* name){if(!ok)throw std::runtime_error(name);std::cout<<"PASS "<<name<<'\n';}
void reset(Player& a,Player& b){
 durable.clear();saved.clear();TestLedger::cache.clear();TestLedger::actors={{a.guid,&a},{b.guid,&b}};
 a.session.aborted=b.session.aborted=false;a.session.delivered=b.session.delivered=0;
 a.locked=b.locked=false;a.mirror=b.mirror=a.inventory=b.inventory=0;
 commitOk=true;throwCommit=false;commits=0;scripts={};
}
int main(){
 PlayerEconomy::Install(&TestLedger::provider);Player a(1,10),b(2,20);
 reset(a,b);
 check(a.SetMoney(UINT64_MAX)&&a.GetAccountMoney()==UINT64_MAX&&a.GetMoney()==UINT32_MAX,"uint64 balance and saturated mirror");
 check(a.ModifyMoney(-int64(UINT32_MAX))&&a.GetAccountMoney()==UINT64_MAX-UINT32_MAX,"spend directly above mirror ceiling");
 check(scripts.wide==1&&scripts.legacy==0,"wide hook fires once, mirror refresh fires none");
 check(!a.ModifyMoney(INT64_MAX)&&durable[{10,false,0}].amount==UINT64_MAX-UINT32_MAX,"overflow refuses without fallback");
 reset(a,b);a.SetMoney(uint64(INT64_MAX)+1);
 check(a.ModifyMoney(INT64_MIN)&&a.GetAccountMoney()==0,"INT64_MIN magnitude is defined");
 reset(a,b);a.SetMoney(10);
 check(!a.ModifyMoney(-11)&&durable[{10,false,0}].amount==10&&a.session.aborted,"insufficient debit does not saturate or save");
 reset(a,b);a.SetMoney(100);commitOk=false;
 {PlayerEconomy::Scope op(&a);a.ModifyMoney(-25);a.inventory=7;WorldPacket p;a.session.SendPacket(&p);check(!op.Finish(),"failed SQL operation reports refusal");}
 check(durable[{10,false,0}].amount==100&&saved[1].first==0&&a.session.aborted&&a.session.delivered==0,"rollback keeps gold and goods together and suppresses success");
 reset(a,b);a.SetMoney(100);
 {PlayerEconomy::Scope op(&a);a.ModifyMoney(-25);a.inventory=7;WorldPacket p;a.session.SendPacket(&p);check(op.Finish(),"successful operation commits");}
 check(durable[{10,false,0}].amount==75&&saved[1].first==7&&a.session.delivered==1,"payment inventory and publication commit together");
 reset(a,b);a.SetMoney(500);
 {PlayerEconomy::Scope op(&a);a.SetMoneyMirror(1);a.SaveToDB(PlayerEconomy::BeginTransaction(),false,false);}
 check(a.GetAccountMoney()==500&&durable[{10,false,0}].amount==500,"loading and saving stale mirror cannot seed ledger");
 reset(a,b);a.SetMoney(100);b.SetMoney(200);
 check(PlayerEconomy::Transfer(&a,&b,40,10)&&a.GetAccountMoney()==70&&b.GetAccountMoney()==230,"trade settles both principals atomically");
 b.account=10;reset(a,b);a.SetMoney(UINT64_MAX);
 check(PlayerEconomy::Transfer(&a,&b,UINT32_MAX,UINT32_MAX)&&a.GetAccountMoney()==UINT64_MAX,"same-account net-zero trade at uint64 maximum");
 b.account=20;b.hardcore=true;reset(a,b);a.SetMoney(100);b.SetMoney(100);
 check(!PlayerEconomy::Transfer(&a,&b,1,0)&&durable[{10,false,0}].amount==100&&durable[{20,true,0}].amount==100,"cross-mode transfer fails unchanged");
 b.hardcore=false;reset(a,b);a.SetMoney(100);
 {PlayerEconomy::Scope op(&a);auto* ctx=dynamic_cast<TestLedger::Operation*>(PlayerEconomy::Current());check(ctx->Adjust({10,false,102000},UINT64_MAX,false),"materials accept full uint64 count");a.ModifyMoney(-20);}
 check(durable[{10,false,102000}].amount==UINT64_MAX&&a.GetAccountMoney()==80,"materials and gold share one durable operation");
 {PlayerEconomy::Scope op(&a);auto* ctx=dynamic_cast<TestLedger::Operation*>(PlayerEconomy::Current());check(!ctx->Adjust({10,false,102000},1,false),"material overflow is checked");PlayerEconomy::Fail();}
 reset(a,b);a.SetMoney(100);durable[{10,false,0}].revision++;
 check(!a.ModifyMoney(-5)&&durable[{10,false,0}].amount==100&&TestLedger::cache.count({10,false,0})==0,"stale revision rolls back and invalidates cache");
 reset(a,b);a.SetMoney(100);throwCommit=true;
 check(!a.ModifyMoney(-5)&&a.session.aborted&&TestLedger::cache.count({10,false,0})==0,"commit exception refuses and evicts uncertain cache");
 reset(a,b);a.SetMoney(0);std::vector<std::unique_ptr<Player>> workers;
 for(uint32 i=0;i<4;++i)workers.push_back(std::make_unique<Player>(100+i,10));
 std::vector<std::thread> threads;std::atomic<bool> ok=true;
 for(auto& p:workers)threads.emplace_back([&,actor=p.get()]{for(int i=0;i<50;++i)if(!PlayerEconomy::Change(actor,1,false))ok=false;});
 for(auto& thread:threads)thread.join();
 check(ok&&a.GetAccountMoney()==200,"concurrent same-account credits do not lose updates");
 check(PlayerEconomy::CreditOffline(1,9)&&a.GetAccountMoney()==209,"offline reward uses the same ledger");
 check(!PlayerEconomy::IsEconomicOpcode(0xffffffff)&&PlayerEconomy::IsEconomicOpcode(CMSG_MESSAGECHAT),"only economic packet dispatch receives broad scope");
}
'''
    for key, value in {"HEADER": header, "CORE": core, "METHODS": methods,
                       "OPERATION": operation, "OPCODES": opcodes}.items():
        code = code.replace(f"@{key}@", value)
    lock = ROOT / "build.lock"
    owner = f"Codex account economy harness {uuid.uuid4()} {time.time()}"
    while True:
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock: inspect owner before continuing")
            print("Waiting for build.lock", flush=True)
            time.sleep(10)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "test.cpp").write_text(code, encoding="utf-8")
        (OUT / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\nproject(account_test LANGUAGES CXX)\n"
            "add_executable(account_test test.cpp)\ntarget_compile_features(account_test PRIVATE cxx_std_17)\n",
            encoding="utf-8")
        env = host_cmake.environment()
        configure, build, binary = host_cmake.commands(OUT, OUT / "build", "account_test")
        for command in (configure, build, [binary]):
            os.utime(lock, None)
            subprocess.run(command, cwd=ROOT, env=env, check=True)
    finally:
        if lock.read_text(encoding="utf-8") == owner:
            lock.unlink()


if __name__ == "__main__":
    main()
