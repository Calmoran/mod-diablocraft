"""Resolve D3Planner's slot groups to skill bonuses by spell id; never edit CSVs.

K5. This used to bridge a D3Planner affix to a skill by stripping every
non-letter from both English names and matching the result, and the server then
carried that English name all the way into the damage formula. Two skills whose
names normalise alike would have collided silently, and renaming a skill would
have detached every affix pointing at it.

The affix id itself says which class and which skill it belongs to
(`skill_barbarian_ancientspear`), so the class stem is matched against
`class_key` - the canonical identity the class catalogue publishes - and the
skill stem against that class's own skills. What is written is the **base
skill's spell id**, because a "+X% Bash damage" affix applies to Bash with any
rune; the runes share `skill_id` and differ in `spell_id`.

Every step that could be ambiguous is checked rather than assumed: colliding
normalised names, an unknown class, an unknown skill, and an affix that resolves
to more than one id are all errors.

diablocraft-class-roll-rules rule 6 (decisions.md 2026-09-23): every playable
class has its own groups. D3Planner's `skill_<slot>` group lists the per-class
groups (`skill_wizard_head`, ...); each one whose class has a generated catalogue
is read, in catalogue class order, into the same `skill_<slot>` group id the
affix pool rolls, and the server picks among the choices of the item's class.
Classes with no catalogue get no rows yet. The rows ship in their own new
migration; items_0004/items_0005 were applied Barbarian-only and stay frozen.

A class D3Planner has no groups for (the Shaman is not a D3 class) gets its groups from its own
skill sheet by D3's slot rule: the legs group is every Primary (all seven D3 classes, exactly),
the head group the damaging Secondaries and the torso group the other damaging skills, and a
Defensive skill is left out (D3 gives an affix to 1 of its 23 Defensive skills, a pet). D3 has no
category rule for head against torso beyond that the Secondaries sit mostly in the head (24 of
28), so the split is the rule's reading, not D3's list. The affix id is the class key and the skill's shown
name, as D3Planner spells them (`skill_shaman_earthquake`).
"""
import csv
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_class_catalogue as catalogue_source
import generate_spells as spells_source
from applied_migrations import write_migration
from class_names import item_key

ROOT = pathlib.Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"


def stem(name):
    return re.sub(r"[^a-z]", "", name.lower())


def skills_by_class():
    """class_key -> {normalised skill name: (class_id, skill_id)}, from the
    catalogue's own rows. Base rows only: rune_id 0 is the skill itself."""
    rows, _, labels, _, class_map, _, _, _ = catalogue_source.catalogue()
    key_of = {row[0]: row[1] for row in class_map}          # class_id -> class_key
    name_of = {(label[1], label[0]): label[2] for label in labels}
    table = {}
    for class_id, skill_id, rune_id, spell_id, _unlock, _indicator in rows:
        if rune_id:
            continue
        class_key = key_of[class_id]
        skill_name = name_of[(class_id, spell_id)]
        bucket = table.setdefault(class_key, {})
        collapsed = stem(skill_name)
        if collapsed in bucket and bucket[collapsed] != (class_id, skill_id, skill_name):
            raise ValueError(
                f"{class_key}: {skill_name!r} and {bucket[collapsed][2]!r} both normalise to "
                f"{collapsed!r}, so a D3Planner affix could not name one of them")
        bucket[collapsed] = (class_id, skill_id, skill_name)
    return table


# items_0004 and items_0005 were applied with the Barbarian's rows only; their
# renders are reproduced from exactly those classes so they never move a byte.
APPLIED_CLASS_IDS = (1,)

SLOTS = ("head", "torso", "legs")


def playable_classes():
    """(class_id, class_key) for every class with a generated catalogue, in id order."""
    _, _, _, _, class_map, _, _, _ = catalogue_source.catalogue()
    return sorted((row[0], row[1]) for row in class_map)


# The slot rule for a class D3Planner has no groups for. Legs is every Primary in each of D3's
# seven classes; a skill with no weapon-damage figure has no damage to raise.
LEGS_CATEGORY = "Primary"
HEAD_CATEGORY = "Secondary"
NO_AFFIX_CATEGORY = "Defensive"


def sheet_skills(class_key):
    """The class's own skill sheet rows, in sheet order."""
    for _class_id, d3_class, stem in catalogue_source.classes():
        if item_key(d3_class) == class_key:
            return catalogue_source.read(catalogue_source.D3 / f"{stem}_skills.csv")
    raise ValueError(f"{class_key!r} has no skill sheet")


def derived_slot(skill):
    """head, torso, legs or None: the slot of D3's skill-damage affix for this sheet row."""
    if not (skill.get("damage_pct_weapon_damage") or "").strip():
        return None
    category = skill["category"].strip()
    if category == LEGS_CATEGORY:
        return "legs"
    if category == HEAD_CATEGORY:
        return "head"
    if category == NO_AFFIX_CATEGORY:
        return None
    return "torso"


