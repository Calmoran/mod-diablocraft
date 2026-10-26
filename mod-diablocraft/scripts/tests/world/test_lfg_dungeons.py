"""diablocraft-v1sw4: the Dungeon Finder's rows (LFGDungeons, client and server from one sheet).

generate_lfg_dungeons.py neutralises every stock row but the zone rows and adds a visible random row and a hidden key
row per activity. This pins: every stock id survives with only Group_Id and the level range changed, and the zone rows
(type 4, read by the faction change's taxi mask, CharacterHandler.cpp:2313-2324) not at all; at every player level
the stock rows reach neither the dropdown nor the Specific list, by the core's random-list rule (LFGMgr.cpp:2952-2953) and
the client's (LFDFrame.lua isRandomDungeonDisplayable, LFDList_DefaultFilterFunction); the dropdown at level 70 is
exactly the sheet's visible rows; the hidden rows are type 1, Group_Id 0, on the hub's map with an entrance row at the
hub spawn; no non-random row shares a visible row's group (a stock expansion finds nothing); the server overlay
carries the same rows as the client file; a taken or doubled id is refused; the committed outputs are the render;
and each rule fails the check when one line of the generator is broken.

Not covered: what a real client does with the file, or whether the core joins a hidden row (the probe's test sheet,
docs/test-diablocraft-v1sw4.md, is that walk).
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_lfg_dungeons as gen  # noqa: E402
from dbc_store import Store, schema  # noqa: E402

COLUMNS = schema(gen.ROOT, "lfgdungeons_dbc")
NAMES = [c[0] for c in COLUMNS]
LEVELS = range(1, 81)  # every level a character can have: StartPlayerLevel 1 to MaxPlayerLevel 80 (dev conf)
EXPANSION = 2


def stock():
    return Store(gen.stock_path(gen.STOCK_DIR).read_bytes(), COLUMNS)


def rows_of(data):
    store = Store(data, COLUMNS)
    return {k: store.decode(k) for k in store.rows}


def server_rows(sql):
    """{ID: {column: raw literal}} from the lfgdungeons_dbc INSERT."""
    body = sql.split("INSERT INTO `lfgdungeons_dbc`", 1)[1].split(" VALUES\n", 1)[1].split(";\nDELETE", 1)[0]
    out = {}
    for line in body.split("\n"):
        cells = re.findall(r"'(?:[^'\\]|''|\\.)*'|[^,()]+", line.strip().rstrip(","))
        assert len(cells) == len(NAMES), line
        out[int(cells[0])] = dict(zip(NAMES, cells))
    return out


def random_list(rows, level):
    """The core's dropdown source for one player (GetRandomAndSeasonalDungeons, no season active)."""
    return {k for k, r in rows.items() if r["TypeID"] == 6 and r["ExpansionLevel"] <= EXPANSION
            and r["MinLevel"] <= level <= r["MaxLevel"]}


def specific_list(rows, level):
    """The client's Specific list filter, without the lock clause (it only adds rows that pass the rest)."""
    return {k for k, r in rows.items() if r["TypeID"] != 6 and r["Group_Id"] != 0
            and EXPANSION >= r["ExpansionLevel"] and r["MinLevel"] <= level <= r["MaxLevel"]}


