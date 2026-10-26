# Constant (audit 115, 100000): Native item namespace cutoff for durability donors; Content namespace boundary.
# Constant (audit 121, 0): Gem template no-bind policy; Native binding enum; gameplay policy deserves a named constant.
# Constant (audit 124, 102001): Reusable Parts material ID; Stable content identity; repeated in recipe/salvage mapping.
# Constant (audit 125, 102002): Arcane Dust material ID; Stable content identity; repeated in recipe/salvage mapping.
# Constant (audit 126, 102003): Veiled Crystal material ID; Stable content identity; repeated in recipe/salvage mapping.
# Constant (audit 127, 102004): Forgotten Soul material ID; Stable content identity; repeated in recipe/salvage mapping.
# Constant (audit 128, 102000): Death's Breath material ID; Stable content identity; repeated in recipe/salvage mapping.
# Constant (audit 129, 3577): Gold Bar display donor; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 130, 39900): Ruby display donor; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 131, 36932): Emerald display donor; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 132, 36929): Topaz display donor; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 133, 36926): Amethyst display donor; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 134, 42225): Diamond display donor; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 135, 102006): Gold Bar output item; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 136, 910000): Blacksmith repair NPC; Template identity; appearance choice can move with its owning CSV.
# Constant (audit 137, 910001): Mystic repair NPC; Template identity; appearance choice can move with its owning CSV.
"""Generate launch artisan data and extract affix display order; stdlib only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import reserved_number, write_coupled_outputs, write_migration
from tunable_values import integer as tunable_integer
from persistent_ids import gem_items, blacksmith_recipes
from text_guard import refuse_unfilled
import csv
import io
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
DATA = MODULE / 'data/d3'
MYSTIC_COLUMNS = ['rarity', 'slot', 'payment_kind', 'material_1_entry', 'material_2_entry', 'material_count',
                  'gem_tier', 'gem_count_rule', 'source']
TIERS = ['Normal', 'Flawless', 'Square', 'Flawless Square', 'Star', 'Marquise',
         'Imperial', 'Flawless Imperial', 'Royal', 'Flawless Royal']


# Phase 2 (Architect, 2026-09-19): loot_tuning.csv is the designer's numbers, not
# D3's published reference data, so the FILE moved to data/tunables/ and out
# of data/d3/. Its runtime home is unchanged - still dc_loot_tuning, not
# dc_tunables. data/tunables/README.md lists it under "Files with their own
# table".
TUNABLES = MODULE / 'data/tunables'


def read(name, folder=None):
    with ((folder or DATA) / name).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, strict=True)
        result = list(reader)
        for n, row in enumerate(result, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'{name}:{n}: malformed row {row!r}')
        return result


def number(row, key):
    try:
        value = int(row[key])
        if value < 0: raise ValueError()
        return value
    except (KeyError, ValueError) as error:
        raise ValueError(f'Invalid {key}: {row!r}') from error


def quote(value):
    if isinstance(value, (int, float)): return str(value)
    return "'" + str(value).replace('\\', '\\\\').replace("'", "''") + "'"


def ensure_column(table_name, name, definition):
    # The regular generator creates these columns on fresh installs. This
    # migration also upgrades existing installations without duplicate ALTERs.
    return [f"SET @dc_column_exists=(SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name={quote(table_name)} AND column_name={quote(name)});",
            f"SET @dc_ddl=IF(@dc_column_exists=0,{quote('ALTER TABLE '+table_name+' ADD COLUMN '+name+' '+definition)},'DO 0');",
            'PREPARE dc_artisan_ddl FROM @dc_ddl;', 'EXECUTE dc_artisan_ddl;', 'DEALLOCATE PREPARE dc_artisan_ddl;']


def table(name, columns, rows):
    return [f'DROP TABLE IF EXISTS `{name}`;', f'CREATE TABLE `{name}` ({columns}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;'] + [
        f'INSERT INTO `{name}` VALUES (' + ','.join(map(quote, row)) + ');' for row in rows]


def display_orders():
    # slots.js uses two-space slot declarations, four-space affix objects, and
    # six-space affix declarations. Keep first occurrence of duplicate keys.
    text = (ROOT / 'reference/d3planner/slots.js').read_text(encoding='utf-8')
    out = {}
    for match in re.finditer(r'^  (\w+): \{\n(.*?)(?=^  \},)', text, re.M | re.S):
        affixes = re.search(r'^    affixes: \{\n(.*?)^    \}', match[2], re.M | re.S)
        if affixes:
            out[match[1]] = {key: n for n, key in enumerate(dict.fromkeys(
                re.findall(r'^      (\w+):', affixes[1], re.M)), 1)}
    if not out: raise ValueError('No slot affix lists found in slots.js')
    return out


def apply_display_orders(pools, orders):
    preserved = 0
    for row in pools:
        try:
            row['display_order'] = str(orders[row['slot']][row['affix_id']])
        except KeyError as error:
            # Shield required base stats use slots.js required/baseblockShield, not ordinary offhand affixes.
            if not row.get('display_order', '').strip():
                raise ValueError(f'No slots.js or existing CSV display order: {row!r}') from error
            preserved += 1
    return preserved


def approved_designation_delta(before, after):
    """Return only the three approved #67 updates when nothing else changed."""
    approved = {'P66_Unique_Mojo_002': 'witchdoctor',
                'P43_Unique_Fist_003_x1': 'monk',
                'P71_Unique_Fist_003': 'monk'}
    if len(before) != len(after):
        return None
    changed = []
    seen = set()
    for old, new in zip(before, after):
        if old == new:
            continue
        for d3_id, designation in approved.items():
            if (d3_id not in seen and
                    old.startswith('UPDATE dc_base_item SET pool_version=') and
                    old.endswith(f" WHERE d3_id='{d3_id}';") and
                    old.count("designated_class=''") == 1 and
                    new == old.replace("designated_class=''",
                                       f"designated_class='{designation}'")):
                changed.append(new)
                seen.add(d3_id)
                break
        else:
            return None
    return changed if seen == set(approved) else None


