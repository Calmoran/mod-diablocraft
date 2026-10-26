"""Big Bad Voodoo and its five runes (src/classes/witch_doctor/dc_witch_doctor_big_bad_voodoo*.{h,cpp}): Slam Dance, Jungle Drums, Ghost
Trance, Rain Dance, Boogie Man.

What this proves, and how:

  * **The rules that need no core type.** tests/witch_doctor_big_bad_voodoo/harness.cpp compiles the real
    dc_witch_doctor_big_bad_voodoo_math.h with the sheets' and the tunables' numbers: how long an ally keeps the gifts after a look, what
    Ghost Trance heals each look and takes off a blow, whether an ally stands in the ritual, whether a corpse rises as a Zombie Dog.
    Planted mutations must each turn it red.
  * **The numbers.** Every rune's tooltip number is a row of witch_doctor_skill_values.csv; the numbers only the power file gives are
    tunables with their SF cited, equal to the decoded Power/Witchdoctor_BigBadVoodoo.pow (skipped where the game archives are not on this
    machine). Nothing is the designer's: no placeholder.
  * **It is wired.** The ground cast lays the ritual; each rune reads its own sheet; the dispatch hands the ground cast, the hit
    multipliers and the damage taken to the ritual; the pets' piece raises Boogie Man's dog only with room; the minions piece lets boosts and
    hastes of different sources stand together.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_big_bad_voodoo.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_big_bad_voodoo_math.h"
HARNESS = MODULE / "tests/witch_doctor_big_bad_voodoo/harness.cpp"
SKILL = "Big Bad Voodoo"
RUNES = ("Slam Dance", "Jungle Drums", "Ghost Trance", "Rain Dance", "Boogie Man")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(token, rune=""):
    rows = [r for r in read(D3 / "witch_doctor_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, "")]
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


def numbers():
    return [tune("big_bad_voodoo_tick_seconds"), tune("big_bad_voodoo_linger_seconds"), value("heal_pct", "Ghost Trance"),
            value("damage_reduction_pct", "Ghost Trance"), tune("big_bad_voodoo_radius_yards"), value("proc_chance_pct", "Boogie Man")]


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)] + [str(n) for n in numbers()], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 14, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the gifts end with the pause", ("(tickSeconds + std::max(0.0, lingerSeconds)) * 1000.0", "tickSeconds * 1000.0")),
            ("a negative linger shortens them", ("std::max(0.0, lingerSeconds)", "lingerSeconds")),
            ("the gifts are in seconds", ("(tickSeconds + std::max(0.0, lingerSeconds)) * 1000.0", "(tickSeconds + std::max(0.0, lingerSeconds))")),
            ("no pause still gives them", ("return tickSeconds > 0 ?", "return true ?")),
            ("the gifts hold at their end", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("the gifts never end", ("return nowMs < untilMs;", "return true;")),
            ("a look heals the whole percent", ("maxLife * pctPerSecond / 100.0 * tickSeconds : 0.0", "maxLife * pctPerSecond / 100.0 : 0.0")),
            ("a look heals a fraction of the Life", ("maxLife * pctPerSecond / 100.0 * tickSeconds : 0.0", "maxLife * pctPerSecond * tickSeconds : 0.0")),
            ("no pause still heals", ("&& pctPerSecond > 0 && tickSeconds > 0 ?", "&& pctPerSecond > 0 ?")),
            ("no percent still heals", ("maxLife > 0 && pctPerSecond > 0 &&", "maxLife > 0 &&")),
            ("a blow loses nothing", ("damage * (1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0)", "damage")),
            ("a blow loses the reduction as points", ("damage * (1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0)", "damage - reductionPct")),
            ("a reduction over all", ("std::clamp(reductionPct, 0.0, 100.0)", "std::clamp(reductionPct, 0.0, 1000.0)")),
            ("a negative reduction adds damage", ("std::clamp(reductionPct, 0.0, 100.0)", "std::clamp(reductionPct, -100.0, 100.0)")),
            ("the edge is out", ("return distance <= radius;", "return distance < radius;")),
            ("everything is inside", ("return distance <= radius;", "return true;")),
            ("a roll over the chance rises", ("return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll > chancePct;")),
            ("a roll at the chance rises", ("return chancePct > 0 && roll < chancePct;", "return chancePct > 0 && roll <= chancePct;")),
            ("no chance still rises", ("return chancePct > 0 && roll < chancePct;", "return roll < chancePct;")),
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
        text = (FOLDER / "dc_witch_doctor_big_bad_voodoo.cpp").read_text(encoding="utf-8")
        for name in RUNES:
            if name != "Jungle Drums":  # its seconds are the rune's own duration, read like the skill's
                self.assertIn(f'"{name}"', text)

    def test_the_tooltip_numbers(self):
        self.assertEqual([value("cooldown_seconds"), value("movement_speed_pct"), value("duration_seconds")], [120, 15, 20])
        self.assertEqual(value("damage_bonus_pct", "Slam Dance"), 15)
        self.assertEqual(value("duration_seconds", "Jungle Drums"), 30)
        self.assertEqual([value("heal_pct", "Ghost Trance"), value("damage_reduction_pct", "Ghost Trance")], [5, 20])
        self.assertEqual(value("regen_per_second_resource", "Rain Dance"), 250)
        self.assertEqual(value("proc_chance_pct", "Boogie Man"), 50)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, cite in (("big_bad_voodoo_tick_seconds", "0.5", "Witchdoctor_BigBadVoodoo.pow SF_10"),
                               ("big_bad_voodoo_linger_seconds", "0.2", "Witchdoctor_BigBadVoodoo.pow SF_9"),
                               ("big_bad_voodoo_radius_yards", "30", "Witchdoctor_BigBadVoodoo.pow SF_2")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(cite, rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists(self):
        text = (FOLDER / "dc_witch_doctor_big_bad_voodoo.cpp").read_text(encoding="utf-8")
        for name in re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text):
            self.assertIn(name, tunables(), name)
        tokens = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        for token in re.findall(r'Num\(\s*(?:id|spellId),\s*"([a-z_]+)"', text):
            self.assertIn(token, tokens, token)

    def test_the_numbers_are_the_power_file(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_BigBadVoodoo.pow"))["sf"]
        number = lambda n: float(str(sf[n]).strip())  # noqa: E731
        self.assertAlmostEqual(number(1) * 100, value("movement_speed_pct"))
        self.assertAlmostEqual(number(2), tune("big_bad_voodoo_radius_yards"))
        self.assertAlmostEqual(number(3) * 100, value("damage_bonus_pct", "Slam Dance"))
        self.assertAlmostEqual(number(4) * 100, value("heal_pct", "Ghost Trance"))
        self.assertAlmostEqual(number(5), value("regen_per_second_resource", "Rain Dance"))
        self.assertAlmostEqual(number(6) * 100, value("proc_chance_pct", "Boogie Man"))
        self.assertAlmostEqual(number(7), value("duration_seconds"))
        self.assertAlmostEqual(number(7) + 10, value("duration_seconds", "Jungle Drums"))
        self.assertAlmostEqual(number(10), tune("big_bad_voodoo_tick_seconds"))
        self.assertAlmostEqual(number(10) + tune("big_bad_voodoo_linger_seconds"), 0.7)
        self.assertAlmostEqual(number(12), value("cooldown_seconds"))
        self.assertAlmostEqual(number(13) * 100, value("damage_reduction_pct", "Ghost Trance"))


# The one Reduce of the Witch Doctor on the Mitigate line: the passives', Big Bad Voodoo's, the dogs' and Spirit Vessel's reducers each
# applied once. A line written twice (a second Reduce, a merge that kept both) would reduce the damage twice.
REDUCE_LINE = "return Passive::Survival::Reduce(victim, ZombieDogs::Reduce(victim, BigBadVoodoo::Reduce(victim, Passive::Reduce(victim, damage))));"


def reduce_line_once(test, dispatch):
    test.assertEqual(dispatch.count(REDUCE_LINE), 1, "the dispatch's Reduce line is written exactly once")


class Wiring(unittest.TestCase):
    def test_the_dispatch_hands_the_ritual_what_it_needs(self):
        dispatch = code("classes/witch_doctor/dc_witch_doctor.cpp")
        self.assertEqual(dispatch.count("BigBadVoodoo::Ground(player, spellId, center);"), 1)
        self.assertEqual(dispatch.count("BigBadVoodoo::Multipliers(player, out);"), 1)
        self.assertEqual(dispatch.count("BigBadVoodoo::RegisterScripts();"), 1)
        # Its reduction comes first, then the dogs' share of what is left, then Spirit Vessel's fatal check.
        reduce_line_once(self, dispatch)

    def test_a_reduce_line_written_twice_is_caught(self):
        dispatch = code("classes/witch_doctor/dc_witch_doctor.cpp")
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, REDUCE_LINE + " " + REDUCE_LINE))
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, ""))

    def test_each_rune_does_what_its_tooltip_says(self):
        text = code("classes/witch_doctor/dc_witch_doctor_big_bad_voodoo.cpp")
        self.assertIn('zone.until = Now() + std::uint64_t(Num(spellId, "duration_seconds") * 1000.0 + 0.5);', text)
        self.assertIn('Stats::AddContribution(guid, {Source::Temporary, Stat::AttackSpeed, id, speed, Bucket::Flat});', text)
        self.assertIn('Stats::AddContribution(guid, {Source::Temporary, Stat::MovementSpeed, id, speed, Bucket::Uncapped});', text)
        self.assertIn('if (IsRune(spellId, "Rain Dance") && Passive::IsWitchDoctor(ally))', text)
        self.assertIn('Num(spellId, "regen_per_second_resource"), Bucket::Flat', text)
        self.assertIn('TickHeal(double(ally->GetMaxHealth()), Num(id, "heal_pct"), tick)', text)
        self.assertIn('AddFactor(out, "Slam Dance", Num(id, "damage_bonus_pct"));', text)
        self.assertIn('Taken(damage, Num(id, "damage_reduction_pct"))', text)
        self.assertIn('Minions::Haste(owner, group, speed, speed, std::uint32_t(gift), Origin);', text)
        self.assertIn('Minions::Boost(owner, group, Num(id, "damage_bonus_pct"), std::uint32_t(gift), Origin);', text)
        self.assertIn('Rises(frand(0.0f, 100.0f), Num(id, "proc_chance_pct"))', text)
        self.assertIn("Pets::RaiseDogAt(witchDoctor, at);", text)
        self.assertIn("if (old) End(player, old);", text)

    def test_boogie_mans_dog_needs_room(self):
        pets = code("classes/witch_doctor/dc_witch_doctor_pets.cpp")
        self.assertIn('Minions::Alive(owner, "dog") >= DogCap(owner)', pets)
        self.assertIn('return Minions::Raise(owner, "zombie_dog", at);', pets)
        self.assertIn("Creature* RaiseDogAt(Player* owner, Position const& at);", code("classes/witch_doctor/dc_witch_doctor_pets.h"))

    def test_boosts_and_hastes_of_different_sources_add(self):
        header = code("combat/dc_minions.h")
        self.assertIn("std::string_view source = {}", header)
        minions = code("combat/dc_minions.cpp")
        self.assertIn("total += boost.pct;", minions)
        self.assertIn("total.attackPct += haste.attackPct; total.movePct += haste.movePct;", minions)
        self.assertIn("boosts[std::string(group)][std::string(source)] = {pct, Now() + ms};", minions)


if __name__ == "__main__":
    unittest.main()
