"""Execute the installed transmog purchase methods with failing persistence/payment.

The C++ methods are extracted, not reimplemented; database and world objects are
test doubles. Server compilation and the designer's live test remain separate gates.
"""
from pathlib import Path
import os
import subprocess
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mod-diablocraft/scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import host_cmake

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "azerothcore-wotlk/modules/mod-transmog/src"
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/transmog-payment-tests"


def extract(text: str, signature: str) -> str:
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main() -> None:
    source = (SRC / "Transmogrification.cpp").read_text(encoding="utf-8")
    methods = extract(source, "bool Transmogrification::SetFakeEntry(")
    methods += "\n" + extract(source, "TransmogStrings Transmogrification::Transmogrify(Player* player, Item* ")
    gossip = (SRC / "transmog_scripts.cpp").read_text(encoding="utf-8")
    begin = gossip.index("                std::ostringstream ss;", gossip.index("std::string name(code)"))
    end = gossip.index("                break;\n            }\n        }", begin)
    preset = gossip[begin:end]
    code = r'''
#include <cstdint>
#include <future>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <iostream>
using uint8=std::uint8_t; using uint32=std::uint32_t;
using int32=std::int32_t; using int64=std::int64_t;
using TransmogStrings=int;
enum { LANG_TRANSMOG_OK, LANG_TRANSMOG_INVALID_SLOT, LANG_TRANSMOG_MISSING_DEST_ITEM,
 LANG_TRANSMOG_NOT_ENOUGH_MONEY, LANG_TRANSMOG_NOT_ENOUGH_TOKENS, LANG_TRANSMOG_INVALID_ITEMS };
constexpr int EQUIPMENT_SLOT_END=19, INVENTORY_SLOT_BAG_0=0, HIDDEN_ITEM_ID=1,
 BIND_WHEN_EQUIPPED=2,BIND_WHEN_USE=3;
#define LOG_DEBUG(...) ((void)0)
struct ObjectGuid { uint32 n=1; uint32 GetCounter()const{return n;} bool operator<(ObjectGuid b)const{return n<b.n;} };
struct Player;
struct Template { int Bonding=0; };
struct Item {
 Template proto; Template* GetTemplate(){return &proto;} ObjectGuid GetGUID(){return {};}
 uint32 GetEntry(){return 10;} void UpdatePlayedTime(Player*){} void SetOwnerGUID(ObjectGuid){}
 void SetNotRefundable(Player*){} void ClearSoulboundTradeable(Player*){} void SetBinding(bool){}
};
struct Session {};
bool writeOk=true, debitOk=true; int writes=0, charges=0, updates=0, notices=0;
struct Player {
 int64 money=1000; uint32 tokens=1; Item item; Session session;
 ObjectGuid GetGUID(){return {};} std::string GetName(){return "test";}
 Item* GetItemByPos(int,int){return &item;} bool HasEnoughMoney(int64 cost){return money>=cost;}
 bool ModifyMoney(int64 amount,bool=true){++charges;if(!debitOk)return false;money+=amount;return true;}
 bool HasItemCount(uint32,uint32 count){return tokens>=count;}
 void DestroyItemCount(uint32,uint32 count,bool){tokens-=count;} Session* GetSession(){return &session;}
};
struct Tx { template<class... T> void Append(char const*,T const&...){} };
struct DB {
 std::shared_ptr<Tx> BeginTransaction(){return std::make_shared<Tx>();}
 struct Result { std::future<bool> m_future; };
 Result AsyncCommitTransaction(std::shared_ptr<Tx>){++writes;std::promise<bool> p;p.set_value(writeOk);return {p.get_future()};}
} CharacterDatabase;
struct ChatHandler { ChatHandler(Session*){} void SendNotification(int){++notices;} };
int Tstr(Session*,int value){return value;}
class Transmogrification {
public:
 bool HiddenTransmogIsFree=false,RequireToken=false;
 double ScaledCostModifier=1; int32 CopperCost=0; uint32 TokenEntry=1,TokenAmount=1;
 std::map<ObjectGuid,std::map<ObjectGuid,uint32>> entryMap;
 std::map<ObjectGuid,ObjectGuid> dataMap;
 std::map<ObjectGuid,std::map<uint8,std::map<uint8,uint32>>> presetById;
 std::map<ObjectGuid,std::map<uint8,std::string>> presetByName;
 int32 GetSpecialPrice(Template*){return 10;}
 bool CanTransmogrifyItemWithItem(Player*,Template*,Template*){return true;}
 void UpdateItem(Player*,Item*){++updates;} void DeleteFakeEntry(Player*,uint8,Item*){}
 bool SetFakeEntry(Player*,uint32,uint8,Item*);
 TransmogStrings Transmogrify(Player*,Item*,uint8,bool,bool);
};
@METHODS@
void Preset(Transmogrification* sT,Player* player) {
 uint8 presetID=0; int32 cost=10;std::string name="test";std::map<uint8,uint32> items={{0,10}};
 do {
 @PRESET@
 } while(false);
}
void check(bool b,char const* msg){if(!b)throw std::runtime_error(msg);std::cout<<"PASS "<<msg<<'\n';}
void reset(){writeOk=debitOk=true;writes=charges=updates=notices=0;}
int main(){
 for(bool hidden:{false,true}) {
  reset();Transmogrification t;Player p;Item appearance;
  check(t.Transmogrify(&p,&appearance,0,false,hidden)==LANG_TRANSMOG_OK && p.money==990 && writes==1 && charges==1,"paid appearance success");
  reset();p.money=1000;writeOk=false;
  check(t.Transmogrify(&p,&appearance,0,false,hidden)!=LANG_TRANSMOG_OK && p.money==1000 && charges==0 && updates==0,"write failure cannot charge");
  reset();p.money=1000;debitOk=false;
  check(t.Transmogrify(&p,&appearance,0,false,hidden)==LANG_TRANSMOG_NOT_ENOUGH_MONEY && p.money==1000 && writes==1,"failed debit returns refusal; stored cosmetic may be free");
  reset();p.money=0;
  check(t.Transmogrify(&p,&appearance,0,false,hidden)==LANG_TRANSMOG_NOT_ENOUGH_MONEY && writes==0 && charges==0,"insufficient balance refuses before write");
 }
 reset();Transmogrification t;Player p;Preset(&t,&p);
 check(p.money==990 && charges==1 && t.presetByName.size()==1,"preset success");
 reset();t={};p.money=1000;writeOk=false;Preset(&t,&p);
 check(p.money==1000 && charges==0 && t.presetByName.empty(),"preset write failure does not charge or publish");
 reset();t={};debitOk=false;Preset(&t,&p);
 check(p.money==1000 && notices==1 && t.presetByName.empty(),"preset debit failure reports refusal");
 reset();t={};p.money=1000;t.RequireToken=true;writeOk=false;Item appearance;
 t.Transmogrify(&p,&appearance,0,false,false);
 check(p.tokens==1 && p.money==1000,"failed appearance write preserves tokens and gold");
}
'''.replace("@METHODS@", methods).replace("@PRESET@", preset)
    lock = ROOT / "build.lock"
    owner = f"Codex transmog tests {uuid.uuid4()} {time.time()}"
    while True:
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock; inspect owner before proceeding")
            print("Waiting for build.lock", flush=True)
            time.sleep(10)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "test.cpp").write_text(code, encoding="utf-8")
        (OUT / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\nproject(transmog_test LANGUAGES CXX)\n"
            "add_executable(transmog_test test.cpp)\ntarget_compile_features(transmog_test PRIVATE cxx_std_17)\n",
            encoding="utf-8")
        env = host_cmake.environment()
        configure, build, binary = host_cmake.commands(OUT, OUT / "build", "transmog_test")
        for command in (configure, build, [binary]):
            os.utime(lock, None)
            subprocess.run(command, cwd=ROOT, env=env, check=True)
    finally:
        if lock.read_text(encoding="utf-8") == owner:
            lock.unlink()


if __name__ == "__main__":
    main()
