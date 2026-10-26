"""Legendary 054, bead diablocraft-jxvsn: Blood Brother (a two-handed sword, any class), which builds N-BLOCK (a block as an event the items listen to).

  "Grants a [15-20]% chance to block attacks. Blocked attacks inflict 30% less damage. After blocking an attack, your next attack inflicts 30% additional
  damage." (d3planner item_twohand.js, leg_bloodbrother)
  * the table (data/legendary_powers.csv) holds THREE rows for the sword: a `player` `block_chance_pct` [15-20] (the item's number, rolled once per item),
    a `player` `blocked_damage_cut_pct` 30 (Power file SF_0 'Percent Damage To Block' 0.3) and an `effect` `next_attack_pct` 30 (SF_1 'Percent Damage Bonus
    after Block' 0.3) fired by the new `block` event; the generator refuses each row half built;
  * the aura 83562 'Blood Brother' (data/legendary_power_buffs.csv `dummy`) is the armed state the next attack spends: in the spell header, the shell
    manifest and the combat migration;
  * the production rules (src/combat/dc_item_power_math.h: Fire on `block`, PlayerSum, CutFactor; src/combat/dc_item_block_math.h: Chance, Blocked, Arm,
    NextAttackFactor, Connect, Press) are compiled and driven with the generated rows: the block chance joins the sheet's under the total cap, a blocked hit is
    cut before the flat Block Amount comes off and never goes below 0, the bonus is armed by a block and kept at the larger, the next attack and the rest of
    its cast carry it, and the next skill pressed ends the cast;
  * mutants of the rules and of the rows fail the same driver; the source-text guards on the executor, the reads in Mitigate and ComputeHit, the spend on
    a connected attack and the press, with their source mutants, are in test_item_power_blood_brother_wiring.py. The C++ is compile-checked by
    syntax_check.sh; the in-game steps are in docs/test-diablocraft-jxvsn.md.
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
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
BLOCK_MATH = SRC / "combat/dc_item_block_math.h"
HARNESS = MODULE / "tests/item_power_blood_brother/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
SPELL_MIGRATION = MODULE / "data/sql/db-world/updates/combat_0090_blood_brother_next_attack.sql"
OWNER = "Unique_Sword_2H_103_x1"
EVENT = "block"
RECORD = 83562
POWER = "ItemPassive_Unique_Ring_917_x1"
CHANCE, CUT, NEXT = "block_chance_pct", "blocked_damage_cut_pct", "next_attack_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def decoded():
    """{SF label: value} of the sword's Power file, read from the client MPQs by the decoder; skips where they are not on the machine."""
    run = subprocess.run([sys.executable, "-I", str(MODULE / "scripts/decode_pow.py"), "power", POWER], capture_output=True, text=True)
    if run.returncode or "SF_" not in run.stdout:
        raise unittest.SkipTest("the decoder cannot read the client MPQs here: " + (run.stderr or run.stdout)[-200:])
    numbers = {m[1]: float(m[2]) for m in re.finditer(r"SF_\d+ '([^']+)' = ([\d.]+)", run.stdout)}
    numbers["ProcCoefficient"] = float(re.search(r"ProcCoefficient = ([\d.]+)", run.stdout)[1])
    return numbers


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not there exactly once" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


def source(name):
    """A server file's text; empty when it does not exist yet (a branch without the file reads red, not a crash)."""
    path = SRC / "combat" / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


