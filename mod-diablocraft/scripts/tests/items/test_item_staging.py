"""Compile and exercise the actual staged-roll lifecycle against world doubles."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "mod-diablocraft/scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import host_cmake

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "azerothcore-wotlk/build/_agent-scratch/scripts/item-staging-tests"


def main() -> None:
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("transmog_tests", ROOT / "core-patches/tests/test_transmog_payment.py")
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    cpp = items_source.read("dc_items_roll.cpp")
    methods = helper.extract(cpp, "StagedRoll::~StagedRoll()") + "\n" + helper.extract(cpp, "Item* StagedRoll::Publish()")
    stage = helper.extract(cpp, "std::unique_ptr<StagedRoll> StageRoll(")
    assert "CommitTransaction" not in stage and "player->StoreNewItem(" not in stage
    assert "transaction->Append" in stage
    wrapper = helper.extract(cpp, "Item* RollItem(")
    assert wrapper.index("AsyncCommitTransaction") < wrapper.index("staged->Publish()")
    code = r'''
#include <cstdint>
#include <map>
#include <mutex>
#include <iostream>
#include <stdexcept>
enum {ITEM_CHANGED, ACHIEVEMENT_CRITERIA_TYPE_RECEIVE_EPIC_ITEM,
ACHIEVEMENT_CRITERIA_TYPE_OWN_ITEM,ADDITIONAL_SAVING_INVENTORY_AND_GOLD};
struct Guid { std::uint64_t GetRawValue(){return 1;} std::uint64_t GetCounter(){return 2;} };
int deleted=0, removed=0, dequeued=0, sent=0, added=0, quests=0, criteria=0, saves=0,hooks=0;
struct Player;
struct Bag {bool dirty=false;void SetState(int,Player*){dirty=true;}};
struct Item {
 Bag* bag=nullptr;bool world=false;
 ~Item(){++deleted;} Bag* GetContainer(){return bag;}
 int GetBagSlot(){return 1;} int GetSlot(){return 2;}
 void RemoveFromUpdateQueueOf(Player*){++dequeued;}
 bool IsInWorld(){return world;} void RemoveFromWorld(){world=false;}
 void AddToWorld(){world=true;++added;} void SendUpdateToPlayer(Player*){++sent;}
 int GetEntry(){return 100;} Guid GetGUID(){return {};}
};
struct Player {
 bool world=true; bool IsInWorld(){return world;} Guid GetGUID(){return {};}
 void RemoveItem(int,int,bool){++removed;} void ItemAddedQuestCheck(int,int){++quests;}
 void UpdateAchievementCriteria(int,int,int){++criteria;}void AdditionalSavingAddMask(int){++saves;}
};
struct Scripts {void OnPlayerStoreNewItem(Player*,Item*,int){++hooks;}} scripts;
auto* sScriptMgr=&scripts;std::mutex lastMutex;std::map<std::uint64_t,std::uint64_t> lastRolled;
class StagedRoll {
 Player* player_;Item* item_;bool published_=false;
 public:StagedRoll(Player* p,Item* i):player_(p),item_(i){}~StagedRoll();Item* Publish();
};
@METHODS@
void check(bool ok,char const* message){if(!ok)throw std::runtime_error(message);std::cout<<"PASS "<<message<<'\n';}
int main(){
 Player p;Bag bag;
 {auto* item=new Item;item->bag=&bag;StagedRoll staged(&p,item);}
 check(deleted==1 && removed==1 && dequeued==1 && bag.dirty,"discard removes only staged item and repairs bag save state");
 check(hooks==0 && sent==0 && quests==0 && lastRolled.empty(),"discard never publishes reward or last-roll state");
 Item* kept=new Item;
 {StagedRoll staged(&p,kept);check(staged.Publish()==kept && staged.Publish()==kept,"publish returns same item and is idempotent");}
 check(deleted==1 && hooks==1 && sent==1 && quests==1 && criteria==2 && saves==1,"successful publication notifies once and transfers ownership");
 check(lastRolled[1]==2,"last-roll state published only on success");
 delete kept;
 p.world=false;kept=new Item;
 {StagedRoll staged(&p,kept);staged.Publish();}
 check(sent==1 && added==1 && hooks==2,"loading player publishes hooks without premature world packets");
 delete kept;
}
'''.replace("@METHODS@", methods)
    lock = ROOT / "build.lock"
    owner = f"Codex item staging {uuid.uuid4()} {time.time()}"
    while True:
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(owner)
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime >= 1800:
                raise RuntimeError("Stale build.lock; inspect owner")
            print("Waiting for build.lock", flush=True)
            time.sleep(10)
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "test.cpp").write_text(code, encoding="utf-8")
        (OUT / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\nproject(item_staging_test LANGUAGES CXX)\n"
            "add_executable(item_staging_test test.cpp)\ntarget_compile_features(item_staging_test PRIVATE cxx_std_17)\n", encoding="utf-8")
        configure, build, binary = host_cmake.commands(OUT, OUT / "build", "item_staging_test")
        for command in (configure, build, [binary]):
            os.utime(lock, None)
            subprocess.run(command, cwd=ROOT, env=host_cmake.environment(), check=True)
    finally:
        if lock.read_text(encoding="utf-8") == owner:
            lock.unlink()


if __name__ == "__main__":
    main()
