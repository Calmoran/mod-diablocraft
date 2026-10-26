"""N-SUMMON (diablocraft-uisny): the creature templates and the AI of the item-summoned allies.

What runs: the generator on data/legendary_summons.csv (its checks and its SQL), the production header
src/rifts/dc_ally.h compiled and driven with the sheet's own entries and scripts, and cross-source checks against
the pinned core (every donor creature has a row and a model) and the module's other summon sheets (no entry is
shared). Source checks hold the wiring the class bodies cannot show without a worldserver: the scripts are registered,
every ally script starts with dc_ (so IsRiftTrash leaves the ally alone), and difficulty scaling skips them. The
contract (docs/contracts/legendary-world-pieces.md) must name every entry, script and the one hook.
NOT run here: the worldserver. That an ally follows, fights what its owner fights and leaves with its owner is
The designer's check on dev (docs/test-diablocraft-uisny.md).

DC_ALLY_ROOT points the read at a copy of the module root (mutation runs)."""
import csv
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'mod-diablocraft/scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import harness_env  # noqa: E402
import generate_legendary_summons as generator  # noqa: E402

MODULE = Path(os.environ.get('DC_ALLY_ROOT', ROOT / 'mod-diablocraft'))
CORE_SQL = ROOT / 'azerothcore-wotlk/data/sql/base/db_world'
read = lambda path: Path(path).read_text(encoding='utf-8')
sheet = list(csv.DictReader((MODULE / 'data/legendary_summons.csv').open(encoding='utf-8', newline='')))
entries = [int(r['entry']) for r in sheet]
scripts = sorted({r['script'] for r in sheet})
header, source = read(MODULE / 'src/rifts/dc_ally.h'), read(MODULE / 'src/rifts/dc_ally.cpp')


