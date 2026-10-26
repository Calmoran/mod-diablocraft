"""diablocraft-976b: the hub's data files read the Sanctum of Torment, and nothing else names the old hub.

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum_data.py

Data-driven, no database. Pinned (brief "Tests", docs/test-diablocraft-976b.md):
  * every hub-bound point, placement, the Tester's Coffer and the sealed door read map 750 and area 4273;
  * nothing in the live hub data names map 530 or areas 3703/3898 except a closed area rule;
  * the old positions are test fixtures only: none of them is in the live files;
  * a position that is not placed yet is a blank cell with a note that names the card (q-1003-39) and the bead
    that applies it (diablocraft-ftoz), never a guess;
  * the old hub's frozen inputs are intact, so the applied migrations still regenerate (their own tests).
Mutations are run by hand and listed in the test doc (each rule broken once, this suite red).
"""
import csv
import glob
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from scryer_hub import LEGACY  # noqa: E402

MODULE = HERE.parent
D3 = MODULE / "data/d3"
HUB_MAP, HUB_AREA = 750, 4273
OLD_MAPS, OLD_AREAS = {530}, {3703, 3898}
# The hub-bound things: the designer's card q-1003-39 plus what the inventory found (docs/test-diablocraft-976b.md).
# 1799, 180324 and 2695 are the designer's campfire, table and book (card q-1005-04), stock templates he placed once and said can go to all layers.
# diablocraft-bb67 (the designer's Azeroth World Editor layout, 2026-10-09): Kadala (910005), the stairs (910090), the platform and the table pieces made with
# the adder (910092-910096) and four stock decorations (180338, 180425, 180340, 182005).
SERVICES = {"c": {910000, 910001, 910002, 910003, 910004, 910005, 31146},
            "g": {910011, 910016, 1799, 180324, 2695, 910090, 910092, 910093, 910094, 910095, 910096, 180338, 180425, 180340, 182005}}
DUMMY, DUMMIES = 31146, {8000108, 8000109, 8000110}   # the Heroic Training Dummy: three spawns on one entry
POINTS = {"spawn", "town_portal", "rift_exit", "graveyard"}
MAP_KEYS = {"map", "map_id"}
AREA_KEYS = {"area_id", "areaId", "zoneId", "zone_id"}
POSITION_KEYS = {"x", "y", "z", "o", "position_x", "position_y", "position_z", "orientation"}


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def placements(base):
    out = []
    for row in rows(base / "world_hub_placements.csv"):
        out.append((row, json.loads(row["placement"])))
    return out


def cells(row):
    """(column, value) for every cell, and for every key of a JSON cell as (column.key, value)."""
    for key, value in row.items():
        if key == "placement":
            for inner, v in json.loads(value).items():
                yield inner, v
        else:
            yield key, value


def old_point_coordinates():
    """The old hub's spawn, town portal and rift exit x, y, z: ui.csv's hub_*_yards rows, which stay as the
    frozen generator's input (nothing else reads them)."""
    import tunable_values
    return {round(tunable_values.value("ui", f"hub_{name}_{axis}_yards"), 4)
            for name in ("spawn", "town_portal", "rift_exit") for axis in ("x", "y", "z")}


def coordinates(base):
    """Every position number a hub file holds, as a set rounded to 4 places."""
    found = old_point_coordinates() if base == LEGACY else set()
    for name in ("world_hub_points.csv", "world_tester_coffer.csv"):
        for row in rows(base / name):
            for key in POSITION_KEYS & set(row):
                if row[key].strip():
                    found.add(round(float(row[key]), 4))
    for _, row in placements(base):
        for key in POSITION_KEYS & set(row):
            if row[key] is not None:
                found.add(round(float(row[key]), 4))
    return found


