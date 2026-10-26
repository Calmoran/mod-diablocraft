"""diablocraft-ugfc: the Sanctum of Torment's client DBC rows and their server overlay, built from one sheet.

    python3 mod-diablocraft/scripts/tests/world/test_hub_sanctum.py

Map 750 is Yogg-Saron's arena (Ulduar, map 603) as an open map. The sheet data/d3/world_sanctum_dbc.csv drives
generate_hub_sanctum.py, which writes the four client DBCs and the server's map_dbc / areatable_dbc overlay in one
run. Pinned here, each so that breaking the generator or the sheet turns something red:

  * append-only: every stock row of Map, WorldMapArea, Light, AreaTable, DungeonMap and DungeonMapChunk survives byte
    for byte, except the one row we rename in place (AreaTable 4273); our rows are the only additions; the new ids
    are free in stock;
  * the rows: Map 750 is row 603 with the directory kept, instance type 0, the new name and Ulduar's own loading
    screen (LoadingScreens row 244, read from the stock file; the brief's 142 is the Deadmines); WorldMapArea 750 and
    Light 2750 are clones that change only the map id; AreaTable 4273 changes only its name;
  * the world map's floors (diablocraft-bk308): Ulduar's map is drawn per floor, and the client finds the floor from
    DungeonMapChunk (map + WMO group -> DungeonMap row) and DungeonMap (map + floor index). Every Ulduar row of both is
    cloned onto map 750, each chunk pointing at the cloned floor of the same index, never at Ulduar's own row;
  * every file is a well-formed WDBC to a second, independent parser (sizes, unique ascending ids, string offsets);
  * the server overlay holds exactly the Map and AreaTable rows the client files hold, deletes before it inserts and
    carries no WorldMapArea, Light, DungeonMap or DungeonMapChunk row (the core reads none of them for map 750);
  * rerun-safe: running over its own output changes nothing, a different row already on a new id is refused, every
    wrong sheet is refused, the committed files are exactly what the generator renders now, and emit() leaves
    identical files alone;
  * single-rule mutants: a wrong sheet value, and each rule of the generator broken in an in-memory copy of its source,
    must fail the check that guards it (nothing is written to the tree, so a killed run leaves nothing behind).
"""
import re
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_hub_sanctum as gen  # noqa: E402
from dbc_store import Store  # noqa: E402

TMP = tempfile.TemporaryDirectory(prefix="sanctum_")
SHEET = gen.SOURCE.read_text(encoding="utf-8")
_sheets = []


def under_tmp(path):
    assert Path(path).resolve().is_relative_to(Path(TMP.name).resolve()), f"{path} is not under the test's temp dir"
    return Path(path)


def sheet_with(*replacements):
    """A copy of the sheet in the temp dir with each (old, new) applied; `old` must occur exactly once."""
    text = SHEET
    for old, new in replacements:
        assert text.count(old) == 1, f"{old!r} is not in the sheet exactly once"
        text = text.replace(old, new)
    _sheets.append(under_tmp(Path(TMP.name) / f"sheet{len(_sheets)}.csv"))
    _sheets[-1].write_text(text, encoding="utf-8")
    return _sheets[-1]


def columns(g, table):
    return g.columns(table)


def stock(g, table, stock_dir=None):
    return Store(g.stock_path(stock_dir or g.STOCK_DIR, table).read_bytes(), columns(g, table))


def pair(g, outputs, table):
    return Store(outputs[f"{table}.dbc"], columns(g, table)), stock(g, table)


def loading_screen_name(g, row_id):
    """LoadingScreens.dbc row `row_id`'s name, read with plain struct (it is not one of ours to write)."""
    data = (g.STOCK_DIR / "LoadingScreens.dbc").read_bytes()
    _, count, fields, size, _ = struct.unpack_from("<4s4I", data)
    strings = data[20 + count * size:]
    for index in range(count):
        values = struct.unpack_from(f"<{fields}I", data, 20 + index * size)
        if values[0] == row_id:
            return strings[values[1]:strings.index(b"\0", values[1])].decode()
    return None


