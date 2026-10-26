"""The Witch Doctor's pets (src/classes/witch_doctor/dc_witch_doctor_pets*.{h,cpp}, on the shared piece combat/dc_minions*): the
Zombie Dogs and the Gargantuan (permanent), the Fetishes of the Army (a timed burst), the Fetish Sycophants of the passive, and the
dog Sacrifice consumes.

What this proves, and how:

  * **The rules that need no core type.** tests/witch_doctor_pets/harness.cpp compiles the real dc_witch_doctor_pets_math.h with the
    sheets' and the tunables' numbers: how many dogs may stand, a pet's Life and blow after Zombie Handler and Midnight Feast,
    where a Fetish of the Army appears on its ring, whether an enemy stands in the Gargantuan's cleave, the Sycophants' cap. Planted
    mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltips; the extra numbers the power files give are tunables with their SF cited
    (decode_pow.py power Witchdoctor_*). Nothing is the designer's: no placeholder.
  * **The creatures and the proc coefficients.** witch_doctor_summons.csv and its migration give the four creatures; the sheet holds
    each spell's proc coefficient so the Sycophants' chance reads it.
  * **It is wired.** The kinds read the sheets; the skills' calls; the Sycophants' seam in both places a hit lands; the owner's
    Strike is the pets' blow; the Gargantuan's own swing time; the Sacrifice call sends the oldest dog away.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_witch_doctor_pets.py
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
HEADER = "src/classes/witch_doctor/dc_witch_doctor_pets_math.h"
HARNESS = MODULE / "tests/witch_doctor_pets/harness.cpp"
CODE = FOLDER / "dc_witch_doctor_pets.cpp"
SKILLS = ("Summon Zombie Dogs", "Gargantuan", "Fetish Army")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, token, rune="", sheet="witch_doctor_skill_values.csv"):
    rows = [r for r in read(D3 / sheet) if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, "")]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return float(rows[0]["value"])


def passive(name, token):
    return value(name, token, sheet="witch_doctor_passive_values.csv")


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/witchdoctor.csv")}


def tune(name):
    return float(tunables()[name]["d3_value"])


def squeeze(text):
    return re.sub(r"\s+", " ", text)


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
    return [value("Summon Zombie Dogs", "pet_count"), passive("Zombie Handler", "pet_count"), passive("Midnight Feast", "pet_count"),
            passive("Fierce Loyalty", "pet_count"), tune("zombie_dog_life_pct"), passive("Zombie Handler", "pet_life_pct"),
            value("Summon Zombie Dogs", "damage_pct"), passive("Midnight Feast", "damage_bonus_pct"), tune("fetish_ring_min_yards"),
            tune("fetish_ring_max_yards"), tune("gargantuan_cleave_yards"), tune("gargantuan_cleave_degrees"),
            tune("fetish_sycophants_max"), tune("gargantuan_swing_seconds"), tune("fetish_spawn_interval_seconds")]


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)] + [str(n) for n in numbers()], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 50, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a passive adds nothing", ("std::max(0.0, skillCount) + std::max(0.0, passivesAdd)", "std::max(0.0, skillCount)")),
            ("a negative passive takes dogs away", ("std::max(0.0, skillCount) + std::max(0.0, passivesAdd)", "std::max(0.0, skillCount) + passivesAdd")),
            ("a negative count allows dogs", ("std::max(0.0, skillCount) +", "skillCount +")),
            ("the Life is not raised", ("std::max(0.0, sharePct) * (1.0 + std::max(0.0, handlerPct) / 100.0)", "std::max(0.0, sharePct)")),
            ("the Life is raised by points", ("std::max(0.0, sharePct) * (1.0 + std::max(0.0, handlerPct) / 100.0)", "std::max(0.0, sharePct) + std::max(0.0, handlerPct)")),
            ("a negative percent lowers the Life", ("(1.0 + std::max(0.0, handlerPct) / 100.0)", "(1.0 + handlerPct / 100.0)")),
            ("the blow is not raised", ("std::max(0.0, damagePct) * (1.0 + std::max(0.0, feastPct) / 100.0)", "std::max(0.0, damagePct)")),
            ("the blow is raised by points", ("std::max(0.0, damagePct) * (1.0 + std::max(0.0, feastPct) / 100.0)", "std::max(0.0, damagePct) + std::max(0.0, feastPct)")),
            ("a negative blow", ("std::max(0.0, damagePct) *", "damagePct *")),
            ("the ring ignores the inner edge", ("std::sqrt(low * low + std::min(1.0, std::max(0.0, radiusUnit)) * (high * high - low * low))", "std::sqrt(std::min(1.0, std::max(0.0, radiusUnit)) * high * high)")),
            ("the ring is covered unevenly", ("std::sqrt(low * low + std::min(1.0, std::max(0.0, radiusUnit)) * (high * high - low * low))", "low + std::min(1.0, std::max(0.0, radiusUnit)) * (high - low)")),
            ("the radius draw has no end", ("std::min(1.0, std::max(0.0, radiusUnit))", "std::max(0.0, radiusUnit)")),
            ("an inverted ring", ("double const low = std::max(0.0, minYards), high = std::max(low, maxYards);", "double const low = std::max(0.0, minYards), high = maxYards;")),
            ("the angle is half a turn", ("2.0 * 3.141592653589793 * std::min", "3.141592653589793 * std::min")),
            ("the angle swaps the axes", ("return {radius * std::cos(angle), radius * std::sin(angle)};", "return {radius * std::sin(angle), radius * std::cos(angle)};")),
            ("the angle does not wrap", ("difference > twoPi / 2 ? twoPi - difference : difference", "difference")),
            ("the cleave is a full circle", ("AngleBetween(heading, centre) <= degrees * 0.017453292519943295 / 2.0 + 1e-9", "true")),
            ("the cleave is the whole angle each side", ("degrees * 0.017453292519943295 / 2.0 + 1e-9", "degrees * 0.017453292519943295 + 1e-9")),
            ("the side is out", ("degrees * 0.017453292519943295 / 2.0 + 1e-9", "degrees * 0.017453292519943295 / 2.0 - 1e-3")),
            ("the cleave has no reach", ("distance < 0 || distance > yards", "distance < 0")),
            ("the reach's end is out", ("distance > yards", "distance >= yards")),
            ("no angle still cleaves", ("if (degrees <= 0 || yards <= 0 || distance < 0 || distance > yards)", "if (yards <= 0 || distance < 0 || distance > yards)")),
            ("the Sycophants have no most", ("return cap > 0 && standing < cap;", "return cap > 0;")),
            ("one Sycophant too many", ("return cap > 0 && standing < cap;", "return cap > 0 && standing <= cap;")),
            ("no cap summons without end", ("return cap > 0 && standing < cap;", "return standing < cap || cap == 0;")),
            ("a time is cut short", ("std::llround(seconds * 1000.0)", "static_cast<long long>(seconds * 1000.0)")),
            ("a time is in seconds", ("std::llround(seconds * 1000.0)", "std::llround(seconds)")),
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
    def test_the_skills_sheet_numbers(self):
        self.assertEqual([value("Summon Zombie Dogs", t) for t in ("cooldown_seconds", "pet_count", "damage_pct")], [45, 3, 120])
        self.assertEqual([value("Gargantuan", t) for t in ("cooldown_seconds", "damage_pct")], [60, 450])
        self.assertEqual([value("Fetish Army", t) for t in ("cooldown_seconds", "pet_count", "duration_seconds", "damage_pct")],
                         [120, 5, 20, 180])

    def test_the_passives_sheet_numbers(self):
        self.assertEqual([passive("Zombie Handler", t) for t in ("pet_life_pct", "pet_count")], [20, 1])
        self.assertEqual(passive("Midnight Feast", "damage_bonus_pct"), 50)
        self.assertEqual(passive("Midnight Feast", "pet_count"), 1)
        self.assertEqual(passive("Fierce Loyalty", "pet_count"), 1)
        self.assertEqual([passive("Fetish Sycophants", t) for t in ("proc_chance_pct", "duration_seconds")], [15, 60])

    def test_every_name_the_pets_read_exists(self):
        text = CODE.read_text(encoding="utf-8")
        skills = {r["skill"] for r in read(D3 / "witch_doctor_skill_values.csv")}
        passives = {r["skill"] for r in read(D3 / "witch_doctor_passive_values.csv")}
        for name in ("Summon Zombie Dogs", "Gargantuan", "Fetish Army"):
            self.assertIn(name, skills)
        for name in ("Zombie Handler", "Fierce Loyalty", "Midnight Feast", "Fetish Sycophants"):
            self.assertIn(name, passives)
        tokens = set(re.findall(r'Num\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"\)', text)) | set(re.findall(r'FromPassive\([^,]+, [^,]+, "([a-z_]+)"\)', text))
        sheet = {r["token"] for r in read(D3 / "witch_doctor_skill_values.csv") if r["skill"] in SKILLS}
        sheet |= {r["token"] for r in read(D3 / "witch_doctor_passive_values.csv")}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"pet_count", "damage_pct", "duration_seconds", "pet_life_pct", "damage_bonus_pct", "proc_chance_pct"})

    def test_the_sheet_holds_each_spells_proc_coefficient(self):
        rows = [r for r in read(D3 / "witch_doctor_skill_values.csv") if r["token"] == "proc_coefficient"]
        self.assertGreaterEqual(len(rows), 100)
        for row in rows:
            self.assertIn("decode_pow.py power", row["source"])
            self.assertGreaterEqual(float(row["value"]), 0)
        self.assertEqual(value("Fetish Army", "proc_coefficient"), 0.2)
        mapped = {(r["skill"], r["rune"], r["token"]) for r in read(MODULE / "data/generated/spell_value_map.csv")}
        self.assertIn(("Fetish Army", "", "proc_coefficient"), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "zombie_dog_life_pct": "35",             # Witchdoctor_SummonZombieDog.pow
        "gargantuan_life_pct": "50",             # Witchdoctor_Gargantuan.pow
        "gargantuan_swing_seconds": "3",         # Witchdoctor_Gargantuan_Cleave.pow
        "gargantuan_cleave_yards": "15",
        "gargantuan_cleave_degrees": "180",
        "fetish_ring_min_yards": "9",            # Witchdoctor_FetishArmy.pow
        "fetish_ring_max_yards": "14",
        "fetish_spawn_interval_seconds": "0.1",
        "fetish_sycophants_max": "15",           # Witchdoctor_Passive_FetishSycophants.pow
    }

    ALEX = {"fetish_life_pct": "35"}             # a Fetish's Life: no power file states it; the designer's value, card q-1021-95

    def test_the_rows_hold_the_power_files_numbers_apart_from_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("Power/Witchdoctor_", rows[name]["notes"])

    def test_a_fetishs_life_is_alexs_card_value(self):
        rows = tunables()
        for name, number in self.ALEX.items():
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), ("", number))
            self.assertIn("q-1021-95", rows[name]["notes"])
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS) | set(self.ALEX))


class Creatures(unittest.TestCase):
    def test_four_creatures_from_the_sheet(self):
        rows = read(D3 / "witch_doctor_summons.csv")
        self.assertEqual([(r["summon"], r["entry"], r["script"]) for r in rows],
                         [("Zombie Dog", "900170", "dc_minion"), ("Gargantuan", "900171", "dc_minion"),
                          ("Fetish", "900172", "dc_minion"), ("Fetish Sycophant", "900173", "dc_minion")])
        text = CODE.read_text(encoding="utf-8") + (FOLDER / "dc_witch_doctor_pets.h").read_text(encoding="utf-8")
        for row in rows:
            self.assertIn(row["entry"], text)

    def test_the_migration_gives_each_one_its_own_template_and_no_loot(self):
        sql = (MODULE / "data/sql/db-world/updates/minions_0003_witch_doctor_summons.sql").read_text(encoding="utf-8")
        for entry, donor in (("900170", "8599"), ("900171", "27605"), ("900172", "416"), ("900173", "416")):
            self.assertIn(f"WHERE entry={donor};", sql)
            self.assertIn(f"SET entry={entry},", sql)
            self.assertIn(f"WHERE CreatureID={entry};", sql)
        self.assertEqual(sql.count("ScriptName='dc_minion'"), 4)
        self.assertEqual(sql.count("lootid=0,pickpocketloot=0,skinloot=0"), 4)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.resolve = squeeze((SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))
        self.combat = squeeze((SRC / "combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.internal = (SRC / "combat/dc_combat_internal.h").read_text(encoding="utf-8")
        self.minions = squeeze((SRC / "combat/dc_minions.cpp").read_text(encoding="utf-8"))

    def test_the_four_kinds_are_defined_at_startup(self):
        for key, make in (("zombie_dog", "Dog"), ("gargantuan", "Gargantuan"), ("fetish", "Fetish"), ("fetish_sycophant", "Sycophant")):
            self.assertIn(f'Minions::Define("{key}", {make});', self.code)
        self.assertIn("WitchDoctor::Pets::RegisterScripts();", self.combat)
        self.assertIn('#include "../classes/witch_doctor/dc_witch_doctor_pets.h"', self.internal)

    def test_the_dogs_stand_up_to_the_cap_the_passives_raise(self):
        self.assertIn('for (std::string_view passive : DogPassives) extra += FromPassive(owner, passive, "pet_count");', self.code)
        self.assertIn('Pets::DogCap(Num(BaseId(DogSkill), "pet_count"), extra);', self.code)
        self.assertIn('constexpr std::string_view DogPassives[] = {"Zombie Handler", "Fierce Loyalty", "Midnight Feast"};', self.code)
        self.assertIn("while (standing + raised < cap && Minions::Raise(owner, \"zombie_dog\", Beside(owner, standing + raised))) ++raised;", self.code)

    def test_the_pets_strike_with_the_skills_record_and_the_passives_raise_them(self):
        self.assertIn('BlowPct(Num(record, "damage_pct"), FromPassive(owner, "Midnight Feast", "damage_bonus_pct"))', self.code)
        self.assertIn('LifePct(Tune("zombie_dog_life_pct"), FromPassive(owner, "Zombie Handler", "pet_life_pct"))', self.code)
        self.assertIn('LifePct(Tune("gargantuan_life_pct"), FromPassive(owner, "Zombie Handler", "pet_life_pct"))', self.code)

    def test_both_fetishes_have_a_share_of_the_witch_doctors_life(self):
        for kind, duration in (("Fetish(Player*)", 'kind.lifeMs = Millis(Num(record, "duration_seconds"));'),
                               ("Sycophant(Player*)", 'kind.lifeMs = Millis(Num(PassiveId(SycophantPassive), "duration_seconds"));')):
            body = self.code[self.code.index("Minions::Kind " + kind):]
            body = body[:body.index("return kind;")]
            self.assertIn(duration + ' kind.lifeToCopyPct = Tune("fetish_life_pct");', body)

    def test_the_gargantuan_swings_on_its_own_time_and_cleaves(self):
        self.assertIn('kind.swingMs = Millis(Tune("gargantuan_swing_seconds"));', self.code)
        self.assertIn("kind.cap = 1;", self.code)
        self.assertIn("InCleave(pet->GetAngle(other), centre, pet->GetExactDist(other), yards, degrees)", self.code)
        self.assertIn("other != struck && other->IsAlive()", self.code)
        self.assertIn("Combat::Strike(owner, other, record, pct);", self.code)
        self.assertIn("kind.struck = [record, blow](Player* player, Unit* enemy) { Cleave(player, enemy, record, blow); };", self.code)
        self.assertIn("Minions::Dismiss(owner, \"gargantuan\");", self.code)

    def test_the_minions_piece_reads_a_swing_time_of_its_own(self):
        self.assertIn("SwingMs(aps, kind.swingMs)", self.minions)

    def test_the_army_raises_its_fetishes_on_a_ring_one_by_one_for_its_seconds(self):
        self.assertIn('Offset const offset = RingPoint(low, high, rand_norm(), rand_norm());', self.code)
        self.assertIn("After(owner, (firstIndex + i) * interval,", self.code)
        self.assertIn('kind.lifeMs = Millis(Num(record, "duration_seconds"));', self.code)
        self.assertIn('kind.cap = unsigned(Num(record, "pet_count")) + armyCast.extra;', self.code)
        self.assertIn("Minions::Raise(owner, key, at);", self.code)
        self.assertIn('return Ring(owner, "fetish", unsigned(Num(BaseId(ArmySkill), "pet_count")) + extra, 0, extra, std::move(arrival));', self.code)

    def test_sacrifice_takes_the_oldest_dog(self):
        self.assertIn('return Minions::DismissOldest(owner, "dog");', self.code)
        self.assertIn('return owner && Minions::Alive(owner, "dog") > 0;', self.code)
        self.assertIn('std::optional<Position> DismissOldest(Player* owner, std::string_view group)', self.minions)

    def test_the_sycophants_proc_reads_the_spells_coefficient_and_stops_at_the_most(self):
        self.assertIn("if (!IsWitchDoctor(owner) || !Chosen(owner, SycophantPassive) || IsPetSkill(spellId)) return;", self.code)
        self.assertIn('if (!MaySummonSycophant(Minions::Alive(owner, "sycophant"), unsigned(Tune("fetish_sycophants_max")))) return;', self.code)
        self.assertIn('Proc::Rolls(Numbers::Get(spellId, "proc_coefficient"), FromPassive(owner, SycophantPassive, "proc_chance_pct"),', self.code)
        self.assertIn('Minions::Raise(owner, "fetish_sycophant", Beside(owner, 0));', self.code)
        self.assertIn('kind.lifeMs = Millis(Num(PassiveId(SycophantPassive), "duration_seconds"));', self.code)

    def test_the_seam_is_called_where_every_hit_lands(self):
        self.assertEqual(self.resolve.count("WitchDoctor::Pets::Landed(player, target, shell.spellId);"), 1)
        self.assertLess(self.resolve.index("DemonHunter::Landed(player, target, shell.spellId, hit.critical);"), self.resolve.index("WitchDoctor::Pets::Landed(player, target, shell.spellId);"))
        self.assertEqual(self.resolve.count("WitchDoctor::Pets::Landed(player, target, spellId);"), 1)
        self.assertLess(self.resolve.index("DemonHunter::Landed(player, target, spellId, hit.critical);"), self.resolve.index("WitchDoctor::Pets::Landed(player, target, spellId);"))


if __name__ == "__main__":
    unittest.main()
