"""The bounty travel cast's spell shell (diablocraft-dm9vg.10; ruling 2026-10-12: from the open world bounty travel is a cast).

Read out of the generated spell_dbc rows the new migration carries: one shell, 83601, named 'Teleporting' (the cast bar), a cast as
long as the rifts tunable bounty_travel_cast_ms, whose default is Town Portal's (town_portal_cast_ms), with the cast-time row looked
up in the stock SpellCastTimes.dbc; a harmless effect on the caster; no cost or cooldown; the interrupt flags left to the server, as
Town Portal's are (dc_bounties.cpp sets them at load); and the id in dc_spell_shells.h as Shells::BountyTravel. What this does not
run: the core's loader, the cast, the client's cast bar (docs/test-diablocraft-dm9vg.10.md).
"""
import re
import csv
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as generator  # noqa: E402
from test_bounty_click_shell import cast_ms  # noqa: E402
from test_control_immunity_gap import insert_rows, newest_spell_render, number  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
GENERATED = MODULE / "data/generated/spell_shells.sql"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0062_bounty_travel_shell.sql"
SHELLS_CSV = MODULE / "data/generated/spell_shells.csv"
HEADER = MODULE / "src/combat/dc_spell_shells.h"
RIFTS = MODULE / "data/tunables/rifts.csv"
SPELL_EFFECT_DUMMY, TARGET_UNIT_CASTER = 3, 1


def rifts(name):
    with RIFTS.open(encoding="utf-8", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if r["name"] == name)
    return number(row["value"] or row["d3_value"])


class BountyTravelShell(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = GENERATED.read_text(encoding="utf-8")
        rows = [r for r in insert_rows(cls.sql, "spell_dbc") if r["ID"] == "83601"]
        assert len(rows) == 1, len(rows)
        cls.row = rows[0]

    def test_the_migration_is_the_generated_full_replacement(self):
        # combat_0062 brought the shell; the generated render and the newest full spell render both carry the record it brought
        # unchanged. Nothing is asserted about their other records, so a later render of another record leaves this green.
        brought = [r for r in insert_rows(MIGRATION.read_text(encoding="utf-8"), "spell_dbc") if r["ID"] == "83601"]
        self.assertEqual([self.row], brought)
        newest = newest_spell_render(MIGRATION.parent)
        self.assertEqual(brought, [r for r in insert_rows(newest.read_text(encoding="utf-8"), "spell_dbc") if r["ID"] == "83601"], newest.name)
        # the replacement's range ends at the newest record of any class: 83601 when this shell was the last, higher since
        # the Monk's block (diablocraft-3mk78, to 83864)
        top = re.search(r"DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 81000 AND (\d+);", self.sql)
        self.assertIsNotNone(top)
        self.assertGreaterEqual(int(top.group(1)), 83601)
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn("combat_0062", applied)

    def test_one_shell_named_for_the_cast_bar(self):
        shells = [r for r in csv.DictReader(SHELLS_CSV.read_text(encoding="utf-8").splitlines()) if r["kind"] == "bounty_travel"]
        self.assertEqual([{"spell_id": "83601", "name": "Teleporting", "element": "physical", "base_spell": "10059",
                           "kind": "bounty_travel"}], shells)
        self.assertEqual("Teleporting", self.row["Name_Lang_enUS"])
        self.assertEqual(generator.BOUNTY_ID_FIRST + 1, generator.BOUNTY_TRAVEL_SPELL)

    def test_town_portals_cast_length_by_default(self):
        self.assertEqual(rifts("town_portal_cast_ms"), rifts("bounty_travel_cast_ms"))
        self.assertEqual(rifts("bounty_travel_cast_ms"), generator.BOUNTY_TRAVEL_CAST_MS)
        self.assertEqual(generator.BOUNTY_TRAVEL_CAST_MS, cast_ms(number(self.row["CastingTimeIndex"])))

    def test_it_does_nothing_and_the_server_owns_its_interrupts(self):
        for field in ("InterruptFlags", "AuraInterruptFlags", "ChannelInterruptFlags"):
            self.assertEqual(0, number(self.row[field]), field)
        self.assertEqual((SPELL_EFFECT_DUMMY, 0, 0), tuple(number(self.row["Effect_%d" % s]) for s in (1, 2, 3)))
        self.assertEqual((TARGET_UNIT_CASTER, 0), (number(self.row["ImplicitTargetA_1"]), number(self.row["ImplicitTargetB_1"])))
        for field in ("EffectAura_1", "EffectBasePoints_1", "EffectDieSides_1", "ManaCost", "ManaCostPct", "RecoveryTime",
                      "CategoryRecoveryTime", "StartRecoveryTime", "Category", "Mechanic", "Reagent_1"):
            self.assertEqual(0, number(self.row[field]), field)

    def test_the_server_reads_the_id_from_the_shells(self):
        header = HEADER.read_text(encoding="utf-8")
        self.assertIn("inline constexpr uint32_t BountyTravel = 83601;", header)
        ids = header[header.index("inline constexpr uint32_t ShellIds[] = {"):]
        self.assertIn("83601,", ids[:ids.index("};")])


if __name__ == "__main__":
    unittest.main()
