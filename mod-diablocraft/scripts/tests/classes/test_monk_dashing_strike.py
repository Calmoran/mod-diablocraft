"""diablocraft-tnqei (Monk 2.3.08, Dashing Strike and its five runes).

What this proves, and how:

  * **The maths.** tests/monk_dashing_strike/harness.cpp compiles the real dc_monk_dashing_strike.h and the shared dc_charge_store.h: a Monk starts with
    every charge, a dash spends one, the empty button waits exactly until the next charge lands, charges come back one at
    a time and stop at the cap, a running recharge keeps the period it started with (cooldown reduction then, as Furious
    Charge's), a lower cap clamps, and Barrage's 975% over 2 s is 20 ticks that pay the whole total. Planted mutations
    in a scratch copy must each make it fail.
  * **The data the glue reads.** Every Dashing Strike record carries the sheet's charges (ProcCharges: 2, Quicksilver 3)
    and recharge (CategoryRecoveryTime 8000 ms, one category for the skill and its runes); the line is 50 yards long and
    2 wide; Barrage's tick tunable is the power file's 0.1 s and reaches the tunables migration.
  * **The wiring.** Monk::BasePct and Monk::Cast hand a Dashing Strike record to it before anything else, and the cast
    path calls Monk::Cast with no guard on the target list (a dash into nothing still spends its charge).

What it does not prove: anything on a running server (the dash's movement is the record's CHARGE_DEST, the hits are the
shared line path); the test sheet's checks do.

    python mod-diablocraft/scripts/tests/classes/test_monk_dashing_strike.py
"""

import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
HEADER = "src/classes/monk/dc_monk_dashing_strike.h"
STORE = "src/combat/dc_charge_store.h"   # the charges: the shared store the Monk, Bone Spirit and Blood Rush use
SOURCES = [HEADER, STORE, "tests/monk_dashing_strike/harness.cpp"]
RECORDS = MODULE / "data/sql/db-world/updates/combat_0066_monk_records.sql"
SKILL = "Dashing Strike"


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_dashing_strike/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)], capture_output=True, text=True)


def sheet(name):
    with (MODULE / "data" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def values():
    """{(rune, token): value} of Dashing Strike in monk_skill_values.csv."""
    return {(r["rune"], r["token"]): float(r["value"]) for r in sheet("d3/monk_skill_values.csv") if r["skill"] == SKILL}


def records():
    """{name: {column: value}} of the Dashing Strike spell_dbc rows in the Monk records migration."""
    text = RECORDS.read_text(encoding="utf-8")
    out = {}
    for insert in re.finditer(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES(.*?);\n", text, re.S):
        columns = [c.strip(" `") for c in insert.group(1).split(",")]
        for row in re.finditer(r"^\((.*)\),?$", insert.group(2), re.M):
            cells = re.findall(r"'(?:[^'\\]|\\.)*'|[^,]+", row.group(1))
            record = dict(zip(columns, cells))
            name = record.get("Name_Lang_enUS", "").strip("'")
            if name == SKILL or name.startswith(SKILL + " - "):
                out[name] = record
    return out


class Harness(unittest.TestCase):
    def test_the_charges_and_the_ticks(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 23, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("a charge lands a millisecond late", (STORE, "while (next && now >= next && count < cap)",
                                                    "while (next && now > next && count < cap)")),
            ("only one charge comes back on a long wait", (STORE, "next = count < cap && period ? next + period : 0;",
                                                           "next = 0;")),
            ("the recharge takes the new period", (STORE, "next = count < cap && period ? next + period : 0;",
                                                   "next = count < cap && periodMs ? next + periodMs : 0;")),
            ("a dash spends nothing", (STORE, "            if (count)\n                --count;\n", "")),
            ("the cap does not clamp", (STORE, "                count = cap;\n                next = 0;",
                                        "                next = 0;")),
            ("the ticks drop the remainder", (HEADER, "return {count, totalPct / count};",
                                              "return {count, std::floor(totalPct / count)};")),
            ("a Monk starts empty", (STORE, "                count = cap;\n                known = true;",
                                     "                known = true;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Data(unittest.TestCase):
    def test_every_record_carries_the_sheets_charges_and_recharge(self):
        sheet_values = values()
        rows = records()
        runes = [r["rune_name"] for r in sheet("d3/monk_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(len(runes), 5)
        self.assertEqual(sorted(rows), sorted([SKILL] + [f"{SKILL} - {rune}" for rune in runes]))
        base_count = sheet_values[("", "charge_count")]
        recharge_ms = sheet_values[("", "charge_recharge_seconds")] * 1000
        categories = {rows[name]["Category"] for name in rows}
        self.assertEqual(len(categories), 1, categories)   # one cooldown for the skill and every rune
        self.assertNotEqual(categories, {"0"})
        for name, record in rows.items():
            rune = name[len(SKILL) + 3:] if " - " in name else ""
            with self.subTest(name):
                self.assertEqual(int(record["ProcCharges"]), int(sheet_values.get((rune, "charge_count"), base_count)))
                self.assertEqual(int(record["CategoryRecoveryTime"]), int(recharge_ms))
                self.assertEqual(int(record["RecoveryTime"]), 0)
        self.assertEqual((base_count, sheet_values[("Quicksilver", "charge_count")]), (2, 3))

    def test_the_line_is_fifty_yards_by_two(self):
        row = next(r for r in sheet("d3/skill_targeting.csv") if r["skill"] == SKILL)
        self.assertEqual((row["target_type"], float(row["range_yards"]), float(row["width_yards"])), ("line_to_point", 50, 2))
        self.assertEqual(float(row["range_yards"]), values()[("", "radius_yards")])

    def test_barrage_tick_is_the_power_files_and_reaches_the_migration(self):
        row = next(r for r in sheet("tunables/monk.csv") if r["name"] == "dashing_strike_barrage_tick_seconds")
        self.assertEqual(float(row["d3_value"]), 0.1)
        self.assertIn("SF_11", row["notes"])
        sql = (MODULE / "data/sql/db-world/updates/tunables_0012.sql").read_text(encoding="utf-8")
        self.assertIn("('monk', 'dashing_strike_barrage_tick_seconds', 0.1,", sql)
        # 975% over 2 s: the sheet's numbers the harness splits
        self.assertEqual((values()[("Barrage", "damage_pct")], values()[("Barrage", "dot_duration_seconds")]), (975, 2))


if __name__ == "__main__":
    unittest.main()
