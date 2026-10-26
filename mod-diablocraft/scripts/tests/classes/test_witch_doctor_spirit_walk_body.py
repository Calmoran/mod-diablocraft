"""The body Spirit Walk leaves behind (src/classes/witch_doctor/dc_witch_doctor_spirit_walk.cpp, combat/dc_minions.*).

What this proves, and how:

  * **The body stays put and strikes nobody.** The shared minions piece has a `staysPut` flag on a kind: its rule (`Follows`, in
    dc_minions_math.h) is compiled by tests/minions/harness.cpp with mutants in test_minions.py (a stay-put kind following, every
    kind staying put); the AI (dc_minions.cpp) asks it when the minion is configured (no follow) and every update (it stops any
    attack and returns before it aims), so a kind that does not set it behaves as before.
  * **The kind is the body.** One minion at a time (a second walk takes the first one's place), a copy of the Witch Doctor drawn by
    the owner's Clone Me! (the Wizard's image shape: the donor is the stock Mirror Image), with `spirit_walk_body_life_pct`
    (the power file's 'Dummy Health', 0.50) of the Witch Doctor's Life, living for the walk's seconds, with no blow of its own.
  * **It is raised where the walk began.** Spirit Walk's cast raises it at the Witch Doctor's position, before the walk starts, with
    the walk's seconds, and the kind is registered through the class's RegisterScripts.
  * **The creature and the number are rows.** witch_doctor_body_summons.csv names the creature (entry 900175), the generator's
    output is its migration (minions_0005), the pets' migration is as it was, and the Life is one tunable row equal to the power file.

What it does not prove: anything on a running server, how the body looks once the core's Clone Me! has run, or that monsters
attack it (they are free to; nothing taunts them to).

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_spirit_walk_body.py
"""

import csv
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_spirit_walk.cpp"
DISPATCH = MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp"
MINIONS = MODULE / "src/combat/dc_minions.cpp"
MATH = MODULE / "src/combat/dc_minions_math.h"
HEADER = MODULE / "src/combat/dc_minions.h"
COMBAT = MODULE / "src/combat/dc_combat.cpp"
TUNABLE = "spirit_walk_body_life_pct"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


class Flag(unittest.TestCase):
    def test_the_kind_has_the_flag_and_the_rule_is_one_line(self):
        self.assertIn("bool staysPut = false;", HEADER.read_text(encoding="utf-8"))
        self.assertIn("inline bool Follows(bool staysPut) { return !staysPut; }", flat(MATH))

    def test_the_ai_follows_only_when_the_kind_does_and_a_decoy_strikes_nobody(self):
        text = flat(MINIONS)
        self.assertIn("if (Follows(kind.staysPut)) me->GetMotionMaster()->MoveFollow(player, PET_FOLLOW_DIST, PET_FOLLOW_ANGLE); }", text)
        self.assertIn("Pulse(player, diff); if (!Follows(kind.staysPut)) { // a decoy stands where it was raised: it follows no one and strikes no one "
                      "if (me->GetVictim()) me->AttackStop(); return; }", text)

    def test_no_other_kind_sets_it(self):
        users = [p.name for p in (MODULE / "src").rglob("*.cpp") if "staysPut" in p.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual(sorted(users), ["dc_minions.cpp", "dc_shaman_earth_elemental.cpp", "dc_witch_doctor_spirit_walk.cpp"])


class Kind(unittest.TestCase):
    def test_the_body_is_one_copy_of_the_witch_doctor_that_stays_put(self):
        text = flat(CODE)
        for needle in ('kind.group = "spirit_walk_body";', "kind.entry = BodyEntry;", "kind.cap = 1;", "kind.staysPut = true;",
                       'kind.lifeToCopyPct = Tune("spirit_walk_body_life_pct");',
                       "kind.lifeMs = std::uint32_t(walkCast.seconds * 1000.0 + 0.5);"):
            self.assertIn(needle, text)
        self.assertNotIn("damagePct", text)
        self.assertIn("constexpr std::uint32_t BodyEntry = 900175;", text)

    def test_it_is_raised_where_the_walk_began_with_the_walks_seconds_and_registered(self):
        text = flat(CODE)
        self.assertIn('walkCast.seconds = seconds; Minions::Raise(player, "spirit_walk_body", player->GetPosition(), 0, true); walkCast = {};', text)
        self.assertLess(text.index('Minions::Raise(player, "spirit_walk_body"'), text.index("ControlImmunity::Set(player, spellId, true);"))
        self.assertIn('Minions::Define("spirit_walk_body", Body);', text)
        self.assertIn("SpiritWalk::Register();", flat(DISPATCH))
        self.assertIn("DemonHunter::RegisterScripts();\n        WitchDoctor::RegisterScripts();", COMBAT.read_text(encoding="utf-8"))


class Rows(unittest.TestCase):
    def test_the_creature_is_one_row_and_one_migration(self):
        rows = read(D3 / "witch_doctor_body_summons.csv")
        self.assertEqual([(r["summon"], r["skill"], r["entry"], r["donor_creature"], r["script"]) for r in rows],
                         [("Spirit Walk Body", "Spirit Walk", "900175", "31216", "dc_minion")])
        sys.path.insert(0, str(MODULE / "scripts/generate/classes"))
        import generate_witch_doctor_summons as gen
        sql = (MODULE / "data/sql/db-world/updates/minions_0005_witch_doctor_body_summons.sql").read_text(encoding="utf-8")
        self.assertEqual(sql, gen.render(MODULE, gen.BODY_SHEET))
        self.assertIn("SET entry=900175,", sql)
        self.assertIn("lootid=0,pickpocketloot=0,skinloot=0", sql)
        pets = (MODULE / "data/sql/db-world/updates/minions_0003_witch_doctor_summons.sql").read_text(encoding="utf-8")
        self.assertNotIn("900175", pets)

    def test_the_life_is_one_tunable_row_equal_to_the_power_file(self):
        rows = [r for r in read(MODULE / "data/tunables/witchdoctor.csv") if r["name"] == TUNABLE]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["d3_value"], rows[0]["value"], rows[0]["unit"]), ("50", "", "percent"))
        migration = (MODULE / "data/generated" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        self.assertIn(f"('witchdoctor', '{TUNABLE}', 50.0,", migration)
        out = subprocess.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", "Witchdoctor_SpiritWalk"], capture_output=True, text=True)
        if out.returncode:
            raise unittest.SkipTest("no D3 power files on this machine")
        found = re.search(r"SF_\d+ 'Dummy Health\s*' = ([\d.]+)", out.stdout)
        self.assertEqual(float(found.group(1)) * 100, 50.0)


if __name__ == "__main__":
    unittest.main()
