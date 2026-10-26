"""B1+B2 - one class-keyed catalogue, replacing per-class tables and booleans.

`dc_classes.cpp` held three Barbarian tables and gated on `CLASS_WARRIOR`, and
`dc_loot.cpp` reduced eligibility to a Barbarian/other boolean. Adding a second
class meant a second set of tables and a second branch in every gate.

This emits one catalogue keyed by `class_id`, so a second class is data:

  dc_class_catalogue   class_id, skill_id, rune_id, spell_id, unlock_level,
                       indicator_spell_id
  dc_class_passive     class_id, spell_id, unlock_level
  dc_class_label       spell_id, class_id, skill_name, rune_name, category, element
  dc_class_passive_label  spell_id, passive_name
  dc_class_category    class_id, category, display_order

Identities are not invented. `skill_id` and `rune_id` are the spell ids the
spell rewrite already publishes in generated/spell_shells.csv - the base skill's
id, and the rune's id or 0 on a base row - and `spell_id` is the one a player
actually casts, which is the rune's id when runed and the skill's otherwise.
The brief asks for exactly this in the neighbouring task: the spell ids come
from the spell rewrite's own index, not a second list.

Labels are separate by design. A catalogue row carries no English, so renaming
a skill cannot move a row, and the label tables are what the UI reads.

The skills window (diablocraft-skills-window-class-data) needs two display
facts no other table carried. `element` is on dc_class_label because that is
the UI's table and the element is display data: the rune's colour and label
come from the sheet's `element`, and a skill row carries the skill's own. It is
not on dc_class_catalogue, which C++ reads for gameplay and which carries no
sheet text. `dc_class_category` is D3's fixed per-class order of the skill
categories, from class_skill_categories.csv; the UI joins it on
(class_id, category).
"""
import csv
from pathlib import Path

import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import primary_spells
import barbarian_source  # noqa: E402
from applied_migrations import write_migration
from class_names import item_key, sheet_stem

ROOT = Path(__file__).resolve().parents[3]
GENERATED = ROOT / 'data' / 'generated'
SHELLS = GENERATED / 'spell_shells.csv'
D3 = ROOT / 'data' / 'd3'


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream, strict=True))


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def shell_index():
    """name -> spell id, for the kinds a catalogue is made of.

    'active' is a skill, 'rune' is "Skill - Rune" and 'passive' is a passive.
    Anything else in the file is a marker, a helper or another system's shell
    and has no business in a class catalogue.
    """
    wanted = {'active': {}, 'rune': {}, 'passive': {}}
    for row in read(SHELLS):
        kind = row['kind']
        if kind not in wanted:
            continue
        name, identity = row['name'], int(row['spell_id'])
        if name in wanted[kind]:
            raise ValueError(f'spell_shells.csv: two {kind} shells named {name!r}')
        wanted[kind][name] = identity
    return wanted


def classes():
    """The classes the realm has data for, from class_map.csv's own ids."""
    found = []
    for row in read(D3 / 'class_map.csv'):
        identity = row['class_id'].strip()
        if not identity:
            raise ValueError(f'class_map.csv: {row["d3_class"]!r} has no class_id')
        if not identity.isdigit() or int(identity) < 1:
            raise ValueError(f'class_map.csv: {row["d3_class"]!r} class_id must be a positive '
                             f'whole number, got {identity!r}')
        stem = sheet_stem(row['d3_class'])
        if (D3 / f'{stem}_skills.csv').exists():
            found.append((int(identity), row['d3_class'].strip(), stem))
    if not found:
        raise ValueError('class_map.csv: no class has a <class>_skills.csv')
    if len({identity for identity, _, _ in found}) != len(found):
        raise ValueError('class_map.csv: duplicate class_id')
    return sorted(found)


def element_of(row, what, d3_class):
    value = (row.get('element') or '').strip()
    if not value:
        raise ValueError(f'{d3_class}: {what} has no element; the skills window colours '
                         f'and labels it from this cell')
    return value


