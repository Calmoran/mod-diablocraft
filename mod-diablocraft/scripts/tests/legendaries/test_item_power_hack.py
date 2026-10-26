"""Legendary rest, bead diablocraft-fhpm9: Hack (a one-hand axe, list row 59, K3), and the piece it builds, N-THDEAL.

  "[75 - 100]% of your Thorns damage is applied on every attack."
  * the numbers are read from d3planner (item_onehand.js, Unique_Axe_1H_103_x1: the 75-100) and the item's roll through decode_pow.py
    (Item_Power_Passive ItemPassive_Unique_Ring_673_x1.pow: 0.75-1; the power file holds only a proc coefficient of 0, so the roll is the share); the table
    (data/legendary_powers.csv) holds ONE `effect` row for the axe: `thorns_on_attack_pct` 75-100 fired on every `hit`, rolled once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator refuses a
    bad row of the stat;
  * the production rules (src/combat/dc_item_power_math.h: Fire, ThornsShare, with Owned and RollPowers) are compiled and driven with the generated row:
    while the axe is worn and rolled every hit, of any skill and whatever its proc coefficient, applies the rolled share of the Thorns damage; an unworn
    axe, another owner's, an unrolled one and a Thorns damage of 0 apply nothing; a Primal rolls 100;
  * mutants of the row, the rules and the source fail the same driver; source-text guards that the effect is dealt to the hit's own target through
    Stats::ThornsHit, which refuses a Thorns hit while one is being dealt, and that the Thorns hit taken (Struck) and this one share DealThorns. The C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-fhpm9.md.
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
SUSTAIN = SRC / "stats/dc_sustain.cpp"
STATS_H = SRC / "stats/dc_stats.h"
HARNESS = MODULE / "tests/item_power_hack/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Axe_1H_103_x1"
STAT = "thorns_on_attack_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def words():
    text = (REPO / "reference/d3planner/item_onehand.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n  },", start)]
    m = re.search(r'format: "%d%% of your Thorns damage is applied on every attack\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_sources_say_75_to_100(self):
        self.assertEqual((75.0, 100.0), words())
        self.assertIn("[75-100]% of your Thorns damage is applied on every attack.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_files_roll_is_the_same_share(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        item = harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), "item", OWNER], capture_output=True, text=True).stdout
        self.assertIn("ItemPassive_Unique_Ring_673_x1.pow: 0.75-1", item)

    def test_one_effect_row_on_every_hit(self):
        low, high = words()
        self.assertEqual([(OWNER, 0, "effect", "", STAT, low, high, "", 0.0, "", 0.0, 0, "hit", "", 100.0, 0.0)], mine())

    def test_the_tooltip_says_it(self):
        m = re.search(r"INSERT INTO `dc_item_tooltip` VALUES \('%s','[^']*','([^']*)'" % OWNER,
                      (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertIn("75–100% of your Thorns damage is applied on every attack.", m[1])

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0064_table.sql")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "75", "value_max": "100", "cond": "", "cond_arg": "",
            "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": "", "chance_pct": "", "icd_seconds": "",
            "source": "s", "note": "n"}

    def render_with(self, edit):
        work = Path(tempfile.mkdtemp(prefix="hack-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        refused = {
            "a cast": {"fire_on": "cast", "fire_skills": "Rend"},
            "no event": {"fire_on": ""},
            "named skills": {"fire_skills": "Rend"},
            "a chance": {"chance_pct": "50"},
            "an internal cooldown": {"icd_seconds": "1"},
            "a condition": {"cond": "triggered", "cond_arg": "3"},
            "a set level": {"pieces": "2"},
            "a skill": {"skill": "Rend"},
            "zero": {"value_min": "0", "value_max": "0"},
            "more than all of it": {"value_min": "75", "value_max": "101"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="itemhack-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, not from the code."""
        low, high = words()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        # not worn: nothing
        out += clear + [(T("hit", "Rend", 1, 1000), "")]
        # worn and rolled: every hit of any skill, whatever its proc coefficient, applies the rolled share of the Thorns damage
        for roll in (low, 90, high):
            out += clear + [(T("wears", OWNER), None), (T("rolled", OWNER, "", STAT, roll), None)]
            for skill in ("Rend", "Fists of Thunder", "Bone Spear", "Frenzy", "", "Not A Skill"):
                for scale in (0, 0.5, 1):
                    out += [(T("hit", skill, scale, 1000), "%s=%s;" % (STAT, g(1000 * roll / 100)))]
            out += [(T("hit", "Rend", 1, 0), "%s=0;" % STAT), (T("hit", "Rend", 1, 333), "%s=%s;" % (STAT, g(333 * roll / 100)))]
        # worn, nothing rolled yet: the row is not on
        out += clear + [(T("wears", OWNER), None), (T("hit", "Rend", 1, 1000), "")]
        # a roll stored but the axe in the bag, and another owner's axe
        out += clear + [(T("rolled", OWNER, "", STAT, 90), None), (T("hit", "Rend", 1, 1000), "")]
        out += clear + [(T("wears", "Other Axe"), None), (T("rolled", "Other Axe", "", STAT, 90), None), (T("hit", "Rend", 1, 1000), "")]
        # the share itself: clamped to 0..100, never from a negative Thorns
        for thorns, pct, want in ((1000, 100, 1000), (1000, 0, 0), (1000, 150, 1000), (1000, -5, 0), (-100, 50, 0), (999, 33, 329.67), (0, 80, 0), (1234.5, 75, 925.875)):
            out += [(T("share", thorns, pct), g(want))]
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
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row = rows[0]
        row_mutants = {
            "a_tenth_fixed": [row[:5] + (10.0, 10.0) + row[7:]],
            "only_on_a_cast": [row[:12] + ("cast",) + row[13:]],
            "only_for_one_skill": [row[:13] + ("Rend",) + row[14:]],
            "a_chance_of_half": [row[:14] + (50.0,) + row[15:]],
            "the_wrong_stat": [row[:4] + ("thorns_on_hit_pct",) + row[5:]],
            "no_row": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double ThornsShare("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "the_share_is_not_clamped": ("std::min(100.0, std::max(0.0, pct)) / 100.0", "std::max(0.0, pct) / 100.0"),
            "a_negative_share_counts": ("std::min(100.0, std::max(0.0, pct)) / 100.0", "std::min(100.0, pct) / 100.0"),
            "a_negative_thorns_counts": ("std::max(0.0, thorns) *", "thorns *"),
            "the_share_is_a_fraction_too_small": ("pct)) / 100.0;", "pct)) / 1000.0;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, body.count(old), name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def source_failures(effects, sustain, stats_h):
    """What is wrong with the dealing of the Hack effect in the texts given ([] when it is right)."""
    e = re.sub(r"\s+", " ", effects)
    s = re.sub(r"\s+", " ", sustain)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the effect is dealt to the hit's own target, as the share of the sheet's Thorns",
         'else if (one.stat == "thorns_on_attack_pct" && target) {' in e
         and "Stats::ThornsHit(player, target, ItemPower::ThornsShare((*sheet)[Stat::Thorns], one.value));" in e)
    need("the sheet is the player's own", "if (auto const sheet = Stats::Get(player->GetGUID().GetRawValue()))" in e[e.index('"thorns_on_attack_pct"'):])
    need("a Thorns hit taken is dealt by the shared dealer from the victim's sheet", "DealThorns(victim, attacker, Sheet(victim, Stat::Thorns));" in s)
    need("an attack's Thorns hit refuses while one is being dealt, a Stagger payment, an unsheeted player, itself and a target it may not attack",
         "void ThornsHit(Player* player, Unit* target, double amount) { if (!Sheeted(player)) return; if (resolvingThorns || DC::Combat::GemPowers::PayingStagger() || !target || target == player) return; "
         "if (!player->IsAlive() || !target->IsAlive() || !player->IsValidAttackTarget(target)) return; DealThorns(player, target, amount); }" in s)
    need("the shared dealer is a Physical hit under the Thorns shell that cannot critically strike",
         'hit.skillName = "Thorns"; hit.school = SPELL_SCHOOL_MASK_NORMAL; hit.total = amount; hit.crit = 1.0; hit.critical = false; ThornsGuard guard; DC::Combat::DealHit(from, to, THORNS_SHELL, hit);' in s)
    need("nothing is dealt for 0", "void DealThorns(Player* from, Unit* to, double amount) { if (amount <= 0) return;" in s)
    need("the dealer is declared for the effects", "void ThornsHit(Player* player, Unit* target, double amount);" in stats_h)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_effect_and_the_dealer(self):
        self.assertEqual([], source_failures(EFFECTS.read_text(encoding="utf-8"), SUSTAIN.read_text(encoding="utf-8"), STATS_H.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        texts = [re.sub(r"\s+", " ", t.read_text(encoding="utf-8")) for t in (EFFECTS, SUSTAIN, STATS_H)]   # the guards read whitespace-collapsed text
        mutants = {
            "no_target": (0, 'one.stat == "thorns_on_attack_pct" && target', 'one.stat == "thorns_on_attack_pct"'),
            "the_whole_thorns": (0, "ItemPower::ThornsShare((*sheet)[Stat::Thorns], one.value)", "(*sheet)[Stat::Thorns]"),
            "the_wrong_stat": (0, "(*sheet)[Stat::Thorns]", "(*sheet)[Stat::Armor]"),
            "no_recursion_guard": (1, "if (resolvingThorns || DC::Combat::GemPowers::PayingStagger() || !target || target == player)", "if (DC::Combat::GemPowers::PayingStagger() || !target || target == player)"),
            "it_may_hit_itself": (1, "|| !target || target == player) return;", "|| !target) return;"),
            "a_friend_may_be_hit": (1, "!target->IsAlive() || !player->IsValidAttackTarget(target)", "!target->IsAlive()"),
            "the_victims_sheet_is_not_read": (1, "DealThorns(victim, attacker, Sheet(victim, Stat::Thorns));", "DealThorns(victim, attacker, 0);"),
            "the_hit_may_critically_strike": (1, "hit.critical = false;", "hit.critical = true;"),
            "not_declared": (2, "void ThornsHit(Player* player, Unit* target, double amount);", ""),
        }
        for name, (index, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, texts[index].count(old), name + " does not apply")
                changed = list(texts)
                changed[index] = texts[index].replace(old, new, 1)
                self.assertNotEqual([], source_failures(*changed), name + " survived")


if __name__ == "__main__":
    unittest.main()