def derived_groups(class_key, slot):
    """[(affix id, sheet skill name)] for `slot`, from the class's sheet."""
    shown = spells_source.shown_names()
    return [(f"skill_{class_key}_{stem(spells_source.shown_name(shown, skill['skill_name']))}",
             skill["skill_name"])
            for skill in sheet_skills(class_key) if derived_slot(skill) == slot]


def definitions():
    reference = json.loads((ROOT / "reference/d3planner/data.json").read_text(encoding="utf-8"))
    groups = reference["statGroups"]
    table = skills_by_class()
    shown = spells_source.shown_names()
    rows = []
    for slot in SLOTS:
        group = "skill_" + slot
        # D3Planner's own union for the slot names every class's group.
        members = groups[group]
        index = 0
        for _class_id, class_key in playable_classes():
            member = f"skill_{class_key}_{slot}"
            if member in groups:
                if member not in members:
                    raise ValueError(f"{group!r} in data.json lists no {member!r} for playable "
                                     f"class {class_key!r}; members: {members!r}")
                named = []
                for affix in groups[member]:
                    body = affix.removeprefix("skill_")
                    affix_class, _, skill_stem = body.partition("_")
                    if affix_class != class_key:
                        raise ValueError(f"{affix!r} in {member!r} names class {affix_class!r}")
                    named.append((affix, skill_stem))
            else:
                named = [(affix, stem(skill)) for affix, skill in derived_groups(class_key, slot)]
            for affix, skill_stem in named:
                affix_class = affix.removeprefix("skill_").partition("_")[0]
                if affix_class not in table:
                    raise ValueError(f"{affix!r} names class {affix_class!r}, which has no generated "
                                     f"catalogue; known: {sorted(table)!r}")
                if skill_stem not in table[affix_class]:
                    raise ValueError(f"{affix!r} names no skill of {affix_class!r}")
                class_id, skill_id, skill = table[affix_class][skill_stem]
                skill = spells_source.shown_name(shown, skill)
                rows.append((group, index, affix, class_id, skill_id, skill, skill + " Damage"))
                index += 1

    # One affix id must mean one skill. The primary key would catch a repeat of
    # the id itself; this catches the same id arriving with two different
    # targets, which is the collision that would silently move a bonus.
    seen = {}
    for group, _index, affix, class_id, skill_id, _skill, _name in rows:
        target = (class_id, skill_id)
        if seen.setdefault(affix, target) != target:
            raise ValueError(f"{affix!r} resolves to both {seen[affix]!r} and {target!r}")
    return rows


# items_0012 (Barbarian, Wizard) and items_0029 (the Monk) are applied and frozen; each
# class added since ships every class's rows again in a new number (the REPLACE is
# idempotent): items_0044 for the Necromancer (applied on dev and frozen), items_0049 for
# the Crusader (applied on dev and frozen), items_0052 for the Demon Hunter (applied on dev
# and frozen), items_0055 for the Witch Doctor (applied on dev and frozen), items_0062 for the
# Shaman.
CLASSES_MIGRATION = "items_0062_skill_affix_classes.sql"

# No semicolon inside: a literal containing one breaks any runner that splits a
# script on semicolons.
ABORT_UNRESOLVED = ('MIGRATION ABORTED - a dc_skill_affix row has no skill_id. Re-run '
                    'generate_skill_affixes.py and re-import the affix migrations')


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def cell(value):
    return str(value) if isinstance(value, int) else quote(value)


def render_classes(rows):
    """items_0012: every playable class's rows, ids included, in one idempotent
    REPLACE. The (group_id, choice_index) key is stable because classes are
    appended in catalogue id order, so the applied Barbarian rows keep theirs."""
    sql = "-- Generated by generate_skill_affixes.py from D3Planner statGroups and the class catalogue.\n"
    sql += "-- diablocraft-class-roll-rules rule 6: each playable class's own skill-affix choices in the\n"
    sql += "-- slot groups the affix pool rolls. The server rolls only the choices of the item's class\n"
    sql += "-- (dc_roll_class.h). Classes with no generated catalogue get no rows yet.\n"
    sql += "REPLACE INTO dc_skill_affix (group_id,choice_index,affix_id,class_id,skill_id,skill_name,affix_name) VALUES\n"
    sql += ",\n".join(
        f"({quote(group)},{index},{quote(affix)},{class_id},{skill_id},{quote(skill)},{quote(name)})"
        for group, index, affix, class_id, skill_id, skill, name in rows) + ";\n"
    sql += "-- Backstop, as items_0005: a row left without a skill_id aborts on a duplicate key.\n"
    sql += "DROP TEMPORARY TABLE IF EXISTS dc_skill_affix_abort;\n"
    sql += ("CREATE TEMPORARY TABLE dc_skill_affix_abort (reason VARCHAR(190) NOT NULL, "
            "PRIMARY KEY (reason)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n")
    sql += ("INSERT INTO dc_skill_affix_abort (reason)\n"
            f"  SELECT {quote(ABORT_UNRESOLVED)} FROM dc_skill_affix WHERE skill_id = 0\n"
            "  UNION ALL\n"
            f"  SELECT {quote(ABORT_UNRESOLVED)} FROM dc_skill_affix WHERE skill_id = 0;\n")
    sql += "DROP TEMPORARY TABLE IF EXISTS dc_skill_affix_abort;\n"
    return sql


