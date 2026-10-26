"""the designer's monster model picks reach the data and the generated rows (diablocraft-5p3n).

Four sources have to agree: the designer's picks file (frozen beside this test), data/d3/monster_family_models.csv
(import_monster_picks.py), the SQL generate_monster_models.py writes, and the client's Item.dbc. The SQL is
applied to a scratch schema on the fixture mysqld (never the live one) and read back, so a wrong column or a
quoting slip fails here and not at the migration.

DC_MONSTER_MODELS_SOURCE points the generator import at a mutated copy (mutation runs)."""
import csv
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
sys.path.insert(0, str(MODULE / 'scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import import_monster_picks as importer  # noqa: E402

source = Path(os.environ.get('DC_MONSTER_MODELS_SOURCE', MODULE / 'scripts/generate/monsters/generate_monster_models.py'))
spec = importlib.util.spec_from_file_location('generate_monster_models', source)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

picks = list(csv.DictReader(open(MODULE / 'tests/monster_models/monster_model_picks.csv', encoding='utf-8')))
rows = {r['monster']: r for r in csv.DictReader(open(MODULE / 'data/d3/monster_family_models.csv', encoding='utf-8'))}
roster = [r['name'] for r in csv.DictReader(open(MODULE / 'data/d3/monster_roster.csv', encoding='utf-8'))]
by_slug = {importer.slug(name): rows[name] for name in roster}
items = importer.client_items()

# --- the data: one row per roster monster, every pick carried over -----------------------------------
assert list(rows) == roster and len(roster) == 65
assert len(picks) == 42 and sum(1 for p in picks if p['npc_id']) == 41
assert sum(r['picked'] == 'yes' for r in rows.values()) == 41
for pick in picks:
    row = importer.roster_row(by_slug, pick['monster_slug'])    # the importer's own lookup: the store may send an old slug
    assert row is not None, pick['monster_slug']
    if not pick['npc_id']:
        assert row['picked'] == 'no'                          # Decaying Cryptstalker: left as it was, with the designer's note
        assert 'does not appear to exist' in row['notes'] and row['candidates']
        continue
    assert row['picked'] == 'yes' and row['wow_creature_id'] == pick['npc_id'], pick['monster_slug']
    shown = gen.displays(row['displays'])
    if pick['display']:
        assert [d for d, _, _ in shown] == [int(pick['display'])], pick['monster_slug']   # pinned: only that skin
    else:
        assert len(shown) >= 1
    assert (float(row['scale']) if row['scale'] else None) == (float(pick['scale']) if pick['scale'] else None)
    hand = [int(pick[c]) for c in ('mainhand', 'offhand') if pick[c]]
    got = [int(row[c]) for c in ('mainhand', 'offhand', 'ranged') if row[c]]
    assert sorted(hand) == sorted(got), pick['monster_slug']                               # same weapons, whichever slot
    for item in got:
        assert item in items, (pick['monster_slug'], item)                                 # the client knows every weapon id
# the three named cases of the brief
archer = rows['Skeletal Archer']
assert (archer['mainhand'], archer['offhand'], archer['ranged']) == ('', '', '2504')       # Worn Shortbow is ranged, not a hand item
hound = rows['Fallen Hound']
assert hound['displays'] == '24908:1:1' and hound['wow_creature_id'] == '253655'           # not a WotLK NPC: its pinned display
shaman = rows['Fallen Shaman']
assert (shaman['mainhand'], shaman['offhand']) == ('3327', '27463')                         # a staff and a dagger
assert len(gen.displays(rows['Dark Berserker']['displays'])) == 3                           # every skin of the NPC, rolled per spawn
assert rows['Savage']['displays'] == '8869:1:1' and rows['Savage']['scale'] == '3'          # pinned skin, the designer's size
# the tweak round (diablocraft-wnhg), the designer's dev look: three sizes, the satyr for the shaman, the Tomb Guardian's aura
# the roster renames (diablocraft-ibrp): the picks store may still send an old slug, the importer maps it to the new name
assert all(s in by_slug for s in importer.RENAMED_SLUGS.values()) and not any(s in by_slug for s in importer.RENAMED_SLUGS)
# the frozen store copy keeps the slugs the designer's page still sends, so the map is what lets them land
assert {'night-clan-shaman', 'ice-clan-brawler', 'dune-wasp', 'plague-swarm'} <= {p['monster_slug'] for p in picks}
assert {old: importer.roster_row(by_slug, old)['monster'] for old in importer.RENAMED_SLUGS} == {
    'night-clan-shaman': 'Moon Clan Shaman', 'ice-clan-brawler': 'Ice Clan Warrior', 'bogan-beast': 'Tusked Bogan',
    'dune-wasp': 'Sand Wasp', 'shade': 'Shade Stalker', 'plague-swarm': 'Stinging Swarm'}
assert rows['Stinging Swarm']['wow_creature_id'] == '14894' and rows['Stinging Swarm']['scale'] == '0.2' and 'Plague Swarm' not in rows    # the pick is kept (diablocraft-yqlv)
assert importer.roster_row(by_slug, 'moon-clan-shaman') is importer.roster_row(by_slug, 'night-clan-shaman')   # new slug, same row
assert importer.roster_row(by_slug, 'not-a-monster') is None
assert [rows[n]['scale'] for n in ('Blood Clan Warrior', 'Spiderling', 'Carrion Bat')] == ['0.5', '0.3', '2.5']
assert rows['Moon Clan Shaman']['wow_creature_id'] == '3758' and rows['Moon Clan Shaman']['displays'] == rows['Moon Clan Warrior']['displays']
assert rows['Moon Clan Shaman']['mainhand'] == '10826'                                       # weapon kept
assert {n: r['auras'] for n, r in rows.items() if r['auras']} == {'Tomb Guardian': '47840'}  # a Spell.dbc id, no other monster has one
assert rows['Fallen Shaman']['scale'] == '1.4' and rows['Savage']['scale'] == '3'            # left for batch 2


# --- the importer's slot rule, against a double of the item table -----------------------------------
class Db:
    def __init__(self, types):
        self.types = types

    def query(self, sql):
        item = int(re.search(r'entry=(\d+)', sql).group(1))
        return [str(self.types[item])] if item in self.types else []


bow = importer.weapons(Db({2504: 15}), items, {'mainhand': '2504', 'offhand': ''}, 'x')
assert bow == ('', '', '2504')
assert importer.weapons(Db({3327: 17, 27463: 13}), items, {'mainhand': '3327', 'offhand': '27463'}, 'x') == ('3327', '27463', '')
for bad in (Db({}), Db({2504: 15})):
    try:
        importer.weapons(bad, items, {'mainhand': '999999999', 'offhand': ''}, 'x')
    except SystemExit:
        continue
    raise AssertionError('an item id the client does not have must stop the import')

# --- the generator ----------------------------------------------------------------------------------
sql, picked, ids = gen.render()
# diablocraft-o18f: every monster gets rows (the designer's 41 picks and the 23 placeholders), bar the held-back Decaying Cryptstalker
assert len(picked) == 64 and sum(r['picked'] == 'yes' for r in picked) == 41 and gen.HELD_BACK == {'Decaying Cryptstalker'}
assert all(ids[name] == 950000 + i for i, name in enumerate(roster, 1))                     # the roster's place, stable across batches
entries = {ids[r['monster']] for r in picked}
assert len(entries) == 64 and all(950001 <= e <= 950999 for e in entries)
# the champion and rare clones of these entries do not meet the stock clones in the committed migration
stock = (MODULE / 'data/sql/db-world/updates/rifts_0006_elite_clones.sql').read_text(encoding='utf-8')
stock_entries = set()
for columns, values in re.findall(r"INSERT INTO `creature_template` \(([^)]*)\) VALUES \(([^;]*)\);", stock):
    stock_entries.add(int(values.split(',')[columns.replace('`', '').split(',').index('entry')]))   # values hold no commas: strings are hex
assert stock_entries
for entry in entries:
    assert 8000000 + entry not in stock_entries and 9000000 + entry not in stock_entries

# --- the SQL, applied to a scratch schema on the fixture and read back ------------------------------
mysql, defaults = fixture_db.mysql_and_defaults([])
scratch = 'scratch_monster_models_%d' % os.getpid()


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
    # a stale champion and rare row from an earlier render: the rerun clears it
    run('INSERT INTO %s.creature_template (entry, name) VALUES (8950999, "stale"), (9950999, "stale")' % scratch)
    run(None, scratch, sql)
    run(None, scratch, sql)                                                                  # twice: a rerun replaces, never doubles
    total = lambda table: int(run('SELECT COUNT(*) FROM %s' % table, scratch)[0][0])
    # Part 1 (diablocraft-uole): each picked monster also has a champion and a rare row, with the same models, gear and addon
    assert total('creature_template') == 3 * 64 and total('dc_monster_family') == 64
    assert total('creature_equip_template') == 3 * 64
    assert total('creature_template_model') == 3 * sum(len(gen.displays(r['displays'])) for r in picked)
    weaponed = [r for r in picked if r['mainhand'] or r['offhand'] or r['ranged']]
    addoned = [r for r in picked if r['mainhand'] or r['offhand'] or r['ranged'] or r['auras']]
    assert total('creature_template_addon') == 3 * len(addoned)
    assert len(addoned) == sum(1 for p in picks if p['mainhand'] or p['offhand'] or p['auras'])   # armed, or with an aura
    for r in picked:
        entry = ids[r['monster']]
        name = run('SELECT name FROM creature_template WHERE entry=%d' % entry, scratch)[0][0]
        assert name == r['monster']
        models = run('SELECT CreatureDisplayID, DisplayScale, Probability FROM creature_template_model '
                     'WHERE CreatureID=%d ORDER BY Idx' % entry, scratch)
        want = [(d, round(s * (float(r['scale']) if r['scale'] else 1), 4), p) for d, s, p in gen.displays(r['displays'])]
        assert [(int(a), round(float(b), 4), float(c)) for a, b, c in models] == want, r['monster']
        equip = run('SELECT ItemID1, ItemID2, ItemID3 FROM creature_equip_template WHERE CreatureID=%d AND ID=1' % entry, scratch)[0]
        assert equip == [r['mainhand'] or '0', r['offhand'] or '0', r['ranged'] or '0'], r['monster']
        sheath = run('SELECT bytes2 FROM creature_template_addon WHERE entry=%d' % entry, scratch)
        if r in weaponed:
            assert sheath == [['2' if r['ranged'] else '1']], r['monster']                     # a bow drawn as ranged, the rest as melee
        else:
            assert sheath == ([['0']] if r['auras'] else []), r['monster']                      # an aura alone: no weapon to draw
        auras = run('SELECT auras FROM creature_template_addon WHERE entry=%d' % entry, scratch)
        assert auras == ([[r['auras']]] if r['auras'] else [['NULL']] if r in weaponed else []), r['monster']
    # nothing outside the three ranges, nothing for the one monster held back
    assert run('SELECT COUNT(*) FROM creature_template WHERE entry NOT BETWEEN 950001 AND 950999 '
               'AND entry NOT BETWEEN 8950001 AND 8950999 AND entry NOT BETWEEN 9950001 AND 9950999', scratch) == [['0']]
    assert run('SELECT COUNT(*) FROM creature_template WHERE entry = 8950999 OR entry = 9950999', scratch) == [['0']]
    assert run("SELECT COUNT(*) FROM creature_template WHERE name='Decaying Cryptstalker'", scratch) == [['0']]
finally:
    run('DROP DATABASE IF EXISTS %s' % scratch)
# last, so a mutation run meets the targeted assertions above before this one: the committed files are this render
migration = MODULE / 'data/sql/db-world/updates' / gen.MIGRATION
assert migration.read_text(encoding='utf-8') == sql == (MODULE / 'data/generated/monster_models.sql').read_text(encoding='utf-8')
print('PASS: monster model picks: data, importer slots, generated rows applied and read back.')
