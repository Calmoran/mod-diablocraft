"""Fetish Army and its five runes (src/classes/witch_doctor/dc_witch_doctor_fetish_army*.{h,cpp}, on the pets' piece
dc_witch_doctor_pets.cpp and the shared minions piece combat/dc_minions*): Fetish Ambush, Legion of Daggers, Tiki Torchers, Devoted
Following, Head Hunters.

What this proves, and how:

  * **The rules that need no core type.** tests/witch_doctor_fetish_army/harness.cpp compiles the real
    dc_witch_doctor_fetish_army_math.h with the tunables' numbers: whether a dagger of Fetish Ambush appears on an enemy and on which. The
    cone of the casters and the hunters is the pets' (test_witch_doctor_pets.py). Planted mutations must each turn it red.
  * **The numbers.** Every rune's tooltip number is a row of witch_doctor_skill_values.csv; the numbers only the power files give are
    tunables with their SF cited, equal to the decoded Power/Witchdoctor_FetishArmy*.pow (skipped where the game archives are not on this
    machine). Nothing is the designer's: no placeholder; the casters' and hunters' pauses and cones are the Shaman's and the Hunter's own files.
  * **It is wired.** The cast raises the daggers through the pets' piece and the runes add to them; the casters and hunters are kinds of
    their own; the pets' groups are one list; the minions piece lets a kind make its first swing at once.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_fetish_army.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SRC = MODULE / "src"
FOLDER = SRC / "classes/witch_doctor"
HEADER = "src/classes/witch_doctor/dc_witch_doctor_fetish_army_math.h"
HARNESS = MODULE / "tests/witch_doctor_fetish_army/harness.cpp"
SKILL = "Fetish Army"
RUNES = ("Fetish Ambush", "Legion of Daggers", "Tiki Torchers", "Devoted Following", "Head Hunters")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(token, rune="", qualifier=""):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/witchdoctor.csv")}


def tune(name):
    return float(tunables()[name]["d3_value"])


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def code(path):
    return squeeze((SRC / path).read_text(encoding="utf-8"))


def scratch_tree(mutate=None):
    key = HEADER[len("src/"):]
    files = {key: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary), str(tune("fetish_ambush_chance_pct"))], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 9, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a roll over the chance appears", ("return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll > chancePct;")),
            ("a roll at the chance appears", ("return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll <= chancePct;")),
            ("no chance still appears", ("return chancePct > 0 && roll < chancePct;", "return roll < chancePct;")),
            ("a chance never appears", ("return chancePct > 0 && roll < chancePct;", "return false;")),
            ("the pick can pass the last enemy", ("std::min(count - 1, static_cast<std::size_t>(std::max(0.0, unit) * static_cast<double>(count)))",
                                                  "static_cast<std::size_t>(std::max(0.0, unit) * static_cast<double>(count))")),
            ("the pick is always the first", ("static_cast<std::size_t>(std::max(0.0, unit) * static_cast<double>(count))", "std::size_t{0}")),
            ("the pick is always the last", ("static_cast<std::size_t>(std::max(0.0, unit) * static_cast<double>(count))", "count")),
            ("the shares are uneven", ("std::max(0.0, unit) * static_cast<double>(count)", "std::max(0.0, unit) * static_cast<double>(count) * 0.5")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_runes_are_the_five_the_sheet_names(self):
        sheet = [r["rune_name"] for r in read(D3 / "witch_doctor_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(sorted(sheet), sorted(RUNES))
        text = (FOLDER / "dc_witch_doctor_fetish_army.cpp").read_text(encoding="utf-8")
        for name in ("Fetish Ambush", "Legion of Daggers", "Tiki Torchers", "Head Hunters"):
            self.assertIn(f'"{name}"', text)

    def test_the_tooltip_numbers(self):
        self.assertEqual([value("cooldown_seconds"), value("pet_count"), value("duration_seconds"), value("damage_pct")], [120, 5, 20, 180])
        self.assertEqual(value("damage_pct", "Fetish Ambush"), 680)
        self.assertEqual(value("pet_count", "Legion of Daggers"), 3)
        self.assertEqual([value("pet_count", "Tiki Torchers"), value("damage_pct", "Tiki Torchers")], [2, 85])
        self.assertEqual(value("cooldown_seconds", "Devoted Following"), 90)
        self.assertEqual([value("pet_count", "Head Hunters"), value("damage_pct", "Head Hunters")], [2, 130])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, cite in (("fetish_ambush_chance_pct", "100", "Witchdoctor_FetishArmy.pow SF_8"),
                               ("fetish_ambush_radius_yards", "5", "Witchdoctor_FetishArmy.pow SF_7"),
                               ("fetish_caster_swing_seconds", "20", "Witchdoctor_FetishArmy_Shaman.pow CooldownTime"),
                               ("fetish_caster_range_yards", "20", "Witchdoctor_FetishArmy_Shaman.pow SF_2"),
                               ("fetish_caster_cone_degrees", "45", "Witchdoctor_FetishArmy_Shaman.pow SF_3"),
                               ("fetish_hunter_swing_seconds", "1", "Witchdoctor_FetishArmy_Hunter.pow CooldownTime"),
                               ("fetish_hunter_range_yards", "20", "Witchdoctor_FetishArmy_Hunter.pow SF_2"),
                               ("fetish_hunter_cone_degrees", "45", "Witchdoctor_FetishArmy_Hunter.pow SF_3")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(cite, rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists(self):
        text = (FOLDER / "dc_witch_doctor_fetish_army.cpp").read_text(encoding="utf-8")
        for name in re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text):
            self.assertIn(name, tunables(), name)
        tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        for token in re.findall(r'(?:Num|Own)\(\s*(?:id|spellId|base|BaseId\(Skill\)),\s*"([a-z_]+)"', text):
            self.assertIn(token, tokens, token)

    def test_the_numbers_are_the_power_files(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")

        def sf(name):
            return decode_pow.parse_power(decode_pow.extract(f"Power/Witchdoctor_{name}.pow"))["sf"]

        army = sf("FetishArmy")
        number = lambda table, n: float(str(table[n]).strip())  # noqa: E731
        self.assertAlmostEqual(number(army, 0), value("pet_count"))
        self.assertAlmostEqual(number(army, 1), tune("fetish_ring_max_yards"))
        self.assertAlmostEqual(number(army, 2), tune("fetish_spawn_interval_seconds"))
        self.assertAlmostEqual(number(army, 3), value("duration_seconds"))
        self.assertAlmostEqual(number(army, 4), tune("fetish_ring_min_yards"))
        self.assertAlmostEqual(number(army, 5) * 100, value("damage_pct", "Fetish Ambush"))
        self.assertAlmostEqual(number(army, 7), tune("fetish_ambush_radius_yards"))
        self.assertAlmostEqual(number(army, 8) * 100, tune("fetish_ambush_chance_pct"))
        self.assertAlmostEqual(number(army, 10), value("pet_count", "Tiki Torchers"))
        self.assertAlmostEqual(number(army, 11) * 100, value("damage_pct", "Tiki Torchers"))
        self.assertAlmostEqual(number(army, 13), value("pet_count", "Head Hunters"))
        self.assertAlmostEqual(number(army, 14) * 100, value("damage_pct", "Head Hunters"))
        self.assertAlmostEqual(number(army, 17) - 30, value("cooldown_seconds", "Devoted Following"))
        self.assertAlmostEqual(number(army, 19) * 100, value("damage_pct"))
        self.assertIn("3", str(army[9]))
        shaman, hunter = sf("FetishArmy_Shaman"), sf("FetishArmy_Hunter")
        self.assertAlmostEqual(number(shaman, 2), tune("fetish_caster_range_yards"))
        self.assertAlmostEqual(number(shaman, 3), tune("fetish_caster_cone_degrees"))
        self.assertAlmostEqual(number(hunter, 2), tune("fetish_hunter_range_yards"))
        self.assertAlmostEqual(number(hunter, 3), tune("fetish_hunter_cone_degrees"))


class Wiring(unittest.TestCase):
    def test_the_cast_raises_what_the_rune_says(self):
        text = code("classes/witch_doctor/dc_witch_doctor_fetish_army.cpp")
        self.assertIn('if (rune == "Legion of Daggers") Pets::RaiseFetishes(player, unsigned(Own(spellId, "pet_count")));', text)
        self.assertIn('else if (rune == "Fetish Ambush") Pets::RaiseFetishes(player, 0, Ambush());', text)
        self.assertIn('Pets::RaiseOnRing(player, "fetish_caster", unsigned(Own(spellId, "pet_count")), daggers);', text)
        self.assertIn('Pets::RaiseOnRing(player, "fetish_hunter", unsigned(Own(spellId, "pet_count")), daggers);', text)
        dispatch = code("classes/witch_doctor/dc_witch_doctor.cpp")
        self.assertEqual(dispatch.count("FetishArmy::Cast(player, spellId, targets);"), 1)
        self.assertEqual(dispatch.count("FetishArmy::RegisterScripts();"), 1)

    def test_a_caster_and_a_hunter_are_kinds_of_their_own(self):
        text = code("classes/witch_doctor/dc_witch_doctor_fetish_army.cpp")
        self.assertIn("kind.firstSwingAtOnce = true;", text)
        self.assertIn('kind.swingMs = Pets::Millis(swingSeconds); kind.rangeYards = range;', text)
        self.assertIn("kind.cap = unsigned(Own(id, \"pet_count\"));", text)
        self.assertIn('Ranged("fetish_caster", RuneId("Tiki Torchers"), Tune("fetish_caster_swing_seconds"),', text)
        self.assertIn('Ranged("fetish_hunter", RuneId("Head Hunters"), Tune("fetish_hunter_swing_seconds"),', text)
        self.assertIn("Pets::InCleave(fetish->GetAngle(other), centre, fetish->GetExactDist(other), yards, degrees)", text)

    def test_fetish_ambush_lands_on_an_enemy_and_strikes_round_it(self):
        text = code("classes/witch_doctor/dc_witch_doctor_fetish_army.cpp")
        self.assertIn('if (!Apparates(frand(0.0f, 100.0f), Tune("fetish_ambush_chance_pct"))) return ring;', text)
        self.assertIn('Combat::Enemies(player, id, player->GetPosition(), Tune("fetish_ring_max_yards"))', text)
        self.assertIn('Combat::Strike(player, enemy, id, Num(id, "damage_pct"));', text)

    def test_the_pets_pieces_share_one_list_of_groups(self):
        math = code("classes/witch_doctor/dc_witch_doctor_pets_math.h")
        self.assertIn('{"dog", "gargantuan", "fetish", "fetish_caster", "fetish_hunter", "sycophant"}', math)
        for name in ("dc_witch_doctor_pet_passives.cpp", "dc_witch_doctor_big_bad_voodoo.cpp"):
            self.assertIn("Pets::PetGroups", code("classes/witch_doctor/" + name))

    def test_the_ring_takes_a_start_and_the_minions_piece_a_first_swing(self):
        pets = code("classes/witch_doctor/dc_witch_doctor_pets.cpp")
        self.assertIn("Position at(x, y, z, centre.GetOrientation()); if (arrival.where) at = arrival.where(owner, at);", pets)
        self.assertIn("if (arrival.landed) arrival.landed(owner, at);", pets)
        self.assertIn("return Ring(owner, key, count, firstIndex, 0, {});", pets)
        self.assertIn("bool firstSwingAtOnce = false;", code("combat/dc_minions.h"))
        self.assertIn("if (kind.firstSwingAtOnce) clock = 1e9;", code("combat/dc_minions.cpp"))


if __name__ == "__main__":
    unittest.main()
