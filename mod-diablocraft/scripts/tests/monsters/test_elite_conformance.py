"""Conformance findings C3, C9 and A4 on today's elites (diablocraft-l5ge; monster-families.md 3.3).

C3: a single-target affix aims through the family picker, not through the AI's chase target. C9: Fast, Juggernaut, Avenger and
the guardian's Frenzy put their speed and haste on stock auras (one each, the composed percent) instead of writing SetSpeed or
SetAttackTime that the next speed effect would rebuild away. A4: Juggernaut's and the Illusionist copy's Life factor is held on
the creature and multiplied in by the scaling owner, not written to MaxHealth behind it.

The pace arithmetic (src/rifts/dc_rift_pace.h) is compiled and driven; the donors are checked against Spell.dbc where this
checkout has it; the rest is read from the source, because the game itself is not run here (docs/test-diablocraft-l5ge.md has the
dev steps). DC_ELITE_CONFORMANCE_SRC points the read at a copy of mod-diablocraft/src (mutation runs)."""
import csv
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
sys.path.insert(0, str(MODULE / 'scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import affixes_text  # noqa: E402
import harness_env  # noqa: E402

SRC = Path(os.environ.get('DC_ELITE_CONFORMANCE_SRC', MODULE / 'src'))
text = lambda name: (SRC / name).read_text(encoding='utf-8')
ELITES, ELITES_H = affixes_text(SRC), text('monsters/affixes/dc_affixes.h')
RIFT_AI, RIFT_AI_H, RIFTS_H, DIFFICULTY = text('monsters/dc_monster_ai.cpp'), text('monsters/dc_monster_ai.h'), text('rifts/dc_rifts.h'), text('difficulty/dc_difficulty.cpp')

# --- C3: one picker --------------------------------------------------------------------------------------------------------
assert 'GetVictim()' not in ELITES                                                      # nothing in the affix half chases the AI's target
pick = ELITES[ELITES.index('Player* AffixTick::Pick(float reach) const'):]
assert 'Family::PickPlayer(elite, Family::Rule::Random, 0.0f, reach, false)' in pick[:200]
# N-CHARM (hdrct): a charmed elite is on the players' side, so its single-target affixes aim through `Aim`, which asks
# PickFoe for a former ally and otherwise the one picker above.
aim = ELITES[ELITES.index('Unit* AffixTick::Aim(float reach) const'):]
assert 'elite->IsCharmed() ? PickFoe(elite, reach) : Pick(reach)' in aim[:200]
def tick_of(name):
    start = ELITES.index(f'void {name}(AffixTick const& t')
    return ELITES[start:ELITES.index('\n}\n', start)]
# each victim-picking affix declares its victim first, through the one picker, and uses none before that
victims = {'FrozenTick': 'Unit* victim = now >= state->nextCastFor[affix.behaviour] ? t.Aim(t.aiReach) : nullptr;',
           'JailerTick': 'Player* victim = now >= pack->nextCastFor["jailer"] ? t.Pick(n.jailerReach) : nullptr;',
           'ArcaneEnchantedTick': 'Unit* const victim = t.Aim(t.aiReach);',
           'FrozenPulseTick': 'Unit* const victim = t.Aim(t.aiReach);',
           'ThunderstormTick': 'Unit* const victim = t.Aim(t.aiReach);',
           'VortexTick': 'Unit* const victim = t.Aim(n.vortexRange);',
           'TeleporterTick': 'Unit* const victim = t.Aim(t.aiReach);'}
for name, declaration in victims.items():
    body = tick_of(name)
    assert body.count(declaration) == 1 and body.index('victim') == body.index(declaration) + declaration.index('victim'), name
loop = ELITES[ELITES.index('void OnUnitUpdate('):ELITES.index('void OnDamage(Unit* attacker')]
assert 'victim' not in loop and 'Aim(' not in loop and 'Pick(' not in loop                 # the loop picks for none of them
# the cast-cadence group (beam, pulse, thunderstorm, vortex, teleporter) waits on its cast cadence before it aims
for behaviour, name in (('beam', 'ArcaneEnchantedTick'), ('pulse', 'FrozenPulseTick'), ('thunderstorm', 'ThunderstormTick'),
                        ('vortex', 'VortexTick'), ('teleporter', 'TeleporterTick')):
    assert f'{{"{behaviour}", false, {name}}}' in ELITES, behaviour
assert 'if (!entry->ownClock && !tick.Due(affix))' in ELITES and 'if (entry == std::end(TICK_AFFIXES))' in ELITES
assert re.search(r'float AffixTargetReach\(\)\s*\{[^}]*targetingProfiles\.find\("elite"\)[^}]*candidateMaxYards', RIFT_AI)
assert 'float AffixTargetReach();' in RIFT_AI_H and 'AffixTick const tick{elite, state, map, rift, n, now, AffixTargetReach()};' in ELITES

# --- C9: speed and haste are auras ------------------------------------------------------------------------------------------
assert 'SetSpeed(MOVE_RUN' not in ELITES and 'SetAttackTime(BASE_ATTACK' not in ELITES
assert '->ApplyAttackTimePercentMod(' not in RIFT_AI and '.ApplyAttackTimePercentMod(' not in RIFT_AI    # the comment that names it stays
for call in ('AddPace(elite, n.fastMove, n.fastAttack);', 'AddPace(elite, n.juggernautMove, 1.0);',
             'AddPace(survivor, movement, attack);'):
    assert ELITES.count(call) == 1, call
assert RIFT_AI.count('AddPace(me, 1.0, 1.0 + GuardianFrenzyHastePct() / 100.0);') == 1
assert 'void AddPace(Unit* unit, double speedRatio, double hasteRatio);' in ELITES_H
compose = ELITES[ELITES.index('void ComposePace('):ELITES.index('void AddPace(Unit* unit, double speedRatio')]
assert 'ComposePercent(fresh ? 0 : effect->GetAmount(), ratio)' in compose and 'ChangeAmount(' in compose
speed_donor, slow_donor, haste_donor = (int(x) for x in re.search(
    r'PACE_SPEED_DONOR = (\d+), PACE_SLOW_DONOR = (\d+), PACE_HASTE_DONOR = (\d+)', ELITES).groups())
assert (speed_donor, slow_donor, haste_donor) == (19582, 61458, 34675)
# a ratio below one rides the decrease-speed aura: the route is the production function, not a restated branch
add = ELITES[ELITES.index('void AddPace(Unit* unit, double speedRatio'):]
assert 'SpeedAuraFor(speedRatio) == SpeedAura::Decrease ? PACE_SLOW_DONOR : PACE_SPEED_DONOR' in add[:400]

# the sheet's own ratios drive the harness below (never a literal): Fast +40, Juggernaut -30, Avenger +20
params = {}
with (MODULE / 'data/tunables/elite_affix_parameters.csv').open(encoding='utf-8', newline='') as stream:
    for row in csv.DictReader(stream):
        params[(row['affix_name'], row['parameter'])] = float(row['d3_value'] or row['tuned_value'] or 0)
FAST, JUGGERNAUT, AVENGER = (1 + params[('Fast', 'move_speed')] / 100, 1 - params[('Juggernaut', 'move_speed_reduction')] / 100,
                             1 + params[('Avenger', 'move_speed_bonus')] / 100)

harness = r'''
#include <cassert>
#include <cmath>
#include "dc_rift_pace.h"
using namespace DC::Rifts;
// The pace of one monster as the core reads it: the two speed auras, each composed on its own side by the production route.
struct Pace { int inc = 0, dec = 0; };
static void add(Pace& p, double ratio) {
    if (ratio == 1.0) return;
    (SpeedAuraFor(ratio) == SpeedAura::Decrease ? p.dec : p.inc) = ComposePercent(SpeedAuraFor(ratio) == SpeedAura::Decrease ? p.dec : p.inc, ratio);
}
static bool near(double a, double b) { return std::fabs(a - b) < 0.011; }
int main() {
    const double FAST = @FAST@, JUGGERNAUT = @JUGGERNAUT@, AVENGER = @AVENGER@;
    assert(ComposePercent(0, 1.4) == 40);              // Fast on a plain monster: +40 percent
    assert(ComposePercent(40, 1.0) == 40);             // a ratio of one changes nothing
    assert(ComposePercent(40, 1.5) == 110);            // 1.4 x 1.5 = 2.1, not 1.9
    assert(ComposePercent(0, 1.0 / 1.25) == -20);      // a slow composes the same way
    int pct = 0;
    for (int i = 0; i < 3; ++i) pct = ComposePercent(pct, 1.1);
    assert(pct == 33);                                 // three Avenger deaths at 10 percent: 1.331, to the percent
    // Where a ratio goes
    assert(SpeedAuraFor(FAST) == SpeedAura::Increase && SpeedAuraFor(AVENGER) == SpeedAura::Increase);
    assert(SpeedAuraFor(JUGGERNAUT) == SpeedAura::Decrease);
    assert(SpeedAuraFor(1.0) == SpeedAura::Increase);
    // What the core makes of it (Unit::UpdateSpeed: max positive increase x strongest slow). Juggernaut alone is slower than
    // a plain monster, Fast + Juggernaut is the product, and Avenger after Juggernaut still speeds it up.
    { Pace p; add(p, JUGGERNAUT); assert(SpeedFactor(p.inc, p.dec) < 1.0 && near(SpeedFactor(p.inc, p.dec), JUGGERNAUT)); }
    { Pace p; add(p, FAST); add(p, JUGGERNAUT); assert(near(SpeedFactor(p.inc, p.dec), FAST * JUGGERNAUT)); assert(p.inc > 0 && p.dec < 0); }
    { Pace p; add(p, JUGGERNAUT); add(p, FAST); assert(near(SpeedFactor(p.inc, p.dec), FAST * JUGGERNAUT)); }
    { Pace p; add(p, JUGGERNAUT); add(p, AVENGER); add(p, AVENGER); assert(near(SpeedFactor(p.inc, p.dec), JUGGERNAUT * AVENGER * AVENGER)); }
    { Pace p; add(p, FAST); assert(near(SpeedFactor(p.inc, p.dec), FAST) && p.dec == 0); }
    // The mistake the review found: every ratio on the increase aura. The core reads a negative amount there as nothing.
    { int inc = ComposePercent(0, JUGGERNAUT); assert(inc < 0 && SpeedFactor(inc, 0) == 1.0); }
    return 0;
}
'''.replace('@FAST@', repr(FAST)).replace('@JUGGERNAUT@', repr(JUGGERNAUT)).replace('@AVENGER@', repr(AVENGER))
spec = os.environ.get('DC_ELITE_CONFORMANCE_SRC')
scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
with tempfile.TemporaryDirectory(prefix='elite-conformance-', dir=scratch) as folder:
    cpp, exe = Path(folder) / 'pace.cpp', Path(folder) / 'pace'
    cpp.write_text(harness, encoding='utf-8')
    subprocess.run(['c++', '-std=c++17', '-O0', '-UNDEBUG', '-Wall', '-Werror', '-I', str(SRC / 'rifts'), str(cpp), '-o', str(exe)], check=True)
    done = harness_env.run([str(exe)], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr

# the two donors are what the code says: a bare single-effect aura of the right type, no stance, no visual, no duration
spell_dbc = ROOT / 'client-patch/dbc/Spell.dbc'
if spell_dbc.exists():
    import dbc_store
    store = dbc_store.Store(spell_dbc.read_bytes(), dbc_store.schema(ROOT, 'spell_dbc'))
    for donor, aura in ((speed_donor, 31), (slow_donor, 33), (haste_donor, 138)):          # INCREASE_SPEED, DECREASE_SPEED, MELEE_HASTE
        spell = store.decode(donor)
        assert (spell['Effect_1'], spell['EffectAura_1'], spell['Effect_2'], spell['Effect_3']) == (6, aura, 0, 0), donor
        assert spell['ShapeshiftMask'] == 0 and spell['ShapeshiftExclude'] == 0, donor
        assert spell['SpellVisualID_1'] == 0 and spell['ImplicitTargetA_1'] == 1, donor      # self, nothing drawn
        # no mechanic anywhere, so Juggernaut's snare/root/stun immunities cannot refuse the aura (Unit::IsImmunedToSpell)
        assert spell['Mechanic'] == 0 and spell['EffectMechanic_1'] == 0 and spell['DispelType'] == 0, donor
    for donor in (speed_donor, haste_donor):                                               # passives: no duration
        assert store.decode(donor)['DurationIndex'] == 0, donor
    assert store.decode(slow_donor)['DurationIndex'] == 21                                    # SpellDuration.dbc row 21 is -1: never expires
    assert store.decode(slow_donor)['EffectBasePoints_1'] < 0                                 # a slow by its own base amount, ours replaces it
else:
    print('SKIP: the pace donors are not checked against Spell.dbc here (client-patch/dbc/Spell.dbc is absent)')

# --- A4: the scaling owner holds the Life factor ----------------------------------------------------------------------------
scale = ELITES[ELITES.index('void ScaleLife(Creature* creature, double factor)'):ELITES.index('// The always-on affixes')]
assert 'GetDefault<LifeFactor>("DCEliteLife")->factor = factor;' in scale
assert scale.index('->factor = factor;') < scale.index('RefreshCreatureScaling(creature)')        # stored before the owner is asked
assert scale.index('RefreshCreatureScaling(creature)') < scale.index('SetMaxHealth(')      # the owner first, the direct write only as the fallback
assert 'creature->SetHealth(creature->GetMaxHealth());\n        return;' in scale
assert 'double EliteLifeFactor(Creature const* creature)' in ELITES and 'double EliteLifeFactor(Creature const* creature);' in RIFTS_H
owner = DIFFICULTY[DIFFICULTY.index('bool OnModuleCreatureScaling'):]
assert owner.count('Rifts::EliteLifeFactor(creature)') == 1
assert owner.index('Rifts::EliteLifeFactor(creature)') > owner.index('GreaterScaling(level')            # after the Greater Rift level's own factors
assert owner.index('Rifts::EliteLifeFactor(creature)') < owner.index('ScaleCreatureLife(')               # and before the Life is made
print('PASS: elite conformance: C3 picker, C9 pace auras, A4 Life factor.')
