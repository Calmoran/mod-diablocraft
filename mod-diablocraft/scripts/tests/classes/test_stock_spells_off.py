#!/usr/bin/env python3
"""Stock spells switched off (diablocraft-hcwjv, diablocraft-r0d0h; generate_stock_spells_off.py).

The committed migration is the sheet; its flags are the core's own DisableMgr.h bits; every trap gameobject that casts a listed
spell spawns only on the listed map (read from the core's base world SQL, so a spawn elsewhere would keep the buff); and the
migration loads on the core's `disables` table and a re-run leaves the same rows. The Shaman's rows (Shaman 1a: every stock spell of
its class skill lines, off for players on every map, Ghost Wolf kept) are re-derived from the client DBCs and must equal the sheet's,
none is one of our records, every one is a spell the core knows, and a Shaman monster's casts stay (no creature flag). Run
standalone; the load needs the fixture mysqld and is skipped without it.
"""
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db  # noqa: E402
import generate_stock_spells_off as G  # noqa: E402

MODULE = G.MODULE
CORE = MODULE.parent / "azerothcore-wotlk"
COMMON = Path(subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=MODULE,
                             capture_output=True, text=True, check=True).stdout.strip()).parent
BASE = COMMON / "azerothcore-wotlk/data/sql/base/db_world"


def test_the_migration_is_the_sheet():
    sql = G.render(G.read_sheet())
    assert (MODULE / "data/sql/db-world/updates" / G.NAME).read_text() == (MODULE / "data/generated/stock_spells_off.sql").read_text() == sql
    assert [r["spell"] for r in G.read_sheet()][0] == "30939"
    assert (MODULE / "data/sql/db-world/updates/world_0041_stock_spells_off.sql").read_text().count("INSERT INTO") == 1, "0041 is applied and stays"


def test_the_flags_are_the_cores():
    header = (CORE / "src/server/game/Conditions/DisableMgr.h").read_text()
    bit = {name: int(value, 16) for name, value in re.findall(r"(SPELL_DISABLE_\w+)\s*=\s*(0x[0-9A-Fa-f]+)", header)}
    assert G.FLAGS == bit["SPELL_DISABLE_PLAYER"] | bit["SPELL_DISABLE_CREATURE"] | bit["SPELL_DISABLE_MAP"]
    assert G.FLAGS_EVERYWHERE == bit["SPELL_DISABLE_PLAYER"], "a Shaman monster still casts its stock spells"
    assert re.search(r"DISABLE_TYPE_SPELL\s*=\s*0\b", header) and G.SOURCE_SPELL == 0


def test_every_trap_of_a_listed_spell_is_on_its_map():
    templates = (BASE / "gameobject_template.sql").read_text(encoding="utf-8", errors="replace")
    spawns = (BASE / "gameobject.sql").read_text(encoding="utf-8", errors="replace")
    for row in [r for r in G.read_sheet() if r["map_id"]]:
        # gameobject_template: (entry, type, displayId, name, IconName, castBarCaption, unk1, size, Data0, Data1, Data2, Data3, ...);
        # a trap (type 6) casts Data3.
        traps = [m[0] for m in re.findall(r"^\((\d+),6,\d+,'(?:[^']|'')*','[^']*','[^']*','[^']*',[\d.]+,(-?\d+),(-?\d+),(-?\d+),(\d+),",
                                           templates, re.M) if m[4] == row["spell"]]
        assert traps, f"no trap casts spell {row['spell']}"
        maps = set(re.findall(r"^\(\d+,(?:%s),(\d+)," % "|".join(traps), spawns, re.M))
        assert maps == {row["map_id"]}, (row["spell"], traps, maps)


def shaman_rows():
    return [r for r in G.read_sheet() if r["source"].startswith(G.SHAMAN_SOURCE.split("%")[0])]


def test_the_shaman_rows_are_the_stock_class_spells_and_nothing_else():
    if not (G.DBC / "SkillLineAbility.dbc").is_file():
        print("SKIP no extracted client DBCs")
        return
    derived = G.shaman_rows()
    assert shaman_rows() == derived, "the sheet's Shaman rows drifted from the DBCs: rerun the generator with --shaman"
    ids = {int(r["spell"]) for r in derived}
    assert len(derived) == len(ids) > 500
    assert not ids & set(G.SHAMAN_KEPT), "Ghost Wolf stays"
    assert {403, 331, 2825, 32182, 324} <= ids, "Lightning Bolt, Healing Wave, Bloodlust, Heroism and Lightning Shield are off"
    assert all(r["map_id"] == "" for r in derived)
    assert not [r for r in G.read_sheet() if r["spell"] in map(str, G.SHAMAN_KEPT)]
    assert min(ids) > 0 and max(ids) < 81000, "none of ours (the module's records start at 81000)"
    assert len({r["spell"] for r in G.read_sheet()}) == len(G.read_sheet()), "a spell is listed once"


def test_the_shaman_rows_are_off_for_players_only_and_everywhere():
    sql = G.render(G.read_sheet())
    assert ", 1, '', '', 'Torment: Lightning Bolt off for players (stock_spells_off.csv)')" in sql
    assert "(0, 30939, 19, '542'" in sql
    assert sql.count(", 1, '', '',") == len(shaman_rows())


def test_the_migration_loads_and_reruns():
    mysql = [fixture_db.mysql_exe(), "--defaults-file=" + str(fixture_db.defaults_file()), "--no-login-paths"]
    if subprocess.run(mysql + ["-e", "SELECT 1"], capture_output=True).returncode != 0:
        print("SKIP the fixture mysqld is down (fixture_mysql.sh start)")
        return
    db = "stock_spells_off_" + uuid.uuid4().hex[:10]
    run = lambda *a, stdin=None: subprocess.run(mysql + list(a), input=stdin, capture_output=True, text=True)
    assert run("-e", f"CREATE DATABASE {db}").returncode == 0
    try:
        assert run(db, stdin=(BASE / "disables.sql").read_text()).returncode == 0
        assert run(db, "-e", "INSERT INTO disables VALUES (0, 30939, 1, '', '', 'old'), (0, 1, 1, '', '', 'someone else')").returncode == 0
        sql = (MODULE / "data/sql/db-world/updates" / G.NAME).read_text()
        for _ in range(2):
            done = run(db, stdin=sql)
            assert done.returncode == 0, done.stderr
            got = run(db, "-N", "-B", "-e", "SELECT sourceType, entry, flags, params_0 FROM disables WHERE sourceType = 0 AND entry IN (1, 30939) ORDER BY entry").stdout.split("\n")
            assert got[:2] == ["0\t1\t1\t", "0\t30939\t19\t542"], got
            shaman = run(db, "-N", "-B", "-e", "SELECT flags, params_0 FROM disables WHERE sourceType = 0 AND entry = 403").stdout.split("\n")
            assert shaman[0] == "1\t", shaman
            count = run(db, "-N", "-B", "-e", "SELECT COUNT(*) FROM disables WHERE comment LIKE 'Torment: %'").stdout.strip()
            assert count == str(len(G.read_sheet())), count
    finally:
        run("-e", f"DROP DATABASE IF EXISTS {db}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
