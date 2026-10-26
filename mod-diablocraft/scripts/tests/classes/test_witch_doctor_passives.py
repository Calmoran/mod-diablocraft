"""The Witch Doctor's passives, 1 of 3: Jungle Fortitude, Circle of Life, Spiritual Attunement, Gruesome Feast, Blood Ritual and
Bad Medicine (src/classes/witch_doctor/dc_witch_doctor_passives_math.h and dc_witch_doctor_passives.cpp).

What this proves, and how:

  * **The rules that need no core type.** tests/witch_doctor_passives/harness.cpp compiles the real
    dc_witch_doctor_passives_math.h with the sheet's own numbers: a share of a pool (and nothing for no pool or a bad percent);
    Jungle Fortitude's reduction; Spiritual Attunement's bonus that never feeds on itself; Circle of Life's roll and its range
    widened by the gold pickup radius (and not by a negative one); Bad Medicine's school; Blood Ritual's payment, which never takes
    Life below 1 and leaves the rest a Mana cost. Fourteen mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_witch_doctor_passives.cpp reads by name is a row of
    witch_doctor_passive_values.csv for its passive, the generated value table says each passive's record holds it, and the numbers
    are D3's: 15% less damage, a 20 yard circle and a 15% chance, +10% maximum Mana and 2% of it a second, 10% of the pool and +10%
    Intelligence up to 5 times for 15 seconds, 20% of Mana costs paid with Life and 1% of the Life a second, 25% less enemy damage for
    5 seconds.
  * **The sheet is D3's.** The numbers are the ones the power files hold (decode_pow.py, Power/Witchdoctor_Passive_*.pow).
  * **The wiring.** The engine asks the class after the hit lands, in the damage taken and at startup; the dispatch hands each to
    the passives' file; Gruesome Feast's globe call is a seam with no caller (the health globes are not built); Circle of Life's
    Zombie Dog is raised by the pets' RaiseDogAt, which brings one only while the Witch Doctor stands short of the most dogs they
    may have; Blood Ritual's Life never takes the last point.
  * **The look is a tunable row.** How often the sheet is looked at is passive_poll_seconds (witchdoctor.csv, 1, the code's own
    cadence and not D3's): the code reads it through Tune, no number of its own is left, and the generated migration holds it.
  * **Blood Ritual's conversion is a D3 value.** The share of a Mana cost paid in Life is the power file's (0.2); the pools' own
    fraction is the rule the tooltip states, so the rate between the pools is one tunable row of 1, a published value and no card.

What it does not prove: anything on a running server, and that a health globe calls Gruesome Feast (nothing does yet).

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_passives.py
"""

