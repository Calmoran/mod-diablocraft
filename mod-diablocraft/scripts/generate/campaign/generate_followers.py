#!/usr/bin/env python3
"""Emit the followers' world rows from data/d3/followers_roster.csv and data/d3/followers_rules.csv (diablocraft-gh1c1.3).

followers_0001_roster.sql: the dc_follower table (the three followers, their creature entries and names) and the
dc_follower_rule table (the revive, party and catch-up rules), which src/campaign/dc_followers.cpp reads at startup.
Nothing in it depends on how a follower looks.

followers_0002_templates.sql: one creature template per follower, the donor creature's own row and model with the
module's AI (ScriptName dc_follower), a gossip menu, no loot, gold or credit, and life and damage at the stock
numbers of its level (modifiers 1, rank 0). Written only when every row names a donor: the donor is the follower's
look, which is the designer's to choose, so until then the sheet's donor_creature cells stay blank and this file is not made.
A follower's life, damage and gear stats come from its own gear (docs/contracts/followers.md), not from the donor.

followers_0003_hub.sql: the three hub spawns, one `creature` row each from data/d3/followers_hub.csv (the designer's .gps reading,
card q-1016-23, and the places around it). It guards each guid: free, or already this follower's.

Those three migrations are history: they ran on dev with the Templar at entry 900140 and the Scoundrel at 900141, which are
the Crusader Phalanx's Avatar and Warhorse (classes_0004_crusader_summons.sql), so the follower templates overwrote the
Crusader's and the hub spawns showed the wrong creatures (diablocraft-gh1c1.8). They are no longer rendered and stay as they
ran. followers_0004_entries.sql is the one migration this generator writes: it moves the Templar to 900143 and the Scoundrel
to 900144, puts the Crusader's two templates back, re-points the hub spawns, and writes the roster and the rules again
(the party rule is now zero). It is written to run on a world that has 0001 to 0003 and on one that has not, any number of times.
"""
import csv
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import write_migration

MODULE = Path(__file__).resolve().parents[3]
SCRIPT = 'dc_follower'
KEYS = ('templar', 'scoundrel', 'enchantress')
STATS = ('strength', 'dexterity', 'intelligence')
RULES = ('revive_seconds', 'party_leave_seconds', 'catch_up_seconds', 'catch_up_yards')
# The one rule that may be zero: a second player sends the follower away at once (the designer's dev look, q-1021-43).
MAY_BE_ZERO = ('party_leave_seconds',)
MIGRATION = 'followers_0004_entries'
# Where the first migrations (0001 to 0003) put the three before they were renumbered, by key.
LEGACY_ENTRIES = {'templar': 900140, 'scoundrel': 900141, 'enchantress': 900142}
# Our spawn guid space starts here (scripts/export_dev_edits.py OUR_GUIDS) and ends at the largest guid the world tables hold.
OUR_GUIDS = 8000000
MAX_GUID = 4294967295
# The respawn column of every hub service spawn (the other hub rows carry 300); a friendly hub follower is never killed.
SPAWN_SECONDS = 300
# The entries the module's other creatures hold; a follower never takes one.
TAKEN = (range(900100, 900103), range(900110, 900118), range(900120, 900128), range(900130, 900136),
         range(900140, 900142), range(900150, 900155), range(910000, 910014))


def read(module, name):
    with (module / 'data/d3' / name).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def quote(text):
    return "'" + text.replace('\\', '\\\\').replace("'", "''") + "'"


def roster(module=MODULE):
    out, seen = [], set()
    rows = read(module, 'followers_roster.csv')
    if [r['key'] for r in rows] != list(KEYS):
        raise ValueError(f"followers_roster.csv: the rows are {', '.join(KEYS)}, in that order")
    for number, row in enumerate(rows, 1):
        where = f"followers_roster.csv {row['key']}"
        if row['follower_id'] != str(number):
            raise ValueError(f'{where}: follower_id is {number}')
        if row['main_stat'] != STATS[number - 1]:
            raise ValueError(f'{where}: main_stat is {STATS[number - 1]}')
        if not row['name'] or not row['subname'] or not row['source']:
            raise ValueError(f'{where}: name, subname and source are required')
        entry, level = int(row['entry']), int(row['level'])
        if entry in seen or any(entry in taken for taken in TAKEN):
            raise ValueError(f'{where}: entry {entry} is taken')
        seen.add(entry)
        if not 1 <= level <= 80:
            raise ValueError(f'{where}: level is 1 to 80')
        donor = int(row['donor_creature']) if row['donor_creature'] else 0
        out.append(dict(id=number, key=row['key'], name=row['name'], subname=row['subname'], entry=entry, level=level,
                        donor=donor, legacy=LEGACY_ENTRIES[row['key']]))
    return out


