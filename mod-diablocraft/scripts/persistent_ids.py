"""Project-owned, append-only content identities (not D3 reference numbers).

The three data/*.csv maps were seeded once from a9df081's derived identities.
Never allocate an ID from row order again. Existing migration rows are only
compatibility checks, never an allocation source; applied history is read-only.
Native item_template entries and dc_tier_phase retain their existing IDs.
"""
import csv
import re


def _mapping(module, name, keys, id_column):
    path = module / 'data' / name
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != [*keys, id_column]:
            raise ValueError(f'{name}: expected columns {[*keys, id_column]}')
        rows = list(reader)
    if not rows:
        raise ValueError(f'{name}: missing IDs')
    result, used = {}, set()
    for row in rows:
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError(f'{name}: missing key or ID: {row!r}')
        key = tuple(row[k] for k in keys)
        raw = row[id_column]
        if not re.fullmatch(r'[1-9][0-9]*', raw):
            raise ValueError(f'{name}: invalid {id_column}: {raw!r}')
        identity = int(raw)
        if key in result or identity in used:
            raise ValueError(f'{name}: duplicate key or ID: {row!r}')
        result[key] = identity
        used.add(identity)
    return result


def _require(mapping, keys, name):
    missing = set(keys) - mapping.keys()
    if missing:
        raise ValueError(f'{name}: missing IDs for {sorted(missing)!r}')


def _preserve(mapping, key, identity, name):
    if mapping.get(key) != int(identity):
        raise ValueError(f'{name}: append-only identity changed or missing: {key!r} = {identity}')


def gem_items(module, gems):
    mapping = _mapping(module, 'gem_items.csv', ['gem_id', 'tier'], 'item_entry')
    definitions, colours = {}, {}
    for row in gems:
        if row['is_legendary'] != '0':
            continue
        key = row['gem_id'], row['tier']
        value = row['gem_name'], row['colour']
        colour_key = row['colour'], row['tier']
        if key in definitions and definitions[key] != value:
            raise ValueError(f'Conflicting gem identity metadata: {key!r}')
        if colour_key in colours and colours[colour_key] != key:
            raise ValueError(f'Ambiguous gem colour/tier: {colour_key!r}')
        definitions[key] = value
        colours[colour_key] = key
    _require(mapping, definitions, 'gem_items.csv')
    for path in (module / 'data/sql/db-world/updates').glob('crafting_*.sql'):
        for identity, gem, tier in re.findall(
                r"INSERT INTO `dc_gem_item` VALUES \((\d+),'([^']+)','([^']+)'", path.read_text()):
            _preserve(mapping, (gem, tier), identity, 'gem_items.csv')
    return mapping


def blacksmith_recipes(module, recipes):
    mapping = _mapping(module, 'blacksmith_recipe_ids.csv', ['slot'], 'recipe_id')
    _require(mapping, ((row['slot'],) for row in recipes if row['row_type'] == 'recipe'),
             'blacksmith_recipe_ids.csv')
    for path in (module / 'data/sql/db-world/updates').glob('crafting_*.sql'):
        for identity, slot in re.findall(
                r"INSERT INTO `dc_blacksmith_recipe` VALUES \((\d+),'([^']+)'", path.read_text()):
            _preserve(mapping, (slot,), identity, 'blacksmith_recipe_ids.csv')
    return {key[0]: identity for key, identity in mapping.items()}


def difficulty_tiers(module, tiers):
    mapping = _mapping(module, 'difficulty_ids.csv', ['tier'], 'tier_id')
    names = [row['tier'] for row in tiers]
    if len(names) != len(set(names)):
        raise ValueError('difficulty_tiers.csv: duplicate tier name')
    for name, in mapping:
        if name not in names:
            raise ValueError(f'difficulty_ids.csv: unknown tier {name!r}')
    # This immutable launch migration is the existing runtime phase contract.
    # Do not generate or rewrite it as part of an identity-sheet change.
    path = module / 'data/sql/db-world/updates/difficulty_0001_tier_phase.sql'
    for identity, phase, name in re.findall(r"\((\d+),(\d+),'([^']+)'\)", path.read_text()):
        _preserve(mapping, (name,), identity, 'difficulty_ids.csv')
    _require(mapping, [('Normal',), ('Master',)], 'difficulty_ids.csv')
    return {key[0]: identity for key, identity in mapping.items()}
