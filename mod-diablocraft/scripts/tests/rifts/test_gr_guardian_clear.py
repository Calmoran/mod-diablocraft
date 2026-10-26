"""A Greater Rift's other monsters vanish when its Guardian spawns (diablocraft-aejc, ruling 2026-10-07).

Cuts the production functions IsRiftTrash, ClearedByGuardian and ClearGreaterRift out of
src/monsters/dc_monster_ai.cpp (brace-balanced from their signatures) and compiles them against small core
doubles, so the harness drives the code that ships:
  - a Greater Rift clears every hostile monster, native spawn or summon, with the long respawn so a
    native never comes back; the clear is a despawn (the doubles have no kill path at all);
  - a Nephalem Rift is left as it was and ClearGreaterRift says so (false);
  - a monster under a player's charm is cleared (it is controlled by the player, so IsRiftTrash alone would keep it);
  - kept: the Guardian, its summons, a player's pet / guardian / totem / controlled creature (a charmed pet too), a critter,
    a trigger, our own dc_ scripted creatures and Ancients, a friendly NPC, a corpse.
Source scans cover what a double cannot reach: SpawnGuardian clears through ClearGreaterRift before it
summons the Guardian and has no other clear, so a Nephalem Rift despawns nothing (ruling 2026-10-08,
diablocraft-gja4: the old radius clear around the killer is gone, and its helper with it); GreaterTick sweeps again
while the state is guardian or complete (a late-loading grid, a respawn); and GONE_FOR_THE_RUN is 7 days of
the core's DAY.

DC_GR_CLEAR_SOURCE points the compile at a mutated copy of dc_rift_ai.cpp (mutation runs)."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
SOURCE = Path(os.environ.get('DC_GR_CLEAR_SOURCE', MODULE / 'src/monsters/dc_monster_ai.cpp'))
TEXT = SOURCE.read_text(encoding='utf-8')
PROGRESS = (MODULE / 'src/rifts/dc_gr_progress.cpp').read_text(encoding='utf-8')
INTERNAL = (MODULE / 'src/rifts/dc_rifts_internal.h').read_text(encoding='utf-8')


def function(text, signature):
    """The full text of the function whose definition starts with `signature`, brace-balanced."""
    match = re.search(r'\n[ \t]*' + re.escape(signature), text)
    if not match:
        raise SystemExit('test_gr_guardian_clear: anchor `%s` is not in %s; renamed or moved, '
                         'update this harness' % (signature, SOURCE.name))
    brace = text.index('{', match.end())
    depth = 0
    for index in range(brace, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[match.start() + 1:index + 1]
    raise SystemExit('test_gr_guardian_clear: unbalanced braces after %s' % signature)


# --- cross-source: the long respawn is the core's 7 days -----------------------------------------
gone = re.search(r'inline constexpr std::uint32_t GONE_FOR_THE_RUN = ([^;]+);', INTERNAL)
assert gone and gone.group(1).replace(' ', '') == '7*DAY', gone
common = (ROOT / 'azerothcore-wotlk/src/common/Common.h').read_text(encoding='utf-8')
for line in ('MINUTE = SECOND * 60;', 'HOUR = MINUTE * 60;', 'DAY = HOUR * 24;', 'SECOND = 1;'):
    assert line in common, line   # so the core's DAY is 86400, which the harness uses

# --- source scans: where the clear is called from ------------------------------------------------
spawn = function(TEXT, 'void SpawnGuardian(Player* killer, Rift& rift)')
assert spawn.index('ClearGreaterRift(map, rift, killer)') < spawn.index('killer->SummonCreature'), \
    'the Greater Rift clear runs before the Guardian is summoned'
for despawn in ('DespawnOrUnsummon', 'GetCreatureListWithEntryInGrid', 'GuardianClearRangeYards', 'UnSummon', 'KillSelf'):
    assert despawn not in spawn, 'SpawnGuardian removes monsters only through ClearGreaterRift, found ' + despawn
assert 'GuardianClearRangeYards' not in TEXT, 'the radius helper is gone with the Nephalem clear'
tick = function(PROGRESS, 'void GreaterTick(Map* map)')
assert re.search(r'rift\.state == "guardian" \|\| rift\.state == "complete"\) && map->GetInstanceId\(\) == rift\.guardianInstance\)\s*\{.*?ClearGreaterRift\(map, rift, reference\)',
                 tick, re.S), 'the tick sweeps while the Guardian is up or just dead, on the Guardian floor only (rift floors 6.9)'
assert tick.index('ClearGreaterRift') < tick.index('std::vector<Orb> lying'), 'the sweep is before the orb early return'

harness = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <string>
#include <vector>
#include "dc_charm.h"
using namespace std::chrono_literals;
using Seconds = std::chrono::seconds;
enum { DAY = 86400 };
GONE_LINE
namespace Classes::Ancients { inline bool IsAncientEntry(std::uint32_t e) { return e >= 700 && e < 710; } }
struct Unit;
struct Unit {
    std::uint32_t entry = 0; bool creature = true;
    std::uint32_t GetEntry() const { return entry; }
    bool IsCreature() const { return creature; }
};
struct TempSummon { Unit const* summoner = nullptr; Unit const* GetSummonerUnit() const { return summoner; } };
struct Creature : Unit {
    bool alive = true, pet = false, totem = false, critter = false, guardian = false, byPlayer = false,
         trigger = false, hostile = true, summon = false, charmed = false;
    std::string script;
    TempSummon temp;
    int despawns = 0; long respawn = -1;
    bool IsAlive() const { return alive; }
    bool IsPet() const { return pet; }
    bool IsTotem() const { return totem; }
    bool IsCritter() const { return critter; }
    bool IsGuardian() const { return guardian; }
    bool IsControlledByPlayer() const { return byPlayer; }
    bool IsTrigger() const { return trigger; }
    bool IsCharmed() const { return charmed; }
    std::string GetScriptName() const { return script; }
    TempSummon const* ToTempSummon() const { return summon ? &temp : nullptr; }
    bool IsHostileTo(Unit const*) const { return hostile; }
    void DespawnOrUnsummon(std::chrono::milliseconds, Seconds forced = 0s) { ++despawns; respawn = forced.count(); }
};
struct Map { std::vector<Creature*> creatures; };
struct Rift { std::string mode; };
bool IsGuardianEntry(std::uint32_t entry) { return entry == 900; }
std::vector<Creature*> CreaturesOf(Map* map) { return map->creatures; }
namespace DC::Rifts {
FUNCTIONS
}
using namespace DC::Rifts;
int main() {
    Unit player; player.creature = false;
    Creature guardianBoss; guardianBoss.entry = 900;
    Creature native;                                   // a dungeon spawn
    Creature pack; pack.summon = true;                 // an elite pack member: a summon of another monster
    Unit monster; monster.entry = 5; pack.temp.summoner = &monster;
    Creature minion; minion.summon = true; minion.temp.summoner = &guardianBoss;   // the Guardian's own
    Creature pet; pet.pet = true;
    Creature guard; guard.guardian = true;
    Creature totem; totem.totem = true;
    Creature mine; mine.byPlayer = true;
    Creature critter; critter.critter = true;
    Creature trigger; trigger.trigger = true;
    Creature scripted; scripted.script = "dc_loot_carrier";
    Creature ancient; ancient.entry = 705;
    Creature friendly; friendly.hostile = false;
    Creature corpse; corpse.alive = false;
    Creature lateGuardian; lateGuardian.entry = 900;
    Creature charmedMonster; charmedMonster.byPlayer = true; charmedMonster.charmed = true; charmedMonster.hostile = false;   // N-CHARM (spr13)
    Creature charmedPet; charmedPet.byPlayer = true; charmedPet.charmed = true; charmedPet.pet = true; charmedPet.hostile = false;

    Map greater;
    greater.creatures = {&guardianBoss, &native, &pack, &minion, &pet, &guard, &totem, &mine, &critter,
                         &trigger, &scripted, &ancient, &friendly, &corpse, &lateGuardian, &charmedMonster, &charmedPet};
    Rift gr{"gr"};
    assert(ClearGreaterRift(&greater, gr, &player));
    // Gone: the dungeon's own monster and the pack member, with the long respawn.
    assert(native.despawns == 1 && native.respawn == 7 * DAY);
    assert(pack.despawns == 1 && pack.respawn == 7 * DAY);
    // A monster under a player's charm is cleared too: it is the player's for the charm's length, an enemy again after.
    assert(charmedMonster.despawns == 1 && charmedMonster.respawn == 7 * DAY);
    // Stays: everything else.
    Creature* kept[] = {&guardianBoss, &minion, &pet, &guard, &totem, &mine, &critter, &trigger, &scripted,
                        &ancient, &friendly, &corpse, &lateGuardian, &charmedPet};
    for (Creature* c : kept) assert(c->despawns == 0);

    // A second sweep (the tick) is harmless: a respawned native goes again.
    native.despawns = 0;
    assert(ClearGreaterRift(&greater, gr, &player) && native.despawns == 1);

    // A Nephalem Rift is untouched, and says so.
    Map nephalem; nephalem.creatures = {&native, &pack};
    native.despawns = pack.despawns = 0;
    Rift nr{"nephalem"};
    assert(!ClearGreaterRift(&nephalem, nr, &player));
    assert(native.despawns == 0 && pack.despawns == 0);
}
'''
functions = '\n'.join(function(TEXT, sig) for sig in (
    'Charm::Body CharmBodyOf(Creature const* creature)',
    'bool IsRiftTrash(Creature const* creature)',
    'bool ClearedByGuardian(Creature const* creature, Unit const* reference)',
    'bool ClearGreaterRift(Map* map, Rift const& rift, Unit const* reference)'))
harness = harness.replace('GONE_LINE', gone.group(0)).replace('FUNCTIONS', functions)

scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='gr-guardian-clear-', dir=scratch) as folder:
    cpp = Path(folder) / 'test.cpp'
    exe = Path(folder) / 'test.exe'
    cpp.write_text(harness, encoding='utf-8')
    subprocess.run(['clang++', '-std=c++17', '-I', str(MODULE / 'src/rifts'), str(cpp), '-o', str(exe)], check=True)
    harness_env.run([str(exe)], check=True)
print('Greater Rift Guardian clear checks passed')