def check_all(mod, test):
    """Every rule, against `mod` (the real generator or a mutant of it)."""
    data, sql, lua = mod.generate(gen.STOCK_DIR)
    rows, raw = rows_of(data), stock()
    sheet = gen.read_sheet()
    hub_map, spawn = gen.hub_spawn()
    visible = {a["visible"] for a in sheet}
    hidden = {a["hidden"] for a in sheet}
    # every stock id survives; only the group and the level range change
    test.assertEqual(set(rows), set(raw.rows) | visible | hidden)
    for key in raw.rows:
        before, after = raw.decode(key), rows[key]
        test.assertEqual({n for n in NAMES if before[n] != after[n]} - {"Group_Id", "MinLevel", "MaxLevel"}, set(), key)
        if before["TypeID"] == 4:
            test.assertEqual(before, after, key)
    test.assertEqual(sum(raw.decode(k)["TypeID"] == 4 for k in raw.rows), 59, "the stock zone rows")
    # no stock row reaches the dropdown or the Specific list at any level; the dropdown at 70 is the sheet's
    for level in LEVELS:
        test.assertEqual(random_list(rows, level) - visible, set(), level)
        test.assertEqual(specific_list(rows, level), set(), level)
    test.assertEqual(random_list(rows, 70), visible)
    # the rows of each activity
    for a in sheet:
        v, h = rows[a["visible"]], rows[a["hidden"]]
        test.assertEqual((v["TypeID"], h["TypeID"]), (6, 1))
        test.assertEqual((v["Name_Lang_enUS"], h["Name_Lang_enUS"]), (a["name"], a["name"]))
        test.assertEqual((v["MinLevel"], v["MaxLevel"], h["MinLevel"], h["MaxLevel"]), (a["min"], a["max"]) * 2)
        test.assertEqual((h["Group_Id"], h["MapID"], h["Difficulty"]), (0, hub_map, 0))
        # a stock expansion of the visible row (LFGMgr.cpp:2435) finds no dungeon
        test.assertEqual({k for k, r in rows.items() if r["TypeID"] != 6 and r["Group_Id"] == v["Group_Id"]}, set())
        test.assertNotEqual(v["Group_Id"], 0, "group 0 expands to every dungeon")
        test.assertIn("(%d,'%s',%s,0)" % (a["hidden"], a["name"], ",".join(format(c, ".9g") for c in spawn)), sql)
        test.assertIn("[%d] = %d," % (a["visible"], a["hidden"]), lua)
    test.assertIn("DELETE FROM `lfg_dungeon_template` WHERE `dungeonId` IN (%s);"
                  % ",".join(str(a["hidden"]) for a in sheet), sql)
    # the server overlay carries every row of the client file, field for field
    over = server_rows(sql)
    test.assertEqual(set(over), set(rows))
    test.assertIn("DELETE FROM `lfgdungeons_dbc` WHERE `ID` IN (%s);" % ",".join(map(str, over)), sql)
    for key, r in rows.items():
        for n in NAMES:
            want = "'%s'" % r[n].replace("'", "''") if isinstance(r[n], str) else str(r[n])
            test.assertEqual(over[key][n], want, (key, n))
    # a taken or doubled id is refused
    header = "activity,visible_id,hidden_id,name,min_level,max_level,notes\n"
    for body in ("a,1000,202,A,70,70,\n",                         # 202 is a stock row
                 "a,1000,1100,A,70,70,\nb,1001,1100,B,70,70,\n",  # 1100 twice
                 "a,1000,1000,A,70,70,\n"):                         # one id for both rows
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "lfg_activities.csv"
            sheet.write_text(header + body, encoding="utf-8")
            with test.assertRaises(mod.LfgError, msg=body):
                mod.generate(gen.STOCK_DIR, source=sheet)


class RealBuild(unittest.TestCase):
    def test_every_rule_holds_on_the_real_sheet_and_stock(self):
        check_all(gen, self)

    def test_committed_outputs_are_what_the_generator_renders(self):
        data, sql, lua = gen.generate(gen.STOCK_DIR)
        self.assertEqual(gen.CLIENT_DBC.read_bytes(), data, "LFGDungeons.dbc is stale: rerun generate_lfg_dungeons.py")
        self.assertEqual(gen.MIGRATION.read_text(encoding="utf-8"), sql, f"{gen.MIGRATION.name} is stale")
        self.assertEqual(gen.ADDON_ROWS.read_text(encoding="utf-8"), lua, "LFGRows.lua is stale")


# One rule at a time. Each must make check_all fail.
MUTATIONS = (
    ("the zone rows are neutralised too", 'if values["TypeID"] != TYPE_ZONE:', "if True:"),
    ("stock rows keep their group", "values.update(Group_Id=0, MinLevel=0, MaxLevel=0)",
     "values.update(MinLevel=0, MaxLevel=0)"),
    ("stock rows keep their levels", "values.update(Group_Id=0, MinLevel=0, MaxLevel=0)", "values.update(Group_Id=0)"),
    ("the hidden row keeps its clone's group", "values.update(MapID=hub_map, Group_Id=0)", "values.update(MapID=hub_map)"),
    ("the hidden row keeps its clone's map", "values.update(MapID=hub_map, Group_Id=0)", "values.update(Group_Id=0)"),
    ("the visible row is not random", "VISIBLE_TEMPLATE = 261", "VISIBLE_TEMPLATE = 202"),
    ("a stock id is overwritten", "if taken:", "if False:"),
    ("an id is used twice", "if seen & set(ids) or ids[0] == ids[1]:", "if False:"),
    ("the entrance row is missing", "for a in activities)]", "for a in activities[1:])]"),
    ("the overlay misses the stock rows", '",\\n".join("(" + ",".join(sql_value(r[n]) for n in names) + ")" for r in rows)),',
     '",\\n".join("(" + ",".join(sql_value(r[n]) for n in names) + ")" for r in rows[-6:])),'),
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
            Mod.LfgError = namespace["LfgError"]
            check_all(Mod, self)
        except Exception as error:  # noqa: BLE001 - a broken generator or a failed check both count
            return error
        return None


if __name__ == "__main__":
    unittest.main(verbosity=2)
