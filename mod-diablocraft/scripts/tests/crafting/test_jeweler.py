"""Validate generated Jeweler data and migrations in a disposable MySQL database."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_crafting import MODULE, read
from generate_hub_placements import DATA as OLD_HUB_PLACEMENTS, generate as placements
from generate_jeweler import recipe_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql', default=None)
    parser.add_argument('--defaults-file', default=None)
    args = parser.parse_args()
    if not (args.mysql and args.defaults_file):
        import fixture_db
        fixture_mysql, fixture_defaults = fixture_db.mysql_and_defaults([])
        args.mysql, args.defaults_file = args.mysql or fixture_mysql, args.defaults_file or fixture_defaults
    database = 'dc_jeweler_test_' + uuid.uuid4().hex
    command = [args.mysql, '--defaults-file='+str(Path(args.defaults_file).resolve()),
               '--no-login-paths', '--batch', '--raw', '--skip-column-names']
    def run(sql):
        return subprocess.run(command, input=sql, text=True, encoding='utf-8', capture_output=True,
                              check=True, env={k.upper(): v for k, v in os.environ.items()}).stdout.strip()
    def query(sql):
        return run(f'USE `{database}`;\n'+sql)
    def migration(name):
        return (MODULE/'data/generated'/name).read_text(encoding='utf-8')

    run(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
    try:
        for table in ('dc_gem_item', 'dc_gem_effect', 'dc_tier_phase', 'dc_world_areas', 'dc_loot_tuning',
                      'creature_template', 'creature_template_model', 'creature', 'dc_area_source', 'dc_area_spawn'):
            query(f'CREATE TABLE `{table}` LIKE acore_world.`{table}`;')
            if table in ('dc_gem_item', 'dc_gem_effect', 'dc_tier_phase', 'dc_world_areas', 'dc_loot_tuning'):
                query(f'INSERT INTO `{table}` SELECT * FROM acore_world.`{table}`;')
        query('INSERT INTO creature_template SELECT * FROM acore_world.creature_template WHERE entry=910000;'
              'INSERT INTO creature_template_model SELECT * FROM acore_world.creature_template_model WHERE CreatureID=910000;')
        query((MODULE/'data/sql/db-characters/updates/loot_0001_loot_buffer.sql').read_text(encoding='utf-8'))
        query("INSERT INTO dc_loot_buffer(guid,base_item,item_level,expires_at) VALUES(1,100000,70,DATE_ADD(NOW(),INTERVAL 60 SECOND));")
        sql = '\n'.join(migration(n) for n in ('crafting_0002_jeweler.sql', 'loot_0003_buffer_kind.sql', 'loot_0004_gem_tuning.sql', 'world_0008_jeweler.sql'))
        query(sql);query(sql)
        # diablocraft-jeweler-window (ruling q-1001-15): world_0008 created the Jeweler as 'Jeweler'; the
        # later migration names it Covetous Shen <Jeweler>. The hand-applied copy is the generated one.
        assert query('SELECT name,subname FROM creature_template WHERE entry=910004') == 'Jeweler'
        rename = migration('world_0025_jeweler_rename.sql')
        assert rename == (MODULE/'data/sql/db-world/updates/world_0025_jeweler_rename.sql').read_text(encoding='utf-8')
        query(rename);query(rename)
        assert query('SELECT name,subname FROM creature_template WHERE entry=910004') == 'Covetous Shen\tJeweler'
        assert query('SELECT COUNT(*) FROM creature_template WHERE entry=910004') == '1'
        assert query('SELECT name FROM creature_template WHERE entry=910000') != 'Covetous Shen'
        assert query('SELECT COUNT(*) FROM dc_jeweler_recipe') == '45'
        assert query("SELECT COUNT(*) FROM dc_jeweler_recipe r JOIN dc_gem_item i ON i.entry=r.input_entry JOIN dc_gem_item o ON o.entry=r.output_entry WHERE i.colour=o.colour AND o.`rank`=i.`rank`+1") == '45'
        actual = [tuple(map(int, line.split('\t'))) for line in query('SELECT * FROM dc_jeweler_recipe ORDER BY output_entry').splitlines()]
        assert actual == sorted(recipe_rows())
        assert query('SELECT COUNT(*) FROM dc_jeweler_recipe r JOIN dc_gem_effect e ON e.entry=r.output_entry') == '135'
        assert query("SELECT kind FROM dc_loot_buffer WHERE guid=1") == 'rolled'
        query("INSERT INTO dc_loot_buffer(guid,base_item,item_level,expires_at,kind) VALUES(2,103000,70,DATE_ADD(NOW(),INTERVAL 60 SECOND),'gem');")
        assert query("SELECT kind,item_level FROM dc_loot_buffer WHERE guid=2") == 'gem\t70'
        assert query("SELECT gem_chance_pct,gem_imperial_share_pct FROM dc_loot_tuning WHERE source='gem'") == '10\t10'
        assert query('SELECT npcflag,ScriptName FROM creature_template WHERE entry=910004') == '4225'
        # diablocraft-jeweler-window follow-up: the Jeweler repairs and sells nothing. world_0008 made it
        # a clone of the Blacksmith's 4225; world_0026 leaves gossip only (1): no repairer 4096, no vendor 128.
        flags = migration('world_0026_jeweler_flags.sql')
        assert flags == (MODULE/'data/sql/db-world/updates/world_0026_jeweler_flags.sql').read_text(encoding='utf-8')
        query(flags);query(flags)
        assert query('SELECT npcflag FROM creature_template WHERE entry=910004') == '1'
        assert query('SELECT npcflag&4096,npcflag&128,npcflag&1 FROM creature_template WHERE entry=910004') == '0\t0\t1'
        assert query('SELECT npcflag FROM creature_template WHERE entry=910000') == '4225'
        assert query('SELECT COUNT(*) FROM creature_template WHERE entry=910004') == '1'
        assert query('SELECT name FROM creature_template WHERE entry=910004') == 'Covetous Shen'
        assert query('SELECT COUNT(*) FROM creature_template_model WHERE CreatureID=910004') == query('SELECT COUNT(*) FROM creature_template_model WHERE CreatureID=910000')
        print('PASS 45 sourced recipes/effects, repeatable additive migrations, typed buffer preservation, 10% tunables and Jeweler flags/model')
        cases = [(1, ''), (14, ''), (15, 'Normal'), (29, 'Normal'), (30, 'Flawless'), (39, 'Flawless'),
                 (40, 'Square'), (49, 'Square'), (50, 'Flawless Square'), (60, 'Flawless Square'),
                 (61, 'Marquise'), (70, 'Marquise'), (71, '')]
        master = int(query("SELECT tier_id FROM dc_tier_phase WHERE tier_name='Master'"))
        for level, expected in cases:
            for tier in range(1, 11):
                want = expected + ('\nImperial' if 61 <= level <= 70 and tier >= master else '')
                got = query(f'SELECT gem_tier FROM dc_gem_drop WHERE {level} BETWEEN min_level AND max_level AND min_tier<={tier} ORDER BY min_tier')
                assert got == want, (level, tier, got, want)
        print('PASS 130 level/tier boundary cases; no craft-only drops or below-level-15 drops')
        # The frozen generator's input: the old hub's Blacksmith row is only a well-formed row to relabel (diablocraft-976b).
        with OLD_HUB_PLACEMENTS.open(encoding='utf-8', newline='') as stream:
            source = next(r for r in csv.DictReader(stream) if json.loads(r['placement'])['id'] == 910000)
        source = dict(source)
        row = json.loads(source['placement']);row['id'] = 910004
        source['placement'] = json.dumps(row)
        scratch = MODULE.parent/'azerothcore-wotlk/build/_agent-scratch/scripts'
        scratch.mkdir(parents=True, exist_ok=True)  # absent in a fresh release-gate worktree
        with tempfile.TemporaryDirectory(prefix='jeweler-placement-test-', dir=scratch) as temporary:
            path = Path(temporary)/'placement.csv'
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(source));writer.writeheader();writer.writerow(source)
            sql = placements(path, {'c': {910004}})
            query(sql);query(sql)
        assert query('SELECT phaseMask FROM creature WHERE id=910004 ORDER BY phaseMask') == '\n'.join(map(str,range(1,11)))
        assert query('SELECT COUNT(*) FROM dc_area_spawn') == '9'
        print('PASS Jeweler placement generation restores one source and nine managed tier copies without touching other services')
    finally:
        run(f'DROP DATABASE `{database}`;')


if __name__ == '__main__':
    main()
