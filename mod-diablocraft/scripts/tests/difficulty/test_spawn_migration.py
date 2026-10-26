"""Exercise full-world copy retirement and rerun safety against an isolated MySQL fixture DB.
Usage: python test_spawn_migration.py MYSQL_EXE CLIENT_DEFAULTS_FILE
"""
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
mysql, defaults = fixture_db.mysql_and_defaults()
database = "dc_tier_test_" + uuid.uuid4().hex[:12]
root = Path(__file__).resolve().parents[3]
def run(sql, db=None):
    args = [mysql, "--defaults-file="+defaults, "--no-login-paths", "--batch", "--skip-column-names"]
    if db: args += [db]
    return subprocess.check_output(args, input=sql, text=True).strip()

tables = "creature gameobject creature_addon creature_movement_override creature_multispawn creature_sparring vehicle_accessory gameobject_addon game_event_creature game_event_gameobject game_event_model_equip game_event_npc_vendor game_event_npcflag creature_formations pool_template pool_creature pool_gameobject pool_pool spawn_group_template spawn_group linked_respawn smart_scripts conditions".split()
run("CREATE DATABASE `"+database+"`")
try:
    for table in tables:
        run(f"CREATE TABLE `{table}` LIKE acore_world.`{table}`",database)
    cleanup=(root/"data/sql/db-world/updates/difficulty_0005_remove_full_world_copies.sql").read_text()
    run(cleanup,database)  # Also works on a fresh install with no old copies.
    for kind, table in (("c","creature"),("g","gameobject")):
        columns=run(f"SELECT column_name FROM information_schema.columns WHERE table_schema='{database}' AND table_name='{table}' ORDER BY ordinal_position").splitlines()
        for guid in (900000,900001,900002):
            select=','.join(str(guid) if col=='guid' else 's.`'+col+'`' for col in columns)
            run(f"INSERT INTO `{table}` SELECT {select} FROM acore_world.`{table}` s ORDER BY s.guid LIMIT 1",database)
        run(f"INSERT INTO dc_tier_spawn VALUES ('{kind}',900000,2,900001)",database)
    run("""INSERT INTO dc_tier_pool VALUES (10,2,20),(11,2,21);
INSERT INTO pool_template VALUES (10,1,'stock'),(11,1,'stock parent'),(20,1,'copy'),(21,1,'copy parent');
INSERT INTO pool_creature VALUES (900000,10,0,'stock'),(900001,20,0,'copy');
INSERT INTO pool_gameobject VALUES (900000,10,0,'stock'),(900001,20,0,'copy');
INSERT INTO pool_pool VALUES (10,11,0,'stock'),(20,21,0,'copy');
INSERT INTO creature_formations VALUES (900000,900002,2,0,0,0,0),(900001,900001,2,0,0,0,0);
INSERT INTO linked_respawn VALUES (900000,900002,0),(900001,900001,0);
INSERT INTO game_event_creature VALUES (1,900000),(1,900001);
INSERT INTO dc_tier_spawn_group VALUES (10,2,20);
INSERT INTO spawn_group_template VALUES (10,'stock',0),(20,'copy',0);
INSERT INTO spawn_group VALUES (10,0,900000),(20,0,900001),(20,1,900001);""",database)
    for _ in range(2):
        run(cleanup,database)
        for table in ("creature","gameobject"):
            assert run(f"SELECT GROUP_CONCAT(guid ORDER BY guid) FROM {table}",database)=='900000,900002'
        for table in ("dc_tier_spawn","dc_tier_pool","dc_tier_spawn_group"):
            assert run(f"SELECT COUNT(*) FROM {table}",database)=='0'
        for table in ("pool_pool","creature_formations","linked_respawn","game_event_creature","spawn_group"):
            assert run(f"SELECT COUNT(*) FROM {table}",database)=='1'
        assert run("SELECT GROUP_CONCAT(entry ORDER BY entry) FROM pool_template",database)=='10,11'
    print("Retirement migration preserves stock/GM placements and removes owned copies and relationships; fresh install and rerun passed")
finally:
    run("DROP DATABASE `"+database+"`")