def write_generated(sql, snapshot, legacy, database='world'):
    """Refresh snapshots; keep applied migrations and emit the next numbered delta."""
    (MODULE / 'data/generated' / snapshot).write_text(sql, encoding='utf-8', newline='\n')
    updates = MODULE / f'data/sql/db-{database}/updates'
    baseline = updates / legacy
    if not baseline.exists():
        write_migration(MODULE, baseline, sql)
        return
    def statements(text):
        return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith('--')]
    suffix = Path(snapshot).stem
    previous = sorted(updates.glob(f'crafting_*_{suffix}_tunables.sql'),
                      key=lambda path: int(path.name.split('_')[1]))
    latest = previous[-1] if previous else baseline
    rendered = statements(sql)
    latest_statements = statements(latest.read_text())
    # #67 changes only three keyed designations. Compare against the applied
    # full render, then compare the resulting delta against the newest file so
    # a second generation does not mistake its own small migration for a stale
    # full render and emit the same change forever.
    published = updates / 'crafting_0003_crafting_tunables.sql'
    if database == 'world' and snapshot == 'crafting.sql' and published.is_file():
        delta = approved_designation_delta(statements(published.read_text()), rendered)
        if delta is not None:
            if latest_statements == delta:
                return
            delta_sql = '\n'.join(delta) + '\n'
            if latest != published and latest_statements == rendered:
                # Replace an earlier, unlisted full-render attempt in place.
                # write_migration still protects it if it became applied.
                write_migration(MODULE, latest, delta_sql)
                return
            sql = delta_sql
        elif latest_statements == rendered:
            return
    elif latest_statements == rendered:
        return
    numbers = [int(match[1]) for path in updates.glob('crafting_*.sql')
               if (match := re.match(r'crafting_(\d+)_', path.name))]
    next_number = max(numbers + [reserved_number(MODULE, 'crafting')]) + 1
    write_migration(MODULE, updates / f'crafting_{next_number:04d}_{suffix}_tunables.sql', sql)


