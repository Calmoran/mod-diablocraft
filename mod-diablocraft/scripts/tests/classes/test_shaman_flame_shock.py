"""Shaman Flame Shock and its five runes (src/classes/shaman/dc_shaman_flame_shock.h and .cpp, dc_shaman_burning.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_flame_shock/harness.cpp compiles the real dc_shaman_flame_shock.h and
    dc_shaman_burning.h with the sheets' own rune names and numbers: each rune name is its rune; where each cast's own hit takes its
    damage from; only the base and Lava Shock leave the burn and only Lava Shock on a Burning target erupts; Primal Shock's small
    effect follows the Attunement; Frost Shock adds Maelstrom against a chilled enemy only; the mark raises a marked enemy's hit and
    holds for its seconds; a second burn extends Burning and never shortens it. Mutations planted in a scratch copy must each make
    it fail.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Flame Shock (or the
    rune that states it); the four numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables
    migration current_migration.txt names.
  * **The wiring.** The class dispatch answers the seams; the loader takes the Primaries' hit damage before the Witch Doctor's and the
    engine asks for the Primal Shock element where the Wizard's is asked; Lava Shock reads Burning before its own burn starts, Frost
    Shock reads the chill before it gives its own, Earth Shock spares elites and bosses, and a strike the skill starts starts nothing.

What it does not prove: anything on a running server. The burn, the eruption, the chill, the stun, the arcs and the Primal Shock
effects are docs/test-diablocraft-xnrvn.13.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_flame_shock.py
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
HEADERS = ["src/classes/shaman/dc_shaman_flame_shock.h", "src/classes/shaman/dc_shaman_burning.h", "src/combat/dc_damage_buckets.h"]
HEADER = HEADERS[0]
BURNING = HEADERS[1]
HARNESS = MODULE / "tests/shaman_flame_shock/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_flame_shock.cpp"
SKILL = "Flame Shock"
RUNES = ["Lava Shock", "Frost Shock", "Earth Shock", "Static Shock", "Primal Shock"]
TUNABLES = {
    "flame_shock_burn_tick_seconds": "0.5",
    "flame_shock_arc_radius_yards": "15",
    "flame_shock_primal_chill_seconds": "3",
    "flame_shock_primal_arc_damage_pct": "120",
}


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
        header, old, new = mutate
        key = header[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {header}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = RUNES + [value("Frost Shock", "gain_resource"), value("Primal Shock", "damage_taken_pct"), value("Primal Shock", "duration_seconds"),
                       value("", "dot_duration_seconds")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 15, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Frost Shock")\n            return Rune::FrostShock;', 'if (name == "Frost Shock")\n            return Rune::LavaShock;')),
            ("Frost Shock hits for the skill's number", (HEADER, "case Rune::FrostShock:\n            case Rune::EarthShock:\n                return HitFrom::RuneOnly;",
                                                         "case Rune::EarthShock:\n                return HitFrom::RuneOnly;")),
            ("Primal Shock hits for its own number only", (HEADER, "case Rune::StaticShock:\n            case Rune::PrimalShock:\n                return HitFrom::RuneHit;",
                                                           "case Rune::StaticShock:\n                return HitFrom::RuneHit;")),
            ("every rune burns", (HEADER, "return rune == Rune::None || rune == Rune::LavaShock;", "return true;")),
            ("Lava Shock does not burn", (HEADER, "return rune == Rune::None || rune == Rune::LavaShock;", "return rune == Rune::None;")),
            ("Lava Shock erupts on any target", (HEADER, "return rune == Rune::LavaShock && wasBurning;", "return rune == Rune::LavaShock;")),
            ("every rune erupts on a Burning target", (HEADER, "return rune == Rune::LavaShock && wasBurning;", "return wasBurning;")),
            ("Cold marks", (HEADER, 'if (attuned == "cold")\n            return Small::Chill;', 'if (attuned == "cold")\n            return Small::Mark;')),
            ("Lightning adds nothing", (HEADER, 'if (attuned == "lightning")\n            return Small::Arc;', "")),
            ("Frost Shock adds against any enemy", (HEADER, "return chilled && gain > 0 ? gain : 0.0;", "return gain > 0 ? gain : 0.0;")),
            ("the mark raises an unmarked enemy's hit", (HEADER, "return marked && pct > 0 ? pct : 0.0;", "return pct > 0 ? pct : 0.0;")),
            ("the mark holds a millisecond long", (HEADER, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("a burn shortens the one running", (BURNING, "return seconds > 0 ? std::max(untilMs, nowMs + std::uint64_t(seconds * 1000.0)) : untilMs;",
                                                 "return seconds > 0 ? nowMs + std::uint64_t(seconds * 1000.0) : untilMs;")),
            ("a burn never extends the one running", (BURNING, "std::max(untilMs, nowMs + std::uint64_t(seconds * 1000.0))", "untilMs ? untilMs : nowMs + std::uint64_t(seconds * 1000.0)")),
            ("an enemy burns a millisecond long", (BURNING, "return nowMs < untilMs;", "return nowMs <= untilMs;")),
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

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::Num\((?:spellId|BaseId\(\)), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 9, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "damage_pct", "hit"), value("", "damage_pct", "dot"), value("", "dot_duration_seconds"), value("", "generated_resource"),
                          value("Lava Shock", "damage_pct"), value("Lava Shock", "radius_yards"), value("Frost Shock", "damage_pct"),
                          value("Frost Shock", "chill_pct"), value("Frost Shock", "chill_duration_seconds"), value("Frost Shock", "gain_resource"),
                          value("Earth Shock", "damage_pct"), value("Earth Shock", "stun_duration_seconds"), value("Earth Shock", "generated_resource", "new"),
                          value("Static Shock", "damage_pct", "hit"), value("Static Shock", "damage_pct", "arc"), value("Static Shock", "target_count"),
                          value("Primal Shock", "damage_pct", "hit"), value("Primal Shock", "damage_pct", "fire"), value("Primal Shock", "chill_pct"),
                          value("Primal Shock", "damage_taken_pct"), value("Primal Shock", "duration_seconds"), value("Primal Shock", "target_count")],
                         [160, 450, 6, 11, 200, 8, 240, 60, 3, 4, 330, 0.5, 16, 260, 120, 2, 300, 300, 40, 5, 4, 1])

    def test_the_tunables_are_rows_of_the_combat_sheet_and_of_the_migration(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv")}
        name = (MODULE / "data/tunables/current_migration.txt").read_text(encoding="utf-8").strip()
        migration = (MODULE / "data/sql/db-world/updates" / name).read_text(encoding="utf-8")
        mirror = (MODULE / "data/generated" / name).read_text(encoding="utf-8")
        self.assertEqual(migration, mirror)
        for tunable, number in TUNABLES.items():
            with self.subTest(tunable):
                self.assertEqual(rows[tunable]["value"], number)
                self.assertTrue(rows[tunable]["notes"].strip())
                self.assertIn(f"('combat', '{tunable}', NULL, {float(number)},", migration)

    def test_the_code_reads_only_tunables_the_sheet_has(self):
        code = CODE.read_text(encoding="utf-8")
        used = set(re.findall(r'Tune\("([a-z_]+)"\)', code))
        self.assertEqual(used, set(TUNABLES))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.combat = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))
        self.attunement = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_attunement.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("LightningBolt::Landed(player, target, spellId, critical); FlameShock::Landed(player, target, spellId);", self.dispatch)
        self.assertIn("LightningBolt::Multipliers(player, target, spellId, out); FlameShock::Multipliers(player, target, spellId, out);", self.dispatch)
        self.assertIn("std::optional<double> PrimaryBasePct(std::uint32_t spellId) { if (auto lightningBolt = LightningBolt::BasePct(spellId)) return lightningBolt; if (auto flameShock = FlameShock::BasePct(spellId)) return flameShock;", self.dispatch)
        self.assertIn("char const* Element(Player* player, std::uint32_t spellId) { if (!IsShaman(player)) return nullptr; if (char const* element = FlameShock::Element(player, spellId)) return element;", self.dispatch)

    def test_the_engine_asks_for_the_hit_damage_and_the_element(self):
        loader = "else if (auto shamanPrimary = Shaman::PrimaryBasePct(ability.id)) shell.damagePct = *shamanPrimary;"
        self.assertEqual(self.combat.count(loader), 1)
        self.assertLess(self.combat.index("DemonHunter::BasePct(ability.id)"), self.combat.index(loader))
        self.assertLess(self.combat.index(loader), self.combat.index("WitchDoctor::BasePct(ability.id)"))
        element = "if (char const* element = Shaman::Element(player, shell.spellId)) shell.element = element;"
        self.assertEqual(self.combat.count(element), 1)
        self.assertLess(self.combat.index("Wizard::Element(player, shell.spellId)"), self.combat.index(element))
        self.assertLess(self.combat.index(element), self.combat.index("hit.school = SchoolOf(shell.element);"))

    def test_the_hit_takes_its_number_from_the_row_the_rule_names(self):
        base = self.code[self.code.index("std::optional<double> BasePct("):self.code.index("char const* Element(")]
        self.assertIn('case HitFrom::RuneOnly: return Numbers::Num(spellId, "damage_pct");', base)
        self.assertIn('case HitFrom::RuneHit: return Numbers::Num(spellId, "damage_pct", "hit");', base)
        self.assertIn('default: return Numbers::Num(BaseId(), "damage_pct", "hit");', base)

    def test_primal_shock_deals_the_attunement(self):
        self.assertIn("RuneAt(spellId) == Rune::PrimalShock ? Attunement::Current(player) : nullptr;", self.code)
        self.assertIn("SmallOf(Attunement::Current(player))", self.code)
        self.assertIn("char const* Current(Player* player) { if (!IsShaman(player)) return \"\";", self.attunement)

    def test_the_burn_is_the_periodic_strike_and_burning(self):
        self.assertIn('Burning::Burn(player, target, spellId, totalPct, seconds, Tune("flame_shock_burn_tick_seconds"));', self.code)
        self.assertIn('Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "dot"), Numbers::Num(spellId, "dot_duration_seconds"));', self.code)

    def test_lava_shock_reads_burning_before_its_own_burn_starts(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("case Rune::FrostShock:")]
        self.assertLess(landed.index("Burning::Is(player, target)"), landed.index("BaseBurn(player, target, spellId)"))
        self.assertIn("if (Erupts(rune, wasBurning))", landed)
        self.assertIn('Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"))', landed)
        self.assertIn('Strikes(player, enemy, spellId, Numbers::Num(spellId, "damage_pct")); if (enemy->IsAlive()) BaseBurn(player, enemy, spellId);', landed)

    def test_a_strike_the_skill_starts_starts_nothing(self):
        self.assertIn("if (striking || !player || !target || !Is(spellId)) return;", self.code)
        self.assertIn("striking = true; Combat::Strike(player, target, spellId, pct); striking = false;", self.code)

    def test_frost_shock_reads_the_chill_before_it_gives_its_own(self):
        frost = self.code[self.code.index("case Rune::FrostShock:"):self.code.index("case Rune::EarthShock:")]
        self.assertLess(frost.index("Chilled(player, target)"), frost.index("Chill(player, target,"))
        self.assertIn('Chill(player, target, Numbers::Num(spellId, "chill_pct"), Numbers::Num(spellId, "chill_duration_seconds"));', frost)
        self.assertIn('Gain(player, spellId, ChilledGain(chilled, Numbers::Num(spellId, "gain_resource")));', frost)

    def test_earth_shock_spares_elites_and_bosses(self):
        earth = self.code[self.code.index("case Rune::EarthShock:"):self.code.index("case Rune::StaticShock:")]
        self.assertIn('if (!IsElite(target)) Stun(player, target, Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player));', earth)

    def test_the_arcs_go_to_the_nearest_others(self):
        arc = self.code[self.code.index("void Arc("):self.code.index("void Mark(")]
        self.assertIn('Tune("flame_shock_arc_radius_yards")', arc)
        self.assertIn("near.erase(std::remove(near.begin(), near.end(), from), near.end());", arc)
        self.assertIn("return from->GetExactDist(a) < from->GetExactDist(b);", arc)
        self.assertIn("if (near.size() > count) near.resize(count);", arc)
        static = self.code[self.code.index("case Rune::StaticShock:"):self.code.index("case Rune::PrimalShock:")]
        self.assertIn('Arc(player, target, spellId, unsigned(Numbers::Num(spellId, "target_count")), Numbers::Num(spellId, "damage_pct", "arc"));', static)

    def test_primal_shocks_small_effects(self):
        primal = self.code[self.code.index("case Rune::PrimalShock:"):self.code.index("default: break; } } void Multipliers(")]
        self.assertIn('Burn(player, target, spellId, Numbers::Num(spellId, "damage_pct", "fire"), Numbers::Num(spellId, "dot_duration_seconds"));', primal)
        self.assertIn('Chill(player, target, Numbers::Num(spellId, "chill_pct"), Tune("flame_shock_primal_chill_seconds"));', primal)
        self.assertIn('Mark(player, target, Numbers::Num(spellId, "damage_taken_pct"), Numbers::Num(spellId, "duration_seconds"));', primal)
        self.assertIn('Tune("flame_shock_primal_arc_damage_pct")', primal)

    def test_the_mark_is_the_shamans_who_made_it(self):
        multipliers = self.code[self.code.index("void Multipliers("):]
        self.assertIn("if (found->second.owner == player->GetGUID()) pct = found->second.pct;", multipliers)
        self.assertIn("MarkBonus(pct > 0, pct)", multipliers)
        self.assertIn('AddFactor(out, "Primal Shock", bonus);', multipliers)
        self.assertIn("if (!Holds(Now(), found->second.until)) { marks.erase(found); return; }", multipliers)


if __name__ == "__main__":
    unittest.main()
