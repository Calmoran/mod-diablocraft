"""Compile extracted production provider/dispatcher and exercise cast isolation.

World objects and formula inputs are doubles; the dispatcher, module provider,
buff expiry and APS calculation are production source, not reimplementations.
"""
import os
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "mod-diablocraft/scripts"))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import host_cmake

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'azerothcore-wotlk/build/_agent-scratch/scripts/primary-provider-tests'

def extract(source,signature):
    start=source.index(signature)
    opening=source.index('{',start)
    depth,end=1,opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}')
        end+=1
    return source[start:end]

def main():
    module=(ROOT/'mod-diablocraft/src/classes/barbarian/dc_barbarian_primaries.cpp').read_text()
    resources=(ROOT/'mod-diablocraft/src/classes/dc_resources.h').read_text()
    dispatcher=(ROOT/'azerothcore-wotlk/src/server/game/Scripting/ScriptDefines/UnitScript.cpp').read_text()
    spell=(ROOT/'azerothcore-wotlk/src/server/game/Spells/Spell.cpp').read_text()
    boundary=spell[spell.index('            uint64 providedDamage = 0;'):spell.index('            Unit::DealDamageMods(damageInfo.target',spell.index('            uint64 providedDamage = 0;'))]
    # Pin native immunity/processed guard and logging/delivery order around the seam.
    target=extract(spell,'void Spell::DoAllEffectOnTarget(')
    assert target.index('target->processed = true') < target.index('ProvideFinalSpellDamage')
    assert target.index('IsImmunedToDamage') < target.index('ProvideFinalSpellDamage')
    assert target.index('ProvideFinalSpellDamage') < target.index('SendSpellNonMeleeDamageLog') < target.index('DealSpellDamage') < target.index('CallScriptAfterHitHandlers')
    code=r'''
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <iostream>
#include <initializer_list>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include "@DATA@"
#include "@RESDATA@"
#include "@RESCARRYH@"
#include <cmath>
#include <list>
#include <map>
#include <utility>
using uint8=uint8_t;using uint32=uint32_t;using uint64=uint64_t;using int32=int32_t;
namespace D=DC::Combat::PrimaryData;using B=D::Behavior;
#define LOG_INFO(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
enum {UNITHOOK_PROVIDE_FINAL_SPELL_DAMAGE};
struct Guid {uint64 value;uint64 GetRawValue() const{return value;}std::string ToString()const{return std::to_string(value);}};
struct Player;
struct SpellInfo {uint32 Id;uint32 SchoolMask=1;};
struct Damage {uint32 damage=0,cleanDamage=0,HitInfo=0,blocked=0;bool physicalLog=false;};
struct Unit {Guid guid;bool onslaught=false;Player* ToPlayer();Guid GetGUID(){return guid;}
 bool HasAura(uint32){return onslaught;}uint32 entry=0;Unit* owner=nullptr;int stockCalls=0;
 uint32 GetEntry(){return entry;}Unit* GetOwner(){return owner;}
 void CalculateSpellDamageTaken(Damage* d,int seed,SpellInfo const*,int,bool crit){++stockCalls;d->damage=seed*(crit?2:1);}};
enum Powers : int {POWER_RAGE=1,POWER_ENERGY=3};
struct Aura {uint32 stacks=0;uint32 GetStackAmount()const{return stacks;}};
struct Player:Unit {int fury=0,loh=0;Aura punish;uint32 punishId=0;
 // Whole Fury points in the slot's units at the registry's scale (one a point since class powers P2).
 static double Scale(){return DC::Resources::Data::Find("Barbarian","fury")->scale;}
 uint32 GetPower(Powers)const{return uint32(fury*Scale());}uint32 GetMaxPower(Powers)const{return uint32(100*Scale());}
 void SetPower(Powers,uint32 power){fury=int(power/Scale());}
 Aura* GetAura(uint32 id){return id==punishId&&punish.stacks?&punish:nullptr;}};
// The resource helper: the production registry row and the production Units/MaxUnits/Add
// (dc_resources.h), so Fury clamping is tested where it lives.
namespace DC::Resources {
 using Resource=Data::Row;using Data::Find;
 inline constexpr Resource const& Fury=*Find("Barbarian","fury");
 inline Powers Slot(Resource const& r){return static_cast<Powers>(r.power);}
 inline double ToUnits(Resource const& r,double points){return points*r.scale;}
 @RESUNITS@
 @RESMAX@
 @RESGET@
 @RESCARRY@;
 @RESCARRIES@;
 @RESSTORE@
 @RESWHOLE@
 @RESADD@
}
namespace Resources=DC::Resources;
namespace Passives {double GenerationFactor(Player*){return 1;}}
namespace Shells {uint32 HelperFor(char const*){return 99001;}struct Ability{uint32 id;char const* skill;char const* rune;double radius;};inline Ability const* FindAbility(uint32){return nullptr;}}
namespace ItemPowers {inline bool GrantsRune(Player const*,std::string const&,std::string const&){return false;}} // no power gives a rune here: test_item_power_undisputed_champion.py drives that
void RecordPreCritHit(Player*,Unit*,double,uint32){}
double DevBoost(Unit const*,double a){return a;} uint64 ExactDamage(double a){return a>0?uint64(a):0;} // the GM multiplier off, and the whole hit as the module's header makes it
Player* Unit::ToPlayer(){return static_cast<Player*>(this);}
struct Spell;
struct UnitScript {UnitScript(char const*,bool,std::initializer_list<int>){}virtual ~UnitScript(){};
 virtual bool ProvideFinalSpellDamage(Spell*,Unit*,Unit*,SpellInfo const*,uint8,uint64&,bool&){return false;}};
template<class T>struct ScriptRegistry {inline static std::vector<T*> EnabledHooks[1];};
struct ScriptMgr {bool ProvideFinalSpellDamage(Spell*,Unit*,Unit*,SpellInfo const*,uint8,uint64&,bool&);};
@DISPATCH@
ScriptMgr mgr;ScriptMgr* sScriptMgr=&mgr;
constexpr unsigned SPELL_SCHOOL_MASK_NORMAL=1,SPELL_HIT_TYPE_CRIT=2,SPELL_MISS_NONE=0,SPELL_MISS_BLOCK=1;
struct Spell {bool forced=false;bool triggered=false;bool IsTriggered()const{return triggered;}Spell* GetSpellValue(){return this;}bool ForcedCritResult=false;
 void Resolve(Unit* caster,Unit* unitTarget,SpellInfo const* m_spellInfo,Damage& damageInfo,bool& critical){
 Unit* m_caster=caster;Unit* unitCaster=caster;int m_damage=17,m_attackType=0,missInfo=SPELL_MISS_NONE;unsigned m_spellSchoolMask=1;uint8 mask=1;
 struct Target {bool crit;};Target t{critical};Target* target=&t;
 @BOUNDARY@
 critical=target->crit;
 }};
struct Hit {double total=100,crit=0,spent=0;uint32 school=1;bool critical=true,offHand=false;std::string Describe()const{return {};}};
bool formulaReady=true,formulaCritical=true;
double hitSawSpent=-1;
bool ComputeHit(Player*,Unit*,uint32,Hit& h){hitSawSpent=h.spent;h.total=100;h.critical=formulaCritical;return formulaReady;}
@PUNISHAURA@
@PUNISHROW@
@FURY@
// Combat::Connected: once per cast that hit (Life per Hit and the item powers' per-attack events, diablocraft-pl8fc)
std::vector<uint32> connected;void Connected(Player* p,uint32 id){++p->loh;connected.push_back(id);}
uint32 now=10000;uint32 getMSTime(){return now;}uint32 getMSTimeDiff(uint32 a,uint32 b){return b-a;}
@ALIVE@
@GIVEN@
@EFFECT@
@FURYGAIN@
@BUFFS@;
@CAST@;
std::mutex mutex;std::unordered_map<uint64,Buffs> buffs;std::unordered_map<Spell*,Cast> casts;
@DAMAGE@
@CRIT@
@APS@
void Movement(Player*,double,unsigned=0){}void ShowFrenzy(Player*,unsigned){}
namespace ItemPowers{double worn=0;double SkillSetTo(Player const*,std::string const&,std::string const&,double base){return worn>base?worn:base;}
 // Blade of the Warlord's take: what the player has up to the cap (the shape of ItemPower::ResourceSpend; the rows are test_item_power_blade_of_the_warlord.py's).
 // The stub records what the provider asked, so the take path runs and its inputs are checked.
 double spendCap=0;int spendCalls=0;double spendSawHave=-1;std::string spendSawSkill;
 double ResourceSpend(Player const*,std::string const& skill,double have){++spendCalls;spendSawHave=have;spendSawSkill=skill;return std::max(0.0,std::min(have,spendCap));}}
namespace Abilities{int spentCalls=0;double spentTotal=0;void Spent(Player*,double fury){++spentCalls;spentTotal+=fury;}}
@MAXSTACKS@
@GRANT@
@SECONDARY@
@PROVIDER@;
struct Decline:UnitScript {Decline():UnitScript("decline",true,{0}){}bool ProvideFinalSpellDamage(Spell*,Unit*,Unit*,SpellInfo const*,uint8,uint64& d,bool& c)override{d=999;c=false;return false;}};
int checks=0;void check(bool x,char const* why){++checks;if(!x)throw std::runtime_error(why);}
int main(){
 Provider provider;Decline decline;Player player;player.guid={1};Unit victim;victim.guid={2};Spell a,b;SpellInfo base{81001},chain{81029},reaping{81041},secondary{D::RUPTURE},stock{57755};
 uint64 damage=7;bool critical=true;
 check(!mgr.ProvideFinalSpellDamage(&a,&player,&victim,&base,1,damage,critical)&&damage==7&&critical,"no providers preserves stock inputs");
 ScriptRegistry<UnitScript>::EnabledHooks[0]={&decline};
 check(!mgr.ProvideFinalSpellDamage(&a,&player,&victim,&base,1,damage,critical)&&damage==7&&critical,"declined mutations isolated");
 Damage log;a.Resolve(&player,&victim,&stock,log,critical);check(player.stockCalls==1&&log.damage==34,"stock fallback crit calculated once");
 ScriptRegistry<UnitScript>::EnabledHooks[0]={&decline,&provider};
 Cast first;first.valid=true;first.serial=1;casts[&a]=first;first.serial=2;casts[&b]=first;
 check(mgr.ProvideFinalSpellDamage(&a,&player,&victim,&chain,1,damage,critical)&&damage==100&&critical,"first chain target");
 for(unsigned i=3;i<6;++i){victim.guid={i};mgr.ProvideFinalSpellDamage(&a,&player,&victim,&chain,1,damage,critical);}
 check(player.fury==6&&player.loh==1&&casts[&a].hits==4,"four chain targets pay one Fury and LoH");
 check(connected==std::vector<uint32>{81029},"four chain targets are one connected cast, of the cast's own spell");
 mgr.ProvideFinalSpellDamage(&b,&player,&victim,&base,1,damage,critical);
 check(player.fury==12&&player.loh==2,"in-flight casts remain independent");
 casts.erase(&a);casts[&a]=first;player.fury=player.loh=0;
 for(int i=0;i<3;++i){victim.guid={uint64(i+2)};mgr.ProvideFinalSpellDamage(&a,&player,&victim,&reaping,1,damage,critical);}
 check(player.fury==8&&player.loh==1,"Reaping three targets pays base six plus two");
 mgr.ProvideFinalSpellDamage(&a,&player,&victim,&reaping,1,damage,critical);
 check(player.fury==8&&player.loh==1,"duplicate target does not generate Fury again");
 casts.erase(&a);casts[&a]=first;
 mgr.ProvideFinalSpellDamage(&a,&player,&victim,&secondary,1,damage,critical);
 check(player.fury==8&&player.loh==1,"secondary cannot pay sustain or Fury");
 formulaReady=false;casts.erase(&b);casts[&b]=first;
 mgr.ProvideFinalSpellDamage(&b,&player,&victim,&base,1,damage,critical);
 check(damage==0&&!critical&&player.loh==1,"missing data fails closed");formulaReady=true;
 casts.erase(&b);mgr.ProvideFinalSpellDamage(&b,&player,&victim,&base,1,damage,critical);
 check(damage==0&&!critical,"missing cast state fails closed");
 casts[&b]=first;critical=false;Damage final;a.ForcedCritResult=true;
 a.Resolve(&player,&victim,&base,final,critical);
 check(final.damage==100&&critical&&player.stockCalls==1&&(final.HitInfo&2),"handled bypasses native calculation with final crit flag");
 formulaCritical=false;critical=true;Damage noncrit;a.Resolve(&player,&victim,&base,noncrit,critical);
 check(noncrit.damage==100&&!critical&&!(noncrit.HitInfo&2),"provider clears crit despite native roll and forced visual crit");
 check(!mgr.ProvideFinalSpellDamage(&a,&player,&victim,&stock,1,damage,critical),"unrelated spells never claimed");
 Buffs buff;buff.frenzy=5;buff.frenzyAt=now;buff.frenzyRune=81023;buffs[1]=buff;
 auto punishRow=PunishRow();check(punishRow!=nullptr,"the data carries a Punish row");
 player.punishId=PunishAura();player.punish.stacks=3;
 double const maniac=5*D::Find(81023)->magnitude,punish=3*punishRow->magnitude;
 check(DamageBonus(&player)==maniac+punish&&maniac>0&&punish>0,"Maniac and Punish additive buckets (Punish read from its aura stacks)");
 check(AttackSpeed(&player,81000,2)==3.5&&AttackSpeed(&player,81002,2)==2,"Frenzy haste only affects Frenzy");
 check(AttackSpeed(&player,81000,4)==5,"APS cap preserved");
 now+=4000;check(AttackSpeed(&player,81000,2)==2&&DamageBonus(&player)==punish,"Frenzy expires exactly at four seconds");
 player.punish.stacks=0;check(DamageBonus(&player)==0,"Punish ends with its aura");
 // Echoing Fury (diablocraft-pl8fc): its stacks are D3's Frenzy buff and speed every attack; Frenzy reads its whole buff once.
 GrantFrenzy(&player,5);
 check(AttackSpeed(&player,81002,2)==3.5&&AttackSpeed(&player,0,2)==3.5,"Echoing Fury's stacks speed every attack and the sheet's speed");
 check(AttackSpeed(&player,81000,2)==3.5,"Frenzy counts Echoing Fury's stacks once, not twice");
 now+=3999;check(AttackSpeed(&player,81002,2)==3.5,"Echoing Fury's stacks last their four seconds");
 buffs[1].frenzyAt=now;now+=1;check(AttackSpeed(&player,81002,2)==2&&AttackSpeed(&player,81000,2)==3.5,"a Frenzy swing does not renew Echoing Fury's stacks for the other attacks");
 GrantFrenzy(&player,2);check(AttackSpeed(&player,81002,2)==2*(1+2*D::frenzy_ias_pct/100),"a new grant after they ended starts from its own stacks");
 // Bastion's Revered (diablocraft-z6znd): the worn power raises Frenzy's limit (ItemPowers::SkillSetTo, stubbed to the power's 10); its own 5 returns without it.
 ItemPowers::worn=10;GrantFrenzy(&player,10);check(buffs[1].frenzy==10&&buffs[1].granted==10,"a worn power holds Echoing Fury's grant to its ten stacks");
 ItemPowers::worn=0;GrantFrenzy(&player,10);check(buffs[1].frenzy==5&&buffs[1].granted==5,"without it the grant is held to Frenzy's own five");
 victim.onslaught=true;check(CritBonus(&victim)==10&&CritBonus(nullptr)==0,"Onslaught is target specific");
 player.fury=99;Fury(&player,9);check(player.fury==100,"Fury saturates at native cap");
 player.fury=1;Fury(&player,-9);check(player.fury==0,"Fury clamps at zero without unsigned wrap");
 // Blade of the Warlord's take (production: if (takes) ... ResourceSpend, then if (takes && hit.spent > 0) the Fury leaves and Abilities::Spent hears of it).
 {
  auto const* bashRow=D::Find(81001);double const grant=FuryGain(&player,*bashRow);
  auto pressed=[&](){Cast c;c.valid=true;c.serial=9;return c;};
  auto reset=[&](Spell& s,double fury,double cap){casts.erase(&s);casts[&s]=pressed();player.fury=int(fury);ItemPowers::spendCap=cap;
   ItemPowers::spendCalls=0;ItemPowers::spendSawHave=-1;ItemPowers::spendSawSkill.clear();Abilities::spentCalls=0;Abilities::spentTotal=0;hitSawSpent=-1;};
  Spell s;victim.guid={50};
  // the cap is below the Fury held: the cap leaves
  reset(s,40,25);mgr.ProvideFinalSpellDamage(&s,&player,&victim,&base,1,damage,critical);
  check(ItemPowers::spendCalls==1&&ItemPowers::spendSawHave==40&&ItemPowers::spendSawSkill==bashRow->skill,"the take asks for the skill's row with the Fury the player holds");
  check(hitSawSpent==25&&casts[&s].spent==25&&casts[&s].paid,"the Fury taken is what the hit is worked out with, and the cast remembers it");
  check(player.fury==40-25+int(grant),"the Fury taken leaves the player before the hit's own gain arrives");
  check(Abilities::spentCalls==1&&Abilities::spentTotal==25,"Abilities::Spent hears of the Fury taken, once");
  // a second target of the same cast does not take again
  int const furyAfter=player.fury;victim.guid={51};
  mgr.ProvideFinalSpellDamage(&s,&player,&victim,&base,1,damage,critical);
  check(ItemPowers::spendCalls==1&&Abilities::spentCalls==1&&player.fury==furyAfter&&hitSawSpent==25,"a pressed cast pays once, for its first hit; later hits keep its figure");
  // the player holds less than the cap: all of it leaves
  reset(s,10,25);victim.guid={52};mgr.ProvideFinalSpellDamage(&s,&player,&victim,&base,1,damage,critical);
  check(ItemPowers::spendSawHave==10&&hitSawSpent==10&&Abilities::spentTotal==10&&player.fury==int(grant),"a player holding less than the cap loses what is held");
  // nothing to take: no Fury moves and Abilities::Spent is not told
  reset(s,40,0);victim.guid={53};mgr.ProvideFinalSpellDamage(&s,&player,&victim,&base,1,damage,critical);
  check(ItemPowers::spendCalls==1&&hitSawSpent==0&&Abilities::spentCalls==0&&player.fury==40+int(grant),"a take of nothing moves no Fury and tells Abilities::Spent nothing");
  // a triggered cast never takes
  reset(s,40,25);s.triggered=true;victim.guid={54};mgr.ProvideFinalSpellDamage(&s,&player,&victim,&base,1,damage,critical);
  check(ItemPowers::spendCalls==0&&Abilities::spentCalls==0&&player.fury==40+int(grant)&&!casts[&s].paid,"a triggered cast takes nothing");s.triggered=false;
  // a secondary shell (no row) carries its cast's figure and takes nothing of its own
  reset(s,40,25);casts[&s].spent=7;victim.guid={55};mgr.ProvideFinalSpellDamage(&s,&player,&victim,&secondary,1,damage,critical);
  check(ItemPowers::spendCalls==0&&Abilities::spentCalls==0&&hitSawSpent==7&&player.fury==40,"a secondary shell takes nothing and works with its cast's figure");
  ItemPowers::spendCap=0;
 }
 std::cout<<"PASS "<<checks<<" production provider/state checks\n";
}
'''
    replacements={'DATA':(ROOT/'mod-diablocraft/src/classes/barbarian/dc_barbarian_primary_data.h').as_posix(),
        'DISPATCH':extract(dispatcher,'bool ScriptMgr::ProvideFinalSpellDamage('),'BOUNDARY':boundary,
        'PROVIDER':extract(module,'class Provider final'), 'SECONDARY':extract(module,'bool Secondary('), 'BUFFS':extract(module,'struct Buffs'),
        'CAST':extract(module,'struct Cast'),
        'RESDATA':(ROOT/'mod-diablocraft/src/classes/dc_resource_data.h').as_posix(),
        'RESCARRYH':(ROOT/'mod-diablocraft/src/classes/dc_resource_carry.h').as_posix(),
        'RESUNITS':extract(resources,'inline std::uint32_t Units('),'RESMAX':extract(resources,'inline std::uint32_t MaxUnits('),
        'RESADD':extract(resources,'inline void Add('),
        'RESCARRY':extract(resources,'struct Owed\n'),'RESCARRIES':extract(resources,'struct Carries'),
        'RESSTORE':extract(resources,'inline Carries& CarryStore('),'RESWHOLE':extract(resources,'inline int32 WholeUnits('),'RESGET':extract(resources,'inline double Get('),
        'PUNISHAURA':extract(module,'uint32 PunishAura('),'PUNISHROW':extract(module,'D::Row const* PunishRow('), 'ALIVE':extract(module,'bool Alive('),'GIVEN':extract(module,'bool Given('),'EFFECT':extract(module,'D::Row const* Effect('),'FURYGAIN':extract(module,'double FuryGain('),
        'DAMAGE':extract(module,'double DamageBonus('),'CRIT':extract(module,'double CritBonus('),
        'MAXSTACKS':extract(module,'unsigned MaxStacks('),'APS':extract(module,'double AttackSpeed('),'GRANT':extract(module,'void GrantFrenzy('),'FURY':extract(module,'void Fury(')}
    for key,value in replacements.items():code=code.replace('@'+key+'@',value)
    lock=ROOT/'build.lock';owner=f'Codex Primaries harness {os.getpid()} {time.time()}'
    while True:
        try:
            with lock.open('x') as stream:stream.write(owner)
            break
        except FileExistsError:
            if time.time()-lock.stat().st_mtime>=1800:raise RuntimeError('Stale build.lock; inspect owner')
            print('Waiting for server build lock',flush=True);time.sleep(10)
    try:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'test.cpp').write_text(code)
        (OUT/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(primary_test LANGUAGES CXX)\nadd_executable(primary_test test.cpp)\ntarget_compile_features(primary_test PRIVATE cxx_std_17)\n')
        env=host_cmake.environment()
        configure,build,binary=host_cmake.commands(OUT,OUT/'build','primary_test')
        for command in (configure,build,[binary]):
            os.utime(lock,None);subprocess.run(command,env=env,check=True)
    finally:
        if lock.read_text()==owner:lock.unlink()

if __name__=='__main__':main()
