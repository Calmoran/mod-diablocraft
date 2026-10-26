"""Shaman Lava Burst and its five runes (src/classes/shaman/dc_shaman_lava_burst.h and .cpp, dc_shaman_free_lava_burst.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_lava_burst/harness.cpp compiles the real dc_shaman_lava_burst.h with the sheets'
    own names and numbers: each rune name is its rune; only Obsidian Burst's own damage is the lava's hit; a Burning enemy takes the
    flat bonus, a chilled one only under Steam Burst, and Obsidian Burst's damage replaces it; Path of Flames spreads a burn from a
    Burning target only; Volcanic Lightning's strike picks one of the enemies near. Mutations planted in a scratch copy must each make
    it fail.
  * **No guaranteed critical strike.** The sheet's bonus is a flat `damage_bonus_pct` (50) and the code adds it as a damage factor; no
    path of the skill sets a critical hit.
  * **Every record's hit loads above 0.** The runes whose record states a duration (Path of Flames, Obsidian Burst) are read from the
    sheet, and the skill hands the loader the hit of every Lava Burst record: Obsidian Burst's own 1000, the skill's 830 for the others.
  * **The free cast.** The Lava Surge state cuts the whole cost of Lava Burst before the cast (the shared cost cut, the skill's hidden cost
    aura, record in the newest combat migration) and the next Lava Burst cast spends it.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Lava Burst (or the rune
    that states it); the burn's tick is a row of data/tunables/combat.csv, rendered into the tunables migration current_migration.txt
    names.

What it does not prove: anything on a running server. The bonus, the free cast, the spread, the eruption, the knock down, the freeze and
the strikes are docs/test-diablocraft-xnrvn.26.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_lava_burst.py
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
HEADERS = ["src/classes/shaman/dc_shaman_lava_burst.h", "src/combat/dc_damage_buckets.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_lava_burst/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_lava_burst.cpp"
FREE = MODULE / "src/classes/shaman/dc_shaman_free_lava_burst.cpp"
SKILL = "Lava Burst"
RUNES = ["Path of Flames", "Pyroclasm", "Obsidian Burst", "Steam Burst", "Volcanic Lightning"]
TUNABLE = ("lava_burst_burn_tick_seconds", "0.5")
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0135_shaman_lava_burst_cost_aura.sql"


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
    numbers = RUNES + [value("Volcanic Lightning", "hit_count")]
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
            ("two runes share a name", ('if (name == "Steam Burst")\n            return Rune::SteamBurst;', 'if (name == "Steam Burst")\n            return Rune::Pyroclasm;')),
            ("Pyroclasm's eruption is the lava's hit", ("return rune == Rune::ObsidianBurst;\n    }\n\n    // \"Deals", "return rune == Rune::ObsidianBurst || rune == Rune::Pyroclasm;\n    }\n\n    // \"Deals")),
            ("Obsidian Burst hits for the skill's", ("return rune == Rune::ObsidianBurst;\n    }\n\n    // \"Deals", "return false;\n    }\n\n    // \"Deals")),
            ("the bonus is for every enemy", ("return burning || (rune == Rune::SteamBurst && chilled);", "return true;")),
            ("the bonus is for a chilled enemy under any rune", ("return burning || (rune == Rune::SteamBurst && chilled);", "return burning || chilled;")),
            ("Steam Burst ignores a chilled enemy", ("return burning || (rune == Rune::SteamBurst && chilled);", "return burning;")),
            ("Obsidian Burst keeps the bonus", ("if (rune == Rune::ObsidianBurst)\n            return false;", "")),
            ("Path of Flames spreads from any target", ("return rune == Rune::PathOfFlames && targetBurning;", "return rune == Rune::PathOfFlames;")),
            ("every rune spreads", ("return rune == Rune::PathOfFlames && targetBurning;", "return targetBurning;")),
            ("a strike always picks the first", ("return std::min(count - 1, std::size_t(std::max(roll, 0.0) * double(count)));", "return std::size_t(0);")),
            ("a strike can pick past the last", ("return std::min(count - 1, std::size_t(std::max(roll, 0.0) * double(count)));", "return std::size_t(std::max(roll, 0.0) * double(count));")),
            ("a strike picks an enemy when none is near", ("if (!count)\n            return std::nullopt;", "")),
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

    def test_the_records_the_loader_would_give_no_hit(self):
        # Path of Flames states its burn's seconds and Obsidian Burst the knock down's: DamageWaits reads both as a damage that waits.
        self.assertEqual(waiting_runes(), ["Path of Flames", "Obsidian Burst"])

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 6, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct"), value("", "damage_bonus_pct"),
                          value("Path of Flames", "radius_yards"), value("Path of Flames", "damage_pct"), value("Path of Flames", "dot_duration_seconds"),
                          value("Pyroclasm", "damage_pct"), value("Pyroclasm", "radius_yards"), value("Obsidian Burst", "damage_pct"),
                          value("Obsidian Burst", "duration_seconds"), value("Steam Burst", "freeze_duration_seconds"),
                          value("Volcanic Lightning", "hit_count"), value("Volcanic Lightning", "radius_yards"), value("Volcanic Lightning", "damage_pct")],
                         [35, 830, 50, 10, 300, 6, 260, 10, 1000, 1, 1, 3, 15, 220])

    def test_the_tunable_is_a_row_of_the_combat_sheet_and_of_the_migration(self):
        name, number = TUNABLE
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        migration_name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / migration_name).read_text(encoding="utf-8")
        self.assertEqual(migration, (MODULE / "data/generated" / migration_name).read_text(encoding="utf-8"))
        self.assertEqual(rows[name]["value"], number)
        self.assertTrue(rows[name]["notes"].strip())
        self.assertIn(f"('combat', '{name}', NULL, {float(number)},", migration)
        self.assertEqual(set(re.findall(r'Tunables::Get\("combat", "([a-z_]+)"\)', CODE.read_text(encoding="utf-8"))), {name})

    def test_lava_burst_has_its_hidden_cost_aura(self):
        shells = {r["name"]: r for r in read(MODULE / "data/generated/spell_shells.csv")}
        aura = shells["Lava Burst cost reduction"]
        self.assertEqual(aura["kind"], "skill_cost_modifier")
        header = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{"Lava Burst", %s},' % aura["spell_id"], header)
        self.assertIn(aura["spell_id"], MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(aura["spell_id"], (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.free = re.sub(r"\s+", " ", FREE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.generator = (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8")

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("Passive::Landed(player, target, spellId, critical); LavaBurst::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("FrostLance::Multipliers(player, spellId, out); LavaBurst::Multipliers(player, target, spellId, out);", self.dispatch)
        self.assertIn("if (auto chainLightning = ChainLightning::BasePct(spellId)) return chainLightning; if (auto lavaBurst = LavaBurst::BasePct(spellId)) return lavaBurst;", self.dispatch)
        self.assertIn("LavaBurst::Cast(player, spellId); ElementalBlast::Cast(player, spellId);", self.dispatch)

    def test_the_skill_hands_the_loader_every_records_hit(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("void Cast(")]
        self.assertIn("if (!Is(spellId)) return std::nullopt;", base)
        self.assertIn('return HitIsRunes(RuneAt(spellId)) ? Numbers::Num(spellId, "damage_pct") : Numbers::Num(BaseId(), "damage_pct");', base)

    def test_the_bonus_is_a_flat_factor_never_a_critical_hit(self):
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn("BonusApplies(RuneAt(spellId), Burning::Is(player, target), Chilled(player, target))", multipliers)
        self.assertIn('AddFactor(out, "Burning", Numbers::Num(BaseId(), "damage_bonus_pct"));', multipliers)
        self.assertNotIn("critical", self.code.lower())
        self.assertNotIn("crit", self.code.lower())

    def test_the_free_cast_cuts_the_whole_cost_and_the_cast_spends_it(self):
        self.assertIn("CostCut::Stand(player, Skill, Key, 100.0);", self.free)
        self.assertIn("CostCut::Stand(player, Skill, Key, 0.0);", self.free)
        self.assertIn('constexpr std::string_view Skill = "Lava Burst";', self.free)
        cast = self.code[self.code.index("void Cast("):self.code.index("void Landed(")]
        self.assertIn("if (player && Is(spellId) && FreeLavaBurst::Pending(player)) FreeLavaBurst::Spend(player);", cast)
        self.assertRegex(self.generator, r'CLASS_COST_CUT_SKILLS = \([^)]*"Lava Burst"')

    def test_each_runes_code(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Multipliers(")]
        self.assertIn("if (striking || !player || !target || !Is(spellId)) return;", landed)
        self.assertIn("if (Spreads(rune, Burning::Is(player, target)))", landed)
        self.assertIn('Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"))', landed)
        self.assertIn('Tunables::Get("combat", "lava_burst_burn_tick_seconds")', landed)
        self.assertIn('Burning::Burn(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"), Numbers::Num(spellId, "dot_duration_seconds"), Tunables::Get("combat", "lava_burst_burn_tick_seconds"));', landed)
        self.assertIn('Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));', landed)
        self.assertIn('Stun(player, target, Numbers::Num(spellId, "duration_seconds"));', landed)
        self.assertIn('Freeze(player, target, Numbers::Num(spellId, "freeze_duration_seconds"));', landed)
        self.assertIn('count = unsigned(Numbers::Num(spellId, "hit_count"))', landed)
        self.assertIn("Pick(frand(0.0f, 1.0f), near.size())", landed)
        self.assertIn("Strikes(player, near[*pick], spellId, Numbers::Num(spellId, \"damage_pct\"));", landed)


if __name__ == "__main__":
    unittest.main()
