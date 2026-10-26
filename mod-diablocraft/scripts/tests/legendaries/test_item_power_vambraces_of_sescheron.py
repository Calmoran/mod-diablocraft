"""Legendary rest, bead diablocraft-uovwz: Vambraces of Sescheron (bracers, list row 66, K3), and the piece it builds, N-HEAL.

  "Your primary skills heal you for [5-6]% of your missing Life."
  * the words and the range are d3planner's (item_wrists.js, P4_Unique_Bracer_106: custom leg_vambracesofsescheron, min 5 max 6, step 0.1); the item's roll is read through
    decode_pow.py (Item_Power_Passive P4_ItemPassive_Unique_Ring_062.pow: 0.05-0.06; the power file holds only an unrelated 'Damage Reduction Duration' = 5, so the roll is
    the whole number). The table (data/legendary_powers.csv) holds ONE `effect` row: `heal_missing_life_pct` [5-6], rolled once per item, fired by `hit_generator` of every
    skill the sheets file under Primary (the bead's list named the eight of the Barbarian and the Wizard, the classes then built). No tunable, no card;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat only as an item's
    percent (above 0, at most 100) fired by `hit_generator` of named skills, with no chance, cooldown, condition or set level;
  * the production rules (src/combat/dc_item_power_math.h: Fire, MissingLifeHeal) are compiled and driven with the generated row: a cast of a Primary that hit fires the effect with
    the wearer's roll (5, 5.5 or 6), no other skill, event, unworn staff or unrolled bracer does; the heal is the percent of the Life that is missing, nothing at full Life;
    mutants of the row and the rules fail the same driver;
  * source-text guards that the executor heals the wearer a stock heal record's amount, from the Life missing now. The C++ is compile-checked by syntax_check.sh and the in-game
    steps are in docs/test-diablocraft-uovwz.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
EFFECTS = SRC / "combat/dc_item_powers_effects.cpp"
HARNESS = MODULE / "tests/item_power_vambraces_of_sescheron/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P4_Unique_Bracer_106"
STAT = "heal_missing_life_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


# The Shaman's four Primaries (Lightning Bolt, Flame Shock, Elemental Lash, Frost Lance) are not in the row yet: the Shaman's legendary
# work is held (step 3 of its build), and the row changes with a legendary fold's table. The exemption names those four and nothing else,
# and test_one_effect_row_on_the_primaries fails once the row lists any of them, so the fold removes this set.
AWAITING_FOLD = {"Lightning Bolt", "Flame Shock", "Elemental Lash", "Frost Lance"}


def primaries(everything=False):
    """Every skill the sheets file under Primary, read here without the generator, less the ones awaiting the fold."""
    out = []
    for path in sorted((MODULE / "data/d3").glob("*_skills.csv")):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if rows and "category" in rows[0]:
            out += [r["skill_name"] for r in rows if (r["category"] or "").lower() == "primary"
                    and (everything or r["skill_name"] not in AWAITING_FOLD)]
    return out


class Table(unittest.TestCase):
    def test_the_sources_say_primary_skills_heal_for_five_to_six_percent_of_missing_life(self):
        text = (REPO / "reference/d3planner/item_wrists.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n\n", start) if "},\n\n" in text[start:] else start + 900]
        self.assertIn("Your primary skills heal you for %.1f%% of your missing Life.", item)
        self.assertRegex(item, r"min: 5, max: 6")
        self.assertIn("Your primary skills heal you for [5-6]% of your missing Life.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_item_carries_the_roll(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        out = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "item", OWNER], capture_output=True, text=True).stdout
        self.assertIn("P4_ItemPassive_Unique_Ring_062.pow: 0.05-0.06", out)

    def test_one_effect_row_on_the_primaries(self):
        self.assertTrue(AWAITING_FOLD <= set(primaries(everything=True)), "the Shaman's Primaries are no longer on the sheets")
        skills = primaries()
        self.assertGreaterEqual(len(skills), 24)
        rows = mine()
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual((OWNER, 0, "effect", "", STAT, 5.0, 6.0, "", 0.0, "", 0.0, 0, "hit_generator"), row[:13])
        self.assertEqual(sorted(skills), sorted(row[13].split(";")),
                         "the row lists a Shaman Primary now: remove AWAITING_FOLD" if AWAITING_FOLD & set(row[13].split(";")) else "")
        self.assertEqual((100.0, 0.0), row[14:])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0067_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "5", "value_max": "6", "cond": "", "cond_arg": "",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit_generator", "fire_skills": "Frenzy;Bash", "chance_pct": "", "icd_seconds": "",
            "source": "s", "note": "n"}

    def render_with(self, edit):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="vambraces-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **edit}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_shape_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "on a plain hit": {"fire_on": "hit"},
            "on a spender": {"fire_on": "hit_spender"},
            "no skills named": {"fire_skills": ""},
            "a skill that is none": {"fire_skills": "Frenzy;No Such Skill"},
            "a chance": {"chance_pct": "50"},
            "a cooldown": {"icd_seconds": "5"},
            "a condition": {"cond": "triggered", "cond_arg": "5"},
            "a set level": {"pieces": "2"},
            "no percent": {"value_min": "0", "value_max": "0"},
            "over a hundred": {"value_min": "50", "value_max": "150"},
            "a stat row": {"kind": "player"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        for other in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + other] = (SRC / "combat" / other).read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemvambraces-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        for roll in (5, 5.5, 6):
            wear = clear + [(T("wears", OWNER), None), (T("rolled", OWNER, "", STAT, roll), None), (T("now", 5000), None)]
            for skill in primaries():
                out += wear + [(T("fire", "hit_generator", skill, 1, 0), "%s:%g" % (STAT, roll))]
            for skill in ("Whirlwind", "Rend", "Teleport", "Hydra", "Leap", "Blessed Hammer", "Primary", "frenzy", ""):
                out += wear + [(T("fire", "hit_generator", skill, 1, 0), "none")]
            for event in ("hit", "hit_spender", "cast", "kill", "taken", "tick", ""):
                out += wear + [(T("fire", event, "Frenzy", 1, 0), "none")]
        # worn but not rolled yet, in the bag, another owner's bracers, not worn
        out += clear + [(T("wears", OWNER), None), (T("fire", "hit_generator", "Frenzy", 1, 0), "none")]
        out += clear + [(T("rolled", OWNER, "", STAT, 5.5), None), (T("fire", "hit_generator", "Frenzy", 1, 0), "none")]
        out += clear + [(T("wears", "Other Bracers"), None), (T("rolled", "Other Bracers", "", STAT, 5.5), None), (T("fire", "hit_generator", "Frenzy", 1, 0), "none")]
        # the heal: the percent of the Life that is missing, nothing at full Life or past it
        for pct, health, most, want in ((5.5, 500, 1000, 27.5), (5, 0, 1000, 50), (6, 1, 1000, 59.94), (5.5, 999, 1000, 0.055), (5.5, 1000, 1000, 0), (5.5, 1200, 1000, 0),
                                        (5.5, -50, 1000, 55), (0, 500, 1000, 0), (-5, 500, 1000, 0), (5.5, 500, 0, 0), (5.5, 500, -1, 0), (5.5, -5, -1, 0), (100, 250, 1000, 750)):
            out.append((T("heal", pct, health, most), "%.10g" % want))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 100)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row = rows[0]
        skills = row[13].split(";")
        row_mutants = {
            "another_event": [row[:12] + ("hit_spender",) + row[13:]],
            "a_plain_hit": [row[:12] + ("hit",) + row[13:]],
            "a_primary_missing": [row[:13] + (";".join(skills[1:]),) + row[14:]],
            "one_skill_too_many": [row[:13] + (";".join(skills + ["Whirlwind"]),) + row[14:]],
            "no_skills_means_every_skill": [row[:13] + ("",) + row[14:]],
            "a_fixed_five": [row[:5] + (5.0, 5.0) + row[7:]],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        for name, (old, new) in {
            "the_heal_is_of_the_maximum": ("return (maxHealth - std::max(0.0, health)) * pct / 100.0;", "return maxHealth * pct / 100.0;"),
            "the_heal_is_of_the_life_left": ("return (maxHealth - std::max(0.0, health)) * pct / 100.0;", "return health * pct / 100.0;"),
            "the_percent_is_a_fraction": ("return (maxHealth - std::max(0.0, health)) * pct / 100.0;", "return (maxHealth - std::max(0.0, health)) * pct;"),
            "full_life_still_heals": ("if (pct <= 0 || maxHealth <= 0 || health >= maxHealth)", "if (pct <= 0 || maxHealth <= 0)"),
            "no_percent_still_heals": ("if (pct <= 0 || maxHealth <= 0 || health >= maxHealth)", "if (maxHealth <= 0 || health >= maxHealth)"),
            "no_maximum_still_heals": ("if (pct <= 0 || maxHealth <= 0 || health >= maxHealth)", "if (pct <= 0 || health >= maxHealth)"),
            "negative_life_heals_more": ("(maxHealth - std::max(0.0, health))", "(maxHealth - health)"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = self.drive(real.replace(old, new, 1), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def heal_failures(effects):
    """What is wrong with the heal branch of the executor in `effects` ([] when it is right)."""
    flat = re.sub(r"\s+", " ", effects)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("void HealMissing(Player* player, double pct) {")
    need("the heal exists", start >= 0)
    body = flat[start:flat.find("// N-ABSGRANT", start)] if start >= 0 else ""
    need("a stock heal record names it", "constexpr std::uint32_t HealRecord = 2060;" in flat)
    need("a dead wearer is not healed", "if (!player->IsAlive()) return;" in body)
    need("the amount is the item's percent of the Life missing now",
         "ItemPower::MissingLifeHeal(pct, static_cast<double>(player->GetHealth()), static_cast<double>(player->GetMaxHealth()));" in body)
    need("less than one point heals nothing", "amount >= 1.0 ? sSpellMgr->GetSpellInfo(HealRecord) : nullptr" in body)
    need("it is dealt as a heal of the record", "HealInfo healing(player, player, static_cast<std::uint32_t>(amount), info, SpellSchoolMask(info->SchoolMask)); player->HealBySpell(healing, false);" in body)
    need("the branch is the heal_missing_life_pct stat", 'else if (one.stat == "heal_missing_life_pct") HealMissing(player, one.value);' in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_heal_branch(self):
        self.assertEqual([], heal_failures(EFFECTS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = EFFECTS.read_text(encoding="utf-8")
        mutants = {
            "no_record": ("constexpr std::uint32_t HealRecord = 2060;", "constexpr std::uint32_t HealRecord = 0;"),
            "the_dead_are_healed": ("            if (!player->IsAlive())\n                return;\n            double const amount = ItemPower::MissingLifeHeal", "            double const amount = ItemPower::MissingLifeHeal"),
            "the_maximum_is_the_life": ("static_cast<double>(player->GetHealth()), static_cast<double>(player->GetMaxHealth()));", "static_cast<double>(player->GetMaxHealth()), static_cast<double>(player->GetMaxHealth()));"),
            "a_fraction_heals": ("amount >= 1.0 ? sSpellMgr->GetSpellInfo(HealRecord) : nullptr", "amount > 0.0 ? sSpellMgr->GetSpellInfo(HealRecord) : nullptr"),
            "heals_the_wrong_player": ("HealInfo healing(player, player,", "HealInfo healing(nullptr, player,"),
            "not_dispatched": ('one.stat == "heal_missing_life_pct")', 'one.stat == "heal_missing_life")'),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], heal_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
