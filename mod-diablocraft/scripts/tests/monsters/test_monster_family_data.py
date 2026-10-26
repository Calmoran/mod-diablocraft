"""Monster families Part 1 (diablocraft-uole, returned as diablocraft-o18f): the numbers, the champion and rare rows and
the ability table: a row for every roster monster the PM has not held back, a WoW donor spell and donor timings in the
ability cells, and a blank tunable row for every cell nobody has published.

Read independently of the generator: Life from the roster, damage, speed and kind rows from monsters.csv, the
ability cells from the research docs they cite. The rendered SQL is applied to a scratch schema on the fixture
mysqld (never the live one) and read back. The refusals (a cell without a source, an unknown kind) are driven
with a mutated sheet. DC_MONSTER_MODELS_SOURCE points the import at a mutated generator (mutation runs)."""
import csv
import importlib.util
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
import fixture_db  # noqa: E402

source = Path(os.environ.get('DC_MONSTER_MODELS_SOURCE', MODULE / 'scripts/generate/monsters/generate_monster_models.py'))
spec = importlib.util.spec_from_file_location('generate_monster_models', source)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def read(path):
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


roster = read(MODULE / 'data/d3/monster_roster.csv')
tunables = {r['name']: r for r in read(MODULE / 'data/tunables/monsters.csv')}
sheet = read(MODULE / 'data/tunables/monster_abilities.csv')
sheet_models = read(MODULE / 'data/d3/monster_family_models.csv')
picked = [r for r in sheet_models if r['picked'] == 'yes']
placed = [r for r in sheet_models if r['monster'] not in gen.HELD_BACK]                  # every monster that gets rows
slug = lambda name: re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
value = lambda name: float(tunables[name]['value'] or tunables[name]['d3_value'])
rbyname = {r['name']: r for r in roster}

# --- the rows the numbers come from exist, one per roster monster and kind -------------------------------------
unpublished = [r['name'] for r in roster if not re.fullmatch(r'[0-9.]+', r['life_multiplier'])]
assert len(unpublished) == 8, unpublished
assert {n for n in tunables if n.startswith('family_life_')} == {'family_life_' + slug(n) for n in unpublished}
assert {n for n in tunables if n.startswith('family_damage_')} == {'family_damage_' + slug(r['name']) for r in roster}
assert len(roster) == 65
kinds = 'melee_swing melee_heavy_slam ranged_bolt projectile_volley channeled_beam cone_breath ground_hazard_dot ' \
        'ground_detonation charge_rush leap_slam summon_minions suicide_bomb buff_roar shield_deflection ' \
        'heal_cannibalize teleport_reposition burrow_submerge pull_vortex wall_barrier crowd_control_trap'.split()
assert gen.KINDS == kinds                                           # the 20 archetypes of monster-abilities.md section 4
assert {n for n in tunables if n.startswith('ability_damage_')} == {'ability_damage_' + k for k in kinds}
archetypes = (ROOT / 'docs/research/monster-abilities.md').read_text(encoding='utf-8')
assert all('`%s`' % k in archetypes for k in kinds)
for name in tunables:
    if name.startswith(('family_', 'ability_damage_')):
        row = tunables[name]
        assert row['value'] or row['d3_value'], name
        if name.startswith(('family_life_', 'family_damage_', 'ability_damage_')):
            assert row['value'] == '1.0' and 'PLACEHOLDER' in row['notes'], name       # the designer's, marked
assert (value('family_speed_normal'), value('family_speed_fast')) == (1.0, 1.4)       # 13 section 5: 1.0x and +40%
assert 'PLACEHOLDER' in tunables['family_speed_slow']['notes'] and 'PLACEHOLDER' in tunables['family_speed_very_fast']['notes']

