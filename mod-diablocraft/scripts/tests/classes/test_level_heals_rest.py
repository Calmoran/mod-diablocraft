"""The rest of the heals D3 builds from its Healing table scale with the caster's level (diablocraft-75e41, after l4ccq's
test_level_heals.py): the Barbarian's Bloodthirst, Battle Rage, Call of the Ancients, Ignore Pain, Wrath of the Berserker and War
Cry; the Crusader's Smite, Sweep Attack, Consecration, Judgment, Provoke, the Laws of Valor, Justice and Hope and the passives Vigilant,
Indestructible, Wrathful and Renewal; the Monk's Cyclone Strike, Epiphany, Transcendence, Mantra of Healing, Inner Sanctuary and Mystic
Ally (src/classes/dc_level_heal.h over src/combat/dc_healing_table.h). The Witch Doctor's (Hex, Haunt, Soul Harvest) and the Demon
Hunter's and Necromancer's are built elsewhere (Spirit Barrage's Phlebotomize in vxrcu.24, Shadow Power, Leech) or not built yet.

What this proves, and how:

  * **The sheets are the file's coefficient at the top level.** Each number the sheets hold for these heals is the power file's
    coefficient times the table's last row, rounded; with the game archives on this machine the coefficient is read back from the decoded
    power file (the file's own formula, '/ 2' and '/ 4' included).
  * **The heal at a level is the file's.** tests/level_heal/harness.cpp (l4ccq's) compiles the real dc_level_heal.h over the real table and,
    for every one of these numbers at levels 5, 35 and 70, the heal is within a whole point of the file's coefficient times the table
    there; at 70 it is the sheet's number itself.
  * **The wiring.** Every place the code reads one of these tokens in the files that heal with them scales it by the caster's level
    first, and no other reader of them is left unscaled.

What it does not prove: the numbers in game, or the tooltips (which keep the level-70 numbers the sheets hold).

    python mod-diablocraft/scripts/tests/classes/test_level_heals_rest.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import decode_pow
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/dc_level_heal.h"
TABLE = "src/combat/dc_healing_table.h"
HARNESS = MODULE / "tests/level_heal/harness.cpp"
LEVELS = (5, 35, 70)

B, C, M = "barbarian", "crusader", "monk"
# (label, sheet, skill, rune, token, power file, the file's SF, the coefficient the sheet holds, the number to multiply the file's own coefficient of that SF by to get the sheet's)
# Sustenance doubles Mantra of Healing's heal a second (0.04 against the file's 0.02): its factor is 2.
VALUES = [
    ("Bloodthirst", B + "_passive_values.csv", "Bloodthirst", "", "heal_life", "Barbarian_Passive_Bloodthirst", 0, 0.0018, 1),
    ("Battle Rage - Swords to Ploughshares", B + "_skill_values.csv", "Battle Rage", "Swords to Ploughshares", "heal_life", "Barbarian_BattleRage", 6, 0.04, 1),
    ("Call of the Ancients - Ancients' Blessing", B + "_skill_values.csv", "Call of the Ancients", "Ancients' Blessing", "heal_life", "Barbarian_CallOfTheAncients", 21, 0.0018, 1),
    ("Ignore Pain - Ignorance is Bliss", B + "_skill_values.csv", "Ignore Pain", "Ignorance is Bliss", "heal_per_hit_life", "Barbarian_IgnorePain", 1, 0.01, 1),
    ("Wrath of the Berserker - Thrive on Chaos", B + "_skill_values.csv", "Wrath of the Berserker", "Thrive on Chaos", "heal_per_hit_life", "Barbarian_WrathOfTheBerserker", 21, 0.01, 1),
    ("War Cry - Invigorate", B + "_skill_values.csv", "War Cry", "Invigorate", "heal_per_second_life", "X1_Barbarian_WarCry_v2", 6, 0.025, 1),
    ("Smite - Reaping", C + "_skill_values.csv", "Smite", "Reaping", "heal_per_second_life", "X1_Crusader_Smite", 15, 0.012, 1),
    ("Sweep Attack - Holy Shock", C + "_skill_values.csv", "Sweep Attack", "Holy Shock", "heal_per_hit_life", "X1_Crusader_SweepAttack", 14, 0.01, 1),
    ("Consecration", C + "_skill_values.csv", "Consecration", "", "heal_per_second_life", "X1_Crusader_Consecration", 7, 0.06, 1),
    ("Consecration - Bathed in Light", C + "_skill_values.csv", "Consecration", "Bathed in Light", "heal_per_second_life", "X1_Crusader_Consecration", 23, 0.09, 1),
    ("Judgment - Penitence", C + "_skill_values.csv", "Judgment", "Penitence", "heal_per_second_life", "X1_Crusader_Judgment", 3, 0.005, 1),
    ("Provoke - Cleanse", C + "_skill_values.csv", "Provoke", "Cleanse", "heal_per_hit_life", "X1_Crusader_Provoke", 13, 0.002, 1),
    ("Laws of Valor - Invincible", C + "_skill_values.csv", "Laws of Valor", "Invincible", "heal_per_hit_life", "X1_Crusader_LawsOfValor_Passive2", 7, 0.04, 1),
    ("Laws of Justice - Faith's Armor", C + "_skill_values.csv", "Laws of Justice", "Faith's Armor", "absorb_life", "X1_Crusader_LawsOfJustice_Passive2", 6, 0.05, 1),
    ("Laws of Hope absorb", C + "_skill_values.csv", "Laws of Hope", "", "absorb_life", "X1_Crusader_LawsOfHope_Passive2", 7, 0.2314, 1),
    ("Laws of Hope heal", C + "_skill_values.csv", "Laws of Hope", "", "heal_per_second_life", "X1_Crusader_LawsOfHope_Passive2", 2, 0.02, 1),
    ("Laws of Hope - Faith's Reward", C + "_skill_values.csv", "Laws of Hope", "Faith's Reward", "heal_per_hit_life", "X1_Crusader_LawsOfHope2", 16, 0.002, 1),
    ("Vigilant", C + "_passive_values.csv", "Vigilant", "", "heal_per_second_life", "X1_Crusader_Passive_Vigilant", 1, 0.005, 1),
    ("Indestructible", C + "_passive_values.csv", "Indestructible", "", "heal_per_hit_life", "X1_Crusader_Passive_Indestructible", 1, 0.2, 1),
    ("Wrathful", C + "_passive_values.csv", "Wrathful", "", "heal_per_hit_life", "X1_Crusader_Passive_Wrathful", 0, 0.0025, 1),
    ("Renewal", C + "_passive_values.csv", "Renewal", "", "heal_life", "X1_Crusader_Passive_Renewal", 0, 0.03, 1),
    ("Cyclone Strike - Soothing Breeze", M + "_skill_values.csv", "Cyclone Strike", "Soothing Breeze", "heal_life", "Monk_CycloneStrike", 20, 0.057857, 1),
    ("Epiphany - Soothing Mist", M + "_skill_values.csv", "Epiphany", "Soothing Mist", "heal_life", "X1_Monk_Epiphany", 47, 0.03, 1),
    ("Transcendence", M + "_passive_values.csv", "Transcendence", "", "heal_per_hit_life", "Monk_Passive_Transcendence", 0, 0.0008, 1),
    ("Mantra of Healing absorb", M + "_skill_values.csv", "Mantra of Healing", "", "absorb_life", "X1_Monk_MantraOfHealing_v2", 5, 0.1157, 1),
    ("Mantra of Healing heal", M + "_skill_values.csv", "Mantra of Healing", "", "heal_per_second_life", "X1_Monk_MantraOfHealing_v2", 10, 0.02, 1),
    ("Mantra of Healing - Sustenance", M + "_skill_values.csv", "Mantra of Healing", "Sustenance", "heal_per_second_life", "X1_Monk_MantraOfHealing_v2", 10, 0.04, 2),
    ("Mantra of Healing - Boon of Inspiration", M + "_skill_values.csv", "Mantra of Healing", "Boon of Inspiration", "heal_per_hit_life", "X1_Monk_MantraOfHealing_v2", 9, 0.006667, 1),
    ("Inner Sanctuary - Intervene", M + "_skill_values.csv", "Inner Sanctuary", "Intervene", "absorb_life", "X1_Monk_InnerSanctuary", 12, 0.2, 1),
    ("Inner Sanctuary - Safe Haven", M + "_skill_values.csv", "Inner Sanctuary", "Safe Haven", "heal_per_second_life", "X1_Monk_InnerSanctuary", 25, 0.0667, 1),
    ("Mystic Ally - Enduring Ally", M + "_skill_values.csv", "Mystic Ally", "Enduring Ally", "heal_per_second_life", "X1_Monk_MysticAlly_v2", 7, 0.02, 1),
]

# The files that heal with these tokens: every read of one is scaled by the caster's level.
FILES = {
    "barbarian/dc_barbarian_passives.cpp", "barbarian/dc_barbarian_battle_rage.cpp", "barbarian/dc_barbarian_call_of_the_ancients.cpp",
    "barbarian/dc_barbarian_ignore_pain.cpp", "barbarian/dc_barbarian_wrath_of_the_berserker.cpp", "barbarian/dc_barbarian_war_cry.cpp",
    "crusader/dc_crusader_smite.cpp", "crusader/dc_crusader_sweep_attack.cpp", "crusader/dc_crusader_consecration.cpp",
    "crusader/dc_crusader_judgment.cpp", "crusader/dc_crusader_provoke.cpp", "crusader/dc_crusader_laws_of_valor.cpp",
    "crusader/dc_crusader_laws_of_justice.cpp", "crusader/dc_crusader_laws_of_hope.cpp", "crusader/dc_crusader_passives.cpp",
    "monk/dc_monk_cyclone_strike.cpp", "monk/dc_monk_epiphany.cpp", "monk/dc_monk_mantras.cpp", "monk/dc_monk_inner_sanctuary.cpp",
    "monk/dc_monk_mystic_ally.cpp", "monk/dc_monk_passives.cpp",
}
TOKENS = ("heal_life", "heal_per_hit_life", "heal_per_second_life", "absorb_life")


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def healing(level):
    return float(next(r for r in read(D3 / "healing_table.csv") if int(r["level"]) == level)["value"])


def sheet_value(sheet, skill, rune, token):
    rows = [r for r in read(D3 / sheet) if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, "")]
    assert len(rows) == 1, (skill, rune, token, len(rows))
    return float(rows[0]["value"])


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (HEADER, TABLE)}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = []
    for _label, sheet, skill, rune, token, _power, _sf, coefficient, _factor in VALUES:
        for level in LEVELS:
            numbers += [sheet_value(sheet, skill, rune, token), level, coefficient * healing(level)]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


def formula(text):
    """The coefficient of a power file's 'k * Table(Healing, ...)' term, the file's own '/ 2' and '/ 4' and parentheses included."""
    reduced = re.sub(r"Table\(Healing,\s*(?:Effective_)?Level\)", "1", text.replace(" ", ""))
    assert re.fullmatch(r"[0-9.*/()+]+", reduced), text
    return eval(reduced)  # noqa: S307  (digits and the four operators only, checked above)


class Sheets(unittest.TestCase):
    def test_each_number_is_the_files_coefficient_at_the_top_level(self):
        for label, sheet, skill, rune, token, _power, _sf, coefficient, _factor in VALUES:
            with self.subTest(label):
                self.assertEqual(round(coefficient * healing(70)), sheet_value(sheet, skill, rune, token))

    @unittest.skipUnless(decode_pow.available(), "needs reference/blizzless-diiis and smpq")
    def test_the_coefficients_are_the_decoded_power_files(self):
        for label, _sheet, _skill, _rune, _token, power, number, coefficient, factor in VALUES:
            with self.subTest(label):
                parsed = decode_pow.parse_power(decode_pow.extract(f"Power/{power}.pow"))
                self.assertAlmostEqual(formula(parsed["sf"][number]) * factor, coefficient, places=6)


class Harness(unittest.TestCase):
    def test_the_heal_at_a_level_is_the_files(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, len(VALUES) * len(LEVELS) * 2, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the level is ignored", (HEADER, "atTopLevel * Combat::Healing::At(level) / TopLevelHealing()", "atTopLevel * Combat::Healing::At(70) / TopLevelHealing()")),
            ("the table is not divided by the top level", (HEADER, "atTopLevel * Combat::Healing::At(level) / TopLevelHealing()", "atTopLevel * Combat::Healing::At(level)")),
            ("a level-up rebuilds nothing", (HEADER, "return builtAt != level;", "return builtAt == 0;")),
            ("the heal does not grow", (HEADER, "atTopLevel * Combat::Healing::At(level) / TopLevelHealing()", "atTopLevel * (level < 36 ? Combat::Healing::At(35) : Combat::Healing::At(level)) / TopLevelHealing()")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Wiring(unittest.TestCase):
    def test_every_read_of_these_numbers_is_scaled_by_the_casters_level(self):
        reads = 0
        for path in sorted(FILES):
            text = (MODULE / "src/classes" / path).read_text(encoding="utf-8")
            self.assertIn('#include "../dc_level_heal.h"', text, path)
            flat = re.sub(r"\s+", " ", text)
            for found in re.finditer(r'(?:Combat::)?Numbers::Num\(|(?<![\w:])Num\(', flat):
                depth, end = 1, found.end()
                while depth:
                    depth += (flat[end] == "(") - (flat[end] == ")")
                    end += 1
                call = flat[found.start():end]
                token = re.search(r'"(%s)"' % "|".join(TOKENS), call)
                if not token:
                    continue
                reads += 1
                self.assertTrue(flat[:found.start()].rstrip().endswith("HealAtLevel("), f"{path}: {call} is not scaled by the level")
        # One for each place the code reads one of the numbers (Battle Rage's three and Call of the Ancients' two among them).
        self.assertGreaterEqual(reads, 30)

    def test_each_scaling_names_the_caster(self):
        for path in sorted(FILES):
            flat = re.sub(r"\s+", " ", (MODULE / "src/classes" / path).read_text(encoding="utf-8"))
            for found in re.finditer(r"Classes::HealAtLevel\(", flat):
                depth, i = 1, found.end()
                while depth:
                    depth += (flat[i] == "(") - (flat[i] == ")")
                    i += 1
                self.assertRegex(flat[found.start():i], r", (p|player|owner|killer)->GetLevel\(\)\)$", f"{path}: {flat[found.start():i]}")

    def test_a_standing_contribution_is_rebuilt_when_the_level_changes(self):
        # Vigilant's and Enduring Ally's regeneration sit on the stat sheet and are rebuilt only when something else changes (the Crusader's
        # passive bits, Block Chance and gems; the ally in play), so they must also remember the level they were built at and rebuild when
        # it is not the caster's (the Reviewer's return of 75e41, lzmil). Each file asks the one rule.
        passives = re.sub(r"\s+", " ", (MODULE / "src/classes/crusader/dc_crusader_passives.cpp").read_text(encoding="utf-8"))
        self.assertIn("unsigned level = 0;", passives[passives.index("struct State"):passives.index("std::mutex mutex;")])
        update = passives[passives.index("void OnPlayerUpdate("):passives.index("void OnPlayerLogout(")]
        self.assertIn("unsigned const level = player->GetLevel();", update)
        self.assertIn("refresh = state.dirty || state.signature != wanted || state.blockCenti != blockCenti || state.gems != gems || Classes::BuiltAtOtherLevel(state.level, level);", update)
        self.assertIn("state.level = level;", update)
        self.assertLess(update.index("Classes::BuiltAtOtherLevel(state.level, level)"), update.index("state.level = level;"))
        refresh = passives[passives.index("void Refresh("):passives.index("class Update")] if "class Update" in passives else passives[passives.index("void Refresh("):]
        self.assertIn('Classes::HealAtLevel(Numbers::Num(vigilant, "heal_per_second_life"), player->GetLevel())', refresh)
        ally = re.sub(r"\s+", " ", (MODULE / "src/classes/monk/dc_monk_mystic_ally.cpp").read_text(encoding="utf-8"))
        self.assertIn("unsigned builtLevel = 0;", ally[ally.index("struct State"):ally.index("std::unordered_map<std::uint64_t, State> states;")])
        upkeep = ally[ally.index("void Upkeep("):ally.index("Resources::Flow(")]
        self.assertIn("applied == IdOf(\"Enduring Ally\") && Classes::BuiltAtOtherLevel(state.builtLevel, level)", upkeep)
        self.assertIn("state.builtLevel = level;", upkeep)
        self.assertIn("if (applied != previous || stale) Sheet(player, applied);", upkeep)
        self.assertLess(upkeep.index("state.builtLevel = level;"), upkeep.index("if (applied != previous || stale) Sheet(player, applied);"))
        # The rule is the shared header's one function.
        self.assertEqual(len(re.findall(r"inline bool BuiltAtOtherLevel\(", (MODULE / HEADER).read_text(encoding="utf-8"))), 1)

    def test_no_other_reader_of_the_tokens_is_left_unscaled(self):
        # The readers of these tokens in the class folders are the files above, l4ccq's four and the shared Laws/Mantra helpers that take
        # the number as a parameter.
        known = FILES | {"crusader/dc_crusader_punish.cpp", "crusader/dc_crusader_justice.cpp", "monk/dc_monk_serenity.cpp", "monk/dc_monk_breath_of_heaven.cpp"}
        found = set()
        for folder in ("barbarian", "crusader", "monk"):
            for path in (MODULE / "src/classes" / folder).glob("*.cpp"):
                text = path.read_text(encoding="utf-8")
                if any(f'"{token}"' in text for token in TOKENS):
                    found.add(f"{folder}/{path.name}")
        self.assertEqual(found - known, set(), "a file reads a heal token and is not scaled or listed here")


if __name__ == "__main__":
    unittest.main()