def artisan_rule_rows():
    """No class gate: these content rules apply to every living crafter."""
    def matrix(name, columns):
        with (DATA / name).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != columns:
                raise ValueError(f'Unexpected {name} columns (class columns are not allowed)')
            rows = list(reader)
        if not rows or any(None in row or any(value is None for value in row.values()) or not row['source'] for row in rows):
            raise ValueError(f'Empty or malformed matrix: {name}')
        return rows
    blacksmith = matrix('blacksmith_rules.csv', ['recipe_slot', 'base_slot', 'base_rarity', 'output_rarity', 'source'])
    mystic = matrix('mystic_rules.csv', MYSTIC_COLUMNS)
    recipe_slots = {r['slot'] for r in read('blacksmith_recipes.csv') if r['row_type'] == 'recipe'}
    bases = {(r['slot'], r['rarity']) for r in read('base_items.csv') if r['pool_version'] == 'yes'}
    rarity_ids = {r['rarity'].split(' (', 1)[0].lower() for r in read('rarity_tiers.csv')}
    seen, output_rarities = set(), {}
    for row in blacksmith:
        key = row['recipe_slot'], row['base_slot']
        if key in seen or row['recipe_slot'] not in recipe_slots or (row['base_slot'], row['base_rarity']) not in bases or row['output_rarity'] not in rarity_ids:
            raise ValueError(f'Invalid/duplicate Blacksmith rule: {row}')
        seen.add(key)
        previous = output_rarities.setdefault(row['recipe_slot'], row['output_rarity'])
        if previous != row['output_rarity']:
            raise ValueError('A recipe slot has conflicting output rarities')
    materials = {number(r, 'item_entry') for r in read('account_economy.csv') if r['kind'] == 'material'}
    gem_tiers = {r['tier'] for r in read('gems.csv') if r['is_legendary'] == '0'}
    slots = {slot for slot, _ in bases}
    from generate_numeric_data import CELLS
    seen = set()
    for row in mystic:
        key = row['rarity'], row['slot']
        if key in seen or row['rarity'] not in rarity_ids or row['slot'] not in slots | {'*'}:
            raise ValueError(f'Invalid/duplicate Mystic rule: {row}')
        seen.add(key)
        if row['payment_kind'] == 'gold':
            # diablocraft-xw2m: the materials and their count are D3's own (mystic-enchant.md 10.2), one row each.
            ids = [number(row, key) for key in ('material_1_entry', 'material_2_entry')]
            if len(set(ids)) != len(ids) or not all(entry in materials for entry in ids):
                raise ValueError('Mystic materials must be distinct account material identities')
            if number(row, 'material_count') < 1:
                raise ValueError(f'Mystic material count must be positive: {row}')
            if row['gem_tier'] or row['gem_count_rule']:
                raise ValueError('Gold payment cannot carry a gem requirement')
        elif row['payment_kind'] == 'gem':
            # A legendary or set ring or amulet pays one gem and nothing else.
            if row['material_1_entry'] or row['material_2_entry'] or row['material_count']:
                raise ValueError(f'Gem payment cannot carry materials: {row}')
            if row['gem_tier'] not in gem_tiers or row['gem_count_rule'] not in CELLS:
                raise ValueError('Gem payment needs an existing tier and sourced count rule')
            file, key, identity, column = CELLS[row['gem_count_rule']]
            matches = [r for r in read(file + '.csv') if r[key] == identity]
            if len(matches) != 1:
                raise ValueError('Sourced gem count must identify exactly one cell')
            value = float(matches[0][column])
            if not math.isfinite(value) or value <= 0 or value != int(value):
                raise ValueError('Gem count must be a positive sourced integer')
        else:
            raise ValueError('Unknown Mystic payment kind')
    for rarity in {r['rarity'] for r in mystic}:
        if (rarity, '*') not in seen:
            raise ValueError('Mystic rarity requires an explicit fallback slot rule')
    return blacksmith, mystic


def render_artisan_rules():
    blacksmith, mystic = artisan_rule_rows()
    sql = ['-- Generated from blacksmith_rules.csv and mystic_rules.csv by generate_crafting.py --artisan-rules.',
           '-- No class eligibility gate: class is an input to the item roll only.', 'SET NAMES utf8mb4;']
    sql += table('dc_blacksmith_rule',
                 'recipe_slot VARCHAR(20) NOT NULL,base_slot VARCHAR(20) NOT NULL,base_rarity VARCHAR(20) NOT NULL,output_rarity VARCHAR(20) NOT NULL,PRIMARY KEY(recipe_slot,base_slot)',
                 [tuple(r[k] for k in ('recipe_slot', 'base_slot', 'base_rarity', 'output_rarity')) for r in blacksmith])
    sql += mystic_table_sql(mystic)
    return '\n'.join(sql) + '\n'