# --- the speed class of the roster's word ---------------------------------------------------------------------
words = {r['movement_speed'] for r in roster}
assert gen.speed_class('NOT PUBLISHED (slow)') == 'slow' and gen.speed_class('NOT PUBLISHED (average)') == 'normal'
assert gen.speed_class('NOT PUBLISHED (fast)') == 'fast' and gen.speed_class('NOT PUBLISHED (very fast)') == 'very_fast'
for qualified in ('NOT PUBLISHED (fast charge)', 'NOT PUBLISHED (fast leap)', 'NOT PUBLISHED (fast backward glide)',
                  'NOT PUBLISHED (fast when burrowed)', 'NOT PUBLISHED (flying/phase)', 'NOT PUBLISHED'):
    assert gen.speed_class(qualified) == 'normal', qualified
assert {gen.speed_class(w) for w in words} == {'slow', 'normal', 'fast', 'very_fast'}

# --- rows_for: driven with distinct numbers so a swapped column cannot hide behind a 1.0 placeholder ---------------
real = gen.tunable
fake = {'family_speed_slow': 0.5, 'family_speed_normal': 1.0, 'family_speed_fast': 1.4, 'family_speed_very_fast': 2.5}
gen.tunable = lambda name: fake.get(name, 3.25 if name.startswith('family_damage_') else 7.5)
try:
    pick = next(r for r in picked if r['monster'] == 'Walking Corpse')          # slow, Life 1.5
    template, models, equip, addon = gen.rows_for(pick, 950001, rbyname['Walking Corpse'])
    assert (template['HealthModifier'], template['DamageModifier'], template['speed_run']) == (1.5, 3.25, 0.5)
    pick = next(r for r in picked if r['monster'] == 'Moon Clan Shaman')        # Life NOT PUBLISHED: its own row
    template = gen.rows_for(pick, 950009, rbyname['Moon Clan Shaman'])[0]
    assert template['HealthModifier'] == 7.5 and template['DamageModifier'] == 3.25
    very = [r['name'] for r in roster if gen.speed_class(r['movement_speed']) == 'very_fast']
    assert len(very) == 1
    template = gen.rows_for(next(r for r in picked if r['monster'] == very[0]), 950999, rbyname[very[0]])[0]
    assert template['speed_run'] == 2.5
    for name in ('Walking Corpse', 'Savage'):
        template, models, equip, addon = gen.rows_for(next(r for r in picked if r['monster'] == name), 950001, rbyname[name])
        assert (template['BaseAttackTime'], template['RegenHealth'], template['flags_extra']) == (1000, 0, 0x4 | 0x10 | 0x20)
        assert template['rank'] == 0
        champion, rare = list(gen.clones(template, models, equip, addon))
        assert [c[0]['entry'] for c in (champion, rare)] == [8950001, 9950001]
        assert [c[0]['rank'] for c in (champion, rare)] == [1, 2]
        assert [c[0]['name'] for c in (champion, rare)] == ['Champion ' + name, 'Rare ' + name]
        for clone in (champion, rare):
            assert {k: v for k, v in clone[0].items() if k not in ('entry', 'rank', 'name')} == \
                   {k: v for k, v in template.items() if k not in ('entry', 'rank', 'name')}
            assert all(m['CreatureID'] == clone[0]['entry'] for m in clone[1]) and len(clone[1]) == len(models)
            assert clone[2]['CreatureID'] == clone[0]['entry']
finally:
    gen.tunable = real
assert gen.FLAGS_EXTRA == 52 and gen.CHAMPION_BASE == 8000000 and gen.RARE_BASE == 9000000

# --- the ability sheet: sources, cross-checked against the research it cites -----------------------------------------
docs = (ROOT / 'docs/research/monster-abilities.md').read_text(encoding='utf-8')
table = docs[docs.index('## 2. Monster Families'):docs.index('## 3. Rift Guardians')]
renamed = {'Night Clan Shaman': 'Moon Clan Shaman', 'Ice Clan Brawler': 'Ice Clan Warrior', 'Dune Wasp': 'Sand Wasp',
           'Bogan Beast': 'Tusked Bogan', 'Shade': 'Shade Stalker', 'Plague Swarm': 'Stinging Swarm'}