def category_orders(class_map):
    """(class_id, category, display_order) for every playable class.

    class_skill_categories.csv holds D3's order for every D3 class. A class not
    in class_map.csv is planned: its rows are checked for shape and published
    nowhere. A playable class must order exactly the categories its skills use,
    each once - a class with generated spells and no order rows is an error.
    """
    by_class = {}
    for line, row in enumerate(read(D3 / 'class_skill_categories.csv'), 2):
        d3_class, category = row['d3_class'].strip(), row['category'].strip()
        order, source = row['display_order'].strip(), row['source'].strip()
        where = f'class_skill_categories.csv:{line}'
        if not d3_class or not category or not source:
            raise ValueError(f'{where}: d3_class, category and source are all required')
        if not order.isdigit() or int(order) < 1:
            raise ValueError(f'{where}: display_order must be a positive whole number, '
                             f'got {order!r}')
        orders = by_class.setdefault(d3_class, {})
        if category in orders:
            raise ValueError(f'{where}: {d3_class} orders {category!r} twice')
        orders[category] = int(order)
    for d3_class, orders in by_class.items():
        if sorted(orders.values()) != list(range(1, len(orders) + 1)):
            raise ValueError(f'class_skill_categories.csv: {d3_class} display_order must be '
                             f'1..{len(orders)} with no gap or repeat, got '
                             f'{sorted(orders.values())!r}')
    out = []
    for row in class_map:
        class_id, d3_class = row[0], row[2]
        stem = sheet_stem(d3_class)
        used = {(skill.get('category') or '').strip()
                for skill in read(D3 / f'{stem}_skills.csv')}
        orders = by_class.get(d3_class)
        if not orders:
            raise ValueError(f'{d3_class} has generated spells but no row in '
                             f'class_skill_categories.csv; the skills window cannot order '
                             f'its categories')
        if used - set(orders):
            raise ValueError(f'{d3_class}: no display order for categories '
                             f'{sorted(used - set(orders))!r} that its skills use')
        if set(orders) - used:
            raise ValueError(f'{d3_class}: class_skill_categories.csv orders '
                             f'{sorted(set(orders) - used)!r}, which no skill of the class uses')
        out += sorted(((class_id, category, order) for category, order in orders.items()),
                      key=lambda entry: entry[2])
    return out


def level(row, column):
    value = (row.get(column) or '').strip()
    if not value:
        return 1
    if not value.isdigit():
        raise ValueError(f'{column}: expected a level, got {value!r}')
    return int(value)


# Worn auras, TRACED ACROSS EXECUTION rather than pattern-matched in one file.
# The first version of this regexed dc_barbarian_primaries.cpp alone and declared two; a
# regex over one file cannot assert that no other skill wears anything, and
# seven more do. Two producers put an aura on the PLAYER:
#
# 1. dc_barbarian_primaries.cpp - the Frenzy stack buff, AddAura(D::FRENZY_BUFF, player)
#    at :220. It is applied whenever the stack counter is non-zero, and that
#    counter belongs to the SKILL, so every Frenzy rune wears it, not just the
#    unruned row. Plus the Vanguard rune's own movement aura at :98,
#    BuffValues::Show(player, D::VANGUARD, stacks, ...) (stacked with Frenzy since
#    diablocraft-b3zj), taken off by the same call with no stacks.
#
# 2. dc_abilities.cpp - Mark(p, p, row) at :497, :510, :547, :567, :574, :596
#    and :670, which adds AuraId(row.id), the ability's own marker aura. `row`
#    is the RUNE's row when runed, so the id is per catalogue entry. Four of
#    the seven are unconditional; three fire only under one named rune.
SELF_MARK_SKILLS = ('Sprint', 'Ignore Pain', 'Battle Rage', 'Wrath of the Berserker')
SELF_MARK_RUNES = (('Overpower', 'Killing Spree'), ('Overpower', 'Crushing Advance'),
                   ('Revenge', 'Best Served Cold'), ('Leap', 'Iron Impact'))