class Table(unittest.TestCase):
    def test_the_words_are_the_planners_and_the_item_is_a_pool_legendary(self):
        text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n", text.index("preset", start))]
        self.assertIn('custom: {id: "leg_bloodbrother", name: "Chance to Block", format: "Grants a %d%% chance to block attacks. Blocked attacks inflict 30%% less '
                      'damage. After blocking an attack, your next attack inflicts 30%% additional damage.", min: 15, max: 20}', item)
        row = next(r for r in read_csv(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Grants a [15-20]% chance to block attacks. Blocked attacks inflict 30% less damage. After blocking an attack, your next attack "
                          "inflicts 30% additional damage.", "K3"), (row["power_text"], row["kind"]))
        base = next(r for r in read_csv(MODULE / "data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Blood Brother", "twohand", "legendary", "yes"), (base["d3_name"], base["slot"], base["rarity"], base["pool_version"]))

    def test_the_power_file_numbers(self):
        self.assertEqual({"Percent Damage To Block": 0.3, "Percent Damage Bonus after Block": 0.3, "ProcCoefficient": 0.0}, decoded())

    def test_three_rows_the_chance_rolled_and_the_cut_and_the_arm_fixed(self):
        self.assertEqual([(OWNER, 0, "player", "", CHANCE, 15.0, 20.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          (OWNER, 0, "player", "", CUT, 30.0, 30.0, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0),
                          (OWNER, 0, "effect", "", NEXT, 30.0, 30.0, "", 0.0, "", 0.0, 0, EVENT, "", 100.0, 0.0)], mine())

    def test_the_rows_have_their_source(self):
        rows = [r for r in read_csv(MODULE / "data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(3, len(rows))
        for row in rows:
            self.assertEqual(("", ""), (row["chance_pct"], row["fire_skills"]))
            for need in ("item_twohand.js", "leg_bloodbrother", POWER, "diablocraft-jxvsn"):
                self.assertIn(need, row["source"])
            self.assertTrue(row["note"])

    def test_the_aura_record(self):
        record = next(r for r in read_csv(MODULE / "data/legendary_power_buffs.csv") if r["owner"] == OWNER)
        self.assertEqual((str(RECORD), NEXT, "dummy", "Blood Brother", "Your next attack inflicts $s1% additional damage.", ""),
                         (record["spell_id"], record["stat"], record["aura"], record["name"], record["text"], record["element"]))
        self.assertIn('{%d, "%s", "%s"},' % (RECORD, OWNER, NEXT), (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))
        self.assertIn("%d,Blood Brother,physical," % RECORD, (MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8"))
        # the migration is the render that added the record, and a later record's render (immutable once applied) carries it on
        sql = SPELL_MIGRATION.read_text(encoding="utf-8")
        self.assertRegex(sql, r"\(%d,0,0,0,\d+," % RECORD)
        self.assertRegex((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), r"\(%d,0,0,0,\d+," % RECORD)
        ids = [int(r["spell_id"]) for r in read_csv(MODULE / "data/legendary_power_buffs.csv")]
        self.assertEqual(len(ids), len(set(ids)), "a record id is used twice")


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": CHANCE, "value_min": "15", "value_max": "20", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, stat, change, record=True):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row of `stat` replaced (None leaves it out)."""
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="bloodbrother-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            buffs = read_csv(MODULE / "data/legendary_power_buffs.csv")
            with (work / "data/legendary_power_buffs.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(buffs[0].keys()))
                writer.writeheader()
                writer.writerows(b for b in buffs if record or b["owner"] != OWNER)
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            real = next(r for r in sheet if r["owner"] == OWNER and r["stat"] == stat)
            kept = [r for r in sheet if not (r["owner"] == OWNER and r["stat"] == stat)]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + ([{**real, **change}] if change is not None else []))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        for stat in (CHANCE, CUT, NEXT):
            with self.subTest(stat=stat):
                self.assertEqual(3, len([r for r in self.render_with(stat, {}) if r[0] == OWNER]))

    def test_it_refuses_a_half_built_arm(self):
        refused = {
            "on another event": ({"fire_on": "taken"}, "fired by block"),
            "no event": ({"fire_on": ""}, "need a fire_on event"),
            "a range": ({"value_min": "25", "value_max": "30"}, "one whole percent"),
            "a fraction": ({"value_min": "30.5", "value_max": "30.5"}, "one whole percent"),
            "a chance": ({"chance_pct": "50"}, "one whole percent"),
            "a cooldown": ({"icd_seconds": "1"}, "one whole percent"),
            "naming a skill": ({"skill": "Bash"}, "a skill is named|one whole percent"),
            "on a set level": ({"owner": "Immortal King's Call", "pieces": "2"}, "one whole percent"),
            "a condition": ({"cond": "triggered", "cond_arg": "3"}, "one whole percent"),
            "zero": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
        }
        for name, (change, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(NEXT, change)

    def test_it_refuses_the_arm_without_its_record(self):
        with self.assertRaisesRegex(ValueError, "needs its dummy record"):
            self.render_with(NEXT, {}, record=False)

    def test_it_refuses_a_bad_chance_or_cut(self):
        refused = {
            "a chance over 100": (CHANCE, {"value_min": "90", "value_max": "101"}, "at most 100"),
            "no chance": (CHANCE, {"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "a backwards chance": (CHANCE, {"value_min": "20", "value_max": "15"}, "needs 0 < value_min"),
            "a cut of 100": (CUT, {"value_min": "100", "value_max": "100"}, "below 100"),
            "no cut": (CUT, {"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "an event on a chance": (CHANCE, {"fire_on": "block"}, "an event fires an effect row"),
        }
        for name, (stat, change, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(stat, change)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, headers, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/" + file: text for file, text in headers.items()}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itembloodbrother-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    @staticmethod
    def headers(**changed):
        out = {"dc_item_power_math.h": MATH.read_text(encoding="utf-8"), "dc_item_block_math.h": source("dc_item_block_math.h")}
        out.update({k.replace("__", "."): v for k, v in changed.items()})
        return out

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and its Power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        arm = "%s=30;" % NEXT
        # not worn, or only in the bag: no power, no cut, no event
        out += [(T("clear"), None), (T("now", 5000), None), (T("fire", EVENT), ""), (T("bonus"), "0"), (T("cut"), "1")]
        out += [(T("clear"), None), (T("bag", OWNER), None), (T("fire", EVENT), ""), (T("bonus"), "0"), (T("cut"), "1")]
        # worn with no stored roll: the ranged chance gives nothing; the fixed cut and the fixed arm stand
        out += [(T("clear"), None), (T("wears", OWNER), None), (T("bonus"), "0"), (T("cut"), "0.7"), (T("fire", EVENT), arm)]
        # worn: the item's rolled chance, the 30% cut, and a block arms the next attack every time (no cooldown, no chance)
        for roll in (15, 17.5, 20, 16.25):
            out += [(T("clear"), None), (T("wears", OWNER, roll), None), (T("bonus"), g(roll)), (T("cut"), "0.7"),
                    (T("fire", EVENT), arm), (T("fire", EVENT), arm)]
        # the block is its own event: nothing else arms the attack
        out += [(T("clear"), None), (T("wears", OWNER, 18), None), (T("now", 1000), None)]
        out += [(T("fire", e), "") for e in ("hit", "cast", "taken", "kill", "kill_elite", "tick", "life_below", "land", "")]
        # the chance joins the sheet's, held to the total cap; an item that adds nothing leaves the sheet's as it is
        for sheet, bonus, cap, want in ((0, 15, 75, 15), (0, 20, 75, 20), (10, 15, 75, 25), (60, 20, 75, 75), (75, 20, 75, 75), (74, 0.5, 75, 74.5),
                                        (10, 0, 75, 10), (0, 0, 75, 0), (80, 0, 75, 80), (0, 17.5, 10, 10), (30, 20, 100, 50)):
            out.append((T("chance", sheet, bonus, cap), g(want)))
        # a blocked hit: the cut first (a multiplier), then the flat amount, never below 0
        for damage, flat, cut, want in ((100, 0, 0.7, 70), (100, 20, 0.7, 50), (100, 0, 1, 100), (100, 20, 1, 80), (10, 20, 0.7, 0), (100, 80, 0.7, 0),
                                        (1000, 150, 0.7, 550), (0, 0, 0.7, 0), (100, 70, 0.7, 0)):
            out.append((T("blocked", damage, flat, cut), g(want)))
        # the next attack: an armed bonus multiplies any hit; the cast that spent it keeps it for its own skill only
        for armed, spent_pct, spent_skill, skill, want in ((30, 0, "", "Bash", 1.3), (30, 0, "", "Cleave", 1.3), (50, 0, "", "Bash", 1.5), (0, 30, "Cleave", "Cleave", 1.3),
                                                           (0, 30, "Cleave", "Bash", 1), (0, 0, "", "Bash", 1), (0, 0, "Cleave", "Cleave", 1), (30, 30, "Cleave", "Bash", 1.3),
                                                           (0, 30, "", "Cleave", 1), (0, 30, "Cleave", "", 1)):
            out.append((T("factor", armed, spent_pct, spent_skill, skill), g(want)))
        # an attack that connects spends the armed bonus on its cast; with nothing armed the cast keeps what it had; a new spend replaces the old
        for armed, spent_pct, spent_skill, skill, want in ((30, 0, "", "Cleave", "30|Cleave"), (0, 30, "Cleave", "Bash", "30|Cleave"), (0, 0, "", "Bash", "0|"),
                                                           (30, 30, "Bash", "Cleave", "30|Cleave"), (50, 0, "", "Whirlwind", "50|Whirlwind")):
            out.append((T("connect", armed, spent_pct, spent_skill, skill), want))
        # a skill pressed ends the attack before it
        out += [(T("press", 30, "Cleave"), "0|"), (T("press", 0, ""), "0|")]
        # two items that give the same stats: the chances add and the cuts multiply, each source its own multiplier
        out += [(T("row", "Other_Item", 0, "player", "", CHANCE, 10, 10, "", 0, "", 0, 0, "", "", 100, 0), None),
                (T("row", "Other_Item", 0, "player", "", CUT, 20, 20, "", 0, "", 0, 0, "", "", 100, 0), None),
                (T("clear"), None), (T("wears", OWNER, 18), None), (T("wears", "Other_Item"), None), (T("bonus"), "28"), (T("cut"), "0.56"),
                (T("clear"), None), (T("wears", "Other_Item"), None), (T("bonus"), "10"), (T("cut"), "0.8")]
        # a block while armed keeps the larger bonus, it does not stack
        for armed, pct, want in ((0, 30, 30), (30, 30, 30), (50, 30, 50), (30, 50, 50), (0, 0, 0)):
            out.append((T("arm", armed, pct), g(want)))
        return out

    def drive(self, headers, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(headers, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item(self):
        want, got = self.drive(self.headers(), mine(), "real")
        self.assertGreater(len(want), 70)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        rows = mine()
        self.assertEqual(3, len(rows))
        row_mutants = {
            "another_event": [r[:12] + ("hit",) + r[13:] if r[2] == "effect" else r for r in rows],
            "no_arm": [r for r in rows if r[2] != "effect"],
            "no_chance": [r for r in rows if r[4] != CHANCE],
            "no_cut": [r for r in rows if r[4] != CUT],
            "a_smaller_cut": [r[:5] + (20.0, 20.0) + r[7:] if r[4] == CUT else r for r in rows],
            "a_smaller_arm": [r[:5] + (20.0, 20.0) + r[7:] if r[4] == NEXT else r for r in rows],
            "a_fixed_chance": [r[:5] + (20.0, 20.0) + r[7:] if r[4] == CHANCE else r for r in rows],
            "another_effect": [r[:4] + ("drain_life",) + r[5:] if r[2] == "effect" else r for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(), mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        block = source("dc_item_block_math.h")
        block_mutants = {
            "chance_uncapped": ("std::clamp(sheetChance + itemBonus, 0.0, totalCap)", "sheetChance + itemBonus"),
            "chance_capped_with_no_bonus": ("return itemBonus > 0 ? std::clamp(sheetChance + itemBonus, 0.0, totalCap) : sheetChance;",
                                            "return std::clamp(sheetChance + itemBonus, 0.0, totalCap);"),
            "chance_ignores_the_sheet": ("std::clamp(sheetChance + itemBonus, 0.0, totalCap)", "std::clamp(itemBonus, 0.0, totalCap)"),
            "chance_ignores_the_item": ("return itemBonus > 0 ? std::clamp(sheetChance + itemBonus, 0.0, totalCap) : sheetChance;", "return sheetChance;"),
            "flat_first": ("return std::max(0.0, damage * cutFactor - flat);", "return std::max(0.0, (damage - flat) * cutFactor);"),
            "can_go_below_zero": ("return std::max(0.0, damage * cutFactor - flat);", "return damage * cutFactor - flat;"),
            "no_cut": ("return std::max(0.0, damage * cutFactor - flat);", "return std::max(0.0, damage - flat);"),
            "no_flat": ("return std::max(0.0, damage * cutFactor - flat);", "return std::max(0.0, damage * cutFactor);"),
            "armed_ignored": ("if (armedPct > 0)\n            return 1.0 + armedPct / 100.0;", "if (false)\n            return 1.0 + armedPct / 100.0;"),
            "armed_percent_wrong": ("if (armedPct > 0)\n            return 1.0 + armedPct / 100.0;", "if (armedPct > 0)\n            return 1.0 + armedPct / 10.0;"),
            "spent_for_any_skill": ("spent.pct > 0 && spent.skill == skill ?", "spent.pct > 0 ?"),
            "spent_ignored": ("spent.pct > 0 && spent.skill == skill ?", "false ?"),
            "connect_forgets": ("return armedPct > 0 ? Spent{armedPct, skill} : spent;", "return Spent{armedPct, skill};"),
            "connect_never_spends": ("return armedPct > 0 ? Spent{armedPct, skill} : spent;", "return spent;"),
            "connect_wrong_skill": ("return armedPct > 0 ? Spent{armedPct, skill} : spent;", "return armedPct > 0 ? Spent{armedPct, spent.skill} : spent;"),
            "press_keeps": ("inline Spent Press(Spent const&)\n    {\n        return {};", "inline Spent Press(Spent const& spent)\n    {\n        return spent;"),
            "arm_adds": ("return std::max(armedPct, pct);", "return armedPct + pct;"),
            "arm_replaces": ("return std::max(armedPct, pct);", "return pct;"),
        }
        for name, (old, new) in block_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(self.headers(dc_item_block_math__h=mutate(block, old, new)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        power = MATH.read_text(encoding="utf-8")
        cut = power[power.index("inline double CutFactor("):]
        cut = cut[:cut.index("\n    }\n")]
        sum_ = power[power.index("inline double PlayerSum("):]
        sum_ = sum_[:sum_.index("\n    }\n")]
        fire = power[power.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        rules = {
            "cut_adds": (cut, "factor *= 1.0 - pct / 100.0;", "factor *= 1.0 + pct / 100.0;"),
            "cut_is_the_percent": (cut, "factor *= 1.0 - pct / 100.0;", "factor *= pct / 100.0;"),
            "cut_adds_up": (cut, "factor *= 1.0 - pct / 100.0;", "factor -= pct / 100.0;"),
            "sum_takes_the_last": (sum_, "sum += value;", "sum = value;"),
            "unworn_fires": (fire, "!Owned(row, counts, situation, number)", "false"),
            "any_event_fires": (fire, "row.fireOn != fireOn ||", "false ||"),
        }
        for name, (where, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, where.count(old), name + " does not apply once")
                want, got = self.drive(self.headers(dc_item_power_math__h=power.replace(where, where.replace(old, new))), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
