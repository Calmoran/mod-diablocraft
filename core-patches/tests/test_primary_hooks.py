"""Execute extracted DR dispatch, admission, finite-line and movement hooks.

No game server is started. Lightweight world/spline doubles exercise the actual
production methods; live client parabolic rendering remains the designer's acceptance.
"""
from pathlib import Path
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'mod-diablocraft/scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_primary_provider import extract
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mod-diablocraft/scripts"))
import host_cmake

def main():
    game=ROOT/'azerothcore-wotlk/src/server/game'
    dispatch=(game/'Scripting/ScriptDefines/UnitScript.cpp').read_text()
    spell=(game/'Spells/Spell.cpp').read_text()
    motion=(game/'Movement/MovementGenerators/PointMovementGenerator.cpp').read_text()
    spline=(game/'Movement/Spline/MoveSpline.cpp').read_text()
    combat=(ROOT/'mod-diablocraft/src/combat/dc_combat.cpp').read_text()
    internal=(ROOT/'mod-diablocraft/src/combat/dc_combat_internal.h').read_text()
    application=extract(spell,'SpellMissInfo Spell::DoSpellHitOnUnit(')
    assert application.index('IsSpellDiminishingExempt') < application.index('IncrDiminishing')
    assert application.index('IsSpellDiminishingExempt') < application.index('ApplyDiminishingToDuration')
    check=extract(combat,'class CombatCastCheck final')
    assert 'Slotted(player, spell->GetSpellInfo()->Id)' in check
    assert 'SPELL_FAILED_NOT_KNOWN' in check
    code=r'''
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "@DATA@"
using uint8=uint8_t;using uint32=uint32_t;using uint64=uint64_t;
struct Position {float x=0,y=0;float GetPositionX()const{return x;}float GetPositionY()const{return y;}};
struct Spell{};struct SpellInfo{};
struct Spline {uint32 id=5;bool done=true;int passed=100,duration=100;
 uint32 GetId(){return id;}bool Finalized(){return done;}int timePassed(){return passed;}int Duration(){return duration;}bool isFalling(){return false;}};
struct AI {int calls=0;void MovementInform(int,uint32){++calls;}};
struct Guid {uint64 id=1;uint64 GetRawValue()const{return id;}};
struct Unit {Spline state;Spline* movespline=&state;struct AI ai;
 bool IsCreature(){return true;}bool HasUnitMovementFlag(int){return false;}void RemoveUnitMovementFlag(int){}
 Unit* ToCreature(){return this;}struct AI* AI(){return &ai;}
 bool los=true;bool IsWithinLOSInMap(void*){return los;}};
struct WorldObject:Position {bool valid=true;};
enum {UNITHOOK_IS_SPELL_DIMINISHING_EXEMPT,UNITHOOK_PROVIDE_SPELL_LINE_GEOMETRY};
struct UnitScript {virtual ~UnitScript(){};
 virtual bool IsSpellDiminishingExempt(Spell*,Unit*,Unit*,SpellInfo const*){return false;}
 virtual bool ProvideSpellLineGeometry(Spell*,uint8,Unit*,Position&,float&,float&,float&){return false;}};
template<class T>struct ScriptRegistry {inline static std::vector<T*> EnabledHooks[2];};
struct ScriptMgr {bool notified=false,completed=false;uint32 spline=0;
 bool IsSpellDiminishingExempt(Spell*,Unit*,Unit*,SpellInfo const*);
 bool ProvideSpellLineGeometry(Spell*,uint8,Unit*,Position&,float&,float&,float&);
 void OnEffectMovementFinalized(Unit*,uint32,uint32 id,bool c){notified=true;completed=c;spline=id;}} mgr;
auto sScriptMgr=&mgr;
@DR@
@DISPATCH@
struct Exempt:UnitScript {bool IsSpellDiminishingExempt(Spell*,Unit*,Unit*,SpellInfo const*)override{return true;}};
struct DecliningLine:UnitScript {bool ProvideSpellLineGeometry(Spell*,uint8,Unit*,Position& o,float& d,float& l,float& w)override{o.x=99;d=l=w=99;return false;}};
struct Line:UnitScript {bool ProvideSpellLineGeometry(Spell*,uint8,Unit*,Position& o,float& d,float& l,float& w)override{o.x=10;o.y=20;d=0;l=26;w=1;return true;}};
namespace Acore {
struct WorldObjectSpellTargetCheck {bool operator()(WorldObject* t){return t->valid;}};
struct WorldObjectSpellLineTargetCheck:WorldObjectSpellTargetCheck {Position _origin;float _direction=0,_length=26,_width=1;Unit* _caster;
 bool operator()(WorldObject*);};
@LINE@
}
enum {MOVEMENTFLAG_FALLING,EFFECT_MOTION_TYPE};
struct EffectMovementGenerator {uint32 m_Id=81201,m_splineId=5;bool m_launched=true;void Finalize(Unit*);};
@FINALIZE@
float MSToSec(int v){return v/1000.f;}
namespace Movement {struct MoveSpline {int time_passed=0,effect_start_time=0,duration=1000;float vertical_acceleration=16;
 int Duration()const{return duration;}void computeParabolicElevation(float&)const;};
@PARABOLA@
}
struct CommonInitializer {explicit CommonInitializer(float){}};
struct TimestampSpline {std::vector<int> lengths;int first(){return 0;}int last(){return 1;}
 void initLengths(CommonInitializer&){lengths.resize(2);}
 void set_length(int index,int value){lengths.at(index)=value;}};
struct StationaryTiming {TimestampSpline spline;int point_Idx=-1;
 struct Args {int explicitDuration=900;float velocity=7;} args;
 void initialize(){@TIMING@}};
struct Player:Unit {};
namespace Classes {struct Slot {uint32 spellId=0;};std::vector<Slot> bar(6);auto Bar(Player*){return bar;}}
constexpr uint32 FIRST_SHELL=81000,LAST_ACTIVE_SHELL=81137;
namespace Shells {struct Ability{};Ability const* FindAbility(uint32 id){static Ability a;return id>=FIRST_SHELL&&id<=LAST_ACTIVE_SHELL?&a:nullptr;}}
@SLOTTED@
int checks=0;
void check(bool pass,char const* name){++checks;if(!pass)throw std::runtime_error(name);}
int main(){
 Unit unit;Spell spell;SpellInfo info;
 check(!mgr.IsSpellDiminishingExempt(&spell,&unit,&unit,&info),"unhandled DR unchanged");
 Exempt exempt;ScriptRegistry<UnitScript>::EnabledHooks[0]={&exempt};
 check(mgr.IsSpellDiminishingExempt(&spell,&unit,&unit,&info),"module DR exemption handled");
 Position origin{1,2};float direction=3,length=4,width=5;DecliningLine decline;Line line;
 ScriptRegistry<UnitScript>::EnabledHooks[1]={&decline};
 check(!mgr.ProvideSpellLineGeometry(&spell,0,&unit,origin,direction,length,width)&&origin.x==1&&direction==3&&length==4&&width==5,"declining line mutations isolated");
 ScriptRegistry<UnitScript>::EnabledHooks[1].push_back(&line);
 check(mgr.ProvideSpellLineGeometry(&spell,0,&unit,origin,direction,length,width)&&origin.x==10&&length==26&&width==1,"handled geometry copied");
 Acore::WorldObjectSpellLineTargetCheck beam;beam._caster=&unit;beam._origin=origin;
 WorldObject victim;victim.x=10;victim.y=20;
 check(beam(&victim),"victim-origin start");victim.x=36;victim.y=20.5f;
 check(beam(&victim),"exact end and half width included");victim.x=36.01f;
 check(!beam(&victim),"beyond line end excluded");victim.x=9.99f;victim.y=20;
 check(!beam(&victim),"behind origin excluded");victim.x=25;victim.y=20.51f;
 check(!beam(&victim),"full width is one yard not two");victim.y=20;unit.los=false;
 check(!beam(&victim),"LOS retained");unit.los=true;victim.valid=false;
 check(!beam(&victim),"native target validity retained");victim.valid=true;
 beam._direction=float(std::acos(-1)/2);victim.x=10;victim.y=30;
 check(beam(&victim),"rotated line");
 EffectMovementGenerator movement;movement.Finalize(&unit);
 check(mgr.notified&&mgr.completed&&mgr.spline==5&&unit.ai.calls==1,"exact completed spline and native AI callback");
 unit.state.passed=50;movement.Finalize(&unit);check(!mgr.completed,"interruption does not land");
 unit.state.passed=100;unit.state.id=6;movement.Finalize(&unit);check(!mgr.completed,"replacement does not land");
 unit.state.id=5;movement.m_launched=false;movement.Finalize(&unit);check(!mgr.completed,"failed launch does not land");
 Movement::MoveSpline parabola;float z=0;parabola.computeParabolicElevation(z);check(z==0,"parabola begins at ground");
 parabola.time_passed=500;parabola.computeParabolicElevation(z);check(z==2,"two yard peak");
 z=0;parabola.time_passed=1000;parabola.computeParabolicElevation(z);check(z==0,"parabola returns to ground");
 StationaryTiming timing;timing.initialize();
 check(timing.spline.lengths.at(0)==0&&timing.spline.lengths.at(1)==900&&timing.point_Idx==0,"stationary timestamps allocated and set before use");
 Player player;for(uint32 id=81000;id<=81137;++id){check(!Slotted(&player,id),"every unslotted base/rune refused");Classes::bar[0].spellId=id;check(Slotted(&player,id),"every slotted shell admitted");Classes::bar[0].spellId=0;}
 check(Slotted(&player,81188),"internal secondary excluded from six-slot gate");
 std::cout<<"PASS "<<checks<<" production core/admission checks\n";
}
'''
    replacements={
        'DATA':(ROOT/'mod-diablocraft/src/classes/barbarian/dc_barbarian_primary_data.h').as_posix(),
        'DR':extract(dispatch,'bool ScriptMgr::IsSpellDiminishingExempt('),
        'DISPATCH':extract(dispatch,'bool ScriptMgr::ProvideSpellLineGeometry('),
        'LINE':extract(spell,'bool WorldObjectSpellLineTargetCheck::operator()('),
        'FINALIZE':extract(motion,'void EffectMovementGenerator::Finalize('),
        'PARABOLA':extract(spline,'void MoveSpline::computeParabolicElevation('),
        'TIMING':extract(spline,'if (args.explicitDuration > 0)'),
        'SLOTTED':extract(internal,'bool Slotted(')}
    for key,value in replacements.items():code=code.replace('@'+key+'@',value)
    out=ROOT/'azerothcore-wotlk/build/_agent-scratch/scripts/primary-core-tests'
    out.mkdir(parents=True,exist_ok=True)
    (out/'test.cpp').write_text(code)
    (out/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(primary_core_test LANGUAGES CXX)\nadd_executable(primary_core_test test.cpp)\ntarget_compile_features(primary_core_test PRIVATE cxx_std_17)\n')
    lock=ROOT/'build.lock';owner=f'Codex Primaries core harness {os.getpid()} {time.time()}'
    while True:
        try:
            with lock.open('x') as stream:stream.write(owner)
            break
        except FileExistsError:
            if time.time()-lock.stat().st_mtime>=1800:raise RuntimeError('Stale build.lock; inspect owner')
            print('Waiting for server build lock',flush=True);time.sleep(10)
    try:
        env=host_cmake.environment()
        configure,build,binary=host_cmake.commands(out,out/'build','primary_core_test')
        for command in (configure,build,[binary]):
            os.utime(lock,None);subprocess.run(command,env=env,check=True)
    finally:
        if lock.read_text()==owner:lock.unlink()

if __name__=='__main__':main()
