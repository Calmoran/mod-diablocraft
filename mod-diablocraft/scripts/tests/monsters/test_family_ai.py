"""Monster families Part 3 (diablocraft-l5ge): the family AI.

What can run here runs: the pure rules (src/monsters/dc_family_ability.h) are compiled with tests/family_ai/harness.cpp and
fed the generated ability rows; the production registry query (cut out of dc_family_ai.cpp) runs on a scratch schema of
the fixture mysqld holding the generated Part 1 and Part 3 tables, and what it returns is checked against the sheets and
against the numbers each built ability needs (a cell or a kind default, never nothing). What needs the worldserver (the
cast bar, the charge, the pool on the ground) is held by source checks on the wiring and by docs/test-diablocraft-l5ge.md
on dev.

DC_FAMILY_AI_RIFTS points the read at src/rifts in a copy of src, DC_FAMILY_AI_TUNABLES at a copy of monsters.csv and
DC_FAMILY_AI_GENERATOR at a copy of generate_family_ai.py (mutation runs)."""
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
import fixture_db  # noqa: E402
import generate_family_ai as ai  # noqa: E402
import generate_monster_models as models  # noqa: E402
import importlib.util  # noqa: E402
import harness_env  # noqa: E402

if os.environ.get('DC_FAMILY_AI_GENERATOR'):                                       # mutation runs: a mutated generator
    spec = importlib.util.spec_from_file_location('generate_family_ai_mutated', os.environ['DC_FAMILY_AI_GENERATOR'])
    ai = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ai)
RIFTS = Path(os.environ.get('DC_FAMILY_AI_RIFTS', MODULE / 'src/rifts'))
MONSTERS = RIFTS.parent / 'monsters'
text = lambda name: (RIFTS / name).read_text(encoding='utf-8')
CPP, HEADER = text('../monsters/dc_family_ai.cpp'), text('../monsters/dc_family_ability.h')
RIFT_AI, ELITES, ELITES_H = text('../monsters/dc_monster_ai.cpp'), affixes_text(RIFTS.parent), text('../monsters/affixes/dc_affixes.h')
INTERNAL = text('dc_rifts_internal.h')


def read(path):
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


tunables = {r['name']: r for r in read(os.environ.get('DC_FAMILY_AI_TUNABLES', MODULE / 'data/tunables/monsters.csv'))}
has = lambda name: bool(tunables.get(name, {}).get('value') or tunables.get(name, {}).get('d3_value'))
sql, ai_rows = ai.render()
sheet = models.read_csv(models.ABILITIES)
assert len(sheet) == len(ai_rows) == 123
runnable = [(s, r) for s, r in zip(sheet, ai_rows) if r['built']]
assert len(runnable) == 91

# --- what holds an ability back, driven with a changed sheet (today's data has no row that reaches these two rules) ------------
real_read_csv = models.read_csv


def with_sheet(change):
    def patched(path):
        rows = [dict(r) for r in real_read_csv(path)]
        change(Path(path), rows)
        return rows
    models.read_csv = patched
    try:
        return ai.ability_ai_rows()
    finally:
        models.read_csv = real_read_csv


def no_donor(path, rows):
    if path == models.ABILITIES:
        next(r for r in rows if r['kind'] == 'ranged_bolt')['wow_spell'] = ''


def no_minion(path, rows):
    if path == ai.AI_CSV:
        next(r for r in rows if r['ability'] == 'Summon Skeletons')['summon_monster'] = ''


for change, why in ((no_donor, 'no donor spell'), (no_minion, 'no monster to bring')):
    changed = with_sheet(change)
    held_now = [r for r, was in zip(changed, ai.ability_ai_rows()) if r['built'] != was['built']]
    assert len(held_now) == 1 and held_now[0]['built'] == 0 and held_now[0]['held_reason'] == why, (why, held_now)

# --- the pure rules, compiled and driven with the generated rows -------------------------------------------------------
with tempfile.TemporaryDirectory(prefix='family-ai-', dir=ROOT / 'azerothcore-wotlk/build/_agent-scratch') as folder:
    folder = Path(folder)
    (folder / 'rows.tsv').write_text(''.join(f"{r['kind']}\t{r['trigger_code']}\t{r['built']}\n" for r in ai_rows), encoding='utf-8')
    binary = folder / 'harness'
    core = ROOT / 'azerothcore-wotlk/src/common'                                    # stock EventMap, compiled from the core's own source
    subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Werror', '-I', str(MONSTERS), '-I', str(core), '-I', str(core / 'Utilities'),
                    '-I', str(core / 'Debugging'), str(MODULE / 'tests/family_ai/harness.cpp'), str(core / 'Utilities/EventMap.cpp'),
                    '-o', str(binary)], check=True)
    done = harness_env.run([str(binary), str(folder / 'rows.tsv'), ' '.join(ai.BUILT_KINDS)], capture_output=True, text=True)
    assert done.returncode == 0 and 'family ability harness: ok' in done.stdout, done.stdout + done.stderr

