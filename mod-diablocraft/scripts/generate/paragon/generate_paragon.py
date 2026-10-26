"""10-paragon migrations. Called by generate_sql.py --paragon; no historical rewrites."""
import csv
from decimal import Decimal
from pathlib import Path
import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration

ROOT = Path(__file__).resolve().parents[3]
CATEGORIES = ['Core', 'Offensive', 'Defensive', 'Utility']
# The 16 stats, their IDs and their numbers all come from paragon.csv now. The
# ID used to be a row's position in a list here, and that ID is what
# dc_character_paragon.stat holds: reordering the list would have silently
# re-pointed every saved allocation at a different stat. The prose columns stay
# and are DISPLAY ONLY: generation reads the cells and validates them
# structurally, so rewording a label or a sentence never blocks a build. The
# one-time proof that the cells equal what the old parser produced lives in
# test_paragon_ids.py as a frozen baseline, not in this path.

# loot_tuning.csv moved to data/tunables/ on 2026-09-19 (Architect): it is the designer's
# numbers, not D3's published data. Its runtime home is still dc_loot_tuning.
def read(root, name, folder='data/d3'):
    with (root / folder / (name + '.csv')).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, strict=True))

def quote(s):
    return "'" + str(s).replace("'", "''") + "'"

def cell(row, column, name):
    value = row[column].strip()
    if not value:
        raise ValueError(f'paragon.csv: {name}: {column} is empty')
    return value


def whole(row, column, name):
    value = cell(row, column, name)
    if not re.fullmatch(r'(0|[1-9][0-9]*)', value):
        raise ValueError(f'paragon.csv: {name}: {column} must be a whole number, got {value!r}')
    return int(value)


UNITS = {'', '%', 'yards'}
NUMBER = re.compile(r'(0|[1-9][0-9]*)(\.[0-9]+)?')
KEY = re.compile(r'[a-z][a-z0-9_]*')


PUBLISHED_RULE = re.compile(r"^INSERT INTO dc_paragon_rules VALUES \('(\d+)','([^']+)'", re.M)
PUBLISHED_RULE_CANDIDATE = re.compile(r"^INSERT INTO dc_paragon_rules VALUES ", re.M)


def check_published_rules(rows, published):
    """A published stat_id keeps the key it was published with.

    Contiguity cannot see the failure that matters. Swap two keys inside one
    category and the IDs still run 1..16, every category_id still matches, and
    every point any player ever spent now buys a different stat. The applied
    paragon_0001_rules.sql is the record of what the database was told, so it
    is what the sheet has to still agree with - and it is read here, before the
    generator overwrites it.

    As with base item entries: a missing, unreadable or half-parsed authority
    is an error, never a pass. A check with nothing to check is not a weaker
    check.
    """
    if not published.exists():
        raise ValueError(f'{published}: the published paragon rules migration is missing; '
                         f'the stat_id-to-stat_key pairing cannot be checked without it')
    try:
        text = published.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        raise ValueError(f'{published}: cannot be read as the published pairing: {error}') from error
    found = PUBLISHED_RULE.findall(text)
    candidates = len(PUBLISHED_RULE_CANDIDATE.findall(text))
    if not found:
        raise ValueError(f'{published}: no published paragon rules could be parsed; an '
                         f'unparsed authority is not a passed check')
    if len(found) != candidates:
        raise ValueError(f'{published}: parsed {len(found)} of {candidates} published rules; '
                         f'the pairing is not fully checked')
    published_keys = {}
    for identity, key in found:
        identity = int(identity)
        if identity in published_keys:
            raise ValueError(f'{published}: stat_id {identity} is published twice')
        published_keys[identity] = key
    by_id = {row[0]: row[1] for row in rows}
    for identity, key in sorted(published_keys.items()):
        if identity not in by_id:
            raise ValueError(f'paragon.csv: stat_id {identity} was published as {key!r} and is '
                             f'gone; a published paragon id is never removed')
        if by_id[identity] != key:
            raise ValueError(f'paragon.csv: stat_id {identity} was published as {key!r} but the '
                             f'sheet says {by_id[identity]!r}; a published paragon id keeps its '
                             f'key or every saved allocation changes meaning')
    return len(found)


