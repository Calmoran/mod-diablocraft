"""Integration checks in a disposable MySQL database; never mutates acore_world."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import uuid

scripts = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("area_copies", scripts / "generate/world/generate_area_copies.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
mysql, defaults = fixture_db.mysql_and_defaults()
name = "dc_area_test_" + uuid.uuid4().hex[:12]
admin = module.Database(mysql, defaults, "acore_world")
admin.query(f"CREATE DATABASE {name}")
db = module.Database(mysql, defaults, name)
try:
    tables = set(module.BASE.values()) | {t for v in module.SIMPLE.values() for t in v}
    tables |= set("dc_world_areas pool_creature pool_gameobject game_event_creature game_event_gameobject spawn_group smart_scripts conditions game_event_model_equip game_event_npc_vendor game_event_npcflag creature_formations linked_respawn".split())
    for table in sorted(tables):
        db.query(f"CREATE TABLE {table} LIKE acore_world.{table}")
    for table in ('creature_template','creature_classlevelstats','dc_tier_phase','dc_difficulty_tiers','dc_party_scaling'):
        db.query(f"CREATE TABLE {table} LIKE acore_world.{table}")
        db.query(f"INSERT INTO {table} SELECT * FROM acore_world.{table}" + (" WHERE entry=448" if table=='creature_template' else ''))
    db.query((scripts.parent / "data/sql/db-world/updates/difficulty_0006_area_sources.sql").read_text())
    db.query("INSERT INTO dc_world_areas VALUES (1,876,'all','open','fixture')")
    for kind, table in module.BASE.items():
        sample = admin.rows(table, "1", "ORDER BY guid LIMIT 1")[0]
        for guid in ((100,101,102) if kind == 'c' else (100,102)):
            row = dict(sample, guid=guid, map=1, phaseMask=1, position_x=16000,
                       position_y=16000, position_z=20, orientation=0)
            row["id"] = 448 if kind == 'c' else 101766
            db.query(module.insert(table, row))
            if guid != 102:  # Unlisted stock spawn must never be copied/deleted.
                db.query(f"INSERT INTO dc_area_source VALUES(1,876,'{kind}',{guid},{row['id']},1,16000,16000,20,0)")
    db.query("INSERT INTO creature_formations VALUES(100,101,2,0,0,0,0)")
    db.query("INSERT INTO linked_respawn VALUES(100,101,0)")
    sql, sources, copies = module.generate(db, 1, 876)
    assert (sources, copies) == (3,27)
    collision = dict(db.rows('creature', 'guid=102')[0], guid=103)
    db.query(module.insert('creature', collision))
    result = subprocess.run(db.args, input=sql, text=True, capture_output=True)
    assert result.returncode and 'Check constraint' in result.stderr
    assert db.query("SELECT COUNT(*) FROM dc_area_spawn") == ['0']
    assert db.query("SELECT COUNT(*) FROM creature WHERE guid=103") == ['1']
    db.query("DELETE FROM creature WHERE guid=103")
    db.query(sql)
    again, _, _ = module.generate(db, 1, 876)
    assert again == sql, "Rerun must preserve file content and GUID ownership"
    db.query(again)
    assert db.query("SELECT COUNT(*) FROM creature") == ['21']
    assert db.query("SELECT COUNT(*) FROM gameobject") == ['11']
    assert db.query("SELECT COUNT(*) FROM creature_formations") == ['10']
    assert db.query("SELECT COUNT(*) FROM linked_respawn") == ['10']
    assert db.query("SELECT COUNT(*) FROM dc_area_spawn WHERE source_guid=102") == ['0']
    assert db.query("SELECT COUNT(*) FROM creature WHERE guid=102 AND phaseMask=1") == ['1']
    try:
        module.generate(db, 1, 876, 10**18)  # past the 64-bit Life pool (2**64); 32-bit Life is allowed since diablocraft-12in
        raise AssertionError("Life overflow accepted")
    except ValueError as error:
        assert 'Life overflow' in str(error)
    db.query("INSERT INTO pool_creature VALUES(100,123,0,'fixture')")
    try:
        module.generate(db, 1, 876)
        raise AssertionError("Pool silently skipped")
    except ValueError as error:
        assert 'pool_creature' in str(error) and '100' in str(error)
    db.query("DELETE FROM pool_creature")
    db.query("UPDATE creature_formations SET memberGUID=102 WHERE leaderGUID=100")
    try:
        module.generate(db, 1, 876)
        raise AssertionError("Cross-area relationship accepted")
    except ValueError as error:
        assert 'Cross-area' in str(error)
    db.query("UPDATE creature_formations SET memberGUID=101 WHERE leaderGUID=100")
    db.query("UPDATE creature SET position_x=16001 WHERE guid=100")
    try:
        module.generate(db, 1, 876)
        raise AssertionError("Stale source accepted")
    except ValueError as error:
        assert 'changed since area scan' in str(error)
    result = subprocess.run(db.args, input=sql, text=True, capture_output=True)
    assert result.returncode and 'Check constraint' in result.stderr
    assert db.query("SELECT COUNT(*) FROM dc_area_spawn") == ['27'], "Failed guard must precede deletion"
    db.query("UPDATE creature SET position_x=16000 WHERE guid=100")
    db.query("DELETE FROM creature_formations WHERE leaderGUID=100")
    db.query("DELETE FROM linked_respawn WHERE guid=100")
    db.query("DELETE FROM dc_area_source WHERE kind='c' AND source_guid=101")
    reduced, sources, copies = module.generate(db, 1, 876)
    assert (sources,copies) == (2,18)
    db.query(reduced)
    assert db.query("SELECT COUNT(*) FROM creature") == ['12']
    assert db.query("SELECT COUNT(*) FROM creature WHERE guid=101") == ['1']
    assert db.query("SELECT COUNT(*) FROM creature_formations") == ['0']
    assert db.query("SELECT COUNT(*) FROM linked_respawn") == ['0']
    try:
        module.generate(db, *module.hub_key())
        raise AssertionError("Tier copies of the hub accepted")
    except ValueError as error:
        assert 'one shared phase' in str(error)
    db.query("UPDATE dc_world_areas SET status='closed'")
    try:
        module.generate(db, 1, 876)
        raise AssertionError("Closed area accepted")
    except ValueError as error:
        assert 'not open' in str(error)
    print("PASS: area-only copies, stable rerun, links, removed-source cleanup, unowned preservation, GUID collision, Life ceiling (2^64), closed/pool/cross-area/stale rejection, SQL rollback")
finally:
    admin.query(f"DROP DATABASE {name}")
