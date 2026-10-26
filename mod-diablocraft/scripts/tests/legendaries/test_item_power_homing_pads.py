"""Legendary rest, bead diablocraft-9ebp6: Homing Pads (shoulders, any class).

  "Your Town Portal is no longer interrupted by taking damage. While casting Town Portal you gain a protective bubble that reduces damage taken by [50 - 65]%."
  * the numbers (the roll range 50-65 percent) are read from d3planner (item_shoulders.js, leg_homingpads); the table (data/legendary_powers.csv) holds ONE
    `player` row for the pool item Unique_Shoulder_001_x1: `town_portal_bubble_pct`, 50-65, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the
    stat as an item's own percent and refuses a set level, a condition, an event, a number of 100 or more and a zero;
  * the production rule (src/combat/dc_item_power_math.h: PortalBubbleFactor, with Owned / Holds / RollPowers) is compiled and driven with the generated row:
    1 - N/100 of the item's stored roll while the item is worn and rolled, 1 with none, two sources multiply; a Primal stores 65;
  * mutants of the rule and of the row fail the same driver;
  * source-text guards that Town Portal no longer carries the core's ABORT_ON_DMG flag (the ONE baseline change for everyone: a hit a shield absorbs in full
    no longer cancels the cast), that PortalDamage alone cancels and skips the wearer and scales the wearer's damage by the factor;
    test_town_portal.py (the compiled portal harness) drives the same hook with a wearer and without. The in-game steps are in docs/test-diablocraft-9ebp6.md.
"""
import csv
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_homing_pads/harness.cpp"
PORTAL = SRC / "rifts/dc_town_portal.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Shoulder_001_x1"
STAT = "town_portal_bubble_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
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


