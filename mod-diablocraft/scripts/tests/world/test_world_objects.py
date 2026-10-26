"""diablocraft-8jd5: Torment's own object displays and the decoration templates wearing them.

    python3 mod-diablocraft/scripts/tests/world/test_world_objects.py

Two sheets (world_object_displays.csv, world_objects.csv) drive generate_world_objects.py. Pinned, each so that breaking
the generator or a sheet turns something red:

  * the PACKED client-patch/patch-4.MPQ holds DBFilesClient\\GameObjectDisplayInfo.dbc with every stock row byte for
    byte and exactly the sheet's rows besides (read by a parser of its own, not the generator's Store);
  * the committed client DBC and migration are what the generator renders now, and the MPQ's file is the DBC;
  * the server overlay's display rows equal the client's, the template rows match the sheet (type 5, display, name, size),
    and the template's column list is the table's;
  * every wrong sheet is refused (id at or below the stock maximum, a template on an unknown display, an entry outside
    the object block, a doubled id, a clash with a different stock row);
  * single-rule mutants of the generator's source must each fail the build check.
Needs smpq and the server's extracted stock DBCs (azerothcore-wotlk/build/server/data/dbc).
"""
import csv
import re
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_world_objects as gen  # noqa: E402
from dbc_store import schema  # noqa: E402

PATCH = gen.ROOT / "client-patch/patch-4.MPQ"
TMP = tempfile.TemporaryDirectory(prefix="world_objects_")


def parse_dbc(raw):
    """{id: (record bytes, model name, six floats)} of a GameObjectDisplayInfo.dbc (19 fields of 4 bytes)."""
    magic, count, fields, size, strings = struct.unpack_from("<4s4I", raw)
    assert magic == b"WDBC" and fields == 19 and size == 76 and len(raw) == 20 + count * size + strings
    block, rows = raw[20 + count * size:], {}
    for n in range(count):
        record = raw[20 + n * size:20 + (n + 1) * size]
        offset, = struct.unpack_from("<I", record, 4)
        rows[struct.unpack_from("<I", record)[0]] = (record, block[offset:block.index(0, offset)].decode(),
                                                     struct.unpack_from("<6f", record, 48))
    assert len(rows) == count, "duplicate ids"
    return rows


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sheet(name):
    return read(gen.MODULE / "data/d3" / name)


def stock():
    return parse_dbc((gen.STOCK_DIR / "GameObjectDisplayInfo.dbc").read_bytes())


def from_mpq():
    out = Path(TMP.name) / "mpq"
    out.mkdir(exist_ok=True)
    subprocess.run(["smpq", "--extract", str(PATCH), r"DBFilesClient\GameObjectDisplayInfo.dbc"], cwd=out, check=True, capture_output=True)
    return (out / "DBFilesClient/GameObjectDisplayInfo.dbc").read_bytes()


def check_build(g, display_source=None, object_source=None):
    """Everything one render of generator module `g` must satisfy; raises on a defect."""
    display_source = display_source or g.DISPLAYS
    outputs, sql = g.generate(g.STOCK_DIR, display_source, object_source or g.OBJECTS)
    new = parse_dbc(outputs["GameObjectDisplayInfo.dbc"])
    check_rows(new, stock(), read(display_source))
    check_sql(sql, new, read(display_source), read(object_source or g.OBJECTS))


def check_rows(new, old, displays):
    for key, row in old.items():
        assert new.get(key, (None,))[0] == row[0], f"stock row {key} changed or is gone"
    assert set(new) - set(old) == {int(r["display_id"]) for r in displays}, "the new ids are exactly the sheet's"
    for r in displays:
        _, model, box = new[int(r["display_id"])]
        assert model == r["model_path"], "model path as the sheet writes it"
        assert list(box) == [float(r[f]) for f in gen.BOX], "size box as the sheet writes it, column by column"
        assert int(r["display_id"]) > 9624 and int(r["display_id"]) not in old, "above the stock maximum"


def check_sql(sql, new, display_rows=None, object_rows=None):
    names = [c[0] for c in schema(gen.ROOT, "gameobjectdisplayinfo_dbc")]
    for r in display_rows or sheet("world_object_displays.csv"):
        model = r["model_path"].replace("\\", "\\\\")  # SQL doubles the backslash
        row = re.search(r"^\(%s,'%s',(.*)\)[;,]$" % (r["display_id"], re.escape(model)), sql, re.M)
        assert row, "the server overlay holds the display row"
        cells = row.group(1).split(",")
        assert len(cells) == len(names) - 2, "one cell per column"
        assert [float(c) for c in cells[10:16]] == list(new[int(r["display_id"])][2]), "overlay box equals the client's"
    assert [c[0] for c in schema(gen.ROOT, "gameobject_template")] == gen.TEMPLATE_COLUMNS, "the table's column list"
    for r in object_rows or sheet("world_objects.csv"):
        row = re.search(r"^\(%s,(\d+),(\d+),'([^']*)','','','',([\d.]+),(?:0,){24}'','',12340\)" % r["entry"], sql, re.M)
        assert row, f"template {r['entry']} row (type, display, name, size, 24 zero Data cells)"
        assert (int(row.group(1)), int(row.group(2)), row.group(3), float(row.group(4))) == (
            5, int(r["display_id"]), r["name"], float(r["size"])), "template matches the sheet"
        assert int(r["display_id"]) in new, "the template's display exists in the client table"


