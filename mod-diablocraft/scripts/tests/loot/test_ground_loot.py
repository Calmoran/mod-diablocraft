#!/usr/bin/env python3
"""Offline generator invariants; run without building the core."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_ground_loot as ground


class GroundLootGeneratorTests(unittest.TestCase):
    def test_mapping_matches_item_generator(self):
        # Check every pair against the existing generated item data, not against
        # another implementation of this generator's sort algorithm.
        sql = ground.render()
        item_sql = (ground.GENERATED / 'base_items.sql').read_text(encoding='utf-8')
        source = ground.read('base_items.csv')
        for row in source:
            match = re.search(r'\((\d+), ' + re.escape(ground.quote(row['d3_id'])) + r',', item_sql)
            self.assertIsNotNone(match, row['d3_id'])
            item = int(match[1])
            carrier = ground.CARRIER_BASE + item - ground.ITEM_BASE
            self.assertIn(f'VALUES ({item},{carrier});', sql)
            self.assertIn(f'entry={carrier},name={ground.quote(row["d3_name"])}', sql)
        self.assertEqual(sql.count('REPLACE INTO dc_ground_loot_carrier'), len(source)+53)

    def test_an_added_base_item_has_a_carrier_at_its_own_entry(self):
        # The Shaman's Ritual Mace and Totem (xnrvn.3) sit in the middle of the d3_id order but take the next free entries:
        # their carriers follow the entry (CARRIER_BASE + entry - ITEM_BASE), and no shipped carrier moves.
        added = ground.render_added_carriers()
        for d3_id, entry in (('Shaman_RitualMace_001', 101176), ('Shaman_Totem_001', 101177), ('Shaman_Unique_RitualMace_001', 101178)):
            carrier = ground.CARRIER_BASE + entry - ground.ITEM_BASE
            self.assertIn(f'VALUES ({entry},{carrier});', added, d3_id)
        self.assertEqual(added.count('REPLACE INTO dc_ground_loot_carrier'), 3)
        self.assertNotIn("entry=920469,name='Ritual Mace'", ground.render('shipped'))
        shipped = ground.render('shipped')
        self.assertIn("entry=920469,name='Shield'", shipped)       # the carrier the old numbering gave the Shield, unmoved
        self.assertEqual(shipped.count('REPLACE INTO dc_ground_loot_carrier'), 1114 + 53)
        # npcflag: the carriers loot_0012 cleared were the shipped ones; the added ones clear it themselves.
        self.assertIn('npcflag & ~16777216 WHERE entry IN (921176,921177,921178)', added)

    def test_csv_wins_on_reapply_and_no_characters_writes(self):
        # Ruling 2026-09-19: ground_loot_parameters.csv is in data/tunables/ and
        # the sheet is the source of truth, so a re-apply writes its numbers
        # over the table's instead of leaving an edit stranded in the CSV.
        sql = ground.render()
        update = sql.split('ON DUPLICATE KEY UPDATE', 1)[1].split(';', 1)[0]
        self.assertIn('tuned_value=VALUES(tuned_value)', update)
        self.assertNotIn('dc_loot_buffer', sql)
        self.assertNotIn('dc_item_unidentified', sql)
        self.assertEqual(sql.count('flags_extra=8576'), len(ground.read('base_items.csv'))+53)
        self.assertEqual(sql.count('unit_flags=770'), len(ground.read('base_items.csv'))+53)
        self.assertIn('START TRANSACTION;', sql)
        self.assertNotIn('TRUNCATE TABLE', sql)

    def test_reject_invalid_inputs_before_output(self):
        # The parameters sheet moved to data/tunables/ and is read through
        # read_tunables now, so that is what this patches.
        original = ground.read_tunables
        def invalid(name):
            rows = original(name)
            if name == 'ground_loot_parameters.csv':
                rows[0]['tuned_value'] = 'nan'
            return rows
        with patch.object(ground, 'read_tunables', invalid):
            with self.assertRaises(ValueError):
                ground.render()

    def test_repeatable_output_and_correct_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / 'generated'
            updates = Path(directory) / 'db-world/updates'
            with patch.object(ground, 'GENERATED', generated), patch.object(ground, 'UPDATES', updates):
                ground.main()
                first = (updates / 'loot_0005_ground_carriers.sql').read_bytes()
                added = (updates / ground.CARRIERS_ADDED).read_bytes()
                ground.main()
                self.assertEqual(first, (updates / 'loot_0005_ground_carriers.sql').read_bytes())
                self.assertEqual(added, (updates / ground.CARRIERS_ADDED).read_bytes())
                # loot_0005 carries the base items 0002 shipped; the mirror every base item, so the mirror is the two.
                self.assertEqual(first, ground.render('shipped').encode())
                mirror = (generated / 'ground_loot.sql').read_text(encoding='utf-8')
                self.assertEqual(mirror.count('REPLACE INTO dc_ground_loot_carrier'),
                                 first.decode().count('REPLACE INTO dc_ground_loot_carrier') + added.decode().count('REPLACE INTO dc_ground_loot_carrier'))

    def test_white_drops_have_no_beam(self):
        # Ruling 2026-09-28: normal (white) gets no beam, as the explicit value
        # 0 rather than a missing row; every other rarity keeps a real spell.
        beams = {r['rarity']: int(r['beam_spell']) for r in ground.read_visuals()}
        self.assertEqual(beams['normal'], ground.NO_BEAM)
        self.assertTrue(all(beams[r] > 0 for r in ('magic', 'rare', 'legendary', 'set')))
        self.assertIn("('normal',1,0)", ground.render())
        self.assertIn("('normal',1,0)", ground.render_visuals())
        materials = {r['name']: r['rarity'] for r in ground.read('ground_loot_materials.csv')}
        self.assertEqual(materials['Reusable Parts'], 'normal')

    def test_negative_beam_rejected(self):
        original = ground.read
        def invalid(name):
            rows = original(name)
            if name == 'ground_loot_visuals.csv':
                rows[0]['beam_spell'] = '-1'
            return rows
        with patch.object(ground, 'read', invalid):
            with self.assertRaises(ValueError):
                ground.render_visuals()

    def test_visuals_migrations_carry_the_full_renders_rows(self):
        # loot_0008 is applied, so it keeps the five rarities and the Primal look (diablocraft-t3t8) ships in
        # its own migration; between them they hold every row the full render has.
        full = ground.VISUAL_ROWS.search(ground.render())[0]
        lines = [line.strip().rstrip(',;') for line in full.splitlines() if line.startswith('(')]
        self.assertEqual(len(lines), 6)
        for line in lines:
            in_primal = line.startswith("('primal'")
            self.assertIn(line, ground.render_primal_visual() if in_primal else ground.render_visuals())
            self.assertNotIn(line, ground.render_visuals() if in_primal else ground.render_primal_visual())

    def test_applied_carriers_with_beam_drift_ship_only_loot_0008(self):
        # loot_0005 is applied: a beam-only change must leave it byte-identical
        # and write loot_0008, without the frozen warning; any other drift
        # must still reach the guard.
        applied = ground.VISUAL_ROWS.sub(
            "REPLACE INTO dc_ground_loot_visual (rarity,plate_level,beam_spell) VALUES\n('normal',1,25824);\n",
            ground.render('shipped'))
        for drift, guarded in ((applied, False), (applied.replace('SET NAMES', 'SET  NAMES', 1), True)):
            with tempfile.TemporaryDirectory() as directory:
                generated = Path(directory) / 'generated'
                updates = Path(directory) / 'db-world/updates'
                updates.mkdir(parents=True)
                (updates / ground.CARRIERS).write_text(drift, encoding='utf-8', newline='\n')
                calls = []
                def record(module, target, content, **_):
                    calls.append(Path(target).name)
                    return True
                with patch.object(ground, 'GENERATED', generated), patch.object(ground, 'UPDATES', updates), \
                     patch.object(ground, 'migration_state', lambda *_: ground.MIGRATION_FROZEN), \
                     patch.object(ground, 'write_migration', record):
                    ground.main()
                self.assertEqual(ground.CARRIERS in calls, guarded)
                self.assertIn(ground.VISUALS, calls)
                self.assertIn(ground.PRIMAL_VISUAL, calls)
                self.assertEqual((updates / ground.CARRIERS).read_text(encoding='utf-8'), drift)


BASE = ground.MODULE.parent / "azerothcore-wotlk/data/sql/base/db_world"
SPELLCLICK = 16777216
BYSTANDER = 2840   # a stock entry the carriers never use


def core_table(name):
    """The core's own CREATE TABLE for `name`, from its base SQL."""
    text = (BASE / f"{name}.sql").read_text(encoding="utf-8")
    return re.search(rf"CREATE TABLE `{name}` \(.*?\) ENGINE=[^;]*;", text, re.S).group(0)


