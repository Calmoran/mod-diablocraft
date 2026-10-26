"""diablocraft-kw18: the open-world rift map 751 (Kalimdor's terrain as a private party instance); diablocraft-hyoic.6: 752,
the Eastern Kingdoms', a third layer; diablocraft-hyoic.9: 753, Outland's, a fourth.

generate_open_rift_map.py builds its layers over the Sanctum's output and writes the client Map, WorldMapArea,
Light and WorldMapOverlay rows (the last: zone fog, diablocraft-y0gjt) plus each layer's server overlay (map_dbc,
mapdifficulty_dbc, instance_template). This pins: the new rows are
clones of Kalimdor's with only the sheet's fields changed; every stock row and the Sanctum's own rows survive
byte for byte; the ids are free in stock; the overlay carries the two rows the core demands before it lets anyone into
a dungeon-type map; the committed files are what the generator renders; and each rule fails the check when a single
line of the generator is broken.

Not covered: that a client reads the rows and the terrain as an instance (docs/test-diablocraft-kw18.md is the walk),
or that the core takes the overlay on a real start.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_sanctum as sanctum  # noqa: E402
import generate_open_rift_map as gen  # noqa: E402
from dbc_store import Store, schema  # noqa: E402

TABLES = {"Map": "map_dbc", "WorldMapArea": "worldmaparea_dbc", "Light": "light_dbc", "AreaTable": "areatable_dbc",
          "WorldMapOverlay": "worldmapoverlay_dbc"}
# Each clone layer: (clone map, source map, its directory, WorldMapArea rows, Light rows, WorldMapOverlay rows)
# (diablocraft-kw18, -y0gjt zone fog, -hyoic.6, -hyoic.9: 752 and 753 have no overlay rows).
CLONES = ((751, 1, "Kalimdor", 22, 127, 230), (752, 0, "Azeroth", 26, 82, 0), (753, 530, "Expansion01", 9, 176, 0))
# 753's world map is Outland's 9 rows only; map 530's other 7 (the Blood Elf and Draenei isles) are not in act 5
# (docs/research/bounty-acts.md 6, diablocraft-hyoic.9).
OUTLAND_WMA = {465, 466, 467, 473, 475, 477, 478, 479, 481}
# The Map fields a sheet sets; every other field is the source row's.
SET = ("ID", "InstanceType", "MapName_Lang_enUS", "CorpseMapID", "CorpseX", "CorpseY", "MaxPlayers")


def store(table, data):
    return Store(data, schema(gen.ROOT, TABLES[table]))


def stock(table):
    return store(table, sanctum.stock_path(sanctum.STOCK_DIR, table).read_bytes())


def check_all(mod, test):
    """Every rule of the sheets' output, against `mod` (the real generator or a mutant of it)."""
    outputs, sqls = mod.generate(sanctum.STOCK_DIR)
    base, _ = sanctum.generate(sanctum.SOURCE, sanctum.STOCK_DIR)
    # the Sanctum layer survives, row for row, and so does every stock row
    for table in ("Map", "WorldMapArea", "Light", "AreaTable", "WorldMapOverlay"):
        mine, raw = store(table, outputs[f"{table}.dbc"]), stock(table)
        layer = store(table, base[f"{table}.dbc"]) if f"{table}.dbc" in base else raw   # the Sanctum has no overlay rows
        for row_id, raw_row in layer.rows.items():
            test.assertEqual(mine.rows.get(row_id), raw_row, f"{table} {row_id} of the Sanctum layer changed")
        for row_id, raw_row in raw.rows.items():
            if (table, row_id) != ("AreaTable", 4273):  # the Sanctum's own rename, checked against its layer above
                test.assertEqual(mine.rows.get(row_id), raw_row, f"{table} {row_id} is a stock row and changed")
    maps, wma, light = (store(t, outputs[f"{t}.dbc"]) for t in ("Map", "WorldMapArea", "Light"))
    stock_wma, stock_light = stock("WorldMapArea"), stock("Light")
    test.assertEqual(list(sqls), [gen.MIGRATION, gen.EK_MIGRATION, gen.OUTLAND_MIGRATION])   # one migration a layer, in build order
    migrations = {751: gen.MIGRATION, 752: gen.EK_MIGRATION, 753: gen.OUTLAND_MIGRATION}
    overlay, stock_overlay = store("WorldMapOverlay", outputs["WorldMapOverlay.dbc"]), stock("WorldMapOverlay")
    for clone, source, directory, wma_rows, light_rows, overlay_rows in CLONES:
        sql = sqls[migrations[clone]]
        origin = stock("Map").decode(source)
        row = maps.decode(clone)
        test.assertEqual({k: v for k, v in row.items() if k not in SET}, {k: v for k, v in origin.items() if k not in SET},
                         f"the Map row {clone} is its continent's but for the sheet's fields")
        test.assertEqual((row["Directory"], row["InstanceType"], row["MaxPlayers"]), (directory, 1, 4))
        # the world map and the sky: every row of the continent cloned, ids free, nothing else different
        old_wma = [i for i in stock_wma.rows if stock_wma.decode(i)["MapID"] == source and (clone != 753 or i in OUTLAND_WMA)]
        old_light = [i for i in stock_light.rows if stock_light.decode(i)["ContinentID"] == source]
        new_wma = [i for i in wma.rows if i not in stock_wma.rows and wma.decode(i)["MapID"] == clone]
        new_light = [i for i in light.rows if i not in stock_light.rows and light.decode(i)["ContinentID"] == clone]
        test.assertEqual((len(old_wma), len(new_wma)), (wma_rows, wma_rows))
        test.assertEqual((len(old_light), len(new_light)), (light_rows, light_rows))
        for i in old_wma:
            test.assertEqual({**wma.decode(3000 + i), "ID": i, "MapID": source}, stock_wma.decode(i))
        for i in old_light:
            test.assertEqual({**light.decode(5000 + i), "ID": i, "ContinentID": source}, stock_light.decode(i))
        # zone fog (diablocraft-y0gjt): every overlay of a cloned world map is cloned onto that map's clone, so the client has
        # a sub-area to light on the copy; the areas, textures and places are the stock row's
        new_overlay = [i for i in overlay.rows if i not in stock_overlay.rows and overlay.decode(i)["MapAreaID"] in new_wma]
        test.assertEqual(len(new_overlay), overlay_rows)
        if overlay_rows:
            old_overlay = [i for i in stock_overlay.rows if stock_overlay.decode(i)["MapAreaID"] in old_wma]
            test.assertEqual(len(old_overlay), overlay_rows)
            for i in old_overlay:
                copy, original = overlay.decode(3000 + i), stock_overlay.decode(i)
                test.assertIn(copy["MapAreaID"], new_wma)
                test.assertEqual(wma.decode(copy["MapAreaID"])["AreaID"], stock_wma.decode(original["MapAreaID"])["AreaID"])
                test.assertEqual({**copy, "ID": i, "MapAreaID": original["MapAreaID"]}, original)
        # the server overlay: this map's rows only
        test.assertIn(f"DELETE FROM `map_dbc` WHERE `ID` IN ({clone});", sql)
        test.assertNotIn("(750,", sql)                                  # the Sanctum's rows are world_0030's, not ours
        test.assertIn(f"DELETE FROM `instance_template` WHERE `map` IN ({clone});", sql)
        test.assertIn(f"DELETE FROM `mapdifficulty_dbc` WHERE `ID` IN ({clone}0);", sql)
        test.assertIn(f"INSERT INTO `instance_template` (`map`,`parent`,`script`,`allowMount`) VALUES ({clone},{source},'',1);", sql)
        test.assertRegex(sql, rf"\({clone}0,{clone},0,'',.*,16712190,0,4,''\);")  # normal difficulty, no reset, four players
        test.assertEqual(sql.count("INSERT INTO"), 3)
        test.assertNotIn("worldmapoverlay", sql.lower())             # the overlay rows are the client's alone
    test.assertEqual(len([i for i in overlay.rows if i not in stock_overlay.rows]), sum(c[5] for c in CLONES))   # no stray overlay row
    # 751 keeps its corpse point; 752 keeps row 0's (no entrance yet: diablocraft-hyoic.6)
    test.assertEqual([maps.decode(751)[k] for k in ("CorpseMapID", "MapName_Lang_enUS")], [1, "Kalimdor Rift"])
    test.assertEqual([maps.decode(752)[k] for k in ("CorpseMapID", "CorpseX", "CorpseY", "MapName_Lang_enUS")],
                     [-1, 0.0, 0.0, "Eastern Kingdoms"])
    # 753: no entrance either (row 530 carries 0, which would point a dungeon's corpse arrow at map 0)
    test.assertEqual([maps.decode(753)[k] for k in ("CorpseMapID", "CorpseX", "CorpseY", "MapName_Lang_enUS")],
                     [-1, 0.0, 0.0, "Outland"])
    test.assertFalse([i for i in wma.rows if wma.decode(i)["MapID"] == 753 and i - 3000 not in OUTLAND_WMA])


