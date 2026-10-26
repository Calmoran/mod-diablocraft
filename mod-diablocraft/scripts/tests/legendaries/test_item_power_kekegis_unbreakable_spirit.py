"""Legendary rest, bead diablocraft-hk2xg: Kekegi's Unbreakable Spirit (Monk spirit stone), which builds N-COST (every ability's cost removed for a while).

  "Damaging enemies has a chance to grant you an effect that removes the Spirit cost of your abilities for [2-4] seconds."
  * the text and range are read from d3planner (data.json items, leg_kekegisunbreakablespirit, min 2 max 4) and the catalogue row, the chance and
    the internal cooldown from the decoded power file (docs/research/legendary-pow-data.csv, ItemPassive_Unique_Ring_569_x1.pow: SF_0 Proc Chance
    0.20, SF_1 Internal Cooldown 30, SF_2 Discounted Cost 0); the table (data/legendary_powers.csv) holds ONE `effect` row for the pool item
    Unique_SpiritStone_102_x1: `cost_free_seconds` 2-4 (a range the roller rolls once per item), fired on `hit` naming no skill (every hit),
    chance 20, icd 30;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator
    refuses the stat on a set level, with a condition or on another event, and any other effect on a cast or a hit that names no skill;
  * the production rules (src/combat/dc_item_power_math.h: Fire with the generated row, CostFreeEnd, CostFreeAt) are compiled and driven: any
    skill's hit, 20% x the hit's proc coefficient, at most once per 30 s, the item's own roll as the seconds, only while worn; a window never
    shortens an open one and ends on its last millisecond;
  * mutants of the rules and of the row fail the same driver, and mutants of the readers fail the source guards on them: ItemPowers::Fire opens
    the window (OpenCostFree: a Temporary 100% Resource Cost Reduction, Passives::RefreshModifiers so the class's gear cost aura carries it to the
    core's costs, an end on the player's event queue that CloseCostFree honours only for its own end), ItemPowers::CostFree reads it for the
    costs the module charges (Tempest Rush's ticks), a logout forgets it. The C++ is compile-checked by syntax_check.sh and the in-game steps
    are in docs/test-diablocraft-hk2xg.md.
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
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
MATH = MODULE / "src/combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_kekegis_unbreakable_spirit/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_SpiritStone_102_x1"
STAT = "cost_free_seconds"
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


def planner():
    """(text, min, max) of the pool item's power in d3planner's data.json."""
    item = next(i for i in json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"] if i["id"] == OWNER)
    custom = item["required"]["custom"]
    return custom["format"], float(custom["min"]), float(custom["max"])


def power_file():
    """{SF label: value} of the decoded power file's row."""
    with (REPO / "docs/research/legendary-pow-data.csv").open(encoding="utf-8", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if r["linked_by"] == "item " + OWNER)
    assert row["power_file"] == "ItemPassive_Unique_Ring_569_x1.pow" and row["item_number"] == "2-4", row
    return {m[1].strip(): float(m[2]) for m in re.finditer(r"SF_\d+ ([^=;]+)= ([\d.]+)", row["script_formulas"])}


