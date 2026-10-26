#!/usr/bin/env python3
"""Generator checks and isolated tests of production hazard functions.

Compiles only a temporary standard-library test program in agent scratch;
never builds, links, deploys or starts worldserver. Map/player lookups are stubs,
so the benchmark measures queue/geometry cost, not live-server performance.
"""
from fractions import Fraction
from pathlib import Path
import shutil
import csv
import json
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import affixes_text  # noqa: E402
import harness_env
import tempfile
import unittest
from unittest.mock import patch

import generate_affix_tunables as generator

ROOT = Path(__file__).resolve().parents[4]
SCRATCH = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
AFFIXES = ROOT / 'mod-diablocraft/src/monsters/affixes'


def function(source, name):
    start = source.index(name)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


class DataTests(unittest.TestCase):
    def test_generation_lets_the_csv_win_and_retires_rejected_branches(self):
        rows = generator.parameters()
        sql = generator.sql(rows)
        update = sql.split('ON DUPLICATE KEY UPDATE')[-1].split(';')[0]
        # Ruling 2026-09-19: the sheet is the source of truth on every apply, so
        # the clause is plain VALUES() - no COALESCE keeping the table's own
        # number, and no CASE deciding which rows may be refreshed.
        self.assertIn('`tuned_value` = VALUES(`tuned_value`)', update)
        self.assertNotIn('COALESCE', update)
        self.assertNotIn('CASE WHEN', update)
        keys = {(r[0], r[1]) for r in rows}
        self.assertNotIn(('Avenger', 'damage_taken_increase'), keys)
        self.assertFalse(any(a == '_global' and p.startswith('damage_') for a, p in keys))
        self.assertIn("`parameter`='damage_taken_increase'", sql)
        self.assertIn('damage_ground_tick', sql.split('DELETE FROM')[1])
        damage = [r for r in rows if r[1].startswith('base_')]
        # Ruling 2026-10-11 (decisions 9a2969fd): Reflects Damage joins AffixDamage with its own blank base_damage row.
        self.assertIn(('Reflects Damage', 'base_damage'), keys)
        self.assertEqual(len(damage), 16)
        self.assertTrue(all(r[2] is None and r[4] == 'damage' and "the designer's tunable" in r[5] for r in damage))
        # The Architect's seed for the designer (2026-10-11): 25000 (about 5% of a 500k T6 pool) / T6's 25.40, rounded; D3 has none.
        reflect = next(r for r in damage if r[0] == 'Reflects Damage')
        self.assertEqual(reflect[3], 984)
        self.assertIn('25.40', reflect[5])
        self.assertTrue(all(r[3] is None and 'NOT YET SET' in r[5] for r in damage if r is not reflect))

    def test_invalid_numeric_tuning_rejected(self):
        for value in ['nan', 'inf', '-1', 'broken']:
            with self.subTest(value=value), self.assertRaises(SystemExit):
                generator.number(value)
        self.assertEqual(generator.number('0'), 0)
        self.assertIsNone(generator.number(''))

    def test_current_output_and_historical_migration_not_rewritten(self):
        sql = generator.sql(generator.parameters())
        self.assertEqual(sql, (generator.GENERATED / 'affix_tunables.sql').read_text())
        # rifts_0015 is applied and frozen; the sheet's current render is the next number (hcwjv, Reflects Damage's row).
        self.assertEqual(sql, (generator.UPDATES / 'rifts_0027_affix_values.sql').read_text())
        applied = (ROOT / 'mod-diablocraft/data/sql/applied_migrations.csv').read_text()
        self.assertIn('db-world/updates/rifts_0015_affix_values.sql,', applied)
        self.assertNotIn('rifts_0027_affix_values.sql', applied)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            with patch.object(generator, 'GENERATED', Path(directory) / 'generated'), \
                 patch.object(generator, 'UPDATES', Path(directory) / 'world'):
                generator.main()
                first = (generator.UPDATES / 'rifts_0027_affix_values.sql').read_bytes()
                generator.main()
                self.assertEqual(first, (generator.UPDATES / 'rifts_0027_affix_values.sql').read_bytes())
                self.assertFalse((generator.UPDATES / 'rifts_0010_affix_tunables.sql').exists())
                self.assertFalse((generator.UPDATES / 'rifts_0015_affix_values.sql').exists())

    def test_mysql_reapply_writes_the_csv_over_whatever_the_table_holds(self):
        config = ROOT / 'azerothcore-wotlk/build/mysql/client.cnf'
        if not shutil.which('mysql') or not config.exists():
            self.skipTest('local MySQL fixture configuration unavailable')
        rows = generator.parameters()
        filled = []
        for row in rows:
            if row[:2] == ('Frozen Pulse', 'chase_speed'):
                row = row[:3] + (8.0,) + row[4:]
            elif row[:2] == ('Electrified', 'bolt_speed'):
                row = row[:3] + (999.0,) + row[4:]
            filled.append(row)
        table = 'dc_affix_round_two_fixture'
        def temporary(sql):
            return sql.replace('`dc_affix_tunables`', '`' + table + '`').replace(
                'CREATE TABLE IF NOT EXISTS', 'CREATE TEMPORARY TABLE IF NOT EXISTS')
        script = temporary(generator.sql(rows))
        script += f"UPDATE `{table}` SET tuned_value=NULL WHERE affix_name='Jailer' AND parameter='reach';\n"
        script += f"UPDATE `{table}` SET tuned_value=22 WHERE affix_name='Electrified' AND parameter='bolt_speed';\n"
        script += temporary(generator.sql(filled))
        # Ruling 2026-09-19: the sheet wins on every apply. Jailer/reach was NULLed
        # and Electrified/bolt_speed was set to 22 in the table above; the second
        # apply must put the CSV's own numbers back over both, and land the 8 the
        # edited sheet gives Frozen Pulse/chase_speed.
        wanted = [('Jailer', 'reach'), ('Electrified', 'bolt_speed'), ('Frozen Pulse', 'chase_speed')]
        tuned = {row[:2]: row[3] for row in filled}
        expected = ['NULL' if tuned[key] is None else '%g' % tuned[key] for key in wanted]
        for affix, parameter in wanted:
            script += (f"SELECT tuned_value FROM `{table}` WHERE affix_name='{affix}' "
                       f"AND parameter='{parameter}';\n")
        result = subprocess.run(['mysql', '--defaults-extra-file=' + str(config), '-N', '-B',
                                 '--database=acore_world'], input=script, text=True,
                                capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), expected)

    def test_only_native_landed_attacks_proc_and_no_swing_damage_path(self):
        source = affixes_text()
        self.assertIn('type == DIRECT_DAMAGE', function(source, 'uint32 DealDamage('))
        self.assertNotIn('EliteHits(', function(source, 'void OnDamage('))
        self.assertNotIn('swing *', source)
        self.assertNotIn('n.groundTick', source)
        self.assertIn('monster_damage_multiplier_pct', source)
        self.assertIn('base->second * factor->second', function(source, 'double AffixDamage('))

    def test_reflection_records_exact_precrit_damage_and_clears_receipts(self):
        combat = "".join(p.read_text() for p in [ROOT / "mod-diablocraft/src/combat" / "dc_combat_internal.h", *sorted((ROOT / "mod-diablocraft/src/combat").glob("dc_combat*.cpp"))])
        primary = (ROOT / 'mod-diablocraft/src/classes/barbarian/dc_barbarian_primaries.cpp').read_text()
        self.assertIn('adjusted / hit.crit', function(combat, 'void DealHit('))
        self.assertIn('ClearPreCritHit(player)', function(combat, 'void DealHit('))
        self.assertIn('hit.total / hit.crit', primary)
        self.assertIn('ClearPreCritHit(GetCaster()->ToPlayer())', function(primary, 'void Landed('))
        reflect = function(affixes_text(), 'void ReflectsDamageStruck(')
        # Ruling 2026-10-11 (decisions 9a2969fd): the player's hit only triggers the reflect; its damage is the
        # affix's own base_damage times the tier (or Greater Rift) factor, in the hit's school.
        self.assertIn('AffixDamage(n, state->tier, state->grLevel, affix.name), preCrit->school', reflect)
        self.assertNotIn('preCrit->damage', reflect)
        self.assertNotIn('ComputeHit(', reflect)