def tuple_values(sql, table):
    """{column: value} of the one row `INSERT INTO table` carries (strings unquoted, numbers as text)."""
    match = re.search(r"INSERT INTO `%s` \((.*?)\) VALUES\n\((.*)\);" % table, sql)
    assert match, f"no INSERT INTO {table}"
    names = [n.strip("`") for n in match.group(1).split(",")]
    body, values, i = match.group(2), [], 0
    while i < len(body):
        if body[i] == "'":
            j, text = i + 1, ""
            while True:
                if body[j] == "'" and body[j + 1:j + 2] == "'":
                    text, j = text + "'", j + 2
                elif body[j] == "'":
                    break
                else:
                    text, j = text + body[j], j + 1
            values.append(text)
            i = j + 2
        else:
            j = body.find(",", i)
            j = len(body) if j < 0 else j
            values.append(body[i:j])
            i = j + 1
    assert len(values) == len(names), (len(values), len(names))
    return dict(zip(names, values))


# ---- checks on one build: (g, outputs, sql); each raises on a defect ----

ADDED = {"Map": 1, "WorldMapArea": 1, "Light": 1, "AreaTable": 0}  # the floor tables add one row per Ulduar row


def on_map(store, map_id):
    return [store.decode(k) for k in store.rows if store.decode(k)["MapID"] == map_id]


def check_stock_kept(g, outputs, sql):
    for table in g.TABLES:
        if f"{table}.dbc" not in outputs:   # a table only a later layer writes (WorldMapOverlay, the open-rift map)
            continue
        new, old = pair(g, outputs, table)
        renamed = {4273} if table == "AreaTable" else set()
        for key, row in old.rows.items():
            if key not in renamed:
                assert new.rows.get(key) == row, f"{table}.dbc stock row {key} changed or is gone"
        added = ADDED[table] if table in ADDED else len(on_map(old, 603))
        assert len(new.rows) == len(old.rows) + added, f"{table}.dbc row count"


def check_map_row(g, outputs, sql):
    new, old = pair(g, outputs, "Map")
    ours, ulduar = new.decode(750), old.decode(603)
    assert ours["Directory"] == "UlduarRaid", "the client reads the terrain by directory"
    assert ours["InstanceType"] == 0, "an open map, not a raid"
    assert ours["MapName_Lang_enUS"] == "Sanctum of Torment"
    assert ours["LoadingScreenID"] == ulduar["LoadingScreenID"], "Ulduar's own loading screen"
    assert loading_screen_name(g, ours["LoadingScreenID"]) == "InstanceUlduarRaid"
    for field in ours:
        if field not in ("ID", "InstanceType", "MapName_Lang_enUS"):
            assert ours[field] == ulduar[field], f"Map {field} is copied from 603"


def check_clones(g, outputs, sql):
    for table, new_id, base, field in (("WorldMapArea", 750, 529, "MapID"), ("Light", 2750, 1862, "ContinentID")):
        new, old = pair(g, outputs, table)
        ours, source = new.decode(new_id), old.decode(base)
        assert ours[field] == 750, f"{table} {new_id} is on map 750"
        for name in ours:
            if name not in ("ID", field):
                assert ours[name] == source[name], f"{table} {name} is copied from row {base}"


def check_area_rename(g, outputs, sql):
    new, old = pair(g, outputs, "AreaTable")
    ours, base = new.decode(4273), old.decode(4273)
    assert base["AreaName_Lang_enUS"] == "Ulduar", "the stock row is the Ulduar area"
    assert ours["AreaName_Lang_enUS"] == "Sanctum of Torment"
    for field in ours:
        if field != "AreaName_Lang_enUS":
            assert ours[field] == base[field], f"AreaTable {field} is unchanged"


def check_dungeon_floors(g, outputs, sql):
    floors, old_floors = pair(g, outputs, "DungeonMap")
    chunks, old_chunks = pair(g, outputs, "DungeonMapChunk")
    ours = {f["FloorIndex"]: f for f in on_map(floors, 750)}
    ulduar = {f["FloorIndex"]: f for f in on_map(old_floors, 603)}
    assert ulduar and sorted(ours) == sorted(ulduar) and len(ours) == len(on_map(floors, 750)), \
        "map 750 has each of Ulduar's floors once"
    for index, floor in ulduar.items():
        assert {**ours[index], "ID": floor["ID"], "MapID": 603} == floor, f"floor {index} is Ulduar's but for the map"
    floor_of = {f["ID"]: f["FloorIndex"] for f in ours.values()}
    ulduar_floor_of = {f["ID"]: f["FloorIndex"] for f in ulduar.values()}
    mine = {(c["WmoGroupID"], c["MinZ"]): c for c in on_map(chunks, 750)}
    theirs = on_map(old_chunks, 603)
    assert len(mine) == len(theirs) == len(on_map(chunks, 750)), "each Ulduar chunk has one clone on map 750"
    for chunk in theirs:
        clone = mine.get((chunk["WmoGroupID"], chunk["MinZ"]))
        assert clone, f"WMO group {chunk['WmoGroupID']} has no chunk on map 750"
        assert clone["DungeonMapID"] in floor_of, f"chunk {clone['ID']} points at a floor row that is not on map 750"
        assert floor_of[clone["DungeonMapID"]] == ulduar_floor_of[chunk["DungeonMapID"]], \
            f"chunk {clone['ID']} is on another floor than Ulduar's"