def numbers():
    """(low, high) percent as the planner words them."""
    text = (REPO / "reference/d3planner/item_shoulders.js").read_text(encoding="utf-8")
    start = text.index('id: "leg_homingpads"')
    item = text[start:text.index("},", start)]
    m = re.search(r'Your Town Portal is no longer interrupted by taking damage\. While casting Town Portal you gain a protective bubble that reduces '
                  r'damage taken by %d%%\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_source_gives_the_range(self):
        self.assertEqual((50.0, 65.0), numbers())

    def test_one_player_row_holds_the_range(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, *BLANK)], mine())

    def test_the_row_has_its_source_and_the_baseline_change_in_its_note(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_shoulders.js", rows[0]["source"])
        self.assertIn("leg_homingpads", rows[0]["source"])
        self.assertIn("ABORT_ON_DMG", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("reduces damage taken by 50–65%", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "50", "value_max": "65", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="homing-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a zero number": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min <= value_max"),
            "a hundred": ({"value_min": "100", "value_max": "100"}, "below 100"),
            "a range above a hundred": ({"value_min": "50", "value_max": "120"}, "below 100"),
            "a set bonus": ({"pieces": "2", "value_max": "50"}, STAT),
            "a condition": ({"cond": "skills_active", "cond_skills": "Sprint"}, "."),
            "an event": ({"fire_on": "cast", "fire_skills": "Sprint"}, "."),
        }
        for name, (edit, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemhoming-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, roll), None)]  # noqa: E731
        # not worn: no bubble
        out += clear + [(T("bubble"), "1")]
        # worn, no roll stored yet: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("bubble"), "1")]
        # worn and rolled: 1 - N/100, at both ends and between
        for roll in (low, 57.5, high):
            out += worn(roll) + [(T("bubble"), g(1 - roll / 100))]
        # a roll stored but the item in the bag
        out += clear + [(T("value", OWNER, "", STAT, 60), None), (T("bubble"), "1")]
        # a second owner's row multiplies the first's: two sources are two multipliers, not a sum
        out += worn(high) + [(T("wears", "Other Pads"), None), (T("value", "Other Pads", "", STAT, 20), None),
                             (T("bubble"), g((1 - high / 100) * (1 - 20 / 100)))]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
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

    def other(self):
        return [("Other Pads", 0, "player", "", STAT, 20.0, 20.0, *BLANK)]

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.other(), "real")
        self.assertGreater(len(want), 8)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        other = self.other()
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_kind_lost": [r[:2] + ("skill",) + r[3:] for r in rows],
            "the_range_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_wrong_stat": [r[:4] + ("damage_reduction_pct",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mine() + other, name + "-want")
                _, got = self.drive(real, mutant_rows + other, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline double PortalBubbleFactor("):]
        body = body[:body.index("\n    }\n") + 7]
        rules = {
            "added_not_taken_off": ("factor *= 1.0 - pct / 100.0;", "factor *= 1.0 + pct / 100.0;"),
            "only_the_last_source": ("factor *= 1.0 - pct / 100.0;", "factor = 1.0 - pct / 100.0;"),
            "sources_subtracted": ("factor *= 1.0 - pct / 100.0;", "factor -= pct / 100.0;"),
            "percent_read_as_a_fraction": ("factor *= 1.0 - pct / 100.0;", "factor *= 1.0 - pct;"),
            "the_stat_swapped": ('"town_portal_bubble_pct"', '"damage_reduction_pct"'),
            "the_kind_swapped": ('"player", "", "town_portal_bubble_pct"', '"skill", "", "town_portal_bubble_pct"'),
            "starts_at_nothing": ("double factor = 1.0;", "double factor = 0.0;"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real, mine() + other, name + "-want")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), mine() + other, name)
                self.assertNotEqual(want, got, name + " survived")


class Hooks(unittest.TestCase):
    def portal(self):
        return PORTAL.read_text(encoding="utf-8")

    def damage_hook(self, text=None):
        text = self.portal() if text is None else text
        body = text[text.index("void OnDamage(Unit*, Unit* victim, uint32& damage)"):]
        return body[:body.index("\n            }\n") + 14]

    # diablocraft-86qcn: the wearer's share comes off the exact hit, so it has a hook of its own, and the preparing-cast test both share
    def exact_hook(self, text=None):
        text = self.portal() if text is None else text
        body = text[text.index("void ModifyExactDamage("):]
        return body[:body.index("\n            }\n") + 14]

    def preparing(self, text=None):
        text = self.portal() if text is None else text
        body = text[text.index("static bool PreparingPortal(Unit* victim)"):]
        return body[:body.index("\n            }\n") + 14]

    def test_the_reader_is_declared_and_reads_before_the_power_lock(self):
        self.assertIn("double TownPortalFactor(Player const*);", (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))
        text = item_powers_source.CPP.read_text(encoding="utf-8")
        body = text[text.index("double TownPortalFactor("):]
        body = body[:body.index("\n    }\n")]
        self.assertRegex(body, r"if \(!player\)\s+return 1\.0;")
        self.assertIn("ItemPower::PortalBubbleFactor(Data().rows, CountsOf(guid),", body)
        self.assertLess(body.index("Seen(player)"), body.index("std::lock_guard"))

    def test_town_portal_loses_the_cores_damage_abort_flag(self):
        text = self.portal()
        start = text.index("void OnLoadSpellCustomAttr(SpellInfo* info)")
        body = text[start:text.index("\n            }\n", start)]
        self.assertIn("info->InterruptFlags = SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT;", body)
        self.assertNotRegex(re.sub(r"//.*", "", body), r"ABORT_ON_DMG")

    def test_only_portal_damage_cancels_and_the_wearer_is_skipped(self):
        hook, exact, preparing = self.damage_hook(), self.exact_hook(), self.preparing()
        self.assertIn("void ModifyExactDamage(Unit*, Unit* victim, uint64& damage, DamageEffectType) override", self.portal())
        self.assertIn("{UNITHOOK_ON_DAMAGE, UNITHOOK_MODIFY_EXACT_DAMAGE}", self.portal())
        # a factor below 1 scales the EXACT hit (whole numbers, 128-bit, rounded to the nearest) and keeps the cast; anything else cancels it
        self.assertIn("DC::Combat::ItemPowers::TownPortalFactor(victim->ToPlayer())", exact)
        self.assertIn("if (bubble < 1.0)", exact)
        self.assertIn("unsigned __int128 const product = static_cast<unsigned __int128>(damage) *", exact)
        self.assertIn("static_cast<std::uint64_t>(std::llround(std::max(bubble, 0.0) * scale))", exact)
        self.assertIn("damage = static_cast<std::uint64_t>((product + scale / 2) / scale);", exact)
        self.assertNotIn("uint32", exact)
        self.assertRegex(hook, r"if \(DC::Combat::ItemPowers::TownPortalFactor\(victim->ToPlayer\(\)\) >= 1\.0\)\s+victim->InterruptNonMeleeSpells\(false, PORTAL_SPELL\);")
        self.assertNotIn("damage =", hook)       # the 32-bit view is never written: a changed view replaces the exact hit
        # no damage, no portal cast, or a cast already past preparing: nothing is touched, and the reader is not asked
        for body in (hook, exact):
            self.assertIn("!damage || !PreparingPortal(victim)", body)
            self.assertLess(body.index("PreparingPortal"), body.index("TownPortalFactor"))
        self.assertIn("cast->GetSpellInfo()->Id == PORTAL_SPELL && cast->getState() == SPELL_STATE_PREPARING", preparing)

    def test_the_hook_mutants_are_caught(self):
        text = self.portal()
        mutants = {
            "the_flag_comes_back": ("SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT;",
                                    "SPELL_INTERRUPT_FLAG_MOVEMENT | SPELL_INTERRUPT_FLAG_INTERRUPT | SPELL_INTERRUPT_FLAG_ABORT_ON_DMG;"),
            "the_wearer_is_cancelled_too": ("TownPortalFactor(victim->ToPlayer()) >= 1.0", "TownPortalFactor(victim->ToPlayer()) >= 0.0"),
            "the_wearer_is_not_scaled": ("if (bubble < 1.0)", "if (false)"),
            "the_damage_is_not_scaled": ("damage = static_cast<std::uint64_t>((product + scale / 2) / scale);", "damage = damage;"),
            "the_damage_scaled_the_wrong_way": ("std::max(bubble, 0.0) * scale", "std::max(1.0 / bubble, 0.0) * scale"),
            "the_share_is_not_rounded": ("(product + scale / 2) / scale", "product / scale"),
            "the_share_goes_back_to_the_32_bit_view": ("uint64& damage, DamageEffectType", "uint32& damage, DamageEffectType"),
            "the_exact_hook_is_not_registered": ("{UNITHOOK_ON_DAMAGE, UNITHOOK_MODIFY_EXACT_DAMAGE}", "{UNITHOOK_ON_DAMAGE}"),
            "the_reader_is_not_asked": ("DC::Combat::ItemPowers::TownPortalFactor(victim->ToPlayer())", "1.0"),
            "any_state_cancels": ("cast->getState() == SPELL_STATE_PREPARING", "true"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertIn(old, text, name + " does not apply")
                mutated = text.replace(old, new, 1)
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    h = Hooks()
                    h.portal = lambda m=mutated: m
                    h.test_town_portal_loses_the_cores_damage_abort_flag()
                    h.test_only_portal_damage_cancels_and_the_wearer_is_skipped()

    def test_the_compiled_portal_harness_drives_a_wearer_and_a_stranger(self):
        run = subprocess.run([sys.executable, str(MODULE / "scripts/tests/rifts/test_town_portal.py")], capture_output=True, text=True, cwd=str(MODULE / "scripts"))
        self.assertEqual(0, run.returncode, run.stdout[-1500:] + run.stderr[-3000:])
        self.assertIn("PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