PRELUDE = r'''
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <iterator>
#include <mutex>
#include <memory>
#include <limits>
#include <array>
#include <type_traits>
#include <string>
#include <sstream>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <cassert>
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using ObjectGuid = std::uint64_t;
uint32 clockMs = 0;
uint32 getMSTime() { return clockMs; }
struct Player {
    ObjectGuid guid=1; float x=0,y=0,z=0; bool alive=true;
    bool IsAlive() const {return alive;}
    ObjectGuid GetGUID() const {return guid;}
    float GetPositionX() const {return x;} float GetPositionY() const {return y;}
    float GetPositionZ() const {return z;}
    void* ownerMap=nullptr;
    void* GetMap() const {return ownerMap;}
    void SetSpeed(int, float, bool) {}
    void InterruptNonMeleeSpells(bool) {}
    void SetControlled(bool, uint32) {}
};
using Unit = Player;   // N-CHARM (hdrct): a charmed elite's foes are monsters; here they are just more units
struct Creature {
    float x=0,y=0,z=0;
    float GetPositionX() const {return x;} float GetPositionY() const {return y;}
    float GetPositionZ() const {return z;}
    bool alive=true;
    uint64 health=100,maxHealth=100;   // the core's Life is 64-bit since patch 0027: the real number, no scaled copy
    uint64 GetHealth() const {return health;} uint64 GetMaxHealth() const {return maxHealth;}
    void SetHealth(uint64 value) {health=value;}
    float GetDistance(Creature* other) const {return std::hypot(x-other->x,y-other->y);}
    bool IsAlive() const {return alive;}
    // A charmed creature has the players' faction, so the players are not its to attack (the core's own rule).
    bool charmed=false;
    bool IsCharmed() const {return charmed;}
    bool IsValidAttackTarget(Player* p) const {return p && p->alive && !charmed;}
};
struct Map {
    unsigned id=1,instance=1;
    std::unordered_map<ObjectGuid,Creature*> creatures;
    std::vector<Player*> players;
    unsigned GetId() const{return id;}
    unsigned GetInstanceId() const{return instance;}
    Creature* GetCreature(ObjectGuid guid) {auto f=creatures.find(guid);return f==creatures.end()?nullptr:f->second;}
    template<class F> void DoForAllPlayers(F f) {for(auto* p:players)f(p);}
};
std::unordered_map<ObjectGuid,Player*> playerLookup;
struct ObjectAccessor {static Player* FindPlayer(ObjectGuid g) {auto f=playerLookup.find(g);return f==playerLookup.end()?nullptr:f->second;}};
Unit* HazardTarget(Map*, ObjectGuid g) {return ObjectAccessor::FindPlayer(g);}
// The monsters a charmed source may attack, and what is done to them (HitFoe, HoldFoe, SlowFoe are the elite file's own).
std::vector<Unit*> foesStub;
template<class C> std::vector<Unit*> AffixFoesOf(C*) {return foesStub;}
std::vector<std::pair<ObjectGuid,double>> foeHits;
unsigned foeHolds=0, foeSlows=0;
template<class C> void HitFoe(C*, Unit* foe, uint32, double damage) {if(damage>0)foeHits.push_back({foe->GetGUID(),damage});}   // like the real one, a zero hit is nothing
template<class C> bool HoldFoe(C*, Unit*, uint32, uint32) {++foeHolds;return true;}
template<class C> void SlowFoe(C*, Unit*, uint32, double, uint32) {++foeSlows;}
struct Rift {unsigned instanceId=0,mapId=0;};
constexpr int MOVE_RUN=0;
constexpr uint32 UNIT_STATE_STUNNED=1;
constexpr uint32 FREEZE_HOLD=15878;
template<class S> bool ApplyHold(S*, Player*, uint32, uint32) {return true;}
bool recording=true;
std::vector<double> damageLog;
std::uint64_t hits=0;
namespace DC::Combat {void DealMonsterHit(Creature*,Player*,uint32,double damage) {++hits;if(recording)damageLog.push_back(damage);}}
std::mutex workMutex;
'''

