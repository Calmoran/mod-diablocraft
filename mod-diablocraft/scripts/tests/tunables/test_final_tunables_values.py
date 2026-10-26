"""diablocraft-final-tunables-values: the 27 approved values (ruling 2026-09-29,
Decision Queue q-0929-07) are in their sheets, reach the migrations, and no
PLACEHOLDER row is left among them. The expected numbers are typed here from
the brief on purpose: reading them back from the sheets would test nothing."""
import csv
import re
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
UPDATES = MODULE / "data/sql/db-world/updates"

ABILITY = {
    "sprint_gangway_knockback_yards": 10, "ignore_pain_bravado_knockback_yards": 10,
    "leap_toppling_knockback_yards": 20, "fury_charge_knockback_yards": 0,
    "overpower_storm_axes_radius_yards": 50, "devils_anvil_radius_yards": 10,
    "seismic_shattered_knockup_height_yards": 2, "storm_armor_shock_radius_yards": 50,
    "ice_armor_chilling_aura_radius_yards": 15, "mirror_image_taunt_radius_yards": 8,
    # overpower_crit_cdr_chance_pct and slaughter_eruption_chance_pct were retired by
    # diablocraft-proc-coefficients-wiring (the designer, q-0929-11): both roll the skill's own
    # proc coefficient now (scripts/tests/combat/test_proc_coefficients.py).
    "superstition_fury_proc_chance_pct": 20, "juggernaut_heal_proc_chance_pct": 30,
    "ability_knockback_speed_xy": 16, "ability_knockback_speed_z": 6,
    "ignore_pain_bravado_radius_yards": 5, "battle_rage_recent_crit_window_seconds": 1,
    "rage_flip_behind_yards": 5, "ancients_life_pct_of_owner": 100,
    "throwing_hammer_visual_id": 7250,
}
# (affix, parameter) -> (d3_value, tuned_value); the server reads tuned when set.
AFFIX = {
    ("Electrified", "bolt_speed"): (None, 15), ("Electrified", "bolt_radius"): (None, 1.5),
    ("Electrified", "bolt_length"): (None, 20), ("Frozen Pulse", "chase_speed"): (None, 5),
    ("Orbiter", "orbit_speed"): (None, 45), ("Orbiter", "max_radius"): (15, None),
    ("Orbiter", "max_radius_champion"): (30, None), ("Poison Enchanted", "trail_length"): (None, 15),
}


def read(path):
    with (MODULE / path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class FinalTunables(unittest.TestCase):
    def test_ability_rows_hold_the_approved_value_and_are_not_placeholders(self):
        rows = {r["name"]: r for r in read("data/tunables/ability_tunables.csv")}
        for name, expected in ABILITY.items():
            self.assertIn(name, rows)
            self.assertEqual(float(rows[name]["value"]), expected, name)
            self.assertNotEqual(rows[name]["status"], "PLACEHOLDER", name)
            self.assertNotIn("the designer sets", rows[name]["notes"], name)
        self.assertNotIn("ancients_life", rows, "the flat row is replaced by the percent row")

    def test_sourced_rows_cite_the_d3_data_and_designed_rows_say_so(self):
        rows = {r["name"]: r for r in read("data/tunables/ability_tunables.csv")}
        for name in ABILITY:
            note = rows[name]["notes"]
            if rows[name]["status"] == "SOURCED":
                self.assertRegex(note, r"\.pow|placeholder-values-d3-data", name)
            else:
                self.assertEqual(rows[name]["status"], "SET", name)
                self.assertIn("ruling 2026-09-29", note, name)

    def test_affix_rows(self):
        rows = {(r["affix_name"], r["parameter"]): r for r in read("data/tunables/elite_affix_parameters.csv")}
        for key, (d3, tuned) in AFFIX.items():
            self.assertIn(key, rows)
            got = rows[key]
            self.assertEqual(float(got["d3_value"]) if got["d3_value"] else None, d3, key)
            self.assertEqual(float(got["tuned_value"]) if got["tuned_value"] else None, tuned, key)
            self.assertNotIn("PLACEHOLDER", got["notes"], key)
        champion = rows[("Orbiter", "max_radius_champion")]["notes"]
        self.assertIn("15 + 15", champion, "the 30 is inferred and must be cited that way")

    def test_ability_migration_carries_every_row(self):
        text = (UPDATES / "combat_0037_final_tunable_values.sql").read_text(encoding="utf-8")
        for name, expected in ABILITY.items():
            self.assertRegex(text, r"\('%s',%s," % (name, re.escape(repr(float(expected)))), name)
        self.assertIn("DELETE FROM dc_ability_tuning WHERE name='ancients_life';", text)

    def test_affix_migration_carries_every_row(self):
        text = (UPDATES / "rifts_0015_affix_values.sql").read_text(encoding="utf-8")
        for (affix, parameter), (d3, tuned) in AFFIX.items():
            row = re.search(r"\('%s', '%s', ([^,]+), ([^,]+), " % (re.escape(affix), parameter), text)
            self.assertTrue(row, (affix, parameter))
            want = lambda v: "NULL" if v is None else repr(float(v))
            self.assertEqual((row.group(1), row.group(2)), (want(d3), want(tuned)), (affix, parameter))

    def test_hammer_visual_reaches_the_shell_migration_and_the_client_dbc(self):
        old = (UPDATES / "combat_0035_gathering_chill_sourced.sql").read_text(encoding="utf-8")
        new = (UPDATES / "combat_0038_throwing_hammer_visual.sql").read_text(encoding="utf-8")
        self.assertEqual(len(old), len(new) - 3)  # only "0" became "7250"
        self.assertIn(",7250,", new)
        # The visual went out in client patch 44; the counter only rises, so a later
        # patch (45, 46, ...) still carries it. An exact pin went stale at every bump.
        patch = re.search(r"(?m)^client_patch=(\d+)$", (REPO / "VERSION").read_text())
        self.assertTrue(patch, "VERSION has no client_patch line")
        self.assertGreaterEqual(int(patch.group(1)), 44, "the hammer visual shipped in client patch 44")

    def test_code_reads_the_new_rows(self):
        ancients = (MODULE / "src/classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")
        self.assertIn("ancients_life_pct_of_owner", ancients)
        self.assertIn("GetMaxHealth()", ancients)
        self.assertNotRegex(ancients, r"'ancients_life'")
        elites = (MODULE / "src/monsters/affixes/dc_affix_orbiter.cpp").read_text(encoding="utf-8")
        self.assertIn('state->rare ? "Orbiter|max_radius"', elites)
        self.assertIn('"Orbiter|max_radius_champion"', elites)
        # the same guard for both ranks: the chosen radius must exceed the central orb
        self.assertIn("n.Parameter(radiusKey) <= n.orbiterRadius", elites)


if __name__ == "__main__":
    unittest.main()