class CarrierSpellclickFlagTests(unittest.TestCase):
    """The core logs one error per template that has UNIT_NPC_FLAG_SPELLCLICK and no npc_spellclick_spells row, then strips
    the flag itself (ObjectMgr::LoadNPCSpellClickSpells). The carriers have no spellclick rows (BeforeSpellClick claims the
    pickup), so loot_0005's npcflag 16777216 made one line per carrier on every start (1167 of them): a migration that
    clears the bit leaves the templates the way the core leaves them, without the line."""

    def test_replay_leaves_no_carrier_with_the_spellclick_flag(self):
        from test_account_economy_sql import MYSQL, isolated
        stock = (core_table("creature_template") + "\n" + core_table("creature_template_model") + "\n"
                 f"INSERT INTO creature_template (entry, name, subname, npcflag, faction) VALUES ({ground.CLONE_SOURCE}, 'Stock', 'x', 0, 35);\n"
                 # a creature that is no carrier, with the bit and a flag beside it (a vehicle with spellclick rows, say)
                 f"INSERT INTO creature_template (entry, name, subname, npcflag, faction) VALUES ({BYSTANDER}, 'Bystander', 'x', {SPELLCLICK | 3}, 35);\n")
        applied = (ground.UPDATES / ground.CARRIERS).read_text(encoding="utf-8")
        clear = ground.render_carrier_flag()

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n"), done.stderr

            def flagged(database):
                return mysql("SELECT COUNT(*), SUM(npcflag & %d > 0) FROM creature_template t JOIN dc_ground_loot_carrier c "
                             "ON c.creature_entry = t.entry" % SPELLCLICK, database)[1]

            def replay(database, *files):
                mysql(f"CREATE DATABASE {database} CHARACTER SET utf8mb4;")
                code, _out, err = mysql(stock + "\n".join(files), database)
                self.assertEqual(code, 0, err)

            replay("carriers_base", applied)
            total, set_before = (int(n) for n in flagged("carriers_base").split("\t"))
            self.assertGreater(total, 1000, "loot_0005 made the carriers")
            self.assertEqual(set_before, total, "the base: every carrier has the flag, which is what the core logs")
            replay("carriers_fixed", applied, clear, clear)   # twice: the file re-applies cleanly
            self.assertEqual(flagged("carriers_fixed"), f"{total}\t0")
            self.assertEqual(mysql("SELECT npcflag FROM creature_template WHERE entry = %d" % BYSTANDER, "carriers_fixed")[1],
                             str(SPELLCLICK | 3), "only the carriers are cleared")
            # the carrier's other flags survive: the same row, one bit lower
            self.assertEqual(mysql("SELECT COUNT(DISTINCT npcflag), MAX(npcflag), MIN(unit_flags), MAX(flags_extra) "
                                   "FROM creature_template t JOIN dc_ground_loot_carrier c ON c.creature_entry = t.entry", "carriers_fixed")[1],
                             "1\t0\t770\t8576")

        isolated(body)

    def test_the_migration_is_the_generators_and_sorts_after_the_carriers(self):
        self.assertEqual((ground.UPDATES / ground.CARRIER_FLAG).read_text(encoding="utf-8"), ground.render_carrier_flag())
        self.assertGreater(ground.CARRIER_FLAG, ground.CARRIERS)
        self.assertNotIn(ground.CARRIER_FLAG, (ground.MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))
        # the flag the carriers are inserted with is the bit it clears (one number, two files)
        self.assertIn(f"npcflag={SPELLCLICK},", ground.render())
        self.assertIn(f"~{SPELLCLICK}", ground.render_carrier_flag())

    def test_main_writes_it_next_to_the_other_migrations(self):
        with tempfile.TemporaryDirectory() as directory:
            updates = Path(directory) / "db-world/updates"
            with patch.object(ground, "GENERATED", Path(directory) / "generated"), patch.object(ground, "UPDATES", updates):
                ground.main()
            self.assertEqual((updates / ground.CARRIER_FLAG).read_text(encoding="utf-8"), ground.render_carrier_flag())


if __name__ == '__main__':
    unittest.main()