researched = [(renamed.get(c[0], c[0]), c[1]) for c in
              ([x.strip() for x in line.strip().strip('|').split('|')] for line in table.splitlines()
               if line.startswith('| ') and not line.startswith(('| Monster', '|---')))
              if '[Roster Gap]' not in c[0]]
assert len(researched) == 123
assert sorted((r['monster'], r['ability']) for r in sheet) == sorted(researched)   # every roster ability, none made up
assert {r['monster'] for r in sheet} == set(rbyname)                                  # every roster monster has a row
assert {r['kind'] for r in sheet} <= set(kinds) | {'passive'}
catalogue = (ROOT / 'docs/research/diiis-catalogue.md').read_text(encoding='utf-8')
game = [r for r in sheet if r['cooldown_source'] == 'game_data']
assert {r['ability'] for r in sheet if r['range_source'] == 'game_data' and r['cooldown_source'] != 'game_data'} == \
    {'Spear Throw', 'Resurrect Fallen', 'Blood Star'}                                    # catalogue gives a range, no Timer
assert {r['ability'] for r in game if r['range_source'] != 'game_data'} == \
    {'Summon Accursed / Hellion', 'Web Trap', 'Mini-Wasp Barrage'}                        # a Timer, no range
tunable_cells = set()
for r in sheet:
    key = gen.tunable_key(r)
    half = bool(r['range_min_yd'] or r['range_max_yd'])
    for number, origin in (('cooldown_s', 'cooldown_source'), ('range_min_yd', 'range_source'),
                           ('range_max_yd', 'range_source'), ('windup_s', 'windup_source'),
                           ('projectiles', 'projectiles_source'), ('wow_spell', 'wow_spell_source')):
        assert r[origin] in gen.SOURCES and r[origin] != 'placeholder', r
        if r[number]:
            assert r[origin] in ('game_data', 'roster', 'donor'), (r['monster'], r['ability'], number)
        elif r[origin] == 'tunable':                            # an unpublished number: its tunable row is blank and says so
            tunable_cells.add(key + '_' + number)
            row = tunables[key + '_' + number]
            assert row['value'] == '' and row['d3_value'] == '' and 'PLACEHOLDER' in row['notes'], row['name']
        else:                                                   # nothing to time, or half a range
            assert r[origin] == 'n/a' or (number.startswith('range_') and half), (r['monster'], r['ability'], number)
    assert r['source'].strip()
    if r['kind'] == 'passive':
        assert r['cooldown_source'] == r['range_source'] == r['windup_source'] == 'n/a'
    if r['cooldown_source'] == 'game_data' and r['kind'] != 'melee_swing':
        timer = int(re.search(r'Timer=(\d+)', r['source']).group(1))
        assert float(r['cooldown_s']) == timer / 10, (r['monster'], r['ability'])      # deciseconds, as the catalogue says
        assert 'Timer=%d' % timer in catalogue or 'Timer=%d' % timer in r['source']
        assert re.search(r'(\w+_A\.mon)', r['source']).group(1) in catalogue          # the file is one the catalogue names
    if r['cooldown_source'] == 'game_data' and r['kind'] == 'melee_swing':
        assert (r['cooldown_s'], r['range_min_yd'], r['range_max_yd']) == ('1.0', '0.0', '5.0')   # AttSpd 1.00 s, 5 yd
    if r['kind'] == 'melee_swing':
        assert r['cooldown_source'] == 'game_data'