def ids_and_strings(data, cols):
    """(ids, [(row, column, offset)] of every string field, string block) by plain struct, without Store."""
    magic, count, fields, size, strings = struct.unpack_from("<4s4I", data)
    assert (magic, fields, size) == (b"WDBC", len(cols), 4 * len(cols)), "header does not fit the columns"
    assert len(data) == 20 + count * size + strings, "header sizes disagree with the file length"
    ids = [struct.unpack_from("<I", data, 20 + i * size)[0] for i in range(count)]
    offsets = [(i, c, struct.unpack_from("<I", data, 20 + i * size + 4 * c)[0])
               for i in range(count) for c, (_, kind, _) in enumerate(cols) if kind in ("varchar", "text")]
    return ids, offsets, data[20 + count * size:]


def check_wellformed(g, outputs, sql):
    for name, data in outputs.items():
        table = name[:-4]
        cols = columns(g, table)
        ids, offsets, block = ids_and_strings(data, cols)
        old_ids = ids_and_strings(g.stock_path(g.STOCK_DIR, table).read_bytes(), cols)[0]
        assert len(set(ids)) == len(ids), f"{name}: duplicate ids"
        # stock DungeonMapChunk is not in id order, so the client keys rows by id, not position; ours follow suit
        assert old_ids != sorted(old_ids) or ids == sorted(ids), f"{name}: ids are not ascending like the stock file's"
        for row, column, offset in offsets:
            ok = offset < len(block) and (offset == 0 or block[offset - 1] == 0) and block.find(b"\0", offset) >= 0
            assert ok, f"{name}: row {ids[row]} column {cols[column][0]} points outside the string block"


def check_server_overlay(g, outputs, sql):
    for table, row_id in (("Map", 750), ("AreaTable", 4273)):
        sql_table = g.TABLES[table][0]
        row = Store(outputs[f"{table}.dbc"], columns(g, table)).decode(row_id)
        parsed = tuple_values(sql, sql_table)
        assert set(parsed) == set(row), f"{sql_table}: columns differ"
        for column, value in row.items():
            text = parsed[column]
            if isinstance(value, float):
                text = struct.unpack("<f", struct.pack("<f", float(text)))[0]
            elif not isinstance(value, str):
                text = int(text)
            assert text == value, f"{sql_table}.{column}: the server says {text!r}, the client file {value!r}"
        delete = f"DELETE FROM `{sql_table}` WHERE `ID` IN ({row_id});"
        assert delete in sql and sql.index(delete) < sql.index(f"INSERT INTO `{sql_table}`"), \
            f"{sql_table}: delete first, so a rerun cannot double the row"
    assert "worldmaparea_dbc" not in sql and "light_dbc" not in sql, "WorldMapArea and Light are the client's alone"
    assert "dungeonmap" not in sql.lower(), "DungeonMap and DungeonMapChunk are the client's alone"


OUTPUT_CHECKS = (check_stock_kept, check_map_row, check_clones, check_area_rename, check_dungeon_floors, check_wellformed,
                 check_server_overlay)


# ---- checks that drive the generator itself: (g) ----

BAD_SHEETS = (
    ("a taken id", [("Light,2750,1862", "Light,750,1862")]),
    ("an unknown field", [("Directory", "Directry")]),
    ("a missing clone source", [("WorldMapArea,750,529", "WorldMapArea,750,99999")]),
    ("a value that is not its column's type", [("Map,750,603,InstanceType,0", "Map,750,603,InstanceType,zero")]),
    ("an unknown table", [("AreaTable,", "Skybox,")]),
    ("a field set twice", [("Map,750,603,InstanceType,0,", "Map,750,603,InstanceType,2,again\nMap,750,603,InstanceType,0,")]),
    ("one id with two sources", [("Map,750,603,InstanceType,0,", "Map,750,604,Flags,13,again\nMap,750,603,InstanceType,0,")]),
)


