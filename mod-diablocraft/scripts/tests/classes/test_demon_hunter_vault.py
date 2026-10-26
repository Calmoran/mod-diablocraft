"""Demon Hunter Vault and its five runes (src/classes/demon_hunter/dc_demon_hunter_vault.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_vault/harness.cpp compiles the real dc_demon_hunter_vault.h, the DoT
    rules and the clock with the sheets' own rune names and numbers: each rune name is its rune; where an enemy stands along and
    across a path; the box Rattling Roll carries and the band Trail of Cinders leaves hold what they should and nothing more; the
    fire's ticks make the sheet's damage; Action Shot's arrows are shared round the enemies nearest first and every one of a few is
    shot at; only its arrows are sure to crit. Eight mutations planted in a scratch copy must each make it fail.
  * **The record needs no change.** The vault is the engine's charge (a `line_to_point` row of skill_targeting.csv, range 35); the
    Discipline cost, Acrobatics' free cast and its 6 s cooldown are the record's (test_demon_hunter_records.py holds them), so the one new
    migration is the tunables'.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Vault (or the
    rune that states it); every tunable is a row of data/tunables/demonhunter.csv; the numbers equal the decoded
    Power/DemonHunter_Vault.pow (skipped where the game archives are not on this machine).
  * **The wiring.** The dispatch answers the seams (the base pct, the crit chance, Ground, the scripts) and the critical hit line adds
    the class's chance; the vault hits nothing itself; the trail burns the enemies in its band every tick with a damage-over-time
    strike; the arrows are strikes at the nearest enemies; the stun is the Demon Hunter's, stretched by the stun power and with the
    knock; the box is carried until the charge that began with the cast ends; Tumble gives the next Vault's cost cut before the cast (the shared CostCut piece).

What it does not prove: anything on a running server. The charge, the trail, the arrows, the stun and the half cost are
docs/test-diablocraft-vawmy.21.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_vault.py
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
HEADER = "src/classes/demon_hunter/dc_demon_hunter_vault.h"
DOT = "src/classes/demon_hunter/dc_demon_hunter_dot.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, DOT, CLOCK, "tests/demon_hunter_vault/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_vault.cpp"
SKILL = "Vault"
RUNES = ["Trail of Cinders", "Acrobatics", "Action Shot", "Tumble", "Rattling Roll"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "demon_hunter_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_vault/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Trail of Cinders", "damage_pct"), value("Trail of Cinders", "dot_duration_seconds"), tune("vault_trail_tick_seconds"),
                         tune("vault_stun_strip_length_yards"), tune("vault_stun_strip_width_yards"), tune("vault_trail_width_yards"),
                         value("Action Shot", "projectile_count")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 40, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Acrobatics")\n            return Rune::Acrobatics;',
                                        'if (name == "Acrobatics")\n            return Rune::TrailOfCinders;')),
            ("the side is mirrored", (HEADER, "dy * std::cos(angle) - dx * std::sin(angle)", "dy * std::cos(angle) + dx * std::sin(angle)")),
            ("the path is swung the wrong way", (HEADER, "dx * std::cos(angle) + dy * std::sin(angle)", "dx * std::cos(angle) - dy * std::sin(angle)")),
            ("the box has no width", (HEADER, "std::fabs(place.across) <= width / 2;\n    }\n\n    // A band",
                                      "true;\n    }\n\n    // A band")),
            ("the trail reaches behind the start", (HEADER, "width > 0 && place.along >= 0 && place.along <= reach",
                                                    "width > 0 && place.along <= reach")),
            ("a tick is the whole damage", (HEADER, "return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));", "return totalPct;")),
            ("every arrow flies at the nearest", (HEADER, "return enemies ? shot % enemies : 0;", "return 0;")),
            ("the arrows are not sure to crit", (HEADER, "return rune == Rune::ActionShot ? 100.0 : 0.0;", "return 0.0;")),
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

    def test_the_record_is_the_engines_charge(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual((rows[SKILL]["target_type"], rows[SKILL]["range_yards"]), ("line_to_point", "35"))
        self.assertFalse([name for name in rows if name.startswith(SKILL + " - ")])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "distance_yards")], [8, 35])
        self.assertEqual([value("Trail of Cinders", "damage_pct"), value("Trail of Cinders", "dot_duration_seconds")], [300, 3])
        self.assertEqual(value("Acrobatics", "cooldown_seconds"), 6)
        self.assertEqual([value("Action Shot", "projectile_count"), value("Action Shot", "damage_pct")], [4, 75])
        self.assertEqual([value("Tumble", "duration_seconds"), value("Tumble", "cost_reduction_pct")], [6, 50])
        self.assertEqual(value("Rattling Roll", "stun_duration_seconds"), 1.5)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("vault_action_shot_interval_seconds", "0.1", "SF_3"), ("vault_trail_tick_seconds", "0.2", "SF_12"),
                                 ("vault_stun_area_yards", "8", "SF_7"), ("vault_stun_strip_length_yards", "5", "SF_17"),
                                 ("vault_stun_strip_width_yards", "5", "SF_16"), ("vault_stun_check_seconds", "0.1", "SF_18"),
                                 ("vault_action_shot_range_yards", "35", "SF_10")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Vault.pow", rows[name]["notes"])
            self.assertNotIn("placeholder", rows[name]["notes"].lower(), name)

    def test_the_trail_width_is_alexs_standing_default_and_the_knockback_a_marked_placeholder(self):
        width = tunables()["vault_trail_width_yards"]
        self.assertEqual((width["d3_value"], width["value"]), ("", "3"))
        self.assertIn("standing default", width["notes"])
        knock = tunables()["vault_knockback_yards"]
        self.assertEqual((knock["d3_value"], knock["value"]), ("", "5"))
        self.assertIn("placeholder", knock["notes"].lower())

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("vault_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w.()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune, token, origin in (("", "distance_yards", "own"), ("Trail of Cinders", "distance_yards", "inherited"),
                                    ("Trail of Cinders", "damage_pct", "own"), ("Trail of Cinders", "dot_duration_seconds", "own"),
                                    ("Action Shot", "projectile_count", "own"), ("Action Shot", "damage_pct", "own"),
                                    ("Tumble", "duration_seconds", "own"), ("Tumble", "cost_reduction_pct", "own"),
                                    ("Rattling Roll", "stun_duration_seconds", "own")):
            self.assertEqual(mapped[(rune, token)]["origin"], origin, (rune, token))

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Vault.pow"))["sf"]

        def number(n):
            return float(str(sf[n]).strip())

        self.assertAlmostEqual(number(10), value("", "distance_yards"))
        self.assertAlmostEqual(number(5), value("", "cost_resource"))
        self.assertAlmostEqual(number(1) * 100 * number(13), value("Trail of Cinders", "damage_pct"))
        self.assertAlmostEqual(number(13), value("Trail of Cinders", "dot_duration_seconds"))
        self.assertAlmostEqual(float(sf[2].split("?")[1].split(":")[0]), value("Acrobatics", "cooldown_seconds"))
        self.assertAlmostEqual(number(15), value("Action Shot", "projectile_count"))
        self.assertAlmostEqual(number(4) * 100, value("Action Shot", "damage_pct"))
        self.assertAlmostEqual(number(9), value("Tumble", "duration_seconds"))
        self.assertAlmostEqual(number(6) * 100, value("Tumble", "cost_reduction_pct"))
        self.assertAlmostEqual(number(8), value("Rattling Roll", "stun_duration_seconds"))
        self.assertAlmostEqual(number(3), tune("vault_action_shot_interval_seconds"))
        self.assertAlmostEqual(number(10), tune("vault_action_shot_range_yards"))
        self.assertAlmostEqual(number(12), tune("vault_trail_tick_seconds"))
        self.assertAlmostEqual(number(7), tune("vault_stun_area_yards"))
        self.assertAlmostEqual(number(17), tune("vault_stun_strip_length_yards"))
        self.assertAlmostEqual(number(16), tune("vault_stun_strip_width_yards"))
        self.assertAlmostEqual(number(18), tune("vault_stun_check_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        self.combat = (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto dash = Vault::BasePct(spellId)) return dash;"), 1)
        self.assertLess(self.dispatch.index("ElementalArrow::BasePct(spellId)"), self.dispatch.index("Vault::BasePct(spellId)"))
        self.assertLess(self.dispatch.index("Vault::BasePct(spellId)"), self.dispatch.index("return Caltrops::BasePct(spellId);"))
        for call in ("return Vault::CritBonus(spellId) + Multishot::CritBonus(target) + Passive::CritBonus(player, target);", "Vault::Ground(player, spellId, center);", "Vault::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_critical_hit_line_adds_the_classes_chance(self):
        self.assertEqual(self.combat.count("+Necromancer::CritBonus(player, target)+DemonHunter::CritBonus(player, target, shell.spellId)+GemPowers::CritBonus"), 1)
        self.assertIn("return CritBonus(RuneAt(spellId));", self.code)

    def test_the_vault_hits_nothing_itself(self):
        self.assertIn("return Is(spellId) ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_trail_burns_the_enemies_in_its_band_every_tick(self):
        burn = self.code[self.code.index("void Burn("):self.code.index("void Sweep(")]
        self.assertIn('Numbers::Num(trail.spellId, "damage_pct"), Numbers::Num(trail.spellId, "dot_duration_seconds")', burn)
        self.assertIn('Tune("vault_trail_tick_seconds")', burn)
        self.assertIn("InBand(PlaceOn(", burn)
        self.assertIn("Combat::Strike(player, enemy, trail.spellId, pct, true);", burn)
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn('Due(trail.clock, diff, Tune("vault_trail_tick_seconds") * 1000.0)', update)
        self.assertIn("trail.left -= diff;", update)
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts(")]
        self.assertIn('Numbers::Num(spellId, "distance_yards")', ground)
        self.assertIn('trail.left = Numbers::Num(spellId, "dot_duration_seconds") * 1000.0;', ground)

    def test_the_arrows_are_strikes_at_the_nearest_enemies_one_every_interval(self):
        shoot = self.code[self.code.index("void Shoot("):self.code.index("class Vaults")]
        self.assertIn('Tune("vault_action_shot_range_yards")', shoot)
        self.assertIn("player->GetExactDist(a) < player->GetExactDist(b)", shoot)
        self.assertIn('Combat::Strike(player, enemies[ShotAt(shot, enemies.size())], spellId, Numbers::Num(spellId, "damage_pct"));', shoot)
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts(")]
        self.assertIn('unsigned(Numbers::Num(spellId, "projectile_count"))', ground)
        self.assertIn('Tune("vault_action_shot_interval_seconds")', ground)
        self.assertIn("std::chrono::milliseconds(std::uint32_t(interval * shot + 0.5))", ground)

    def test_the_stun_is_the_demon_hunters_and_the_box_is_carried_until_the_charge_ends(self):
        sweep = self.code[self.code.index("void Sweep("):self.code.index("void Shoot(")]
        self.assertIn('Combat::Enemies(player, roll.spellId, here, Tune("vault_stun_area_yards"))', sweep)
        self.assertIn('Tune("vault_stun_strip_length_yards"), Tune("vault_stun_strip_width_yards")', sweep)
        self.assertIn("if (roll.stunned.count(enemy->GetGUID().GetRawValue())) continue;", sweep)
        self.assertIn('Abilities::Knockback(player, enemy, Tune("vault_knockback_yards"));', sweep)
        self.assertIn('Stun(player, enemy, Numbers::Num(roll.spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));', sweep)
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn("player->movespline->GetId() != mine.roll->spline || player->movespline->Finalized()", update)
        self.assertIn('Due(mine.roll->clock, diff, Tune("vault_stun_check_seconds") * 1000.0)', update)
        ground = self.code[self.code.index("void Ground("):self.code.index("void RegisterScripts(")]
        self.assertIn("if (player->movespline->Finalized()) break;", ground)

    def test_tumble_cuts_the_next_vaults_cost_before_the_cast(self):
        """The rune's cut is the shared CostCut piece's: the cost the core charges is lowered through the skill's hidden cost aura before the cast, and nothing is paid
        back after it (test_cost_cut.py holds the piece; this holds what the rune gives it)."""
        hook = self.code[self.code.index("class CastHook"):self.code.index("bool Is(")]
        self.assertIn("RuneAt(info->Id) != Rune::Tumble", hook)
        self.assertIn("spell->IsTriggered()", hook)
        self.assertIn('CostCut::Hold(player, Skill, BaseId(Skill), Numbers::Num(info->Id, "cost_reduction_pct"), Numbers::Num(info->Id, "duration_seconds"));', re.sub(r"\s+", " ", hook))
        for refund in ("Energize", "GetPowerCost", "Refund", "lastCast"):
            self.assertNotIn(refund, self.code)

    def test_what_the_vault_set_going_ends_with_its_owner(self):
        self.assertIn("if (!player->IsAlive()) { Stop(player); return; }", self.code)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)


if __name__ == "__main__":
    unittest.main()
