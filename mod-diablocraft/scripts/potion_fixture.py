"""Install/remove a temporary potion-slot base row for the client acceptance test.

Reuses stock item 118 (already in the client's Item.dbc) without changing its
item_template. Never adds rows to shipped CSV/generated SQL. Refuses collisions
and refuses removal while a character still has this test potion equipped.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess

ENTRY = 118
MARKER = "codex_potion_acceptance_fixture"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "install", "remove"))
    parser.add_argument("--mysql", default=r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe")
    parser.add_argument("--defaults-file")
    parser.add_argument("--worldserver-conf", type=Path, default=Path(__file__).resolve().parents[2]
                        / "azerothcore-wotlk/build/server/configs/worldserver.conf")
    args = parser.parse_args()

    def query(database, sql):
        env = dict(os.environ)
        if args.defaults_file:
            connection = ["--defaults-file=" + args.defaults_file]
        else:
            # Read credentials without printing them or putting a password in
            # the process command line. Use the same databases as this server.
            setting = "WorldDatabaseInfo" if database == "acore_world" else "CharacterDatabaseInfo"
            config = args.worldserver_conf.read_text(encoding="utf-8-sig")
            match = re.search(r'^\s*' + setting + r'\s*=\s*"([^"\r\n]+)"', config, re.M)
            if not match:
                raise SystemExit("Database connection setting is missing from worldserver.conf.")
            host, port, user, password, database = match[1].split(";", 4)
            env["MYSQL_PWD"] = password
            connection = ["--no-defaults", "--host=" + host, "--port=" + port, "--user=" + user]
        result = subprocess.run(
            [args.mysql, *connection, "--batch", "--skip-column-names", database],
            input=sql, encoding="utf-8", capture_output=True, env=env)
        if result.returncode:
            raise SystemExit(result.stderr.strip())
        return result.stdout.strip()

    name = query("acore_world", f"SELECT name FROM item_template WHERE entry={ENTRY};")
    if not name:
        raise SystemExit("Stock fixture template 118 is missing; no changes made.")
    existing = query("acore_world", f"SELECT d3_id FROM dc_base_item WHERE entry={ENTRY};")
    if existing and existing != MARKER:
        raise SystemExit("Entry 118 already has a non-fixture base row; no changes made.")
    if args.action == "check":
        print(f"Fixture template {ENTRY}: {name}; base fixture {'installed' if existing else 'absent'}")
        return
    if args.action == "install":
        if not existing:
            # Clone only a row's schema/defaults. Its gameplay data is overwritten
            # below and the fixture is slot=potion, outside ordinary gear pools.
            query("acore_world", f"""
CREATE TEMPORARY TABLE dc_potion_test_row LIKE dc_base_item;
INSERT INTO dc_potion_test_row SELECT * FROM dc_base_item ORDER BY entry LIMIT 1;
UPDATE dc_potion_test_row SET entry={ENTRY}, d3_id='{MARKER}',
 d3_name='Potion slot test fixture', slot='potion', type='Potion', rarity='',
 usable_by='', item_level=NULL, level_req=NULL, weapon_min=NULL, weapon_max=NULL,
 weapon_aps=NULL, preset_affixes='', set_name='', source_file='{MARKER}',
 pool_version='no', designated_class='';
INSERT INTO dc_base_item SELECT * FROM dc_potion_test_row;
""")
            if query("acore_world", f"SELECT d3_id FROM dc_base_item WHERE entry={ENTRY};") != MARKER:
                raise SystemExit("Fixture was not installed.")
        print("Temporary fixture installed. GM: .additem 118 1")
        print("No legendary power or alternate shell: key 7 remains Health Potion.")
    else:
        count = query("acore_characters", f"SELECT COUNT(*) FROM dc_character_potion WHERE item_entry={ENTRY};")
        if count != "0":
            raise SystemExit("Unequip the fixture on every character before removing its base row.")
        query("acore_world", f"DELETE FROM dc_base_item WHERE entry={ENTRY} AND d3_id='{MARKER}';")
        print("Temporary base row removed; stock item_template was never changed.")


if __name__ == "__main__":
    main()