class Table(unittest.TestCase):
    def test_the_sources_say_two_to_four_seconds_20_percent_30_seconds(self):
        text, low, high = planner()
        self.assertEqual("Damaging enemies has a chance to grant you an effect that removes the Spirit cost of your abilities for %d seconds.", text)
        self.assertEqual((2.0, 4.0), (low, high))
        sf = power_file()
        self.assertEqual((0.20, 30.0, 0.0), (sf["Proc Chance"], sf["Internal Cooldown"], sf["Discounted Cost"]))
        with (REPO / "docs/research/legendary-catalogue.csv").open(encoding="utf-8", newline="") as stream:
            catalogue = [r for r in csv.DictReader(stream) if r["d3_id"] == OWNER]
        self.assertEqual(1, len(catalogue))
        self.assertEqual("Damaging enemies has a chance to grant you an effect that removes the Spirit cost of your abilities for [2-4] seconds.",
                         catalogue[0]["power_text"])

    def test_one_row_on_every_hit_with_the_files_chance_and_cooldown(self):
        _, low, high = planner()
        sf = power_file()
        self.assertEqual([(OWNER, 0, "effect", "", STAT, low, high, "", 0.0, "", 0.0, 0, "hit", "", sf["Proc Chance"] * 100, sf["Internal Cooldown"])],
                         mine())

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("leg_kekegisunbreakablespirit", rows[0]["source"])
        self.assertIn("ItemPassive_Unique_Ring_569_x1.pow", rows[0]["source"])
        self.assertIn("diablocraft-hk2xg", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertIn("removes the Spirit cost of your abilities for 2", m[1])


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "2", "value_max": "4", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "hit", "fire_skills": "", "chance_pct": "20",
            "icd_seconds": "30", "source": "s", "note": "n"}

    def render_with(self, *edits):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="kekegi-gen-", dir=str(SCRATCH)))
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

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))
        # a hit that names its skills is still a hit of those skills
        self.assertEqual(["Fists of Thunder"], [r[13] for r in self.render_with({"fire_skills": "Fists of Thunder"}) if r[0] == OWNER])

    def test_it_refuses_what_it_cannot_carry(self):
        why = "cost_free_seconds is an item's seconds, fired on a hit, with no condition"
        refused = {
            "a set bonus": ({"owner": "Raiment of a Thousand Storms", "pieces": "2", "value_min": "3", "value_max": "3"}, why),
            "a condition": ({"cond": "enemies_hit_at_most", "cond_arg": "1", "fire_on": "hit_spender"}, "enemies_hit_at_most|" + why),
            "another event": ({"fire_on": "taken"}, why),
            "no event": ({"fire_on": "", "chance_pct": "", "icd_seconds": ""}, "need a fire_on event"),
            "no seconds": ({"value_min": "0", "value_max": "4"}, "0 < value_min"),
            "a skill": ({"skill": "Tempest Rush"}, "a skill is named by"),
        }
        for name, (edit, reason) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, reason):
                    self.render_with(edit)

    def test_only_this_effect_fires_on_any_hit(self):
        for event in ("cast", "hit"):
            with self.subTest(event=event):
                with self.assertRaisesRegex(ValueError, "a cast, a hit or a landing needs fire_skills"):
                    self.render_with({"stat": "resource_refund", "value_min": "5", "value_max": "5", "fire_on": event})


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemkekegi-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        _, low, high = planner()
        out = [(T("row", *r), None) for r in rows]
        fired = lambda seconds: "%s=%g;" % (STAT, seconds)  # noqa: E731

        def worn(roll, at=0):
            return [(T("clear"), None), (T("now", at), None), (T("wears", OWNER, 0), None), (T("value", OWNER, "", STAT, roll), None)]
        # not worn: nothing fires, even with the roll known
        out += [(T("clear"), None), (T("now", 1000), None), (T("value", OWNER, "", STAT, low), None),
                (T("fire", "hit", "Fists of Thunder", 1, 0), "")]
        # worn: the hit of any skill fires it, the item's own roll is the seconds (each end of the range)
        for roll in (low, high):
            for skill in ("Fists of Thunder", "Tempest Rush", "Mantra of Healing", "Mystic Ally", ""):
                out += worn(roll) + [(T("fire", "hit", skill, 1, 0), fired(roll))]
        # the chance: 20% x the proc coefficient; draws under it fall, at it do not; a hit of coefficient 0 never procs
        for scale, under, at in ((1, 19.99, 20), (0.5, 9.99, 10), (0.125, 2.49, 2.5)):
            out += worn(low) + [(T("fire", "hit", "Fists of Thunder", scale, at), "")]
            out += [(T("fire", "hit", "Fists of Thunder", scale, under), fired(low))]
        out += worn(low) + [(T("fire", "hit", "Fists of Thunder", 0, 0), "")]
        # the internal cooldown: 30 s from the proc, not from the last try
        out += worn(high, 5000) + [(T("fire", "hit", "Wave of Light", 1, 0), fired(high))]
        for at, want in ((5001, ""), (20000, ""), (34999, ""), (35000, fired(high)), (35001, ""), (64999, ""), (65000, fired(high))):
            out += [(T("now", at), None), (T("fire", "hit", "Wave of Light", 1, 0), want)]
        # only a hit: a cast, a hit taken, a kill, a spender's hit are not this event
        for event in ("cast", "taken", "kill", "hit_spender", "hit_generator"):
            out += worn(low) + [(T("fire", event, "Fists of Thunder", 1, 0), "")]
        # another item's roll is not this item's
        out += [(T("clear"), None), (T("wears", "Other Stone", 0), None), (T("value", "Other Stone", "", STAT, 3), None),
                (T("fire", "hit", "Fists of Thunder", 1, 0), "")]
        # the window: from now for the seconds; a second never shortens an open one; a closed one is no help
        for until, now, seconds, want in ((0, 1000, 3, 4000), (0, 1000, 2, 3000), (0, 1000, 4, 5000), (9000, 1000, 3, 9000), (4000, 3000, 2, 5000),
                                          (4000, 1000, 3, 4000), (2000, 3000, 3, 6000), (4294967000, 4294966000, 3, 1704),
                                          (0, 2147488648, 3, 2147491648)):
            out += [(T("end", until, now, seconds), str(want))]
        for until, now, want in ((4000, 1000, 1), (4000, 3999, 1), (4000, 4000, 0), (4000, 4001, 0), (0, 0, 0), (0, 5, 0), (1704, 4294966000, 1),
                                 (1704, 1704, 0), (0, 2147488648, 0)):
            out += [(T("at", until, now), str(want))]
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
        self.assertGreater(len(want), 40)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows, "want")
        row_mutants = {
            "always": [r[:14] + (100.0,) + r[15:] for r in rows],
            "no_cooldown": [r[:15] + (0.0,) for r in rows],
            "named_skill": [r[:13] + ("Fists of Thunder",) + r[14:] for r in rows],
            "on_a_spender": [r[:12] + ("hit_spender",) + r[13:] for r in rows],
            "wrong_stat": [r[:4] + ("resource_refund",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        end = real[real.index("inline std::uint32_t CostFreeEnd("):]
        end = end[:end.index("\n    }\n") + 7]
        at = real[real.index("inline bool CostFreeAt("):]
        at = at[:at.index("\n    }\n") + 7]
        before = real[real.index("inline bool Before("):]
        before = before[:before.index("\n    }\n") + 7]
        rules = {
            "shortens": (end, "return holds ? until : end;", "return end;"),
            "adds_to_the_open": (end, "return holds ? until : end;", "return holds ? until + (end - now) : end;"),
            "seconds_as_ms": (end, "* 1000.0", "* 1.0"),
            "none_open_is_a_time": (end, "until != 0 && ", ""),
            "last_ms_open": (before, "static_cast<std::int32_t>(until - now) > 0", "static_cast<std::int32_t>(until - now) >= 0"),
            "unsigned_compare": (before, "static_cast<std::int32_t>(until - now) > 0", "until > now"),
            "zero_is_open": (before, "until != 0 && ", ""),
            "the_window_ignores_before": (at, "return Before(now, until);", "return true;"),
        }
        for name, (body, old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertIn(old, body, name + " does not apply")
                _, got = self.drive(real.replace(body, body.replace(old, new, 1)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_bottom_not_the_roll": real.replace("number = found->value;", "number = row.min;"),
            "chance_unscaled": real.replace("roll(row.chancePct * scale)", "roll(row.chancePct)"),
            "named_skills_ignored_blank_refused": real.replace("if (!row.fireSkills.empty() && std::find(", "if (std::find("),
            "cooldown_ignored": real.replace("(situation.now - last->second) < static_cast<std::uint32_t>(icd * 1000.0)", "false"),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