# --- the C++ names are the sheets' names ---------------------------------------------------------------------------------
parse_kind = re.search(r'ParseKind\(.*?names\[\] = \{(.*?)\};', HEADER, re.S).group(1)
assert re.findall(r'"(\w+)"', parse_kind) == ai.BUILT_KINDS
parse_trigger = re.search(r'ParseTrigger\(.*?names\[\] = \{(.*?)\};', HEADER, re.S).group(1)
assert set(re.findall(r'"(\w+)"', parse_trigger)) == set(ai.TRIGGERS.values())      # the codes the generator can write
assert 'MeleeSwing,' in HEADER and HEADER.index('MeleeSwing,') < HEADER.index('CrowdControlTrap,')

# --- the registry query: the columns exist, the fields are read in the order they are selected -----------------------------
load = CPP[CPP.index('bool LoadRegistry()'):CPP.index('std::optional<double> Tunable')]
query = ''.join(re.findall(r'"([^"]*)"', load[load.index('WorldDatabase.Query('):load.index('std::unordered_map<std::uint32_t, std::vector<RawAbility>> loaded')]))
columns = [c.strip() for c in re.match(r'SELECT (.*?) FROM', query).group(1).split(',')]
assert len(columns) == 14, columns
reads = {m.group(1): int(m.group(2)) for m in re.finditer(r'raw\.([\w.]+) = (?:Cell\()?f\[(\d+)\]', load)}
reads['count'] = int(re.search(r'raw\.count = f\[(\d+)\]', load).group(1))
want = {'seq': 'a.seq', 'name': 'a.ability', 'kind': 'i.kind', 'trigger': 'i.trigger_code', 'spell': 'a.wow_spell',
        'summonEntry': 'i.summon_entry', 'count': 'i.count', 'cells.cooldownS': 'a.cooldown_s', 'cells.rangeMinYd': 'a.range_min_yd',
        'cells.rangeMaxYd': 'a.range_max_yd', 'cells.windupS': 'a.windup_s', 'cells.count': 'a.projectiles', 'key': 'a.tunable_key'}
assert {k: columns[v] for k, v in reads.items()} == want, ({k: columns[v] for k, v in reads.items()}, want)
assert columns[0] == 'a.entry' and 'f[0].Get<std::uint32_t>()' in load                 # the registry is keyed by the base entry
assert 'i.built=1' in query                                                              # held abilities never load

# --- entries, clones and the tunables the code reads -----------------------------------------------------------------------
first, last = re.search(r'FAMILY_FIRST = (\d+), FAMILY_LAST = (\d+)', CPP).groups()
assert (int(first), int(last)) == (models.FAMILY_ENTRY_BASE + 1, models.FAMILY_ENTRY_BASE + models.FAMILY_ENTRY_SPAN - 1)
assert re.search(r'CHAMPION_BASE = (\d+), RARE_BASE = (\d+)', INTERNAL).groups() == (str(models.CHAMPION_BASE), str(models.RARE_BASE))
assert 'entry >= RARE_BASE' in CPP and 'entry - RARE_BASE' in CPP and 'entry - CHAMPION_BASE' in CPP
params = re.findall(r'base \+ "(\w+)"', CPP)                                           # DefaultLayer reads
defaults = {}
for name in tunables:
    m = re.fullmatch(r'ability_default_(%s)_(\w+)' % '|'.join(ai.BUILT_KINDS), name)
    if m:
        defaults.setdefault(m.group(1), set()).add(m.group(2))
assert set(params) == set().union(*defaults.values()), (params, defaults)               # every default row is read, every read has a row
assert set(defaults) <= set(ai.BUILT_KINDS) and not any(n.startswith('ability_default_') and n not in {f'ability_default_{k}_{p}' for k, ps in defaults.items() for p in ps} for n in tunables)
assert '"ability_damage_"' in CPP and all(has('ability_damage_' + k) for k in ai.BUILT_KINDS)     # one multiplier per built kind
cell_suffixes = re.findall(r'key \+ "_(\w+)"', CPP)
assert cell_suffixes == ['cooldown_s', 'range_min_yd', 'range_max_yd', 'windup_s', 'projectiles']
for suffix in cell_suffixes:                                                             # each is a cell Part 1 can leave to a tunable row
    assert any(n.endswith('_' + suffix) and n.startswith('ability_') and not n.startswith(('ability_default_', 'ability_damage_')) for n in tunables), suffix
