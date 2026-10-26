"""diablocraft-ground-target-circles: the green ground cursor is the size of the skill's effect.

The client draws a ground-targeted skill's cursor as the radius of the effect
that takes the ground point (Spell.dbc EffectRadiusIndex on the slot whose
implicit target is TARGET_DEST_DEST). The designer's patch 43 check: Teleport's was
"absolutely massive" - its sheet `radius_yards` is the 50-yard REACH, and the
generator wrote it into the radius slot. This reads the published spell rows
(the server's spell_dbc and the client's Spell.dbc are one render) and checks,
against the sheets and not against the generator:

  * every ground skill, rune and Archon form has a cursor that is the sheet's
    area radius, its rune's own radius, or - with no area - the marker
    tunable;
  * no effect slot of a ground record is larger than that cursor, so a reach
    or another number can never be what the client draws;
  * the marker is a stock SpellRadius yardage, and the tunable row exists.

    python mod-diablocraft/scripts/tests/classes/test_ground_target_circles.py
"""
import csv
import re
import struct
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
MODULE = SCRIPTS.parent
REPO = MODULE.parent
sys.path.insert(0, str(SCRIPTS))
from test_spell_records import split_values, load_radii  # noqa: E402

GEN = MODULE / ("data/" + "gener" + "ated")
GROUND = ("ground_point_aoe", "ground_area", "line_to_point")
DEST_DEST = 87
CONE = 104
# Ruling q-0930-13 (diablocraft-as1z): Leap draws the small marker, not its 10 yd
# hit radius, unless a rune has an area of its own.
MARKER_CURSOR = ("Leap",)
PLAYER_KINDS = ("active", "rune", "archon")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def records():
    sql = (GEN / "spell_shells.sql").read_text(encoding="utf-8")
    header = re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES", sql)
    names = [n.strip(" `") for n in header[1].split(",")]
    rows = {}
    for line in sql.splitlines():
        line = line.strip().rstrip(",;")
        if line.startswith("(") and line.endswith(")"):
            values = split_values(line[1:-1])
            if len(values) == len(names):
                rows[int(values[0])] = dict(zip(names, values))
    return rows


