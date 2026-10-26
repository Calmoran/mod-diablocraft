"""diablocraft-976b: the old hub's frozen inputs still carry what its applied migrations shipped.

    python3 mod-diablocraft/scripts/tests/world/test_scryer_hub_frozen.py

An applied migration is immutable (applied_migrations.py), and the hub move repointed the live data files at the
Sanctum of Torment. The generators of the Scryer's Tier migrations therefore read tests/scryer_hub (scryer_hub.py);
this test proves that is enough. world_0009 (with its mirror and the live snapshot), world_0020 and world_0024 are
regenerated and compared byte for byte; world_0007 and world_0023 were made by a generator that has outgrown them,
so the frozen CSV is checked to carry the positions and GUIDs they shipped; world_0005 needs a world database to build
its templates, so its rule rows and point rows are checked inside the file. If a fixture drifts, or a frozen generator
starts reading a live file again, this is red. No database, no live data; temp copies live under the scratch folder.
"""
import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_placements as placements  # noqa: E402
import generate_hub_relocation as relocation  # noqa: E402
import generate_hub_tester_coffer as coffer  # noqa: E402
import generate_sql  # noqa: E402
from scryer_hub import LEGACY  # noqa: E402

MODULE = HERE.parent
UPDATES = MODULE / "data/sql/db-world/updates"
GENERATED = MODULE / "data/generated"
SCRATCH = MODULE.parent / "azerothcore-wotlk/build/_agent-scratch"


def committed(name):
    migration = (UPDATES / name).read_text(encoding="utf-8")
    assert (GENERATED / name).read_text(encoding="utf-8") == migration, f"{name}: mirror differs from the migration"
    return migration


class FrozenGenerators(unittest.TestCase):
    def test_world_0007_and_0023_were_made_from_these_placements(self):
        # These two are applied files the generator has outgrown (its statement forms and its guard changed since:
        # the tolerance fix of diablocraft-yeh2), so they cannot be compared byte for byte; what must hold is that the
        # frozen CSV carries the very positions and GUIDs they shipped.
        with (LEGACY / "world_hub_placements.csv").open(encoding="utf-8", newline="") as stream:
            sources = list(csv.DictReader(stream))
        for name, entries in (("world_0007_hub_placements.sql", placements.ORIGINAL_ENTRIES),
                              ("world_0023_hub_tome_stack_placements.sql", placements.TOME_STACK_ENTRIES)):
            text = committed(name)
            rows = [r for r in sources if json.loads(r["placement"])["id"] in entries.get(r["kind"], set())]
            self.assertEqual(len(rows), sum(map(len, entries.values())), name)
            for row in rows:
                placement = json.loads(row["placement"])
                keys = ("position_x", "position_y") + (() if placement["id"] == placements.TOME_ENTRY else ("position_z",))
                for key in keys:
                    self.assertIn(str(placement[key]), text, (name, placement["id"], key))
                for guid in [row["source_guid"]] + list(json.loads(row["copy_guids"]).values()):
                    self.assertIn(str(guid), text, (name, guid))

    def test_world_0024_the_pillar_restore(self):
        self.assertEqual(placements.generate_pillar_restore(), committed("world_0024_difficulty_pillar_restore.sql"))

    def test_world_0020_the_tester_coffer(self):
        self.assertEqual(coffer.generate(), committed("world_0020_tester_coffer.sql"))

    def test_world_0009_the_area_rules(self):
        # generate_world_areas works on a module root: its live sheet is <root>/data/d3/world_areas.csv (the Sanctum's rules since
        # the hub move) and its frozen one <root>/tests/scryer_hub/world_areas.csv. World_0009 and its mirror must come from the
        # frozen sheet while the generated snapshot follows the live one.
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="scryer-frozen-", dir=SCRATCH) as folder:
            root = Path(folder) / "mod-diablocraft"
            (root / "data/d3").mkdir(parents=True)
            (root / "tests/scryer_hub").mkdir(parents=True)
            (root / "data/generated").mkdir(parents=True)
            (root / "data/sql/db-world/updates").mkdir(parents=True)
            shutil.copy(MODULE / "data/d3/world_areas.csv", root / "data/d3/world_areas.csv")
            shutil.copy(LEGACY / "world_areas.csv", root / "tests/scryer_hub/world_areas.csv")
            shutil.copy(MODULE / "data/sql/applied_migrations.csv", root / "data/sql/applied_migrations.csv")
            shutil.copy(UPDATES / "world_0009_scryers_tier_area.sql", root / "data/sql/db-world/updates")
            generate_sql.generate_world_areas(root)
            made = (root / "data/generated/world_0009_scryers_tier_area.sql").read_text(encoding="utf-8")
            snapshot = (root / "data/generated/world_areas.sql").read_text(encoding="utf-8")
        self.assertEqual(made, committed("world_0009_scryers_tier_area.sql"))
        self.assertEqual(snapshot, generate_sql.render_world_areas(MODULE / "data/d3/world_areas.csv")[0],
                         "the snapshot is the live sheet's render")
        self.assertIn("750, 4273", snapshot.replace("(750,4273", "(750, 4273"), "the live sheet holds the Sanctum's rule")
        self.assertEqual(snapshot, (GENERATED / "world_areas.sql").read_text(encoding="utf-8"),
                         "data/generated/world_areas.sql is stale: run generate_sql.py --world-areas")

    def test_world_0005_the_relocation_carries_the_frozen_rules_and_points(self):
        migration = committed("world_0005_shattrath_hub.sql")
        # It embeds the rules sheet as it stood on 2026-09-07 (before the 530/3898 subarea row): every row it
        # holds is a row of the frozen sheet.
        with (LEGACY / "world_areas.csv").open(encoding="utf-8", newline="") as stream:
            frozen = {(int(r["map_id"]), int(r["area_id"])): r for r in csv.DictReader(stream)}
        for key in ((1, 876), (530, 3703)):
            r = frozen[key]
            note = r["note"].replace("'", "''")
            self.assertIn(f"({key[0]}, {key[1]}, '{r['phase_scope']}', '{r['status']}', '{note}')", migration, key)
        points = relocation.point_rows()
        self.assertEqual({p["name"] for p in points}, {"spawn", "town_portal", "rift_exit"})
        for p in points:
            values = ",".join(p[k] for k in ("map_id", "area_id", "x", "y", "z", "o"))
            self.assertIn(f"REPLACE INTO dc_world_hub_point VALUES('{p['name']}',{values});", migration, p["name"])
            self.assertEqual((p["map_id"], p["area_id"]), ("530", "3703"))

    def test_the_frozen_generators_read_nothing_live(self):
        for module, names in ((placements, ("DATA", "FOUNTAIN")), (coffer, ("SOURCE",))):
            for name in names:
                self.assertEqual(getattr(module, name).parent, LEGACY, f"{module.__name__}.{name}")
        for name in relocation.FROZEN:
            with (LEGACY / name).open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(relocation.read(name), list(csv.DictReader(stream)), name)
        # The live files of the same names are the Sanctum's: reading one of them would show map 750.
        self.assertEqual({r["map_id"] for r in relocation.read("world_hub_points.csv")}, {"530"})
        self.assertEqual({r["map_id"] for r in relocation.read("world_areas.csv")} - {"1"}, {"530"})


if __name__ == "__main__":
    unittest.main()