# Architect ruling, 2026-09-22. The column is `indicator_spell_id`: the ONE
# worn aura a player watches for that skill's duration or stacks. Never a set.
# An entry may genuinely put more than one aura on the player - the auras below
# are SIDE auras, real but not what the bar watches - so they are excluded by
# name, with the reason, rather than by a rule this generator invented.
#
# Frenzy: the stack buff is the indicator for the base skill and for EVERY
# rune, Vanguard included. Vanguard's own movement aura is a side effect of the
# rune, not the thing that shows Frenzy is up, so it is not the indicator.
SIDE_AURAS = {('Frenzy', 'Vanguard'): ('VANGUARD',)}


def marker_formula():
    """AuraId's constants, read from the file that owns them."""
    source = barbarian_source.abilities()
    match = re.search(r'constexpr uint32 First = (\d+), Last = (\d+), Marker = (\d+);', source)
    if not match:
        raise ValueError('the Barbarian files: cannot read the AuraId constants')
    if 'return Marker + id - First;' not in source:
        raise ValueError('the Barbarian files: AuraId is no longer Marker + id - First')
    first, last, marker = (int(group) for group in match.groups())
    return first, last, marker


def worn_for(skill_name, rune_name, spell_id, first, last, marker):
    """Every aura this entry puts on the player, as a set of spell ids."""
    worn = set()
    if skill_name == 'Frenzy':
        worn.add(primary_spells.FRENZY_BUFF)
        if rune_name == 'Vanguard':
            worn.add(primary_spells.VANGUARD)
    if skill_name in SELF_MARK_SKILLS or (skill_name, rune_name) in SELF_MARK_RUNES:
        if not first <= spell_id <= last:
            raise ValueError(f'{skill_name}: {spell_id} is outside the ability shell range, '
                             f'so AuraId would not name its marker')
        worn.add(marker + spell_id - first)
    return worn


def indicator_of(skill_name, rune_name, spell_id, first, last, marker, ambiguous):
    """The one aura the bar watches for this entry, or 0 if there is no one
    obvious indicator.

    Per the ruling: declared side auras are excluded, what is left must be a
    single id, and an entry with no single obvious indicator stays empty and is
    logged rather than guessed at.
    """
    worn = worn_for(skill_name, rune_name, spell_id, first, last, marker)
    excluded = set()
    for name in SIDE_AURAS.get((skill_name, rune_name), ()):
        aura = getattr(primary_spells, name)
        if aura not in worn:
            # A declaration that no longer describes the code is a stale claim
            # about execution, and silently ignoring it would hide a real change.
            raise ValueError(f'SIDE_AURAS says {skill_name} - {rune_name} wears {name}, but '
                             f'the traced auras for that entry are {sorted(worn)!r}')
        excluded.add(aura)
    candidates = worn - excluded
    if len(candidates) > 1:
        ambiguous.append((skill_name, rune_name, sorted(candidates)))
        return 0
    return candidates.pop() if candidates else 0