def main():
    all_rows = definitions()
    # The applied renders see only the classes they were applied with.
    rows = [row for row in all_rows if row[3] in APPLIED_CLASS_IDS]

    # items_0004 is APPLIED and FROZEN. Its SHA1 is what the live `updates`
    # table records, and the core re-hashes every update file on start, so
    # rewriting it would make an applied migration look changed. The id columns
    # therefore arrive in a NEW migration; 0004 is never written from here
    # again. A new affix row would likewise need its own new file, not an edit
    # to 0004.
    ids = "-- Generated by generate_skill_affixes.py from D3Planner statGroups and the class catalogue.\n"
    ids += "-- K5: dc_skill_affix resolves an affix to class_id and skill_id (the BASE skill, so\n"
    ids += "-- every rune of it is boosted). skill_name stays as display text, joined on by nothing.\n"
    ids += "--\n"
    ids += "-- items_0004_skill_affixes.sql is applied and frozen; this adds the columns to what it\n"
    ids += "-- created. dc_skill_affix is world data regenerated from source, not saved player data,\n"
    ids += "-- so the recovery from a failure here is to re-import, not to restore a backup.\n"
    ids += "ALTER TABLE dc_skill_affix\n"
    ids += "  ADD COLUMN class_id INT UNSIGNED NOT NULL DEFAULT 0 AFTER affix_id,\n"
    ids += "  ADD COLUMN skill_id INT UNSIGNED NOT NULL DEFAULT 0 AFTER class_id,\n"
    ids += "  ADD KEY idx_dc_skill_affix_skill (class_id, skill_id);\n"
    for _group, _index, affix, class_id, skill_id, _skill, _name in rows:
        ids += (f"UPDATE dc_skill_affix SET class_id={class_id}, skill_id={skill_id} "
                f"WHERE affix_id={quote(affix)};\n")
    ids += "-- Backstop. No stored procedure is available, so a row left unresolved aborts by\n"
    ids += "-- selecting the same message twice into a primary key: one such row is a duplicate-key\n"
    ids += "-- error quoting the message, and none inserts nothing. The message carries no semicolon,\n"
    ids += "-- so splitting this file on semicolons stays safe.\n"
    ids += "DROP TEMPORARY TABLE IF EXISTS dc_skill_affix_abort;\n"
    ids += ("CREATE TEMPORARY TABLE dc_skill_affix_abort (reason VARCHAR(190) NOT NULL, "
            "PRIMARY KEY (reason)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n")
    ids += ("INSERT INTO dc_skill_affix_abort (reason)\n"
            f"  SELECT {quote(ABORT_UNRESOLVED)} FROM dc_skill_affix WHERE skill_id = 0\n"
            "  UNION ALL\n"
            f"  SELECT {quote(ABORT_UNRESOLVED)} FROM dc_skill_affix WHERE skill_id = 0;\n")
    ids += "DROP TEMPORARY TABLE IF EXISTS dc_skill_affix_abort;\n"

    repair = "-- Generated by generate_skill_affixes.py. Resolve incomplete group rolls once.\n"
    repair += "-- Keep item GUID, sequence, value, range, kind and rerolled flag unchanged.\n"
    repair += "-- A stable per-item/sequence hash chooses the missing skill; reruns are no-ops.\n"
    for group in dict.fromkeys(row[0] for row in rows):
        choices = [row[2] for row in rows if row[0] == group]
        repair += ("UPDATE dc_item_affix a JOIN item_instance i ON i.guid=a.item_guid "
                   "JOIN characters c ON c.guid=i.owner_guid SET a.affix_id=ELT(1+MOD(CRC32(CONCAT(a.item_guid,':',a.seq,':skill-repair-v1')),"
                   + str(len(choices)) + ")," + ",".join(map(quote, choices))
                   + ") WHERE c.class=1 AND a.affix_id=" + quote(group) + ";\n")
    for name, database, update, content in (
        ("skill_affix_ids.sql", "db-world", "items_0005_skill_affix_ids.sql", ids),
        ("skill_affix_repair.sql", "db-characters", "items_0005_resolve_skill_affixes.sql", repair),
        ("skill_affix_classes.sql", "db-world", CLASSES_MIGRATION, render_classes(all_rows)),
    ):
        (MODULE / "data/generated" / name).write_text(content, encoding="utf-8", newline="\n")
        write_migration(MODULE, MODULE / "data/sql" / database / "updates" / update, content)
    counts = {}
    for row in all_rows:
        counts[row[3]] = counts.get(row[3], 0) + 1
    print(f"Generated {len(all_rows)} skill affixes ({counts} by class id) in {CLASSES_MIGRATION}; "
          f"items_0004/items_0005 left untouched.")


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