TESTS = r'''
int main() {
    Map map; Creature alive,dead; dead.alive=false;
    map.creatures[1]=&alive;map.creatures[2]=&dead;
    Player player;player.ownerMap=&map;map.players={&player};playerLookup[1]=&player;
    // The real base-times-tier entry point, including a valid zero tune.
    AffixNumbers tuning;tuning.value["Mortar|base_damage"]=10;tuning.tierDamage[2]=3;
    assert(AffixDamage(tuning,2,"Mortar")==30);
    {unsigned const none=0,level=7;   // inside a Greater Rift the level's factor replaces the tier's
     assert(AffixDamage(tuning,2,none,"Mortar")==30 && AffixDamage(tuning,2,level,"Mortar")==70);}
    tuning.value["Mortar|base_damage"]=0;assert(AffixDamage(tuning,2,"Mortar")==0);
    tuning.unconfigured["Frozen"]={"crystal_spread"};assert(!tuning.Enabled("Frozen"));
    tuning.unconfigured.erase("Frozen");tuning.value["Frozen|crystal_spread"]=5;
    assert(tuning.Enabled("Frozen") && tuning.Parameter("Frozen|crystal_spread")==5);
    // Health Link: below-floor receivers are not healed; low-Life victims still share.
    Creature struck,low,receiver;struck.health=200;struck.maxHealth=10000;
    low.health=400;low.maxHealth=10000;receiver.health=3000;receiver.maxHealth=10000;
    tuning.healthLinkFloor=0.05;tuning.value["Health Link|link_range"]=10;
    uint64 damage=900;HealthShare(&struck,{&struck,&low,&receiver},damage,tuning);
    assert(low.health==400 && receiver.health==2550 && damage==450);
    // Integer remainders stay on the directly struck monster.
    Creature first,second;damage=1;HealthShare(&first,{&first,&second},damage,tuning);
    assert(damage==1 && second.health==100);
    // Health remains correct above INT32_MAX and out-of-range members are untouched.
    first.maxHealth=4000000000u;first.health=4000000000u;
    second.maxHealth=4000000000u;second.health=3000000000u;
    damage=4000000000u;HealthShare(&first,{&first,&second},damage,tuning);
    assert(second.health==1000000000u && damage==2000000000u);
    second.x=20;damage=100;auto oldLife=second.health;
    HealthShare(&first,{&first,&second},damage,tuning);assert(second.health==oldLife && damage==100);
    // diablocraft-88i0: the hit is shared as the exact whole number it is, a hit past 2^32 included, and every member holds
    // its own real Life: 10,000,000,001 over three is 3,333,333,333 each with the remainder 2 kept by the struck one; the
    // small member can give only what it holds above the floor (5% of 100,000).
    {Creature elite,heavy,small;elite.maxHealth=elite.health=6000000000000ull;heavy.maxHealth=heavy.health=5000000000000ull;
     small.maxHealth=small.health=100000;
     damage=10000000001ull;HealthShare(&elite,{&elite,&heavy,&small},damage,tuning);
     assert(damage==3333333335ull && heavy.health==5000000000000ull-3333333333ull && small.health==5000);
     // a hit under 2^32 splits the same way, and a lone member is not a link
     damage=7;HealthShare(&elite,{&elite},damage,tuning);assert(damage==7);
     damage=4294967296ull;Creature other;other.maxHealth=other.health=4294967296ull*4;
     HealthShare(&elite,{&elite,&other},damage,tuning);assert(damage==2147483648ull && other.health==4294967296ull*4-2147483648ull);}
    // diablocraft-nxp9m: a marked player is passed by Desecrator, Molten and Plagued hazards and by no other affix's.
    {Hazard pools;Player marked;marked.guid=77;
     for(char const* name:{"Desecrator","Molten","Plagued","Poison Enchanted",""}){pools.affixName=name;assert(!PassesGroundEffect(pools,&marked));}
     SetGroundEffectImmune(&marked,true);
     for(char const* name:{"Desecrator","Molten","Plagued"}){pools.affixName=name;assert(PassesGroundEffect(pools,&marked)&&!PassesGroundEffect(pools,&player));}
     for(char const* name:{"Poison Enchanted","Mortar",""}){pools.affixName=name;assert(!PassesGroundEffect(pools,&marked));}
     SetGroundEffectImmune(&marked,false);pools.affixName="Plagued";assert(!PassesGroundEffect(pools,&marked));}
    // Segment width, endpoints and the missing third edge of a triangle.
    Hazard chain;chain.path=HazardPath::Link;chain.originX=0;chain.originY=0;chain.x=10;chain.y=0;chain.halfWidth=1.5f;
    assert(HazardTouches(chain,5,1.5f));assert(!HazardTouches(chain,5,1.51f));assert(!HazardTouches(chain,12,0));
    assert(PointSegmentDistance(0,0,0,0,0,0)==0);
    // Seconds are converted to milliseconds at the production call sites.
    Hazard pool;pool.stackIntervalMs=500;pool.stackMultiplier=2;pool.stackMax=10;pool.stackResetMs=1000;
    for(unsigned i=0;i<10;++i)assert(EscalatedStacks(pool,1,i*500)==i+1);
    pool.stackState[0].inside=false;pool.stackState[0].lastSeenAt=4500;
    assert(EscalatedStacks(pool,1,6501)==1);
    // Grace preserves exposure without granting stacks while outside.
    pool.stackState[0].inside=false;pool.stackState[0].lastSeenAt=6501;
    assert(EscalatedStacks(pool,1,7001)==1);
    assert(EscalatedStacks(pool,1,7501)==2);
    // No quarter-length jump at the end of the poison arming period.
    Hazard gas;gas.path=HazardPath::GrowLine;gas.armUntil=1000;gas.endsAt=7000;gas.maxLength=30;gas.dirX=1;
    MoveHazard(gas,&map,1000);assert(gas.length==0);
    MoveHazard(gas,&map,4000);assert(std::fabs(gas.length-15)<0.001);
    // A fifteen-yard damage radius must not teleport a chasing sphere.
    Hazard pulse;pulse.path=HazardPath::Tracking;pulse.target=1;pulse.radius=15;pulse.speed=2;pulse.endsAt=10000;
    player.x=10;MoveHazard(pulse,&map,1000);assert(pulse.path==HazardPath::Tracking && pulse.x==2);
    MoveHazard(pulse,&map,5000);assert(pulse.path==HazardPath::Static && pulse.x==10);
    // Only the active portion of an update crossing the arm time moves.
    Hazard armed;armed.path=HazardPath::Linear;armed.armUntil=1000;armed.lastMove=500;armed.speed=10;armed.maxLength=100;armed.dirX=1;
    MoveHazard(armed,&map,1500);assert(armed.x==5);
    // A fast bolt crosses the player between sample positions, then stops at its cap.
    Hazard bolt;bolt.path=HazardPath::Linear;bolt.speed=20;bolt.maxLength=10;bolt.dirX=1;bolt.radius=0.5f;
    MoveHazard(bolt,&map,1000);assert(bolt.x==10 && HazardTouches(bolt,5,0));
    // Swept narrow wedge, not the full disc and not a missed one-second sample.
    Hazard beam;beam.path=HazardPath::Sweep;beam.length=25;beam.wedge=0.05f;beam.sweepRate=float(M_PI)/2;
    MoveHazard(beam,&map,1000);assert(HazardTouches(beam,5,5));assert(!HazardTouches(beam,-5,-5));assert(!HazardTouches(beam,30,0));
    // Ballistic travel occurs during the warning and ends at the latched point.
    Hazard shell;shell.path=HazardPath::Ballistic;shell.armUntil=1000;shell.impactX=10;
    MoveHazard(shell,&map,500);assert(shell.x==5 && shell.z>0);
    MoveHazard(shell,&map,1000);assert(shell.x==10 && shell.z==0);
    // Owner-dead pools and chains with a dead endpoint cannot tick once more.
    auto key=MapWorkKey(&map);
    Hazard deadPool;deadPool.tag=TAG_POOL;deadPool.caster=2;deadPool.endsAt=10000;deadPool.radius=20;deadPool.damage=1;
    Hazard deadLink;deadLink.path=HazardPath::Link;deadLink.linkA=1;deadLink.linkB=2;deadLink.endsAt=10000;deadLink.damage=1;
    hazardMaps[key]={deadPool,deadLink};clockMs=100;
    DrainHazards(&map);assert(hazardMaps.count(key)==0 && damageLog.empty());
    // An overdue one-shot still fires exactly once; another map is untouched.
    Hazard once;once.oneShot=true;once.caster=1;once.endsAt=1;once.radius=20;once.damage=7;
    hazardMaps[key]={once};hazardMaps[999]={once};clockMs=10000;
    DrainHazards(&map);assert(damageLog.size()==1 && damageLog.back()==7 && hazardMaps[999].size()==1);
    DrainHazards(&map);assert(damageLog.size()==1);
    hazardMaps.clear();damageLog.clear();
    // Moving the queue must preserve the per-target history allocation.
    Hazard history;history.caster=1;history.endsAt=100000;history.struck={1,2,3};history.radius=20;history.damage=1;history.nextTick=100000;
    hazardMaps[key].push_back(std::move(history));auto* allocation=hazardMaps[key][0].struck.data();
    DrainHazards(&map);assert(hazardMaps[key][0].struck.data()==allocation);
    hazardMaps.clear();
    // N-CHARM (hdrct): a charmed elite's hazards hurt its former allies by the player rules and spare the charmer's side.
    {
        hazardMaps.clear();damageLog.clear();foeHits.clear();foeHolds=foeSlows=0;
        Player ally,farAlly;ally.guid=11;ally.x=3;farAlly.guid=12;farAlly.x=40;foesStub={&ally,&farAlly};
        Player charmer;charmer.guid=77;charmer.x=1;map.players={&charmer};
        Creature charmedSource;charmedSource.charmed=true;Creature plainSource;
        Hazard ground;ground.x=0;ground.radius=5;ground.damage=9;
        ApplyHazard(&charmedSource,&map,ground);
        assert(damageLog.empty());                                         // the charmer's side is not hurt
        assert(foeHits.size()==1 && foeHits[0].first==11 && foeHits[0].second==9);   // the ally in the pool is; the far one is not
        foeHits.clear();ApplyHazard(&plainSource,&map,ground);
        assert(foeHits.empty() && damageLog.size()==1);                    // an uncharmed elite still hurts the players only
        damageLog.clear();
        // A ring takes the direct number inside and the splash number outside; a piercing hazard hits each ally once.
        Hazard ring;ring.x=0;ring.radius=5;ring.innerRadius=1;ring.damage=2;ring.innerDamage=8;ring.oncePerTarget=true;
        ally.x=0.5f;ApplyHazard(&charmedSource,&map,ring);ApplyHazard(&charmedSource,&map,ring);
        assert(foeHits.size()==1 && foeHits[0].second==8);
        foeHits.clear();Hazard splash;splash.x=0;splash.radius=5;splash.innerRadius=1;splash.damage=2;splash.innerDamage=8;
        ally.x=3;ApplyHazard(&charmedSource,&map,splash);assert(foeHits.size()==1 && foeHits[0].second==2);
        // The freeze and the slow reach the ally too.
        foeHits.clear();Hazard cold;cold.x=0;cold.radius=5;cold.freezeMs=2500;cold.slow=0.4f;cold.slowSpell=1;cold.tickMs=250;
        ApplyHazard(&charmedSource,&map,cold);
        assert(foeHits.empty() && foeHolds==1 && foeSlows==1);             // no damage number, so no hit, but the controls land
        // A stacking pool: the ally's stacks grow while it stands in the pool, and the damage grows with them.
        foeHits.clear();Hazard stack;stack.x=0;stack.radius=5;stack.damage=5;stack.escalating=true;stack.stackMultiplier=2;
        stack.stackIntervalMs=500;stack.stackMax=10;stack.stackResetMs=1000;
        clockMs=0;ObservePoolContact(&charmedSource,&map,stack,0);clockMs=500;ObservePoolContact(&charmedSource,&map,stack,500);
        ApplyHazard(&charmedSource,&map,stack);
        assert(foeHits.size()==1 && foeHits[0].second==10);
        // An ally that walks out of the pool keeps its exposure only for the grace delay.
        ally.x=30;ObservePoolContact(&charmedSource,&map,stack,600);
        assert(!stack.stackState.empty() && !stack.stackState[0].inside);
        // A chain with a charmed end serves the charmer, whichever end is charmed; one with none burns the players.
        damageLog.clear();foeHits.clear();map.creatures.clear();
        Creature first,second;map.creatures[21]=&first;map.creatures[22]=&second;
        ally.x=5;charmer.x=5;charmer.y=0;
        auto chain=[&](){Hazard link;link.path=HazardPath::Link;link.linkA=21;link.linkB=22;link.halfWidth=3;link.damage=4;
                         link.endsAt=1000000;link.tickMs=1;hazardMaps[key]={link};first.x=0;second.x=10;++clockMs;DrainHazards(&map);};
        second.charmed=true;chain();assert(damageLog.empty() && foeHits.size()==1);
        hazardMaps.clear();foeHits.clear();second.charmed=false;first.charmed=true;chain();assert(damageLog.empty() && foeHits.size()==1);
        hazardMaps.clear();foeHits.clear();first.charmed=false;chain();assert(foeHits.empty() && damageLog.size()==1);
        hazardMaps.clear();damageLog.clear();foeHits.clear();foesStub.clear();map.creatures.clear();
        map.creatures[1]=&alive;map.creatures[2]=&dead;
    }
    // Synthetic benchmark: four players, 3,000 hazards, 500 map updates.
    // No core pathfinding, networking or real Map lookups are represented.
    recording=false;std::vector<Player> party(4);
    map.players.clear();for(unsigned i=0;i<party.size();++i){party[i].ownerMap=&map;party[i].guid=i+1;map.players.push_back(&party[i]);}
    std::vector<Hazard> batch(3000);
    for(auto& h:batch){h.caster=1;h.endsAt=1000000;h.radius=5;h.damage=1;h.tickMs=1;h.stackState.resize(4);h.struck.resize(4);}
    auto legacy=batch;
    auto start=std::chrono::steady_clock::now();
    for(unsigned i=0;i<500;++i){std::vector<Hazard> mine;mine.assign(legacy.begin(),legacy.end());legacy.clear();std::vector<Hazard> keep;for(auto& h:mine){MoveHazard(h,&map,clockMs);ApplyHazard(&alive,&map,h);keep.push_back(std::move(h));}legacy.insert(legacy.end(),keep.begin(),keep.end());}
    auto oldUs=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-start).count();
    hazardMaps[key]=std::move(batch);hazardPerf.clear();start=std::chrono::steady_clock::now();
    for(unsigned i=0;i<500;++i){++clockMs;DrainHazards(&map);}
    auto newUs=std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-start).count();
    std::cout<<"Synthetic 3000 hazards / 4 players / 500 ticks: legacy copy walk "<<oldUs/500.0<<" us/tick; production map queue "<<newUs/500.0<<" us/tick; production peak "<<hazardPerf[key].peakUs<<" us.\n";
}
'''