class RealBuild(unittest.TestCase):
    def test_every_rule_holds_on_the_real_sheet_and_stock(self):
        check_all(gen, self)

    def test_new_ids_are_free_in_stock(self):
        diffs = Store(sanctum.stock_path(sanctum.STOCK_DIR, "MapDifficulty").read_bytes(), schema(gen.ROOT, "mapdifficulty_dbc"))
        for clone, *_ in CLONES:
            self.assertNotIn(clone, stock("Map").rows)
            self.assertNotIn(clone * gen.DIFFICULTY_ID_FACTOR, diffs.rows)
        self.assertEqual([gen.map_row(source)[:2] for source, *_ in gen.LAYERS], [(751, 1), (752, 0), (753, 530)])

    def test_committed_outputs_are_what_the_generator_renders(self):
        outputs, sqls = gen.generate(sanctum.STOCK_DIR)
        for name, data in outputs.items():
            self.assertEqual((sanctum.CLIENT_DIR / name).read_bytes(), data, f"{name} is stale: rerun generate_open_rift_map.py")
        for migration, sql in sqls.items():
            self.assertEqual(migration.read_text(encoding="utf-8"), sql, f"{migration.name} is stale")
        # the first layer's migration is frozen and renders as it did
        _, sanctum_sql = sanctum.generate(sanctum.SOURCE, sanctum.STOCK_DIR)
        self.assertEqual(sanctum.MIGRATION.read_text(encoding="utf-8"), sanctum_sql)

    def test_the_sanctum_generator_does_not_overwrite_the_later_layer(self):
        self.assertIn("generate_open_rift_map.py", sanctum.main([]) or "")


