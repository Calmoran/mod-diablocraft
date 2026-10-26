"""diablocraft-deeh (cross-tier Sanctum B4): the COMMITTED Sanctum migrations, in order, leave one of everything.

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum_whole.py        # needs the fixture mysqld (fixture_mysql.sh start)

The per-migration tests (test_hub_sanctum_move / _seal / test_sanctum_one_copy) drive each generator's output. This one runs the files the
server will apply (world_0031 door, world_0032 move, world_0037 one copy: the committed SQL, not a regeneration) on the Scryer-era state
Torment Development holds (the old hub with its nine tier copies of every thing), and checks the end state against the live sheets
(world_hub_placements.csv, the coffer, the door), not against a generator:

  * every sheet group, the Tester's Coffer and the door stand exactly once on map 750 area 4273, in phase 1, under their sheet guid and entry;
  * nothing else stands on map 750, and nothing anywhere is in a phase other than 1;
  * no retired copy guid is left in creature or gameobject, and dc_area_spawn is empty (no copy, for any area);
  * the registry holds each registered source once under the Sanctum's key, none twice.

Limits: the characters database (respawn rows) and the worldserver's own load are not run; the Scryer-era seed is the one test_hub_sanctum_move
builds, so a state that differs from it (the designer's hand rows in a tier phase) is covered only by test_sanctum_one_copy.
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_sanctum_move as move  # noqa: E402
import generate_hub_sanctum_seal as seal  # noqa: E402
import generate_sanctum_one_copy as one  # noqa: E402
import test_hub_sanctum_move as old_state  # noqa: E402
from test_hub_sanctum_seal import DONOR, Scratch  # noqa: E402
from test_sanctum_one_copy import sources  # noqa: E402

MAP, AREA = 750, 4273
CHAIN = ("0031_sanctum_seal", "0032_sanctum_hub_move", "0037_sanctum_one_copy")


def committed(stem):
    found = sorted(move.UPDATES.glob(f"world_{stem}.sql"))
    assert len(found) == 1, f"world_{stem}.sql is not committed"
    return found[0].read_text(encoding="utf-8")


class WholeSanctum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = sources()
        cls.chain = [committed(stem) for stem in CHAIN]

    def setUp(self):
        self.db = Scratch(old_state.TABLES)
        self.addCleanup(self.db.drop)
        old_state.seed(self.db)
        self.db.query(f"INSERT INTO gameobject_template SELECT * FROM acore_world.gameobject_template WHERE entry={DONOR};"
                      f"INSERT INTO gameobject_template_addon SELECT * FROM acore_world.gameobject_template_addon WHERE entry={DONOR}")
        self.assertGreater(int(self.db.query("SELECT COUNT(*) FROM dc_area_spawn")), 0, "the seeded old model holds copies, or this proves nothing")
        for sql in self.chain:
            self.db.query(sql)

    def count(self, sql):
        return int(self.db.query(sql))

    def test_every_group_the_coffer_and_the_door_stand_once_in_phase_one(self):
        self.assertEqual(len(self.sources), len(read_sheet()) + 2, "the sheet's groups, the coffer and the door")
        for kind, entry, guid, _ in self.sources:
            table = move.TABLES[kind]
            self.assertEqual(self.db.query(f"SELECT CONCAT(id,',',map,',',areaId,',',phaseMask) FROM {table} WHERE guid={guid}"),
                             f"{entry},{MAP},{AREA},1", f"{kind}:{entry} guid {guid}")

    def test_nothing_else_stands_on_the_sanctum_and_nothing_is_in_a_tier_phase(self):
        for table, kind in (("creature", "c"), ("gameobject", "g")):
            wanted = Counter(entry for k, entry, _, _ in self.sources if k == kind)
            found = Counter(int(e) for e in self.db.query(f"SELECT id FROM {table} WHERE map={MAP}").split())
            self.assertEqual(found, wanted, f"{table} on map {MAP}: one row per sheet row, nothing more")
            self.assertEqual(self.count(f"SELECT COUNT(*) FROM {table} WHERE phaseMask<>1"), 0, f"{table} in a tier phase")

    def test_no_retired_copy_is_left_and_the_registry_holds_no_copy(self):
        for kind, table in move.TABLES.items():
            guids = [str(c) for k, _, _, _, c in one.load() if k == kind]
            self.assertEqual(self.count(f"SELECT COUNT(*) FROM {table} WHERE guid IN ({','.join(guids)})"), 0, f"retired {table} copies")
        self.assertEqual(self.count("SELECT COUNT(*) FROM dc_area_spawn"), 0, "no copy row for any area")

    def test_the_registry_holds_each_source_once_under_the_sanctums_key(self):
        stood = {(kind, guid) for kind, _, guid, _ in self.sources}
        rows = [(r.split("\t")[0], int(r.split("\t")[1]), int(r.split("\t")[2]), int(r.split("\t")[3])) for r in self.db.query(
            "SELECT kind,source_guid,map_id,area_id FROM dc_area_source WHERE map_id=750 OR area_id=4273").splitlines()]
        self.assertEqual(len(rows), len(set(rows)), "a source twice")
        self.assertEqual({(m, a) for _, _, m, a in rows}, {(MAP, AREA)}, "only the Sanctum's key")
        self.assertEqual({(k, g) for k, g, _, _ in rows}, stood, "the registry holds every source that stands, and nothing else")


def read_sheet():
    return old_state.read(move.PLACEMENTS)


if __name__ == "__main__":
    unittest.main()