def body(text, anchor):
    start = text.find(anchor)
    assert start >= 0, 'anchor missing (renamed or moved; update this test): ' + anchor
    brace = text.index('{', start)
    depth = 0
    for index in range(brace, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError('unbalanced braces after ' + anchor)


# --- the sheet: eight allies, one per N-SUMMON row, entries that nothing else owns -------------------------------------
list_csv = list(csv.DictReader((ROOT / 'docs/research/legendary-bead-list.csv').open(encoding='utf-8', newline='')))
want = sorted(r['name'] for r in list_csv if 'N-SUMMON' in r['new_pieces'])
# the first eight (migrations 0001 and 0002, applied) are the bead list's N-SUMMON items; the ones past them (0003) are the Monk set's decoy
first = [r for r in sheet if int(r['entry']) <= generator.FIRST_BATCH_END]
later = [r for r in sheet if int(r['entry']) > generator.FIRST_BATCH_END]
assert sorted(r['item'] for r in first) == want, (sorted(r['item'] for r in first), want)
assert len(first) == 8 and len(sheet) == len(set(entries)) == 9 and [r['item'] for r in later] == ["Monkey King's Garb"]
assert entries == list(range(min(entries), min(entries) + len(entries)))        # contiguous: the header's range
for r in sheet:
    assert r['script'] in generator.SCRIPTS and r['why'] and r['summon']

# --- the generator: its SQL, and the rules it refuses ------------------------------------------------------------------
sql = generator.render(MODULE)
for r in first:
    entry, donor = int(r['entry']), int(r['donor_creature'])
    assert f"INSERT INTO dc_ally_clone SELECT * FROM creature_template WHERE entry={donor};" in sql
    assert re.search(rf"SET entry={entry},name='[^']*',.*ScriptName='{r['script']}',.*lootid=0.*mingold=0,maxgold=0", sql)
    assert f"INSERT INTO creature_template_model SELECT {entry},Idx,CreatureDisplayID,DisplayScale,Probability,VerifiedBuild FROM creature_template_model WHERE CreatureID={donor};" in sql
assert sql.count('INSERT INTO creature_template SELECT') == len(first)
assert read(MODULE / 'data/generated/legendary_summons_0001_templates.sql') == sql, 'regenerate: the generated file is stale'
assert read(MODULE / 'data/sql/db-world/updates/legendary_summons_0001_templates.sql') == sql, 'regenerate: the migration is stale'

# the ones past the first eight go in the next migration, template and difficulty reset together, and never into 0001 or 0002
sql_later = generator.render(MODULE, later=True) + generator.render_difficulty_reset(MODULE, later=True).split('\n', 1)[1]
for r in later:
    assert re.search(rf"SET entry={r['entry']},name='[^']*',.*ScriptName='{r['script']}',", sql_later)
    assert f"WHERE entry IN ({r['entry']});" in sql_later and f"entry={r['entry']}" not in sql
assert read(MODULE / 'data/generated/legendary_summons_0003_later_allies.sql') == sql_later, 'regenerate: the generated 0003 is stale'
assert read(MODULE / 'data/sql/db-world/updates/legendary_summons_0003_later_allies.sql') == sql_later, 'regenerate: the 0003 migration is stale'

def refused(rows, why):
    with tempfile.TemporaryDirectory(prefix='summons-', dir=ROOT / 'azerothcore-wotlk/build/_agent-scratch') as folder:
        copy = Path(folder)
        for name in ('data/legendary_summons.csv',) + generator.OTHER_SHEETS:
            (copy / name).parent.mkdir(parents=True, exist_ok=True)
        for name in generator.OTHER_SHEETS:
            (copy / name).write_text(read(MODULE / name), encoding='utf-8')
        with (copy / 'data/legendary_summons.csv').open('w', encoding='utf-8', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=list(sheet[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        try:
            generator.render(copy)
        except ValueError as error:
            assert why in str(error), (why, str(error))
            return
        raise AssertionError('the generator accepted: ' + why)

refused(sheet + [dict(sheet[0], entry='900110')], 'is taken')                 # the Wizard's Mirror Image entry
refused(sheet + [dict(sheet[0], entry='900101')], 'is taken')                 # an Ancient's
refused(sheet + [dict(sheet[0], entry='900130')], 'is taken')                 # the Monk's Mystic Ally (diablocraft-a0vq0)
refused(sheet + [dict(sheet[0])], 'is taken')                                 # a repeat of its own
refused([dict(sheet[0], script='dc_wizard_image')] + sheet[1:], 'script is one of')
refused([dict(sheet[0], why='')] + sheet[1:], 'needs its reason')

# --- the pinned core: every donor has a row and a model -----------------------------------------------------------------
template_sql, model_sql = read(CORE_SQL / 'creature_template.sql'), read(CORE_SQL / 'creature_template_model.sql')
for r in sheet:
    donor = int(r['donor_creature'])
    assert re.search(rf'^\({donor},', template_sql, re.M), f"{r['summon']}: donor {donor} has no creature_template row"
    assert re.search(rf'^\({donor},0,', model_sql, re.M), f"{r['summon']}: donor {donor} has no model"

# --- the migrations on a real MySQL: no ally keeps a donor's difficulty_entry_1..3 (diablocraft-fah9d) ---------------------
# 0001 clones the donor's whole row, and 17429 lists the heroic 18603: the ally 900122 claimed it (dev error "already listed
# as difficulty_entry_1 for another entry"). The rows come from the fixture's world copy, the SQL is the committed
# migrations, in a throwaway database that is dropped at the end.
UPDATES = MODULE / 'data/sql/db-world/updates'
assert read(MODULE / 'data/generated/legendary_summons_0002_difficulty_entries.sql') == generator.render_difficulty_reset(MODULE), \
    'regenerate: the generated 0002 is stale'
assert read(UPDATES / 'legendary_summons_0002_difficulty_entries.sql') == generator.render_difficulty_reset(MODULE), \
    'regenerate: the 0002 migration is stale'
mysql, defaults = fixture_db.mysql_and_defaults([])


def run_sql(text, database=None):
    done = subprocess.run([mysql, '--defaults-file=' + defaults, '--no-login-paths', '-N', *(['-D', database] if database else [])],
                          input=text, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def claimed(migrations):
    """(entry, column, value) of every ally difficulty_entry that is set after the migrations run on the core's rows."""
    database = 'dc_summons_' + uuid.uuid4().hex[:12]
    try:
        run_sql(f'CREATE DATABASE {database};')
        run_sql('CREATE TABLE creature_template LIKE acore_world.creature_template; '
                'INSERT INTO creature_template SELECT * FROM acore_world.creature_template; '
                'CREATE TABLE creature_template_model LIKE acore_world.creature_template_model; '
                'INSERT INTO creature_template_model SELECT * FROM acore_world.creature_template_model;', database)
        for name in migrations:
            run_sql(read(UPDATES / name), database)
        ids = ','.join(map(str, entries))
        out = run_sql('SELECT entry,1,difficulty_entry_1 FROM creature_template WHERE difficulty_entry_1<>0 AND entry IN (%s) UNION ALL '
                      'SELECT entry,2,difficulty_entry_2 FROM creature_template WHERE difficulty_entry_2<>0 AND entry IN (%s) UNION ALL '
                      'SELECT entry,3,difficulty_entry_3 FROM creature_template WHERE difficulty_entry_3<>0 AND entry IN (%s);' % (ids, ids, ids), database)
        return [tuple(map(int, line.split('\t'))) for line in out.splitlines()]
    finally:
        run_sql(f'DROP DATABASE IF EXISTS {database};')


old = claimed(['legendary_summons_0001_templates.sql'])
assert (900122, 1, 18603) in old, f'the pinned core no longer shows the 18603 clash, the test lost its proof: {old}'
assert claimed(['legendary_summons_0001_templates.sql', 'legendary_summons_0002_difficulty_entries.sql']) == [], \
    'an ally still lists a donor difficulty entry after 0002'
assert claimed(['legendary_summons_0001_templates.sql', 'legendary_summons_0002_difficulty_entries.sql', 'legendary_summons_0003_later_allies.sql']) == [], \
    'a later ally still lists a donor difficulty entry after 0003'

# --- the production header, compiled and driven with the sheet's own values -----------------------------------------------
others = [900100, 900102, 900110, 900117, min(entries) - 1, max(entries) + 1]
arguments = [a for e in entries for a in ('entry', str(e))] + [a for s in scripts for a in ('script', s)] + \
    [a for e in others for a in ('not-entry', str(e))] + \
    [a for s in ('dc_wizard_image', 'dc_ancient', 'npc_training_dummy', '', 'dc_legendary') for a in ('not-script', s)]
scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
with tempfile.TemporaryDirectory(prefix='summons-', dir=scratch) as folder:
    binary = Path(folder) / 'harness'
    subprocess.run(['c++', '-std=c++20', '-O0', '-UNDEBUG', '-Wall', '-Werror', '-I', str(MODULE / 'src/rifts'),
                    str(MODULE / 'tests/legendary_summons/harness.cpp'), '-o', str(binary)], check=True)
    done = harness_env.run([str(binary), *arguments], capture_output=True, text=True)
    assert done.returncode == 0 and 'legendary summons harness: ok' in done.stdout, done.stdout + done.stderr

# --- the wiring ---------------------------------------------------------------------------------------------------------------
names = re.findall(r'(\w+) = "(dc_legendary_\w+)"', header)
assert sorted(n for _, n in names) == scripts, (names, scripts)                          # the header lists the sheet's scripts
assert all(n.startswith('dc_') for n in scripts)                                         # IsRiftTrash keeps dc_ scripts out of the rift's monsters
assert 'new Script<FightingAI>(Fighting);' in source and 'new Script<PawnAI>(Pawn);' in source
assert 'Ally::RegisterScripts();' in body(read(MODULE / 'src/rifts/dc_rift_scripts.cpp'), 'void RegisterScripts()')
context = body(read(MODULE / 'src/difficulty/dc_difficulty.cpp'), 'bool CreatureContext(')
assert 'Rifts::Ally::IsAllyScript(creature->GetScriptName())' in context and 'return false' in context.split('IsAllyScript')[1].split(';')[0]
# the AI: it binds to a player summoner, leaves with its owner, never melees, the pawn is passive
bind = body(source, 'bool Bind(')
for fragment in ('SetOwnerGUID(owner)', 'SetCreatorGUID(owner)', 'SetFaction(player->GetFaction())', 'SetLevel(player->GetLevel())', 'UnSummon()'):
    assert fragment in bind, fragment
update = body(source, 'void UpdateAI(uint32 diff) override')
assert 'Leave(me)' in update and 'Ancients::PickTarget' in update and 'DoMeleeAttackIfReady' not in source
assert 'found->second.swing(*me, *player, *target)' in update and 'IsWithinMeleeRange(target)' in update
assert 'REACT_PASSIVE' in body(source, 'class PawnAI')
# the hook: registered once per entry, the table is read without a lock only because registration is at startup
assert 'Table()[entry] = {intervalMs, std::move(swing)};' in body(source, 'void OnSwing(')

# --- the contract -------------------------------------------------------------------------------------------------------------
contract = read(ROOT / 'docs/contracts/legendary-world-pieces.md')
section = contract[contract.index('## N-SUMMON'):]
for name in [str(e) for e in entries] + scripts + [r['item'] for r in sheet] + ['OnSwing', 'IsAllyEntry', 'TEMPSUMMON_TIMED_DESPAWN']:
    assert name in section, name

print('PASS: N-SUMMON: %d ally templates, the AI, its registration, scaling skip, contract.' % len(sheet))
