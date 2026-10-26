"""Legendary rest, bead diablocraft-c9mth: Scarbringer (Monk fist weapon), on the piece Bracers of Destruction built, N-NHIT.

  "The damage of Lashing Tail Kick is increased by [450 - 600]% to the first 7 enemies hit."
  * the numbers (the roll range 450-600, the count 7) are read from d3planner (item_onehand.js, leg_scarbringer_p6) and the catalogue, the skill
    from monk_skills.csv; the table (data/legendary_powers.csv) holds ONE `skill` row for the pool item P61_Unique_Fist_013_x1: Lashing Tail Kick,
    `damage_increase_pct`, 450-600, condition `first_hits` 7, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    refuses what `first_hits` cannot carry;
  * the production rules (src/combat/dc_item_power_math.h: Holds' `first_hits` and NearestPlace, with SkillFactor / Owned / RollPowers) are compiled
    and driven with the generated row (the Bracers harness, which names no skill): a hit at place 1 to 7 of its cast takes 1 + N/100, the 8th and on
    and a hit no cast counted take nothing; only Lashing Tail Kick, only while worn and rolled; a Primal stores 600; the places over a cone's enemies
    and the kick's own (the rest of its half circle) together go nearest first, the cone's and the others' interleaved;
  * mutants of the rows and the rules fail the same driver;
  * source-text guards that Lashing Tail Kick resolves through ResolveCast's target loop (a cone, no projectile Speed), that the places and the enemy
    count are counted over the core's targets and the enemies the kick strikes beside them (Monk::Beside, read before the hits and again by Kick::Cast,
    which sets the place around each strike and puts it back), and that Beside holds exactly what the kick struck before this bead; the C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-c9mth.md.
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
from test_item_power_bracers_of_destruction import (  # noqa: E402
    GENERATED, HARNESS, MATH, MODULE, REPO, SCRATCH, SRC, T, all_rows, g, read_csv)

OWNER = "P61_Unique_Fist_013_x1"
SKILL = "Lashing Tail Kick"
STAT = "damage_increase_pct"
KICK = SRC / "classes/monk/dc_monk_lashing_tail_kick.cpp"
RESOLVE = SRC / "combat/dc_combat_resolve.cpp"


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high, count) as the planner words them, checked against the catalogue."""
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "The damage of Lashing Tail Kick is increased by %d%% to the first (\d+) enemies hit\.", min: (\d+), max: (\d+)', item)
    assert m, item
    catalogue = (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8")
    assert "The damage of Lashing Tail Kick is increased by [%s-%s]%% to the first %s enemies hit." % (m[2], m[3], m[1]) in catalogue
    return float(m[2]), float(m[3]), int(m[1])


class Table(unittest.TestCase):
    def test_the_sources_name_lashing_tail_kick_the_range_and_the_count(self):
        self.assertEqual((450.0, 600.0, 7), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv("data/d3/monk_skills.csv")])

    def test_one_damage_row_names_lashing_tail_kick_and_its_count(self):
        low, high, count = numbers()
        self.assertEqual([(OWNER, 0, "skill", SKILL, STAT, low, high, "first_hits", float(count), "", 0.0, 0, "", "", 100.0, 0.0)], mine())

    def test_the_tooltip_shows_the_rolled_range(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("450–600%", m[1])
        self.assertIn("first 7 enemies", m[1])

    def test_the_new_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0064_table.sql")   # the newest full table: a later bead renumbers it
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        # (not the CREATE TABLE line: the columns were widened in place, fire_skills to VARCHAR(1024))
        old = [line for line in (MODULE / "data/sql/db-world/updates/legendary_powers_0063_table.sql").read_text(encoding="utf-8").splitlines() if not line.startswith("CREATE TABLE")]
        new = GENERATED.read_text(encoding="utf-8").splitlines()
        # the one render also carries the rows other beads of the same batch add, so this row is among the new lines, not the only one
        self.assertIn("('%s',0,'skill','%s','%s',450,600,'first_hits',7,'',0,0,'','',100,0)," % (OWNER, SKILL, STAT),
                      [line for line in new if line not in old])
        # every row the applied render held is still there; the table's own CREATE line may change when a column is widened
        self.assertEqual([], [line for line in old if line not in new and not line.startswith("CREATE TABLE")])


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="itemscarbringer-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high, count = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        out += clear + [(T("place", SKILL, 1), "1")]                                           # not worn
        out += clear + [(T("wears", OWNER), None), (T("place", SKILL, 1), "1")]               # worn, nothing rolled
        for roll in (low, 500, high):                                                         # worn and rolled
            out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, roll), None)]
            for place in range(0, count + 6):
                out += [(T("place", SKILL, place), g(1 + roll / 100) if 1 <= place <= count else "1")]
            out += [(T("place", SKILL, 100), "1")]
        out += clear + [(T("value", OWNER, SKILL, STAT, 500), None), (T("place", SKILL, 1), "1")]   # rolled, in the bag
        out += clear + [(T("wears", OWNER), None), (T("value", OWNER, SKILL, STAT, high), None)]
        for other in ("Seismic Slam", "Fists of Thunder", "Deadly Reach", "Cyclone Strike", "Dashing Strike", "Lashing Tail", "Lashing Tail Kick Rune", ""):
            out += [(T("place", other, 1), "1")]
        # the places over a cone's enemies and the kick's own together: the list is the core's then the others', and the nearest of both goes first
        union = [4.0, 9.0, 2.0, 7.0, 7.0] + [1.0, 8.0, 3.0, 7.0]
        for index in range(len(union)):
            out += [(T("nearest", ";".join(str(d) for d in union), index), str(1 + sum(1 for i, d in enumerate(union) if d < union[index] or (d == union[index] and i < index))))]
        out += [(T("nearest", ";".join(str(d) for d in union), len(union)), "0")]
        out += [(T("roll", OWNER, 1), "power:%s:%s=%g;" % (SKILL, STAT, high)),
                (T("roll", OWNER, 0), "power:%s:%s=%g;" % (SKILL, STAT, (low + high) / 2))]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_skill_lost": [r[:3] + ("Seismic Slam",) + r[4:] for r in rows],
            "the_range_of_the_old_item": [r[:5] + (300.0, 300.0) + r[7:] for r in rows],
            "the_count_of_the_old_item": [r[:8] + (5.0,) + r[9:] for r in rows],
            "bracers_count": [r[:8] + (10.0,) + r[9:] for r in rows],
            "no_condition": [r[:7] + ("", 0.0) + r[9:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rules = {
            "the_last_place_dropped": ("situation.hitPlace <= row.arg", "situation.hitPlace < row.arg"),
            "an_uncounted_hit_takes_it": ("situation.hitPlace >= 1 && situation.hitPlace <= row.arg", "situation.hitPlace <= row.arg"),
            "every_hit_takes_it": ("return situation.hitPlace >= 1 && situation.hitPlace <= row.arg;", "return true;"),
            "farthest_first": ("distances[other] < distances[index] ||", "distances[other] > distances[index] ||"),
            "ties_by_reverse_order": ("&& other < index))", "&& other > index))"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                want, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


class Hooks(unittest.TestCase):
    """What the .cpp files must call and in what order; read, not compiled."""

    def cast_body(self):
        text = KICK.read_text(encoding="utf-8")
        body = text[text.index("    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)"):]
        return body[:body.index("\n    }\n")]

    def beside_body(self):
        text = KICK.read_text(encoding="utf-8")
        body = text[text.index("    std::vector<Unit*> Beside(Player* player"):]
        return body[:body.index("\n    }\n")]

    def test_lashing_tail_kick_resolves_through_the_target_loop(self):
        targeting = next(r for r in read_csv("data/d3/skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual(("cone_enemies", "instant"), (targeting["target_type"], targeting["cast_type"]))
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql, re.S)[1].split(",")]
        speed = columns.index("Speed")
        shells = [s for s in read_csv("data/generated/spell_shells.csv") if s["name"].split(" - ")[0] == SKILL and s["kind"] in ("active", "rune")]
        self.assertEqual(6, len(shells))
        for shell in shells:
            record = re.search(r"\((%s,[^)]*)\)" % shell["spell_id"], sql)[1].split(",")
            self.assertEqual("0", record[speed], shell["name"])

    def test_the_loop_counts_the_cone_and_the_beside_enemies_together(self):
        text = RESOLVE.read_text(encoding="utf-8")
        body = text[text.index("void ResolveCast(Player* player, Shell const& shell"):]
        body = body[:body.index("\n        }\n")]
        self.assertRegex(body, r"for \(Unit\* target : targets\)\s+distances\.push_back\(from\.GetExactDist\(target\)\);\s+"
                               r"for \(Unit\* target : Monk::Beside\(player, shell\.spellId, targets\)\)\s+distances\.push_back\(from\.GetExactDist\(target\)\);")
        self.assertIn("enemies = distances.size();", body)
        self.assertNotIn("enemies = targets.size();", body)
        self.assertLess(body.index("Monk::Beside("), body.index("place = ItemPower::NearestPlace(distances, index++);"))
        self.assertLess(body.index("place = outer;"), body.index("Monk::Cast(player, shell.spellId, targets, punch);"))

    def test_the_kick_strikes_the_beside_enemies_with_their_places_and_puts_them_back(self):
        body = self.cast_body()
        self.assertIn("auto const beside = Beside(player, spellId, targets);", body)
        self.assertRegex(body, r"for \(Unit\* enemy : targets\)\s+distances\.push_back\(player->GetExactDist\(enemy\)\);\s+"
                               r"for \(Unit\* enemy : beside\)\s+distances\.push_back\(player->GetExactDist\(enemy\)\);")
        self.assertRegex(body, r"unsigned& place = ItemPowers::HitPlace\(\);\s+unsigned& enemies = ItemPowers::CastEnemies\(\);\s+"
                               r"unsigned const outerPlace = place, outerEnemies = enemies;\s+enemies = distances\.size\(\);\s+std::size_t index = targets\.size\(\);")
        self.assertRegex(body, r"for \(Unit\* enemy : beside\)\s+\{\s+place = ItemPower::NearestPlace\(distances, index\+\+\);\s+"
                               r"if \(Combat::Strike\(player, enemy, spellId, pct\)\)\s+struck\.push_back\(enemy\);\s+\}\s+place = outerPlace;\s+enemies = outerEnemies;")
        self.assertEqual(1, body.count("Combat::Strike("), "no strike outside the counted loop")
        self.assertLess(body.index("enemies = outerEnemies;"), body.index("Combat::Connected("))

    def test_beside_holds_what_the_kick_struck_past_the_cone(self):
        body = self.beside_body()
        self.assertIn('IsRune(spellId, "Vulture Claw Kick") || IsRune(spellId, "Sweeping Armada")', body)
        self.assertIn("if (around || player->HasInArc(arc, enemy))", body)
        self.assertIn('IsRune(spellId, "Spinning Flame Kick") && DC::Tunables::Has("monk", "lashing_tail_kick_column_width_yards")', body)
        self.assertEqual(2, body.count("add(enemy);"))
        self.assertIn("std::find(targets.begin(), targets.end(), enemy) == targets.end() &&", body)
        self.assertIn("std::find(beside.begin(), beside.end(), enemy) == beside.end())", body)
        self.assertEqual(0, body.count("Combat::Strike("), "Beside only reads")
        monk = (SRC / "classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.assertIn("if (Kick::Is(spellId))\n            return Kick::Beside(player, spellId, targets);\n        return {};", monk)


if __name__ == "__main__":
    unittest.main()
