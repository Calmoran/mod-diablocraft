"""Read-only starter/inventory snapshots for manual restart/login regression tests.

Use a private MySQL --defaults-file; credentials are never read or printed here.
Save the character in game (.save) before each snapshot, or stop the server.
"""
import argparse
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess


import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pools', action='store_true', help='Validate CSV starter candidates without a database')
    parser.add_argument('--mysql')
    parser.add_argument('--defaults-file')
    parser.add_argument('--database', default='acore_characters')
    parser.add_argument('--character')
    parser.add_argument('--server-log', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--world-database', default='acore_world')
    args = parser.parse_args()
    if args.pools:
        from generate_sql import MODULE_ROOT, class_start_rows, starter_candidates
        with (MODULE_ROOT / 'data/d3/base_items.csv').open(newline='') as stream:
            bases = list(csv.DictReader(stream))
        for profile in class_start_rows(MODULE_ROOT / 'data/d3/class_starts.csv').values():
            for kit in profile['kit']:
                if not kit['count']:
                    continue
                candidates = starter_candidates(profile, kit, bases)
                if not candidates:
                    parser.error(f"Empty starter pool: {profile['class_key']} {kit['slot']}")
                print(f"{profile['class_key']} {kit['slot']}: {len(candidates)} candidates; "
                      f"types={','.join(sorted({b['type'] for b in candidates}))}")
        return 0
    if not all((args.mysql, args.defaults_file, args.character, args.server_log, args.output)):
        parser.error('Snapshots require --mysql, --defaults-file, --character, --server-log and --output.')
    if not re.fullmatch(r'[A-Za-z0-9_]+', args.world_database):
        parser.error('Invalid world database name.')
    if not re.fullmatch(r'[A-Za-z]+', args.character):
        parser.error('Use an unadorned alphabetic character name.')
    if not re.fullmatch(r'[A-Za-z0-9_]+', args.database):
        parser.error('Invalid database name.')
    if args.output.exists():
        parser.error('Output exists; choose a new snapshot name.')

    def query(sql):
        result = subprocess.run(
            [args.mysql, '--defaults-file=' + args.defaults_file,
             '--no-login-paths', '--batch', '--database=' + args.database,
             '--execute=' + sql], capture_output=True, text=True, check=True)
        return list(csv.DictReader(io.StringIO(result.stdout), delimiter='\t'))

    character = query("SELECT guid,account,name,level,online,at_login,map,position_x,position_y,position_z,orientation FROM characters WHERE name='"
                      + args.character + "'")
    if len(character) != 1:
        parser.error('Expected exactly one matching character.')
    guid = int(character[0]['guid'])
    snapshot = {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'database': args.database,
        'character': character[0],
        'start': query(f'SELECT * FROM dc_character_start WHERE guid={guid}'),
        'homebind': query(f'SELECT * FROM character_homebind WHERE guid={guid}'),
        'mode': query(f'SELECT * FROM dc_character_mode WHERE guid={guid}'),
        'tier': query(f'SELECT * FROM dc_character_tier WHERE guid={guid}'),
        'skillbar': query(f'SELECT * FROM dc_character_skillbar WHERE guid={guid} ORDER BY slot'),
        'bags': query(f'SELECT * FROM dc_character_bag_grant WHERE guid={guid}'),
        'paragon': query('SELECT p.* FROM dc_account_paragon p JOIN characters c ON c.account=p.account_id '
                         'JOIN dc_character_mode m ON m.guid=c.guid AND m.mode=p.pool '
                         f'WHERE c.guid={guid}'),
        'allocation': query(f'SELECT * FROM dc_character_paragon WHERE guid={guid} ORDER BY stat'),
        'weapons': query('SELECT c.slot,i.guid,b.type,b.slot AS base_slot,b.rarity,b.designated_class,b.usable_by '
                         'FROM character_inventory c JOIN item_instance i ON i.guid=c.item '
                         f'JOIN `{args.world_database}`.dc_base_item b ON b.entry=i.itemEntry '
                         f'WHERE c.guid={guid} AND c.bag=0 AND c.slot IN (15,16) ORDER BY c.slot'),
        'starter_slots': query('SELECT * FROM dc_character_starter_item '
                               f'WHERE guid={guid} ORDER BY slot'),
        'inventory': query(
            'SELECT c.bag,c.slot,i.guid,i.itemEntry,i.count,d.base_item,d.rarity,'
            'd.rolled_at,d.crafted FROM character_inventory c '
            'JOIN item_instance i ON i.guid=c.item '
            'LEFT JOIN dc_item_instance d ON d.item_guid=i.guid '
            f'WHERE c.guid={guid} ORDER BY i.guid'),
        'buffer': query(f'SELECT * FROM dc_loot_buffer WHERE guid={guid} ORDER BY id'),
    }
    log = args.server_log.read_text(encoding='utf-8', errors='replace')
    snapshot['log_lines'] = [line for line in log.splitlines()
                             if args.character.casefold() in line.casefold()
                             and any(tag in line for tag in
                                     ('[DC world start]', '[DC world kit]',
                                      '[DC items]', '[DC stats] Loaded'))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the whole startup/login log before a restart overwrites it.
    log_copy = args.output.with_suffix('.server.log')
    with log_copy.open('x', encoding='utf-8') as stream:
        stream.write(log)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(snapshot, stream, indent=2)
        stream.write('\n')
    print(f"Saved {args.output}: {len(snapshot['starter_slots'])} starter slots, "
          f"{len(snapshot['inventory'])} inventory items, "
          f"{len(snapshot['buffer'])} buffered drops.")
    for line in snapshot['log_lines']:
        print(line)
    if args.compare:
        previous = json.loads(args.compare.read_text(encoding='utf-8'))
        if (previous['database'], previous['character']['guid']) != (args.database, str(guid)):
            parser.error('Comparison snapshot belongs to a different database or character.')
        changed = [key for key in ('start', 'starter_slots', 'inventory', 'buffer')
                   if previous[key] != snapshot[key]]
        print('Changed: ' + ', '.join(changed) if changed else
              'UNCHANGED: starter completion, slot GUIDs, inventory and buffer.')
        return bool(changed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