def catalogue():
    """Every castable entry, every passive and their labels, for every class."""
    index = shell_index()
    rows, passives, labels, passive_labels = [], [], [], []
    first, last, marker = marker_formula()
    ambiguous = []
    playable, waiting = [], []
    for entry in classes():
        skills = read(D3 / f'{entry[2]}_skills.csv')
        covered = sum(1 for skill in skills if skill['skill_name'] in index['active'])
        if covered == 0:
            # Reference data for a class whose spells have not been generated
            # yet. The catalogue is class-keyed precisely so this is data: it
            # joins the moment its shells exist. Reported, never silent.
            waiting.append(entry[1])
            continue
        if covered != len(skills):
            raise ValueError(f'{entry[1]}: {covered} of {len(skills)} skills have shells; a '
                             f'partly generated class is an error, not a catalogue')
        playable.append(entry)
    by_name = {row['d3_class'].strip(): row for row in read(D3 / 'class_map.csv')}
    # class_key is the CANONICAL identity and class_of the display label.
    # base_items.csv writes usable_by and designated_class in lower case, and
    # the eligibility predicate compares tokens exactly, so publishing the
    # display form as the key silently changed 202 items' pools. The key is the
    # same lower-case name base_items.csv spells usable_by and designated_class
    # in - one spelling, derived once, never re-derived at a call site. A name of
    # two words has two spellings (demon_hunter for its sheets, demonhunter for
    # the items); the key is the items'.
    class_map = [(class_id, item_key(d3_class), d3_class, int(by_name[d3_class]['wow_class_id']),
                  by_name[d3_class]['wow_class'], by_name[d3_class]['primary_stat'],
                  by_name[d3_class]['wow_power_type'])
                 for class_id, d3_class, stem in playable]
    for class_id, d3_class, stem in playable:
        skills = read(D3 / f'{stem}_skills.csv')
        runes = read(D3 / f'{stem}_runes.csv')
        for skill in skills:
            name = skill['skill_name']
            if name not in index['active']:
                raise ValueError(f'{d3_class}: no active shell for skill {name!r}')
            skill_id = index['active'][name]
            rows.append((class_id, skill_id, 0, skill_id, level(skill, 'unlock_level'),
                         indicator_of(name, '', skill_id, first, last, marker, ambiguous)))
            labels.append((skill_id, class_id, name, '', skill.get('category', ''),
                           element_of(skill, f'skill {name!r}', d3_class)))
        known = {skill['skill_name'] for skill in skills}
        for rune in runes:
            parent = rune['skill_name']
            if parent not in known:
                raise ValueError(f'{d3_class}: rune {rune["rune_name"]!r} has no skill {parent!r}')
            name = f'{parent} - {rune["rune_name"]}'
            if name not in index['rune']:
                raise ValueError(f'{d3_class}: no rune shell for {name!r}')
            rune_id = index['rune'][name]
            rows.append((class_id, index['active'][parent], rune_id, rune_id,
                         level(rune, 'unlock_level'),
                         indicator_of(parent, rune['rune_name'], rune_id, first, last,
                                      marker, ambiguous)))
            labels.append((rune_id, class_id, parent, rune['rune_name'], '',
                           element_of(rune, f'rune {name!r}', d3_class)))
        for passive in read(D3 / f'{stem}_passives.csv'):
            name = passive['passive_name']
            if name not in index['passive']:
                raise ValueError(f'{d3_class}: no passive shell for {name!r}')
            passive_id = index['passive'][name]
            passives.append((class_id, passive_id, level(passive, 'unlock_level')))
            passive_labels.append((passive_id, name))
    stale = [entry for entry in SIDE_AURAS
             if entry not in {(label[2], label[3]) for label in labels}]
    if stale:
        raise ValueError(f'SIDE_AURAS names entries that are not in the catalogue: '
                         f'{sorted(stale)!r}')
    if not playable:
        raise ValueError('no class has generated spell shells; the catalogue would be empty')
    for row in class_map:
        if row[1] != row[1].lower() or not row[1]:
            raise ValueError(f'class_key {row[1]!r} is not the canonical lower-case form; '
                             f'base_items.csv tokens are lower case and the eligibility '
                             f'predicate compares them exactly')
    return (rows, passives, labels, passive_labels, class_map,
            [name for _, name, _ in playable], waiting, ambiguous)


