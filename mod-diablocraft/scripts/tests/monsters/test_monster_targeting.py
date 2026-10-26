#!/usr/bin/env python3
"""Targeting generator and production policy tests, without a core/server build.

The policy harness is an isolated standard-library-only executable in scratch;
it includes the production header, and never links or modifies worldserver.
"""
import copy
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import shutil
import tempfile
import unittest
from unittest.mock import patch

import generate_monster_targeting as generator

ROOT = Path(__file__).resolve().parents[4]
AI = ROOT / 'mod-diablocraft/src/monsters/dc_monster_ai.cpp'
HEADER = ROOT / 'mod-diablocraft/src/rifts/dc_monster_targeting.h'


class GeneratorTests(unittest.TestCase):
    def test_world_schema_and_csv_wins_on_reapply(self):
        # Ruling 2026-09-19: monster_targeting.csv is in data/tunables/ and the
        # sheet is the source of truth, so every profile number is refreshed on
        # a re-apply, not only source and notes.
        schema, seed = generator.render()
        for column in generator.COLUMNS:
            self.assertIn(column + ' DOUBLE NOT NULL', schema)
            self.assertIn(column + '=VALUES(' + column + ')',
                          seed.split('ON DUPLICATE KEY UPDATE')[1])
        self.assertNotIn('INSERT', schema)
        self.assertNotIn('CREATE TABLE', seed)
        self.assertNotIn('dc_loot_buffer', schema + seed)
        self.assertEqual(seed.count("the designer''s tunables 2026-09-18"), 3)

    def test_profiles_and_numeric_provenance(self):
        rows = generator.validate(generator.read())
        self.assertEqual({r['profile'] for r in rows}, {'normal', 'elite', 'guardian'})
        for row in rows:
            for key in generator.COLUMNS:
                self.assertGreaterEqual(float(row[key]), 0)

    def test_reject_nonfinite_negative_and_invalid_ranges(self):
        for key, value in [('lock_seconds', '0'), ('recency_window_seconds', '0'),
                           ('candidate_max_yards', '0'), ('jitter_percent', '100'),
                           ('switch_margin', '-1'), ('recency_weight', 'nan'),
                           ('reachability_weight', 'inf'), ('recency_max_yards', '100000'),
                           ('lock_seconds', '1.7e308')]:
            with self.subTest(key=key, value=value):
                rows = copy.deepcopy(generator.read())
                rows[0][key] = value
                with self.assertRaises(ValueError):
                    generator.validate(rows)

    def test_zero_weights_allowed_but_guardian_must_be_stricter(self):
        rows = generator.read()
        for row in rows:
            for key in ('recency_weight', 'proximity_weight', 'reachability_weight'):
                row[key] = '0'
        generator.validate(rows)
        for key in ('lock_seconds', 'switch_margin'):
            invalid = copy.deepcopy(rows)
            invalid[2][key] = invalid[0][key]
            with self.assertRaises(ValueError):
                generator.validate(invalid)

    def test_missing_duplicate_and_unsourced_profiles_rejected(self):
        rows = generator.read()
        cases = [rows[:2], rows + [rows[0]], [rows[0], rows[0], rows[2]]]
        unsourced = copy.deepcopy(rows)
        unsourced[0]['source'] = 'D3 derived'
        cases.append(unsourced)
        for invalid in cases:
            with self.assertRaises(ValueError):
                generator.validate(invalid)

    def test_repeatable_outputs_and_no_writes_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as folder:
            generated = Path(folder) / 'generated'
            updates = Path(folder) / 'db-world/updates'
            with patch.object(generator, 'GENERATED', generated), patch.object(generator, 'UPDATES', updates):
                generator.main()
                before = {p.name: p.read_bytes() for p in updates.iterdir()}
                generator.main()
                self.assertEqual(before, {p.name: p.read_bytes() for p in updates.iterdir()})
                for p in updates.iterdir():
                    self.assertEqual(p.read_bytes(), (generated / p.name).read_bytes())
                with patch.object(generator, 'read', return_value=[]):
                    with self.assertRaises(ValueError):
                        generator.main()
                self.assertEqual(before, {p.name: p.read_bytes() for p in updates.iterdir()})

    def test_checked_in_output_is_current(self):
        for name, sql in zip(('rifts_0012_monster_targeting_schema.sql',
                              'rifts_0013_monster_targeting_profiles.sql'), generator.render()):
            self.assertEqual(sql, (generator.UPDATES / name).read_text())
            self.assertEqual(sql, (generator.GENERATED / name).read_text())


    def test_mysql_reseed_restores_the_csv_values_in_temporary_world_table(self):
        config = ROOT / 'azerothcore-wotlk/build/mysql/client.cnf'
        if not shutil.which('mysql') or not config.exists():
            self.skipTest('local MySQL fixture configuration unavailable')
        schema, seed = generator.render()
        # A connection-local temporary table shadows any production table.
        # Neither migrations nor tuning are applied to the running server DB.
        sql = schema.replace('CREATE TABLE IF NOT EXISTS', 'CREATE TEMPORARY TABLE') + seed
        csv_values = [float({row['profile']: row for row in generator.read()}['normal'][key])
                      for key in generator.COLUMNS]
        assignments = ','.join(key + '=0' for key in generator.COLUMNS)
        sql += "UPDATE dc_monster_targeting SET " + assignments + " WHERE profile='normal';\n"
        sql += seed + "SELECT " + ','.join(generator.COLUMNS) + " FROM dc_monster_targeting WHERE profile='normal';\n"
        sql += "SELECT COUNT(*) FROM dc_monster_targeting;\nDROP TEMPORARY TABLE dc_monster_targeting;\n"
        result = subprocess.run(['mysql', '--defaults-extra-file=' + str(config), '--batch',
                                 '--skip-column-names', 'acore_world'], input=sql,
                                text=True, capture_output=True, check=True)
        lines = result.stdout.strip().splitlines()
        # Zeroed in the table, then re-seeded: the CSV's numbers are what stand,
        # which is the whole of the 2026-09-19 ruling in one query.
        self.assertEqual([float(x) for x in lines[0].split('\t')], csv_values)
        self.assertEqual(lines[1], '3')


