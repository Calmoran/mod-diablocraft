"""Compile actual economy payment helpers against a small player host stub."""
import csv
from pathlib import Path
import os
import shutil
import subprocess
import time
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]


def main():
    out = ROOT/'azerothcore-wotlk/build/_agent-scratch/scripts/jeweler-economy-tests'
    out.mkdir(parents=True, exist_ok=True)
    source = (ROOT/'mod-diablocraft/src/common/dc_economy.cpp').read_text(encoding='utf-8')
    methods = source[source.index('    std::uint64_t Balance('):source.index('    bool Credit(')]
    header = (ROOT/'mod-diablocraft/src/common/dc_economy.h').as_posix()
    # CopperPerBar() reads dc_account_economy_kind on the server; that table is generated
    # from this CSV row, so the harness takes the same value.
    with (ROOT/'mod-diablocraft/data/d3/account_economy.csv').open(encoding='utf-8', newline='') as sheet:
        bar = int(next(r['copper_per_item'] for r in csv.DictReader(sheet) if r['kind'] == 'retired_gold'))
    test = r'''
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include "@HEADER@"
using uint32=std::uint32_t;using uint64=std::uint64_t;using int64=std::int64_t;
struct Player {
    uint32 cash=0,bars=0;uint64 account=0;bool denySet=false;int writes=0;
    uint32 GetMoney() const{return cash;}
    uint64 GetAccountMoney() const{return account;}
    uint32 GetItemCount(uint32,bool) const{return bars;}
    bool SetMoney(uint32 n){if(denySet)return false;cash=n;++writes;return true;}
    void DestroyItemCount(uint32,uint32 n,bool){bars-=n;++writes;}
    bool ModifyMoney(int64 n){if(n<0 && account<uint64(-n))return false;account+=n;++writes;return true;}
};
namespace DC::AccountEconomy {bool enabled=false,eligible=false;bool Enabled(){return enabled;}bool Eligible(Player const*){return eligible;}}
namespace PlayerEconomy {bool Change(Player*,uint64,bool){return false;}}
namespace DC::Economy {
std::uint64_t CopperPerBar(){return @BAR@;}
@METHODS@
}
void need(bool ok){if(!ok)throw std::runtime_error("Payment regression");}
int main(){
    using namespace DC::Economy;
    Player p;
    need(!CanAfford(nullptr,0) && !Charge(nullptr,0));
    need(CanAfford(&p,0));
    need(!Charge(&p,1) && p.writes==0);
    p.cash=4294967295u;p.bars=1;
    auto before=Balance(&p);
    // Cost within the copper on hand: paid from copper, the bar untouched.
    need(Charge(&p,GoldCost(500000)) && p.cash==4294467295u && p.bars==1);
    need(before-Balance(&p)==GoldCost(500000));
    // Cost above the copper on hand: the fewest bars are broken and the change
    // comes back as copper. One bar is 100,000 gold (decisions.md 2026-09-12).
    p.cash=1;p.bars=5;
    need(Charge(&p,GoldCost(150000)) && p.cash==50001u && p.bars==3);
    p.cash=123;p.bars=1;before=Balance(&p);auto writes=p.writes;
    need(!Charge(&p,before+1) && Balance(&p)==before && p.writes==writes);
    p.denySet=true;need(!Charge(&p,1000) && Balance(&p)==before && p.writes==writes);p.denySet=false;
    p.cash=0;p.bars=2147483647u;before=Balance(&p);
    need(Charge(&p,before) && p.cash==0 && p.bars==0);
    // 2026-09-12: one copper is one gold, so the conversion is the identity and
    // can no longer overflow. The guard stays for the day the factor returns.
    need(GoldCost(UINT64_MAX)==UINT64_MAX && GoldCost(2000)==2000);
    DC::AccountEconomy::enabled=true;p.account=GoldCost(500000);p.cash=123;p.bars=9;
    need(!CanAfford(&p,1) && !Charge(&p,1));
    DC::AccountEconomy::eligible=true;need(Charge(&p,GoldCost(500000)) && p.account==0 && p.cash==123 && p.bars==9);
    std::cout<<"PASS actual payment helpers: disabled-mode native gold/bars at the 2026-09-12 unit, bar break with exact change, refusal without mutation, large holdings, identity conversion and unchanged account-mode routing\n";
}
'''.replace('@BAR@', str(bar)).replace('@HEADER@', header).replace('@METHODS@', methods)
    (out/'test.cpp').write_text(test, encoding='utf-8')
    lock=ROOT/'build.lock';owner=f'Codex Jeweler payment test {uuid.uuid4()} {time.ctime()}'
    while True:
        try:
            with lock.open('x', encoding='utf-8') as stream: stream.write(owner)
            break
        except FileExistsError:
            if time.time()-lock.stat().st_mtime>=1800: raise RuntimeError('Stale build.lock; inspect owner')
            print('Waiting for build.lock', flush=True);time.sleep(10)
    try:
        env={k.upper():v for k,v in os.environ.items()}
        # One translation unit: g++ (or clang++) directly, no VS2022 project.
        compiler=shutil.which('g++') or shutil.which('clang++')
        if not compiler: raise SystemExit('no C++ compiler on PATH')
        binary=out/'jeweler_payment'
        result=subprocess.run([compiler,'-std=c++17','-Wall','-Wextra',str(out/'test.cpp'),'-o',str(binary)],capture_output=True,text=True,env=env)
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        harness_env.run([str(binary)],check=True,env=env)
    finally:
        if lock.read_text(encoding='utf-8')==owner: lock.unlink()


if __name__ == '__main__':
    main()