# --- every unpublished number has its tunable row, and every ability tunable belongs to a blank cell ----------------
ability_tunables = {n for n in tunables if n.startswith('ability_') and not n.startswith(('ability_damage_', 'ability_default_'))}
assert ability_tunables == tunable_cells, sorted(ability_tunables ^ tunable_cells)[:5]      # no orphan, no cell without one
assert len(tunable_cells) == 115
assert not [r for r in sheet if 'placeholder' in (r['cooldown_source'], r['range_source'], r['windup_source'],
                                                  r['projectiles_source'], r['wow_spell_source'])]
# wow_spell: a donor id for every ability that is neither the plain swing nor a passive, bar the ten no stock spell suits
assert {r['kind'] for r in sheet if r['wow_spell_source'] == 'n/a'} == {'passive', 'melee_swing'} - {'melee_swing'} | \
    {'melee_swing'}                                                                        # passives and the plain swing
assert sum(r['wow_spell_source'] == 'donor' for r in sheet) == 67 and sum(r['wow_spell_source'] == 'tunable' for r in sheet) == 10
assert all(r['wow_spell'].isdigit() and int(r['wow_spell']) > 0 for r in sheet if r['wow_spell_source'] == 'donor')

# --- the donor cells are the donor spell's own numbers (Spell.dbc), when this checkout has the files ------------------
dbc_dir = ROOT / 'azerothcore-wotlk/build/server/data/dbc'
spell_dbc = ROOT / 'client-patch/dbc/Spell.dbc'
if spell_dbc.exists() and (dbc_dir / 'SpellCastTimes.dbc').exists() and (dbc_dir / 'SpellRange.dbc').exists():
    import struct
    import dbc_store
    store = dbc_store.Store(spell_dbc.read_bytes(), dbc_store.schema(ROOT, 'spell_dbc'))

    def records(path):
        raw = path.read_bytes()
        _, count, _, size, _ = struct.unpack_from('<4s4I', raw)
        return {struct.unpack_from('<I', raw, 20 + i * size)[0]: raw[20 + i * size:20 + (i + 1) * size] for i in range(count)}
    cast_ms = {k: struct.unpack_from('<i', v, 4)[0] for k, v in records(dbc_dir / 'SpellCastTimes.dbc').items()}
    reach = {k: tuple(round(struct.unpack_from('<f', v, o)[0], 1) for o in (4, 12)) for k, v in records(dbc_dir / 'SpellRange.dbc').items()}
    checked = 0
    for r in sheet:
        if r['wow_spell_source'] != 'donor':
            continue
        spell = store.decode(int(r['wow_spell']))
        if r['windup_source'] == 'donor':
            assert float(r['windup_s']) == round(cast_ms[spell['CastingTimeIndex']] / 1000, 1), (r['monster'], r['ability'])
        if r['range_source'] == 'donor':
            assert (float(r['range_min_yd']), float(r['range_max_yd'])) == reach[spell['RangeIndex']], (r['monster'], r['ability'])
        if r['cooldown_source'] == 'donor':
            assert float(r['cooldown_s']) == round(spell['RecoveryTime'] / 1000, 1), (r['monster'], r['ability'])
        assert ('donor ' in r['source']) and ('(%s, Spell.dbc)' % r['wow_spell']) in r['source'], (r['monster'], r['ability'])
        checked += 1
    assert checked == 67
else:
    print('SKIP: the donor cells are not checked against Spell.dbc here (client-patch/dbc/Spell.dbc or the server dbc folder is absent)')
assert 'AttSpd = 1.00s' in catalogue and 'AttackRadius = 5.0' in catalogue
assert 'Fallen Lunatic' in (MODULE / 'data/d3/monster_roster.csv').read_text(encoding='utf-8')
lunatic = next(r for r in sheet if r['ability'] == 'Suicide Bomb')
assert (lunatic['windup_s'], lunatic['windup_source']) == ('1.5', 'roster')                 # DiIiS's 2.0 s is not used
wasp = next(r for r in sheet if r['ability'] == 'Mini-Wasp Barrage')
assert (wasp['projectiles'], wasp['projectiles_source'], wasp['cooldown_s']) == ('4', 'roster', '2.5')
shaman_res = next(r for r in sheet if r['ability'] == 'Resurrect Fallen')
assert shaman_res['cooldown_s'] == '' and shaman_res['range_max_yd'] == '30.0'             # the 7.0 s is DiIiS code: not used

