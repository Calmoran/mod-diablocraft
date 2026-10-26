"""Command Golem and its five runes (src/classes/necromancer/dc_necromancer_command_golem*.{h,cpp}, the Golem in
dc_necromancer_pets.cpp, the boost and the hold in combat/dc_minions*).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_command_golem/harness.cpp compiles the real
    dc_necromancer_command_golem_math.h with the sheet's rune names and numbers: each name is its rune; the skill and Flesh Golem
    collapse; only the school-changing runes' records carry the Golem's blows; the tornado's trip, its pulses (which make the
    sheet's 2000% where it stops), the veins (150% and the 300% rip make the sheet's 450%) and the Decay Golem's corpse bonus.
    Planted mutations must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip; the extra numbers the power file gives are tunables with their SF cited
    (decode_pow.py power P6_Necro_RaiseGolem). The Bone Golem's stun is 2.5 s in the power and 2 in the tooltip, which rounds it: the
    power's own total (five pulses of 400% = the tooltip's 2000%) needs the 2.5.
  * **It is wired.** The dispatch answers BasePct, CanCast, Ground and CritBonus; each rune's part; the Golem's kind reads its rune;
    the keeper sends the Golem away when the rune on the bar changes.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_command_golem.py
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
HEADER = "src/classes/necromancer/dc_necromancer_command_golem_math.h"
HARNESS = MODULE / "tests/necromancer_command_golem/harness.cpp"
CODE = FOLDER / "dc_necromancer_command_golem.cpp"
PETS = FOLDER / "dc_necromancer_pets.cpp"
SKILL = "Command Golem"


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


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


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


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [tune("bone_golem_stun_seconds"), tune("bone_golem_dest_pulse_seconds"), tune("bone_golem_dest_pulse_pct"),
               value("Bone Golem", "damage_pct"), tune("blood_golem_vein_pct"), tune("blood_golem_rip_pct"),
               value("Blood Golem", "damage_pct"), value("Decay Golem", "damage_bonus_pct"), tune("decay_golem_max_corpses"),
               tune("blood_golem_knockback_yards"), tune("decay_golem_max_scale_pct")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::IceGolem;\n        return Rune::None;', 'return Rune::FleshGolem;\n        return Rune::None;')),
            ("Flesh Golem keeps its Golem", ("return rune == Rune::None || rune == Rune::FleshGolem;", "return rune == Rune::None;")),
            ("every rune collapses", ("return rune == Rune::None || rune == Rune::FleshGolem;", "return true;")),
            ("Decay Golem strikes as the skill", ("return rune == Rune::DecayGolem || rune == Rune::IceGolem;", "return rune == Rune::IceGolem;")),
            ("every rune's record carries the blows", ("return rune == Rune::DecayGolem || rune == Rune::IceGolem;", "return rune != Rune::None;")),
            ("the trip ignores the scalar", ("yards / (speed * scalar)", "yards / speed")),
            ("the trip is speed over yards", ("yards / (speed * scalar)", "(speed * scalar) / yards")),
            ("a trip with no speed is infinite", ("yards > 0 && speed > 0 && scalar > 0 ?", "yards > 0 && scalar > 0 ?")),
            ("a pulse is lost to rounding", ("std::floor(seconds / interval + 1e-9)", "std::floor(seconds / interval)")),
            ("a pulse too many", ("std::floor(seconds / interval + 1e-9)", "std::ceil(seconds / interval)")),
            ("the way is not held at the end", ("std::clamp(share, 0.0, 1.0)", "std::max(share, 0.0)")),
            ("the way starts from the far end", ("return a + (b - a) * std::clamp", "return b + (a - b) * std::clamp")),
            ("the veins strike together", ("return gapSeconds > 0 ? index * gapSeconds : 0.0;", "return 0.0;")),
            ("the first vein waits", ("return gapSeconds > 0 ? index * gapSeconds : 0.0;", "return gapSeconds > 0 ? (index + 1) * gapSeconds : 0.0;")),
            ("the meal has no most", ("std::min(corpses, most) * std::max(0.0, perCorpsePct)", "corpses * std::max(0.0, perCorpsePct)")),
            ("a negative percent drains", ("std::max(0.0, perCorpsePct)", "perCorpsePct")),
            ("a meal repeats the number", ("return last + 1;", "return last;")),
            ("an earlier meal's event gives the size back", ("return held != 0 && held == mine;", "return held != 0 && held >= mine;")),
            ("a later event is refused", ("return held != 0 && held == mine;", "return held != 0 && held > mine;")),
            ("nothing held still gives back", ("return held != 0 && held == mine;", "return held == mine;")),
            ("the knockback pulls in", ("distance < radius ? radius : distance", "distance < radius ? 0.0 : distance")),
            ("the knockback pushes the edge", ("distance < radius ? radius", "distance <= radius ? radius + 1.0")),
            ("the knockback pushes the far ones in", ("distance < radius ? radius : distance", "radius")),
            ("the growth has no most", ("maxPct * std::min(corpses, most) / most", "maxPct * corpses / most")),
            ("the growth is the whole at one corpse", ("maxPct * std::min(corpses, most) / most", "maxPct")),
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
        self.assertEqual(runes(), ["Bone Golem", "Blood Golem", "Decay Golem", "Flesh Golem", "Ice Golem"])

    def test_the_sheet_numbers(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "target_count", "damage_pct")], [45, 5, 450])
        self.assertEqual([value("Bone Golem", t) for t in ("stun_duration_seconds", "damage_pct")], [2, 2000])
        self.assertEqual([value("Blood Golem", t) for t in ("heal_pct", "damage_pct")], [25, 450])
        self.assertEqual(value("Decay Golem", "damage_bonus_pct"), 30)
        self.assertEqual(value("Flesh Golem", "target_count"), 8)
        self.assertEqual([value("Ice Golem", t) for t in ("freeze_duration_seconds", "crit_taken_pct", "duration_seconds")], [3, 10, 10])

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"target_count", "heal_pct", "damage_bonus_pct", "duration_seconds", "freeze_duration_seconds",
                                  "crit_taken_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "target_count"), ("Flesh Golem", "target_count"), ("Blood Golem", "heal_pct"),
                            ("Decay Golem", "damage_bonus_pct"), ("Ice Golem", "freeze_duration_seconds"),
                            ("Ice Golem", "crit_taken_pct"), ("Ice Golem", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {
        "bone_golem_stun_seconds": "2.5",           # SF_21
        "bone_golem_pulse_radius_yards": "13",      # SF_22
        "bone_golem_move_pulse_seconds": "0.3",     # SF_18
        "bone_golem_move_pulse_pct": "50",          # SF_19
        "bone_golem_move_speed_scalar": "1.92",     # SF_23
        "bone_golem_dest_pulse_pct": "400",         # SF_24
        "bone_golem_dest_pulse_seconds": "0.5",     # SF_39
        "blood_golem_heal_delay_seconds": "0.5",    # SF_9
        "blood_golem_vein_pct": "150",              # SF_1
        "blood_golem_rip_pct": "300",               # SF_8
        "blood_golem_vein_radius_yards": "20",      # SF_12
        "blood_golem_vein_targets": "20",           # SF_10
        "blood_golem_vein_gap_seconds": "0.07",     # SF_3
        "blood_golem_vein_seconds": "1.5",          # SF_5
        "decay_golem_max_corpses": "10",            # SF_27
        "decay_golem_corpse_radius_yards": "25",    # SF_31
        "decay_golem_buff_seconds": "10",           # SF_30
        "ice_golem_radius_yards": "25",             # SF_36
        "blood_golem_knockback_yards": "7",         # SF_7
        "decay_golem_max_scale_pct": "10",          # SF_29
        "minion_golem_return_seconds": "10",        # SF_26 (the pets)
    }

    def test_the_rows_hold_the_power_files_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                if name != "minion_golem_return_seconds":
                    self.assertIn("decode_pow.py power P6_Necro_RaiseGolem", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), set(self.NUMBERS))

    def test_the_vein_and_the_rip_make_the_sheets_blood_total_and_the_pulses_the_bone_total(self):
        self.assertEqual(tune("blood_golem_vein_pct") + tune("blood_golem_rip_pct"), value("Blood Golem", "damage_pct"))
        self.assertEqual(int(tune("bone_golem_stun_seconds") / tune("bone_golem_dest_pulse_seconds")) * tune("bone_golem_dest_pulse_pct"),
                         value("Bone Golem", "damage_pct"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.pets = squeeze(PETS.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_four_seams(self):
        self.assertIn("if (auto golem = CommandGolem::BasePct(spellId)) return golem;", self.dispatch)
        self.assertIn("CommandGolem::CanCast(player, spellId, aim)", self.dispatch)
        self.assertIn("CommandGolem::Ground(player, spellId, center);", self.dispatch)
        self.assertIn("CorpseLance::CritBonus(player, target) + CommandGolem::CritBonus(player, target)", self.dispatch)

    def test_the_active_has_no_hit_of_its_own_and_needs_the_golem(self):
        self.assertIn("return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;", self.code)
        self.assertIn("return player && aim && Golem(player) ? SPELL_CAST_OK : SPELL_FAILED_NO_VALID_TARGETS;", self.code)

    def test_the_collapse_leaves_the_corpses_and_holds_the_golem_for_its_return(self):
        self.assertIn('unsigned const corpses = unsigned(Numbers::Num(spellId, "target_count"));', self.code)
        self.assertIn("Corpses::LeaveMade(player, center, GolemEntry, GolemEntry);", self.code)
        self.assertIn('Minions::Dismiss(player, "golem", Millis(Tune("minion_golem_return_seconds")));', self.code)
        self.assertIn("default: Collapse(player, spellId, center);", self.code)

    def test_each_rune_has_its_part(self):
        for part in ("case Rune::BoneGolem: Tornado(player, spellId, golem, center);", "case Rune::BloodGolem: Sacrifice(player, spellId, center);",
                     "case Rune::DecayGolem: Feed(player, spellId, golem, center);", "case Rune::IceGolem: Freeze(player, spellId, center);"):
            self.assertIn(part, self.code)

    def test_the_tornado_carries_the_enemies_it_found_at_the_start_and_stuns_with_the_worn_powers(self):
        self.assertIn("for (Unit* enemy : Combat::Enemies(player, spellId, start, radius)) carried.push_back(enemy->GetGUID());", self.code)
        self.assertIn("enemy->NearTeleportTo(center.GetPositionX()", self.code)
        self.assertIn("Stun(player, enemy, stun * ItemPowers::StunFactor(player));", self.code)
        self.assertIn('Minions::Raise(player, "command_golem", center);', self.code)

    def test_the_blood_golem_heals_a_share_of_the_life_and_strikes_the_nearest_enemies(self):
        self.assertIn('Heal(player, spellId, player->GetMaxHealth() * Numbers::Num(spellId, "heal_pct") / 100.0);', self.code)
        self.assertIn("std::stable_sort(enemies.begin(), enemies.end()", self.code)
        self.assertIn('enemies.resize(std::size_t(Tune("blood_golem_vein_targets")));', self.code)

    def test_the_decay_golem_eats_up_to_the_most_and_is_boosted_for_the_time(self):
        self.assertIn('std::size_t(Tune("decay_golem_max_corpses")));', self.code)
        self.assertIn('Minions::Boost(player, "golem", CorpseBonusPct(unsigned(eaten.size()), Numbers::Num(spellId, "damage_bonus_pct"), most), ms);', self.code)
        self.assertIn('std::uint32_t const ms = Millis(Tune("decay_golem_buff_seconds"));', self.code)

    def test_the_blood_golem_pushes_the_enemies_near_the_place_out_as_it_forms(self):
        self.assertIn("Knockback(player, spellId, center); Minions::Raise(player, \"command_golem\", center);", self.code)
        self.assertIn('double const radius = Tune("blood_golem_knockback_yards");', self.code)
        self.assertIn("double const share = PushedTo(distance, radius) / distance;", self.code)

    def test_the_decay_golem_grows_with_its_meal_and_shrinks_when_the_boost_ends(self):
        self.assertIn("golem->SetObjectScale(golem->GetNativeObjectScale() * float(1.0 + ScaleBonusPct(", self.code)
        self.assertIn('Tune("decay_golem_max_scale_pct")) / 100.0));', self.code)
        self.assertIn("if (found == grownAs.end() || !ResetDue(found->second, meal)) return;", self.code)
        self.assertIn("meal = meals = NextMeal(meals);", self.code)
        # One clock: the reset reads no game time.
        grown = self.code[self.code.index("std::uint64_t meal;"):self.code.index("// Ice Golem: the enemies")]
        self.assertNotIn("Now()", grown)
        self.assertIn("golem->SetObjectScale(golem->GetNativeObjectScale());", self.code)

    def test_the_ice_golem_freezes_with_the_worn_powers_and_marks_for_crit(self):
        self.assertIn('Stun(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player));', self.code)
        self.assertIn('Numbers::Num(spellId, "crit_taken_pct"), Now() + Millis(seconds)};', self.code)

    def test_the_golem_reads_its_rune_and_a_changed_rune_sends_it_away(self):
        golem = self.pets[self.pets.index("Minions::Kind Golem("):self.pets.index("// Revive:")]
        self.assertIn("CommandGolem::BlowsUseRuneRecord(rune) ? slotted : BaseId(GolemSkill);", golem)
        self.assertIn("changed = held && held != record;", self.pets)
        self.assertIn('if (changed) Minions::Dismiss(player, "golem");', self.pets)
        self.assertIn("heldGolemAs.erase(player->GetGUID().GetRawValue());", self.pets)


if __name__ == "__main__":
    unittest.main()