class StartupTests(unittest.TestCase):
    def test_real_snapshot_builder_disables_only_unset_profiles_and_accepts_later_values(self):
        if not shutil.which('g++'):
            self.skipTest('g++ unavailable for isolated standard-library test')
        source = affixes_text()
        internal = (ROOT / 'mod-diablocraft/src/rifts/dc_rifts_internal.h').read_text()
        numbers = internal[internal.index('struct AffixNumbers\n'):internal.index('extern double championScale')]
        fields = []
        for affix, parameter, d3, tuned, unit, _ in generator.parameters():
            def field(value):
                return 'Field{}' if value is None else 'Field{' + json.dumps(str(value)) + '}'
            fields.append('std::array<Field,5>{' + ','.join(map(field, [affix, parameter, d3, tuned, unit])) + '}')
        stub = r"""
struct Field {
    bool null=true; std::string value;
    Field()=default; Field(std::string v):null(false),value(std::move(v)){}
    bool IsNull() const{return null;}
    template<class T> T Get() const {
        if constexpr(std::is_same_v<T,std::string>)return value;
        else return static_cast<T>(std::stod(value));
    }
};
struct Rows {
    std::vector<std::array<Field,5>> rows;std::size_t index=0;
    Field* Fetch(){return rows[index].data();}
    bool NextRow(){return ++index<rows.size();}
};
using QueryResult=std::shared_ptr<Rows>;
struct Database {
    std::vector<std::array<Field,5>> parameters,tiers;
    QueryResult Query(std::string const& sql) {
        auto rows=std::make_shared<Rows>();
        rows->rows=sql.find("dc_affix_tunables")!=std::string::npos?parameters:tiers;
        return rows->rows.empty()?nullptr:rows;
    }
} WorldDatabase;
namespace Combat::Shells { inline std::uint32_t AffixSlowFor(char const*) { return 1; } }
"""
        # LaunchTierCount() is a runtime value now (tunables monsters/launch_tier_count);
        # the harness defines it from the same CSV row the server is seeded from.
        with open(ROOT / 'mod-diablocraft/data/tunables/monsters.csv', encoding='utf-8') as sheet:
            tiers = next(row[2] for row in csv.reader(sheet) if row and row[0] == 'launch_tier_count')
        stub += 'namespace DC { unsigned LaunchTierCount() { return %s; } }\n' % int(tiers)
        main = r"""
int main(){
    for(unsigned tier=1;tier<=DC::LaunchTierCount();++tier)
        WorldDatabase.tiers.push_back({Field{std::to_string(tier)},Field{tier==2?"300":"100"},Field{},Field{},Field{}});
    std::string error;auto snapshot=BuildAffixNumbers(error);
    assert(snapshot && error.empty());
    assert(!snapshot->Enabled("Electrified") && !snapshot->Enabled("Health Link"));
    assert(!snapshot->Enabled("Frozen Pulse") && !snapshot->Enabled("Molten"));
    assert(snapshot->Enabled("Reflects Damage"));   // its base_damage row is seeded (984)
    assert(snapshot->Enabled("Illusionist") && snapshot->Enabled("Avenger"));
    assert(snapshot->tierDamage.at(2)==3);
    // Test values only: fill every previously empty CSV cell in the fake DB.
    for(auto& row:WorldDatabase.parameters)
        if(row[2].IsNull() && row[3].IsNull())row[3]=Field{"1"};
    snapshot=BuildAffixNumbers(error);assert(snapshot && snapshot->unconfigured.empty());
    // No unchosen fallback if a newly required migration row is absent.
    auto& rows=WorldDatabase.parameters;
    rows.erase(std::remove_if(rows.begin(),rows.end(),[](auto const& row){return row[0].value=="Frozen" && row[1].value=="crystal_spread";}),rows.end());
    snapshot=BuildAffixNumbers(error);assert(snapshot && !snapshot->Enabled("Frozen"));
    // The same for Reflects Damage's base_damage: a table without the row (its migration not applied) disables it.
    assert(snapshot->Enabled("Reflects Damage"));
    rows.erase(std::remove_if(rows.begin(),rows.end(),[](auto const& row){return row[0].value=="Reflects Damage" && row[1].value=="base_damage";}),rows.end());
    snapshot=BuildAffixNumbers(error);assert(snapshot && !snapshot->Enabled("Reflects Damage"));
    // Invalid input and missing existing difficulty tiers fail loudly.
    rows[0][3]=Field{"-1"};assert(!BuildAffixNumbers(error) && error.find("negative")!=std::string::npos);
    rows[0][3]=Field{"6"};WorldDatabase.tiers.pop_back();
    assert(!BuildAffixNumbers(error) && error.find("difficulty tier")!=std::string::npos);
}
"""
        includes = '#include ' + json.dumps(str(ROOT / 'mod-diablocraft/src/common/dc_tiers.h')) + '\n'
        gravity = source[source.index('constexpr float KNOCKBACK_GRAVITY'):].split(';', 1)[0] + ';\n'
        program = PRELUDE + includes + gravity + numbers + stub + function(source, 'std::uint32_t Ms(')
        program += function(source, 'std::shared_ptr<AffixNumbers const> BuildAffixNumbers(')
        main = main.replace('int main(){', 'int main(){\n WorldDatabase.parameters={' + ',\n'.join(fields) + '};\n')
        program += main
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='affix-startup-', dir=SCRATCH) as directory:
            cpp,binary=Path(directory)/'startup.cpp',Path(directory)/'startup'
            cpp.write_text(program)
            subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-fsanitize=undefined','-I',str(ROOT / 'mod-diablocraft/src/common'),str(cpp),'-o',str(binary)],check=True)
            harness_env.run([str(binary)],check=True)