class PolicyTests(unittest.TestCase):
    def test_production_policy(self):
        profiles = {row['profile']: row for row in generator.read()}
        initializers = '\n'.join('Profile ' + name + '{' + ','.join(profiles[name][k] for k in generator.COLUMNS) + '};'
                                 for name in generator.PROFILES)
        harness = r'''
#include "dc_monster_targeting.h"
#include <cassert>
#include <cmath>
using namespace DC::Rifts::Targeting;
int main()
{
PROFILES
    assert(Valid(normal) && Valid(elite) && Valid(guardian));
    Candidate a{1, 4, true, 0}, b{2, 4, true, 0};
    Policy lock;
    assert(lock.Hit(a, 0, normal, 0));
    assert(!lock.Hit(b, normal.lockSeconds / 2, normal, 0));
    assert(lock.Current() == 1);
    assert(lock.Remaining(normal.lockSeconds / 2) == normal.lockSeconds / 2);
    // No timer extension on repeated hits. An expired lock takes a new close hit.
    assert(lock.Hit(b, normal.lockSeconds, normal, 0));
    assert(lock.Current() == 2);
    // A scored release renews the lock even when nobody merits a switch.
    assert(lock.Choose({a,b}, normal.lockSeconds * 2, normal, 0) == 2);
    assert(lock.Remaining(normal.lockSeconds * 2) == normal.lockSeconds);
    // Explicit margin: exactly equal is insufficient, just above it switches.
    Profile margin = normal;
    margin.recencyWeight = 0; margin.proximityWeight = 1;
    margin.switchMargin = .25; margin.candidateMaxYards = 100;
    Policy threshold;
    Candidate far{1, 50, true}, closer{2, 25, true};
    assert(threshold.Choose({far}, 0, margin, 0) == 1);
    assert(threshold.Choose({far,closer}, margin.lockSeconds, margin, 0) == 1);
    closer.distance = 24;
    assert(threshold.Choose({far,closer}, margin.lockSeconds * 2, margin, 0) == 2);
    // Damage bonus disappears outside the close radius, not merely with age.
    Candidate poke{2, normal.recencyMaxYards + 1, true, 0};
    Profile noRecency = normal; noRecency.recencyWeight = 0;
    assert(Score(poke, normal) == Score(poke, noRecency));
    Policy distant;
    assert(!distant.Hit(poke, 0, normal, 0));
    assert(distant.Current() == 0);
    poke.distance = normal.recencyMaxYards;
    assert(distant.Hit(poke, 0, normal, 0));
    // Reachability gates both entry paths; score also exposes its penalty.
    Candidate ledge{3, 1, false, 0};
    assert(Score(ledge, normal) < Score(a, normal));
    Policy path;
    assert(!path.Hit(ledge, 0, normal, 0));
    assert(path.Choose({ledge}, 0, normal, 0) == 0);
    assert(path.Choose({ledge,a}, 1, normal, 0) == 1);
    assert(path.Choose({ledge}, 1 + normal.lockSeconds, normal, 0) == 0);
    // Death/logout omits current from candidates, so it never waits for a corpse.
    Policy death;
    death.Hit(a, 0, guardian, 0);
    assert(death.Choose({b}, .1, guardian, 0) == 2);
    // Taunt wins during guardian lock, without candidates or path/range scores.
    Policy taunt;
    taunt.Hit(a, 0, guardian, 0);
    assert(taunt.Choose({}, .1, guardian, 0, 9) == 9);
    assert(taunt.Taunted());
    assert(!taunt.Hit(b, 100, guardian, 0));
    assert(taunt.Choose({}, 100, guardian, 0, 10) == 10); // newest aura wins
    assert(taunt.Choose({a,b}, 100.1, guardian, 0) == 1); // aura expired: release now
    assert(!taunt.Taunted());
    taunt.Choose({}, 101, guardian, 0, 9);
    taunt.ReleaseTaunt(101.1);
    assert(taunt.Hit(b, 101.1, guardian, 0));
    // Real profile jitter bounds and guardian minimum dwell exceed trash maximum.
    Policy low, high;
    low.Hit(a, 0, normal, -1); high.Hit(a, 0, normal, 1);
    assert(std::abs(low.Remaining(0) - normal.lockSeconds*(1-normal.jitterPercent/100)) < 1e-9);
    assert(std::abs(high.Remaining(0) - normal.lockSeconds*(1+normal.jitterPercent/100)) < 1e-9);
    Policy guardianLow; guardianLow.Hit(a, 0, guardian, -1);
    assert(guardianLow.Remaining(0) > high.Remaining(0));
    // Equal-distance alternating recency can move trash, but not this guardian.
    a.secondsSinceHit = normal.recencyWindowSeconds; b.secondsSinceHit = 0;
    Policy trash, boss;
    trash.Hit(a, 0, normal, 0); boss.Hit(a, 0, guardian, 0);
    assert(trash.Choose({a,b}, normal.lockSeconds, normal, 0) == 2);
    assert(boss.Choose({a,b}, guardian.lockSeconds, guardian, 0) == 1);
    // Long-range ping-pong stays on a reachable near player across 100 releases.
    Candidate tankless{1, 4, true}, ranged{2, normal.candidateMaxYards - 1, true, 0};
    Policy exploit; exploit.Hit(tankless, 0, normal, 0);
    for (int i=1; i<=100; ++i)
    {
        double now = i*normal.lockSeconds;
        assert(!exploit.Hit(ranged, now, normal, 0));
        assert(exploit.Choose({tankless,ranged}, now, normal, 0) == 1);
    }
    // Zeroing individual weights really removes each contribution.
    Profile off = normal;
    off.recencyWeight = 0; off.proximityWeight = 0; off.reachabilityWeight = 0;
    assert(Score(a, off) == 0);
    // Route efficiency matters among reachable candidates; zero disables it.
    Candidate detour{1,4,true,0,.4}, direct{2,4,true,0,1};
    Policy routing;
    routing.Hit(detour,0,normal,0);
    assert(routing.Choose({detour,direct},normal.lockSeconds,normal,0)==2);
    Profile noRoute = normal; noRoute.reachabilityWeight=0;
    Policy routingOff; routingOff.Hit(detour,0,noRoute,0);
    assert(routingOff.Choose({detour,direct},noRoute.lockSeconds,noRoute,0)==1);
    Profile invalid = normal; invalid.jitterPercent = 100;
    assert(!Valid(invalid)); invalid = normal; invalid.lockSeconds = NAN;
    assert(!Valid(invalid));
}
'''.replace('PROFILES', initializers)
        scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='monster-targeting-tests-', dir=scratch) as folder:
            cpp, exe = Path(folder) / 'test.cpp', Path(folder) / 'test'
            cpp.write_text(harness)
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(HEADER.parent), str(cpp), '-o', str(exe)], check=True)
            harness_env.run([str(exe)], check=True)

    def test_production_ai_ordering(self):
        source = AI.read_text()
        actual = source[source.index('class RiftTargetAI :'):source.index('class TargetingWorld final')]
        profiles = {row['profile']: row for row in generator.read()}
        initialization = '\n'.join('targetingProfiles.emplace("' + name + '", Targeting::Profile{' +
            ','.join(profiles[name][k] for k in generator.COLUMNS) + '});' for name in generator.PROFILES)
        harness = r'''
#include "dc_monster_targeting.h"
#include <cassert>
#include <string>
#include <unordered_map>
#include <mutex>
#include <functional>
using uint32 = unsigned; using uint64 = std::uint64_t;
enum DamageEffectType { DIRECT }; enum SpellSchoolMask { PHYSICAL };
enum EvadeReason { NO_HOSTILES }; constexpr int REACT_AGGRESSIVE = 1;
constexpr unsigned PATHFIND_NORMAL=1, PATHFIND_SHORTCUT=2, PATHFIND_INCOMPLETE=4,
 PATHFIND_NOPATH=8, PATHFIND_NOT_USING_PATH=16, PATHFIND_SHORT=32, PATHFIND_FARFROMPOLY=192;
constexpr int SPELL_AURA_MOD_TAUNT = 11;
struct ObjectGuid { uint64 raw; explicit ObjectGuid(uint64 g):raw(g){} uint64 GetRawValue()const{return raw;} };
struct Map; struct Player; struct Unit; struct Creature;
struct Effect { Unit* caster; Unit* GetCaster(){return caster;} };
struct Unit {
 uint64 guid; double x; bool alive=true, valid=true, reachable=true, acceptsCombat=true, detour=false;
 Unit(uint64 g,double pos):guid(g),x(pos){} virtual ~Unit()=default;
 Unit* charm=nullptr; Unit* GetCharm()const{return charm;}
 Creature* ToCreature(); Creature const* ToCreature()const;
 virtual bool IsPlayer()const{return false;} virtual Player* GetCharmerOrOwnerPlayerOrPlayerItself(){return nullptr;}
 bool IsAlive()const{return alive;} bool IsInWorld()const{return true;}
 bool IsInMap(Unit const*)const{return true;} bool InSamePhase(Unit const*)const{return true;}
 bool CanSeeOrDetect(Unit const* u)const{return u->valid;}
 bool IsValidAttackTarget(Unit const* u)const{return u->valid;}
 ObjectGuid GetGUID()const{return ObjectGuid(guid);} std::string GetName()const{return std::to_string(guid);}
 float GetPositionX()const{return x;} float GetPositionY()const{return 0;} float GetPositionZ()const{return 0;}
 float GetOrientation()const{return 0;} double GetExactDist(Unit const* u)const{return std::abs(x-u->x);}
 Map* GetMap()const;
};
struct Player : Unit {
 using Unit::Unit; bool IsPlayer()const override{return true;}
 Player* GetCharmerOrOwnerPlayerOrPlayerItself()override{return this;}
};
struct Motion { int chases=0,idles=0; void MoveChase(Unit*){++chases;} void MoveChase(Unit*,float){++chases;} void MoveIdle(){++idles;} };
struct Threats {
 Unit* chosen=nullptr; Unit* relationship=nullptr; int refreshes=0; float amount=0; bool combat=false;
 void ResetAllThreat(){amount=0;}
 void AddThreat(Unit* u,float n,void*,bool modifiers,bool redirects){
  assert(modifiers&&redirects); if(u->acceptsCombat){relationship=u; combat=true; amount+=n;}}
 void FixateTarget(Unit* u){chosen=u;} Unit* GetFixateTarget(){return chosen;}
 void TauntUpdate(){++refreshes;} void ClearAllThreat(){chosen=relationship=nullptr; amount=0;}
};
struct Creature : Unit {
 using Unit::Unit; bool charmed=false; Threats threats; Unit* victim=nullptr; Motion motion; int health=100;
 std::vector<Effect*> taunts; bool promoted=false, regen=false;
 Threats& GetThreatMgr(){return threats;} Unit* GetVictim(){return victim;}
 bool IsInCombat()const{return threats.combat;} bool IsInCombatWith(Unit* u){return threats.combat&&u->acceptsCombat;}
 bool IsEngagedBy(Unit* u){return threats.relationship==u;}
 Motion* GetMotionMaster(){return &motion;} void SetHomePosition(float,float,float,float){}
 void CombatStop(bool){threats.combat=false;victim=nullptr;} void SetRegeneratingHealth(bool v){regen=v;}
 bool HasReactState(int)const{return true;} bool IsHostileTo(Unit const*)const{return true;}
 float GetAttackDistance(Unit const*)const{return 20;} bool IsWithinLOSInMap(Unit*)const{return true;}
 std::vector<Effect*> const& GetAuraEffectsByType(int)const{return taunts;}
};
Creature* Unit::ToCreature(){return dynamic_cast<Creature*>(this);} Creature const* Unit::ToCreature()const{return dynamic_cast<Creature const*>(this);}
struct Map { std::vector<Player*> players; std::vector<Unit*> extra;   // extra: the monsters a player has charmed
 void DoForAllPlayers(std::function<void(Player*)> f){for(auto p:players)f(p);}
 std::vector<Unit*> all(){std::vector<Unit*> out(players.begin(),players.end());out.insert(out.end(),extra.begin(),extra.end());return out;} };
Map map; Map* Unit::GetMap()const{return &map;}
struct PathGenerator {
 struct Point {double x,y,z;};
 Unit const* source; bool reachable=false; float endX=0; explicit PathGenerator(Unit const* u):source(u){}
 bool CalculatePath(float x,float,float){endX=x;for(auto p:map.all())if(p->x==x)reachable=p->reachable;return true;}
 std::vector<Point> GetPath()const{
  for(auto p:map.all())if(p->x==endX&&p->detour)return {{source->x,0,0},{source->x-6,0,0},{endX,0,0}};
  return {{source->x,0,0},{endX,0,0}};}
 bool IsInvalidDestinationZ(Unit* u)const{return !u->reachable;}
 unsigned GetPathType()const{return reachable?PATHFIND_NORMAL:PATHFIND_NOPATH;}
};
struct CombatManager {static bool CanBeginCombat(Unit const*,Unit const* u){return u->acceptsCombat;} };
struct ObjectAccessor {static Unit* GetUnit(Unit const&,ObjectGuid guid){
 for(auto p:map.all())if(p->guid==guid.raw)return p;return nullptr;} };
struct ChatHandler {template<typename... T> void PSendSysMessage(char const*,T const&...){} };
struct AggressorAI {
 Creature* me; bool engaged=false; int starts=0; explicit AggressorAI(Creature* u):me(u){} virtual ~AggressorAI()=default;
 virtual bool CanAIAttack(Unit const*)const{return true;} virtual void AttackStart(Unit* u){
  if(me->victim!=u){me->victim=u;me->motion.MoveChase(u);}}
 virtual void DamageTaken(Unit*,uint32&,DamageEffectType,SpellSchoolMask){}
 virtual void EnterEvadeMode(EvadeReason){} virtual void OnCharmed(bool){} bool IsEngaged()const{return engaged;}
 void EngagementStart(Unit*){assert(!engaged);engaged=true;++starts;} void EngagementOver(){engaged=false;}
};
std::vector<Creature*> holderCharmed;   // the monsters the shared charm holds for the player (combat/dc_charm_effect.h)
namespace DC::Combat::CharmEffect { std::vector<Creature*> CharmedBy(Player*){return holderCharmed;} }
namespace DC::Rifts {
std::mutex targetingMutex; std::unordered_map<std::string,Targeting::Profile> targetingProfiles;
double clockNow=100; double TargetingNow(){return clockNow;} double Roll(){return .5;}
bool IsPromotedElite(Creature const* u){return u->promoted;}
bool IsCharmedMonster(Creature const* u){return u && u->charmed;}
ACTUAL
}
using namespace DC::Rifts;
int main(){
PROFILES
 Player a(1,4),b(2,5); map.players={&a,&b}; Creature mob(10,0); RiftTargetAI ai(&mob);
 uint32 damage=1;
 // Real DamageTaken locks BEFORE periodic scoring, and zero refs restore engagement.
 ai.DamageTaken(&a,damage,DIRECT,PHYSICAL);
 assert(mob.victim==&a&&mob.threats.chosen==&a&&ai.engaged&&ai.starts==1);
 assert(ai.CanAIAttack(&a)&&!ai.CanAIAttack(&b));
 clockNow=101; ai.DamageTaken(&b,damage,DIRECT,PHYSICAL); ai.Tick();
 assert(mob.victim==&a&&mob.threats.amount==0);
 clockNow=102; ai.DamageTaken(&b,damage,DIRECT,PHYSICAL);
 assert(mob.victim==&b); // expired hit cannot be preempted by Tick's new score lock
 // A distant poke at release loses its recency and cannot acquire directly.
 b.x=40;clockNow=104;ai.DamageTaken(&b,damage,DIRECT,PHYSICAL);ai.Tick();assert(mob.victim==&a);
 // Native taunt applies synchronously, including during an existing lock.
 Effect taunt{&b};mob.taunts={&taunt};clockNow=104.1;ai.Tick();
 assert(mob.victim==&b&&mob.threats.chosen==&b);
 ai.DamageTaken(&a,damage,DIRECT,PHYSICAL);assert(mob.victim==&b);
 mob.taunts.clear();clockNow=104.2;ai.Tick();assert(mob.victim==&a);
 // An unreachable damage dealer cannot acquire at the next release.
 b.x=5;b.reachable=false;clockNow=106.2;ai.DamageTaken(&b,damage,DIRECT,PHYSICAL);ai.Tick();
 assert(mob.victim==&a);ai.EnterEvadeMode(NO_HOSTILES);assert(mob.victim==&a);
 // Death bypasses dwell; a pathable replacement acquires and an empty fight parks.
 a.alive=false;b.reachable=true;clockNow=106.3;ai.Tick();assert(mob.victim==&b);
 b.alive=false;ai.Tick();assert(!mob.IsInCombat()&&!ai.engaged&&mob.health==100&&!mob.regen);
 assert(mob.threats.chosen==nullptr&&!ai.CanAIAttack(&a));
 // Guardian AI replacement retains combat/threat/victim but restores its own engagement.
 a.alive=true;map.players={&a};Creature guardian(20,0);
 guardian.victim=&a;guardian.threats.relationship=&a;guardian.threats.combat=true;
 RiftTargetAI restored(&guardian,true);restored.Engage(&a);
 assert(restored.engaged&&restored.starts==1&&guardian.motion.chases>0&&guardian.threats.chosen==&a);
 restored.Engage(&a);assert(restored.starts==1);
 // No synthetic engagement for an excluded actor (e.g. GM mode).
 a.acceptsCombat=false;Creature excluded(30,0);RiftTargetAI rejected(&excluded,true);rejected.Engage(&a);
 assert(!rejected.engaged&&!excluded.IsInCombat());
 // Idle acquisition uses attack range, not SelectNearestTarget's visibility range.
 a.acceptsCombat=true;a.x=40;Creature idle(40,0);RiftTargetAI idleAI(&idle);idleAI.Tick();
 assert(!idle.IsInCombat());a.x=4;idleAI.Tick();assert(idle.victim==&a);
 // Real runtime candidate construction carries the measured route efficiency.
 b.alive=true;b.x=5;b.reachable=true;a.detour=true;map.players={&a,&b};
 Creature routeMob(50,0);RiftTargetAI routeAI(&routeMob);clockNow=200;
 routeAI.DamageTaken(&a,damage,DIRECT,PHYSICAL);assert(routeMob.victim==&a);
 clockNow=206;routeAI.Tick();assert(routeMob.victim==&b);
 targetingProfiles.at("normal").reachabilityWeight=0;
 Creature disabledRouteMob(60,0);RiftTargetAI disabledRouteAI(&disabledRouteMob);clockNow=300;
 disabledRouteAI.DamageTaken(&a,damage,DIRECT,PHYSICAL);clockNow=306;disabledRouteAI.Tick();
 assert(disabledRouteMob.victim==&a);
 // N-CHARM (spr13): the core parks this AI while the monster is charmed and calls OnCharmed(true) on it as the charm lands.
 // The commitment goes then (nothing runs while parked), and the AI that comes back picks afresh; ending the charm
 // commits to nobody by itself.
 a.alive=true;a.x=4;map.players={&a};clockNow=400;Creature charmed(70,0);RiftTargetAI charmAI(&charmed);
 charmAI.DamageTaken(&a,damage,DIRECT,PHYSICAL);assert(charmed.victim==&a&&charmAI.CanAIAttack(&a));
 charmAI.OnCharmed(true);assert(!charmAI.CanAIAttack(&a));
 charmAI.OnCharmed(false);assert(!charmAI.CanAIAttack(&a));
 clockNow=401;charmAI.Tick();assert(charmAI.CanAIAttack(&a)&&charmed.victim==&a);
 // N-CHARM (hdrct): D3 has the other enemies see a charmed monster as a hostile target, so the pack picks it and attacks it.
 // The charmer holds one charm (Unit::GetCharm); the monster is an aggro actor beside the players, not its charmer's pet.
 a.alive=true;a.x=10;a.reachable=true;a.detour=false;a.acceptsCombat=true;
 Creature ally(90,3);ally.charmed=true;a.charm=&ally;map.players={&a};map.extra={&ally};
 // It answers the one who hit it: the charmed monster, not the charmer it fights for.
 clockNow=500;Creature packMob(100,0);RiftTargetAI packAI(&packMob);
 packAI.DamageTaken(&ally,damage,DIRECT,PHYSICAL);
 assert(packMob.victim==&ally&&packAI.CanAIAttack(&ally)&&!packAI.CanAIAttack(&a)&&packAI.IsEngaged());
 // A hit from a pet (an owned creature that is not charmed) is still the owner's, never a second actor.
 struct Pet : Creature { using Creature::Creature; Player* owner=nullptr; Player* GetCharmerOrOwnerPlayerOrPlayerItself() override{return owner;} };
 Pet pet(95,2);pet.owner=&a;clockNow=520;Creature petMob(101,0);RiftTargetAI petAI(&petMob);
 petAI.DamageTaken(&pet,damage,DIRECT,PHYSICAL);
 assert(petMob.victim==&a&&!petAI.CanAIAttack(&pet));
 // Idle, it is a candidate like a player: the nearer of the two is taken.
 clockNow=540;Creature idleMob(102,0);RiftTargetAI idlePack(&idleMob);idlePack.Tick();
 assert(idleMob.victim==&ally&&idlePack.CanAIAttack(&ally));
 // Its charmer is not forgotten: with the charmed monster out of reach the player is the choice.
 ally.x=60;clockNow=560;Creature farMob(103,0);RiftTargetAI farPack(&farMob);farPack.Tick();
 assert(farMob.victim==&a);ally.x=3;
 // The charm ends: the monster is its pack's again (not a valid target), and the commitment falls to the player.
 ally.charmed=false;ally.valid=false;a.charm=nullptr;clockNow=600;packAI.Tick();
 assert(!packAI.CanAIAttack(&ally)&&packMob.victim==&a);
 // The shared charm (diablocraft-osikc): the monster hangs under a holder, so the player's own charm slot is empty and the
 // charm's registry names it. The pack still picks it, nearer than the player, and still answers its hit.
 Creature held(91,3);held.charmed=true;held.x=3;held.reachable=true;held.acceptsCombat=true;
 map.extra={&held};holderCharmed={&held};
 clockNow=620;Creature heldMob(104,0);RiftTargetAI heldPack(&heldMob);heldPack.Tick();
 assert(heldMob.victim==&held&&heldPack.CanAIAttack(&held));
 clockNow=640;Creature hitMob(105,0);RiftTargetAI hitPack(&hitMob);hitPack.DamageTaken(&held,damage,DIRECT,PHYSICAL);
 assert(hitMob.victim==&held);
 holderCharmed.clear();clockNow=700;Creature lostMob(106,0);RiftTargetAI lostPack(&lostMob);lostPack.Tick();
 assert(lostMob.victim==&a);   // the charm ended: the player is the choice again
}
'''.replace('ACTUAL', actual).replace('PROFILES', initialization)
        scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='monster-targeting-ai-tests-', dir=scratch) as folder:
            cpp, exe = Path(folder) / 'test.cpp', Path(folder) / 'test'
            cpp.write_text(harness)
            subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(HEADER.parent), str(cpp), '-o', str(exe)], check=True)
            harness_env.run([str(exe)], check=True)

    def test_core_integration_contract(self):
        source = AI.read_text()
        self.assertIn('threats.FixateTarget(target);', source)
        self.assertIn('threats.TauntUpdate();', source)
        self.assertIn('CombatManager::CanBeginCombat(me, target)', source)
        self.assertIn('UNITHOOK_ON_UNIT_UPDATE', source)
        self.assertIn('UNITHOOK_ON_AURA_APPLY', source)
        self.assertIn('UNITHOOK_ON_AURA_REMOVE', source)
        self.assertNotIn('GUARDIAN_ENGAGE_THREAT', source)
        self.assertNotIn('Engage(me->SelectNearestTarget', source)
        self.assertNotIn('ScriptedAI::EnterEvadeMode', source)
        self.assertIn('if (!me->IsInCombatWith(target) || !me->IsEngagedBy(target))', source)
        self.assertIn('target && _policy.Current() && target->GetGUID().GetRawValue() == _policy.Current()', source)
        spells = (ROOT / 'mod-diablocraft/scripts/generate/classes/generate_spells.py').read_text()
        self.assertIn('11 if skill_name == "Threatening Shout" and rune_name == "Demoralize"', spells)


if __name__ == '__main__':
    unittest.main()