def paragon_rules(root):
    """The 16 stats with their immutable IDs, read from paragon.csv.

    A row belongs to this realm exactly when it carries a stat_id; the D3 sheet
    also lists resources other classes use, and those keep empty cells.
    """
    rows, by_id, by_key = [], {}, {}
    for r in read(root, 'paragon'):
        if not r['stat_id'].strip():
            continue
        name = r['stat']
        identity = whole(r, 'stat_id', name)
        category = whole(r, 'category_id', name)
        key = cell(r, 'stat_key', name)
        value = cell(r, 'per_point', name)
        cap = whole(r, 'point_cap', name)
        unit = r['unit'].strip()
        if identity < 1:
            raise ValueError(f'{name}: stat_id must be positive')
        if identity in by_id:
            raise ValueError(f'stat_id {identity} is used by both {by_id[identity]!r} and {name!r}')
        if key in by_key:
            raise ValueError(f'stat_key {key!r} is used by both {by_key[key]!r} and {name!r}')
        if not KEY.fullmatch(key):
            raise ValueError(f'{name}: stat_key {key!r} is not a lower-case identifier')
        by_id[identity], by_key[key] = name, name
        if category >= len(CATEGORIES):
            raise ValueError(f'{name}: category_id {category} is not one of 0..{len(CATEGORIES)-1}')
        if r['points_per_rank'] != '1':
            raise ValueError('Unexpected paragon point rule: ' + name)
        if not NUMBER.fullmatch(value):
            raise ValueError(f'{name}: per_point must be a number, got {value!r}')
        if Decimal(value) <= 0:
            raise ValueError(f'{name}: per_point must be positive')
        if unit not in UNITS:
            raise ValueError(f'{name}: unit must be one of {sorted(UNITS)!r}, got {unit!r}')
        rows.append((identity, key, name, category, value, cap, unit))
    rows.sort()
    check_published_rules(rows, root / 'data/sql/db-world/updates/paragon_0001_rules.sql')
    # dc_character_paragon.stat is stored as this ID and read back as an array
    # index, so the published IDs have to stay 1..N with nothing missing.
    if [row[0] for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('paragon stat_id must run 1..%d with no gaps' % len(rows))
    if len(rows) != 16:
        raise ValueError('expected 16 paragon stats, found %d' % len(rows))
    # Four categories of four, in order: the allocation rule depends on it.
    for identity, key, name, category, *_ in rows:
        if category != (identity - 1) // 4:
            raise ValueError(f'{name}: stat_id {identity} belongs to category '
                             f'{(identity - 1) // 4}, not {category}')
    return rows


def party_rule(root):
    """The party XP numbers, from cells. The sentence beside them is prose.

    The cells have to agree with each other - the cap is the per-player bonus
    over one short of a full party - which is a check on the numbers rather
    than on anybody's wording.
    """
    row = next(r for r in read(root, 'monster_xp') if r['rule/level'] == 'party_xp_bonus')
    try:
        per = int(row['party_per_member_pct'])
        cap = int(row['party_bonus_cap_pct'])
        members = int(row['party_max_members'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('monster_xp.csv: party XP cells are missing or not whole numbers') from error
    if members < 1:
        raise ValueError('monster_xp.csv: party_max_members must be at least 1')
    if per < 0 or cap < 0:
        raise ValueError('monster_xp.csv: party XP percentages cannot be negative')
    if per * (members - 1) != cap:
        raise ValueError(f'monster_xp.csv: {per}% per extra player over {members} members is '
                         f'{per * (members - 1)}%, not the {cap}% cap')
    return per, cap, members


def generate(root=ROOT):
    from generate_sql import render_table, TABLES
    rows = paragon_rules(root)
    per, cap, members = party_rule(root)
    supported = sorted(int(r['players']) for r in read(root, 'party_scaling') if r['context'] == 'open_world')
    if supported != list(range(1, members+1)) or per*(members-1) != cap:
        raise ValueError('party_scaling and monster_xp disagree')
    tuning = read(root, 'loot_tuning', 'data/tunables')
    base = int(next(r['base_monster_xp'] for r in tuning if r['source'] == 'normal'))
    if base <= 0: raise ValueError('base_monster_xp must be positive')
    world = [
        '-- Generated by generate_sql.py --paragon from paragon.csv, monster_xp.csv, party_scaling.csv and loot_tuning.csv.',
        'SET NAMES utf8mb4;',
        'CREATE TABLE IF NOT EXISTS dc_paragon_rules (id INT UNSIGNED PRIMARY KEY, stat_key VARCHAR(32) NOT NULL UNIQUE, name VARCHAR(128) NOT NULL, category INT UNSIGNED NOT NULL, per_point DECIMAL(12,4) NOT NULL, cap INT UNSIGNED NOT NULL, unit VARCHAR(8) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;',
        'DELETE FROM dc_paragon_rules;',
    ]
    world += ['INSERT INTO dc_paragon_rules VALUES (' + ','.join(quote(v) for v in row) + ');' for row in rows]
    world += [
        'CREATE TABLE IF NOT EXISTS dc_paragon_party_xp (id INT UNSIGNED PRIMARY KEY, per_member INT UNSIGNED NOT NULL, bonus_cap INT UNSIGNED NOT NULL, max_members INT UNSIGNED NOT NULL) ENGINE=InnoDB;',
        f'REPLACE INTO dc_paragon_party_xp VALUES (1,{per*100},{cap*100},{members});',
        "SET @dc_has_base_xp=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='dc_loot_tuning' AND column_name='base_monster_xp');",
        "SET @dc_paragon_ddl=IF(@dc_has_base_xp=0,'ALTER TABLE dc_loot_tuning ADD COLUMN base_monster_xp BIGINT UNSIGNED NULL','DO 0');",
        'PREPARE dc_paragon_stmt FROM @dc_paragon_ddl;', 'EXECUTE dc_paragon_stmt;', 'DEALLOCATE PREPARE dc_paragon_stmt;',
        f"UPDATE dc_loot_tuning SET base_monster_xp={base} WHERE source='normal';",
    ]
    characters = [
        '-- Generated by generate_sql.py --paragon; schema from 10-paragon section 2.',
        "CREATE TABLE IF NOT EXISTS dc_account_paragon (account_id INT UNSIGNED NOT NULL, pool ENUM('normal','hardcore') NOT NULL, level INT UNSIGNED NOT NULL DEFAULT 0, xp BIGINT UNSIGNED NOT NULL DEFAULT 0, PRIMARY KEY(account_id,pool)) ENGINE=InnoDB;",
        'CREATE TABLE IF NOT EXISTS dc_character_paragon (guid INT UNSIGNED NOT NULL, stat INT UNSIGNED NOT NULL, points INT UNSIGNED NOT NULL DEFAULT 0, PRIMARY KEY(guid,stat)) ENGINE=InnoDB;',
    ]
    loot_sql, _ = render_table(root / 'data/tunables/loot_tuning.csv', TABLES['loot_tuning'])
    (root / 'data/generated').mkdir(parents=True, exist_ok=True)
    for db, stem, lines in [('world', 'paragon_0001_rules', world), ('characters', 'paragon_0001_pools', characters)]:
        data = ('\n'.join(lines) + '\n').encode('utf-8')
        (root / 'data/generated' / (stem + '.sql')).write_bytes(data)
        write_migration(root, root / f'data/sql/db-{db}/updates/{stem}.sql', data)
    # Current reference snapshot, separate from the immutable 0001 migration.
    (root / 'data/generated/loot_tuning.sql').write_bytes(loot_sql.encode('utf-8'))
    print('Paragon: 16 Barbarian stats, party XP rule, shared base XP tunable, account pools and character allocations generated.')

if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()
