"""Legendary rest, bead diablocraft-9qisl: Jang's Envelopment (Wizard belt), which builds N-MONSLOW (an item effect that slows a monster).

  "Enemies damaged by Black Hole are also slowed by [60-80]% for 3 seconds."
  * the numbers (60-80 percent, 3 seconds) are read from d3planner (item_waist.js, leg_jangsenvelopment) and the catalogue row and the item's
    tooltip, apart from the table; the table holds TWO rows for the pool item Unique_Belt_106_x1: an `effect` `slow_pct` 60-80 (rolled once per item)
    fired on a `hit` of Black Hole, and the fixed `player` `slow_seconds` 3 beside it (the slow's length, read only by that effect);
  * the generated SQL and the committed migration are what the generator renders, the migration the newest full table; the generator accepts the
    slow and refuses it half built (no seconds row, a seconds row alone, a set level, a condition, a percent of 100, another event, no skill);
  * the production rules (src/combat/dc_item_power_math.h: Fire on a `hit` of the named skill with the item's stored roll, OwnerNumber for the
    seconds, SlowAmount, SlowHold, RollPowers) are compiled and driven with the generated rows: every hit of Black Hole slows at the item's roll for
    3 s, another skill's hit and other events do not, an unworn item does not; a Primal stores 80;
  * mutants of the rules and of the rows fail the same driver;
  * source-text guards: the effect puts the stock snare on the enemy the hit struck at -N% for the owner's seconds (the player's own snare taken off
    first); stock 13496 "Dazed" is a snare-only aura with the Snare mechanic in the client's Spell.dbc, and no other Torment code uses it (the Monk's
    50259 would be replaced by it on the same enemy). The C++ is compile-checked by syntax_check.sh; the in-game steps are in
    docs/test-diablocraft-9qisl.md.
"""
import csv
import re
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_jangs_envelopment/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Belt_106_x1"
SKILL = "Black Hole"
SLOW, SECONDS = "slow_pct", "slow_seconds"
DAZED = 13496
KEY = "power::%s" % SLOW
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine():
    return [r for r in all_rows() if r[0] == OWNER]