# One rule at a time. Each must make check_all fail.
MUTATIONS = (
    ("a rerun cannot replace the instance_template row", 'lines.append("DELETE FROM `instance_template` WHERE `map` IN (%d);" % map_id)\n', "pass\n"),
    ("the instance_template row is missing", 'lines.append("INSERT INTO `instance_template` (`map`,`parent`,`script`,`allowMount`) VALUES (%d,%d,\'\',1);" % (map_id, parent))\n', "pass\n"),
    ("the parent is not the source continent", "VALUES (%d,%d,'',1);\" % (map_id, parent)", "VALUES (%d,%d,'',1);\" % (map_id, 1)"),
    ("a later layer is built over the Sanctum's, not the one before", "outputs, map_sql = layer(outputs, stock_dir, source)",
     "outputs, map_sql = layer(sanctum.generate(sanctum_source, stock_dir)[0], stock_dir, source)"),
    ("a layer's migration is lost", "sqls[migration] = migration_sql(", "sqls[MIGRATION] = migration_sql("),
    ("the difficulty row is for a different party size", '"MaxPlayers": max_players,', '"MaxPlayers": 5,'),
    ("a rerun cannot replace the difficulty row", 'lines.append("DELETE FROM `mapdifficulty_dbc` WHERE `ID` IN (%d);" % difficulty["ID"])\n', "pass\n"),
    ("a reset time is left on the copy", '"RaidDuration": 0,', '"RaidDuration": 86400,'),
    ("the Sanctum layer is lost", "outputs = {**base, **own}", "outputs = {**own}"),
    ("the Sanctum layer is not the base", "(Path(layer) / name).write_bytes(data)", "pass"),
)


class Mutants(unittest.TestCase):
    def test_each_rule_fails_the_check_when_broken(self):
        source = Path(gen.__file__).read_text(encoding="utf-8")
        self.assertIsNone(self.run_source(source), "the unmutated generator must pass the checks")
        for name, old, new in MUTATIONS:
            with self.subTest(mutation=name):
                self.assertEqual(source.count(old), 1, f"mutation target {old!r} is not unique")
                self.assertIsNotNone(self.run_source(source.replace(old, new)), f"the checks passed with: {name}")

    def run_source(self, source):
        """None when every check holds for this source of the generator, else the failure."""
        namespace = {"__name__": "mutant", "__file__": gen.__file__}

        class Mod:
            pass
        try:
            exec(compile(source, "mutant.py", "exec"), namespace)
            Mod.generate = staticmethod(namespace["generate"])
            check_all(Mod, self)
        except Exception as error:  # noqa: BLE001 - a broken generator or a failed check both count
            return error
        return None


if __name__ == "__main__":
    unittest.main(verbosity=2)
