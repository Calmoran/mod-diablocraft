"""The follower skills (src/classes/follower/, diablocraft-gh1c1.6): the shared framework and the Templar's eight.

What this proves, and how:

  * **The sheet is the files' numbers.** data/d3/followers_skill_numbers.csv holds each number of the Templar's skills with its source;
    with the game archives on this machine each one that a power file holds is read back from the decoded file (Heal and Loyalty as
    shares of the Healing table, Intervene's taunt and radius, Intimidate's slow, Charge's and Onslaught's damage, Guardian's
    knockback), and the planner's absolute Heal and Loyalty figures are those shares of the table at level 70.
  * **The migration is the sheet.** generate_follower_skills.py's render is the world migration and its generated copy.
  * **The rules.** tests/follower_skills/harness.cpp compiles the real dc_follower_skill_rules.h with the sheet's own numbers: a number
    scales with the main stat up to the cap, a tier opens at its level, a pick or the all-skills relic puts a skill on, the relic halves
    a cooldown, the arithmetic of a heal, a hit, a fatal blow and a pulse. Each rule is killed by a planted difference.
  * **The wiring.** What the C++ reads (the tables, the stat and swing the follower's gear exports, the stock spells it holds and heals
    with) and the three seams in the shared files, one pin each.

What it does not prove: the casts, taunts, stuns, slows, heals and the cheat-death save on a running server (the test sheet's checks).

    python mod-diablocraft/scripts/tests/classes/test_follower_skills.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import decode_pow
import generate_follower_skills as gen
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/follower/dc_follower_skill_rules.h"
HARNESS = MODULE / "tests/follower_skills/harness.cpp"
FOLDER = MODULE / "src/classes/follower"

# The Templar's skills and the tokens each must hold (the sheet may hold more).
TEMPLAR = {
    "heal": {"heal_table_share", "life_below_pct"},
    "intervene": {"taunt_seconds", "radius_yards"},
    "loyalty": {"aura_radius_yards", "heal_table_share_per_second"},
    "intimidate": {"slow_pct", "slow_seconds"},
    "charge": {"damage_pct", "stun_seconds", "stun_radius_yards", "cast_range_yards"},
    "onslaught": {"damage_pct", "vulnerability_pct", "vulnerability_seconds", "radius_yards", "cast_range_yards"},
    "inspire": {"mana_per_second", "hatred_per_second", "wrath_per_second", "arcane_power_per_second"},
    "guardian": {"knockback_yards", "heal_life_pct", "shield_seconds"},
}


# The Scoundrel's, likewise.
SCOUNDREL = {
    "crippling-shot": {"damage_pct", "slow_pct", "slow_seconds", "cast_range_yards"},
    "powered-shot": {"damage_pct", "radius_yards", "stun_chance_pct", "stun_seconds", "cast_range_yards"},
    "hysteria": {"damage_bonus_pct", "bonus_seconds"},
    "anatomy": {"crit_chance_pct", "aura_radius_yards"},
    "piercing-shot": {"damage_pct", "vulnerability_pct", "vulnerability_seconds", "line_width_yards", "cast_range_yards"},
    "multishot": {"damage_pct", "extra_bolts", "passive_chance_pct", "cast_range_yards"},
    "vanish": {"conceal_seconds"},
    "nights-veil": {"radius_yards", "seconds", "cast_range_yards"},
}


# The Enchantress', likewise.
ENCHANTRESS = {
    "charm": {"duration_seconds", "cast_range_yards"},
    "temporal-pulse": {"damage_pct", "radius_yards", "slow_pct", "slow_seconds", "cast_range_yards"},
    "amplification": {"bonus_pct"},
    "prophetic-harmony": {"cooldown_reduction_pct"},
    "powered-shield": {"ranged_reduction_pct", "armor_pct", "slow_pct", "slow_seconds"},
    "erosion": {"damage_pct", "seconds", "vulnerability_pct", "radius_yards", "tick_seconds", "cast_range_yards"},
    "focused-mind": {"attack_speed_pct", "aura_radius_yards"},
    "fates-lapse": {"slow_pct", "slow_seconds", "radius_yards"},
}


def read(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, token, follower="templar", high=False):
    rows = [r for r in read("followers_skill_numbers.csv") if (r["key"], r["skill_id"], r["token"]) == (follower, skill, token)]
    assert len(rows) == 1, (skill, token, len(rows))
    cell = rows[0]["value_max" if high else "value"]
    return float(cell) if cell != "" else None


def enchantress(skill, token, high=False):
    return value(skill, token, follower="enchantress", high=high)


def scoundrel(skill, token, high=False):
    return value(skill, token, follower="scoundrel", high=high)


def rule(token):
    rows = [r for r in read("followers_skill_numbers.csv") if (r["key"], r["skill_id"], r["token"]) == ("", "", token)]
    assert len(rows) == 1, token
    return float(rows[0]["value"])


def healing(level):
    return float(next(r for r in read("healing_table.csv") if int(r["level"]) == level)["value"])


def tier_pair(follower_key, tier):
    rows = [r for r in read("followers.csv") if r["key"] == follower_key and r["kind"] == "skill" and r["tier"] == str(tier)]
    return [r["skill_id"] for r in rows]


def scratch_tree(mutate=None):
    files = {HEADER[len("src/"):]: (MODULE / HEADER).read_text(encoding="utf-8")}
    if mutate:
        old, new = mutate
        if files[HEADER[len("src/"):]].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        files[HEADER[len("src/"):]] = files[HEADER[len("src/"):]].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    first, second = tier_pair("templar", 1)
    numbers = [rule("main_stat_cap"), value("guardian", "heal_life_pct"), value("guardian", "heal_life_pct", high=True),
               value("intervene", "taunt_seconds"), value("intervene", "taunt_seconds", high=True), value("heal", "life_below_pct"),
               value("heal", "heal_table_share"), value("charge", "damage_pct"), healing(70), first, second, value("inspire", "fury_generated_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Sheets(unittest.TestCase):
    def test_the_migration_is_the_sheets_render(self):
        text = gen.render()
        self.assertEqual((MODULE / "data/sql/db-world/updates" / gen.MIGRATION).read_text(encoding="utf-8"), text)
        self.assertEqual((MODULE / "data/generated" / gen.MIGRATION).read_text(encoding="utf-8"), text)

    def test_every_templar_skill_has_its_numbers_and_every_row_its_source(self):
        rows = read("followers_skill_numbers.csv")
        for skill, tokens in TEMPLAR.items():
            held = {r["token"] for r in rows if (r["key"], r["skill_id"]) == ("templar", skill)}
            self.assertLessEqual(tokens, held, skill)
        for row in rows:
            self.assertTrue(row["source"].strip() and row["unit"].strip(), row)
        self.assertEqual(rule("main_stat_cap"), 25000)
        # The Templar's skills are the sheet's: followers.csv holds the same eight.
        self.assertEqual({r["skill_id"] for r in read("followers.csv") if r["key"] == "templar" and r["kind"] == "skill"}, set(TEMPLAR))

    def test_every_scoundrel_skill_has_its_numbers_and_the_eight_are_followers_csvs(self):
        rows = read("followers_skill_numbers.csv")
        for skill, tokens in SCOUNDREL.items():
            held = {r["token"] for r in rows if (r["key"], r["skill_id"]) == ("scoundrel", skill)}
            self.assertLessEqual(tokens, held, skill)
        self.assertEqual({r["skill_id"] for r in read("followers.csv") if r["key"] == "scoundrel" and r["kind"] == "skill"}, set(SCOUNDREL))

    def test_every_enchantress_skill_has_its_numbers_and_the_eight_are_followers_csvs(self):
        rows = read("followers_skill_numbers.csv")
        for skill, tokens in ENCHANTRESS.items():
            held = {r["token"] for r in rows if (r["key"], r["skill_id"]) == ("enchantress", skill)}
            self.assertLessEqual(tokens, held, skill)
        self.assertEqual({r["skill_id"] for r in read("followers.csv") if r["key"] == "enchantress" and r["kind"] == "skill"}, set(ENCHANTRESS))
        # Her tiers open at 15, 20, 25 and 30 (R1a section 5), so the pairs are the sheet's.
        self.assertEqual(sorted({int(r["d3_level"]) for r in read("followers.csv") if r["key"] == "enchantress" and r["kind"] == "skill"}), [15, 20, 25, 30])

    def test_the_enchantress_scaling_numbers_have_a_maximum_above_the_minimum(self):
        for skill, token in (("temporal-pulse", "slow_seconds"), ("amplification", "bonus_pct"), ("prophetic-harmony", "cooldown_reduction_pct"),
                             ("powered-shield", "slow_seconds"), ("erosion", "seconds"), ("focused-mind", "attack_speed_pct"),
                             ("fates-lapse", "slow_seconds")):
            self.assertGreater(enchantress(skill, token, high=True), enchantress(skill, token), (skill, token))

    def test_erosions_tick_is_the_standing_half_second(self):
        # No source gives the tick: the designer's standing default for a burn or bleed (AGENTS.md Numbers, 2026-10-22).
        self.assertEqual(enchantress("erosion", "tick_seconds"), 0.5)
        row = next(r for r in read("followers_skill_numbers.csv") if (r["key"], r["skill_id"], r["token"]) == ("enchantress", "erosion", "tick_seconds"))
        self.assertIn("standing default", row["source"])

    def test_every_text_value_fits_its_column_and_the_migration_widens_the_unit(self):
        # followers_0010 stopped the world server: 'percent of weapon damage, Arcane' is 33 characters and the unit column held 32.
        text = gen.render()
        widths = {name: int(width) for name, width in re.findall(r"(skill_id|token|unit) VARCHAR\((\d+)\)", text.split("\n")[2])}
        self.assertEqual(widths, {"skill_id": gen.SKILL_WIDTH, "token": gen.TOKEN_WIDTH, "unit": gen.UNIT_WIDTH})
        for row in read("followers_skill_numbers.csv"):
            for column, width in widths.items():
                self.assertLessEqual(len(row[column]), width, (row["key"], row["skill_id"], row["token"], column))
        # The table exists on dev at 32 from followers_0008 and 0009 (CREATE IF NOT EXISTS leaves it): the file widens it before the rows.
        self.assertIn(f"ALTER TABLE dc_follower_skill_value MODIFY unit VARCHAR({gen.UNIT_WIDTH}) NOT NULL;", text)
        self.assertLess(text.index("ALTER TABLE dc_follower_skill_value"), text.index("DELETE FROM dc_follower_skill_value;"))
        self.assertLess(text.index("ALTER TABLE dc_follower_skill_value"), text.index("INSERT INTO dc_follower_skill_value"))
        self.assertGreater(gen.UNIT_WIDTH, 32)
        # The generator refuses a row that does not fit, at the column's edge and one past it.
        row = {"skill_id": "x", "token": "y", "unit": "u" * gen.UNIT_WIDTH}
        gen.fits(row, "edge")
        row["unit"] += "u"
        with self.assertRaises(ValueError):
            gen.fits(row, "one past")
        with self.assertRaises(ValueError):
            gen.fits({"skill_id": "s" * (gen.SKILL_WIDTH + 1), "token": "y", "unit": "u"}, "skill")
        with self.assertRaises(ValueError):
            gen.fits({"skill_id": "s", "token": "t" * (gen.TOKEN_WIDTH + 1), "unit": "u"}, "token")

    def test_piercing_shots_line_is_the_standing_three_yards(self):
        # No source gives the width: the designer's standing default for a line attack (AGENTS.md Numbers, 2026-10-22).
        self.assertEqual(scoundrel("piercing-shot", "line_width_yards"), 3)
        row = next(r for r in read("followers_skill_numbers.csv") if (r["key"], r["skill_id"], r["token"]) == ("scoundrel", "piercing-shot", "line_width_yards"))
        self.assertIn("standing default", row["source"])

    def test_the_scoundrels_scaling_numbers_have_a_maximum_above_the_minimum(self):
        for skill, token in (("crippling-shot", "slow_seconds"), ("powered-shot", "stun_seconds"), ("hysteria", "bonus_seconds"),
                             ("anatomy", "crit_chance_pct"), ("piercing-shot", "vulnerability_seconds"), ("multishot", "passive_chance_pct"),
                             ("vanish", "conceal_seconds"), ("nights-veil", "seconds")):
            self.assertGreater(scoundrel(skill, token, high=True), scoundrel(skill, token), (skill, token))

    def test_a_number_that_scales_has_a_maximum_above_its_minimum(self):
        for skill, token in (("intervene", "taunt_seconds"), ("intimidate", "slow_seconds"), ("charge", "stun_seconds"),
                             ("onslaught", "vulnerability_seconds"), ("guardian", "heal_life_pct")):
            self.assertGreater(value(skill, token, high=True), value(skill, token), (skill, token))

    def test_the_planners_absolute_heals_are_shares_of_the_table_at_the_top_level(self):
        texts = {r["skill_id"]: r["text"] for r in read("followers.csv") if r["key"] == "templar"}
        planner_heal = float(re.search(r"for (\d+) Life", texts["heal"]).group(1))
        planner_loyalty = float(re.search(r"Regenerates (\d+) Life per second", texts["loyalty"]).group(1))
        self.assertAlmostEqual(planner_heal / (value("heal", "heal_table_share") * healing(70)), 1, delta=0.001)
        self.assertAlmostEqual(planner_loyalty / (value("loyalty", "heal_table_share_per_second") * healing(70)), 1, delta=0.001)

    def test_the_numbers_are_the_decoded_power_files(self):
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")

        def sf(name):
            return decode_pow.parse_power(decode_pow.extract(f"Power/{name}.pow"))["sf"]

        def coefficient(text):
            match = re.fullmatch(r"\(?([0-9.]+)\)?\s*\*\s*Table\(Healing,\s*Level\)", str(text).strip())
            self.assertIsNotNone(match, text)
            return float(match.group(1))

        heal, loyalty, intervene, intimidate = sf("Templar_Heal_110"), sf("Templar_Loyalty"), sf("Templar_Intervene"), sf("Templar_Intimidate")
        charge, onslaught, guardian = sf("Templar_ShieldCharge"), sf("Templar_Onslaught"), sf("Templar_Guardian")
        self.assertAlmostEqual(coefficient(heal[0]), value("heal", "heal_table_share"))
        self.assertAlmostEqual(coefficient(loyalty[1]), value("loyalty", "heal_table_share_per_second"))
        self.assertAlmostEqual(float(str(loyalty[0])), value("loyalty", "aura_radius_yards"))
        self.assertAlmostEqual(float(str(intervene[3])), value("intervene", "taunt_seconds"))
        self.assertAlmostEqual(float(str(intervene[4])), value("intervene", "radius_yards"))
        self.assertAlmostEqual(float(str(intimidate[0])) * 100, value("intimidate", "slow_pct"))
        self.assertAlmostEqual(float(str(intimidate[1])), value("intimidate", "slow_seconds"))
        self.assertAlmostEqual(float(str(charge[0])) * 100, value("charge", "damage_pct"))
        self.assertAlmostEqual(float(str(charge[4])), value("charge", "stun_seconds"))
        self.assertAlmostEqual(float(str(charge[5])), value("charge", "stun_radius_yards"))
        self.assertAlmostEqual(float(str(onslaught[0])) * 100, value("onslaught", "damage_pct"))
        self.assertAlmostEqual(float(str(guardian[5])), value("guardian", "knockback_yards"))
        focused, armor, ward, scorched = sf("Enchantress_FocusedMind"), sf("Enchantress_PoweredArmor"), sf("Enchantress_MissileWard"), sf("Enchantress_ScorchedEarth")
        self.assertAlmostEqual(float(str(focused[1])) * 100, enchantress("focused-mind", "attack_speed_pct"))
        self.assertAlmostEqual(float(str(focused[0])), enchantress("focused-mind", "aura_radius_yards"))
        self.assertAlmostEqual(float(str(armor[0])) * 100, enchantress("powered-shield", "armor_pct"))
        self.assertAlmostEqual(float(str(armor[1])) * 100, enchantress("powered-shield", "slow_pct"))
        self.assertAlmostEqual(float(str(ward[0])) * 100, enchantress("powered-shield", "ranged_reduction_pct"))
        self.assertAlmostEqual(float(str(scorched[2])), enchantress("erosion", "radius_yards"))
        self.assertAlmostEqual(float(str(scorched[1])), enchantress("erosion", "seconds"))
        crippling, powered, hysteria, anatomy = sf("Scoundrel_CripplingShot"), sf("Scoundrel_PowerShot"), sf("Scoundrel_Hysteria"), sf("Scoundrel_Anatomy")
        multishot, passive = sf("X1_Scoundrel_Multishot"), sf("X1_Scoundrel_Multishot_Passive")
        self.assertAlmostEqual(float(str(crippling[3])) * 100, scoundrel("crippling-shot", "damage_pct"))
        self.assertAlmostEqual(float(str(crippling[0])) * 100, scoundrel("crippling-shot", "slow_pct"))
        self.assertAlmostEqual(float(str(powered[8])), scoundrel("powered-shot", "radius_yards"))
        self.assertAlmostEqual(float(str(powered[1])) * 100, scoundrel("powered-shot", "stun_chance_pct"))
        self.assertAlmostEqual(float(str(hysteria[0])) * 100, scoundrel("hysteria", "damage_bonus_pct"))
        self.assertAlmostEqual(float(str(hysteria[1])), scoundrel("hysteria", "bonus_seconds"))
        self.assertAlmostEqual(float(str(anatomy[1])) * 100, scoundrel("anatomy", "crit_chance_pct"))
        self.assertAlmostEqual(float(str(anatomy[0])), scoundrel("anatomy", "aura_radius_yards"))
        self.assertAlmostEqual(float(str(multishot[1])) * 100, scoundrel("multishot", "damage_pct"))
        self.assertAlmostEqual(float(str(multishot[2])), scoundrel("multishot", "extra_bolts"))
        self.assertAlmostEqual(float(str(passive[2])), scoundrel("multishot", "extra_bolts"))
        self.assertAlmostEqual(float(str(multishot[4])) * 100, scoundrel("multishot", "passive_chance_pct"))


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 40, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("the share ignores the cap", ("std::clamp(mainStat / cap, 0.0, 1.0)", "std::clamp(mainStat / 20000.0, 0.0, 1.0)")),
            ("the share has no top", ("std::clamp(mainStat / cap, 0.0, 1.0)", "std::max(mainStat / cap, 0.0)")),
            ("a number never scales", ("return high > low ? low + (high - low) * std::clamp(share, 0.0, 1.0) : low;", "return low;")),
            ("a number scales past its maximum", ("low + (high - low) * std::clamp(share, 0.0, 1.0)", "low + (high - low) * std::max(share, 0.0)")),
            ("a tier opens a level late", ("return level >= tierLevel;", "return level > tierLevel;")),
            ("a pick in a closed tier is on", ("return tierOpen && (picked || allSkills);", "return picked || (tierOpen && allSkills);")),
            ("the relic does not give every skill", ("return tierOpen && (picked || allSkills);", "return tierOpen && picked;")),
            ("the relic does not halve the cooldown", ("(halved ? 0.5 : 1.0)", "1.0")),
            ("a skill is ready a millisecond early", ("return nowMs >= readyAtMs;", "return nowMs + 1 >= readyAtMs;")),
            ("a heal is asked for the dead", ("return life > 0 && maxLife > 0 && life * 100.0 < maxLife * belowPct;", "return maxLife > 0 && life * 100.0 < maxLife * belowPct;")),
            ("a heal is asked at the share, not below it", ("life * 100.0 < maxLife * belowPct", "life * 100.0 <= maxLife * belowPct")),
            ("the table heal forgets the share", ("return share > 0 && tableAtLevel > 0 ? share * tableAtLevel : 0.0;", "return tableAtLevel;")),
            ("the Life heal is the whole Life", ("return maxLife > 0 && pct > 0 ? maxLife * pct / 100.0 : 0.0;", "return maxLife;")),
            ("a hit is always the low of the swing", ("swingMin + (std::max(swingMax, swingMin) - swingMin) * std::clamp(roll, 0.0, 1.0)", "swingMin")),
            ("a hit is the whole swing", ("return pct > 0 && swing > 0 ? pct / 100.0 * swing : 0.0;", "return swing;")),
            ("a blow is fatal one short", ("return damage > 0 && damage >= health;", "return damage > 0 && damage > health;")),
            ("a pulse is lost", ("clockMs -= periodMs;\n        ++due;", "clockMs = 0;\n        ++due;")),
            ("a pick names the first for both", ("if (text == \"2\" || (!text.empty() && text == second))\n        return 1;", "if (text == \"2\")\n        return 1;")),
            ("a critical hit is the sheet's damage alone", ("return 1.0 + std::max(0.0, critDamagePct) / 100.0;", "return std::max(0.0, critDamagePct) / 100.0;")),
            ("a chance is always rolled", ("return chancePct > 0 && roll * 100.0 < chancePct;", "return chancePct > 0;")),
            ("a bonus is the percent alone", ("return 1.0 + std::max(0.0, pct) / 100.0;", "return std::max(0.0, pct) / 100.0;")),
            ("Inspire scales by the percent alone", ("return std::max(pct, 0.0) / 100.0 + 1.0;", "return std::max(pct, 0.0) / 100.0;")),
            ("Inspire's negative percent takes generation away", ("return std::max(pct, 0.0) / 100.0 + 1.0;", "return pct / 100.0 + 1.0;")),
            ("an effect holds a millisecond long", ("return nowMs < untilMs;", "return nowMs <= untilMs;")),
            ("a line has no ends", ("std::clamp(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0)", "((px - ax) * dx + (py - ay) * dy) / length2")),
            ("a line is wider than its width", ("nx * nx + ny * ny <= halfWidth * halfWidth", "nx * nx + ny * ny <= 4 * halfWidth * halfWidth")),
            ("the bolts all go to the first enemy", ("return available ? unsigned(bolt % available) : 0;", "return 0;")),
            ("a pool deals its total every tick", ("totalPct * std::min(tickSeconds, seconds) / seconds", "totalPct")),
            ("a pool is not capped by its seconds", ("totalPct * std::min(tickSeconds, seconds) / seconds", "totalPct * tickSeconds / seconds")),
            ("a melee blow is reduced too", ("return melee ? 1.0 : 1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0;", "return 1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0;")),
            ("a ranged blow is not reduced", ("return melee ? 1.0 : 1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0;", "return 1.0;")),
            ("the bonus is amplified by the percent alone", ("return highest > 0 && pct > 0 ? highest * pct / 100.0 : 0.0;", "return pct;")),
            ("the highest is the last", ("if (values[i] > values[best])", "if (values[i] >= values[best])")),
            ("the highest is the first value", ("std::size_t best = 0;\n    for (std::size_t i = 1; i < count; ++i)", "std::size_t best = 0;\n    for (std::size_t i = 1; i < 1; ++i)")),
            ("a pool follows the map alone", ("return map == nowMap && instance == nowInstance;", "return map == nowMap;")),
            ("a pool follows the instance alone", ("return map == nowMap && instance == nowInstance;", "return instance == nowInstance;")),
            ("a place is any place", ("return map == nowMap && instance == nowInstance;", "return true;")),
            ("the range is open at the top", ("return range > 0 && distance <= range;", "return range > 0 && distance < range;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


def flat(path):
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.skills = flat(FOLDER / "dc_follower_skills.cpp")
        self.templar = flat(FOLDER / "dc_follower_templar.cpp")
        self.scoundrel = flat(FOLDER / "dc_follower_scoundrel.cpp")
        self.enchantress = flat(FOLDER / "dc_follower_enchantress.cpp")

    def test_every_token_the_code_reads_is_a_row_of_the_sheet(self):
        rows = {(r["key"], r["skill_id"], r["token"]) for r in read("followers_skill_numbers.csv")}
        read_by_templar = set(re.findall(r'(?:Raw\(c\.follower|Num\(c), "([a-z_]+)", "([a-z_]+)"\)', self.templar))
        self.assertGreaterEqual(len(read_by_templar), 20)
        for skill, token in read_by_templar:
            self.assertIn(("templar", skill, token), rows, (skill, token))
        read_by_scoundrel = set(re.findall(r'(?:Raw\(c\.follower|Num\(c), "([a-z-]+)", "([a-z_]+)"\)', self.scoundrel))
        # The reach of the four shots is read through the shared CanShoot with the skill's name.
        read_by_scoundrel |= {(skill, "cast_range_yards") for skill in ("crippling-shot", "powered-shot", "piercing-shot", "multishot")}
        self.assertGreaterEqual(len(read_by_scoundrel), 20)
        for skill, token in read_by_scoundrel:
            self.assertIn(("scoundrel", skill, token), rows, (skill, token))
        read_by_enchantress = set(re.findall(r'(?:Raw\(c\.follower|Num\(c), "([a-z-]+)", "([a-z_]+)"\)', self.enchantress))
        self.assertGreaterEqual(len(read_by_enchantress), 22)
        for skill, token in read_by_enchantress:
            self.assertIn(("enchantress", skill, token), rows, (skill, token))
        for token in re.findall(r'Rule\("([a-z_]+)"\)', self.skills):
            self.assertIn(("", "", token), rows, token)
        # Inspire reads its four per-second rows through a table of tokens.
        inspire = self.templar[self.templar.index("void Inspire("):self.templar.index("} // namespace")]
        for token in re.findall(r'"([a-z_]+_per_second)"', inspire):
            self.assertIn(("templar", "inspire", token), rows, token)

    def test_every_templar_skill_is_asked_whether_it_is_on_and_each_cast_starts_its_cooldown(self):
        for skill in TEMPLAR:
            self.assertIn(f'On(c, "{skill}")', self.templar, skill)
        for skill in ("heal", "intervene", "charge", "onslaught", "guardian"):
            self.assertIn(f'Ready(c, "{skill}")', self.templar, skill)
            self.assertEqual(self.templar.count(f'Spend(c, "{skill}");'), 1, skill)
        # A passive has no cooldown in dc_follower_skill, and the sheet's cooldowns are the ones the framework starts.
        cooldowns = {r["skill_id"]: r["cooldown_seconds"] for r in read("followers.csv") if r["key"] == "templar" and r["kind"] == "skill"}
        for skill in ("heal", "intervene", "charge", "onslaught", "guardian"):
            self.assertTrue(cooldowns[skill], skill)
        for skill in ("loyalty", "intimidate", "inspire"):
            self.assertFalse(cooldowns[skill], skill)

    def test_the_framework_reads_the_tables_the_migrations_write(self):
        self.assertIn("SELECT follower_id, tier, d3_level, skill_id, cooldown_seconds FROM dc_follower_skill", self.skills)
        self.assertIn("SELECT follower_id, skill_id, token, value, value_max FROM dc_follower_skill_value", self.skills)
        self.assertIn("SELECT follower, tier, skill_id FROM dc_character_follower_skill WHERE guid={}", self.skills)
        self.assertIn("REPLACE INTO dc_character_follower_skill (guid, follower, tier, skill_id)", self.skills)
        self.assertIn("DELETE FROM dc_character_follower_skill WHERE guid=", self.skills)
        characters = (MODULE / "data/sql/db-characters/updates/followers_0003_character_skill.sql").read_text(encoding="utf-8")
        for column in ("guid", "follower", "tier", "skill_id"):
            self.assertIn(f"`{column}`", characters)
        self.assertIn("PRIMARY KEY (`guid`, `follower`, `tier`)", characters)
        world = (MODULE / "data/sql/db-world/updates" / gen.MIGRATION).read_text(encoding="utf-8")
        self.assertIn("dc_follower_skill_value (follower_id TINYINT UNSIGNED NOT NULL, skill_id VARCHAR(32) NOT NULL, token VARCHAR(40) NOT NULL", world)

    def test_a_pick_is_made_in_the_hub_in_an_open_tier_and_kept_for_its_follower(self):
        pick = self.skills[self.skills.index("std::string TryPick("):self.skills.index("bool List(")]   # the checks, and the command that prints them
        self.assertIn("!player->IsAlive() || player->IsInCombat() || !World::IsInHub(player)", pick)
        self.assertIn("ChoiceOf(choice, pair[0]->id, pair[1]->id)", pick)
        self.assertIn("!TierOpen(player->GetLevel(), pair[0]->level)", pick)
        self.assertIn("picks[follower - 1][tier - 1] = skill;", pick)
        self.assertIn('{"skills", HandleSkills, SEC_PLAYER, Console::No}', self.skills)
        self.assertIn('{"skill", HandleSkill, SEC_PLAYER, Console::No}', self.skills)

    def test_a_skill_is_on_by_its_pick_the_tier_and_the_relic(self):
        on = self.skills[self.skills.index("bool On("):self.skills.index("double Rule(")]
        self.assertIn("picks[c.follower - 1][row->tier - 1] == skill", on)
        self.assertIn("return Active(picked, c.allSkills, TierOpen(c.level, row->level));", on)
        context = self.skills[self.skills.index("bool Context("):self.skills.index("bool On(")]
        self.assertIn('HasPower(player, follower, "cooldown_half")', context)
        self.assertIn('HasPower(player, follower, "all_skills")', context)
        self.assertIn("MainStatShare(stats.mainStat, Rule(\"main_stat_cap\"))", context)
        self.assertIn("SkillStatsOf(player, follower, stats)", context)
        num = self.skills[self.skills.index("double Num("):self.skills.index("bool Ready(")]
        self.assertIn("Scaled(found->second.low, found->second.high, c.share)", num)
        spend = self.skills[self.skills.index("void Spend("):self.skills.index("void Stun(")]
        self.assertIn("Now() + CooldownMs(row->cooldown, c.halved)", spend)

    def test_the_follower_goes_down_with_the_player_and_its_cooldowns_are_reset(self):
        died = self.skills[self.skills.index("void OnPlayerJustDied("):self.skills.index("void OnPlayerDeleteFromDB(")]
        self.assertIn("readyAt.clear();", died)
        self.assertIn("shieldUntil = 0;", died)

    def test_the_templars_skills_do_what_their_text_says(self):
        t = self.templar
        heal = t[t.index('On(c, "heal")'):t.index("// Loyalty")]
        self.assertIn('Below(player->GetHealth(), player->GetMaxHealth(), below) || Below(templar->GetHealth(), templar->GetMaxHealth(), below)', heal)
        self.assertIn('TableHeal(Raw(c.follower, "heal", "heal_table_share"), Table(c))', heal)
        self.assertIn("Heal(player, player, HealSpell, amount);", heal)
        self.assertIn("Heal(player, templar, HealSpell, amount);", heal)
        loyalty = t[t.index("// Loyalty"):t.index("if (inspired")]
        self.assertIn('InRange(templar->GetDistance(player), Raw(c.follower, "loyalty", "aura_radius_yards"))', loyalty)
        self.assertIn('TableHeal(Raw(c.follower, "loyalty", "heal_table_share_per_second"), Table(c)) * loyal', loyalty)
        self.assertIn("Heal(player, player, RegenerationSpell, amount);", loyalty)
        self.assertIn("Heal(player, templar, RegenerationSpell, amount);", loyalty)
        charge = t[t.index("// Charge:"):t.index("// Onslaught:")]
        self.assertIn('Strike(c, target, ChargeSpell, Raw(c.follower, "charge", "damage_pct"), SPELL_SCHOOL_MASK_NORMAL);', charge)
        self.assertIn('Num(c, "charge", "stun_seconds")', charge)
        self.assertIn('Raw(c.follower, "charge", "stun_radius_yards")', charge)
        self.assertIn("Stun(templar, enemy, seconds);", charge)
        onslaught = t[t.index("// Onslaught:"):t.index("// Intervene:")]
        self.assertIn('Strike(c, target, OnslaughtSpell, Raw(c.follower, "onslaught", "damage_pct"), SPELL_SCHOOL_MASK_NORMAL);', onslaught)
        self.assertIn("Combat::EnemyEffects::Taken(enemy, OnslaughtSpell, pct, seconds);", onslaught)
        intervene = t[t.index("// Intervene:"):t.index("// Intimidate:")]
        self.assertIn("!c.player->IsValidAttackTarget(attacker)", intervene)
        self.assertIn("Taunt(c.companion, enemy, seconds);", intervene)
        self.assertIn('Raw(c.follower, "intervene", "radius_yards")', intervene)
        intimidate = t[t.index("// Intimidate:"):t.index("// Guardian:")]
        self.assertIn('Slow(c.companion, enemy, Raw(c.follower, "intimidate", "slow_pct"), Num(c, "intimidate", "slow_seconds"));', intimidate)
        guardian = t[t.index("// Guardian:"):]
        self.assertIn("DC::Classes::Follower::Fatal(c.player->GetHealth(), damage)", guardian)
        self.assertIn("damage = 0;", guardian)
        self.assertIn('Combat::Abilities::Knockback(c.player, enemy, Raw(c.follower, "guardian", "knockback_push_yards"));', guardian)
        self.assertIn('LifeHeal(c.player->GetMaxHealth(), Num(c, "guardian", "heal_life_pct"))', guardian)
        self.assertIn('Shield(c.player, Now() + std::uint64_t(Raw(c.follower, "guardian", "shield_seconds") * 1000.0));', guardian)

    def test_the_scoundrels_skills_do_what_their_text_says(self):
        t = self.scoundrel
        # Every skill is asked whether it is on; the shots need his weapon; each cast starts its cooldown.
        for skill in SCOUNDREL:
            self.assertIn(f'"{skill}"', t, skill)
        can = t[t.index("bool CanShoot("):t.index("// Multishot: the bolts")]
        self.assertIn("c.stats.swingMax > 0 && On(c, skill) && Ready(c, skill)", can)
        self.assertIn('Raw(c.follower, skill, "cast_range_yards")', can)
        for skill in ("crippling-shot", "powered-shot", "piercing-shot", "multishot", "nights-veil", "vanish"):
            self.assertEqual(t.count(f'Spend(c, "{skill}");'), 1, skill)
        for skill in ("crippling-shot", "powered-shot", "piercing-shot", "multishot"):
            self.assertIn(f'CanShoot(c, target, "{skill}")', t, skill)
        tick = t[t.index("void Tick("):t.index("// Vanish:")]
        self.assertIn('Slow(scoundrel, target, Raw(c.follower, "crippling-shot", "slow_pct"), Num(c, "crippling-shot", "slow_seconds"));', tick)
        self.assertIn('Strike(c, enemy, PoweredSpell, Raw(c.follower, "powered-shot", "damage_pct"), SPELL_SCHOOL_MASK_ARCANE);', tick)
        self.assertIn('Rolls(frand(0.0f, 1.0f), Raw(c.follower, "powered-shot", "stun_chance_pct"))', tick)
        self.assertIn("Stun(scoundrel, enemy, seconds);", tick)
        self.assertIn('special && c.stats.swingMax > 0 && On(c, "multishot") && Rolls(frand(0.0f, 1.0f), Num(c, "multishot", "passive_chance_pct"))', tick)
        self.assertIn('SetAnatomy(player, On(c, "anatomy") && NearEnough(c, "anatomy", "aura_radius_yards") ? Num(c, "anatomy", "crit_chance_pct") : 0.0);', tick)
        pierce = t[t.index("void Pierce("):t.index("} // namespace\n\n    void Tick")] if "} // namespace\n\n    void Tick" in t else t[t.index("void Pierce("):t.index("void Tick(")]
        self.assertIn("if (enemy == target || OnLine(from.GetPositionX(), from.GetPositionY(), toX, toY, enemy->GetPositionX(), enemy->GetPositionY(), width / 2))", pierce)
        self.assertIn("Combat::EnemyEffects::Taken(enemy, PiercingSpell, pct, seconds);", pierce)
        volley = t[t.index("void Volley("):t.index("// Piercing Shot:")]
        self.assertIn("enemies[BoltTarget(bolt, enemies.size())]", volley)
        self.assertIn("1 + unsigned(Raw(c.follower, \"multishot\", \"extra_bolts\"))", volley)
        self.assertIn("enemies.insert(enemies.begin(), target);", volley)
        veil = tick[tick.index("// Night's Veil:"):]
        self.assertIn('own.veilUntil = Now() + std::uint64_t(Num(c, "nights-veil", "seconds") * 1000.0);', veil)
        self.assertIn('own.veilRadius = Raw(c.follower, "nights-veil", "radius_yards");', veil)
        self.assertIn("own.veilInstance = target->GetInstanceId();", veil)
        vanish = t[t.index("// Vanish:"):t.index("// Hysteria:")]
        self.assertIn("damage = 0;", vanish)
        self.assertIn('Conceal(c.player, Num(c, "vanish", "conceal_seconds"));', vanish)
        hysteria = t[t.index("// Hysteria:"):t.index("double DamageFactor(")]
        self.assertIn('Combat::DamageBoost::Hold(c.player, HysteriaKey, pct, seconds);', hysteria)
        self.assertIn("own.hysteriaUntil = Now() + std::uint64_t(seconds * 1000.0);", hysteria)
        cloud = t[t.index("double CloudBonus("):t.index("void Away(")]
        # The cloud holds on the map and the instance it was laid on, as every ground effect does: another run of the same map is not it.
        self.assertIn("found->second.veilMap != target->GetMapId() || found->second.veilInstance != target->GetInstanceId()", cloud)
        self.assertIn("InRange(std::sqrt(dx * dx + dy * dy), found->second.veilRadius) ? 100.0 : 0.0", cloud)
        away = t[t.index("void Away("):]
        self.assertIn("Stats::RemoveContribution(Key(player), Source::Passives, Stat::CritChance, AnatomyId);", away)
        self.assertIn("Combat::DamageBoost::Hold(player, HysteriaKey, 0, 0);", away)

    def test_the_enchantresss_skills_do_what_their_text_says(self):
        t = self.enchantress
        for skill in ENCHANTRESS:
            self.assertIn(f'"{skill}"', t, skill)
        for skill in ("charm", "temporal-pulse", "erosion", "fates-lapse"):
            self.assertIn(f'Ready(c, "{skill}")', t, skill)
            self.assertEqual(t.count(f'Spend(c, "{skill}");'), 1, skill)
        tick = t[t.index("void Tick("):t.index("// Fate's Lapse:")]
        self.assertIn('Stand(player, HarmonyKey, Stat::CooldownReduction, Bucket::Flat, On(c, "prophetic-harmony") ? Num(c, "prophetic-harmony", "cooldown_reduction_pct") : 0.0);', tick)
        self.assertIn('Stand(player, ArmorKey, Stat::Armor, Bucket::Percent, shield ? Raw(c.follower, "powered-shield", "armor_pct") : 0.0);', tick)
        self.assertIn('bool const focused = On(c, "focused-mind") && InRange(her->GetDistance(player), Raw(c.follower, "focused-mind", "aura_radius_yards"));', tick)
        self.assertIn('Stand(player, FocusKey, Stat::AttackSpeed, Bucket::Flat, focused ? Num(c, "focused-mind", "attack_speed_pct") : 0.0);', tick)
        self.assertIn('own.rangedPct = shield ? Raw(c.follower, "powered-shield", "ranged_reduction_pct") : 0.0;', tick)
        self.assertIn("if (look) Amplify(c);", tick)
        self.assertIn('Combat::CharmEffect::Apply(player, target, CharmSpell, Raw(c.follower, "charm", "duration_seconds")))', tick)
        self.assertIn('Strike(c, enemy, PulseSpell, Raw(c.follower, "temporal-pulse", "damage_pct"), SPELL_SCHOOL_MASK_ARCANE);', tick)
        self.assertIn('Slow(her, enemy, Raw(c.follower, "temporal-pulse", "slow_pct"), seconds);', tick)
        self.assertIn('own.poolUntil = Now() + std::uint64_t(own.poolSeconds * 1000.0);', tick)
        amplify = t[t.index("void Amplify("):t.index("// Erosion: the pool")]
        self.assertIn("bonuses[static_cast<unsigned>(held)] -= had;", amplify)
        self.assertIn("Highest(bonuses.data(), bonuses.size())", amplify)
        self.assertIn('Amplified(bonuses[top], Num(c, "amplification", "bonus_pct"))', amplify)
        self.assertIn("Stand(c.player, AmplificationKey, Stat::ElementalDamage, Bucket::Flat, want, element);", amplify)
        self.assertIn("own.poolInstance = target->GetInstanceId();", tick)
        pool = t[t.index("void Pool("):t.index("} // namespace\n\n    void Tick")] if "} // namespace\n\n    void Tick" in t else t[t.index("void Pool("):t.index("void Tick(")]
        self.assertIn('PerTick(Raw(c.follower, "erosion", "damage_pct"), own.poolSeconds, tick)', pool)
        self.assertIn("Strike(c, enemy, ErosionSpell, pct, SPELL_SCHOOL_MASK_ARCANE);", pool)
        self.assertIn("Combat::EnemyEffects::Taken(enemy, ErosionSpell, weak, tick + 0.75);", pool)
        self.assertIn("if (!Holds(Now(), state.poolUntil) || !SamePlace(state.poolMap, state.poolInstance, c.player->GetMapId(), c.player->GetInstanceId()))", pool)
        lapse = t[t.index("// Fate's Lapse:"):t.index('// Powered Shield: "slows')]
        self.assertIn("damage = 0;", lapse)
        self.assertIn("Slow(c.companion, enemy, pct, seconds);", lapse)
        self.assertIn("Weary(c.companion, enemy, pct, seconds);", lapse)
        shield = t[t.index('// Powered Shield: "slows'):t.index("void Away(")]
        self.assertIn('Slow(c.companion, attacker, Raw(c.follower, "powered-shield", "slow_pct"), Num(c, "powered-shield", "slow_seconds"));', shield)
        self.assertIn("RangedFactor(found->second.rangedPct, melee)", shield)

    def test_the_framework_holds_the_sheet_stat_dispatches_the_enchantress_and_the_engine_asks_powered_shield(self):
        stand = self.skills[self.skills.index("void Stand("):self.skills.index("double Standing(")]
        self.assertIn("Stats::RemoveContribution(Key(player), Source::Passives, stat, key);", stand)
        self.assertIn("Stats::AddContribution(Key(player), {Source::Passives, stat, key, want, bucket, element});", stand)
        self.assertIn("Stats::Recompute(player);", stand)
        clear = self.skills[self.skills.index("void ClearStanding("):self.skills.index("double TakenFactor(")]
        self.assertIn("Stats::RemoveContribution(Key(player), Source::Passives, one.stat, key);", clear)
        upkeep = self.skills[self.skills.index("void OnPlayerUpdate("):self.skills.index("// The follower goes down")]
        self.assertIn("Enchantress::Away(player); Templar::Away(player); ClearStanding(player);", upkeep)
        self.assertIn("else if (c.follower == EnchantressId) Enchantress::Tick(c, target, since);", self.skills)
        self.assertIn("else if (c.follower == EnchantressId) Enchantress::Fatal(c, damage);", self.skills)
        self.assertIn("constexpr std::uint32_t WearyHold = 10371;", self.skills)
        hits = self.skills[self.skills.index("class Hits"):self.skills.index("class Players")]
        self.assertIn("UNITHOOK_MODIFY_MELEE_DAMAGE", hits)
        self.assertIn("c.follower == EnchantressId) Enchantress::Struck(c, attacker);", hits)
        self.assertIn("return data.ready && player ? Enchantress::Taken(player, melee) : 1.0;", self.skills)
        combat = flat(MODULE / "src/combat/dc_combat.cpp")
        self.assertEqual(combat.count("Follower::TakenFactor(victim->ToPlayer(),melee)"), 1)
        self.assertEqual(combat.count("Follower::TakenFactor(victim->ToPlayer(), melee)"), 1)
        self.assertEqual(combat.count("ItemPowers::IncomingFactor(victim->ToPlayer())*Monk::TakenFactor(victim)*Shaman::TakenFactor(victim);") + combat.count("ItemPowers::IncomingFactor(victim->ToPlayer()) * Monk::TakenFactor(victim) * Shaman::TakenFactor(victim);"), 2)

    def test_the_framework_ends_what_stands_when_the_follower_is_gone_and_dispatches_the_scoundrel(self):
        upkeep = self.skills[self.skills.index("void OnPlayerUpdate("):self.skills.index("// The follower goes down")]
        self.assertIn("state->second.sinceUpkeep < 1000", upkeep)
        self.assertIn("if (!Context(player, c)) { Scoundrel::Away(player);", upkeep)
        self.assertIn("PLAYERHOOK_ON_UPDATE", self.skills)
        self.assertIn("else if (c.follower == ScoundrelId) Scoundrel::Tick(c, target, since);", self.skills)
        self.assertIn("else if (c.follower == ScoundrelId) Scoundrel::Fatal(c, damage);", self.skills)
        self.assertIn("Hold(player, player, InvisibleHold, seconds);", self.skills)
        self.assertIn("constexpr std::uint32_t InvisibleHold = 8149;", self.skills)
        self.assertIn("return data.ready ? Scoundrel::CloudBonus(player, target) : 0.0;", self.skills)

    def test_inspire_pays_the_four_per_second_resources_to_the_class_that_has_them(self):
        inspire = self.templar[self.templar.index("void Inspire("):self.templar.index("} // namespace")]
        for resource, token in (("Resources::Mana", "mana_per_second"), ("Resources::Hatred", "hatred_per_second"), ("Wrath", "wrath_per_second"),
                                ("Resources::ArcanePower", "arcane_power_per_second")):
            self.assertIn(f'{{{resource}, "{token}"}}', inspire)
        self.assertIn("ClassIdOf(c.player) == gain.resource.classId && Resources::Displayed(c.player, gain.resource)", inspire)
        self.assertIn("Resources::Flow(c.player, gain.resource, Raw(c.follower, \"inspire\", gain.token) * pulses, 1000 * pulses);", inspire)

    def test_inspire_scales_what_fury_spirit_and_essence_generate_through_one_seam(self):
        t = re.sub(r"\s+", " ", self.templar)
        generating = t[t.index("void Generating("):t.index("} // namespace")]
        for token in ("fury_generated_pct", "spirit_generated_pct", "essence_generated_pct"):
            self.assertIn(f'Raw(c.follower, "inspire", "{token}")', generating)
            self.assertIn(("templar", "inspire", token), {(r["key"], r["skill_id"], r["token"]) for r in read("followers_skill_numbers.csv")})
        self.assertIn('if (!On(c, "inspire")) { std::lock_guard<std::mutex> guard(mutex); generated.erase(guid); return; }', generating)
        self.assertIn("Generating(c); if (inspired && On(c, \"inspire\")) Inspire(c, inspired);", t)
        factor = t[t.index("double Generation("):t.index("void Away(")]
        for resource, pct in (("Fury", "fury"), ("Spirit", "spirit"), ("Essence", "essence")):
            self.assertIn(f"if (&resource == &{'Resources::' if resource != 'Essence' else ''}{resource}) return GeneratedFactor(found->second.{pct});", factor)
        self.assertIn("if (found == generated.end()) return 1.0;", factor)
        self.assertIn("void Away(Player* player) { std::lock_guard<std::mutex> guard(mutex); generated.erase(player->GetGUID().GetRawValue()); }", t)
        skills = re.sub(r"\s+", " ", self.skills)
        self.assertIn("Resources::GenerationSourceOf() = [](Player const* player, Resources::Resource const& resource) { return data.ready && player ? Templar::Generation(player, resource) : 1.0; };", skills)
        self.assertIn("Templar::Away(player); }", skills)                      # the logout
        # The layers that pay a gain ask the seam, and a cost given back does not.
        res = re.sub(r"\s+", " ", (MODULE / "src/classes/dc_resources.h").read_text(encoding="utf-8"))
        self.assertIn("int32 const units = WholeUnits(player, r, generated ? Generated(player, r, points) : points);", res)
        # A flow is regeneration (the Monk's regen_per_second_resource rows, a Mantra's pulse), never a skill's generation: Inspire does not scale it.
        pulse = re.sub(r"\s+", " ", (MODULE / "src/stats/dc_resource_pulse.cpp").read_text(encoding="utf-8"))

        def flow_is_unscaled(text):
            return "flows.push_back({ToUnits(r, points), double(overMs)});" in text and "Generated(" not in text

        self.assertTrue(flow_is_unscaled(pulse))
        self.assertFalse(flow_is_unscaled(pulse.replace("ToUnits(r, points)", "ToUnits(r, Generated(player, r, points))")))   # a scaled flow is caught
        # Neither is a passive's gain: Harmony's refill of Spirit and Dark Reaping's Essence per kill pass `generated` false.
        for path, gain in (("src/classes/monk/dc_monk_passives_harmony.cpp", 'maxSpirit * Numbers::Num(id, "gain_pct") / 100.0, false);'),
                           ("src/classes/necromancer/dc_necromancer_passives.cpp", "ReapGain(Resources::Max(killer, Essence), pct), false);")):
            self.assertIn(gain, re.sub(r"\s+", " ", (MODULE / path).read_text(encoding="utf-8")), path)
        barbarian = re.sub(r"\s+", " ", (MODULE / "src/classes/barbarian/dc_barbarian_passives.cpp").read_text(encoding="utf-8"))
        self.assertIn("Resources::Generated(p, Resources::Fury, 1.0);", barbarian)
        for path, refund in (("src/classes/monk/dc_monk_deadly_reach.cpp", "Resources::Energize(player, Resources::Spirit, spellId, back, false);"),
                             ("src/classes/monk/dc_monk_passives.cpp", 'PaidBack(paid, Numbers::Num(id, "cost_reduction_pct")), false);')):
            self.assertIn(refund, re.sub(r"\s+", " ", (MODULE / path).read_text(encoding="utf-8")), path)

    def test_the_hits_ride_the_shared_damage_and_the_events(self):
        hits = self.skills[self.skills.index("class Hits"):self.skills.index("class Players")]
        self.assertIn("UNITHOOK_ON_DAMAGE", hits)
        self.assertIn("Templar::Hurt(c, attacker);", hits)
        self.assertIn("Templar::Fought(c, enemy);", hits)
        self.assertIn("owner->IsValidAttackTarget(enemy)", hits)
        strike = self.skills[self.skills.index("bool Strike("):self.skills.index("void Conceal(")]
        self.assertIn("WeaponHit(pct, low, high, frand(0.0f, 1.0f)) * more * multiplier", strike)
        self.assertIn("Rolls(frand(0.0f, 1.0f), c.stats.critChance + bonus)", strike)
        self.assertIn("critical ? CritMultiplier(c.stats.critDamage) : 1.0", strike)
        self.assertIn("hit.critical = critical;", strike)
        self.assertIn("more = Scoundrel::DamageFactor(c);", strike)
        self.assertIn("bonus = Scoundrel::CritBonus(c, target);", strike)
        self.assertIn("if (critical && c.follower == ScoundrelId) Scoundrel::Crit(c);", strike)
        self.assertIn("Combat::DealHit(c.player, target, spellId, hit, true);", strike)
        fatal = self.skills[self.skills.index("void Fatal(Player*"):self.skills.index("void RegisterScripts")]
        self.assertIn("if (Shielded(player)) { damage = 0; return; }", fatal)
        self.assertIn("Templar::Fatal(c, damage);", fatal)

    def test_the_seams_in_the_shared_files(self):
        creature = flat(MODULE / "src/campaign/dc_follower_creature.cpp")
        self.assertEqual(creature.count("Classes::Follower::Tick(player, me, target, diff);"), 1)
        self.assertLess(creature.index("Classes::Follower::Tick(player, me, target, diff);"), creature.index("if (!target) {"))
        self.assertIn('#include "../classes/follower/dc_follower_skills.h"', creature)
        hooks = flat(MODULE / "src/combat/dc_combat_hooks.cpp")
        self.assertEqual(hooks.count("Classes::Follower::Fatal(player, damage);"), 1)
        self.assertLess(hooks.index("Crusader::Fatal(player, damage);"), hooks.index("Classes::Follower::Fatal(player, damage);"))
        self.assertLess(hooks.index("Classes::Follower::Fatal(player, damage);"), hooks.index("ItemPowers::Fatal(player, damage);"))
        barbarian = flat(MODULE / "src/classes/barbarian/dc_barbarian.cpp")
        critical = barbarian[barbarian.index("void CriticalHit("):barbarian.index("void Taken(")]
        self.assertIn("Wrath::OnCritical(p, target, spellId); Classes::Follower::Critical(p);", critical)
        combat = flat(MODULE / "src/combat/dc_combat.cpp")
        self.assertEqual(combat.count("+ItemPowers::CritBonus(player, target)+Follower::CritBonus(player, target)) / 100.0, 0.0, 1.0);"), 1)
        self.assertIn("namespace Follower = Classes::Follower;", combat)
        classes = flat(MODULE / "src/classes/dc_classes.cpp")
        self.assertEqual(classes.count("Follower::RegisterScripts();"), 1)
        items = flat(MODULE / "src/items/dc_items.h")
        self.assertIn("bool SkillStatsOf(Player const* player, unsigned follower, SkillStats& out);", items)
        gear = flat(MODULE / "src/items/dc_follower_gear.cpp")
        self.assertIn("out.critChance = computed.sheet[Stat::CritChance];", gear)
        self.assertIn("out.critDamage = computed.sheet[Stat::CritDamage];", gear)
        self.assertIn("out.mainStat = computed.sheet[computed.mainStat];", gear)
        self.assertIn("out.swingMin = plan.swings ? plan.swingMin : 0.0;", gear)

    def test_the_tick_looks_at_the_follower_out_and_alive_only(self):
        tick = self.skills[self.skills.index("void Tick("):self.skills.index("void Fatal(Player*")]
        self.assertIn('Rule("cast_tick_ms")', tick)
        self.assertIn("!Context(player, c) || c.companion != companion", tick)
        self.assertIn("if (c.follower == TemplarId) Templar::Tick(c, target, since);", tick)
        context = self.skills[self.skills.index("bool Context("):self.skills.index("bool On(")]
        self.assertIn("!companion->IsAlive()", context)


if __name__ == "__main__":
    unittest.main()
