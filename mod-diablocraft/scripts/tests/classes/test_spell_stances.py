"""Check generated SQL/client shells have no inherited stance restrictions."""

import csv
import re
import struct
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as generator


def newest_shells_migration():
    """Return the newest applied full-render spell_shells migration.

    generate_spells.py rewrites the whole shell render into
    data/generated/spell_shells.sql and, when given a migration name, writes an
    identical copy under updates/. Every full rewrite is a new migration, so the
    shipped render is the newest file that carries the same generated-by header,
    the same FIRST_SPELL_ID floor and the same INSERT column list. The filename
    is discovered here instead of hardcoded: pinning combat_0005 was the stale
    assumption that broke when the render moved on. No migration is edited.
    """
    generated = (generator.GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
    columns = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", generated)[1]
    # The generator's own header line, read from its render: S1 moved the script
    # but its stamp kept the old path, and a pinned path went stale with it.
    header = generated.splitlines()[0]
    floor = f"DELETE FROM `spell_dbc` WHERE `ID` BETWEEN {generator.FIRST_SPELL_ID} AND"
    candidates = []
    for path in generator.UPDATES.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        if not text.startswith(header) or floor not in text:
            continue
        match = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", text)
        if match and match[1] == columns:
            candidates.append(path)
    assert candidates, "no full-render spell_shells migration found under updates/"

    def migration_number(path):
        return (int(re.search(r"_(\d+)_", path.name)[1]), path.name)

    return max(candidates, key=migration_number)


class SpellStances(unittest.TestCase):
    def test_sql_and_client_are_stance_free_and_stock_is_preserved(self):
        # The generated render is the authoritative current shells. The applied
        # combat_0005_ability_targeting.sql is frozen history and no longer what
        # the generator writes, so the render must equal the newest shipped
        # full-render migration, discovered dynamically rather than by a fixed
        # filename that goes stale every time the render moves on.
        sql = (generator.GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        newest = newest_shells_migration()
        self.assertEqual(sql, newest.read_text(encoding="utf-8"),
                         f"generated shell render drifted from {newest.name}")
        columns = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql)[1]
        columns = [column.strip().strip("`") for column in columns.split(",")]
        masks = [columns.index(name) for name in
                 ("ShapeshiftMask", "unk_320_2", "ShapeshiftExclude", "unk_320_3")]
        rows = [next(csv.reader([line[1:-2]], quotechar="'", skipinitialspace=True))
                for line in sql.splitlines() if line.startswith("(")]
        # Derived from the generator's own manifest rather than hardcoded: this
        # set was a literal range and went stale twice, once when the 09-rifts
        # shells grew past eleven and again when the stat shells were added.
        with (generator.GENERATED / "spell_shells.csv").open(encoding="utf-8-sig", newline="") as stream:
            manifest = {int(row["spell_id"]): row for row in csv.DictReader(stream)}
        expected_ids = set(manifest)
        bleed_ids = {spell_id for spell_id, row in manifest.items() if row["kind"] == "bleed"}
        self.assertTrue(bleed_ids, "no bleed shells to check")
        self.assertEqual({int(row[0]) for row in rows}, expected_ids)
        self.assertEqual(min(expected_ids), generator.FIRST_SPELL_ID)
        for row in rows:
            for index in masks:
                self.assertEqual(int(row[index]), 0, f"SQL {row[0]} {columns[index]}")
            if int(row[0]) in bleed_ids:
                # 3 PERIODIC_DAMAGE: the native tick with core patch 0016's
                # provider (decisions.md 2026-09-23, pre-beta-bugs-b item 4).
                for name, value in (("Effect_1", 6), ("EffectAura_1", 3),
                                    ("EffectAuraPeriod_1", 1000), ("ImplicitTargetA_1", 6),
                                    ("Effect_2", 0), ("Effect_3", 0)):
                    self.assertEqual(int(row[columns.index(name)]), value)
                duration = int(row[columns.index("DurationIndex")])
                durations = generator.load_dbc("SpellDuration.dbc")[0]
                self.assertEqual(struct.unpack_from("<i", durations[duration], 4)[0], 5000)
                self.assertTrue(int(row[columns.index("Attributes")]) & 0x04000000)

        # Ruling 2026-09-13: every learned shell stays visible; only unlearned
        # helper records are hidden. The chain-beam visuals have since joined
        # the per-enemy lockout markers, so this checks by kind instead of the
        # fixed {81194} id that went stale, and proves no learned shell is ever
        # hidden.
        unlearned_hidden = {"primary_internal", "beam_visual"}
        hidden = {int(row[0]) for row in rows
                  if int(row[columns.index("Attributes")]) & generator.SPELL_ATTR0_DO_NOT_DISPLAY}
        self.assertTrue(hidden)
        self.assertEqual({manifest[spell_id]["kind"] for spell_id in hidden}, unlearned_hidden,
                         {spell_id: manifest[spell_id]["name"] for spell_id in hidden})

        stock = (generator.DBC / "Spell.dbc").read_bytes()
        client = generator.CLIENT_DBC.read_bytes()
        _, stock_count, fields, size, string_size = struct.unpack_from("<4sIIII", stock)
        magic, count, client_fields, client_size, _ = struct.unpack_from("<4sIIII", client)
        self.assertEqual((magic, client_fields, client_size), (b"WDBC", fields, size))
        # generate_spells.py's __main__ runs generate_wings.py afterwards, which
        # appends its cosmetic rows to this same file. So the shells are a subset
        # of what was added, not all of it, and the count is a lower bound. This
        # assertion used to be an equality and broke the moment wings landed.
        stock_end = 20 + stock_count * size
        wing_ids = {int(row['spell_id']) for row in generator.read_csv('wing_variants.csv')}
        preserved = b''.join(stock[i:i+size] for i in range(20,stock_end,size)
            if struct.unpack_from('<I',stock,i)[0] not in expected_ids | wing_ids)
        self.assertGreaterEqual(count, len(preserved)//size + len(expected_ids))
        self.assertEqual(client[20:20+len(preserved)], preserved)
        client_strings = 20 + count * size
        self.assertEqual(client[client_strings:client_strings + string_size], stock[stock_end:])
        found = set()
        for offset in range(20+len(preserved), client_strings, size):
            spell_id = struct.unpack_from("<I", client, offset)[0]
            found.add(spell_id)
            if spell_id in expected_ids:
                for index in masks:
                    self.assertEqual(struct.unpack_from("<I", client, offset + index * 4)[0],
                                     0, f"DBC {spell_id} {columns[index]}")
        self.assertTrue(expected_ids <= found, expected_ids - found)
    def test_shell_names_are_unique(self):
        # Only genuinely learned shells are looked up by name. Unlearned helpers
        # (ability auras, token storage, archon copies, ...) reuse the skill's
        # real D3 name and are addressed by id. active/rune/passive is exactly
        # the set generate_class_catalogue.py builds a catalogue from, so this
        # follows the learned contract instead of assuming every row's name is
        # unique, which reported 143 helper duplicates as failures.
        learned = {"active", "rune", "passive"}
        with (generator.GENERATED / "spell_shells.csv").open(encoding="utf-8-sig", newline="") as stream:
            names = [row["name"] for row in csv.DictReader(stream) if row["kind"] in learned]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        self.assertEqual(duplicates, [], duplicates)


if __name__ == "__main__":
    unittest.main()