import csv
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/witch_doctor/dc_witch_doctor_passives_math.h"
SOURCES = [HEADER, "tests/witch_doctor_passives/harness.cpp"]
CODE = MODULE / "src/classes/witch_doctor/dc_witch_doctor_passives.cpp"
DISPATCH = MODULE / "src/classes/witch_doctor/dc_witch_doctor.cpp"
RESOLVE = MODULE / "src/combat/dc_combat_resolve.cpp"
COMBAT = MODULE / "src/combat/dc_combat.cpp"
PASSIVES = ("Jungle Fortitude", "Circle of Life", "Spiritual Attunement", "Gruesome Feast", "Blood Ritual", "Bad Medicine")
TUNABLE = "blood_ritual_life_scale"
POLL = "passive_poll_seconds"
PETS = MODULE / "src/classes/witch_doctor/dc_witch_doctor_pets.cpp"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(passive, token):
    rows = [r for r in read(D3 / "witch_doctor_passive_values.csv") if (r["skill"], r["token"]) == (passive, token)]
    assert len(rows) == 1, (passive, token, len(rows))
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/witch_doctor_passives/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Jungle Fortitude", "damage_reduction_pct"), value("Circle of Life", "radius_yards"),
               value("Circle of Life", "proc_chance_pct"), value("Spiritual Attunement", "max_pool_pct"),
               value("Spiritual Attunement", "regen_pool_share_pct"), value("Gruesome Feast", "gain_pct"),
               value("Blood Ritual", "resource_cost_share_pct"), value("Blood Ritual", "life_regen_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 25, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        share = "return maximum > 0 && pct > 0 ? maximum * pct / 100.0 : 0.0;"
        reduced = "return damage > 0 ? damage * (1.0 - std::clamp(pct, 0.0, 100.0) / 100.0) : 0.0;"
        in_range = "return radius > 0 && distance <= radius + std::max(0.0, pickup);"
        paid = "double const paid = std::min(wanted, std::max(0.0, health - 1.0));"
        mutations = [
            ("a share that is not divided by a hundred", share.replace(" / 100.0", "")),
            ("a negative percent pays", share.replace("maximum > 0 && pct > 0", "maximum > 0")),
            ("the reduction is not clamped", reduced.replace("std::clamp(pct, 0.0, 100.0)", "pct")),
            ("a negative reduction adds damage", reduced.replace("0.0, 100.0", "-100.0, 100.0")),
            ("the pool bonus feeds on itself", "return Share(sheetMax, pct);"),
            ("the roll holds at the chance", "return roll <= chancePct;"),
            ("the pickup radius is ignored", in_range.replace(" + std::max(0.0, pickup)", "")),
            ("a negative pickup radius narrows the circle", in_range.replace("std::max(0.0, pickup)", "pickup")),
            ("the circle ends before its radius", in_range.replace("distance <=", "distance <")),
            ("another school is Poison", "return (schoolMask & 8u) != 0;"),
            ("Life can be taken to nothing", paid.replace("health - 1.0", "health")),
            ("what Life cannot pay is lost", "return {want, paid};"),
            ("the scale is ignored", "double const wanted = want / maxMana * maxLife;"),
            ("a scale of none pays", "if (want <= 0 || maxMana <= 0 || maxLife <= 0)"),
        ]
        originals = {
            "a share that is not divided by a hundred": share, "a negative percent pays": share,
            "the reduction is not clamped": reduced, "a negative reduction adds damage": reduced,
            "the pool bonus feeds on itself": "return Share(sheetMax - applied, pct);",
            "the roll holds at the chance": "return roll < chancePct;",
            "the pickup radius is ignored": in_range, "a negative pickup radius narrows the circle": in_range,
            "the circle ends before its radius": in_range,
            "another school is Poison": "return (schoolMask & 32u) != 0;",
            "Life can be taken to nothing": paid, "what Life cannot pay is lost": "return {want * (paid / wanted), paid};",
            "the scale is ignored": "double const wanted = want / maxMana * maxLife * scale;",
            "a scale of none pays": "if (want <= 0 || maxMana <= 0 || maxLife <= 0 || scale <= 0)",
        }
        for label, new in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree((HEADER, originals[label], new))
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual(value("Jungle Fortitude", "damage_reduction_pct"), 15)
        self.assertEqual((value("Circle of Life", "radius_yards"), value("Circle of Life", "proc_chance_pct")), (20, 15))
        self.assertEqual((value("Spiritual Attunement", "max_pool_pct"), value("Spiritual Attunement", "regen_pool_share_pct")), (10, 2))
        self.assertEqual([value("Gruesome Feast", t) for t in ("gain_pct", "primary_stat_pct", "duration_seconds", "max_stacks_count")],
                         [10, 10, 15, 5])
        self.assertEqual((value("Blood Ritual", "resource_cost_share_pct"), value("Blood Ritual", "life_regen_pct")), (20, 1))
        self.assertEqual((value("Bad Medicine", "enemy_damage_pct"), value("Bad Medicine", "duration_seconds")), (25, 5))

    def test_the_numbers_are_the_power_files(self):
        def sf(power):
            out = subprocess.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "power", power], capture_output=True, text=True)
            if out.returncode:
                raise unittest.SkipTest("no D3 power files on this machine")
            found = {}
            for line in out.stdout.splitlines():
                m = re.match(r"\s*SF_(\d+) '([^']*)' = (.*)$", line)
                if m:
                    found[m.group(2)] = m.group(3).strip()
            return found
        jungle = sf("Witchdoctor_Passive_JungleFortitude")
        self.assertEqual(float(jungle["Damage Modifier"]) * 100, value("Jungle Fortitude", "damage_reduction_pct"))
        circle = sf("Witchdoctor_Passive_CircleOfLife")
        self.assertEqual(float(circle["Radius - Monster Distance"]), value("Circle of Life", "radius_yards"))
        self.assertEqual(float(circle["Puppy Spawn Chance"]) * 100, value("Circle of Life", "proc_chance_pct"))
        attune = sf("Witchdoctor_Passive_SpiritualAttunement")
        self.assertEqual(float(attune["Maximum Mana Increase Amount"]) * 100, value("Spiritual Attunement", "max_pool_pct"))
        self.assertEqual(float(attune["Mana Regeneration"]) * 100, value("Spiritual Attunement", "regen_pool_share_pct"))
        feast = sf("Witchdoctor_Passive_GruesomeFeast")
        self.assertEqual(float(feast["Mana Bonus"]) * 100, value("Gruesome Feast", "gain_pct"))
        self.assertEqual(float(feast["Intelligence Bonus"]) * 100, value("Gruesome Feast", "primary_stat_pct"))
        self.assertEqual(float(feast["Buff Duration"]), value("Gruesome Feast", "duration_seconds"))
        self.assertEqual(float(feast["Max Stacks (Attack)"]), value("Gruesome Feast", "max_stacks_count"))
        ritual = sf("Witchdoctor_Passive_BloodRitual")
        self.assertEqual(float(ritual["Sacrifice Amount"]) * 100, value("Blood Ritual", "resource_cost_share_pct"))
        self.assertEqual(float(ritual["Regenerate Amount"]) * 100, value("Blood Ritual", "life_regen_pct"))
        medicine = sf("Witchdoctor_Passive_BadMedicine")
        self.assertEqual(float(medicine["Damage Reduction"]) * 100, value("Bad Medicine", "enemy_damage_pct"))
        self.assertEqual(float(medicine["Duration"]), value("Bad Medicine", "duration_seconds"))

    def test_every_name_the_code_reads_is_a_row_of_its_passive_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        calls = set(re.findall(r'Num\("([A-Za-z ]+)", "([a-z_]+)"\)', text))
        self.assertEqual({p for p, _t in calls}, set(PASSIVES))
        sheet = {(r["skill"], r["token"]) for r in read(D3 / "witch_doctor_passive_values.csv")}
        self.assertEqual(calls - sheet, set())
        ids = {r["name"]: int(r["id"]) for r in [dict(zip(("id", "name"), m)) for m in
               re.findall(r'\{(\d+), "([A-Za-z\' ]+)"\}', (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8"))]}
        table = (MODULE / "src/combat/dc_spell_values.h").read_text(encoding="utf-8")
        for passive, token in sorted(calls):
            with self.subTest(passive=passive, token=token):
                self.assertIn(f'{{{ids[passive]}, "{token}"', table)

    def test_the_conversion_is_one_published_row_and_no_placeholder(self):
        rows = [r for r in read(MODULE / "data/tunables/witchdoctor.csv") if r["name"] == TUNABLE]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["d3_value"], rows[0]["value"], rows[0]["unit"]), ("1", "", "multiplier"))
        self.assertNotIn("placeholder", rows[0]["notes"].lower())
        self.assertEqual(set(re.findall(r'Tune\("([a-z_]+)"\)', CODE.read_text(encoding="utf-8"))), {TUNABLE, POLL})
        self.assertIn(f"('witchdoctor', '{TUNABLE}',", (MODULE / "data/generated" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8"))

    def test_the_look_is_one_row_of_the_code_s_own_cadence_and_the_code_keeps_no_number_of_its_own(self):
        rows = [r for r in read(MODULE / "data/tunables/witchdoctor.csv") if r["name"] == POLL]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["d3_value"], rows[0]["value"], rows[0]["unit"]), ("1", "", "seconds"))
        self.assertIn("not D3", rows[0]["notes"])
        text = CODE.read_text(encoding="utf-8")
        self.assertIn(f'Millis(Tune("{POLL}"))', text)
        self.assertNotIn("PollMs", text)
        self.assertNotRegex(text, r"constexpr std::uint32_t \w+ = \d+;")
        migration = (MODULE / "data/generated" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        self.assertRegex(migration, r"\('witchdoctor', '" + POLL + r"', 1\.0, NULL, 'seconds',")


# The one Reduce of the Witch Doctor on the Mitigate line: the passives', Big Bad Voodoo's, the dogs' and Spirit Vessel's reducers each
# applied once. A line written twice (a second Reduce, a merge that kept both) would reduce the damage twice.
REDUCE_LINE = "return Passive::Survival::Reduce(victim, ZombieDogs::Reduce(victim, BigBadVoodoo::Reduce(victim, Passive::Reduce(victim, damage))));"


def reduce_line_once(test, dispatch):
    test.assertEqual(dispatch.count(REDUCE_LINE), 1, "the dispatch's Reduce line is written exactly once")


class Wiring(unittest.TestCase):
    def test_the_engine_asks_the_class_after_the_hit_in_the_damage_taken_and_at_startup(self):
        resolve = RESOLVE.read_text(encoding="utf-8")
        self.assertEqual(resolve.count("WitchDoctor::Landed(player, target, shell.spellId);"), 1)
        self.assertEqual(resolve.count("WitchDoctor::Landed(player, target, spellId);"), 1)
        combat = COMBAT.read_text(encoding="utf-8")
        self.assertIn("result = Necromancer::Reduce(victim, result);\n        result = WitchDoctor::Reduce(victim, result);", combat)
        self.assertIn("DemonHunter::RegisterScripts();\n        WitchDoctor::RegisterScripts();", combat)

    def test_a_reduce_line_written_twice_is_caught(self):
        dispatch = " ".join(DISPATCH.read_text(encoding="utf-8").split())
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, REDUCE_LINE + " " + REDUCE_LINE))
        with self.assertRaises(AssertionError):
            reduce_line_once(self, dispatch.replace(REDUCE_LINE, ""))

    def test_the_dispatch_hands_each_call_to_the_passives_file(self):
        text = " ".join(DISPATCH.read_text(encoding="utf-8").split())
        self.assertEqual(text.count("Passive::Landed(player, target, spellId);"), 1)
        reduce_line_once(self, text)
        self.assertEqual(text.count("Passive::Register();"), 1)

    def test_gruesome_feasts_globe_call_has_no_caller_and_circle_of_lifes_dog_is_raised_by_the_pets(self):
        callers = []
        for path in (MODULE / "src").rglob("*.cpp"):
            if path != CODE and "Passive::GlobePicked" in path.read_text(encoding="utf-8", errors="ignore"):
                callers.append(path.name)
        self.assertEqual(callers, [], "the health globes are not built: nothing may call it yet")
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertRegex(text, r"void DogEmerges\(Player\* player, Position const& where\) \{ // [^}]*Pets::RaiseDogAt\(player, where\); \}")
        self.assertIn('#include "dc_witch_doctor_pets.h"', CODE.read_text(encoding="utf-8"))
        pets = " ".join(PETS.read_text(encoding="utf-8").split())
        # one dog, only while short of the most they may have, and none sent away to make room
        self.assertIn('Creature* RaiseDogAt(Player* owner, Position const& at) { if (!owner || !owner->IsInWorld() || !owner->IsAlive() || '
                      'Minions::Alive(owner, "dog") >= DogCap(owner)) return nullptr; return Minions::Raise(owner, "zombie_dog", at); }', pets)

    def test_blood_ritual_never_takes_the_last_point_of_life(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn("if (paid.life >= 1.0) player->ModifyHealth(-std::int32_t(paid.life));", text)
        self.assertIn("Num(\"Blood Ritual\", \"resource_cost_share_pct\"), Resources::Max(player, Resources::Mana), player->GetMaxHealth(), "
                      "Tune(\"blood_ritual_life_scale\"), player->GetHealth());", text)

    def test_circle_of_life_asks_the_player_hostile_to_the_dead_enemy_and_not_pets(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn("dead->IsControlledByPlayer() || dead->GetScriptName() == \"dc_minion\"", text)
        self.assertIn("!player->IsHostileTo(dead)) continue;", text)
        self.assertIn('(*sheet)[Stat::GoldPickupRange]', text)

    def test_jungle_fortitude_reaches_the_pets_through_the_damage_hook(self):
        text = " ".join(CODE.read_text(encoding="utf-8").split())
        self.assertIn('minion->GetScriptName() != "dc_minion" || !On(owner, "Jungle Fortitude")', text)
        self.assertIn('Reduced(damage, Num("Jungle Fortitude", "damage_reduction_pct"))', text)


if __name__ == "__main__":
    unittest.main()