assert has('family_caster_standoff_fraction') and '"family_caster_standoff_fraction"' in CPP
tunable_fn = CPP[CPP.index('std::optional<double> Tunable('):CPP.index('Layer TunableLayer')]
assert 'DC::Tunables::Has("monsters", name)' in tunable_fn                               # a blank PLACEHOLDER row is not a number

# --- every built ability can start and do its thing: each number it needs is a cell or a default ---------------------------
NEED = {'melee_swing': [], 'melee_heavy_slam': ['cooldown_s', 'range_max_yd', 'area_yd', 'arc_deg'],
        'ranged_bolt': ['cooldown_s', 'range_max_yd'], 'projectile_volley': ['cooldown_s', 'range_max_yd', 'count'],
        'channeled_beam': ['cooldown_s', 'range_max_yd'], 'cone_breath': ['cooldown_s', 'range_max_yd', 'arc_deg'],
        'ground_hazard_dot': ['area_yd', 'duration_s', 'tick_s'], 'ground_detonation': ['cooldown_s', 'range_max_yd', 'area_yd'],
        'charge_rush': ['cooldown_s', 'range_min_yd', 'range_max_yd', 'area_yd'],
        'leap_slam': ['cooldown_s', 'range_min_yd', 'range_max_yd', 'area_yd', 'speed_xy', 'speed_z'],
        'summon_minions': ['area_yd', 'count'], 'suicide_bomb': ['area_yd'], 'buff_roar': ['cooldown_s'],
        'crowd_control_trap': ['cooldown_s', 'range_max_yd']}
CELLS = {'cooldown_s': 'cooldown_s', 'range_min_yd': 'range_min_yd', 'range_max_yd': 'range_max_yd', 'count': 'projectiles'}
assert set(NEED) == set(ai.BUILT_KINDS)
for line, (cells, row) in enumerate(runnable):
    kind, trigger = row['kind'], row['trigger_code']
    needs = list(NEED[kind])
    if trigger in ('death', 'hit'):
        needs = [n for n in needs if n not in ('cooldown_s', 'range_max_yd', 'range_min_yd')]       # nothing paces or aims them
    if kind == 'melee_heavy_slam' and trigger == 'melee':
        needs = [n for n in needs if n != 'area_yd']                                                   # the reach is the cone's length too
    if kind == 'suicide_bomb' and trigger == 'proximity':
        needs.append('area_yd')
    if kind == 'summon_minions' and trigger == 'death':
        needs = [n for n in needs if n != 'cooldown_s']
    for need in needs:
        cell = cells.get(CELLS.get(need, '_none')) if need in CELLS else ''
        sheet_has = bool(str(cell or '').strip())
        sheet_has = sheet_has or (row['count'] is not None and need == 'count')
        assert sheet_has or need in defaults.get(kind, set()), (cells['monster'], cells['ability'], kind, need)

# --- the production query on a scratch schema of the fixture mysqld ---------------------------------------------------------
mysql, defaults_file = fixture_db.mysql_and_defaults([])
scratch = 'scratch_family_ai_%d' % os.getpid()