def hub(module=MODULE):
    """The hub spawns from followers_hub.csv, one per roster follower, in roster order."""
    names = {r['id']: r for r in roster(module)}
    rows = read(module, 'followers_hub.csv')
    if [r['key'] for r in rows] != list(KEYS):
        raise ValueError(f"followers_hub.csv: the rows are {', '.join(KEYS)}, in that order")
    out, guids, places = [], set(), set()
    for number, row in enumerate(rows, 1):
        where = f"followers_hub.csv {row['key']}"
        if row['follower_id'] != str(number):
            raise ValueError(f'{where}: follower_id is {number}')
        guid = int(row['guid'])
        if not OUR_GUIDS <= guid <= MAX_GUID or guid in guids:
            raise ValueError(f'{where}: guid {guid} is outside the module space or repeated')
        guids.add(guid)
        x, y, z, o = (float(row[c]) for c in 'xyzo')
        if not all(math.isfinite(v) for v in (x, y, z, o)) or not 0 <= o < 2 * math.pi:
            raise ValueError(f'{where}: x, y, z and o are finite numbers, o in [0, 2 pi)')
        if (x, y) in places:
            raise ValueError(f'{where}: another follower stands on this spot')
        places.add((x, y))
        if not row['source']:
            raise ValueError(f'{where}: source is required')
        out.append(dict(id=number, guid=guid, entry=names[number]['entry'], legacy=names[number]['legacy'], map=int(row['map_id']),
                        area=int(row['area_id']), x=x, y=y, z=z, o=o))
    if len({(r['map'], r['area']) for r in out}) != 1:
        raise ValueError('followers_hub.csv: the three stand in one area')
    return out


def rules(module=MODULE):
    rows = read(module, 'followers_rules.csv')
    if [r['rule'] for r in rows] != list(RULES):
        raise ValueError(f"followers_rules.csv: the rules are {', '.join(RULES)}, in that order")
    out = []
    for row in rows:
        value = float(row['value'])
        if not math.isfinite(value) or value < 0 or (value == 0 and row['rule'] not in MAY_BE_ZERO):
            raise ValueError(f"followers_rules.csv {row['rule']}: the value is a positive number"
                             + (' or zero' if row['rule'] in MAY_BE_ZERO else ''))
        if not row['unit'] or not row['source']:
            raise ValueError(f"followers_rules.csv {row['rule']}: unit and source are required")
        out.append((row['rule'], format(value, '.15g'), row['unit']))
    return out


def render_roster(module=MODULE):
    sql = ("-- Generated by generate_followers.py from followers_roster.csv and followers_rules.csv; do not hand-edit.\n"
           "CREATE TABLE IF NOT EXISTS dc_follower (\n"
           "  follower_id TINYINT UNSIGNED NOT NULL PRIMARY KEY,\n"
           "  entry INT UNSIGNED NOT NULL,\n"
           "  name VARCHAR(64) NOT NULL\n"
           ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n"
           "CREATE TABLE IF NOT EXISTS dc_follower_rule (\n"
           "  rule VARCHAR(32) NOT NULL PRIMARY KEY,\n"
           "  value DOUBLE NOT NULL,\n"
           "  unit VARCHAR(16) NOT NULL\n"
           ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n"
           "DELETE FROM dc_follower;\n"
           "INSERT INTO dc_follower (follower_id, entry, name) VALUES\n")
    sql += ',\n'.join(f"({r['id']},{r['entry']},{quote(r['name'])})" for r in roster(module)) + ';\n'
    sql += "DELETE FROM dc_follower_rule;\nINSERT INTO dc_follower_rule (rule, value, unit) VALUES\n"
    sql += ',\n'.join(f"({quote(name)},{value},{quote(unit)})" for name, value, unit in rules(module)) + ';\n'
    return sql


