"""Command Skeletons and its five runes (src/classes/necromancer/dc_necromancer_command_skeletons*.{h,cpp}, the skeleton in
dc_necromancer_pets.cpp, the commanded rate in combat/dc_minions*).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_command_skeletons/harness.cpp compiles the real
    dc_necromancer_command_skeletons_math.h with the sheet's rune names and Dark Mending's heal: each name is its rune; only Kill
    Command's blows use the skill's record; a blow heals only at the commanded target. Planted mutations must each turn it
    red. The commanded rate (Frenzy) is proved in test_minions.py.
  * **The numbers.** Every number the cast reads is a row of necromancer_skill_values.csv from the tooltip (the sheet's test):
    the freeze 3 s, the explosion 215% within 15 yards, Dark Mending 0.5% per hit, Frenzy 25%; the power file
    (decode_pow.py power P6_Necro_CommandSkeletons) agrees on them (SF_19 0.005, SF_21 3, SF_22 2.15, SF_23 15, SF_24 0.25) and gives
    the order no duration (SF_9 0). No tunable is added.
  * **It is wired.** The dispatch answers BasePct and Cast; the skeleton kind reads its runes; the keeper sends the skeletons
    away when the rune on the bar changes.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_command_skeletons.py
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
HEADER = "src/classes/necromancer/dc_necromancer_command_skeletons_math.h"
HARNESS = MODULE / "tests/necromancer_command_skeletons/harness.cpp"
CODE = FOLDER / "dc_necromancer_command_skeletons.cpp"
PETS = FOLDER / "dc_necromancer_pets.cpp"
SKILL = "Command Skeletons"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, "")]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "necromancer_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


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
    return harness_env.run([str(binary)] + runes() + [str(value("Dark Mending", "heal_pct"))], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 10, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::Frenzy;\n        return Rune::None;', 'return Rune::KillCommand;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Enforcer")\n            return Rune::Enforcer;', 'if (name == "Enforcers")\n            return Rune::Enforcer;')),
            ("every rune strikes as the skill", ("return rune == Rune::KillCommand;", "return rune != Rune::None;")),
            ("Kill Command strikes as its own record", ("return rune == Rune::KillCommand;", "return false;")),
            ("a blow at another target heals", ("return commanded && maxLife > 0 && healPct > 0 ?", "return maxLife > 0 && healPct > 0 ?")),
            ("the heal is not a percent", ("maxLife * healPct / 100.0 : 0.0", "maxLife * healPct : 0.0")),
            ("no Life still heals", ("commanded && maxLife > 0 && healPct > 0", "commanded && healPct > 0")),
            ("a negative percent drains", ("commanded && maxLife > 0 && healPct > 0", "commanded && maxLife > 0")),
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
        self.assertEqual(runes(), ["Enforcer", "Dark Mending", "Freezing Grasp", "Kill Command", "Frenzy"])

    def test_the_numbers_the_code_reads_are_the_power_files(self):
        self.assertEqual(value("", "cost_resource"), 50)
        self.assertEqual(value("Enforcer", "cost_resource"), 25)  # SF_18
        self.assertEqual(value("Dark Mending", "heal_pct"), 0.5)  # SF_19 0.005
        self.assertEqual(value("Freezing Grasp", "freeze_duration_seconds"), 3)  # SF_21
        self.assertEqual([value("Kill Command", t) for t in ("damage_pct", "radius_yards")], [215, 15])  # SF_22, SF_23
        self.assertEqual(value("Frenzy", "attack_speed_pct"), 25)  # SF_24
        self.assertEqual([value("", t) for t in ("damage_bonus_pct", "interval_seconds", "max_count", "damage_pct")], [50, 2, 7, 50])

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"damage_pct", "radius_yards", "freeze_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("Dark Mending", "heal_pct"), ("Freezing Grasp", "freeze_duration_seconds"),
                            ("Kill Command", "damage_pct"), ("Kill Command", "radius_yards"), ("Frenzy", "attack_speed_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.pets = squeeze(PETS.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_base_hit_and_the_cast(self):
        self.assertIn("if (auto skeletons = CommandSkeletons::BasePct(spellId)) return skeletons;", self.dispatch)
        self.assertIn("CommandSkeletons::Cast(player, spellId, targets);", self.dispatch)

    def test_the_active_has_no_hit_of_its_own(self):
        self.assertIn("return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_order_has_no_time_but_the_targets_life(self):
        self.assertIn("UntilTheTargetDies = std::numeric_limits<std::uint32_t>::max() / 2;", self.code)
        self.assertIn("Pets::CommandSkeletons(player, target, UntilTheTargetDies);", self.code)

    def test_freezing_grasp_stuns_the_target_stretched_by_the_worn_powers(self):
        self.assertIn('if (rune == Rune::FreezingGrasp) Stun(player, target, Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));', self.code)

    def test_kill_command_explodes_each_skeleton_on_the_enemies_around_the_target_and_spends_them(self):
        self.assertIn("unsigned const skeletons = Minions::Alive(player, \"skeleton\");", self.code)
        self.assertIn("Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, \"radius_yards\"))", self.code)
        self.assertIn("for (unsigned i = 0; i < skeletons; ++i) for (Unit* enemy : enemies)", self.code)
        self.assertIn('Minions::Dismiss(player, "skeleton");', self.code)
        # Kill Command orders nothing: the skeletons go instead.
        self.assertLess(self.code.index("Explode(player, spellId, target); return; }"), self.code.index("Pets::CommandSkeletons("))

    def test_the_skeleton_reads_its_runes(self):
        skeleton = self.pets[self.pets.index("Minions::Kind Skeleton("):self.pets.index("// Command Golem:")]
        self.assertIn("CommandSkeletons::BlowsUseSkillRecord(rune) ? BaseId(SkeletonSkill) : slotted;", skeleton)
        self.assertIn('kind.commandSpeedPct = Numbers::Num(slotted, "attack_speed_pct");', skeleton)
        self.assertIn("Minions::IsOrdered(player, \"skeleton\", enemy)", skeleton)
        self.assertIn('Numbers::Num(slotted, "heal_pct")', skeleton)
        self.assertIn("Heal(player, slotted,", skeleton)

    def test_a_changed_rune_sends_the_skeletons_away(self):
        self.assertIn("changed = held && held != record;", self.pets)
        self.assertIn('if (changed) Minions::Dismiss(player, "skeleton");', self.pets)
        self.assertIn("heldAs.erase(player->GetGUID().GetRawValue());", self.pets)


if __name__ == "__main__":
    unittest.main()
