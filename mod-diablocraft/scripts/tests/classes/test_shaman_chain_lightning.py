"""Shaman Chain Lightning and its five runes (src/classes/shaman/dc_shaman_chain_lightning.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_chain_lightning/harness.cpp compiles the real dc_shaman_chain_lightning.h with
    the sheets' own names and numbers: each rune name is its rune; only Chain Lava leaves the bolt's own hit the skill's; the walk of
    the jumps goes to the nearest enemy not hit yet, stops at the jump count or when no enemy is left within the radius and never
    repeats one; a Chain Frost jump deals its percent more than the one before; Chain Heal heals its percent of the maximum Life;
    Thunderhead refunds for its crowd and more. The runes whose record states a duration are read from the sheet and the harness
    checks the skill leaves each its hit. Mutations planted in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Chain Lightning (or
    the rune that states it); the two numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables
    migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the seams; the first enemy's hit is the engine's and the jumps are strikes of the
    skill that start nothing; each rune's code is what the draft says.

What it does not prove: anything on a running server. The jumps, the burn, the chill, the heal and the refund are
docs/test-diablocraft-xnrvn.25.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_chain_lightning.py
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
HEADERS = ["src/classes/shaman/dc_shaman_chain_lightning.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_chain_lightning/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_chain_lightning.cpp"
SKILL = "Chain Lightning"
RUNES = ["Forked Lightning", "Chain Lava", "Chain Frost", "Chain Heal", "Thunderhead"]
TUNABLES = {"chain_lightning_burn_tick_seconds": "0.5", "chain_lightning_chill_seconds": "3"}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def waiting_runes():
    """The runes whose record the loader would give no hit (dc_combat_internal.h DamageWaits): the record or its skill states a duration."""
    waits = {"dot_duration_seconds", "duration_seconds", "duration_minutes"}
    rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
    states = lambda rune: any(r["rune"] == rune and (r["token"] in waits or (r["token"], r["qualifier"]) == ("damage_pct", "ramp")) for r in rows)
    return [rune for rune in [""] + RUNES if states("") or states(rune)]


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
    numbers = RUNES + [value("", "target_count"), value("Forked Lightning", "target_count"), value("", "radius_yards"),
                       value("Chain Frost", "damage_bonus_pct"), value("Chain Heal", "heal_pct"), value("Thunderhead", "nearby_enemy_count"),
                       value("Thunderhead", "gain_resource"), value("", "damage_pct"), ",".join(waiting_runes())]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 12, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Chain Frost")\n            return Rune::ChainFrost;', 'if (name == "Chain Frost")\n            return Rune::ChainLava;')),
            ("Chain Lava's hit is left to the loader", ("return rune == Rune::ChainLava;", "return false;")),
            ("every rune leaves the hit to the skill", ("return rune == Rune::ChainLava;", "return rune != Rune::None;")),
            ("a jump goes to the farthest enemy", ("distance(on, candidate) < distance(on, *best)", "distance(on, candidate) > distance(on, *best)")),
            ("a jump may repeat an enemy", ("if (std::find(hit.begin(), hit.end(), candidate) != hit.end())\n                    continue;", "")),
            ("the bolt jumps one time too few", ("for (unsigned jump = 0; jump < jumps; ++jump)", "for (unsigned jump = 1; jump < jumps; ++jump)")),
            ("the bolt never stops walking", ("if (!best)\n                break;", "if (!best)\n                best = first;")),
            ("a jump deals the same as the one before", ("std::pow(1.0 + (bonusPct > 0 ? bonusPct : 0.0) / 100.0, double(jump))", "1.0")),
            ("the bonus adds once", ("std::pow(1.0 + (bonusPct > 0 ? bonusPct : 0.0) / 100.0, double(jump))", "(1.0 + (bonusPct > 0 ? bonusPct : 0.0) / 100.0) * (jump ? 1.0 : 1.0 / (1.0 + (bonusPct > 0 ? bonusPct : 0.0) / 100.0))")),
            ("Chain Heal heals a fraction too much", ("return maxLife > 0 && pct > 0 ? maxLife * pct / 100.0 : 0.0;", "return maxLife > 0 && pct > 0 ? maxLife * pct : 0.0;")),
            ("Thunderhead refunds for any crowd", ("return needed > 0 && gain > 0 && double(enemies) >= needed ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
            ("Thunderhead needs one enemy more", ("double(enemies) >= needed", "double(enemies) > needed")),
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

    def test_the_record_the_loader_would_give_no_hit_is_chain_lava(self):
        self.assertEqual(waiting_runes(), ["Chain Lava"])

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 8, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "target_count"), value("", "radius_yards"),
                          value("Forked Lightning", "target_count"), value("Chain Lava", "damage_pct"), value("Chain Lava", "dot_duration_seconds"),
                          value("Chain Frost", "chill_pct"), value("Chain Frost", "damage_bonus_pct"), value("Chain Heal", "heal_pct"),
                          value("Thunderhead", "nearby_enemy_count"), value("Thunderhead", "gain_resource")],
                         [30, 420, 4, 15, 6, 150, 3, 40, 10, 1.5, 3, 12])

    def test_the_tunables_are_rows_of_the_combat_sheet_and_of_the_migration(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / name).read_text(encoding="utf-8")
        self.assertEqual(migration, (MODULE / "data/generated" / name).read_text(encoding="utf-8"))
        for tunable_name, number in TUNABLES.items():
            with self.subTest(tunable_name):
                self.assertEqual(rows[tunable_name]["value"], number)
                self.assertTrue(rows[tunable_name]["notes"].strip())
                self.assertIn(f"('combat', '{tunable_name}', NULL, {float(number)},", migration)

    def test_the_code_reads_only_tunables_the_sheet_has(self):
        used = set(re.findall(r'Tune\("([a-z_]+)"\)', CODE.read_text(encoding="utf-8")))
        self.assertEqual(used, set(TUNABLES))

    def test_the_skill_is_one_enemy_and_the_jumps_are_the_codes(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        row = rows[SKILL]
        self.assertEqual((row["target_type"], row["range_yards"], row["radius_yards"]), ("single_enemy", "30", "15"))
        for rune in RUNES:
            self.assertNotIn(f"{SKILL} - {rune}", rows, rune)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("FrostLance::Landed(player, target, spellId); ChainLightning::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("if (auto frostLance = FrostLance::BasePct(spellId)) return frostLance; if (auto chainLightning = ChainLightning::BasePct(spellId)) return chainLightning;", self.dispatch)

    def test_chain_lava_hits_for_the_skills_number(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Landed(")]
        self.assertIn("if (!Is(spellId) || !HitIsSkills(RuneAt(spellId))) return std::nullopt;", base)
        self.assertIn('return Numbers::Num(BaseId(), "damage_pct");', base)

    def test_the_jumps_are_strikes_that_start_nothing(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn("if (striking || !player || !target || !Is(spellId)) return;", landed)
        self.assertIn('Walk( target, unsigned(Numbers::Num(spellId, "target_count")) + Ascendance::ExtraChainJumps(player)', landed)
        self.assertIn('Combat::Enemies(player, spellId, on->GetPosition(), radius)', landed)
        self.assertIn('double const radius = Numbers::Num(spellId, "radius_yards");', landed)
        self.assertIn("striking = true; for (std::size_t jump = 1; jump < walk.size(); ++jump)", landed)
        self.assertIn("if (Combat::Strike(player, walk[jump], spellId, pct)) struck.push_back(walk[jump]); } striking = false;", landed)
        self.assertIn('double const hitPct = Numbers::Num(BaseId(), "damage_pct");', landed)

    def test_chain_frost_grows_by_jump_and_chills_every_enemy(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn('rune == Rune::ChainFrost ? JumpPct(hitPct, Numbers::Num(spellId, "damage_bonus_pct"), unsigned(jump)) : hitPct', landed)
        frost = landed[landed.index("case Rune::ChainFrost:"):landed.index("case Rune::ChainHeal:")]
        self.assertIn('Chill(player, enemy, Numbers::Num(spellId, "chill_pct"), Tune("chain_lightning_chill_seconds"));', frost)

    def test_chain_lava_burns_each_enemy_hit(self):
        landed = self.code[self.code.index("void Landed("):]
        lava = landed[landed.index("case Rune::ChainLava:"):landed.index("case Rune::ChainFrost:")]
        self.assertIn('Burning::Burn(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"), seconds, Tune("chain_lightning_burn_tick_seconds"));', lava)
        self.assertIn('double const seconds = Numbers::Num(spellId, "dot_duration_seconds");', lava)
        self.assertIn("for (Unit* enemy : struck)", landed)

    def test_chain_heal_and_thunderhead(self):
        landed = self.code[self.code.index("void Landed("):]
        self.assertIn('Heal(player, spellId, HealAmount(double(player->GetMaxHealth()), Numbers::Num(spellId, "heal_pct")));', landed)
        self.assertIn("if (rune == Rune::Thunderhead) Gain(player, spellId, Refund(unsigned(struck.size()), Numbers::Num(spellId, \"nearby_enemy_count\"), Numbers::Num(spellId, \"gain_resource\")));", landed)


if __name__ == "__main__":
    unittest.main()
