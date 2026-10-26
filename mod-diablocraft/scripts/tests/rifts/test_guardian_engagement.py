"""Exercise the production guardian engagement commit with retained and rejected threat.

The method under test is `RiftTargetAI::ApplyChoice` in
`mod-diablocraft/src/monsters/dc_monster_ai.cpp`. It is the one place that turns a
selected target into a core combat relationship: a fresh or replaced AI is
engaged, a rejected relationship (GM mode, non-attackable) is never synthesized
into engagement, and an already-locked victim is kept without re-engaging.

Issue #76: this harness used to read `dc_rifts.cpp` for `void Engage(Unit*
target)`. The AI moved to `dc_rift_ai.cpp`, and `Engage` is now a two-line
wrapper (`AttackStart` + `Tick`) that delegates every decision to `ApplyChoice`.
The anchor below is checked, so the next rename fails loudly instead of a bare
`ValueError: substring not found`.
"""
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import tempfile

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'mod-diablocraft/src/monsters/dc_monster_ai.cpp'


def production_method(path, name):
    """The full text of `void <name>(Unit* ...) { ... }`, brace-balanced.

    Only the signature is anchored; the closing brace is found by balancing, so
    the harness follows the method body but a rename or a move is a clear error.
    """
    source = path.read_text(encoding='utf-8')
    match = re.search(r'\n[ \t]*void %s\(Unit\*[ \t]*\w+\)' % re.escape(name), source)
    if not match:
        raise SystemExit(
            "test_guardian_engagement: production anchor `void %s(Unit* ...)` is not in %s; "
            "the method was renamed or moved, update this harness's anchor" % (name, path.name))
    start = match.start() + 1
    brace = source.index('{', match.end())
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise SystemExit(
        "test_guardian_engagement: unbalanced braces after %s in %s" % (name, path.name))


method = production_method(SOURCE, 'ApplyChoice')
harness = r'''
#include <cassert>
struct Unit { bool alive=true; bool IsAlive() { return alive; } };
struct Motion { int chases=0; float lastRange=0; void MoveChase(Unit*) { ++chases; } void MoveChase(Unit*, float range) { ++chases; lastRange=range; } };
struct ThreatMgr {
 bool *combat, *threat, *accepts;
 void ResetAllThreat() {}
 void AddThreat(Unit*, float, void*, bool, bool) { if (*accepts) { *combat=true; *threat=true; } }
 void FixateTarget(Unit*) {}
 void TauntUpdate() {}
};
struct Creature : Unit {
 bool combat=false, threat=false, accepts=true; Unit* victim=nullptr; Motion motion;
 ThreatMgr threats{&combat, &threat, &accepts};
 bool IsInCombatWith(Unit*) { return combat; }
 bool IsEngagedBy(Unit*) { return threat; }
 Unit* GetVictim() { return victim; }
 Motion* GetMotionMaster() { return &motion; }
 ThreatMgr& GetThreatMgr() { return threats; }
};
struct Policy { int clears=0; void Clear() { ++clears; } };
struct AggressorAI {
 Creature* me;
 void AttackStart(Unit* u) { bool changed = me->victim != u; me->victim=u; if (changed) me->motion.MoveChase(u); }
};
struct AI : AggressorAI {
 bool engaged=false; int starts=0; bool _busy=false; Policy _policy; float standoff=0;
 float ChaseDistance() const { return standoff; }
 bool IsEngaged() { return engaged; }
 void EngagementStart(Unit*) { assert(!engaged); engaged=true; ++starts; }
 bool ValidTarget(Unit* t) { return me->alive && t && t->IsAlive(); }
METHOD
};
int main() {
 Unit player; Creature boss; AI ai{&boss};
 // Replaced AI: the creature retained combat/threat and its current victim.
 boss.combat=boss.threat=true; boss.victim=&player;
 ai.ApplyChoice(&player);
 assert(ai.engaged && ai.starts==1 && boss.motion.chases==1);
 ai.ApplyChoice(&player); assert(ai.starts==1);
 // Fresh spawn acquires both engagement and a chase target.
 Creature fresh; AI freshAI{&fresh}; freshAI.ApplyChoice(&player);
 assert(freshAI.engaged && fresh.victim==&player && fresh.motion.chases==1);
 // A family caster with no swing (diablocraft-l5ge) is chased at its stand-off, after the core's own approach; a swinger is not.
 Creature caster; AI casterAI{&caster}; casterAI.standoff=12.f; casterAI.ApplyChoice(&player);
 assert(caster.motion.lastRange==12.f && caster.motion.chases==2 && fresh.motion.lastRange==0.f);
 // Rejected combat (e.g. GM mode) must not synthesize AI engagement or a chase,
 // and the rejected choice must be cleared (exactly one clear, no policy left).
 Creature rejected; rejected.accepts=false; AI rejectedAI{&rejected};
 rejectedAI.ApplyChoice(&player);
 assert(!rejectedAI.engaged && rejected.victim==nullptr && rejected.motion.chases==0 &&
        rejectedAI._policy.clears==1);
 // A dead creature must not engage at all.
 Creature dead; dead.alive=false; AI deadAI{&dead};
 deadAI.ApplyChoice(&player); assert(!deadAI.engaged && !dead.threat);
 // A repeated call must not engage twice; a null target is ignored.
 freshAI.ApplyChoice(&player); assert(freshAI.starts==1);
 freshAI.ApplyChoice(nullptr); assert(freshAI.starts==1);
}
'''.replace('METHOD', method)
scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='guardian-engagement-', dir=scratch) as folder:
    cpp = Path(folder) / 'test.cpp'
    exe = Path(folder) / 'test.exe'
    cpp.write_text(harness, encoding='utf-8')
    subprocess.run(['clang++', '-std=c++17', str(cpp), '-o', str(exe)], check=True)
    harness_env.run([str(exe)], check=True)
print('Guardian engagement regression checks passed')
