"""Weapon proficiencies every playable class needs, as stock SkillRaceClassInfo rows.

Ruling 2026-09-23 (diablocraft-class-parity Q1, weapons option A). A D3 class
may use weapon types its WoW body cannot: a Wizard (Mage) swings axes, maces and
bows. The core only lets a character learn a skill that SkillRaceClassInfo
allows for its race and class (`Player::LearnDefaultSkill`, `GetSkillRaceClassInfo`),
and with ValidateSkillLearnedBySpells it deletes a proficiency spell whose skill
is not allowed. So each missing (class, weapon skill) pair gets its own row,
through the stock table and nothing parallel to it.

Everything is derived, nothing is picked:

* the weapon types a class uses are `base_items.csv` rows whose `usable_by`
  lists the class (or is empty) and whose `designated_class` is empty or that
  class - the start kit's own eligibility rule (dc_world.cpp Usable);
* each type's skill is the core's `ItemTemplate::GetSkill` of the item class
  and subclass generate_sql.py writes for it;
* a pair already allowed by the server's own SkillRaceClassInfo.dbc for that
  class (any race) is native and gets no row;
* a new row copies Flags, SkillTierID and SkillCostIndex from the stock rows of
  the same skill (they must agree) and allows every race of that one class.

Identities are append-only in data/class_proficiency_ids.csv, inside the block
the PM reserved (decisions.md 2026-09-23: 1002-1999). A pair with no identity is
an error naming the pair; an identity is never allocated from row order.

Outputs: the world migration (server overlay `skillraceclassinfo_dbc`) and, coupled to it, the client's
SkillRaceClassInfo.dbc and a data/generated mirror.
"""
import argparse
import csv
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from class_names import item_key
from applied_migrations import require_companion_migration, write_coupled_outputs, write_migration
from generate_sql import classify
from dbc_store import Store, schema, sql_value

MODULE = Path(__file__).resolve().parents[3]
# world_0017 (the Wizard's rows) and world_0049 (the Monk's) are applied and frozen; the Necromancer's
# (diablocraft-im7mr.1) render the whole reserved block into the next number, and a class added later is a new number again:
# world_0061 is applied, so the Crusader's are world_0067; world_0067 is applied, so the Demon Hunter's are world_0073; world_0073 is applied, so the Witch Doctor's are world_0079; world_0079 is applied, so the Shaman's are world_0085; world_0085 is applied, so the Shaman's two weapon skills are world_0088 (the number is provisional until the merge).
MIGRATION = "world_0088_class_proficiencies.sql"
RESERVED = range(1002, 2000)          # decisions.md 2026-09-23, PM reservation
ITEM_CLASS_WEAPON = 2
# ItemTemplate::GetSkill, item_weapon_skills (azerothcore-wotlk
# src/server/game/Entities/Item/ItemTemplate.h:784-791), indexed by subclass.
WEAPON_SKILLS = (44, 172, 45, 46, 54, 160, 229, 43, 55, 0, 136, 0, 0, 473, 0, 173, 176, 253, 226, 228, 356)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def classes(module):
    """class_key -> WoW class id, from class_map.csv (the playable classes)."""
    return {item_key(row["d3_class"]): int(row["wow_class_id"])
            for row in read_csv(module / "data/d3/class_map.csv")}


def usable(base, key):
    listed = base["usable_by"]
    return ((not listed or key in listed.split(";"))
            and (not base["designated_class"] or base["designated_class"] == key))


def weapon_skills(module, key):
    """skill id -> sorted D3 weapon types needing it, for one class key."""
    needed = {}
    for line, base in enumerate(read_csv(module / "data/d3/base_items.csv"), 2):
        if base["pool_version"] != "yes" or not usable(base, key):
            continue
        item_class, subclass, _ = classify(base, module / "data/d3/base_items.csv", line, list(base.values()))
        if item_class != ITEM_CLASS_WEAPON:
            continue
        skill = WEAPON_SKILLS[subclass] if subclass < len(WEAPON_SKILLS) else 0
        if skill:
            needed.setdefault(skill, set()).add(base["type"])
    return {skill: sorted(types) for skill, types in needed.items()}


def identities(module):
    path = module / "data/class_proficiency_ids.csv"
    rows = read_csv(path)
    result, used = {}, set()
    for row in rows:
        if list(row) != ["class_key", "skill_id", "race_class_id"]:
            raise ValueError(f"{path.name}: expected class_key,skill_id,race_class_id")
        key, identity = (row["class_key"], int(row["skill_id"])), int(row["race_class_id"])
        if identity not in RESERVED:
            raise ValueError(f"{path.name}: {identity} is outside the reserved block 1002-1999")
        if key in result or identity in used:
            raise ValueError(f"{path.name}: duplicate pair or identity: {row!r}")
        result[key], used = identity, used | {identity}
    return result