def own_output_as_stock(g, outputs):
    folder = Path(tempfile.mkdtemp(prefix="stock_", dir=under_tmp(TMP.name)))
    for name, data in outputs.items():
        (folder / name).write_bytes(data)
    return under_tmp(folder)


def refused(g, label, source, stock_dir):
    try:
        g.generate(source, stock_dir)
    except g.SanctumError:
        return
    except Exception as error:  # noqa: BLE001 - a crash is not a refusal
        raise AssertionError(f"{label}: crashed with {type(error).__name__}: {error}") from None
    raise AssertionError(f"{label}: was not refused")


def check_refuses_bad_input(g):
    for label, replacements in BAD_SHEETS:
        refused(g, label, sheet_with(*replacements), g.STOCK_DIR)
    refused(g, "a missing stock folder", g.SOURCE, Path(tempfile.mkdtemp(prefix="nostock_", dir=under_tmp(TMP.name))))


def check_rerun_is_noop(g):
    outputs, sql = g.generate(g.SOURCE, g.STOCK_DIR)
    again, sql_again = g.generate(g.SOURCE, own_output_as_stock(g, outputs))
    assert (again, sql_again) == (outputs, sql), "a rerun over our own output changed something"


def check_refuses_a_different_row(g):
    outputs, _ = g.generate(g.SOURCE, g.STOCK_DIR)
    folder = own_output_as_stock(g, outputs)
    store = Store(outputs["Map.dbc"], columns(g, "Map"))
    values = store.decode(750)
    values["Flags"] += 1
    store.encode(values)
    (folder / "Map.dbc").write_bytes(store.bytes())
    try:
        g.generate(g.SOURCE, folder)
    except g.SanctumError as error:
        assert "refusing to overwrite" in str(error), str(error)
    else:
        raise AssertionError("a different row on id 750 was overwritten, not refused")


BEHAVIOUR_CHECKS = (check_refuses_bad_input, check_rerun_is_noop, check_refuses_a_different_row)


def failing(g):
    """Names of the checks one generator module fails on the real sheet (a crash counts as a failure)."""
    failed = []
    try:
        outputs, sql = g.generate(g.SOURCE, g.STOCK_DIR)
    except Exception as error:  # noqa: BLE001
        failed.append(f"generate raised {type(error).__name__}: {error}")
    else:
        for check in OUTPUT_CHECKS:
            try:
                check(g, outputs, sql)
            except Exception:  # noqa: BLE001
                failed.append(check.__name__)
    for check in BEHAVIOUR_CHECKS:
        try:
            check(g)
        except Exception:  # noqa: BLE001
            failed.append(check.__name__)
    return failed


def mutant(*replacements):
    """The generator module with each (old, new) applied to its source, in memory only."""
    text = Path(gen.__file__).read_text(encoding="utf-8")
    for old, new in replacements:
        assert text.count(old) == 1, f"{old!r} is not in the generator exactly once"
        text = text.replace(old, new)
    module = types.ModuleType("generate_hub_sanctum_mutant")
    module.__file__ = gen.__file__
    exec(compile(text, gen.__file__, "exec"), module.__dict__)
    return module


WRITE_OUTPUT = '        outputs[f"{table}.dbc"] = store.bytes()\n'
NO_GUARD = '        if False:\n'
DELETE_LINE = ('        lines.append("DELETE FROM `%s` WHERE `ID` IN (%s);" % '
               '(sql_table, ",".join(str(r["ID"]) for r in rows)))\n')

