"""Land of the Dead and its five runes (src/classes/necromancer/dc_necromancer_land_of_the_dead*.{h,cpp}; the corpses used at will
are the shared combat/dc_corpses*, proved in test_corpses.py).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_land_of_the_dead/harness.cpp compiles the real
    dc_necromancer_land_of_the_dead_math.h with the sheet's rune names and numbers: each name is its rune; Shallow Graves extends on every
    tenth kill by a second and never past the most; Plaguelands never takes an enemy past its maximum; a kill heals its share of the
    Life. Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_LandOfTheDead:
    SF_0 10, SF_1 120, SF_2 0.02, SF_3 10, SF_4 2, SF_5 1, SF_11 1.0); the rest are tunables with their SF cited.
  * **It is wired.** The dispatch answers BasePct, Cast and RegisterScripts; the cast opens the window of the shared corpses and each
    rune's part.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_land_of_the_dead.py
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
FOLDER = MODULE / "src/classes/necromancer"
HEADER = "src/classes/necromancer/dc_necromancer_land_of_the_dead_math.h"
HARNESS = MODULE / "tests/necromancer_land_of_the_dead/harness.cpp"
CODE = FOLDER / "dc_necromancer_land_of_the_dead.cpp"
SKILL = "Land of the Dead"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "necromancer_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


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


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Shallow Graves", "trigger_count"), value("Shallow Graves", "duration_seconds", "extension"),
               value("Shallow Graves", "duration_seconds", "maximum"), value("Plaguelands", "damage_pct", "per_second"),
               value("Plaguelands", "damage_pct", "maximum"), value("Land of Plenty", "heal_pct")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 16, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::ShallowGraves;\n        return Rune::None;', 'return Rune::LandOfPlenty;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Plaguelands")', 'if (name == "Plaguelandss")')),
            ("every kill extends", ("return triggerCount > 0 && kills > 0 && kills % triggerCount == 0;", "return triggerCount > 0 && kills > 0;")),
            ("the nth kill does not extend", ("kills % triggerCount == 0", "kills % triggerCount == 1")),
            ("no trigger count extends", ("return triggerCount > 0 && kills > 0 &&", "return kills > 0 &&")),
            ("an extension has no most", ("std::min(step, most - extendedSoFar)", "step")),
            ("an extension past the most is negative", ("std::max(0.0, std::min(step, most - extendedSoFar))", "std::min(step, most - extendedSoFar)")),
            ("the last extension is a whole step", ("std::min(step, most - extendedSoFar)", "(most - extendedSoFar > 0 ? step : 0.0)")),
            ("a plague tick has no maximum", ("std::min(tickPct, maxPct - dealtPct)", "tickPct")),
            ("a plague tick past the maximum is negative", ("std::max(0.0, std::min(tickPct, maxPct - dealtPct))", "std::min(tickPct, maxPct - dealtPct)")),
            ("the last plague tick is a whole one", ("std::min(tickPct, maxPct - dealtPct)", "(maxPct - dealtPct > 0 ? tickPct : 0.0)")),
            ("a kill heals the whole Life", ("maxLife * healPct / 100.0 : 0.0", "maxLife : 0.0")),
            ("the heal is not a percent", ("maxLife * healPct / 100.0 : 0.0", "maxLife * healPct : 0.0")),
            ("a negative percent drains", ("maxLife > 0 && healPct > 0 ?", "maxLife > 0 ?")),
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
        self.assertEqual(runes(), ["Invigoration", "Frozen Lands", "Plaguelands", "Land of Plenty", "Shallow Graves"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "duration_seconds")], [120, 10])  # SF_1, SF_0
        self.assertEqual([value("Plaguelands", "damage_pct", q) for q in ("per_second", "maximum")], [100, 10000])  # SF_11 1.0
        self.assertEqual(value("Land of Plenty", "heal_pct"), 2)  # SF_2 0.02
        self.assertEqual([value("Shallow Graves", "trigger_count"), value("Shallow Graves", "duration_seconds", "extension"),
                          value("Shallow Graves", "duration_seconds", "maximum")], [10, 1, 2])  # SF_3, SF_5, SF_4

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"damage_pct", "heal_pct", "trigger_count", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token, qualifier in (("", "duration_seconds", ""), ("Plaguelands", "damage_pct", "per_second"),
                                       ("Plaguelands", "damage_pct", "maximum"), ("Land of Plenty", "heal_pct", ""),
                                       ("Shallow Graves", "trigger_count", ""), ("Shallow Graves", "duration_seconds", "extension"),
                                       ("Shallow Graves", "duration_seconds", "maximum")):
            with self.subTest(rune=rune, token=token, qualifier=qualifier):
                self.assertIn((rune, token, qualifier), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "land_of_the_dead_corpses": "10",       # P6_Necro_RaiseGolem SF_38 = SF_27
        "frozen_lands_period_seconds": "2",     # SF_6
        "frozen_lands_radius_yards": "60",      # SF_7
        "frozen_lands_freeze_seconds": "10",    # SF_8
        "plaguelands_radius_yards": "60",       # SF_9
        "plaguelands_targets": "10",            # SF_10
        "plaguelands_interval_seconds": "1",    # SF_12
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_LandOfTheDead", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto land = LandOfTheDead::BasePct(spellId)) return land;", self.dispatch)
        self.assertIn("LandOfTheDead::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("LandOfTheDead::RegisterScripts();", self.dispatch)

    def test_the_cast_opens_the_window_of_the_shared_corpses_for_the_duration(self):
        self.assertIn('double const seconds = Numbers::Num(spellId, "duration_seconds");', self.code)
        self.assertIn("Corpses::AtWill(player, until, Phantoms());", self.code)
        self.assertIn('return std::size_t(std::max(0.0, Tune("land_of_the_dead_corpses")));', self.code)

    def test_invigoration_opens_a_window_of_free_abilities_for_the_duration(self):
        self.assertIn("case Rune::Invigoration:", self.code)
        self.assertIn("ItemPowers::FreeAbilities(player, seconds);", self.code)

    def test_frozen_lands_freezes_with_the_worn_powers_every_period_while_the_land_is_open(self):
        self.assertIn('Stun(player, enemy, Tune("frozen_lands_freeze_seconds") * ItemPowers::StunFactor(player));', self.code)
        self.assertIn('std::chrono::milliseconds(Millis(Tune("frozen_lands_period_seconds"))));', self.code)
        self.assertIn("!Open(player->GetGUID().GetRawValue(), stamp, land)", self.code)

    def test_plaguelands_strikes_the_nearest_enemies_none_past_the_maximum(self):
        self.assertIn('enemies.resize(std::size_t(Tune("plaguelands_targets")));', self.code)
        self.assertIn('Numbers::Num(land.spellId, "damage_pct", "per_second")', self.code)
        self.assertIn('Numbers::Num(land.spellId, "damage_pct", "maximum")', self.code)
        self.assertIn("pct = PlagueTick(dealt, tick, most);", self.code)

    def test_a_kill_heals_for_land_of_plenty_and_counts_for_shallow_graves_which_extends_the_window(self):
        self.assertIn('Heal(player, land.spellId, KillHeal(player->GetMaxHealth(), Numbers::Num(land.spellId, "heal_pct")));', self.code)
        self.assertIn('ExtendsOn(held.kills, unsigned(Numbers::Num(held.spellId, "trigger_count")))', self.code)
        self.assertIn('Numbers::Num(held.spellId, "duration_seconds", "extension")', self.code)
        self.assertIn('Numbers::Num(held.spellId, "duration_seconds", "maximum")', self.code)
        self.assertIn("Corpses::AtWill(player, until, Phantoms());", self.code)

    def test_a_new_cast_takes_a_new_stamp_so_an_old_land_stops(self):
        self.assertIn("stamp = ++stamps;", self.code)
        self.assertIn("(stamp && found->second.stamp != stamp)", self.code)


if __name__ == "__main__":
    unittest.main()
