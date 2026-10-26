"""The Gargantuan and its five runes (src/classes/witch_doctor/dc_witch_doctor_gargantuan*.{h,cpp}, on the pets' piece
dc_witch_doctor_pets.cpp and the shared minions piece combat/dc_minions*): Restless Giant, Humongoid, Big Stinker, Wrathful Protector,
Bruiser.

What this proves, and how:

  * **The rules that need no core type.** tests/witch_doctor_gargantuan/harness.cpp compiles the real dc_witch_doctor_gargantuan_math.h
    with the sheets' and the tunables' numbers: when Restless Giant enrages and when it may again, what a pulse of Big Stinker's cloud
    deals, how Wrathful Protector's attack speed shortens a swing, what lifts an enemy into the air. Planted mutations must each turn it
    red.
  * **The numbers.** Every rune's tooltip number is a row of witch_doctor_skill_values.csv; the numbers only the power files give are
    tunables with their SF cited, equal to the decoded Power/Witchdoctor_Gargantuan*.pow (skipped where the game archives are not on
    this machine). Nothing is the designer's: no placeholder; two readings are in the contract.
  * **It is wired.** The ground cast raises the Gargantuan; the pets' piece asks the runes for its blow and to shape it; the cleave takes
    Restless Giant's boost; the minions piece carries the watch, the haste and the boost readout, and nothing else changes for the kinds
    that do not set them; the dispatch hands the ground cast to the runes.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_gargantuan.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_gargantuan_math.h"
HARNESS = MODULE / "tests/witch_doctor_gargantuan/harness.cpp"
SKILL = "Gargantuan"
RUNES = ("Restless Giant", "Humongoid", "Big Stinker", "Wrathful Protector", "Bruiser")


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
    return [value("nearby_enemy_count", "Restless Giant"), value("internal_cooldown_seconds", "Restless Giant"),
            value("damage_pct", "Big Stinker"), tune("big_stinker_tick_seconds"), tune("gargantuan_swing_seconds"),
            tune("wrathful_protector_attack_speed_factor"), tune("wrathful_protector_lift_yards")]


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)] + [str(n) for n in numbers()], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 16, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("an elite does not enrage it", ("return elite || (most > 0 && nearby >= most);", "return most > 0 && nearby >= most;")),
            ("a crowd does not enrage it", ("return elite || (most > 0 && nearby >= most);", "return elite;")),
            ("one enemy short enrages it", ("nearby >= most);", "nearby + 1 >= most);")),
            ("one enemy too many is needed", ("nearby >= most);", "nearby > most);")),
            ("no number named, always a crowd", ("return elite || (most > 0 && nearby >= most);", "return elite || nearby >= most;")),
            ("it never rests", ("return !lastMs || nowMs >= *lastMs + cooldownMs;", "return true;")),
            ("it never comes back", ("return !lastMs || nowMs >= *lastMs + cooldownMs;", "return !lastMs;")),
            ("it comes back a moment late", ("nowMs >= *lastMs + cooldownMs", "nowMs > *lastMs + cooldownMs")),
            ("a pulse deals the whole second", ("perSecondPct * tickSeconds : 0.0", "perSecondPct : 0.0")),
            ("a pulse is divided by its pause", ("perSecondPct * tickSeconds : 0.0", "perSecondPct / tickSeconds : 0.0")),
            ("a pause of nothing pulses", ("return perSecondPct > 0 && tickSeconds > 0 ?", "return perSecondPct > 0 ?")),
            ("no damage pulses", ("return perSecondPct > 0 && tickSeconds > 0 ?", "return tickSeconds > 0 ?")),
            ("the swing is slower", ("swingMs / factor : swingMs", "swingMs * factor : swingMs")),
            ("no factor divides the swing by nothing", ("return swingMs > 0 && factor > 0 ?", "return swingMs > 0 ?")),
            ("the swing is the factor", ("swingMs / factor : swingMs", "factor : swingMs")),
            ("the lift is too low", ("std::sqrt(2 * gravity * heightYards)", "std::sqrt(gravity * heightYards)")),
            ("the lift moves nothing sideways", ("return {MinimumSpeedXY * 1.1,", "return {0.0,")),
            ("the lift is at the core's limit", ("return {MinimumSpeedXY * 1.1,", "return {MinimumSpeedXY,")),
            ("a negative height lifts", ("if (heightYards <= 0 || gravity <= 0)", "if (gravity <= 0)")),
            ("no gravity lifts", ("if (heightYards <= 0 || gravity <= 0)", "if (heightYards <= 0)")),
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
        text = (FOLDER / "dc_witch_doctor_gargantuan.cpp").read_text(encoding="utf-8")
        for name in RUNES:
            self.assertIn(f'name == "{name}"', text)

    def test_the_tooltip_numbers(self):
        self.assertEqual([value("damage_pct"), value("cooldown_seconds")], [450, 60])
        self.assertEqual([value(t, "Restless Giant") for t in ("nearby_enemy_count", "duration_seconds", "movement_speed_pct", "attack_speed_pct",
                                                               "damage_bonus_pct", "internal_cooldown_seconds")], [5, 15, 20, 35, 200, 45])
        self.assertEqual(value("damage_pct", "Humongoid"), 585)
        self.assertEqual(value("damage_pct", "Big Stinker"), 135)
        self.assertEqual([value("duration_seconds", "Wrathful Protector"), value("damage_pct", "Wrathful Protector")], [15, 575])
        self.assertEqual([value("damage_pct", "Bruiser"), value("stun_duration_seconds", "Bruiser")], [200, 3])

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, cite in (("restless_giant_check_seconds", "1", "Witchdoctor_Gargantuan.pow SF_29"),
                               ("restless_giant_check_yards", "15", "Witchdoctor_Gargantuan.pow SF_30"),
                               ("big_stinker_radius_yards", "12", "Witchdoctor_Gargantuan.pow SF_7"),
                               ("big_stinker_tick_seconds", "1", "Witchdoctor_Gargantuan.pow SF_8"),
                               ("wrathful_protector_attack_speed_factor", "2", "Witchdoctor_Gargantuan.pow SF_27"),
                               ("wrathful_protector_smash_radius_yards", "5", "Witchdoctor_Gargantuan.pow SF_28"),
                               ("wrathful_protector_lift_yards", "3", "Witchdoctor_Gargantuan_Smash.pow SF_3"),
                               ("bruiser_slam_cooldown_seconds", "1", "Witchdoctor_Gargantuan_Slam.pow CooldownTime"),
                               ("bruiser_slam_yards", "15", "Witchdoctor_Gargantuan_Slam.pow SF_0")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(cite, rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists(self):
        text = (FOLDER / "dc_witch_doctor_gargantuan.cpp").read_text(encoding="utf-8")
        for name in re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text):
            self.assertIn(name, tunables(), name)
        tokens = {t for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] == SKILL for t in [r["token"]]}
        for token in re.findall(r'Num\(\s*(?:id|slot\.id|base),\s*"([a-z_]+)"', text):
            self.assertIn(token, tokens, token)

    def test_the_numbers_are_the_power_files(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")

        def sf(name):
            return decode_pow.parse_power(decode_pow.extract(f"Power/Witchdoctor_{name}.pow"))["sf"]

        garg = sf("Gargantuan")
        number = lambda n: float(str(garg[n]).strip())  # noqa: E731
        self.assertAlmostEqual(number(6) * 100, value("movement_speed_pct", "Restless Giant"))
        self.assertAlmostEqual(number(9), value("duration_seconds", "Restless Giant"))
        self.assertAlmostEqual(number(14) * 100, value("attack_speed_pct", "Restless Giant"))
        self.assertAlmostEqual(number(15), value("nearby_enemy_count", "Restless Giant"))
        self.assertAlmostEqual(number(31), value("internal_cooldown_seconds", "Restless Giant"))
        self.assertAlmostEqual(number(29), tune("restless_giant_check_seconds"))
        self.assertAlmostEqual(number(30), tune("restless_giant_check_yards"))
        self.assertAlmostEqual(number(5) * 100, value("damage_pct", "Big Stinker"))
        self.assertAlmostEqual(number(7), tune("big_stinker_radius_yards"))
        self.assertAlmostEqual(number(8), tune("big_stinker_tick_seconds"))
        self.assertAlmostEqual(number(19), value("duration_seconds", "Wrathful Protector"))
        self.assertAlmostEqual(number(22) * 100, value("damage_pct", "Wrathful Protector"))
        self.assertAlmostEqual(number(27), tune("wrathful_protector_attack_speed_factor"))
        self.assertAlmostEqual(number(28), tune("wrathful_protector_smash_radius_yards"))
        self.assertAlmostEqual(float(str(garg[4]).split(":")[-1]) * 100, value("damage_pct", "Bruiser"))
        self.assertAlmostEqual(number(3), value("stun_duration_seconds", "Bruiser"))
        self.assertAlmostEqual(number(24) * 100, value("damage_pct"))
        self.assertAlmostEqual(1.3 * number(24) * 100, value("damage_pct", "Humongoid"))
        self.assertAlmostEqual(number(11), value("cooldown_seconds"))
        smash = sf("Gargantuan_Smash")
        self.assertAlmostEqual(float(str(smash[3]).strip()), tune("wrathful_protector_lift_yards"))
        self.assertAlmostEqual(float(str(smash[1]).strip()), 0.0)
        slam = sf("Gargantuan_Slam")
        self.assertAlmostEqual(float(str(slam[0]).strip()), tune("bruiser_slam_yards"))


class Wiring(unittest.TestCase):
    def test_the_ground_cast_raises_it(self):
        text = code("classes/witch_doctor/dc_witch_doctor_gargantuan.cpp")
        self.assertIn("if (!player || !Is(spellId)) return; Pets::RaiseGargantuan(player, center);", text)
        dispatch = code("classes/witch_doctor/dc_witch_doctor.cpp")
        self.assertEqual(dispatch.count("GargantuanRunes::Ground(player, spellId, center);"), 1)

    def test_the_pets_piece_asks_the_runes_for_the_blow_and_the_shape(self):
        pets = code("classes/witch_doctor/dc_witch_doctor_pets.cpp")
        self.assertIn("auto const own = GargantuanRunes::BlowOf(owner); std::uint32_t const record = own.record;", pets)
        self.assertIn("double const blow = BlowPct(own.pct, feast);", pets)
        self.assertEqual(pets.count("GargantuanRunes::Shape(owner, kind, feast);"), 1)
        # Restless Giant's boost reaches the cleave's other blows as it does the swing.
        self.assertIn('double const pct = Minions::BoostedPct(blowPct, Minions::BoostPercent(owner, "gargantuan"));', pets)
        self.assertIn("Combat::Strike(owner, other, record, pct);", pets)

    def test_each_rune_sets_what_its_tooltip_says(self):
        text = code("classes/witch_doctor/dc_witch_doctor_gargantuan.cpp")
        self.assertIn('Minions::Boost(owner, Group, Num(id, "damage_bonus_pct"), ms); Minions::Haste(owner, Group, Num(id, "attack_speed_pct"), Num(id, "movement_speed_pct"), ms);', text)
        self.assertIn("return unit->IsPlayer() || !Combat::IsLesser(unit);", text)
        self.assertIn('kind.auraRadius = Tune("big_stinker_radius_yards"); kind.auraRecord = id;', text)
        self.assertIn('kind.auraPct = PulsePct(Pets::BlowPct(Num(id, "damage_pct"), feastPct), tick);', text)
        self.assertIn('kind.lifeMs = Pets::Millis(Num(id, "duration_seconds"));', text)
        self.assertIn('kind.swingMs = Quickened(kind.swingMs, Tune("wrathful_protector_attack_speed_factor"));', text)
        self.assertIn("kind.struck = [id, blow](Player* player, Unit* enemy) { Smash(player, enemy, id, blow); };", text)
        self.assertIn('Num(id, "stun_duration_seconds") * ItemPowers::StunFactor(owner);', text)
        self.assertIn("Stun(owner, enemy, stun);", text)
        self.assertIn("if (rune == Rune::Humongoid || rune == Rune::WrathfulProtector) return {slot.id, Num(slot.id, \"damage_pct\")};", text)

    def test_the_shared_piece_carries_the_new_fields_and_leaves_the_old_ones(self):
        header = code("combat/dc_minions.h")
        for field in ("watchEveryMs", "watch;", "BoostPercent", "Haste("):
            self.assertIn(field, header)
        self.assertNotIn("WitchDoctor", header)
        minions = code("combat/dc_minions.cpp")
        self.assertIn("kind.watch(player, me);", minions)
        self.assertIn("double const wait = SwingMs(aps, kind.swingMs) / (1.0 + std::max(0.0, haste.attackPct) / 100.0);", minions)
        self.assertIn("me->SetSpeedRate(MOVE_RUN, baseRun * float(1.0 + std::max(0.0, pct) / 100.0));", minions)
        self.assertIn("Hasted const haste = HasteOf(owner.GetRawValue(), kind.group); Run(haste.movePct);", minions)

    def test_the_dogs_and_the_gargantuan_read_the_bar_the_same_way(self):
        bar = code("classes/witch_doctor/dc_witch_doctor_bar.h")
        self.assertIn("for (Classes::Slot const& slot : Classes::Bar(owner))", bar)
        self.assertIn("OnBar(owner, Skill)", code("classes/witch_doctor/dc_witch_doctor_gargantuan.cpp"))
        self.assertIn("WitchDoctor::OnBar(owner, Skill)", code("classes/witch_doctor/dc_witch_doctor_zombie_dogs.cpp"))


if __name__ == "__main__":
    unittest.main()
