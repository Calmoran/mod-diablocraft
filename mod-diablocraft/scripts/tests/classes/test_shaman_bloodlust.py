"""Shaman Bloodlust and its five runes (src/classes/shaman/dc_shaman_bloodlust.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_bloodlust/harness.cpp compiles the real dc_shaman_bloodlust.h with the sheets'
    own names and numbers: each rune name is its rune; each rune adds its own number (Heroism damage reduction, Ancestral Fury damage,
    Elemental Fervor Maelstrom generation, Primal Rage cooldown reduction); Thirst for Battle's kill extends the buff by its step and
    never past its cap, which the kills reach after cap over step of them; the buff holds until it ends. Mutations planted in a
    scratch copy must each make it fail.
  * **No hit to load.** Bloodlust deals no damage: no row of the sheet for it states a `damage_pct`, so there is no hit to load above 0
    (the duration it states is the buff's).
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Bloodlust (or the rune
    that states it); the skill states every number, so there is no tunable.
  * **The wiring.** The class dispatch answers the cast seam with the allies in reach and registers the kill script; a second cast
    replaces the buff (one per player, a new stamp); each rune puts its number on the stat sheet; the end waits for a buff a kill has
    extended; no Sated debuff exists in the code.

What it does not prove: anything on a running server. The buff on the group, the refresh, the runes and the kills are
docs/test-diablocraft-xnrvn.33.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_bloodlust.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADERS = ["src/classes/shaman/dc_shaman_bloodlust.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_bloodlust/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_bloodlust.cpp"
SKILL = "Bloodlust"
RUNES = ["Heroism", "Ancestral Fury", "Thirst for Battle", "Elemental Fervor", "Primal Rage"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "shaman_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in HEADERS}
    if mutate:
        old, new = mutate
        key = HEADER[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = RUNES + [value("Thirst for Battle", "duration_seconds", "extend"), value("Thirst for Battle", "duration_seconds", "cap")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 9, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Heroism")\n            return Rune::Heroism;', 'if (name == "Heroism")\n            return Rune::PrimalRage;')),
            ("Heroism adds the damage bonus", ("case Rune::Heroism:\n                return Adds::DamageReduction;", "case Rune::Heroism:\n                return Adds::DamageBonus;")),
            ("Primal Rage adds nothing", ("case Rune::PrimalRage:\n                return Adds::CooldownReduction;", "case Rune::PrimalRage:\n                return Adds::Nothing;")),
            ("Elemental Fervor adds cooldown reduction", ("case Rune::ElementalFervor:\n                return Adds::MaelstromGeneration;", "case Rune::ElementalFervor:\n                return Adds::CooldownReduction;")),
            ("every rune extends on a kill", ("if (rune != Rune::ThirstForBattle || extendSeconds <= 0 || capSeconds <= 0)", "if (extendSeconds <= 0 || capSeconds <= 0)")),
            ("a kill never extends", ("if (rune != Rune::ThirstForBattle || extendSeconds <= 0 || capSeconds <= 0)", "if (true)")),
            ("the extension passes the cap", ("return extendedMs >= cap ? 0 : std::min(step, cap - extendedMs);", "return step;")),
            ("the extension stops a step early", ("return extendedMs >= cap ? 0 : std::min(step, cap - extendedMs);", "return extendedMs + step > cap ? 0 : step;")),
            ("the extension stops at the cap too soon", ("return extendedMs >= cap ? 0 : std::min(step, cap - extendedMs);", "return extendedMs + 1 >= cap ? 0 : std::min(step, cap - extendedMs);")),
            ("the buff holds a millisecond long", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
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
    def test_the_five_runes(self):
        self.assertEqual(runes(), RUNES)

    def test_bloodlust_deals_no_damage_so_no_hit_loads(self):
        rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
        self.assertFalse([r for r in rows if r["token"] == "damage_pct"])
        # Its seconds are the buff's: DamageWaits reads them as a damage that waits, and nothing here is damage.
        self.assertTrue([r for r in rows if r["token"] == "duration_seconds"])

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|found->second\.spellId|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 7, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "radius_yards"), value("", "attack_speed_pct"), value("", "movement_speed_pct"),
                          value("", "duration_seconds"), value("Heroism", "damage_reduction_pct"), value("Ancestral Fury", "damage_bonus_pct"),
                          value("Thirst for Battle", "duration_seconds", "extend"), value("Thirst for Battle", "duration_seconds", "cap"),
                          value("Elemental Fervor", "regen_pct"), value("Primal Rage", "cooldown_reduction_pct")],
                         [120, 50, 25, 15, 15, 15, 15, 0.5, 10, 50, 25])

    def test_the_cast_reaches_the_allies_within_50_yards(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        row = rows[SKILL]
        self.assertEqual((row["target_type"], row["range_yards"], row["radius_yards"]), ("self_allies", "SELF", "50"))
        self.assertEqual(float(row["radius_yards"]), value("", "radius_yards"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_cast_and_registers_the_script(self):
        self.assertIn("ElementalBlast::Cast(player, spellId); Bloodlust::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("new UpkeepScript(); Bloodlust::RegisterScripts();", self.dispatch)

    def test_the_caster_and_every_ally_in_reach_get_the_buff_for_the_skills_seconds(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void RegisterScripts(")]
        self.assertIn('Combat::ModifiedDurationSeconds(player, spellId, Numbers::Num(BaseId(), "duration_seconds"))', cast)
        self.assertIn("Grant(player, spellId, seconds);", cast)
        self.assertIn("if (Player* ally = unit ? unit->ToPlayer() : nullptr; ally && ally != player) Grant(ally, spellId, seconds);", cast)

    def test_a_second_cast_replaces_the_buff_and_never_stacks(self):
        grant = self.code[self.code.index("void Grant("):self.code.index("class KillScript")]
        self.assertIn("Buff& buff = buffs[key];", grant)
        self.assertIn("stamp = buff.stamp = ++stamps;", grant)
        self.assertIn("buff.extended = 0;", grant)
        put = self.code[self.code.index("void Put("):self.code.index("void Over(Player* player, std::uint64_t key, std::uint64_t stamp);")]
        self.assertIn("Strip(guid);", put)
        self.assertNotIn("Sated", self.code)

    def test_each_runes_number_goes_on_the_sheet(self):
        put = self.code[self.code.index("void Put("):self.code.index("void Over(Player* player, std::uint64_t key, std::uint64_t stamp);")]
        self.assertIn('{Source::Temporary, Stat::AttackSpeed, id, Numbers::Num(spellId, "attack_speed_pct"), Bucket::Flat}', put)
        self.assertIn('{Source::Temporary, Stat::MovementSpeed, id, Numbers::Num(spellId, "movement_speed_pct"), Bucket::Flat}', put)
        self.assertIn('{Source::Temporary, Stat::SpecificReduction, id, Numbers::Num(spellId, "damage_reduction_pct"), Bucket::Flat}', put)
        self.assertIn('Numbers::Num(spellId, "damage_bonus_pct"), Bucket::Flat, static_cast<DC::Element>(element)}', put)
        self.assertIn('{Source::Temporary, Stat::MaelstromGeneration, id, Numbers::Num(spellId, "regen_pct"), Bucket::Flat}', put)
        self.assertIn('{Source::Temporary, Stat::CooldownReduction, id, Numbers::Num(spellId, "cooldown_reduction_pct"), Bucket::Flat}', put)

    def test_the_end_waits_for_a_buff_a_kill_extended(self):
        over = self.code[self.code.index("void Over(Player* player, std::uint64_t key, std::uint64_t stamp) {"):self.code.index("void Grant(")]
        self.assertIn("if (found == buffs.end() || found->second.stamp != stamp) return;", over)
        self.assertIn("over = !Holds(Now(), until);", over)
        self.assertIn("if (!over) { Watch(player, key, stamp, until); return; }", over)
        self.assertIn("Strip(key);", over)

    def test_a_kill_extends_the_buff_by_the_runes_step_and_cap(self):
        kill = self.code[self.code.index("void OnPlayerCreatureKill("):self.code.index("void OnPlayerLogout(")]
        self.assertIn('Numbers::Num(found->second.spellId, "duration_seconds", "extend")', kill)
        self.assertIn('Numbers::Num(found->second.spellId, "duration_seconds", "cap")', kill)
        self.assertIn("found->second.extended += more; found->second.until += more;", kill)
        self.assertIn("!Holds(Now(), found->second.until)", kill)


if __name__ == "__main__":
    unittest.main()
