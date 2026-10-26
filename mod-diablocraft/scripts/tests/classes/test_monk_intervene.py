"""diablocraft-kgg1s: Inner Sanctuary - Intervene is a ground-target record, so the Monk dashes to the circle.

Intervene (rune A) "dashes to the target location, then creates Inner Sanctuary". All six Inner Sanctuary records were
SELF-cast, so the shield and the circle happened where the Monk stood. The rune now has a skill_targeting.csv row of its
own ("Inner Sanctuary - Intervene", a ground point), which generate_spells.py reads for that rune only. The cast then
runs the way Leap's does: the record's jump effect takes the Monk to the point, and the module resolves the cast when
the Monk lands (dc_combat.cpp, the landing handler), so the shield and the circle form where it lands.

What this proves, from the published spell rows (the server's spell_dbc render, which is also the client's Spell.dbc)
and the sheets, not from the generator:

  * Intervene's record takes the ground point: its first effect is a jump to a destination aimed at the ground cursor,
    the record asks the client for a destination, the cursor is the circle's 11 yd, the reach is the sheet's 25 yd,
    and its shell row says a ground point.
  * The other five Inner Sanctuary records (the skill and four runes) stay self-cast, with no destination.
  * The reach is sourced: the row says the mapped WoW spell's range and Intervene's stock range is 25 yd.
  * The generator reads a rune's own row and nothing else changes: every other class rune still takes its skill's row.
  * The checks can fail: each is run on a copy of the record with one field put back.

What it does not prove: the dash on a running server (docs/test-diablocraft-kgg1s.md).

    python mod-diablocraft/scripts/tests/classes/test_monk_intervene.py
"""
import csv
import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))
from test_ground_target_circles import records, GEN, MODULE, read, DEST_DEST  # noqa: E402
from test_spell_records import load_radii  # noqa: E402

SKILL = "Inner Sanctuary"
RUNE = "Intervene"
JUMP_DEST = 42
TARGET_UNIT_CASTER = 1
TARGET_FLAG_DEST_LOCATION = 0x40
SHELL = "Inner Sanctuary - Intervene"


def targeting():
    return {r["skill"]: r for r in read(MODULE / "data/d3/skill_targeting.csv")}


def shells():
    return {r["name"]: r for r in read(GEN / "spell_shells.csv")}


def takes_the_ground_point(row, radii):
    """Whether a record is a dash to the aimed ground point with the circle's cursor."""
    yards = radii.get(int(row["EffectRadiusIndex_1"]), 0.0)
    return (int(row["Effect_1"]) == JUMP_DEST
            and DEST_DEST in (int(row["ImplicitTargetA_1"]), int(row["ImplicitTargetB_1"]))
            and int(row["Targets"]) & TARGET_FLAG_DEST_LOCATION != 0
            and abs(yards - 11.0) < 0.001)


def self_cast(row):
    return int(row["ImplicitTargetA_1"]) == TARGET_UNIT_CASTER and not int(row["Targets"]) & TARGET_FLAG_DEST_LOCATION


class Intervene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = records()
        cls.radii = load_radii()
        cls.shell = shells()
        cls.id = int(cls.shell[SHELL]["spell_id"])

    def test_the_record_dashes_to_the_ground_point(self):
        row = self.rows[self.id]
        self.assertTrue(takes_the_ground_point(row, self.radii))
        # and the check can fail: put back one field at a time
        for field, was in (("Effect_1", "0"), ("ImplicitTargetA_1", str(TARGET_UNIT_CASTER)),
                           ("Targets", "0"), ("EffectRadiusIndex_1", "0")):
            copy = dict(row)
            copy[field] = was
            self.assertFalse(takes_the_ground_point(copy, self.radii), field)

    def test_the_cursor_is_the_circle_and_the_reach_is_the_sheets(self):
        row = targeting()[SHELL]
        self.assertEqual((row["target_type"], row["range_yards"], row["radius_yards"]), ("ground_point_aoe", "25", "11"))
        base = targeting()[SKILL]
        self.assertEqual(base["radius_yards"], row["radius_yards"])  # one circle, whichever way it is aimed
        # the server's shell table says the same, with the reach as a number
        sql = (GEN / "spell_shells.sql").read_text(encoding="utf-8")
        self.assertIn("INSERT INTO dc_spell_targeting VALUES (%d,'ground_point_aoe','NUMERIC',25.0,11.0,0.0);" % self.id, sql)

    def test_the_reach_is_the_mapped_wow_spells(self):
        row = targeting()[SHELL]
        self.assertEqual(row["unsure"], "range")
        visuals = [r for r in read(MODULE / "data/d3/monk_visuals.csv") if (r["d3_skill"], r["d3_rune"]) == (SKILL, RUNE)]
        self.assertEqual([r["wow_spell_id"] for r in visuals], [row["source_spell_id"]])
        self.assertIn("Intervene 3411", row["source"])
        self.assertIn("25 yd", row["source"])

    def test_the_other_five_records_stay_self_cast(self):
        names = [n for n in self.shell if n == SKILL or n.startswith(SKILL + " - ")]
        self.assertEqual(len(names), 6)
        for name in names:
            row = self.rows[int(self.shell[name]["spell_id"])]
            if name == SHELL:
                self.assertFalse(self_cast(row), name)
            else:
                self.assertTrue(self_cast(row), name)
                self.assertFalse(takes_the_ground_point(row, self.radii), name)
        # and the check can fail
        copy = dict(self.rows[self.id])
        copy["ImplicitTargetA_1"] = str(TARGET_UNIT_CASTER)
        copy["Targets"] = "0"
        self.assertTrue(self_cast(copy))

    def test_the_generator_takes_a_runes_own_row_and_nothing_else_changes(self):
        text = (SCRIPTS / "generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"targeting\.get\(f\"\{parent\['skill_name'\]\} - \{rune\['rune_name'\]\}\"\)", text)), 1)
        # only this rune has a row of its own among the non-Barbarian classes' skills and runes
        classes = ["monk", "wizard"]
        named = {r["skill"] for r in read(MODULE / "data/d3/skill_targeting.csv")}
        own = set()
        for stem in classes:
            for rune in read(MODULE / f"data/d3/{stem}_runes.csv"):
                key = f"{rune['skill_name']} - {rune['rune_name']}"
                if key in named:
                    own.add(key)
        self.assertEqual(own, {SHELL})

    def test_the_cast_resolves_at_the_landing(self):
        # ground_point_aoe is the type dc_combat.cpp waits on the movespline for, and the circle forms at the Monk's position
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        self.assertIn('if (shell.targeting.type == "ground_point_aoe")', combat)
        self.assertIn("abilityLandings[player->GetGUID().GetRawValue()]", combat)
        sanctuary = (MODULE / "src/classes/monk/dc_monk_inner_sanctuary.cpp").read_text(encoding="utf-8")
        cast = sanctuary[sanctuary.index("void Cast(Player* player, std::uint32_t spellId)"):]
        self.assertIn("zone.x = player->GetPositionX();", cast)


if __name__ == "__main__":
    unittest.main()