def render(rows, passives, labels, passive_labels, class_map, categories):
    lines = [
        '-- Generated by generate_class_catalogue.py from class_map.csv, the per-class',
        '-- skill/rune/passive sheets and generated/spell_shells.csv. Edit those and rerun.',
        '-- Apply to the world database. Labels live in their own tables: a catalogue',
        '-- row carries no English, so renaming a skill cannot move a row.',
        'SET NAMES utf8mb4;',
        'DROP TABLE IF EXISTS `dc_class_catalogue`;',
        'CREATE TABLE `dc_class_catalogue` (',
        '  `class_id` INT UNSIGNED NOT NULL,',
        '  `skill_id` INT UNSIGNED NOT NULL,',
        '  `rune_id` INT UNSIGNED NOT NULL,',
        '  `spell_id` INT UNSIGNED NOT NULL,',
        '  `unlock_level` INT UNSIGNED NOT NULL,',
        '  `indicator_spell_id` INT UNSIGNED NOT NULL,',
        '  PRIMARY KEY (`class_id`, `spell_id`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
    ]
    for offset in range(0, len(rows), 100):
        lines.append('INSERT INTO `dc_class_catalogue` (`class_id`, `skill_id`, `rune_id`, '
                     '`spell_id`, `unlock_level`, `indicator_spell_id`) VALUES')
        lines.append(',\n'.join('(' + ', '.join(str(field) for field in row) + ')'
                                for row in rows[offset:offset + 100]) + ';')

    lines += [
        'DROP TABLE IF EXISTS `dc_class_passive`;',
        'CREATE TABLE `dc_class_passive` (',
        '  `class_id` INT UNSIGNED NOT NULL,',
        '  `spell_id` INT UNSIGNED NOT NULL,',
        '  `unlock_level` INT UNSIGNED NOT NULL,',
        '  PRIMARY KEY (`class_id`, `spell_id`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_class_passive` (`class_id`, `spell_id`, `unlock_level`) VALUES',
        ',\n'.join('(' + ', '.join(str(field) for field in row) + ')' for row in passives) + ';',
        'DROP TABLE IF EXISTS `dc_class_label`;',
        'CREATE TABLE `dc_class_label` (',
        '  `spell_id` INT UNSIGNED NOT NULL,',
        '  `class_id` INT UNSIGNED NOT NULL,',
        '  `skill_name` VARCHAR(128) NOT NULL,',
        '  `rune_name` VARCHAR(128) NOT NULL,',
        '  `category` VARCHAR(64) NOT NULL,',
        '  -- The sheet\'s element: the rune\'s on a rune row, the skill\'s own on a skill row.',
        '  `element` VARCHAR(32) NOT NULL,',
        '  PRIMARY KEY (`spell_id`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
    ]
    for offset in range(0, len(labels), 100):
        lines.append('INSERT INTO `dc_class_label` (`spell_id`, `class_id`, `skill_name`, '
                     '`rune_name`, `category`, `element`) VALUES')
        lines.append(',\n'.join(
            f'({row[0]}, {row[1]}, ' + ', '.join(quote(field) for field in row[2:]) + ')'
            for row in labels[offset:offset + 100]) + ';')

    lines += [
        '-- Only classes whose spells are generated are listed. A class with',
        '-- reference sheets but no shells is deliberately absent, so nothing',
        '-- treats it as playable and no second-class policy is invented here.',
        'DROP TABLE IF EXISTS `dc_class_map`;',
        'CREATE TABLE `dc_class_map` (',
        '  `class_id` INT UNSIGNED NOT NULL,',
        '  -- The canonical key: what usable_by and designated_class are written in.',
        '  `class_key` VARCHAR(64) NOT NULL,',
        '  -- Display only. Never compared against sheet data.',
        '  `d3_class` VARCHAR(64) NOT NULL,',
        '  `wow_class_id` INT UNSIGNED NOT NULL,',
        '  `wow_class` VARCHAR(64) NOT NULL,',
        '  `primary_stat` VARCHAR(64) NOT NULL,',
        '  `power_type` VARCHAR(64) NOT NULL,',
        '  PRIMARY KEY (`class_id`),',
        '  UNIQUE KEY `wow_class_id` (`wow_class_id`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_class_map` (`class_id`, `class_key`, `d3_class`, `wow_class_id`, '
        '`wow_class`, `primary_stat`, `power_type`) VALUES',
        ',\n'.join(f'({row[0]}, {quote(row[1])}, {quote(row[2])}, {row[3]}, {quote(row[4])}, '
                   f'{quote(row[5])}, {quote(row[6])})' for row in class_map) + ';',
        'DROP TABLE IF EXISTS `dc_class_passive_label`;',
        'CREATE TABLE `dc_class_passive_label` (',
        '  `spell_id` INT UNSIGNED NOT NULL,',
        '  `passive_name` VARCHAR(128) NOT NULL,',
        '  PRIMARY KEY (`spell_id`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_class_passive_label` (`spell_id`, `passive_name`) VALUES',
        ',\n'.join(f'({row[0]}, {quote(row[1])})' for row in passive_labels) + ';',
        '-- D3\'s fixed order of each class\'s skill categories, 1 first. Joined to',
        '-- dc_class_label on (class_id, category).',
        'DROP TABLE IF EXISTS `dc_class_category`;',
        'CREATE TABLE `dc_class_category` (',
        '  `class_id` INT UNSIGNED NOT NULL,',
        '  `category` VARCHAR(64) NOT NULL,',
        '  `display_order` INT UNSIGNED NOT NULL,',
        '  PRIMARY KEY (`class_id`, `category`),',
        '  UNIQUE KEY `class_order` (`class_id`, `display_order`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;',
        'INSERT INTO `dc_class_category` (`class_id`, `category`, `display_order`) VALUES',
        ',\n'.join(f'({row[0]}, {quote(row[1])}, {row[2]})' for row in categories) + ';',
    ]
    return '\n'.join(lines) + '\n'