def run(statement, database=None, stdin=None):
    argv = [mysql, '--defaults-file=' + defaults_file, '--no-login-paths', '--batch', '--raw', '--skip-column-names']
    if database:
        argv.append(database)
    done = subprocess.run(argv + ([] if stdin else ['-e', statement]), input=stdin, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr
    return [line.split('\t') for line in done.stdout.splitlines()]


part1_sql, _, _ = models.render()
run('DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (scratch, scratch))
try:
    for table in ('creature_template', 'creature_template_model', 'creature_equip_template', 'creature_template_addon'):
        run('CREATE TABLE %s.%s LIKE acore_world.%s' % (scratch, table, table))
    run(None, scratch, part1_sql)
    run(None, scratch, sql)
    run(None, scratch, sql)                                                                 # a rerun replaces, never doubles
    got = run(query, scratch)
    assert len(got) == 91, len(got)
    assert [row[3] for row in got] == [r['kind'] for _, r in runnable]                      # the sheet's order, the AI's kinds
    assert [row[4] for row in got] == [r['trigger_code'] for _, r in runnable]
    assert {row[3] for row in got} <= set(ai.BUILT_KINDS) and {row[4] for row in got} <= set(ai.TRIGGERS.values())
    assert all(950001 <= int(row[0]) <= 950999 for row in got)
    names = {entry: name for name, entry in models.entries().items()}
    for row, (cells, ai_row) in zip(got, runnable):
        assert names[int(row[0])] == cells['monster'] and row[2] == cells['ability']
        assert int(row[6]) == ai_row['summon_entry'] and (row[7] == 'NULL') == (ai_row['count'] is None)
        assert row[13] == models.tunable_key(cells)                                          # the key the tunable rows are named by
        if ai_row['kind'] in ai.NEEDS_DONOR:
            assert int(row[5]) > 0, (cells['monster'], cells['ability'])                      # a kind that casts has its donor
    held = run("SELECT COUNT(*) FROM dc_family_ability_ai WHERE built=0", scratch)[0][0]
    assert held == '32', held
finally:
    run('DROP DATABASE IF EXISTS %s' % scratch)

# --- the wiring ------------------------------------------------------------------------------------------------------------
# the brain's hooks are forwarded by the AI class
fam = RIFT_AI[RIFT_AI.index('class FamilyAI final'):RIFT_AI.index('void StripNativeAbilities')]
assert 'class FamilyAI final : public RiftMeleeAI' in fam
for forward in ('_brain.Engage()', '_brain.Update(diff)', '_brain.OnDeath()', '_brain.OnSpellCast(spell)', '_brain.OnSpellFailed(spell)',
                '_brain.OnChannelFinished(spell)', '_brain.OnMovement(type, id)'):
    assert forward in fam, forward
assert 'float ChaseDistance() const override { return _brain.ChaseDistance(); }' in fam
assert 'if (!_brain.Busy() && _brain.CanSwing())' in fam and 'DoMeleeAttackIfReady();' in fam    # no swing while winding, none for a caster
# the chase honours the stand-off, after the core's own approach
apply_choice = RIFT_AI[RIFT_AI.index('void ApplyChoice(Unit* target)'):RIFT_AI.index('void Park()')]
assert re.search(r'ChaseDistance\(\); standoff > 0\.f\)\s*me->GetMotionMaster\(\)->MoveChase\(target, standoff\);', apply_choice)
assert apply_choice.index('AggressorAI::AttackStart(target)') < apply_choice.index('MoveChase(target, standoff)')
assert 'virtual float ChaseDistance() const' in RIFT_AI
# installed in a rift and, for a family monster, outside one
strip = RIFT_AI[RIFT_AI.index('void StripNativeAbilities'):RIFT_AI.index('class RiftCreatures')]
assert 'Family::IsFamilyEntry(creature->GetEntry())' in strip and 'new FamilyAI(creature)' in strip and 'new RiftMeleeAI(creature)' in strip
add_world = RIFT_AI[RIFT_AI.index('void OnCreatureAddWorld'):RIFT_AI.index('StripNativeAbilities(creature);\n        creature->SetRegeneratingHealth(false);')]
assert re.search(r'!ScalingContext\(map, tier, players\)\)\s*\{.*?Family::IsFamilyEntry\(creature->GetEntry\(\)\).*?StripNativeAbilities\(creature\);\s*\}?\s*return;', add_world, re.S)
assert 'Family::RegisterFamilyAiScripts();' in RIFT_AI[RIFT_AI.index('void RegisterAIScripts()'):]
assert 'Brain* BrainOf(Creature* creature)' in RIFT_AI and 'dynamic_cast<FamilyAI*>' in RIFT_AI
# the brain registers what it says
register = CPP[CPP.index('void RegisterFamilyAiScripts()'):]
assert all(f'new {s}();' in register for s in ('FamilyWorld', 'SwingScript', 'FamilyCommands'))
assert '{"reload", Reload, SEC_ADMINISTRATOR, Console::Yes}' in CPP and '{"status", Status, SEC_GAMEMASTER, Console::No}' in CPP and '{"pool", Pool, SEC_ADMINISTRATOR, Console::No}' in CPP
# a monster the tables do not know still swings
assert re.search(r'if \(_abilities\.empty\(\)\)\s*_hasSwing = true;', CPP)
# a melee trigger is the core's reach, not the window's
assert 'a.trigger == Trigger::Melee' in CPP and 'IsWithinMeleeRange(p)' in CPP
# a hit rides the AI's DamageDealt, which the core calls from DealDamage once the swing is rolled and has damage; the swing
# hook (UNITHOOK_MODIFY_MELEE_DAMAGE) runs inside CalculateMeleeDamage, before the outcome, and must not start a rider
swing = CPP[CPP.index('class SwingScript final'):CPP.index('class FamilyWorld final')]
assert 'UNITHOOK_MODIFY_MELEE_DAMAGE' in swing and 'OnDamageDealt' not in re.sub(r'//[^\n]*', '', swing)
assert re.search(r'void DamageDealt\(Unit\* victim, uint32& damage, DamageEffectType type, SpellSchoolMask\) override\s*\{\s*'
                 r'_brain\.OnDamageDealt\(victim, damage, type == DIRECT_DAMAGE\);\s*\}', fam)
on_hit = CPP[CPP.index('void Brain::OnDamageDealt'):CPP.index('void Brain::OnDeath')]
assert 'if (!swing || !damage || _riding || !ValidPlayer(me, player))' in on_hit and on_hit.index('_riding = true;') < on_hit.index('CastDonor(') < on_hit.index('_riding = false;')
# the timers are stock EventMap (brief 3.6 b), not a clock of the brain's own
BRAIN_H = (MONSTERS / 'dc_family_ai.h').read_text(encoding='utf-8')
assert 'EventMap _events;' in BRAIN_H and not re.search(r'_readyAt|_deadline|\b_now\b|\b_scan\b', CPP + BRAIN_H)
assert 'Choose(_abilities, _events,' in CPP and 'Tick(_events, diff,' in CPP
assert CPP.count('RescheduleEvent(EVENT_PHASE') == 4 and 'CancelEvent(EVENT_PHASE)' in CPP[CPP.index('void Brain::Finish()'):CPP.index('void Brain::Strike()')]
# the donor rules the harness tests are the ones that run
args = CPP[CPP.index('CastSpellExtraArgs DonorArgs('):CPP.index('class SwingScript final')]
assert 'CarryOf(IsDamageEffect(info->Effects[i]), ourNumber)' in args and 'Carry::OurNumber' in args
assert 'bool const ours = WindupCarriesOurNumber(a);' in CPP and 'a.kind != Kind::ProjectileVolley;' not in CPP
assert 'DonorDealsDamage' not in CPP + HEADER
# charge and leap ids collide with no stock movement id
ids = [int(x, 16) for x in re.findall(r'(?:CHARGE_ID|LEAP_ID) = (0x[0-9A-Fa-f]+)', CPP)]
assert len(set(ids)) == 2 and not set(ids) & {1003, 1004, 1005}
# donors cast with the flags that keep the cast bar: never the effect-less flag, never a direct cast for the wind-up
assert 'TRIGGERED_IGNORE_EFFECTS' not in CPP
assert 'if (instant)' in CPP and 'flags |= TRIGGERED_FULL_MASK' in CPP
cast_donor = CPP[CPP.index('bool Brain::CastDonor'):CPP.index('void Brain::Finish()')]
assert 'DonorArgs(info, ourNumber, Damage(ability), instant)' in cast_donor and 'return result == SPELL_CAST_OK;' in cast_donor
# a summon is no rift progress and no loot, marked the way the Illusionist's copies are
assert 'GetDefault<IllusionState>("DCRiftIllusion")' in CPP
# the ground effect: the hazard subsystem, anchored at a position, drained on any map
assert 'void SpawnGroundEffect(Creature* source, GroundEffect const& effect);' in ELITES_H and 'struct GroundEffect' in ELITES_H
spawn = ELITES[ELITES.index('void SpawnGroundEffect('):ELITES.index('// Hazard geometry is the ground plane')]
assert 'h.path = HazardPath::Static;' in spawn and 'h.caster = source->GetGUID();' in spawn and 'h.affixName' not in spawn
assert 'h.x = h.originX = effect.x;' in spawn            # the anchor is the effect's own position, not the caster's
drain = ELITES[ELITES.index('void DrainEliteWork('):ELITES.index('void RegisterEliteScripts()')]
assert re.search(r'if \(!rift && !HarnessOnMap\(map\)\)\s*\{\s*if \(GroundEffectsOnMap\(map\)\)\s*DrainHazards\(map\);[^\n]*\n\s*return;', drain)
assert 'PutGroundEffect' in CPP and 'SpawnGroundEffect(me, effect);' in CPP
print('PASS: family AI: rules, registry query, numbers present, wiring.')