# (what is broken, [(old, new) in the generator's source], the check or checks that have to catch it)
MUTANTS = (
    ("a file that holds only our rows", [(WRITE_OUTPUT, '        store.rows = {v["ID"]: store.rows[v["ID"]] for v in ours}\n' + WRITE_OUTPUT)],
     "check_stock_kept"),
    ("a clone that overwrites its source row, with the generator's own guard off",
     [('        values["ID"] = row_id\n', '        values["ID"] = source_id\n'), ('        if lost:\n', NO_GUARD)],
     "check_stock_kept"),
    ("a clone of the wrong row", [('        values = store.decode(source_id)\n', '        values = store.decode(next(iter(store.rows)))\n')],
     ("check_map_row", "check_clones", "check_area_rename")),
    ("a different existing row overwritten",
     [('        if row_id in store.rows and row_id != source_id and store.decode(row_id) != values:\n', NO_GUARD)],
     "check_refuses_a_different_row"),
    # a taken id is refused twice (the clone check and the stock-rows-changed check): only both off lets it through
    ("a taken id overwritten, both of the generator's guards off",
     [('        if row_id in store.rows and row_id != source_id and store.decode(row_id) != values:\n', NO_GUARD),
      ('        if lost:\n', NO_GUARD)],
     "check_refuses_bad_input"),
    ("a migration that does not delete first", [(DELETE_LINE, '')], "check_server_overlay"),
    ("WorldMapArea sent to the server too", [('    "WorldMapArea": ("worldmaparea_dbc", False),\n', '    "WorldMapArea": ("worldmaparea_dbc", True),\n')],
     "check_server_overlay"),
    ("a server row that drifts from the client row",
     [('        ours.append(values)\n', '        ours.append(dict(values, Flags=0) if table == "Map" else values)\n')],
     "check_server_overlay"),
    ("a field set twice accepted", [('        if field in fields:\n', NO_GUARD)], "check_refuses_bad_input"),
    ("two sources for one id accepted", [('        if have_source != source:\n', NO_GUARD)], "check_refuses_bad_input"),
    ("an unknown field accepted", [('        if unknown:\n', NO_GUARD)], "check_refuses_bad_input"),
    ("a missing clone source accepted", [('        if source_id not in store.rows:\n', NO_GUARD)], "check_refuses_bad_input"),
    ("a value taken as it is, whatever the column", [('        return int(raw)\n', '        return raw\n')], "check_refuses_bad_input"),
    ("a floor table's columns misnamed", [('("WmoGroupID", "int", ""), ("DungeonMapID", "int", "")',
                                           '("DungeonMapID", "int", ""), ("WmoGroupID", "int", "")')],
     "check_dungeon_floors"),
    ("a missing stock folder not refused", [('    if not path.is_file():\n', '    if False:\n')], "check_refuses_bad_input"),
)


class RealBuild(unittest.TestCase):
    def test_every_check_holds_on_the_real_sheet_and_stock(self):
        outputs, sql = gen.generate(gen.SOURCE, gen.STOCK_DIR)
        for check in OUTPUT_CHECKS:
            with self.subTest(check=check.__name__):
                check(gen, outputs, sql)
        for check in BEHAVIOUR_CHECKS:
            with self.subTest(check=check.__name__):
                check(gen)

    def test_new_ids_are_free_in_stock(self):
        for table, row_id in (("Map", 750), ("WorldMapArea", 750), ("Light", 2750)):
            self.assertNotIn(row_id, stock(gen, table).rows, f"{table} {row_id} is already a stock row")
        outputs, _ = gen.generate(gen.SOURCE, gen.STOCK_DIR)
        for table in ("DungeonMap", "DungeonMapChunk"):
            new, old = pair(gen, outputs, table)
            ours = {r["ID"] for r in on_map(new, 750)}
            self.assertTrue(ours)
            self.assertFalse(ours & set(old.rows), f"{table}: a clone id is already a stock row")

    def test_committed_outputs_are_what_the_generator_renders(self):
        # The client DBCs are single files that the open-world rift layer (diablocraft-kw18) builds over this layer's
        # output: the committed files are the last layer's render, and test_open_rift_map.py holds that they keep every
        # row of this one. This layer's own migration is frozen and must render as it did.
        outputs, sql = gen.generate(gen.SOURCE, gen.STOCK_DIR)
        if gen.OPEN_RIFT_SOURCE.is_file():
            import generate_open_rift_map as later
            outputs, _ = later.generate(gen.STOCK_DIR)
        for name, data in outputs.items():
            self.assertEqual((gen.CLIENT_DIR / name).read_bytes(), data, f"{name} is stale: rerun the newest layer's generator")
        self.assertEqual(gen.MIGRATION.read_text(encoding="utf-8"), sql, f"{gen.MIGRATION.name} is stale")

    def test_the_six_files_are_ours_alone(self):
        # WorldMapOverlay is the open-rift layer's (zone fog, diablocraft-y0gjt); the Sanctum's sheet has no row for it
        self.assertEqual(sorted(gen.TABLES), ["AreaTable", "DungeonMap", "DungeonMapChunk", "Light", "Map", "WorldMapArea",
                                              "WorldMapOverlay"])
        self.assertNotIn("WorldMapOverlay.dbc", gen.generate(gen.SOURCE, gen.STOCK_DIR)[0])
        self.assertEqual([t for t, (_, server) in gen.TABLES.items() if server], ["Map", "AreaTable"])

    def test_emit_writes_once_and_a_rerun_touches_nothing(self):
        outputs, sql = gen.generate(gen.SOURCE, gen.STOCK_DIR)
        root = Path(tempfile.mkdtemp(prefix="emit_", dir=under_tmp(TMP.name)))
        (root / "data/sql/db-world/updates").mkdir(parents=True)
        (root / "data/sql/applied_migrations.csv").write_text("path,sha1,provenance\n", encoding="utf-8")
        migration, client = under_tmp(root / "data/sql/db-world/updates" / gen.MIGRATION.name), under_tmp(root / "client")
        self.assertTrue(gen.emit(root, migration, client, outputs, sql))
        self.assertEqual(sorted(p.name for p in client.iterdir()), sorted(outputs))
        for name, data in outputs.items():
            self.assertEqual((client / name).read_bytes(), data)
        self.assertEqual(migration.read_text(encoding="utf-8"), sql)
        stamps = {p: p.stat().st_mtime_ns for p in client.iterdir()}
        self.assertTrue(gen.emit(root, migration, client, outputs, sql))
        self.assertEqual({p: p.stat().st_mtime_ns for p in client.iterdir()}, stamps, "a rerun rewrote a client file")
        self.assertEqual(migration.read_text(encoding="utf-8"), sql)