def mystic_table_sql(mystic):
    """dc_mystic_rule (diablocraft-xw2m): the payment and the materials, one row per rarity and slot.
    A gem row carries no materials, so its entries and count are 0."""
    return table('dc_mystic_rule',
                 'rarity VARCHAR(20) NOT NULL,slot VARCHAR(20) NOT NULL,payment_kind VARCHAR(8) NOT NULL,material_1_entry INT UNSIGNED NOT NULL,material_2_entry INT UNSIGNED NOT NULL,material_count INT UNSIGNED NOT NULL,gem_tier VARCHAR(40) NOT NULL,gem_count_rule VARCHAR(80) NOT NULL,PRIMARY KEY(rarity,slot)',
                 [tuple(int(r[k] or 0) if k in ('material_1_entry', 'material_2_entry', 'material_count') else r[k]
                        for k in MYSTIC_COLUMNS[:-1]) for r in mystic])


def mystic_scalar_rows():
    """D3's enchant price table (x1_EnchantItemAffixUseCountCostScalars) as (roll, scalar x10).
    Strictly increasing rolls from 1 and a scalar that never falls, or the price between two
    breakpoints would not be a straight line up."""
    rows = read('mystic_cost_scalars.csv')
    if not rows or list(rows[0]) != ['use_count', 'scalar_tenths', 'source'] or not all(r['source'] for r in rows):
        raise ValueError('Unexpected mystic_cost_scalars.csv')
    out = [(number(r, 'use_count'), number(r, 'scalar_tenths')) for r in rows]
    if len(out) < 2 or out[0][0] != 1 or any(b[0] <= a[0] or b[1] < a[1] for a, b in zip(out, out[1:])) or out[0][1] < 1:
        raise ValueError('Mystic price table must start at roll 1 and rise')
    return out


def render_mystic_rules():
    _, mystic = artisan_rule_rows()
    sql = ['-- Generated from mystic_rules.csv and mystic_cost_scalars.csv by generate_crafting.py --mystic-rules.',
           '-- diablocraft-xw2m: the Mystic rebuilt the D3 way; the price is mystic_base_gold times the scalar for the roll.',
           'SET NAMES utf8mb4;']
    sql += mystic_table_sql(mystic)
    sql += table('dc_mystic_scalar', 'use_count INT UNSIGNED NOT NULL,scalar_tenths INT UNSIGNED NOT NULL,PRIMARY KEY(use_count)',
                 mystic_scalar_rows())
    return '\n'.join(sql) + '\n'


def generate_artisan_rules(sql=None):
    sql = render_artisan_rules() if sql is None else sql
    migration = MODULE / 'data/sql/db-world/updates/crafting_0004_class_artisans.sql'
    # The mirror follows its migration: once 0004 is applied a changed render ships as a new migration
    # (the Mystic's is crafting_0008), and the mirror stays what 0004 holds.
    if write_coupled_outputs(MODULE, migration, sql, [(MODULE / 'data/generated/class_artisans.sql', sql)],
                             label='class_artisans.sql'):
        write_migration(MODULE, migration, sql)


def generate_mystic_rules(sql=None):
    sql = render_mystic_rules() if sql is None else sql
    migration = MODULE / 'data/sql/db-world/updates/crafting_0008_mystic_rules.sql'
    if write_coupled_outputs(MODULE, migration, sql, [(MODULE / 'data/generated/mystic_rules.sql', sql)],
                             label='mystic_rules.sql'):
        write_migration(MODULE, migration, sql)