class HazardTests(unittest.TestCase):
    def test_production_paths_collision_lifecycle_and_queue_benchmark(self):
        if not shutil.which('g++'):
            self.skipTest('g++ unavailable for isolated standard-library test')
        source = affixes_text()
        structs = source[source.index('enum class HazardPath'):source.index('using HazardKey')]
        functions = '\n'.join(function(source, name) for name in [
            'HazardKey MapWorkKey(unsigned', 'HazardKey MapWorkKey(Map const*',
            'double AffixDamage(', 'double AffixDamage(AffixNumbers const& n, unsigned tier, unsigned grLevel,',
            'float Dist2D(', 'float PointSegmentDistance(', 'float AngleDiff(',
            'unsigned EscalatedStacks(', 'bool HazardTouches(', 'void MoveHazard(',
            'void SetGroundEffectImmune(', 'bool PassesGroundEffect(',
            'void ObservePoolContactFoes(', 'void ApplyHazardToFoes(',
            'void ObservePoolContact(', 'void ApplyHazard(', 'void DrainHazards('])
        # HazardKey and HazardPerf are declared in dc_affix_internal.h, the hazard state is defined in dc_affix_hazards.cpp
        # (after the MapWorkKey bodies, which come in with the functions above).
        internal_h = (AFFIXES / 'dc_affix_internal.h').read_text()
        hazards = (AFFIXES / 'dc_affix_hazards.cpp').read_text()
        perf = internal_h.index('struct HazardPerf')
        globals_ = (internal_h[internal_h.index('using HazardKey'):internal_h.index('};\n', perf) + 3]
                    + hazards[hazards.index('std::unordered_map<HazardKey'):hazards.index('std::string AffixPerformance')])
        globals_ += 'std::mutex groundImmuneMutex;\nstd::unordered_set<ObjectGuid> groundImmune;\n'
        gravity = source[source.index('constexpr float KNOCKBACK_GRAVITY'):].split(';', 1)[0] + ';\n'
        internal = (ROOT / 'mod-diablocraft/src/rifts/dc_rifts_internal.h').read_text()
        numbers = internal[internal.index('struct AffixNumbers\n'):internal.index('extern double championScale')]
        config = 'std::shared_ptr<AffixNumbers const> Numbers() { return {}; }\n'
        sharing = source[source.index('        double const range = n.Parameter("Health Link|link_range")'):]
        filtering = sharing[:sharing.index('        if (members.size() > 1)')]
        split = function(sharing, 'if (members.size() > 1)')
        floor_ = function(source, 'std::uint64_t LifeFloor(')
        health = floor_ + 'void HealthShare(Creature* elite, std::vector<Creature*> members, uint64& damage, AffixNumbers const& n) {\n' + filtering + split + '}\n'
        # ApplySlow lives in dc_rift_elites.cpp and needs the aura API; the hazard paths under
        # test only call it, and no assertion here reads the slow.
        slow = 'template<class Caster> void ApplySlow(Caster*, Player*, std::uint32_t, double, std::uint32_t) {}\n'
        # Greater Rift part 3: the level's damage factor comes from the difficulty module; here it is the level.
        greater = 'namespace DC::Difficulty { double GreaterRiftDamage(unsigned level) { return level; } }\n'
        # AffixDamage's default argument is on its declaration in dc_affix_internal.h, so the declarations go first
        affix_damage = '\n'.join(re.findall(r'double AffixDamage\([^;{]*\);', source)) + '\n'
        program = PRELUDE + gravity + numbers + config + slow + greater + structs + globals_ + affix_damage + functions + health + TESTS
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='affix-round-two-', dir=SCRATCH) as directory:
            cpp, binary = Path(directory) / 'hazard_test.cpp', Path(directory) / 'hazard_test'
            cpp.write_text(program)
            subprocess.run(['g++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-fsanitize=undefined', '-I', str(ROOT / 'mod-diablocraft/src/common'), str(cpp), '-o', str(binary)], check=True)
            result = harness_env.run([str(binary)], check=True, text=True, capture_output=True)
            print(result.stdout.strip())


    # diablocraft-86qcn: Juggernaut's +30% taken runs on the exact hit. Through the 32-bit view a hit past 3.3 billion wrapped
    # (3.4e9 x 1.3 came back as about 125 million) and core patch 0028's ApplyThroughView made the wrapped number REPLACE the exact
    # hit. The production JuggernautStruck is compiled as it is, on the sheet's own percent; the expected hits are whole-number
    # arithmetic done here in Python, never the double the production code must not use.
    def juggernaut_run(self, function_text):
        if not shutil.which('g++'):
            self.skipTest('g++ unavailable for isolated standard-library test')
        with (ROOT / 'mod-diablocraft/data/tunables/elite_affix_parameters.csv').open(encoding='utf-8', newline='') as stream:
            rows = {(r['affix_name'], r['parameter']): r for r in csv.DictReader(stream)}
        row = rows[('Juggernaut', 'damage_taken_increase')]
        percent = Fraction(row['d3_value'] or row['tuned_value'])
        top = 2 ** 64 - 1
        # under 2^32 / 1.3 (never wrapped), past it (wrapped), past 2^32 (a saturated view), past 2^53 (a double loses the last
        # digits) and past 2^64 / 1.3 (the product saturates, it does not wrap)
        hits = [1000, 3_400_000_000, 10_000_000_000, 9_000_000_000_000_000_001, 15_000_000_000_000_000_000]
        expected = [min(int(hit * (100 + percent) / 100), top) for hit in hits]
        cases = ''.join('    hit = %dull; Through(&jug, sheet, hit); assert(hit == %dull);\n' % pair for pair in zip(hits, expected))
        patch = (ROOT / 'core-patches/0027-life-64bit.patch').read_text()
        life = patch[patch.index('+inline uint32 LifeToUInt32('):]
        life = life[:life.index('+// The part of a hit that lies past')]
        life = '\n'.join(line[1:] for line in life.splitlines()) + '\n'
        internal = (ROOT / 'mod-diablocraft/src/rifts/dc_rifts_internal.h').read_text()
        numbers = internal[internal.index('struct AffixNumbers\n'):internal.index('extern double championScale')]
        stubs = r'''
struct EliteState { bool juggernaut = false; };
bool HasAffix(EliteState const& state, std::string const& behaviour) { return behaviour == "juggernaut" && state.juggernaut; }
// The hook as the core runs it: the exact hit goes in when the function takes 64 bits; a function still on the 32-bit view gets
// the view and ApplyThroughView puts back whatever it sets (core patch 0027), which is how the old code replaced the hit.
'''
        caller = r'''
template<class S, class N> auto Through(S* s, N const& n, uint64& d, int) -> decltype(JuggernautStruck(s, n, d), void()) { JuggernautStruck(s, n, d); }
template<class S, class N> void Through(S* s, N const& n, uint64& d, long) { ApplyThroughView(d, [&](uint32& v) { JuggernautStruck(s, n, v); }); }
template<class S, class N> void Through(S* s, N const& n, uint64& d) { Through(s, n, d, 0); }
int main() {
    EliteState jug, plain; jug.juggernaut = true;
    AffixNumbers sheet; sheet.juggernautTaken = %s;
    uint64 hit = 0;
%s    // an elite without the affix, and the affix switched off, take the hit as it came
    hit = 10000000000ull; Through(&plain, sheet, hit); assert(hit == 10000000000ull);
    sheet.unconfigured["Juggernaut"] = {"damage_taken_increase"}; hit = 10000000000ull; Through(&jug, sheet, hit); assert(hit == 10000000000ull);
    sheet.unconfigured.clear(); hit = 0; Through(&jug, sheet, hit); assert(hit == 0);
    std::cout << "juggernaut ok" << std::endl;
}
'''
        program = PRELUDE + 'using int32 = std::int32_t;\n' + life + numbers + stubs + function_text + caller % (repr(float(1 + percent / 100)), cases)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='juggernaut-exact-', dir=SCRATCH) as directory:
            cpp, binary = Path(directory) / 'juggernaut_test.cpp', Path(directory) / 'juggernaut_test'
            cpp.write_text(program)
            subprocess.run(['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-fsanitize=undefined', '-I', str(ROOT / 'mod-diablocraft/src/common'), str(cpp), '-o', str(binary)], check=True)
            return harness_env.run([str(binary)], check=True, text=True, capture_output=True).stdout.strip()

    def test_juggernaut_takes_30_percent_more_of_the_exact_hit(self):
        self.assertEqual('juggernaut ok', self.juggernaut_run(function(affixes_text(), 'void JuggernautStruck(')))

    def test_juggernaut_each_rule_has_a_killed_mutant(self):
        source = function(affixes_text(), 'void JuggernautStruck(')
        multiply = re.search(r'damage = [^;]*;', source).group(0)
        mutants = {
            'a double multiply loses the digits past 2^53': source.replace(multiply, 'damage = static_cast<std::uint64_t>(static_cast<double>(damage) * n.juggernautTaken);'),
            'the multiply goes back to the 32-bit view': source.replace('std::uint64_t& damage', 'std::uint32_t& damage').replace(multiply, 'damage = static_cast<uint32>(damage * n.juggernautTaken);'),
            'the product wraps instead of saturating': source.replace(multiply, 'damage = damage * 13 / 10;'),
        }
        for name, broken in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(source, broken)
                with self.assertRaises(subprocess.CalledProcessError):
                    self.juggernaut_run(broken)


if __name__ == '__main__':
    SCRATCH.mkdir(parents=True, exist_ok=True)
    unittest.main()
