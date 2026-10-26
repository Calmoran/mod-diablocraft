"""Siphon Blood and its five runes (src/classes/necromancer/dc_necromancer_siphon_blood*.h/.cpp, the dispatch in
dc_necromancer.cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/necromancer_siphon_blood/harness.cpp compiles the real
    dc_necromancer_siphon_blood_math.h with the sheets' own rune names and numbers: each rune name is its rune; the strikes
    come every base interval shortened by the attack speed; a strike carries its share of the skill's damage for a second;
    Power Shift adds its bonus for each strike up to the cap; Purity of Essence pays more only at full health; the clock
    counts whole intervals and keeps the rest. Planted differences in a scratch copy must each make it fail.
  * **The code reads what the sheets state.** Every token dc_necromancer_siphon_blood.cpp reads by name is a row of
    necromancer_skill_values.csv for Siphon Blood (or the rune that states it), the generated value map says whose record
    holds it, and the numbers are the researched ones: 150% a second, 15 Essence a strike, 2% of Life a second (Drain Life
    6%), Suppress 75%, Purity of Essence 19, Power Shift 10% up to 10 stacks, Blood Sucker 40 yards. The tick is a tunable
    with the power file's 0.35 seconds.
  * **The wiring.** The engine's hit on the cast is none, the first strike lands with the cast, the channel ends when the
    core's channel does, and a channel pays its Essence on each strike, not once for the cast.

What it does not prove: anything on a running server. Blood Sucker's pull of health globes waits for the globes.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_siphon_blood.py
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
MATH = "src/classes/necromancer/dc_necromancer_siphon_blood_math.h"
HARNESS = MODULE / "tests/necromancer_siphon_blood/harness.cpp"
CODE = MODULE / "src/classes/necromancer/dc_necromancer_siphon_blood.cpp"
DISPATCH = MODULE / "src/classes/necromancer/dc_necromancer.cpp"
SKILL = "Siphon Blood"


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


def scratch_tree(mutate=None):
    key = MATH[len("src/"):]
    files = {key: (MODULE / MATH).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {MATH}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [float(tunables()["siphon_blood_tick_seconds"]["d3_value"]), value("", "damage_pct"),
               value("Power Shift", "damage_bonus_pct"), value("Power Shift", "max_stacks_count"),
               value("", "generated_resource"), value("Purity of Essence", "gain_resource")] + runes()
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 24, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('if (name == "Drain Life")\n            return Rune::DrainLife;', 'if (name == "Drain Life")\n            return Rune::Suppress;')),
            ("attack speed slows the strikes", ("baseSeconds / attacksPerSecond", "baseSeconds * attacksPerSecond")),
            ("no speed still strikes", ("baseSeconds > 0 && attacksPerSecond > 0 ?", "baseSeconds > 0 ?")),
            ("a strike is the whole second", ("damagePct * std::max(0.0, tickSeconds)", "damagePct")),
            ("a strike is a tick longer", ("damagePct * std::max(0.0, tickSeconds)", "damagePct * std::max(0.0, tickSeconds + 1.0)")),
            ("Power Shift is not a percent", ("std::max(0.0, bonusPct) / 100.0 * stacks", "std::max(0.0, bonusPct) * stacks")),
            ("Power Shift ignores the stacks", ("/ 100.0 * stacks", "/ 100.0")),
            ("a negative bonus weakens the strike", ("std::max(0.0, bonusPct)", "bonusPct")),
            ("stacks have no cap", ("return std::min(stacks + 1, maxStacks);", "return stacks + 1;")),
            ("a strike gives two stacks", ("return std::min(stacks + 1, maxStacks);", "return std::min(stacks + 2, maxStacks);")),
            ("full health pays the plain", ("return fullHealth && gainedAtFullHealth > 0 ? gainedAtFullHealth : gained;", "return gained;")),
            ("every strike pays the larger", ("return fullHealth && gainedAtFullHealth > 0 ? gainedAtFullHealth : gained;", "return gainedAtFullHealth > 0 ? gainedAtFullHealth : gained;")),
            ("no larger number pays nothing", ("fullHealth && gainedAtFullHealth > 0 ?", "fullHealth ?")),
            ("the clock loses its rest", ("clock -= interval;", "clock = 0;")),
            ("an interval is never due", ("while (clock >= interval && due < cap)", "while (clock > interval && due < cap)")),
            ("the clock has no cap", ("due < cap)", "true)")),
            ("no interval is always due", ("if (interval <= 0)\n        {\n            clock = 0;\n            return 0;\n        }", "if (interval <= 0)\n        {\n            clock = 0;\n            return 1;\n        }")),
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
        self.assertEqual(runes(), ["Suppress", "Purity of Essence", "Drain Life", "Power Shift", "Blood Sucker"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", t) for t in ("generated_resource", "damage_pct", "heal_pct")], [15, 150, 2])
        self.assertEqual(value("Suppress", "slow_pct"), 75)
        self.assertEqual(value("Purity of Essence", "gain_resource"), 19)
        self.assertEqual(value("Drain Life", "heal_pct"), 6)
        self.assertEqual([value("Power Shift", t) for t in ("damage_bonus_pct", "max_stacks_count")], [10, 10])
        self.assertEqual(value("Blood Sucker", "radius_yards"), 40)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet_tokens = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "damage_bonus_pct", "max_stacks_count", "generated_resource", "gain_resource",
                                  "slow_pct", "heal_pct"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "generated_resource"), ("", "damage_pct"), ("", "heal_pct"), ("Suppress", "slow_pct"),
                            ("Purity of Essence", "gain_resource"), ("Drain Life", "heal_pct"),
                            ("Power Shift", "damage_bonus_pct"), ("Power Shift", "max_stacks_count"),
                            ("Suppress", "damage_pct"), ("Drain Life", "generated_resource")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)

    def test_the_skill_pays_on_each_strike_as_its_tooltip_says(self):
        says = {r["skill_name"] for r in read(D3 / "necromancer_skills.csv") if "each time damage is dealt" in r["full_tooltip_text"]}
        self.assertEqual(says, {SKILL})


class Records(unittest.TestCase):
    """The skill and its five runes are real channels, so the loop finds the spell it is holding (combat_0099)."""

    def records(self):
        import re
        migration = (MODULE / "data/sql/db-world/updates/combat_0099_demon_hunter_rapid_fire_and_siphon_blood_channels.sql").read_text(encoding="utf-8")
        found = re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", migration)
        columns = [c.strip(" `\n") for c in found.group(1).split(",")]
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}
        out = {}
        for name, spell in ids.items():
            if name == "Siphon Blood" or name.startswith("Siphon Blood - "):
                row = re.search(r"\(%d,([^\n]*)\)[,;]?\n" % spell, migration)
                values = ("%d," % spell + row.group(1)).split(",")
                out[name] = dict(zip(columns, values))
        return out

    def test_the_skill_and_each_rune_record_is_the_channel_itself(self):
        records = self.records()
        self.assertEqual(len(records), 6)
        wizard = {name: record for name, record in records.items()}
        for name, record in wizard.items():
            with self.subTest(name):
                self.assertEqual(int(record["AttributesEx"]) & 0x4, 0x4)         # SPELL_ATTR1_IS_CHANNELED
                self.assertEqual(record["DurationIndex"], "21")                  # the Wizard channels' own, until released
                self.assertEqual(record["EffectAura_1"], "0")                    # no tick damage of its own
                self.assertEqual(record["ManaCost"], "0")                        # no cost per tick: Siphon Blood has none
                self.assertNotEqual(record["ChannelInterruptFlags"], "0")        # the stock channel's interrupts

    def test_the_duration_is_the_wizard_channels(self):
        migration = (MODULE / "data/sql/db-world/updates/combat_0099_demon_hunter_rapid_fire_and_siphon_blood_channels.sql").read_text(encoding="utf-8")
        import re
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", migration).group(1).split(",")]
        row = re.search(r"\(83104,([^\n]*)\)[,;]?\n", migration)
        ray = dict(zip(columns, ("83104," + row.group(1)).split(",")))
        for record in self.records().values():
            self.assertEqual(record["DurationIndex"], ray["DurationIndex"])
            self.assertEqual(record["ChannelInterruptFlags"], ray["ChannelInterruptFlags"])


class Tunables(unittest.TestCase):
    def test_the_tick_is_the_power_files_number(self):
        row = tunables()["siphon_blood_tick_seconds"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("0.35", "", "seconds"))
        self.assertIn("SF_15", row["notes"])
        self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_the_code_reads_exactly_this(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {"siphon_blood_tick_seconds", "siphon_blood_heal_seconds", "siphon_blood_slow_linger_seconds"})


    def test_the_heal_is_the_tooltips_every_second(self):
        tooltip = [r["full_tooltip_text"] for r in read(D3 / "necromancer_skills.csv") if r["skill_name"] == SKILL][0]
        self.assertIn("{heal_pct} of your total health every second while channeled", tooltip)
        row = tunables()["siphon_blood_heal_seconds"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("1", "", "seconds"))
        self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_the_slow_linger_is_a_row_longer_than_the_tick_and_says_it_is_not_d3s(self):
        rows = tunables()
        row = rows["siphon_blood_slow_linger_seconds"]
        self.assertEqual((row["d3_value"], row["value"], row["unit"]), ("1", "", "seconds"))
        self.assertIn("not D3", row["notes"])
        self.assertGreater(float(row["d3_value"]), float(rows["siphon_blood_tick_seconds"]["d3_value"]))
        text = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.assertNotIn("SlowLingerSeconds", text)
        self.assertIn('Slow(player, target, Numbers::Num(spellId, "slow_pct"), Tune("siphon_blood_slow_linger_seconds"));', text)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", DISPATCH.read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams_for_the_channel(self):
        self.assertIn("if (auto blood = SiphonBlood::BasePct(spellId)) return blood;", self.dispatch)
        self.assertIn("SiphonBlood::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("SiphonBlood::RegisterScripts();", self.dispatch)
        self.assertIn("if (!points || SiphonBlood::PaysByStrike(spellId)) return;", self.dispatch)

    def test_the_engine_hit_is_none_and_the_first_strike_lands_with_the_cast(self):
        self.assertIn("std::optional<double>(0.0) : std::nullopt", self.code)
        self.assertIn("Strike(player, targets.front(), channel);", self.code)

    def test_the_channel_ends_with_the_cores(self):
        self.assertIn("player->GetCurrentSpell(CURRENT_CHANNELED_SPELL)", self.code)
        self.assertIn("current->GetSpellInfo()->Id != channel.spellId", self.code)
        self.assertIn("PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED", self.code)

    def test_each_strike_pays_and_tells_the_engine(self):
        self.assertIn('PayEssence(player, spellId, EssenceOfTick(Numbers::Num(spellId, "generated_resource"), gainedAtFull,', self.code)
        self.assertIn("Combat::Connected(player, spellId, 1);", self.code)

    def test_it_heals_every_second_by_the_runes_number(self):
        self.assertIn('Numbers::Num(channel.spellId, "heal_pct") / 100.0', self.code)
        self.assertNotIn("HealEverySeconds", self.code)
        self.assertIn('Due(channel.healClock, diff, Tune("siphon_blood_heal_seconds") * 1000.0)', self.code)

    def test_purity_reads_full_health_and_only_that_rune_reads_its_number(self):
        self.assertIn("player->GetHealth() >= player->GetMaxHealth()", self.code)
        self.assertIn('rune == Rune::PurityOfEssence ? Numbers::Num(spellId, "gain_resource") : 0.0', self.code)


if __name__ == "__main__":
    unittest.main()