class HubReadsTheSanctum(unittest.TestCase):
    def test_every_named_point_reads_map_750_and_area_4273(self):
        points = rows(D3 / "world_hub_points.csv")
        self.assertEqual({r["name"] for r in points}, POINTS)
        self.assertEqual(len(points), len(POINTS), "one row per point")
        for row in points:
            self.assertEqual((int(row["map_id"]), int(row["area_id"])), (HUB_MAP, HUB_AREA), row["name"])

    def test_every_managed_placement_reads_map_750_and_area_4273(self):
        seen = {"c": set(), "g": set()}
        guids = set()
        for row, placement in placements(D3):
            kind = row["kind"]
            self.assertIn(placement["id"], SERVICES[kind], placement)
            if placement["id"] == DUMMY:   # three rows, one per hand-placed old-hub guid
                self.assertIn(int(row["source_guid"]), DUMMIES, "the dummies are the old hub's three guids")
            else:
                self.assertNotIn(placement["id"], seen[kind], "one row per service")
            seen[kind].add(placement["id"])
            self.assertEqual((placement["map"], placement["areaId"], placement["zoneId"]),
                             (HUB_MAP, HUB_AREA, HUB_AREA), placement["id"])
            self.assertEqual(set(row), {"kind", "source_guid", "placement", "source"}, "one row per thing: the Sanctum has no tier copies")
            self.assertEqual(placement["phaseMask"], 1, placement["id"])
            guid = int(row["source_guid"])
            self.assertNotIn((kind, guid), guids, "no guid twice")
            guids.add((kind, guid))
        self.assertEqual(seen, SERVICES, "every managed service has its row")
        self.assertEqual({int(r["source_guid"]) for r, p in placements(D3) if p["id"] == DUMMY}, DUMMIES, "all three dummies have their row")

    def test_the_coffer_and_the_door_read_map_750_and_area_4273(self):
        for name in ("world_tester_coffer.csv", "world_sanctum_seal.csv"):
            for row in rows(D3 / name):
                self.assertEqual((int(row["map_id"]), int(row["area_id"])), (HUB_MAP, HUB_AREA), name)

    def test_the_old_hub_is_only_a_closed_area_rule(self):
        rules = {(int(r["map_id"]), int(r["area_id"])): r for r in rows(D3 / "world_areas.csv")}
        for key in [(m, a) for m in OLD_MAPS for a in OLD_AREAS]:
            self.assertEqual(rules[key]["status"], "closed", key)
            self.assertEqual(rules[key]["phase_scope"], "all", key)
        opened = {key for key, r in rules.items() if r["status"] == "open"}
        self.assertEqual(opened, {(HUB_MAP, HUB_AREA)}, "the Sanctum is the one open area")
        self.assertEqual(rules[(HUB_MAP, HUB_AREA)]["phase_scope"], "all")

    def test_no_live_hub_file_names_the_old_hub_except_a_closed_rule(self):
        names = sorted(Path(p).name for p in glob.glob(str(D3 / "world_*.csv")) + glob.glob(str(D3 / "jeweler*.csv")))
        self.assertIn("world_hub_points.csv", names)
        self.assertIn("world_sanctum_seal.csv", names)
        checked = 0
        for name in names:
            for row in rows(D3 / name):
                closed = row.get("status") == "closed"
                for key, value in cells(row):
                    column = key.split(".")[-1]
                    if column in MAP_KEYS | AREA_KEYS and value not in (None, ""):
                        checked += 1
                        bad = (OLD_MAPS if column in MAP_KEYS else OLD_AREAS)
                        self.assertFalse(int(value) in bad and not closed, f"{name} {key}={value} names the old hub")
        self.assertGreater(checked, 20, "the scan found the map and area cells")

    def test_the_old_hub_files_moved_out_of_the_live_folder(self):
        for name in ("world_hub_native_spawns.csv", "world_fountain_gps.csv", "world_fountain_picker.csv",
                     "world_fountain_geometry.csv", "world_fountain_display_candidates.csv"):
            self.assertFalse((D3 / name).exists(), f"{name} is Scryer-era data: it lives in tests/scryer_hub")
            self.assertTrue((LEGACY / name).is_file(), name)


class OldPositionsAreFixturesOnly(unittest.TestCase):
    def test_the_fixtures_are_the_old_hub(self):
        old = rows(LEGACY / "world_hub_points.csv")
        self.assertEqual({(r["map_id"], r["area_id"]) for r in old}, {("530", "3703")})
        self.assertEqual({int(p["map"]) for _, p in placements(LEGACY)}, OLD_MAPS)
        self.assertEqual({(r["map_id"], r["area_id"]) for r in rows(LEGACY / "world_tester_coffer.csv")}, {("530", "3703")})
        self.assertGreater(len(coordinates(LEGACY)), 20, "the fixtures hold the old positions to compare with")

    def test_no_old_position_is_in_the_live_files(self):
        old = coordinates(LEGACY)
        live = coordinates(D3)
        self.assertFalse(old & live, f"old positions shipped again: {sorted(old & live)[:6]}")

    def test_a_blank_position_says_what_it_waits_for(self):
        for name in ("world_hub_points.csv", "world_tester_coffer.csv"):
            for row in rows(D3 / name):
                if any(not row[key].strip() for key in POSITION_KEYS & set(row)):
                    note = row.get("source") or row.get("placement_source")
                    self.assertTrue("PENDING" in note and "q-1003-39" in note and "diablocraft-ftoz" in note, (name, row))
        for row, placement in placements(D3):
            if any(placement.get(key) is None for key in POSITION_KEYS & set(placement)):
                self.assertTrue("PENDING" in row["source"] and "q-1003-39" in row["source"]
                                and "diablocraft-ftoz" in row["source"], row)
        # diablocraft-ftoz filled every cell (test_hub_sanctum_readings.py pins the numbers): nothing is blank now, and a blank cell
        # added later still has to say what it waits for.


if __name__ == "__main__":
    unittest.main()