class GroundTargetCircles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = records()
        cls.radii = load_radii()
        cls.targeting = {r["skill"]: r for r in read(MODULE / "data/d3/skill_targeting.csv")}
        # every class's values sheet: a rune's own radius is its cursor, whichever class it is
        cls.values = [row for path in sorted((MODULE / "data/d3").glob("*_skill_values.csv")) for row in read(path)]
        tunable = [r for r in read(MODULE / "data/tunables/combat.csv")
                   if r["name"] == "ground_marker_radius_yards"]
        assert len(tunable) == 1, "combat.csv needs one ground_marker_radius_yards row"
        cls.marker = float(tunable[0]["value"] or tunable[0]["d3_value"])
        cls.shells = [r for r in read(GEN / "spell_shells.csv") if r["kind"] in PLAYER_KINDS]

    def slots(self, spell):
        """[(slot, target A, target B, radius yards)] of one record."""
        row = self.rows[spell]
        return [(n, int(row["ImplicitTargetA_%d" % n]), int(row["ImplicitTargetB_%d" % n]),
                 self.radii.get(int(row["EffectRadiusIndex_%d" % n]), 0.0)) for n in (1, 2, 3)]

    def cursor(self, spell):
        """What the client draws: the radius of the non-cone effect that takes the point."""
        return max([yards for _n, a, b, yards in self.slots(spell)
                    if DEST_DEST in (a, b) and a != CONE] or [0.0])

    def geometry(self, shell):
        base = shell["name"].split(" - ")[0]
        key = "Archon form: " + base if shell["kind"] == "archon" else base
        # A rune with a targeting row of its own (a Shaman rune that is centred on the caster) answers for itself.
        return self.targeting.get(key) if shell["kind"] == "archon" else self.targeting.get(shell["name"]) or self.targeting.get(key)

    def ground_shells(self):
        return [s for s in self.shells
                if (self.geometry(s) or {}).get("target_type") in GROUND]

    def expected(self, shell):
        """The sheet's answer, without asking the generator."""
        geometry = self.geometry(shell)
        rune = shell["name"].partition(" - ")[2]
        own = [float(v["value"]) for v in self.values
               if v["token"] == "radius_yards" and v["qualifier"] != "wall" and rune and v["rune"] == rune
               and v["skill"] == shell["name"].split(" - ")[0]]
        if own:
            return max(own)
        if shell["name"].split(" - ")[0] in MARKER_CURSOR:
            return self.marker
        return float(geometry["radius_yards"]) if geometry["radius_yards"] else self.marker

    def test_there_are_ground_skills_to_check(self):
        names = {s["name"] for s in self.ground_shells()}
        for skill in ("Leap", "Furious Charge", "Avalanche", "Arcane Orb", "Arcane Torrent",
                      "Slow Time", "Teleport", "Energy Twister", "Meteor", "Blizzard", "Black Hole"):
            self.assertIn(skill, names)
        self.assertGreater(len(self.ground_shells()), 60)

    def test_every_ground_cursor_matches_its_sheet(self):
        wrong = []
        for shell in self.ground_shells():
            want, got = self.expected(shell), self.cursor(int(shell["spell_id"]))
            if abs(want - got) > 0.001:
                wrong.append("%s %s: cursor %g yd, sheet %g yd" % (shell["spell_id"], shell["name"], got, want))
        self.assertEqual(wrong, [])

    def test_no_slot_of_a_ground_record_outgrows_its_cursor(self):
        wrong = []
        for shell in self.ground_shells():
            spell = int(shell["spell_id"])
            cursor = self.cursor(spell)
            for n, _a, _b, yards in self.slots(spell):
                if yards > cursor + 0.001:
                    wrong.append("%s %s: slot %d is %g yd, cursor %g yd" % (spell, shell["name"], n, yards, cursor))
        self.assertEqual(wrong, [])

    def test_teleport_and_slow_time_reach_is_not_a_radius(self):
        # The patch 43 bug by name: 50 and 60 yards must be in no radius slot.
        for shell in self.shells:
            if shell["name"].split(" - ")[0] in ("Teleport", "Slow Time"):
                for n, _a, _b, yards in self.slots(int(shell["spell_id"])):
                    self.assertNotIn(yards, (50.0, 60.0), "%s slot %d" % (shell["name"], n))

    def test_leap_draws_the_marker_and_the_server_still_hits_its_sheet_radius(self):
        leap = next(s for s in self.shells if s["name"] == "Leap" and s["kind"] == "active")
        spell = int(leap["spell_id"])
        self.assertEqual(self.cursor(spell), self.marker)
        # No slot of the record carries the sheet's 10 yd: the module reads the
        # hit radius as an exact value, so the record cannot be what it hits with.
        self.assertNotIn(10.0, [yards for _n, _a, _b, yards in self.slots(spell)])
        sheet = float(self.targeting["Leap"]["radius_yards"])
        self.assertEqual(sheet, 10.0)
        mapped = [r for r in read(GEN / "spell_value_map.csv")
                  if r["spell_id"] == str(spell) and r["token"] == "radius_yards"]
        self.assertEqual([(r["source"], r["conversion"]) for r in mapped], [("exact", "")])

    def test_the_marker_is_small_and_a_stock_radius(self):
        self.assertIn(self.marker, self.radii.values())
        self.assertLessEqual(self.marker, 5.0)
        teleport = next(s for s in self.shells if s["name"] == "Teleport" and s["kind"] == "active")
        self.assertEqual(self.cursor(int(teleport["spell_id"])), self.marker)


if __name__ == "__main__":
    unittest.main()
