"""Shaman Ascendance and its five runes (src/classes/shaman/dc_shaman_ascendance.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/shaman_ascendance/harness.cpp compiles the real dc_shaman_ascendance.h with the sheets' and
    tunables' own names and numbers: each rune name is its rune and picks its element; the empowered element takes the rune's damage
    bonus and every other element the skill's; a bolt is its share of the Primary's damage (above 0) and only a Primary cast fires
    one; Eternal Ascendance adds a step for each block of Maelstrom spent, carries the remainder and stops at its cap; only Storm
    Ascendance gives Chain Lightning extra jumps; the buff holds until it ends. Mutations planted in a scratch copy must each make it
    fail.
  * **No hit to load.** Ascendance deals no damage of its own: no row of the sheet for it states a `damage_pct`; its bolts pass a
    percent computed from the Primary's hit, tested above 0.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of shaman_skill_values.csv for Ascendance (or the rune
    that states it); the two numbers the draft does not give are rows of data/tunables/combat.csv, rendered into the tunables migration
    current_migration.txt names.
  * **The wiring.** The class dispatch answers the cast, the paying and the multiplier seams; the buff is one per Shaman (a new cast takes
    a new stamp), doubles Maelstrom generation, the Earth rune wears a reduction, the Flame rune cuts Lava Burst's whole cost for the
    buff's time, the Water rune heals each pulse and Chain Lightning asks for the Storm rune's jumps.

What it does not prove: anything on a running server. The buff, the bolts and each rune are docs/test-diablocraft-xnrvn.36.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_shaman_ascendance.py
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
HEADERS = ["src/classes/shaman/dc_shaman_ascendance.h", "src/combat/dc_damage_buckets.h"]
HEADER = HEADERS[0]
HARNESS = MODULE / "tests/shaman_ascendance/harness.cpp"
CODE = MODULE / "src/classes/shaman/dc_shaman_ascendance.cpp"
SKILL = "Ascendance"
RUNES = ["Flame Ascendance", "Storm Ascendance", "Water Ascendance", "Earth Ascendance", "Eternal Ascendance"]
TUNABLES = {"ascendance_tick_seconds": "1", "ascendance_bolt_radius_yards": "15"}


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
    numbers = RUNES + [value("", "damage_bonus_pct"), value("Flame Ascendance", "damage_bonus_pct"), value("", "damage_share_pct"),
                       value("Eternal Ascendance", "per_trigger_resource"), value("Eternal Ascendance", "duration_seconds", "extend"),
                       value("Eternal Ascendance", "duration_seconds", "cap"), value("Storm Ascendance", "target_count"), 285]
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
            ("two runes share a name", ('if (name == "Water Ascendance")\n            return Rune::WaterAscendance;', 'if (name == "Water Ascendance")\n            return Rune::EarthAscendance;')),
            ("Flame picks Cold", ('case Rune::FlameAscendance:\n                return "fire";', 'case Rune::FlameAscendance:\n                return "cold";')),
            ("Eternal Ascendance picks an element", ("            default:\n                return {};", '            default:\n                return "fire";')),
            ("every element takes the rune's bonus", ("return !empowered.empty() && empowered == element && runePct > 0 ? runePct : (basePct > 0 ? basePct : 0.0);", "return runePct > 0 ? runePct : (basePct > 0 ? basePct : 0.0);")),
            ("the other elements take nothing", ("return !empowered.empty() && empowered == element && runePct > 0 ? runePct : (basePct > 0 ? basePct : 0.0);", "return !empowered.empty() && empowered == element && runePct > 0 ? runePct : 0.0;")),
            ("the empowered element takes the skill's bonus", ("return !empowered.empty() && empowered == element && runePct > 0 ? runePct : (basePct > 0 ? basePct : 0.0);", "return basePct > 0 ? basePct : 0.0;")),
            ("a bolt is the whole damage", ("return hitPct > 0 && sharePct > 0 ? hitPct * sharePct / 100.0 : 0.0;", "return hitPct;")),
            ("a bolt deals nothing", ("return hitPct > 0 && sharePct > 0 ? hitPct * sharePct / 100.0 : 0.0;", "return 0.0;")),
            ("a Secondary cast fires bolts", ('return up && category == "Primary";', "return up;")),
            ("bolts fly with the buff down", ('return up && category == "Primary";', 'return category == "Primary";')),
            ("Maelstrom spent never carries", ("out.remainder = total;", "out.remainder = 0;")),
            ("the extension ignores the cap", ("if (extendedMs + out.addMs < cap)\n                out.addMs += std::min(step, cap - extendedMs - out.addMs);", "out.addMs += step;")),
            ("any rune extends", ("if (rune != Rune::EternalAscendance || spent <= 0", "if (spent <= 0")),
            ("the extension needs one block too many", ("while (total >= perTrigger)", "while (total > perTrigger)")),
            ("every rune gives extra jumps", ("return rune == Rune::StormAscendance && targetCount > 0 ? unsigned(targetCount) : 0u;", "return targetCount > 0 ? unsigned(targetCount) : 0u;")),
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

    def test_ascendance_deals_no_damage_of_its_own_so_no_hit_loads(self):
        rows = [r for r in read(D3 / "shaman_skill_values.csv") if r["skill"] == SKILL]
        self.assertFalse([r for r in rows if r["token"] == "damage_pct"])
        self.assertTrue([r for r in rows if r["token"] == "duration_seconds"])
        # what its bolts deal is a share of a Primary's hit: above 0
        self.assertGreater(value("", "damage_share_pct"), 0)

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        code = CODE.read_text(encoding="utf-8")
        reads = set(re.findall(r'Numbers::(?:Num|Get)\((?:spellId|buff\.spellId|BaseId\(\)|found->second\.spellId), "([a-z_]+)"', code))
        self.assertGreaterEqual(len(reads), 7, reads)
        held = {r["token"] for r in read(D3 / "shaman_skill_values.csv")} | {"cost_resource"}
        for token in reads:
            self.assertIn(token, held, token)

    def test_the_numbers_are_the_drafts(self):
        self.assertEqual([value("", "cooldown_seconds"), value("", "damage_bonus_pct"), value("", "target_count"), value("", "damage_share_pct"),
                          value("", "duration_seconds"), value("Flame Ascendance", "damage_bonus_pct"), value("Storm Ascendance", "damage_bonus_pct"),
                          value("Storm Ascendance", "target_count"), value("Water Ascendance", "damage_bonus_pct"), value("Water Ascendance", "life_regen_pct"),
                          value("Earth Ascendance", "damage_bonus_pct"), value("Earth Ascendance", "damage_reduction_pct"),
                          value("Eternal Ascendance", "per_trigger_resource"), value("Eternal Ascendance", "duration_seconds", "extend"),
                          value("Eternal Ascendance", "duration_seconds", "cap")],
                         [120, 25, 2, 50, 15, 30, 30, 3, 30, 2, 30, 30, 50, 1, 15])

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

    def test_the_cast_is_on_the_shaman_alone(self):
        rows = {r["skill"]: r for r in read(D3 / "skill_targeting.csv")}
        self.assertEqual(rows[SKILL]["target_type"], "self")


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman.cpp").read_text(encoding="utf-8"))
        self.chain = re.sub(r"\s+", " ", (MODULE / "src/classes/shaman/dc_shaman_chain_lightning.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("ElementalShield::Casting(player, spellId); Ascendance::Casting(player, spellId);", self.dispatch)
        self.assertIn("FireElemental::Cast(player, spellId, targets); Ascendance::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("ElementalBlast::Multipliers(player, spellId, out); Ascendance::Multipliers(player, spellId, out);", self.dispatch)

    def test_chain_lightning_asks_for_the_storm_jumps(self):
        self.assertIn('target, unsigned(Numbers::Num(spellId, "target_count")) + Ascendance::ExtraChainJumps(player),', self.chain)
        extra = self.code[self.code.index("unsigned ExtraChainJumps("):]
        self.assertIn('ExtraJumps(found->second.rune, Numbers::Num(found->second.spellId, "target_count"))', extra)

    def test_the_buff_is_one_per_shaman_and_doubles_the_generation(self):
        start = self.code[self.code.index("void Start("):self.code.index("double HitPctOf(")]
        self.assertIn("Buff& buff = buffs[key]; stamp = buff.stamp = ++stamps;", start)
        self.assertIn("Put(player, spellId, rune, true);", start)
        put = self.code[self.code.index("void Put("):self.code.index("void Pulse(")]
        self.assertIn("{Source::Temporary, Stat::MaelstromGeneration, id, DoublesGeneration, Bucket::Flat}", put)
        self.assertIn("constexpr double DoublesGeneration = 100.0;", self.code)
        self.assertIn('if (rune == Rune::EarthAscendance) Stats::AddContribution(guid, {Source::Temporary, Stat::SpecificReduction, id, Numbers::Num(spellId, "damage_reduction_pct"), Bucket::Flat});', put)
        self.assertIn('CostCut::Stand(player, "Lava Burst", CutKey, on && rune == Rune::FlameAscendance ? 100.0 : 0.0);', put)

    def test_the_pulse_ends_the_buff_and_heals_for_the_water_rune(self):
        pulse = self.code[self.code.index("void Pulse("):self.code.index("void Start(")]
        self.assertIn("found == buffs.end() || found->second.stamp != stamp", pulse)
        self.assertIn("over = !Holds(Now(), buff.until) || !player->IsInWorld() || !player->IsAlive();", pulse)
        self.assertIn("Put(player, buff.spellId, buff.rune, false);", pulse)
        self.assertIn('if (buff.rune == Rune::WaterAscendance) Heal(player, buff.spellId, double(player->GetMaxHealth()) * Numbers::Num(buff.spellId, "life_regen_pct") / 100.0 * tick);', pulse)

    def test_a_primary_cast_fires_bolts_at_more_enemies_than_it_hit(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void Multipliers(")]
        self.assertIn("if (Fires(Classes::CategoryOf(spellId), up)) Bolts(player, spellId, targets);", cast)
        bolts = self.code[self.code.index("void Bolts("):self.code.index("} // namespace bool Is(")]
        self.assertIn("std::find(targets.begin(), targets.end(), enemy) != targets.end()", bolts)
        self.assertIn('Tune("ascendance_bolt_radius_yards")', bolts)
        self.assertIn('auto const count = std::size_t(Numbers::Num(BaseId(), "target_count"));', bolts)
        self.assertIn('BoltPct(HitPctOf(primary), Numbers::Num(BaseId(), "damage_share_pct"))', bolts)
        self.assertIn("Combat::Strike(player, enemy, primary, pct);", bolts)
        self.assertIn("PrimaryBasePct(spellId).value_or(Numbers::Num(spellId, \"damage_pct\"))", self.code)

    def test_eternal_ascendance_counts_the_maelstrom_a_secondary_spends(self):
        casting = self.code[self.code.index("void Casting("):self.code.index("void Cast(")]
        self.assertIn('Classes::CategoryOf(spellId) != "Secondary"', casting)
        self.assertIn('Numbers::Get(spellId, "cost_resource").value_or(0.0)', casting)
        self.assertIn('Numbers::Num(buff.spellId, "per_trigger_resource")', casting)
        self.assertIn("buff.carried = more.remainder; buff.extended += more.addMs; buff.until += more.addMs;", casting)

    def test_the_bonus_uses_the_element_the_hit_really_deals(self):
        mult = self.code[self.code.index("void Multipliers("):self.code.index("unsigned ExtraChainJumps(")]
        self.assertIn("char const* dealt = DC::Combat::Shaman::Element(player, spellId);", mult)
        self.assertIn('Bonus(buff.rune, element, Numbers::Num(BaseId(), "damage_bonus_pct"), Numbers::Num(buff.spellId, "damage_bonus_pct"))', mult)
        self.assertIn('AddFactor(out, "Ascendance", bonus);', mult)


if __name__ == "__main__":
    unittest.main()