def numbers():
    """(low, high, seconds) as the planner words them."""
    text = (REPO / "reference/d3planner/item_waist.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("},\n\n", start)]
    m = re.search(r'format: "Enemies damaged by Black Hole are also slowed by %d%% for (\d+) seconds\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[2]), float(m[3]), float(m[1])


def effect(low, high, skill=SKILL):
    return (OWNER, 0, "effect", "", SLOW, low, high, "", 0.0, "", 0.0, 0, "hit", skill, 100.0, 0.0)


def seconds_row(seconds):
    return (OWNER, 0, "player", "", SECONDS, seconds, seconds, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)


class Table(unittest.TestCase):
    def test_the_sources_name_black_hole_and_the_numbers(self):
        self.assertEqual((60.0, 80.0, 3.0), numbers())
        self.assertIn(SKILL, [r["skill_name"] for r in read_csv(MODULE / "data/d3/wizard_skills.csv")])
        catalogue = [r for r in read_csv(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertIn("slowed by [60-80]% for 3 seconds", catalogue[0]["power_text"])

    def test_two_rows_name_the_slow_and_its_seconds(self):
        low, high, seconds = numbers()
        self.assertEqual([effect(low, high), seconds_row(seconds)], mine())

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("slowed by 60–80% for 3 seconds", m[1])


class Generator(unittest.TestCase):
    SLOW = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": SLOW, "value_min": "60", "value_max": "80", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": SKILL, "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}
    SECONDS = {**SLOW, "kind": "player", "stat": SECONDS, "value_min": "3", "value_max": "3", "fire_on": "", "fire_skills": ""}

    def render_with(self, slow=None, seconds=None):
        """The generator run on a copy of the module whose sheet is the real one with the owner's rows replaced (None leaves a row out)."""
        work = Path(tempfile.mkdtemp(prefix="jang-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            rows = ([{**self.SLOW, **slow}] if slow is not None else []) + ([{**self.SECONDS, **seconds}] if seconds is not None else [])
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows([r for r in sheet if r["owner"] != OWNER] + rows)
            return [r for r in generator.rows(work) if r[0] == OWNER]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_vocabulary(self):
        self.assertIn(SLOW, generator.EFFECT_STATS)
        self.assertIn(SECONDS, generator.PLAYER_STATS)

    def test_the_real_rows_pass_and_a_fixed_slow_too(self):
        self.assertEqual(2, len(self.render_with({}, {})))
        self.assertEqual(80.0, self.render_with({"value_min": "80"}, {})[0][5])

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "no seconds row": ({}, None, "slow_seconds"),
            "a seconds row alone": (None, {}, "slow_pct"),
            "ranged seconds": ({}, {"value_min": "2", "value_max": "3"}, "one fixed number"),
            "seconds with an event": ({}, {"fire_on": "taken"}, "."),
            "a slow of 100": ({"value_min": "80", "value_max": "100"}, {}, "below 100"),
            "a set bonus": ({"owner": "Immortal King's Call", "pieces": "2", "value_min": "80"}, {"owner": "Immortal King's Call", "pieces": "2"}, "."),
            "a condition": ({"cond": "enemies_hit_at_most", "cond_arg": "3", "fire_on": "hit_spender"}, {}, "."),
            "on a cast": ({"fire_on": "cast"}, {}, "fired on a hit"),
            "on being hit": ({"fire_on": "taken", "fire_skills": ""}, {}, "."),
            "a hit of no skill": ({"fire_skills": ""}, {}, "needs fire_skills"),
            "a skill named on the effect": ({"skill": SKILL}, {}, "."),
        }
        for name, (slow, seconds, why) in refused.items():
            with self.subTest(case=name), self.assertRaisesRegex(ValueError, why):
                self.render_with(slow, seconds)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemjang-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and numbers, not from the code."""
        low, high, seconds = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        wear = lambda roll: clear + [(T("stored", KEY, roll), None), (T("wears", OWNER), None)]  # noqa: E731
        # not worn: nothing, also with its roll known (in the bag)
        out += clear + [(T("stored", KEY, 70), None), (T("fire", "hit", SKILL), "")]
        out += clear + [(T("stored", KEY, 70), None), (T("bag", OWNER), None), (T("fire", "hit", SKILL), "")]
        # worn, no roll stored: no value, no power
        out += clear + [(T("wears", OWNER), None), (T("fire", "hit", SKILL), "")]
        for roll in (low, 66.5, high):
            # each hit of Black Hole slows by the item's roll, again and again (no cooldown in the text)
            out += wear(roll) + [(T("now", 1000), None), (T("fire", "hit", SKILL), "%s=%g;" % (SLOW, roll)),
                                 (T("now", 1001), None), (T("fire", "hit", SKILL), "%s=%g;" % (SLOW, roll))]
            # another skill's hit, and other events, do not
            for event, skill in (("hit", "Magic Missile"), ("hit", "Meteor"), ("cast", SKILL), ("taken", ""), ("kill", ""), ("hit_spender", SKILL)):
                out += wear(roll) + [(T("fire", event, skill), "")]
            # the aura's amount is the slow as a negative percent, whole
            out += [(T("amount", roll), str(-int(round(roll + 1e-9))))]
        # the slow lasts the item's 3 seconds; the snare is stock 13496
        out += [(T("seconds", OWNER), "%g" % seconds), (T("seconds", "Unique_Belt_xxx"), "0"), (T("hold"), str(DAZED))]
        # a Primal stores the top of the range; the seconds row stores nothing
        out += [(T("roll", OWNER, 1), "%s=%g;" % (KEY, high)), (T("roll", OWNER, 0), "%s=%g;" % (KEY, (low + high) / 2))]
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
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        slow = lambda **k: [r[:5] + (k.get("low", r[5]), k.get("high", r[6])) + r[7:12] + (k.get("event", r[12]), k.get("skills", r[13])) + r[14:]  # noqa: E731
                            if r[4] == SLOW else r for r in rows]
        row_mutants = {
            "the_range_fixed": slow(low=rows[0][6]),
            "the_range_halved": slow(low=rows[0][5] / 2, high=rows[0][6] / 2),
            "another_skill": slow(skills="Meteor"),
            "every_skill": slow(skills=""),
            "the_wrong_event": slow(event="cast"),
            "the_seconds_doubled": [r[:5] + (r[5] * 2, r[6] * 2) + r[7:] if r[4] == SECONDS else r for r in rows],
            "no_seconds_row": [r for r in rows if r[4] != SECONDS],
            "no_slow_row": [r for r in rows if r[4] != SLOW],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("// N-MONSLOW (Jang's Envelopment)"):]
        body = body[:body.index("\n    }\n", body.index("SlowAmount")) + 6]
        rules = {
            "another_snare": ("SlowHold = 13496", "SlowHold = 50259"),
            "a_positive_amount": ("return -static_cast<int>(std::lround(pct));", "return static_cast<int>(std::lround(pct));"),
            "the_amount_truncated": ("std::lround(pct)", "pct"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                want, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_skill_ignored": real.replace("!row.fireSkills.empty() && std::find", "false && std::find"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                want, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


class StockRecord(unittest.TestCase):
    """Stock 13496 "Dazed" in the client's Spell.dbc: one apply-aura effect, MOD_DECREASE_SPEED, with the Snare mechanic and no other effect."""

    def test_dazed_is_a_plain_snare(self):
        dbc = REPO / "azerothcore-wotlk/build/server/data/dbc/Spell.dbc"
        schema = REPO / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql"
        if not dbc.is_file() or not schema.is_file():
            raise unittest.SkipTest("no client Spell.dbc")
        columns, inside = [], False
        for line in schema.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("CREATE TABLE `spell_dbc`"):
                inside = True
            elif inside and line.startswith(")"):
                break
            elif inside and line.strip().startswith("`"):
                columns.append(line.strip().split("`")[1])
        data = dbc.read_bytes()
        _magic, count, fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        self.assertEqual(len(columns), fields)
        records = {struct.unpack_from("<I", data, 20 + i * size)[0]: struct.unpack_from("<%dI" % fields, data, 20 + i * size) for i in range(count)}
        record = dict(zip(columns, records[DAZED]))
        self.assertEqual((6, 0, 0), (record["Effect_1"], record["Effect_2"], record["Effect_3"]))   # SPELL_EFFECT_APPLY_AURA only
        self.assertEqual(33, record["EffectAura_1"])                                                # SPELL_AURA_MOD_DECREASE_SPEED
        self.assertEqual(11, record["Mechanic"])                                                    # MECHANIC_SNARE


if __name__ == "__main__":
    unittest.main()