def salvage_rows():
    """Account-material adapter for the existing native disenchant-style row shape.

    Numeric source cells own quantities; rarity_tiers.salvage_result is display
    text only. The launch rarity IDs match the existing dc_item_instance enum; the quality IDs are
    its quality_tier values.
    """
    rows = read('salvage_rules.csv')
    columns = ['rarity_id', 'crafted', 'quality_id', 'material_entry', 'min_count', 'max_count', 'source_rarity']
    if not rows or list(rows[0]) != columns:
        raise ValueError('salvage_rules.csv: missing rows or unexpected columns')
    materials = {number(r, 'item_entry') for r in read('account_economy.csv') if r['kind'] == 'material'}
    sources = {r['rarity'] for r in read('rarity_tiers.csv')}
    rarities = {'normal', 'magic', 'rare', 'set', 'legendary'}
    qualities = {'normal', 'ancient', 'primal'}
    seen, result, contexts = set(), [], set()
    for row in rows:
        rarity = row['rarity_id']
        quality = row['quality_id']
        crafted, entry, low, high = (number(row, key) for key in
                                   ('crafted', 'material_entry', 'min_count', 'max_count'))
        if (rarity not in rarities or crafted not in (0, 1) or quality not in qualities or entry not in materials
                or low <= 0 or high < low or row['source_rarity'] not in sources):
            raise ValueError(f'Invalid salvage rule: {row!r}')
        key = rarity, crafted, quality, entry
        if key in seen:
            raise ValueError(f'Duplicate salvage rule: {key!r}')
        seen.add(key)
        contexts.add((rarity, crafted, quality))
        result.append((*key, low, high))
    # Only a non-crafted Legendary or Set item has an Ancient or Primal form (kanais-cube.md 6.3).
    launch = {(rarity, crafted, 'normal') for rarity in rarities for crafted in (0, 1)}
    launch |= {(rarity, 0, quality) for rarity in ('set', 'legendary') for quality in ('ancient', 'primal')}
    if contexts != launch:
        raise ValueError('Missing launch salvage rarity/crafted context')
    return result


def item_tooltip_rows(reference):
    """d3_id -> (d3_id, set_id, power_text, flavour), one row per reference item.
    generate_sql.py reads the same rows for item_template.description, so the
    two never disagree about what a power says."""
    metadata=[]
    for item in reference['items']:
        custom=item.get('required',{}).get('custom',{})
        power=custom.get('format','').replace('%%','%')
        if custom.get('min') is not None:
            value=str(custom['min']) if custom.get('max',custom['min'])==custom['min'] else f"{custom['min']}–{custom['max']}"
            power=re.sub(r'%(?:\{\d+\})?[.0-9]*[df]',value,power) # %d, %.1f and the planner's %{0}d
        flavour=item.get('flavor','')
        # dc_item_tooltip is drawn verbatim by the addon: a token the fill missed must stop the build.
        refuse_unfilled(f"the tooltip of {item['id']}", power, flavour)
        metadata.append((item['id'],item.get('set',''),power,flavour))
    # Some reference IDs have aliases/versions; require a single stable ID row.
    return {r[0]:r for r in metadata}


