"""Legendary rest, bead diablocraft-89un3: Arreat's Law (Barbarian spear, P73_Unique_Spear_001): "Weapon Throw and Ancient Spear deal [150-200]%
increased damage. Weapon Throw generates up to 50 additional Fury based on the distance of the enemy hit. The generated Fury can go above the
maximum cap by 200 Fury. Ancient Spear refunds up to 50 Fury based on the distance of the enemy hit, and resets your Fury cap to its base maximum."

  * the item's text is read out of reference/d3planner/data.json (the catalogue's source for a rolled power) and the table
    (data/legendary_powers.csv) must hold exactly its numbers: the damage range on the two skills, two `effect` rows fired on a hit (Weapon
    Throw's gain, Ancient Spear's refund) and the two fixed `player` rows they read (the yards of full benefit, the points over the cap). The
    yards are not in the P73 text: the item's older version states them ("20 or more yards", data.json P3_Unique_Spear_001);
  * the production rules (src/combat/dc_item_power_math.h: DistanceShare, OwnerNumber, Fire) are compiled and driven with the generated rows;
  * mutants of the rules and of the rows fail the same driver;
  * the generator refuses an effect it cannot stand behind;
  * source-text guards that the executor (src/combat/dc_item_powers.cpp) raises the resource maximum with a contribution to the sheet on Weapon
    Throw's gain and takes it off on Ancient Spear's refund and when the item leaves; the C++ is compile-checked by syntax_check.sh and the
    in-game steps are in docs/test-diablocraft-89un3.md.
"""
import csv
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import harness_env
import generate_legendary_powers as generator

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_arreats_law/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
LAW = "P73_Unique_Spear_001"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
TEXT = re.compile(r"Weapon Throw and Ancient Spear deal %d%% increased damage\.\s+Weapon Throw generates up to (\d+) additional Fury based on the "
                  r"distance of the enemy hit\. The generated Fury can go above the maximum cap by (\d+) Fury\.\s+Ancient Spear refunds up to "
                  r"(\d+) Fury based on the distance of the enemy hit, and resets your Fury cap to its base maximum\.")
LEGACY = re.compile(r"Maximum benefit when the enemy hit is (\d+) or more yards away\.")


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def planner_custom(item):
    """The power of `item` in the planner's data.json: (format text, min, max); asserts it is the one item of that id."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("id") == item:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8")))
    assert len(found) == 1, found
    custom = found[0]["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


def numbers():
    """(damage low, damage high, Fury gained, points over the cap, Fury refunded, yards of full benefit) from the item's texts."""
    text, low, high = planner_custom(LAW)
    m = TEXT.fullmatch(text)
    assert m, text
    legacy = LEGACY.search(planner_custom("P3_Unique_Spear_001")[0])
    assert legacy
    return low, high, float(m[1]), float(m[2]), float(m[3]), float(legacy[1])


def generated_rows(text=None):
    text = GENERATED.read_text(encoding="utf-8") if text is None else text
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(text)]


def mine():
    return [r for r in generated_rows() if r[0] == LAW]


BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)


class Table(unittest.TestCase):
    def test_the_text_is_the_catalogues(self):
        low, high, gain, over, refund, yards = numbers()
        self.assertEqual((150.0, 200.0, 50.0, 200.0, 50.0, 20.0), (low, high, gain, over, refund, yards))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            row = next(r for r in csv.DictReader(stream) if r["d3_id"] == LAW)
        self.assertIn("Weapon Throw generates up to 50 additional Fury based on the distance of the enemy hit", row["power_text"])

    def test_five_rows_with_the_texts_numbers(self):
        low, high, gain, over, refund, yards = numbers()
        want = {
            (LAW, 0, "skill", "Weapon Throw;Ancient Spear", "damage_increase_pct", low, high, *BLANK),
            (LAW, 0, "effect", "", "resource_by_distance", gain, gain, "", 0.0, "", 0.0, 0, "hit", "Weapon Throw", 100.0, 0.0),
            (LAW, 0, "effect", "", "resource_refund_by_distance", refund, refund, "", 0.0, "", 0.0, 0, "hit", "Ancient Spear", 100.0, 0.0),
            (LAW, 0, "player", "", "resource_distance_yards", yards, yards, *BLANK),
            (LAW, 0, "player", "", "resource_over_cap", over, over, *BLANK),
        }
        self.assertEqual(want, set(mine()))
        self.assertEqual(5, len(mine()))

    def test_every_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == LAW]
        self.assertEqual(5, len(rows))
        for r in rows:
            self.assertIn("reference/d3planner/data.json", r["source"])
            self.assertIn("leg_arreatslaw_p73", r["source"])
            self.assertTrue(r["note"].strip())
        # the 20 yards are the older version's, and the row says so
        yards = next(r for r in rows if r["stat"] == "resource_distance_yards")
        self.assertIn("P3_Unique_Spear_001", yards["source"])
        self.assertIn("Max Distance", yards["source"])

    def test_the_earlier_table_does_not_carry_the_law(self):
        self.assertNotIn(LAW, (MODULE / "data/sql/db-world/updates/legendary_powers_0025_table.sql").read_text(encoding="utf-8"))