def render_templates(module=MODULE):
    """The creature templates, or None while a follower has no donor."""
    rows = roster(module)
    if not all(r['donor'] for r in rows):
        return None
    sql = "-- Generated by generate_followers.py from followers_roster.csv; do not hand-edit.\n"
    for r in rows:
        entry, donor = r['entry'], r['donor']
        sql += (f"DELETE FROM creature_template WHERE entry={entry};\n"
                "CREATE TEMPORARY TABLE dc_follower_clone LIKE creature_template;\n"
                f"INSERT INTO dc_follower_clone SELECT * FROM creature_template WHERE entry={donor};\n"
                f"UPDATE dc_follower_clone SET entry={entry},name={quote(r['name'])},subname={quote(r['subname'])},"
                f"minlevel={r['level']},maxlevel={r['level']},`rank`=0,HealthModifier=1,DamageModifier=1,"
                "npcflag=1,unit_flags=0,unit_flags2=0,type_flags=0,faction=35,AIName='',"
                f"ScriptName='{SCRIPT}',gossip_menu_id=0,lootid=0,pickpocketloot=0,skinloot=0,mingold=0,maxgold=0,"
                "KillCredit1=0,KillCredit2=0,flags_extra=0,difficulty_entry_1=0,difficulty_entry_2=0,"
                "difficulty_entry_3=0;\n"
                "INSERT INTO creature_template SELECT * FROM dc_follower_clone;\n"
                "DROP TEMPORARY TABLE dc_follower_clone;\n"
                f"DELETE FROM creature_template_model WHERE CreatureID={entry};\n"
                f"INSERT INTO creature_template_model SELECT {entry},Idx,CreatureDisplayID,DisplayScale,"
                f"Probability,VerifiedBuild FROM creature_template_model WHERE CreatureID={donor};\n")
    return sql


def render_hub(module=MODULE):
    """The hub spawns, or None while a follower has no donor (a spawn of a template that is not there)."""
    if not all(r['donor'] for r in roster(module)):
        return None
    rows = hub(module)
    guids = ','.join(str(r['guid']) for r in rows)
    sql = ("-- Generated by generate_followers.py from followers_hub.csv and followers_roster.csv; do not hand-edit.\n"
           "SET NAMES utf8mb4;\n"
           "CREATE TEMPORARY TABLE dc_follower_hub_guard (ok INT NOT NULL CHECK(ok=1));\n")
    for r in rows:
        sql += (f"INSERT INTO dc_follower_hub_guard VALUES ((NOT EXISTS(SELECT 1 FROM creature WHERE guid={r['guid']}) OR "
                f"EXISTS(SELECT 1 FROM creature WHERE guid={r['guid']} AND id IN ({r['entry']},{r['legacy']}))));\n")
    sql += f"DELETE FROM creature WHERE guid IN ({guids});\n"
    sql += ("INSERT INTO creature (guid,id,map,zoneId,areaId,spawnMask,phaseMask,position_x,position_y,position_z,orientation,"
            "spawntimesecs,wander_distance,MovementType) VALUES\n")
    sql += ',\n'.join(f"({r['guid']},{r['entry']},{r['map']},{r['area']},{r['area']},1,1,{r['x']!r},{r['y']!r},{r['z']!r},"
                      f"{r['o']!r},{SPAWN_SECONDS},0,0)" for r in rows) + ';\n'
    return sql + "DROP TEMPORARY TABLE dc_follower_hub_guard;\n"


def body(sql):
    """A render without its generated-by comment line."""
    return sql.split('\n', 1)[1]


def render_entries(module=MODULE):
    """followers_0004_entries.sql, or None while a follower has no donor.

    In order: the roster and the rules; the Crusader's Avatar and Warhorse templates (the follower templates of the first
    migrations overwrote them); the follower templates at their entries; the hub spawns, which may still hold the first
    entries, moved to the new ones."""
    templates, spawns = render_templates(module), render_hub(module)
    if templates is None or spawns is None:
        return None
    import generate_crusader_summons
    return ("-- Generated by generate_followers.py from followers_roster.csv, followers_rules.csv, followers_hub.csv and "
            "crusader_summons.csv; do not hand-edit.\n" + body(render_roster(module))
            + "-- The Crusader Phalanx's two templates, as classes_0004_crusader_summons.sql writes them.\n"
            + body(generate_crusader_summons.render(module)) + body(templates) + body(spawns))


def generate(module=MODULE):
    sql = render_entries(module)
    if sql is None:
        print(f'{MIGRATION}: not written, a follower has no donor_creature yet')
        return
    (module / f'data/generated/{MIGRATION}.sql').write_text(sql, encoding='utf-8', newline='\n')
    write_migration(module, module / f'data/sql/db-world/updates/{MIGRATION}.sql', sql)


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()