def generate():
    artisan_sql = render_artisan_rules()
    blacksmith_rules, _ = artisan_rule_rows()
    output_rarities = {r['recipe_slot']: r['output_rarity'] for r in blacksmith_rules}
    reference = json.loads((ROOT / 'reference/d3planner/data.json').read_text(encoding='utf-8'))
    pools = read('affix_pools.csv')
    orders = display_orders()
    preserved_orders = apply_display_orders(pools, orders)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(pools[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(pools)

    gems = read('gems.csv')
    gem_entries = gem_items(MODULE, gems)
    definitions = sorted({(r['gem_id'], r['gem_name'], r['colour'], r['tier'])
                          for r in gems if r['is_legendary'] == '0'},
                         key=lambda row: gem_entries[row[0], row[3]])
    gem_rows, effects = [], []
    for gem, name, colour, tier in definitions:
        if tier not in TIERS: raise ValueError(f'Unknown gem tier: {(gem, tier)!r}')
        gem_rows.append((gem_entries[(gem, tier)], gem, tier, TIERS.index(tier)+1, f'{tier} {name}', colour))
    for r in gems:
        if r['is_legendary'] == '1': continue # no effects until legendary gem powers ship
        try: value = float(r['effect_value'])
        except ValueError as error: raise ValueError(f'Invalid gem effect: {r!r}') from error
        effects.append((gem_entries[(r['gem_id'], r['tier'])], r['slot_class'], r['effect_stat'], value))

    recipes, costs, seen = [], [], {}
    source_recipes = [row for row in read('blacksmith_recipes.csv') if row['row_type'] != 'training']
    recipe_ids = blacksmith_recipes(MODULE, source_recipes)
    for row in sorted(source_recipes, key=lambda row: recipe_ids[row['slot']]):
        if row['row_type'] != 'recipe' or number(row, 'level') <= 0:
            raise ValueError(f'Unexpected launch recipe: {row!r}')
        slot = row['slot']
        amounts = tuple(number(row, key) for key in ['gold','reusable_parts','arcane_dust','veiled_crystals','deaths_breath'])
        if slot in seen:
            if slot != 'mainhand' or seen[slot] != (number(row, 'level'), amounts):
                raise ValueError(f'Conflicting duplicate recipe: {row!r}')
            continue # the two documented weapon examples share one slot recipe/cost
        seen[slot] = (number(row, 'level'), amounts)
        recipe = recipe_ids[slot] # Explicit IDs retain the reserved jewelry slots.
        if slot not in output_rarities:
            continue # The shared recipe list is the explicit Blacksmith matrix.
        recipes.append((recipe, slot, f"Level {number(row, 'level')} " + ('Weapon' if slot == 'mainhand' else row['recipe_name']), number(row, 'level'), amounts[0], output_rarities[slot]))
        for entry, count in zip([102001,102002,102003,102000], amounts[1:]):
            if count: costs.append((recipe, entry, count))
    expected_slots = set(output_rarities)
    if not recipes or {r[1] for r in recipes} != expected_slots:
        raise ValueError('Blacksmith recipes do not match source slots')

    salvage = salvage_rows()

    rules = {r['rule']: r['value'] for r in read('mystic.csv')}
    if '1,000 gold' not in rules['enchant_mystic_training_ranks']:
        raise ValueError('Mystic training scale changed; review the proposed base cost')
    if '1 Imperial-quality gem' not in rules['enchant_cost_legendary_set_jewelry']:
        raise ValueError('Mystic jewelry cost changed; review the rule')

    sql = ['-- Generated by generate_crafting.py; source costs retained in D3 gold.', 'SET NAMES utf8mb4;']
    sql += table('dc_blacksmith_recipe', 'id INT PRIMARY KEY,slot VARCHAR(20),name VARCHAR(160),item_level INT,gold_d3 INT,rarity VARCHAR(20) NOT NULL', recipes)
    sql += table('dc_recipe_material', 'recipe_id INT,item_entry INT,amount INT,PRIMARY KEY(recipe_id,item_entry)', costs)
    sql += table('dc_salvage_rule', 'rarity VARCHAR(16),crafted TINYINT,quality VARCHAR(16),item_entry INT,amount_min INT,amount_max INT,PRIMARY KEY(rarity,crafted,quality,item_entry)', salvage)
    sql += table('dc_gem_item', 'entry INT PRIMARY KEY,gem_id VARCHAR(80),tier VARCHAR(40),`rank` INT,name VARCHAR(120),colour VARCHAR(20)', gem_rows)
    sql += table('dc_gem_effect', 'entry INT,slot_class VARCHAR(20),stat VARCHAR(40),value DOUBLE,PRIMARY KEY(entry,slot_class)', effects)
    sql += ensure_column('dc_affix_pool','display_order','INT NOT NULL DEFAULT 0')
    for slot, ids in orders.items():
        for affix, order in ids.items():
            sql.append(f'UPDATE dc_affix_pool SET display_order={order} WHERE slot={quote(slot)} AND affix_id={quote(affix)};')
    normal = next(r for r in read('loot_tuning.csv', TUNABLES) if r['source'] == 'normal')
    # mystic_cost_multiplier is retired (diablocraft-t9fl): it left the CSV, but crafting_0001 is applied and
    # frozen, so its render keeps the column the migration added, with the default it was added with.
    for name in ('gold_divisor','mystic_base_gold','mystic_cost_multiplier','repair_multiplier'):
        default = '1.15' if name == 'mystic_cost_multiplier' else normal[name]
        if not math.isfinite(float(default)):
            raise ValueError(f"Invalid loot tuning default: {name}")
        sql += ensure_column('dc_loot_tuning',name,f'DOUBLE NOT NULL DEFAULT {default}')
    sql += ['CREATE TEMPORARY TABLE dc_gold_bar LIKE item_template;',
            'INSERT INTO dc_gold_bar SELECT * FROM item_template WHERE entry=102001;',
            f"UPDATE dc_gold_bar SET entry=102006,name='Gold Bar',displayid=(SELECT displayid FROM item_template WHERE entry=3577),stackable={tunable_integer('economy', 'legacy_gold_bar_stack_count', minimum=1)},BuyPrice=0,SellPrice=0,description='Worth {next(number(r, 'copper_per_item') for r in read('account_economy.csv') if r['kind'] == 'retired_gold'):,} gold. Automatically exchanged for Diablocraft purchases.';",
            'REPLACE INTO item_template SELECT * FROM dc_gold_bar;', 'DROP TEMPORARY TABLE dc_gold_bar;']
    sql += ensure_column('dc_base_item','pool_version',"VARCHAR(3) NOT NULL DEFAULT 'no'")
    sql += ensure_column('dc_base_item','designated_class',"VARCHAR(40) NOT NULL DEFAULT ''")
    # A base item added after 0002 (the Shaman's) is inserted whole, designation included, by its own items migration.
    from generate_sql import added_d3_ids
    added = added_d3_ids(MODULE / 'data/d3/base_items.csv')
    for row in read('base_items.csv'):
        if row['d3_id'] in added: continue
        if row['pool_version'] not in ('yes','no'): raise ValueError(f'Invalid pool_version: {row!r}')
        sql.append(f"UPDATE dc_base_item SET pool_version={quote(row['pool_version'])},designated_class={quote(row['designated_class'])} WHERE d3_id={quote(row['d3_id'])};")
    # Ordinary core durability and account-mail rules remain authoritative.
    sql += [f'UPDATE item_template i JOIN dc_base_item b ON b.entry=i.entry SET i.Flags=i.Flags|134217728, i.ItemLevel={tunable_integer("crafting", "base_item_level", minimum=1)};',
            f'CREATE TEMPORARY TABLE dc_native_durability AS SELECT class,InventoryType,MAX(MaxDurability) durability FROM item_template WHERE entry<100000 AND ItemLevel BETWEEN {tunable_integer("crafting", "durability_donor_min_level", minimum=1)} AND {tunable_integer("crafting", "durability_donor_max_level", minimum=1)} GROUP BY class,InventoryType;',
            'UPDATE item_template i JOIN dc_base_item b ON b.entry=i.entry JOIN dc_native_durability d ON d.class=i.class AND d.InventoryType=i.InventoryType SET i.MaxDurability=d.durability;',
            'DROP TEMPORARY TABLE dc_native_durability;']
    # Clone only the gem visuals; custom gems never use native enchantment stats. The bag icon is not the donor's:
    # legendary_gems_0005_gem_icons.sql (generate_gem_icons.py) sets it, so a new render of these rows needs a new one of it.
    visuals = {'Ruby':39900,'Emerald':36932,'Topaz':36929,'Amethyst':36926,'Diamond':42225}
    zero_stats=','.join(f'stat_type{i}=0,stat_value{i}=0' for i in range(1,11))
    for entry, gem, tier, rank, name, colour in gem_rows:
        sql += ['CREATE TEMPORARY TABLE dc_gem_template LIKE item_template;',
                f'INSERT INTO dc_gem_template SELECT * FROM item_template WHERE entry={visuals[colour]};',
                f'UPDATE dc_gem_template SET entry={entry},name={quote(name)},class=7,subclass=4,Quality={tunable_integer("crafting", "gem_quality")},Flags=0,FlagsExtra=0,ItemLevel={tunable_integer("crafting", "gem_item_level", minimum=1)},RequiredLevel={tunable_integer("crafting", "gem_required_level")},bonding=0,stackable={tunable_integer("crafting", "gem_stack_count", minimum=1)},BuyPrice={tunable_integer("economy", "gem_vendor_gold")},SellPrice={tunable_integer("economy", "gem_vendor_gold")},GemProperties=0,{zero_stats},spellid_1=0,spellid_2=0,spellid_3=0,spellid_4=0,spellid_5=0;',
                'REPLACE INTO item_template SELECT * FROM dc_gem_template;', 'DROP TEMPORARY TABLE dc_gem_template;']
    # Display-only set descriptions/powers; no effects are enabled here.
    sets = [(key, value['name'], json.dumps(value.get('bonuses',{}),ensure_ascii=False)) for key,value in reference['itemSets'].items()]
    sql += table('dc_set_tooltip','set_id VARCHAR(80) PRIMARY KEY,name VARCHAR(160),bonuses LONGTEXT', sets)
    bonuses=[(key,int(count),'\n'.join(b.get('format','') for b in lines))
             for key,value in reference['itemSets'].items() for count,lines in value.get('bonuses',{}).items()]
    sql += table('dc_set_bonus','set_id VARCHAR(80),pieces INT,body LONGTEXT,PRIMARY KEY(set_id,pieces)',bonuses)
    unique=item_tooltip_rows(reference)
    sql += table('dc_item_tooltip','d3_id VARCHAR(100) PRIMARY KEY,set_id VARCHAR(80),power_text LONGTEXT,flavour LONGTEXT',unique.values())
    sql += ['UPDATE creature_template SET npcflag=npcflag|4096 WHERE entry IN (910000,910001);']
    output='\n'.join(sql)+'\n'
    characters=['-- Generated by generate_crafting.py: sockets and persistent paid Mystic offers.']
    for table_name,name,definition in [
        ('dc_item_affix','parent_seq','SMALLINT UNSIGNED NULL'),
        ('dc_item_affix','gem_entry','INT UNSIGNED NULL'),
        ('dc_item_affix','gem_rank','INT UNSIGNED NOT NULL DEFAULT 0'),
        ('dc_item_instance','crafted','TINYINT UNSIGNED NOT NULL DEFAULT 0'),
        ('dc_item_instance','bound_account','INT UNSIGNED NOT NULL DEFAULT 0')]:
        characters+=ensure_column(table_name,name,definition)
    characters += ['CREATE TABLE IF NOT EXISTS dc_enchant_offer (item_guid BIGINT UNSIGNED NOT NULL,choice_id TINYINT UNSIGNED NOT NULL,target_seq SMALLINT UNSIGNED NOT NULL,affix_id VARCHAR(64) NOT NULL,value DOUBLE NOT NULL,range_min DOUBLE NOT NULL,range_max DOUBLE NOT NULL,kind VARCHAR(16) NOT NULL,PRIMARY KEY(item_guid,choice_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;']
    # decisions.md 2026-09-12 gold unit: repair is the one price still derived
    # from WoW's own copper, so its multiplier carries the whole unit change and
    # is now fractional. crafting_0001 above is applied and its hash recorded, so
    # the retune lands as its own migration: widen the column (0001_dc_loot_tuning
    # inferred BIGINT from the old integer value) and set each row from the CSV.
    unit=['-- Generated by generate_crafting.py; 2026-09-12 gold unit (decisions.md).',
          '-- repair_multiplier is sourced from data/tunables/loot_tuning.csv; never hand-edited.',
          'ALTER TABLE dc_loot_tuning MODIFY `repair_multiplier` DOUBLE NULL;']
    for row in read('loot_tuning.csv', TUNABLES):
        value=row['repair_multiplier'].strip()
        if not value: continue
        unit.append(f"UPDATE dc_loot_tuning SET repair_multiplier={float(value)} WHERE source={quote(row['source'])};")
    if len(unit)<4: raise ValueError('loot_tuning.csv has no repair_multiplier rows')
    # All parsing/validation above precedes writes, including the one authorized
    # CSV change: display_order only. Preserve every existing column's value.
    (DATA/'affix_pools.csv').write_text(stream.getvalue(),encoding='utf-8',newline='')
    write_generated('\n'.join(unit)+'\n', 'crafting_gold_unit.sql', 'crafting_0002_gold_unit.sql')
    write_generated(output, 'crafting.sql', 'crafting_0001_artisans.sql')
    write_generated('\n'.join(characters)+'\n', 'crafting_characters.sql', 'items_crafting_0001_artisans.sql', 'characters')
    generate_artisan_rules(artisan_sql)
    generate_mystic_rules()
    print(f'Generated {len(recipes)} recipes, {len(gem_rows)} gem templates, {len(effects)} effects; extracted display order for {len(pools)} affix rows; preserved existing CSV order for {preserved_orders} rows.')


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['--artisan-rules']:
        generate_artisan_rules()
    elif sys.argv[1:] == ['--mystic-rules']:
        generate_mystic_rules()
    elif not sys.argv[1:]:
        generate()
    else:
        raise SystemExit('Usage: generate_crafting.py [--artisan-rules|--mystic-rules]')