class WrongSheetValues(unittest.TestCase):
    """A wrong design value in the sheet builds rows the real checks reject."""

    def caught(self, *replacements, by):
        outputs, sql = gen.generate(sheet_with(*replacements), gen.STOCK_DIR)
        with self.assertRaises(AssertionError):
            by(gen, outputs, sql)

    def test_a_raid_map_is_caught(self):
        self.caught(("Map,750,603,InstanceType,0", "Map,750,603,InstanceType,2"), by=check_map_row)

    def test_the_briefs_deadmines_loading_screen_is_caught(self):
        self.caught(("LoadingScreenID,244", "LoadingScreenID,142"), by=check_map_row)

    def test_a_wrong_directory_is_caught(self):
        self.caught(("Directory,UlduarRaid", "Directory,Ulduar"), by=check_map_row)

    def test_a_wrong_name_is_caught(self):
        self.caught(("Map,750,603,MapName_Lang_enUS,Sanctum of Torment", "Map,750,603,MapName_Lang_enUS,Ulduar"),
                    by=check_map_row)

    def test_a_world_map_left_on_ulduar_is_caught(self):
        self.caught(("WorldMapArea,750,529,MapID,750", "WorldMapArea,750,529,MapID,603"), by=check_clones)

    def test_a_light_left_on_ulduar_is_caught(self):
        self.caught(("Light,2750,1862,ContinentID,750", "Light,2750,1862,ContinentID,603"), by=check_clones)

    def test_a_floor_left_on_ulduar_is_caught(self):
        self.caught(("DungeonMap,1072,72,MapID,750", "DungeonMap,1072,72,MapID,603"), by=check_dungeon_floors)

    def test_a_chunk_pointing_at_ulduars_own_floor_is_caught(self):
        self.caught(("DungeonMapChunk,11677,1677,DungeonMapID,1072", "DungeonMapChunk,11677,1677,DungeonMapID,72"),
                    by=check_dungeon_floors)

    def test_a_chunk_on_the_wrong_floor_is_caught(self):
        self.caught(("DungeonMapChunk,11677,1677,DungeonMapID,1072", "DungeonMapChunk,11677,1677,DungeonMapID,1071"),
                    by=check_dungeon_floors)

    def test_an_area_left_named_ulduar_is_caught(self):
        self.caught(("AreaTable,4273,4273,AreaName_Lang_enUS,Sanctum of Torment",
                     "AreaTable,4273,4273,AreaName_Lang_enUS,Ulduar"), by=check_area_rename)


class GeneratorMutants(unittest.TestCase):
    """Each rule of the generator, broken in a copy of its source, fails the check that guards it."""

    def test_an_unbroken_copy_passes_everything(self):
        self.assertEqual(failing(mutant()), [], "the in-memory copy must behave like the module")

    def test_each_broken_rule_fails_the_check_that_guards_it(self):
        for name, replacements, expected in MUTANTS:
            with self.subTest(broken=name, checks=expected):
                self.assertLessEqual({expected} if isinstance(expected, str) else set(expected),
                                     set(failing(mutant(*replacements))))


if __name__ == "__main__":
    unittest.main()