def load(path, root):
    return Store(path.read_bytes(), schema(root, "skillraceclassinfo_dbc"))


def render(module=MODULE, server_dbc=None, client_dbc=None):
    """(records, sql) for every needed pair; validates before anything is written."""
    root = module.parent
    server = load(Path(server_dbc) if server_dbc else
                  root / "azerothcore-wotlk/build/server/data/dbc/SkillRaceClassInfo.dbc", root)
    client = load(Path(client_dbc) if client_dbc else root / "client-patch/dbc/SkillRaceClassInfo.dbc", root)
    stock = [server.decode(k) for k in server.rows if k not in RESERVED]
    ids = identities(module)
    records, wanted = [], set()
    for key, wow_class in sorted(classes(module).items(), key=lambda item: item[1]):
        bit = 1 << (wow_class - 1)
        for skill, types in sorted(weapon_skills(module, key).items()):
            same = [r for r in stock if r["SkillID"] == skill]
            if any(not r["ClassMask"] or r["ClassMask"] & bit for r in same):
                continue                                     # native for this class
            shapes = {(r["Flags"], r["SkillTierID"], r["SkillCostIndex"]) for r in same}
            if len(shapes) != 1:
                raise ValueError(f"skill {skill}: stock rows disagree on Flags/SkillTierID/SkillCostIndex {shapes}")
            if (key, skill) not in ids:
                raise ValueError(f"data/class_proficiency_ids.csv has no identity for {key} skill {skill} "
                                 f"({', '.join(types)}); append one from the reserved block")
            flags, tier, cost = shapes.pop()
            records.append(dict(ID=ids[(key, skill)], SkillID=skill, RaceMask=0, ClassMask=bit, Flags=flags,
                                MinLevel=0, SkillTierID=tier, SkillCostIndex=cost))
            wanted.add((key, skill))
    stale = set(ids) - wanted
    if stale:
        raise ValueError(f"identities with no needed pair (retire them deliberately): {sorted(stale)}")
    # A reserved identity must not already mean something else on either side.
    for store, side in ((server, "server"), (client, "client")):
        for record in records:
            if record["ID"] in store.rows and store.decode(record["ID"]) != record:
                other = store.decode(record["ID"])
                if other["SkillID"] != record["SkillID"] or other["ClassMask"] != record["ClassMask"]:
                    raise ValueError(f"{side} SkillRaceClassInfo {record['ID']} already holds {other}")
    columns = [c[0] for c in client.columns]
    keys = ",".join(str(r["ID"]) for r in records)
    sql = ["-- Generated by generate_class_proficiencies.py from base_items.csv usable_by, class_map.csv",
           "-- and the stock SkillRaceClassInfo; identities from data/class_proficiency_ids.csv.",
           "-- ruling 2026-09-23 (diablocraft-class-parity Q1 weapons option A).",
           "SET NAMES utf8mb4;",
           f"DELETE FROM `skillraceclassinfo_dbc` WHERE ID BETWEEN {RESERVED.start} AND {RESERVED.stop - 1};"]
    if records:
        sql.append("INSERT INTO `skillraceclassinfo_dbc` (" + ",".join(f"`{c}`" for c in columns) + ") VALUES\n"
                   + ",\n".join("(" + ",".join(sql_value(r[c]) for c in columns) + ")" for r in records) + ";")
    return records, client, "\n".join(sql) + "\n"


def generate(module=MODULE, server_dbc=None, client_dbc=None, migration=None):
    module = Path(module)
    root = module.parent
    updates = module / "data/sql/db-world/updates"
    migration = Path(migration) if migration else updates / MIGRATION
    require_companion_migration(module, migration, updates)
    records, client, sql = render(module, server_dbc, client_dbc)
    for key in [k for k in client.rows if k in RESERVED]:
        del client.rows[key]
    for record in records:
        client.encode(record)
    client.rows = dict(sorted(client.rows.items()))
    write_migration(module, migration, sql)
    write_coupled_outputs(module, migration, sql, [
        (module / "data/generated/class_proficiencies.sql", sql.encode()),
        (Path(client_dbc) if client_dbc else root / "client-patch/dbc/SkillRaceClassInfo.dbc", client.bytes()),
    ], label="Class proficiency client DBC and generated mirror")
    print(f"class proficiencies: {len(records)} SkillRaceClassInfo rows")
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--migration", type=Path)
    args = parser.parse_args()
    generate(migration=args.migration)
