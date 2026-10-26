"""diablocraft-yh7el: every rift in the pool has an exit point.

Desolace opened on dev with "no exit point (dc_rift_exit_point, dc_rift_exit_spot); floor 1 has no exit": no open zone had an
exit row, because the zone survey wrote none (rift floors 4.14 waited for the designer's spot). Ruled (PM 2026-10-14, D3's exit at the
floor's far end): each zone's exit is its anchor farthest from the entrance by walk, source survey; the designer's spot replaces it.

1. The pool: every dungeon generate_rifts.py puts in (the recommended rows) and every open zone with an entrance has exactly one
   row in rift_exit_points.csv, with a position.
2. The zones' rows are with_zone_exits' render of the committed anchors, and the zones' migration carries them.
3. The rule: the farthest anchor, the lowest number on a tie, the designer's row kept; each single-rule mutant is refused.
4. diablocraft-71kk3: prune_open_zone_spots.py's main hands with_zone_exits the exit sheet too (it died with a KeyError on the first
   run after yh7el, since prune() returns the three survey sheets only), and writes the exit sheet back.
"""
import csv
import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_open_zone_survey as O  # noqa: E402
import generate_rift_survey as S  # noqa: E402
import generate_rifts as R  # noqa: E402
import prune_open_zone_spots as P  # noqa: E402


def pool_names():
    dungeons = [r["name"] for r in csv.DictReader(open(S.D3 / "rift_dungeons.csv", encoding="utf-8"))
                if r["recommended"].strip().lower() == "yes"]
    return dungeons + [z["name"] for z in R.read_open_zones()]


def rule_problems(exits_of):
    """What is wrong with `exits_of(sheets, names)` on made-up anchors; empty when the rule holds."""
    out = []
    anchors = [dict(dungeon="Zone", anchor=str(n), x=str(n), y="0", z="0", o="1", entry_walk_yards=w)
               for n, w in ((1, "10.0"), (2, "250.5"), (3, "90.0"), (4, "250.5"), (5, ""))]
    dungeon = dict(dungeon="Cave", x="1", y="2", z="3", o="0", walk_yards="40.0", source="survey")
    sheets = {"rift_anchors.csv": anchors, "rift_exit_points.csv": [dungeon]}
    rows = exits_of(sheets, ["Zone"])["rift_exit_points.csv"]
    if dungeon not in rows:
        out.append("a dungeon's row is lost")
    zone = [r for r in rows if r["dungeon"] == "Zone"]
    if len(zone) != 1:
        return out + ["not one row for the zone"]
    if (zone[0]["x"], zone[0]["walk_yards"], zone[0]["source"]) != ("2", "250.5", "survey"):
        out.append("the zone's exit is not its farthest anchor (lowest number on a tie), source survey")
    alex = dict(dungeon="Zone", x="7", y="7", z="7", o="2", walk_yards="", source="alex")
    rows = exits_of({**sheets, "rift_exit_points.csv": [dungeon, alex]}, ["Zone"])["rift_exit_points.csv"]
    if [r for r in rows if r["dungeon"] == "Zone"] != [alex]:
        out.append("the designer's spot does not replace the survey's")
    return out


SOURCE = inspect.getsource(O.with_zone_exits)
MUTANTS = {
    "nearest anchor": ("far = max(walked,", "far = min(walked,"),
    "highest number on a tie": ("-int(a[\"anchor\"])", "int(a[\"anchor\"])"),
    "the designer's spot dropped": ("        if name in alex:\n            out.append(alex[name])\n            continue\n", ""),
    "dungeons dropped": ("out = [r for r in rows if r[\"dungeon\"] not in names]", "out = []"),
}


class ExitRows(unittest.TestCase):
    def test_every_pool_rift_has_one_exit_row(self):
        rows = S.read_csv(S.D3 / "rift_exit_points.csv")
        for name in pool_names():
            with self.subTest(rift=name):
                mine = [r for r in rows if r["dungeon"] == name]
                self.assertEqual(len(mine), 1, f"{name}: {len(mine)} exit rows (dc_rift_exit_point); the floor has no way on")
                self.assertTrue(all(mine[0][c] not in ("", None) for c in ("x", "y", "z")), f"{name}: an exit row with no position")

    def test_the_zones_rows_are_the_render_and_reach_the_migration(self):
        sheets = S.read_sheets()
        self.assertEqual(O.with_zone_exits(sheets)["rift_exit_points.csv"], sheets["rift_exit_points.csv"])
        migration = (S.MODULE / "data/sql/db-world/updates" / S.OPEN_NAME).read_text(encoding="utf-8")
        exits = migration[migration.index("INSERT INTO `dc_rift_exit_point`"):]
        for zone in R.read_open_zones():
            self.assertIn(f"({S.sql_value(zone['name'])}, ", exits, zone["name"])

    def test_the_merged_migration_is_not_edited(self):
        # rift_survey_0004 is merged and applied on dev; numbered migrations are never edited after merge, so the exit rows ship as 0005
        # and the zones' rerun at the designer's spacing (71kk3) as 0006, the name the generator now renders.
        updates = S.MODULE / "data/sql/db-world/updates"
        self.assertEqual(S.OPEN_NAME, "rift_survey_0006.sql")
        for folder in (updates, S.MODULE / "data/generated"):
            self.assertNotIn("INSERT INTO `dc_rift_exit_point`", (folder / "rift_survey_0004.sql").read_text(encoding="utf-8"), str(folder))

    def test_the_prune_keeps_the_exit_sheet(self):
        written = {}
        saved = (P.spots.build, P.outside, S.write_csv, P.refresh_report, S.generate)
        try:
            P.spots.build, P.outside = (lambda: None), (lambda binary: set())
            S.write_csv = lambda path, columns, rows: written.__setitem__(Path(path).name, rows)
            P.refresh_report, S.generate = (lambda *args: None), (lambda *args: None)
            P.main()
        finally:
            P.spots.build, P.outside, S.write_csv, P.refresh_report, S.generate = saved
        self.assertEqual(written["rift_exit_points.csv"], S.read_sheets()["rift_exit_points.csv"])
        self.assertEqual(sorted(written), sorted(S.SHEETS))

    def test_the_rule(self):
        self.assertEqual(rule_problems(O.with_zone_exits), [])

    def test_every_mutant_is_refused(self):
        for name, (old, new) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(SOURCE.count(old), 1, name)
                scope = dict(O.__dict__)
                exec(compile(SOURCE.replace(old, new), "with_zone_exits", "exec"), scope)
                self.assertNotEqual(rule_problems(scope["with_zone_exits"]), [], "mutant survived: " + name)


if __name__ == "__main__":
    unittest.main()