def mutant(*replacements):
    source = (HERE / "generate/world/generate_world_objects.py").read_text(encoding="utf-8")
    for old, new in replacements:
        assert source.count(old) == 1, f"mutant anchor not unique: {old!r}"
        source = source.replace(old, new)
    module = types.ModuleType("generate_world_objects_mutant")
    module.__file__ = str(HERE / "generate/world/generate_world_objects.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


class Packed(unittest.TestCase):
    def test_mpq_holds_stock_and_ours(self):
        packed = parse_dbc(from_mpq())
        check_rows(packed, stock(), sheet("world_object_displays.csv"))

    def test_committed_files_are_the_render(self):
        outputs, sql = gen.generate(gen.STOCK_DIR)
        self.assertEqual((gen.CLIENT_DIR / "GameObjectDisplayInfo.dbc").read_bytes(), outputs["GameObjectDisplayInfo.dbc"])
        self.assertEqual(gen.MIGRATION.read_text(encoding="utf-8"), sql)
        self.assertEqual(from_mpq(), outputs["GameObjectDisplayInfo.dbc"])

    def test_render_satisfies_every_check(self):
        check_build(gen)


def write_sheets(displays, objects):
    d, o = Path(TMP.name) / "d.csv", Path(TMP.name) / "o.csv"
    for path, rows, head in ((d, displays, "display_id,model_path,name,min_x,min_y,min_z,max_x,max_y,max_z,notes"),
                             (o, objects, "entry,display_id,name,size,notes")):
        path.write_text(head + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return d, o


GAP = next(i for i in range(1, 9625) if i not in stock())  # an id at or below the stock maximum that stock leaves free
GOOD_D, GOOD_O = "9700,a.mdx,A,0,0,0,0,0,0,", "910090,9700,A,1,"


class Refused(unittest.TestCase):
    def refuses(self, displays, objects, text, g=gen):
        d, o = write_sheets(displays, objects)
        with self.assertRaisesRegex(g.ObjectError, text):
            g.generate(g.STOCK_DIR, d, o)

    def test_good_sheets_pass(self):
        gen.generate(gen.STOCK_DIR, *write_sheets([GOOD_D], [GOOD_O]))

    def test_distinct_box_cells_land_in_their_columns(self):
        check_build(gen, *write_sheets(["9700,a.mdx,A,1,2,3,4,5,6,", "9701,b.mdx,B,-1,-2,-3,7,8,9,"], [GOOD_O]))

    def test_display_below_the_stock_maximum(self):
        self.refuses([f"{GAP},a.mdx,A,0,0,0,0,0,0,"], [], "stock maximum")

    def test_display_at_the_stock_maximum(self):
        self.refuses(["9624,a.mdx,A,0,0,0,0,0,0,"], [], "stock maximum")

    def test_doubled_display(self):
        self.refuses([GOOD_D, GOOD_D], [GOOD_O], "twice")

    def test_unknown_display(self):
        self.refuses([GOOD_D], ["910090,9701,A,1,"], "holds")

    def test_template_on_a_stock_display(self):
        check_build(gen, *write_sheets([GOOD_D], [GOOD_O, "910091,264,Red Aura,1,"]))

    def test_template_on_a_gap_in_the_stock_table(self):
        self.refuses([GOOD_D], [f"910090,{GAP},A,1,"], "holds")

    def test_entry_outside_block(self):
        self.refuses([GOOD_D], ["910100,9700,A,1,"], "outside")

    def test_doubled_entry(self):
        self.refuses([GOOD_D], [GOOD_O, GOOD_O], "twice")

    def test_clash_with_a_different_stock_row(self):
        with self.assertRaisesRegex(gen.ObjectError, "refusing"):
            gen.build_dbc([{"display_id": 9491, "model_path": "x.mdx", **{f: 0.0 for f in gen.BOX}}], gen.STOCK_DIR)

    def test_bad_number(self):
        self.refuses(["9700,a.mdx,A,x,0,0,0,0,0,"], [GOOD_O], "not a number")


class Mutants(unittest.TestCase):
    def killed(self, *replacements):
        distinct = write_sheets(["9700,a.mdx,A,1,2,3,4,5,6,"], [GOOD_O, "910091,264,Stock,1,"])
        mod = mutant(*replacements)  # built before the try: a stale anchor must fail the test, not count as a kill
        for sources in ((), distinct):  # the real sheets, then a sheet with six different box cells
            try:
                check_build(mod, *sources)
            except Exception:
                return
        self.fail("the mutant survived every check")

    def test_wrong_object_type(self):
        self.killed(("GENERIC = 5", "GENERIC = 4"))

    def test_box_columns_swapped(self):
        self.killed(('"GeoBoxMinX", "GeoBoxMinY", "GeoBoxMinZ", "GeoBoxMaxX"', '"GeoBoxMaxX", "GeoBoxMinY", "GeoBoxMinZ", "GeoBoxMinX"'))

    def test_model_path_dropped(self):
        self.killed(('ModelName=row["model_path"]', 'ModelName=row["name"]'))

    def test_template_wears_the_wrong_display(self):
        self.killed(('"displayId": r["display_id"]', '"displayId": r["display_id"] + 1'))

    def test_template_size_ignored(self):
        self.killed(('"size": r["size"]', '"size": 2'))

    def test_template_on_a_stock_display_refused(self):
        self.killed(("| set(stock_ids)", ""))

    def test_stock_row_lost(self):
        anchor = 'return Store(stock.read_bytes(), schema(ROOT, "gameobjectdisplayinfo_dbc"))'
        self.killed((anchor, anchor.replace("return ", "store = ") + "; store.rows.pop(min(store.rows)); return store"))

    def test_stock_guard_removed(self):
        mod = mutant(('if row["display_id"] <= STOCK_MAX_DISPLAY:', "if False:"))
        with self.assertRaises(AssertionError):
            Refused().refuses([f"{GAP},a.mdx,A,0,0,0,0,0,0,"], [], "stock maximum", g=mod)

    def test_object_block_guard_removed(self):
        mod = mutant(("if row[\"entry\"] not in OBJECT_RANGE:", "if False:"))
        with self.assertRaises(AssertionError):
            Refused().refuses([GOOD_D], ["910100,9700,A,1,"], "outside", g=mod)


class ZoneWalls(unittest.TestCase):
    """diablocraft-cq7p2 (the designer's dev tweak, 2026-10-12): two decorations for his hand-placed zone walls in the 751 copy.
    diablocraft-ep332 (the designer, card q-1013-20): they wear stock gameobject 194935 'Blocked Passage''s model, the large one
    keeping its step up in size, so the placed walls swap in place with no new GUIDs."""

    def blocked_passage_display(self):
        # The stock template as the core's base SQL writes it (no core update touches 194935): (entry,type,displayId,name,...
        base = (gen.ROOT / "azerothcore-wotlk/data/sql/base/db_world/gameobject_template.sql").read_text(encoding="utf-8")
        row = re.search(r"^\(194935,(\d+),(\d+),'([^']*)'", base, re.M)
        self.assertIsNotNone(row)
        self.assertEqual(row.group(3), "Blocked Passage")
        return int(row.group(2))

    def test_two_templates_wear_the_blocked_passage_model(self):
        display = self.blocked_passage_display()
        rows = {r["entry"]: r for r in sheet("world_objects.csv")}
        self.assertEqual([(int(rows[e]["display_id"]), rows[e]["name"], float(rows[e]["size"])) for e in ("910097", "910098")],
                         [(display, "Zone Wall", 2.0), (display, "Zone Wall (large)", 3.0)])
        self.assertEqual(stock()[display][1].lower(), "world\\goober\\g_cavein.mdx")
        self.assertNotIn(display, [int(r["display_id"]) for r in sheet("world_object_displays.csv")])   # stock: no DBC row of ours

    def test_the_rows_ship_in_a_new_migration_and_world_0043_stays_frozen(self):
        display = self.blocked_passage_display()
        self.assertEqual(gen.MIGRATION.name, "world_0052_world_objects.sql")
        applied = (gen.MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn(gen.MIGRATION.name, applied)
        old = (gen.MIGRATION.parent / "world_0043_world_objects.sql").read_text(encoding="utf-8")
        new = gen.MIGRATION.read_text(encoding="utf-8")
        # world_0043 is applied on dev: it keeps the ice wall it was applied with.
        self.assertIn("(910097,5,9214,'Zone Wall','','','',2,", old)
        for row in (f"(910097,5,{display},'Zone Wall','','','',2,", f"(910098,5,{display},'Zone Wall (large)','','','',3,"):
            self.assertIn(row, new)
        self.assertEqual(new, gen.generate(gen.STOCK_DIR)[1])   # the file is the generator's render of the sheet
        names = sorted(p.name for p in gen.MIGRATION.parent.glob("*.sql"))
        self.assertGreater(names.index(gen.MIGRATION.name), names.index("world_0043_world_objects.sql"))



if __name__ == "__main__":
    unittest.main()