# The migration the catalogue publishes. world_0014 was applied on 2026-09-22
# with the Barbarian alone (docs/deploy-release-20260922.md), and an applied
# migration is never rewritten: the Wizard's rows arrive in world_0015, which
# rebuilds the same tables from the same generator (diablocraft-wizard-records).
# world_0014 stays byte for byte what was applied. world_0018 carries the
# Wizard's power_type moved from Mana to Energy (diablocraft-resource-rollout-a
# item 4, Q1=1A); world_0015 stays as applied. world_0018 was applied on
# 2026-09-26 (data/sql/applied_migrations.csv), so dc_class_label.element and
# dc_class_category arrive in world_0022 (diablocraft-skills-window-class-data). The Monk's rows
# (diablocraft-3mk78, Monk 2.2) arrive in world_0050; world_0022 stays as applied. The Necromancer's
# (diablocraft-im7mr.5) arrive in world_0062; world_0050 stays as it went to dev. The Crusader's
# (diablocraft-qulab) arrive in world_0068; world_0062 stays as it went to dev. The Demon Hunter's
# (diablocraft-vawmy.3) arrive in world_0074; world_0068 stays as it went to dev. The Witch Doctor's
# (diablocraft-vxrcu.5) arrive in world_0080; world_0074 stays as it went to dev. The Shaman's
# (diablocraft-xnrvn.6) arrive in world_0087; world_0080 stays as it went to dev.
MIGRATION = 'world_0089_class_catalogue.sql'
APPLIED_MIGRATIONS = ('world_0014_class_catalogue.sql', 'world_0015_class_catalogue.sql',
                      'world_0018_class_catalogue.sql', 'world_0022_class_catalogue.sql',
                      'world_0050_class_catalogue.sql', 'world_0062_class_catalogue.sql',
                      'world_0068_class_catalogue.sql', 'world_0074_class_catalogue.sql',
                      'world_0080_class_catalogue.sql')


def generate(root=ROOT):
    rows, passives, labels, passive_labels, class_map, playable, waiting, ambiguous = \
        catalogue()
    categories = category_orders(class_map)
    sql = render(rows, passives, labels, passive_labels, class_map, categories)
    (root / 'data/generated/class_catalogue.sql').write_bytes(sql.encode('utf-8'))
    write_migration(root, root / 'data/sql/db-world/updates' / MIGRATION, sql)
    print(f'Class catalogue: {len(rows)} castable entries, {len(passives)} passives, '
          f'{sum(1 for row in rows if row[5])} indicator auras, {len(categories)} category '
          f'orders, for {", ".join(playable)}.')
    for (skill_name, rune_name), names in SIDE_AURAS.items():
        print(f'  side aura excluded: {skill_name} - {rune_name} also wears '
              f'{" and ".join(names)}, which is not what the bar watches for that skill.')
    for skill_name, rune_name, candidates in ambiguous:
        # The ruling: no single obvious indicator means an empty cell and an
        # explanation, never a guess.
        print(f'  NO INDICATOR: {skill_name}{" - " + rune_name if rune_name else ""} wears '
              f'{candidates!r} and none of them is declared a side aura, so no single one is '
              f'the indicator; the cell is empty.')
    if waiting:
        print(f'  reference only, no generated shells yet: {", ".join(waiting)}')
    return rows, passives, labels, passive_labels


if __name__ == '__main__':
    import argparse
    argparse.ArgumentParser(description=__doc__).parse_args()
    generate()
