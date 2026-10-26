"""Summon Zombie Dogs and its five runes (src/classes/witch_doctor/dc_witch_doctor_zombie_dogs*.{h,cpp}, on the pets' piece
dc_witch_doctor_pets.cpp and the shared minions piece combat/dc_minions*): Burning Dogs, Life Link, Rabid Dogs, Chilled to the Bone,
Leeching Beasts.

What this proves, and how:

  * **The rules that need no core type.** tests/witch_doctor_zombie_dogs/harness.cpp compiles the real
    dc_witch_doctor_zombie_dogs_math.h with the sheets' and the tunables' numbers: what one pulse of Burning Dogs deals, the share of a
    blow Life Link gives the dogs and each dog's part, what Leeching Beasts heals, how Midnight Feast's raise reaches a rune's damage,
    when dogs of another rune go. Planted mutations must each turn it red.
  * **The numbers.** Every rune's tooltip number is a row of witch_doctor_skill_values.csv; the numbers only the power file gives are
    tunables with their SF cited, equal to the decoded Power/Witchdoctor_SummonZombieDog.pow (skipped where the game archives are not on
    this machine). The one number neither gives, Rabid Dogs' poison tick, is the designer's standing default for a burn or bleed tick.
  * **It is wired.** The cast raises the dogs; the pets' piece asks the rune to shape each dog; the minions piece carries the aura
    record, the pulse time, the blow and hurt callbacks the runes use, and nothing else changes for the kinds that do not set them; the
    dispatch hands the cast and the damage taken to the runes.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_zombie_dogs.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_zombie_dogs_math.h"
HARNESS = MODULE / "tests/witch_doctor_zombie_dogs/harness.cpp"
SKILL = "Summon Zombie Dogs"
RUNES = ("Burning Dogs", "Life Link", "Rabid Dogs", "Chilled to the Bone", "Leeching Beasts")


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
    return [value("damage_pct", "Burning Dogs"), tune("burning_dogs_tick_seconds"), value("absorb_pct", "Life Link"),
            value("life_per_hit_share_pct", "Leeching Beasts"), 1000.0, 500.0, value("damage_pct"), value("damage_pct") * 1.5]


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)] + [str(n) for n in numbers()], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 18, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a pulse deals the whole second", ("perSecondPct * tickSeconds : 0.0", "perSecondPct : 0.0")),
            ("a pulse is divided by its pause", ("perSecondPct * tickSeconds : 0.0", "perSecondPct / tickSeconds : 0.0")),
            ("a pause of nothing pulses", ("return perSecondPct > 0 && tickSeconds > 0 ?", "return perSecondPct > 0 ?")),
            ("no damage pulses", ("return perSecondPct > 0 && tickSeconds > 0 ?", "return tickSeconds > 0 ?")),
            ("the dogs take more than their share", ("damage * std::min(pct, 100.0) / 100.0", "damage * pct / 100.0")),
            ("the dogs take the whole blow", ("damage * std::min(pct, 100.0) / 100.0", "damage")),
            ("a negative blow is shared", ("return damage > 0 && pct > 0 ? damage", "return pct > 0 ? damage")),
            ("a negative share is taken", ("return damage > 0 && pct > 0 ? damage", "return damage > 0 ? damage")),
            ("each dog takes the whole share", ("return dogs ? share / dogs : 0.0;", "return share;")),
            ("the dogs' parts fall short", ("return dogs ? share / dogs : 0.0;", "return dogs ? share / (dogs + 1) : 0.0;")),
            ("no dog still takes a part", ("return dogs ? share / dogs : 0.0;", "return dogs ? share / dogs : share;")),
            ("an attack heals the whole Life on Hit", ("lifePerHit * sharePct / 100.0 : 0.0", "lifePerHit : 0.0")),
            ("no Life on Hit heals", ("return lifePerHit > 0 && sharePct > 0 ?", "return sharePct > 0 ?")),
            ("no share heals", ("return lifePerHit > 0 && sharePct > 0 ?", "return lifePerHit > 0 ?")),
            ("a rune is not raised", ("runePct * blowPct / baseBlowPct : runePct", "runePct : runePct")),
            ("a rune is lowered", ("runePct * blowPct / baseBlowPct : runePct", "runePct * baseBlowPct / blowPct : runePct")),
            ("a rune is raised with no blow to compare", ("return baseBlowPct > 0 && blowPct > 0 ?", "return blowPct > 0 ?")),
            ("a rune is raised by a blow of nothing", ("return baseBlowPct > 0 && blowPct > 0 ?", "return baseBlowPct > 0 ?")),
            ("dogs of another rune stay", ("return raisedWith == slotted;", "return true;")),
            ("dogs of the same rune go", ("return raisedWith == slotted;", "return false;")),
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
        text = (FOLDER / "dc_witch_doctor_zombie_dogs.cpp").read_text(encoding="utf-8")
        for name in RUNES:
            self.assertIn(f'name == "{name}"', text)

    def test_the_tooltip_numbers(self):
        self.assertEqual(value("damage_pct"), 120)
        self.assertEqual(value("pet_count"), 3)
        self.assertEqual(value("cooldown_seconds"), 45)
        self.assertEqual(value("damage_pct", "Burning Dogs"), 80)
        self.assertEqual(value("absorb_pct", "Life Link"), 10)
        self.assertEqual([value("damage_pct", "Rabid Dogs"), value("dot_duration_seconds", "Rabid Dogs")], [120, 3])
        self.assertEqual(value("chill_duration_seconds", "Chilled to the Bone"), 3)
        self.assertEqual(value("life_per_hit_share_pct", "Leeching Beasts"), 100)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, own in (("burning_dogs_radius_yards", "8", ""), ("burning_dogs_tick_seconds", "0.5", ""),
                              ("chilled_to_the_bone_chill_pct", "60", ""), ("rabid_dogs_tick_seconds", "", "0.5")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, own), name)
        for name in ("burning_dogs_radius_yards", "burning_dogs_tick_seconds", "chilled_to_the_bone_chill_pct"):
            self.assertIn("Witchdoctor_SummonZombieDog.pow SF_", rows[name]["notes"], name)
        self.assertIn("standing default", rows["rabid_dogs_tick_seconds"]["notes"])

    def test_every_name_the_code_reads_exists(self):
        text = (FOLDER / "dc_witch_doctor_zombie_dogs.cpp").read_text(encoding="utf-8")
        for name in re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text):
            self.assertIn(name, tunables(), name)
        skill_tokens = {(r["rune"], r["token"]) for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL}
        for token in re.findall(r'Num\(\s*(?:id|slot\.id|BaseId\(Skill\)),\s*"([a-z_]+)"', text):
            self.assertIn(token, {t for _, t in skill_tokens}, token)

    def test_the_numbers_are_the_power_files(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/Witchdoctor_SummonZombieDog.pow"))["sf"]
        number = lambda n: float(str(sf[n]).strip())  # noqa: E731
        self.assertAlmostEqual(number(3), tune("burning_dogs_radius_yards"))
        self.assertAlmostEqual(number(10), tune("burning_dogs_tick_seconds"))
        self.assertAlmostEqual(number(1) / number(10), value("damage_pct", "Burning Dogs") / 100.0)
        self.assertAlmostEqual(number(23) * 100, tune("chilled_to_the_bone_chill_pct"))
        self.assertAlmostEqual(number(24), value("chill_duration_seconds", "Chilled to the Bone"))
        self.assertAlmostEqual(number(4), value("dot_duration_seconds", "Rabid Dogs"))
        self.assertAlmostEqual(number(5) * 100, value("damage_pct", "Rabid Dogs"))
        self.assertAlmostEqual(number(8) * 100, value("life_per_hit_share_pct", "Leeching Beasts"))
        self.assertAlmostEqual(number(11) * 100, value("damage_pct"))
        self.assertAlmostEqual(number(18), value("cooldown_seconds"))


# The one Reduce of the Witch Doctor on the Mitigate line: the passives', Big Bad Voodoo's, the dogs' and Spirit Vessel's reducers each
# applied once. A line written twice (a second Reduce, a merge that kept both) would reduce the damage twice.
REDUCE_LINE = "return Passive::Survival::Reduce(victim, ZombieDogs::Reduce(victim, BigBadVoodoo::Reduce(victim, Passive::Reduce(victim, damage))));"


def reduce_line_once(test, dispatch):
    test.assertEqual(dispatch.count(REDUCE_LINE), 1, "the dispatch's Reduce line is written exactly once")


class Wiring(unittest.TestCase):
    def test_the_cast_raises_the_dogs_and_sends_away_dogs_of_another_rune(self):
        zd = code("classes/witch_doctor/dc_witch_doctor_zombie_dogs.cpp")
        self.assertIn("keep = found == raisedWith.end() || KeepsDogs(found->second, record); }", zd)
        self.assertIn("if (!keep) Minions::Dismiss(player, Group); Pets::SummonDogs(player);", zd)
        self.assertIn("raisedWith[owner->GetGUID().GetRawValue()] = id;", zd)

    def test_the_pets_piece_asks_the_rune_to_shape_each_dog(self):
        pets = code("classes/witch_doctor/dc_witch_doctor_pets.cpp")
        self.assertEqual(pets.count("ZombieDogs::Shape(owner, kind);"), 1)
        self.assertIn('#include "dc_witch_doctor_zombie_dogs.h"', pets)

    def test_each_rune_sets_what_its_tooltip_says(self):
        zd = code("classes/witch_doctor/dc_witch_doctor_zombie_dogs.cpp")
        self.assertIn('kind.auraRadius = Tune("burning_dogs_radius_yards"); kind.auraRecord = id; kind.auraEveryMs = Pets::Millis(tick);', zd)
        self.assertIn("kind.auraPct = PulsePct(Raised(Num(id, \"damage_pct\"), base, blow), tick);", zd)
        self.assertIn("PeriodicStrike::Start(player, enemy, id, pct, seconds, tick, std::uint32_t(dog->GetGUID().GetCounter()));", zd)
        self.assertIn('Tune("chilled_to_the_bone_chill_pct"), seconds = Num(id, "chill_duration_seconds");', zd)
        self.assertIn("kind.struckBy = [chill, seconds](Player* player, Creature*, Unit* enemy) { Slow(player, enemy, chill, seconds); };", zd)
        self.assertIn("kind.hurt = [chill, seconds](Player* player, Unit* enemy) { Slow(player, enemy, chill, seconds); };", zd)
        self.assertIn("Heal(player, id, Leeched((*sheet)[Stat::LifePerHit], share));", zd)
        self.assertIn('LinkedShare(damage, Num(slot.id, "absorb_pct"));', zd)
        self.assertIn("return damage - share;", zd)

    def test_the_dispatch_hands_over_the_cast_and_the_damage(self):
        dispatch = code("classes/witch_doctor/dc_witch_doctor.cpp")
        self.assertEqual(dispatch.count("ZombieDogs::Cast(player, spellId, targets);"), 1)
        # Life Link takes its share before Spirit Vessel asks whether the blow is fatal.
        reduce_line_once(self, dispatch)

    def test_a_reduce_line_written_twice_is_caught(self):
        dispatch = code("classes/witch_doctor/dc_witch_doctor.cpp")
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, REDUCE_LINE + " " + REDUCE_LINE))
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, ""))

    def test_the_shared_piece_carries_the_new_fields_and_leaves_the_old_ones(self):
        header = code("combat/dc_minions.h")
        for field in ("auraRecord", "auraEveryMs", "struckBy", "hurt"):
            self.assertIn(field, header)
        self.assertNotIn("WitchDoctor", header)
        minions = code("combat/dc_minions.cpp")
        self.assertIn("double const every = kind.auraEveryMs ? double(kind.auraEveryMs) : 1000.0;", minions)
        self.assertIn("std::uint32_t const record = kind.auraRecord ? kind.auraRecord : kind.record;", minions)
        self.assertIn("if (kind.struckBy) kind.struckBy(player, me, target);", minions)
        self.assertIn("if (kind.hurt && attacker && damage > 0 && attacker != me)", minions)
        self.assertIn("kind.hurt(player, attacker);", minions)

    def test_the_dogs_remain_what_the_pets_piece_made_them(self):
        pets = code("classes/witch_doctor/dc_witch_doctor_pets.cpp")
        self.assertIn('kind.group = "dog"; kind.entry = DogEntry; kind.record = record;', pets)
        self.assertIn("kind.cap = DogCap(owner);", pets)


if __name__ == "__main__":
    unittest.main()
