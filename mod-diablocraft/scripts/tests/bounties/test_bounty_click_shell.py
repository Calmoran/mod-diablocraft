"""The Bounty Click channel's spell shell (diablocraft-e719a; World's W2, dm9vg.2, casts it on the player).

What W2 needs of the record, each read out of the generated spell_dbc rows the migration carries and set against its source: one
shell, 83600, named 'Activating' (the cast bar), a cast of maxroll's 4 seconds (the cast-time row looked up in the stock
SpellCastTimes.dbc, and the rifts tunable bounty_click_channel_ms once World's row is on the sheet), nothing in the record that
interrupts it (the server does, on damage), a harmless effect on the caster, no cost or cooldown, and the id in dc_spell_shells.h as
Shells::BountyClick. What this does not run: the core's loader, the cast, the client's cast bar (the in-game step is
docs/test-diablocraft-e719a.md).
"""
import csv
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as generator  # noqa: E402
from test_control_immunity_gap import insert_rows, newest_spell_render, number  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
GENERATED = MODULE / "data/generated/spell_shells.sql"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0060_bounty_click_shell.sql"
SHELLS_CSV = MODULE / "data/generated/spell_shells.csv"
HEADER = MODULE / "src/combat/dc_spell_shells.h"
RIFTS = MODULE / "data/tunables/rifts.csv"
SPELL_EFFECT_DUMMY, TARGET_UNIT_CASTER = 3, 1
D3_SECONDS = 4   # maxroll bounties: "Clicking on an objective will start a 4 second channel"


def record(text):
    rows = [r for r in insert_rows(text, "spell_dbc") if r["ID"] == "83600"]
    assert len(rows) == 1, len(rows)
    return rows[0]


def cast_ms(index):
    """The base cast time of a SpellCastTimes.dbc row (ID, CastTime, CastTimePerLevel, MinCastTime), from the stock client data."""
    rows, _, _, _ = generator.load_dbc("SpellCastTimes.dbc")
    return struct.unpack_from("<i", rows[index], 4)[0]


class BountyClickShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = GENERATED.read_text(encoding="utf-8")
        cls.row = record(cls.sql)

    def test_the_migration_carries_the_generated_record(self):
        # combat_0060 brought the shell; the generated render and the newest full spell render both carry the record it brought
        # unchanged. Nothing is asserted about their other records, so a later render of another record leaves this green.
        brought = record(MIGRATION.read_text(encoding="utf-8"))
        self.assertEqual(self.row, brought)
        self.assertEqual(brought, record(newest_spell_render(MIGRATION.parent).read_text(encoding="utf-8")))
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn("combat_0060", applied)

    def test_one_shell_named_for_the_cast_bar(self):
        shells = [r for r in csv.DictReader(SHELLS_CSV.read_text(encoding="utf-8").splitlines()) if r["kind"] == "bounty_click"]
        self.assertEqual([{"spell_id": "83600", "name": "Activating", "element": "physical", "base_spell": "10059", "kind": "bounty_click"}], shells)
        self.assertEqual("Activating", self.row["Name_Lang_enUS"])
        self.assertEqual(83600, generator.BOUNTY_CLICK_SPELL)
        self.assertEqual((83600, 83649), (generator.BOUNTY_ID_FIRST, generator.BOUNTY_ID_LAST))   # the bounties block, clear of every one before it
        self.assertGreater(generator.BOUNTY_ID_FIRST, generator.POWER_BUFF_ID_LAST)

    def test_a_four_second_cast_as_the_server_has_it(self):
        self.assertEqual(D3_SECONDS * 1000, cast_ms(number(self.row["CastingTimeIndex"])))
        self.assertEqual(D3_SECONDS * 1000, generator.BOUNTY_CLICK_CAST_MS)
        # World's tunable (W2) is the server's number; once it is on the sheet the record and it agree
        with RIFTS.open(encoding="utf-8", newline="") as stream:
            tunable = next((r for r in csv.DictReader(stream) if r["name"] == "bounty_click_channel_ms"), None)
        if tunable is None:
            self.skipTest("bounty_click_channel_ms is not on rifts.csv yet (World's W2 adds it)")
        self.assertEqual(D3_SECONDS * 1000, number(tunable["value"] or tunable["d3_value"]))

    def test_nothing_in_the_record_interrupts_it_and_it_does_nothing(self):
        for field in ("InterruptFlags", "AuraInterruptFlags", "ChannelInterruptFlags"):
            self.assertEqual(0, number(self.row[field]), field)
        self.assertEqual((SPELL_EFFECT_DUMMY, 0, 0), tuple(number(self.row["Effect_%d" % s]) for s in (1, 2, 3)))
        self.assertEqual((TARGET_UNIT_CASTER, 0), (number(self.row["ImplicitTargetA_1"]), number(self.row["ImplicitTargetB_1"])))
        for field in ("EffectAura_1", "EffectBasePoints_1", "EffectDieSides_1", "ManaCost", "ManaCostPct", "RecoveryTime",
                      "CategoryRecoveryTime", "StartRecoveryTime", "Category", "Mechanic", "Reagent_1"):
            self.assertEqual(0, number(self.row[field]), field)

    def test_the_server_reads_the_id_from_the_shells(self):
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uint32_t BountyClick = 83600;", header)
        ids = header[header.index("inline constexpr uint32_t ShellIds[] = {"):]
        self.assertIn("83600,", ids[:ids.index("};")])


if __name__ == "__main__":
    unittest.main()