class Generator(unittest.TestCase):
    EFFECT = {"owner": LAW, "pieces": "", "kind": "effect", "skill": "", "stat": "resource_by_distance", "value_min": "50", "value_max": "50",
              "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": "Weapon Throw",
              "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}
    YARDS = {**EFFECT, "kind": "player", "stat": "resource_distance_yards", "value_min": "20", "value_max": "20", "fire_on": "", "fire_skills": ""}
    OVER = {**YARDS, "stat": "resource_over_cap", "value_min": "200", "value_max": "200"}

    def render_with(self, *edits):
        """The generator run on a copy of the module whose sheet is the real one with Arreat's Law's rows replaced by `edits` (full dicts)."""
        work = Path(tempfile.mkdtemp(prefix="arreat-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != LAW]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + list(edits))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        rows = self.render_with(self.EFFECT, {**self.EFFECT, "stat": "resource_refund_by_distance", "fire_skills": "Ancient Spear"}, self.YARDS, self.OVER)
        self.assertEqual(4, len([r for r in rows if r[0] == LAW]))

    def test_it_refuses_what_it_cannot_carry(self):
        e, y, o = self.EFFECT, self.YARDS, self.OVER
        refused = {
            "no yards row": [e, o],
            "no over-cap row": [e, y],
            "a yards row that rolls": [e, {**y, "value_max": "25"}, o],
            "a yards row with a condition": [e, {**y, "cond": "triggered", "cond_arg": "3", "fire_on": "kill"}, o],
            "an effect that rolls": [{**e, "value_max": "60"}, y, o],
            "an effect on a kill": [{**e, "fire_on": "kill", "fire_skills": ""}, y, o],
            "an effect with a condition": [{**e, "cond": "triggered", "cond_arg": "3"}, y, o],
            "an effect that names no skill": [{**e, "fire_skills": ""}, y, o],
            "a negative number": [{**e, "value_min": "-50", "value_max": "-50"}, y, o],
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(*edits)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itempower-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output)]: the expectations come from the item's text, not from the code."""
        low, high, gain, over, refund, yards = numbers()
        out = [("\t".join(["row", *map(str, (r[0], r[1], r[2], r[3], r[4], "%g" % r[5], "%g" % r[6], r[7], "%g" % r[8], r[9], "%g" % r[10],
                                              r[11], r[12], r[13], "%g" % r[14], "%g" % r[15]))]), None) for r in rows]
        # the share of the gain: a straight line to full at `yards`, nothing past it, nothing for no distance
        for most in (gain, refund):
            for d in (0, 1, 5, 10, 19.99, 20, 21, 40, 100):
                out.append(("share\t%g\t%g\t%g" % (most, d, yards), "%g" % (most * min(d, yards) / yards)))
        out.append(("share\t50\t-3\t20", "0"))
        out.append(("share\t50\t10\t0", "0"))
        out.append(("share\t50\t10\t-5", "0"))
        # the fixed numbers are the item's own, and only its own
        out.append(("number\t%s\tplayer\tresource_distance_yards" % LAW, "%g" % yards))
        out.append(("number\t%s\tplayer\tresource_over_cap" % LAW, "%g" % over))
        out.append(("number\tOther Spear\tplayer\tresource_over_cap", "0"))
        out.append(("number\t%s\tplayer\tdamage_taken_pct" % LAW, "0"))
        out.append(("number\t%s\tskill\tresource_over_cap" % LAW, "0"))
        # worn: Weapon Throw's hit fires the gain, Ancient Spear's the refund, any other hit nothing
        out.append(("wears\t%s" % LAW, None))
        out.append(("fire\tWeapon Throw", "resource_by_distance=%g;" % gain))
        out.append(("fire\tAncient Spear", "resource_refund_by_distance=%g;" % refund))
        for skill in ("Cleave", "Frenzy", "Bash", "Hammer of the Ancients", ""):
            out.append(("fire\t" + skill, ""))
        # not worn: nothing fires
        out.append(("clear", None))
        out.append(("fire\tWeapon Throw", ""))
        out.append(("fire\tAncient Spear", ""))
        # the damage range is rolled once, its middle here; a Primal Ancient takes the top; the yards and the cap are fixed and never roll
        out.append(("roll\t%s\t0" % LAW, "power:Weapon Throw:damage_increase_pct=%g;" % ((low + high) / 2)))
        out.append(("roll\t%s\t1" % LAW, "power:Weapon Throw:damage_increase_pct=%g;" % high))
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return run.stdout.split("\n")[:-1], [w for _, w in cases if w is not None]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        got, want = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(5, len(rows))

        def body_of(name):
            body = real[real.index("inline double %s(" % name):]
            return body[:body.index("\n    }\n") + 7]

        mutants = {
            # the rows
            "row_yards_lost": (real, [r for r in rows if r[4] != "resource_distance_yards"]),
            "row_over_cap_lost": (real, [r for r in rows if r[4] != "resource_over_cap"]),
            "row_yards_doubled": (real, [r[:5] + (40.0, 40.0) + r[7:] if r[4] == "resource_distance_yards" else r for r in rows]),
            "row_over_cap_halved": (real, [r[:5] + (100.0, 100.0) + r[7:] if r[4] == "resource_over_cap" else r for r in rows]),
            "row_gain_on_the_spear": (real, [r[:13] + ("Ancient Spear",) + r[14:] if r[4] == "resource_by_distance" else r for r in rows]),
            "row_refund_on_the_throw": (real, [r[:13] + ("Weapon Throw",) + r[14:] if r[4] == "resource_refund_by_distance" else r for r in rows]),
            "row_gain_not_a_hit": (real, [r[:12] + ("kill", "") + r[14:] if r[4] == "resource_by_distance" else r for r in rows]),
            "row_damage_halved": (real, [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] if r[4] == "damage_increase_pct" else r for r in rows]),
        }
        rules = {
            "no_cap_on_the_yards": ("DistanceShare", "std::min(std::max(yards, 0.0), full)", "std::max(yards, 0.0)"),
            "full_ignored": ("DistanceShare", "most * std::min(std::max(yards, 0.0), full) / full", "most * std::min(std::max(yards, 0.0), full) / 100.0"),
            "negative_yards_kept": ("DistanceShare", "std::max(yards, 0.0)", "yards"),
            "no_guard_on_full": ("DistanceShare", "full > 0 ?", "full != 0 ?"),
            "owner_ignored": ("OwnerNumber", "row.owner == owner &&", ""),
            "kind_ignored": ("OwnerNumber", "row.kind == kind &&", ""),
            "stat_ignored": ("OwnerNumber", "row.stat == stat", "true"),
        }
        for name, (func, old, new) in rules.items():
            body = body_of(func)
            self.assertIn(old, body, name + " does not apply")
            mutants[name] = (real.replace(body, body.replace(old, new, 1)), rows)
        for name, (header, mutant_rows) in mutants.items():
            with self.subTest(mutant=name):
                got, want = self.drive(header, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")


class Executor(unittest.TestCase):
    """Source-text guards for the part no desk test runs (the sheet, the resource): the in-game steps are in the test sheet."""

    @classmethod
    def setUpClass(cls):
        cls.text = item_powers_source.CPP.read_text(encoding="utf-8")

    def body(self, signature):
        text = self.text[self.text.index(signature):]
        return text[:text.index("\n        }\n")]

    def test_fire_hands_both_effects_to_the_executor_with_the_target(self):
        self.assertIn('one.stat == "resource_by_distance" || one.stat == "resource_refund_by_distance"', self.text)
        self.assertIn("ByDistance(player, target, *one.row, one.value, one.stat == \"resource_refund_by_distance\")", self.text)

    def test_the_gain_raises_the_maximum_and_the_refund_takes_it_off(self):
        body = self.body("void ByDistance(")
        self.assertIn("player->GetDistance(target)", body)
        self.assertIn("ItemPower::DistanceShare(", body)
        self.assertIn('ItemPower::OwnerNumber(Data().rows, row.owner, "player", "resource_distance_yards")', body)
        self.assertIn('ItemPower::OwnerNumber(Data().rows, row.owner, "player", "resource_over_cap")', body)
        self.assertIn("Stats::AddContribution(guid, {Source::Temporary, Stat::MaxFury, OverCapId, over, Bucket::Flat})", body)
        self.assertIn("Stats::RemoveContribution(guid, Source::Temporary, Stat::MaxFury, OverCapId)", body)
        # the sheet is redone before the Fury is added, so the gain is clamped to the new maximum (and a reset clamps to the old one first)
        self.assertLess(body.index("Stats::Recompute(player)"), body.index("Resources::Add(player, *resource, points)"))

    def test_the_maximum_comes_back_when_the_item_leaves_and_on_logout(self):
        drop = self.body("void DropStacks(")
        self.assertIn("OverCapId", drop)
        self.assertIn("Stats::RemoveContribution(guid, Source::Temporary, Stat::MaxFury, OverCapId)", drop)
        self.assertIn("raised.erase(player->GetGUID().GetRawValue());", self.text)


if __name__ == "__main__":
    unittest.main()