# --- the refusals: a mutated sheet -------------------------------------------------------------------------------------
ids = gen.entries()
original = gen.ABILITIES


def refused(edit, expect):
    with tempfile.TemporaryDirectory() as folder:
        rows = [dict(r) for r in sheet]
        edit(rows)
        path = Path(folder) / 'abilities.csv'
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, list(sheet[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        gen.ABILITIES = path
        try:
            list(gen.ability_rows(ids))
        except SystemExit as error:
            assert expect in str(error), (expect, error)
            return
        finally:
            gen.ABILITIES = original
        raise AssertionError('the sheet should have been refused: ' + expect)


refused(lambda rows: rows[0].update(kind='fireball'), 'none of the 20 archetypes')
refused(lambda rows: rows[0].update(monster='Nobody'), 'not a roster monster')
refused(lambda rows: rows[1].update(cooldown_s='3.0'), 'holds a number but its source is tunable')
refused(lambda rows: rows[0].update(cooldown_source='placeholder'), 'is none of')                  # placeholders are tunable rows now
refused(lambda rows: rows[1].update(ability='Torso Crawler'), 'has no blank PLACEHOLDER row')      # a tunable cell needs its row
refused(lambda rows: rows[0].update(cooldown_s='', cooldown_source='donor'), 'is blank but its source is donor')
refused(lambda rows: next(r for r in rows if r['wow_spell_source'] == 'donor').update(wow_spell='0'), 'no spell id')
refused(lambda rows: rows.append(dict(rows[1])), 'same tunable name')
refused(lambda rows: rows[0].update(cooldown_source='guess'), 'is none of')
refused(lambda rows: rows[0].update(source=''), 'no source text')
assert len(list(gen.ability_rows(ids))) == 123

# --- the SQL, applied to a scratch schema on the fixture and read back ---------------------------------------------------
sql, picked_rows, _ = gen.render()
assert [r['monster'] for r in picked_rows] == [r['monster'] for r in placed] and len(placed) == 64 and gen.HELD_BACK == {'Decaying Cryptstalker'}
mysql, defaults = fixture_db.mysql_and_defaults([])
scratch = 'scratch_family_data_%d' % os.getpid()


def run(statement, database=None, stdin=None):
    argv = [mysql, '--defaults-file=' + defaults, '--no-login-paths', '--batch', '--raw', '--skip-column-names']
    if database:
        argv.append(database)
    done = subprocess.run(argv + ([] if stdin else ['-e', statement]), input=stdin, text=True, capture_output=True)
    assert done.returncode == 0, done.stderr
    return [line.split('\t') for line in done.stdout.splitlines()]


run('DROP DATABASE IF EXISTS %s; CREATE DATABASE %s' % (scratch, scratch))
try:
    for table in ('creature_template', 'creature_template_model', 'creature_equip_template', 'creature_template_addon'):
        run('CREATE TABLE %s.%s LIKE acore_world.%s' % (scratch, table, table))
    run(None, scratch, sql)
    run(None, scratch, sql)                                                              # a rerun replaces, never doubles
    one = lambda statement: run(statement, scratch)[0][0]
    assert one('SELECT COUNT(*) FROM dc_family_ability') == '123'
    assert one('SELECT COUNT(DISTINCT entry) FROM dc_family_ability') == '65'          # picked or not
    assert one('SELECT COUNT(*) FROM creature_template') == str(3 * len(placed)) == str(3 * 64)
    assert one("SELECT COUNT(*) FROM creature_template WHERE name LIKE '%Cryptstalker'") == '0'   # held back for the PM's ruling
    for r in placed:
        entry = 950000 + [x['name'] for x in roster].index(r['monster']) + 1
        want = rbyname[r['monster']]
        life = float(want['life_multiplier']) if re.fullmatch(r'[0-9.]+', want['life_multiplier']) else value('family_life_' + slug(want['name']))
        speed = value('family_speed_' + gen.speed_class(want['movement_speed']))
        for base, rank, prefix in ((0, 0, ''), (8000000, 1, 'Champion '), (9000000, 2, 'Rare ')):
            got = run('SELECT name, HealthModifier, DamageModifier, speed_run, BaseAttackTime, RegenHealth, flags_extra, `rank` '
                      'FROM creature_template WHERE entry=%d' % (base + entry), scratch)[0]
            assert got[0] == prefix + r['monster'], got
            assert [float(x) for x in got[1:4]] == [life, value('family_damage_' + slug(r['monster'])), speed], (r['monster'], got)
            assert got[4:] == ['1000', '0', '52', str(rank)], (r['monster'], got)
            models = run('SELECT CreatureDisplayID, DisplayScale, Probability FROM creature_template_model WHERE CreatureID=%d ORDER BY Idx' % (base + entry), scratch)
            plain = run('SELECT CreatureDisplayID, DisplayScale, Probability FROM creature_template_model WHERE CreatureID=%d ORDER BY Idx' % entry, scratch)
            assert models == plain and models, r['monster']
            assert run('SELECT ItemID1, ItemID2, ItemID3 FROM creature_equip_template WHERE CreatureID=%d' % (base + entry), scratch) == \
                   run('SELECT ItemID1, ItemID2, ItemID3 FROM creature_equip_template WHERE CreatureID=%d' % entry, scratch)
            assert run('SELECT bytes2, auras FROM creature_template_addon WHERE entry=%d' % (base + entry), scratch) == \
                   run('SELECT bytes2, auras FROM creature_template_addon WHERE entry=%d' % entry, scratch)
    # the table holds the sheet: one row per line, numbered per monster, NULL where blank
    for line, r in enumerate(sheet):
        entry = 950000 + [x['name'] for x in roster].index(r['monster']) + 1
        seq = 1 + sum(1 for q in sheet[:line] if q['monster'] == r['monster'])
        got = run('SELECT ability, kind, cooldown_s, range_min_yd, range_max_yd, windup_s, projectiles, wow_spell, '
                  'cooldown_source, range_source, windup_source, projectiles_source, wow_spell_source, tunable_key FROM dc_family_ability '
                  'WHERE entry=%d AND seq=%d' % (entry, seq), scratch)[0]
        num = lambda cell: 'NULL' if cell == '' else ('%g' % float(cell))
        shown = lambda cell: 'NULL' if cell == 'NULL' else '%g' % float(cell)
        assert got[:2] == [r['ability'], r['kind']], (r, got)
        assert [shown(x) for x in got[2:6]] == [num(r['cooldown_s']), num(r['range_min_yd']), num(r['range_max_yd']), num(r['windup_s'])], r
        assert (got[6] if got[6] == 'NULL' else str(int(got[6]))) == ('NULL' if r['projectiles'] == '' else str(int(r['projectiles'])))
        assert got[7] == (r['wow_spell'] or '0') and got[8:] == [r['cooldown_source'], r['range_source'], r['windup_source'],
                                                                 r['projectiles_source'], r['wow_spell_source'], gen.tunable_key(r)], r
finally:
    run('DROP DATABASE IF EXISTS %s' % scratch)
migration = MODULE / 'data/sql/db-world/updates' / gen.MIGRATION
assert gen.MIGRATION == 'monsters_0004_family_data.sql'
assert migration.read_text(encoding='utf-8') == sql == (MODULE / 'data/generated/monster_models.sql').read_text(encoding='utf-8')
print('PASS: monster family data: numbers, clones, ability sheet sources and refusals, rows applied and read back.')
