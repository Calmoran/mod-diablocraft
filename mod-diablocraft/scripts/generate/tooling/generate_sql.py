#!/usr/bin/env python3
"""Generate the D3 reference tables and the item-system tables; fill tooltip tokens from the values sheets, never interpret tooltip/formula prose."""

import csv
import json
from decimal import Decimal
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from applied_migrations import AppliedStateError, reserved_number, write_coupled_outputs, write_migration
from class_names import sheet_stem
from class_names import item_key
from text_guard import refuse_unfilled
from tunable_values import integer as tunable_integer

# Literal audit (docs/research/literal-audit-claude.md): the numbers below are
# constants, not tunables - recorded here, nothing else changes.
# Constant (audit 117, 100000, 199900, 81203, 1240): item entry base, unidentified-shell entry base, its spell, its display; Identifiers.
# Constant (audit 118, 0, 1, 4, 6, 14, 23, 5-19): item class, subclass and inventory-type enums; One row for the group.
# Constant (audit 119, 30, 65, 63, 32): DECIMAL precision and integer-range guards; Schema validation.
# Constant (audit 120, 1000): ms per second when turning attacks-per-second into a weapon delay; Unit conversion.


MODULE_ROOT = Path(__file__).resolve().parents[3]
# loot_tuning.csv is the designer's, not D3's, so the FILE moved to data/tunables/ and
# out of data/d3/ (Architect 2026-09-19, option a). It keeps this generator and
# its own dc_loot_tuning table; only the folder changed, and this is the one
# place that has to know. data/tunables/README.md lists it under "Files with
# their own table".
RELOCATED = {"loot_tuning"}


def source_csv(module_root, name):
    folder = "data/tunables" if name in RELOCATED else "data/d3"
    return module_root / folder / f"{name}.csv"

# Explicit numeric columns prevent a bad value from silently changing a column to
# text. Other columns are textual, including mixed-value reference fields such as
# paragon.effect_per_point and barbarian_fury.value.
# Inputs are explicit: stats, damage_formula and mitigation are not generated.
TABLES = {
    "world_areas": ("map_id area_id", "", "phase_scope status note"),
    "barbarian_base_stats": (
        "level str dex int vit base_life life_per_vit total_life base_armor fury_max",
        "", "",
    ),
    # all_res_per_int and innate_dr_pct are the numeric transcriptions section B
    # added beside the prose columns (Codex audit 5/11) and generate_numeric_data
    # reads them as plain floats, so they are declared numeric rather than left
    # to land in the table as text. They carry no percent sign: innate_dr_pct
    # already names its unit, and the percentages group would suffix it again.
    "class_primary_stats": (
        "all_res_per_int innate_dr_pct", "",
        "class primary_stat damage_bonus armor_bonus dodge_bonus all_res_bonus innate_class_dr notes",
    ),
    "difficulty_tiers": (
        "deaths_breath_guaranteed deaths_breath_extra_pct unlock_character_level unlock_account_level unlock_solo_gr deaths_breath_min_monster_level", "monster_health_multiplier monster_damage_multiplier xp_bonus_pct gold_bonus_pct legendary_drop_bonus_pct",
        "tier deaths_breath_bounty_rift_bonus unlock_requirement notes",
    ),
    "party_scaling": (
        "players", "monster_life_multiplier monster_damage_multiplier", "context source_url",
    ),
    "elite_affix_count": (
        "hero_level_min hero_level_max affixes_per_pack", "", "applies_to source_url",
    ),
    # The last group is carried in the CSV for generate_paragon.py and is
    # deliberately NOT published in dc_paragon: nothing queries that reference
    # dump, and publishing them would rewrite the applied 0001 migration.
    "paragon": ("", "", "category stat points_per_rank effect_per_point max_rank notes",
                "stat_key stat_id category_id per_point point_cap unit resource_keys"),
    "paragon_xp": ("level xp_to_reach_level", "", ""),
    "barbarian_skills": (
        "unlock_level fury_cost fury_generation cooldown_seconds damage_pct_weapon_damage", "",
        # element is the tooltip's own damage type (Earthquake is Fire); every
        # other base skill's tooltip names none, so it reads Physical.
        "skill_name category element full_tooltip_text notes",
    ),
    "barbarian_runes": (
        "unlock_level", "", "skill_name rune_slot rune_name element full_rune_text modified_cost_cooldown_damage",
    ),
    "barbarian_passives": ("unlock_level", "", "passive_name full_text"),
    # fury_per_life_pct is the numeric transcription section B added beside the
    # prose `value` cell for audit row 7, the way difficulty_tiers carries the
    # Death's Breath level; generate_numeric_data reads it as a plain float.
    "barbarian_fury": ("fury_per_life_pct", "", "metric value details notes"),
    # 06-loot §3. Holds the L1 and L6 tunables; every number here is a decision
    # from the design doc, not a published D3 figure.
    "loot_tuning": (
        "drops_min drops_max legendary_base_pct normal_pct magic_pct rare_pct chest_multiplier deaths_breath_pct elite_promotion_pct gold_divisor mystic_base_gold repair_multiplier elite_scale_champion elite_scale_rare elite_scale_minion champion_pack_size base_monster_xp gem_chance_pct gem_imperial_share_pct identify_item_cast_seconds identify_tome_cast_seconds unidentified_drops",
        "", "source notes",
    ),
}
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")
# GitHub #71. The spell rewrite tokenised the sheets' tooltip cells: a cell
# says `{damage_pct}` where it used to say `600%`, and the number moved to the
# class's values sheets. The reference tables publish the sentence a reader
# sees, so these cells are filled back in before rendering - the same filled
# text the applied 0001 migrations already carry, byte for byte. Each entry:
# the text column, the column naming the skill (or passive), the rune column
# (whose rows fall back to their skill's own values), and the values sheets.
PLACEHOLDER = re.compile(r"\{([a-z_]+)(?::([a-z_]+))?\}")
TOOLTIP_CELLS = {
    "barbarian_skills": ("full_tooltip_text", "skill_name", None, ("barbarian_skill_values",)),
    "barbarian_runes": ("full_rune_text", "skill_name", "rune_name", ("barbarian_skill_values",)),
    "barbarian_passives": ("full_text", "passive_name", None, ("barbarian_passive_values",)),
}
VALUES_COLUMNS = {"skill", "rune", "token", "qualifier", "value", "unit", "source"}


class DataError(ValueError):
    """An input row cannot be represented faithfully."""


def fail(path, line, row, message):
    raise DataError(f"{path}:{line}: {message}\nRow: {row!r}")


def read_csv(path, expected):
    # Keep physical lines so even CSV syntax errors report the original record.
    raw = path.read_bytes().decode("utf-8-sig").splitlines(keepends=True)
    reader = csv.reader(raw, strict=True)
    try:
        header = next(reader)
    except (StopIteration, csv.Error) as error:
        fail(path, 1, "".join(raw[:reader.line_num or 1]), f"invalid header: {error}")
    if len(header) != len(set(header)) or set(header) != expected:
        fail(path, 1, header, f"expected columns: {', '.join(sorted(expected))}")
    rows = []
    while True:
        line = reader.line_num + 1
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            fail(path, line, "".join(raw[line - 1:reader.line_num]), str(error))
        if len(row) != len(header):
            fail(path, line, row, f"expected {len(header)} fields, got {len(row)}")
        rows.append((line, row))
    return header, rows


def tooltip_values(module_root, sheets):
    """{(skill, rune, token, qualifier): the text a reader sees} from values sheets."""
    found = {}
    for sheet in sheets:
        path = source_csv(module_root, sheet)
        header, rows = read_csv(path, VALUES_COLUMNS)
        at = {column: header.index(column) for column in header}
        for line, row in rows:
            key = tuple(row[at[column]] for column in ("skill", "rune", "token", "qualifier"))
            if key in found:
                fail(path, line, row, f"{key} is stated twice")
            found[key] = row[at["value"]] + ("%" if row[at["unit"]] == "pct" else "")
    return found


def fill_tooltips(module_root, name, path, specification):
    """One sheet's rows with every tooltip `{token}` filled from its values.

    A token the values sheets do not state is an error, never passed through:
    an unfilled placeholder is not text a player can be shown.
    """
    text_column, skill_column, rune_column, sheets = TOOLTIP_CELLS[name]
    numeric, percentages, text, *rest = (set(group.split()) for group in specification)
    header, rows = read_csv(path, numeric | percentages | text | (rest[0] if rest else set()))
    values = tooltip_values(module_root, sheets)
    at_text, at_skill = header.index(text_column), header.index(skill_column)
    at_rune = header.index(rune_column) if rune_column else None
    filled = []
    for line, row in rows:
        skill = row[at_skill]
        rune = row[at_rune] if at_rune is not None else ""

        def put(match):
            token, qualifier = match[1], match[2] or ""
            for key in ((skill, rune, token, qualifier), (skill, "", token, qualifier)):
                if key in values:
                    return values[key]
            fail(path, line, row, f"{text_column}: {match[0]} has no row in {', '.join(sheets)}")

        row = list(row)
        row[at_text] = PLACEHOLDER.sub(put, row[at_text])
        filled.append((line, row))
    return header, filled


def refuse_placeholders(label, sql):
    """An unfilled `{token}` never reaches generated output (GitHub #71)."""
    found = sorted(set(match[0] for match in PLACEHOLDER.finditer(sql)))
    if found:
        raise DataError(f"{label}: unfilled placeholders {', '.join(found)}; nothing was written")
    return sql


def number(value, percent, path, line, row, column):
    if value == "":
        return None
    token = value[:-1] if percent and value.endswith("%") else value
    if (percent and not value.endswith("%")) or not NUMBER.fullmatch(token):
        fail(path, line, row, f"{column}: expected {'percentage' if percent else 'number'}, got {value!r}")
    result = Decimal(token)
    _, digits, exponent = result.as_tuple()
    scale = max(0, -exponent)
    integer_digits = max(1, len(digits) + exponent)
    if scale > 30 or integer_digits + scale > 65:
        fail(path, line, row, f"{column}: {value!r} exceeds MySQL DECIMAL precision")
    return result


# Columns whose values happen to be whole today but are seconds, so a retune to
# 2.5 must not be silently truncated by a BIGINT column. Review item 7,
# 2026-09-17: identify_tome_cast_seconds shipped as BIGINT because the designer's value
# is 2, while identify_item_cast_seconds got DECIMAL only because 1.5 forced it.
FORCED_DECIMAL = {"identify_item_cast_seconds", "identify_tome_cast_seconds"}


def numeric_type(values, column=None):
    if column in FORCED_DECIMAL:
        present = [value for value in values if value is not None]
        scale = max(2, max((max(0, -value.as_tuple().exponent) for value in present), default=0))
        digits = max((max(1, len(value.as_tuple().digits) + value.as_tuple().exponent)
                      for value in present), default=1)
        return f"DECIMAL({digits + scale},{scale})"
    present = [value for value in values if value is not None]
    if all(value == value.to_integral_value() and -(2**63) <= value < 2**63 for value in present):
        return "BIGINT"
    scale = max((max(0, -value.as_tuple().exponent) for value in present), default=0)
    digits = max((max(1, len(value.as_tuple().digits) + value.as_tuple().exponent) for value in present), default=1)
    return f"DECIMAL({digits + scale},{scale})"


def sql_text(value):
    # Hex encoding handles backslashes/control characters independently of the
    # session's NO_BACKSLASH_ESCAPES setting; ordinary prose remains readable.
    if "\\" in value or any(ord(char) < 32 for char in value):
        return "CONVERT(X'" + value.encode("utf-8").hex() + "' USING utf8mb4)"
    return "'" + value.replace("'", "''") + "'"


def render_table(path, specification, table_name=None, source_rows=None):
    """Render one reference CSV as its `dc_<stem>` table.

    A specification may carry a fourth group of column names that the CSV holds
    but the table does not publish. That is for cells a generator reads and the
    reference dump has no business restating - identity columns, say - and it
    exists so adding one to a CSV does not rewrite an already-applied 0001
    migration for a table nothing queries.
    """
    numeric, percentages, text, *rest = (set(group.split()) for group in specification)
    ignored = rest[0] if rest else set()
    header, rows = (source_rows if source_rows is not None
                    else read_csv(path, numeric | percentages | text | ignored))
    definitions, columns, converted = [], [], []
    for index, column in enumerate(header):
        if column in ignored:
            continue
        percent = column in percentages
        output_name = column + "_pct" if percent and not column.endswith("_pct") else column
        columns.append(f"`{output_name}`")
        if column in numeric or percent:
            values = [number(row[index], percent, path, line, row, column) for line, row in rows]
            kind = numeric_type(values, column)
            # Precision also needs to accommodate the largest integer and scale
            # when those occur in different records.
            if kind.startswith("DECIMAL") and int(kind.split("(")[1].split(",")[0]) > 65:
                fail(path, rows[-1][0], rows[-1][1], f"{column}: combined precision exceeds 65 digits")
            converted.append(["NULL" if value is None else format(value, "f") for value in values])
            definitions.append(f"  `{output_name}` {kind} NULL")
        else:
            converted.append([sql_text(row[index]) for _, row in rows])
            definitions.append(f"  `{output_name}` LONGTEXT NOT NULL")
    if len(set(columns)) != len(columns):
        fail(path, 1, header, "percentage suffix creates duplicate column names")
    name = table_name or "dc_" + path.stem
    table = f"`{name}`"
    lines = [
        f"-- Generated from data/d3/{path.name}; edit the CSV and rerun generate_sql.py.",
        "-- Apply to the world database.",
        "SET NAMES utf8mb4;",
        f"DROP TABLE IF EXISTS {table};",
        f"CREATE TABLE {table} (",
        ",\n".join(definitions),
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
    ]
    for offset in range(0, len(rows), 100):
        lines.append(f"INSERT INTO {table} ({', '.join(columns)}) VALUES")
        records = ["(" + ", ".join(values[index] for values in converted) + ")"
                   for index in range(offset, min(offset + 100, len(rows)))]
        lines.append(",\n".join(records) + ";")
    return "\n".join(lines) + "\n", len(rows)


def render_world_areas(path):
    header, rows = read_csv(path, {"map_id", "area_id", "phase_scope", "status", "note"})
    seen = set()
    for line, row in rows:
        values = dict(zip(header, row))
        ids = []
        for column in ("map_id", "area_id"):
            value = number(values[column], False, path, line, row, column)
            if value is None or value != value.to_integral_value() or not 0 <= value < 2**32:
                fail(path, line, row, f"{column}: expected an unsigned 32-bit integer")
            ids.append(int(value))
        if values["phase_scope"] not in {"all", "tier", "campaign"}:
            fail(path, line, row, "phase_scope: expected all, tier or campaign")
        if values["status"] not in {"open", "closed"}:
            fail(path, line, row, "status: expected open or closed")
        if tuple(ids) in seen:
            fail(path, line, row, "duplicate map/area rule")
        seen.add(tuple(ids))
    return render_table(path, TABLES["world_areas"])


def generate_world_areas(module_root=MODULE_ROOT):
    """Refresh CSV-owned rules without replacing the live table or old migrations."""
    path = module_root / "data/d3/world_areas.csv"
    snapshot, count = render_world_areas(path)
    # world_0009 is applied: it is the old hub's rules (Scryer's Tier), so it and its mirror regenerate from the frozen sheet,
    # never from the live one (which holds the Sanctum's rules since diablocraft-976b); only the snapshot above follows the live sheet.
    header, rows = read_csv(module_root / "tests/scryer_hub/world_areas.csv", {"map_id", "area_id", "phase_scope", "status", "note"})
    lines = ["-- Generated from data/d3/world_areas.csv by generate_sql.py --world-areas.",
             "-- Reloaded at worldserver startup; no C++ rebuild required.",
             "SET NAMES utf8mb4;", "START TRANSACTION;"]
    for _, row in rows:
        values = dict(zip(header, row))
        map_id, area_id = int(values["map_id"]), int(values["area_id"])
        lines.append(f"DELETE FROM `dc_world_areas` WHERE `map_id`={map_id} AND `area_id`={area_id};")
        text_values = ", ".join(sql_text(values[key]) for key in ("phase_scope", "status", "note"))
        lines.append("INSERT INTO `dc_world_areas` (`map_id`,`area_id`,`phase_scope`,`status`,`note`) "
                     f"VALUES ({map_id},{area_id},{text_values});")
    lines.append("COMMIT;")
    generated = module_root / "data/generated"
    output = generated / "world_0009_scryers_tier_area.sql"
    (generated / "world_areas.sql").write_bytes(snapshot.encode("utf-8"))
    output.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    write_migration(module_root, module_root / "data/sql/db-world/updates" / output.name,
                    output.read_bytes())
    print(f"dc_world_areas: {count} CSV-owned rules; world_0009_scryers_tier_area.sql")


def class_start_rows(path):
    """Read class-keyed rolled kits/proficiencies; all content comes from the sheet."""
    from tunable_values import integer
    columns = {"class_id", "class_key", "class_name", "row_type", "slot", "rarity",
               "count_key", "spell_id", "skill_id", "base_type", "base_slot", "designated_class", "source"}
    header, rows = read_csv(path, columns)
    classes, class_keys = {}, {}
    slots = {"mainhand", "head", "neck", "shoulders", "torso", "waist", "legs",
             "feet", "wrists", "hands", "finger", "offhand"}
    with (path.parent / 'rarity_tiers.csv').open(encoding='utf-8-sig', newline='') as stream:
        rarities = {r['rarity'].split(' (', 1)[0].lower() for r in csv.DictReader(stream)}
    def identifier(value, maximum, line, row):
        if not re.fullmatch(r'[1-9][0-9]*', value) or int(value) > maximum:
            fail(path, line, row, 'expected positive integer identity in native range')
        return int(value)
    for line, cells in rows:
        row = dict(zip(header, cells))
        cid = identifier(row['class_id'], 255, line, row)
        key, name = row['class_key'], row['class_name']
        if not re.fullmatch(r'[a-z][a-z0-9_]*', key) or len(key) > 40 or not name or len(name) > 80 or not row['source']:
            fail(path, line, row, 'missing/invalid class identity or provenance')
        if key in class_keys and class_keys[key] != cid:
            fail(path, line, row, 'class key assigned to multiple class IDs')
        class_keys[key] = cid
        profile = classes.setdefault(cid, dict(class_key=key, class_name=name, kit=[], skills=[]))
        if (profile['class_key'], profile['class_name']) != (key, name):
            fail(path, line, row, 'conflicting class metadata')
        if row['row_type'] == 'kit':
            if row['slot'] not in slots or row['rarity'] not in rarities or row['spell_id'] or row['skill_id']:
                fail(path, line, row, 'invalid kit slot/rarity or unexpected skill fields')
            if any(r['slot'] == row['slot'] for r in profile['kit']):
                fail(path, line, row, 'duplicate class kit slot')
            if not re.fullmatch(r'[a-z][a-z0-9_]*', row['count_key']):
                fail(path, line, row, 'missing/invalid starter count key')
            count = integer('crafting', row['count_key'], module=path.parents[2],
                            maximum=2 if row['slot'] == 'finger' else 1)
            filters = {key: row[key] for key in ('base_type', 'base_slot', 'designated_class')}
            if row['slot'] in ('mainhand', 'offhand'):
                if not filters['base_type'] or filters['base_slot'] not in ('onehand', 'twohand', 'offhand'):
                    fail(path, line, row, 'weapon slot requires an explicit base type and slot')
                if filters['designated_class'] not in ('', key):
                    fail(path, line, row, 'weapon designation must match its class')
            elif any(filters.values()):
                fail(path, line, row, 'weapon filters are only supported on hand slots')
            profile['kit'].append(dict(slot=row['slot'], rarity=row['rarity'], count=count, **filters))
        elif row['row_type'] == 'skill':
            if any(row[k] for k in ('slot', 'rarity', 'count_key', 'base_type', 'base_slot', 'designated_class')):
                fail(path, line, row, 'unexpected kit fields on skill row')
            spell = identifier(row['spell_id'], 2**32-1, line, row)
            skill = identifier(row['skill_id'], 2**32-1, line, row)
            if any(r['spell_id'] == spell or r['skill_id'] == skill for r in profile['skills']):
                fail(path, line, row, 'duplicate class proficiency spell/skill')
            profile['skills'].append(dict(spell_id=spell, skill_id=skill))
        else:
            fail(path, line, row, 'unknown class start row type')
    if not classes:
        fail(path, 1, '', 'missing class start rows')
    for cid, profile in classes.items():
        if not profile['kit'] or not any(r['count'] for r in profile['kit']) or not profile['skills']:
            fail(path, 1, cid, 'class requires a nonempty kit and proficiency rows')
    return classes


def starter_candidates(profile, kit, bases):
    """Mirror runtime eligibility, including CSV-owned hand restrictions."""
    key = profile['class_key']
    return [b for b in bases if b['pool_version'] == 'yes'
            and (not b['usable_by'] or key in b['usable_by'].split(';'))
            and b['designated_class'] in ('', key)
            and (b['slot'] in ('onehand', 'twohand') if kit['slot'] == 'mainhand'
                 else b['slot'] == ('onehand' if kit['slot'] == 'offhand' and kit['base_slot'] == 'onehand' else kit['slot']))
            and (not b['rarity'] if kit['rarity'] == 'rare' else b['rarity'] == kit['rarity'])
            and (not kit['base_type'] or b['type'] == kit['base_type'])
            and (not kit['base_slot'] or b['slot'] == kit['base_slot'])
            and (not kit['designated_class'] or b['designated_class'] == kit['designated_class'])]


def render_class_starts(module_root=MODULE_ROOT):
    classes = class_start_rows(module_root / 'data/d3/class_starts.csv')
    with (module_root / 'data/d3/base_items.csv').open(newline='', encoding='utf-8-sig') as stream:
        bases = list(csv.DictReader(stream))
    for profile in classes.values():
        for kit in profile['kit']:
            if kit['count'] and not starter_candidates(profile, kit, bases):
                raise DataError(f"Empty starter pool: {profile['class_key']} {kit['slot']}")
    lines = ['-- Generated from data/d3/class_starts.csv by generate_sql.py --class-starts.',
             '-- Class-keyed equivalents for rolled starter items and login proficiency repair.',
             '-- Native learnSpell/LearnDefaultSkill and item roll/equip APIs remain authoritative.',
             'SET NAMES utf8mb4;',
             'CREATE TABLE IF NOT EXISTS dc_class_start (class_id TINYINT UNSIGNED PRIMARY KEY, class_key VARCHAR(40) NOT NULL UNIQUE, class_name VARCHAR(80) NOT NULL) ENGINE=InnoDB;',
             # The three filter columns were added by world_0021's ALTER, which cannot run twice; a later render
             # creates them with the table instead (diablocraft-xecwl).
             'CREATE TABLE IF NOT EXISTS dc_class_starter_kit (class_id TINYINT UNSIGNED NOT NULL, slot VARCHAR(20) NOT NULL, rarity VARCHAR(20) NOT NULL, count INT UNSIGNED NOT NULL, base_type VARCHAR(80) NOT NULL DEFAULT \'\', base_slot VARCHAR(20) NOT NULL DEFAULT \'\', designated_class VARCHAR(40) NOT NULL DEFAULT \'\', PRIMARY KEY(class_id,slot)) ENGINE=InnoDB;',
             'CREATE TABLE IF NOT EXISTS dc_class_start_skill (class_id TINYINT UNSIGNED NOT NULL, spell_id INT UNSIGNED NOT NULL, skill_id INT UNSIGNED NOT NULL, PRIMARY KEY(class_id,spell_id), UNIQUE KEY(class_id,skill_id)) ENGINE=InnoDB;',
             'START TRANSACTION;', 'DELETE FROM dc_class_start_skill;',
             'DELETE FROM dc_class_starter_kit;', 'DELETE FROM dc_class_start;']
    for cid, profile in sorted(classes.items()):
        lines.append(f"INSERT INTO dc_class_start VALUES ({cid},{sql_text(profile['class_key'])},{sql_text(profile['class_name'])});")
        for row in profile['kit']:
            lines.append(f"INSERT INTO dc_class_starter_kit VALUES ({cid},{sql_text(row['slot'])},{sql_text(row['rarity'])},{row['count']},{sql_text(row['base_type'])},{sql_text(row['base_slot'])},{sql_text(row['designated_class'])});")
        for row in profile['skills']:
            lines.append(f"INSERT INTO dc_class_start_skill VALUES ({cid},{row['spell_id']},{row['skill_id']});")
    from generate_tunables import read_category, sql as tunables_sql
    floor = [row for row in read_category(module_root / 'data/tunables/paragon.csv') if row[:2] == ('paragon', 'starting_paragon_level')]
    if len(floor) != 1:
        raise DataError('Missing starting Paragon floor')
    lines.append('COMMIT;')
    lines.append(tunables_sql(floor).rstrip())
    return '\n'.join(lines) + '\n', len(classes)


# world_0012 is applied and frozen; the Wizard's profile (diablocraft-class-
# parity item 5) renders the full tables into the next number. A later profile
# change is a new number again, with this one added to CLASS_START_APPLIED.
# world_0040 adds the Barbarian's Dual Wield (diablocraft-xecwl). world_0021 stays out of CLASS_START_APPLIED: that
# list is what the applied legacy companion was rendered against, and no class is new in world_0040.
# world_0048 adds the Monk (diablocraft-1cuvw): world_0040 joins the list and the legacy companion moves to
# db-characters world_0004, so the applied world_0003 (the Wizard's) is left as it is.
# world_0060 adds the Necromancer (diablocraft-im7mr.1): world_0048 joins the list and the legacy companion moves to
# db-characters world_0006, so world_0004 (the Monk's) is left as it is.
# world_0066 adds the Crusader: world_0060 joins the list and the legacy companion moves to db-characters world_0007,
# so world_0006 (the Necromancer's) is left as it is.
# world_0072 adds the Demon Hunter (diablocraft-vawmy.1): world_0066 joins the list and the legacy companion moves to
# db-characters world_0008, so world_0007 (the Crusader's) is left as it is.
# world_0078 adds the Witch Doctor (diablocraft-vxrcu.1): world_0072 joins the list and the legacy companion moves to
# db-characters world_0009, so world_0008 (the Demon Hunter's) is left as it is.
# world_0087 adds the Shaman (diablocraft-xnrvn.3): world_0078 joins the list and the legacy companion moves to
# db-characters world_0010, so world_0009 (the Witch Doctor's) is left as it is.
CLASS_START_APPLIED = ('world_0012_class_starts.sql', 'world_0040_class_starts.sql', 'world_0048_class_starts.sql',
                       'world_0060_class_starts.sql', 'world_0066_class_starts.sql', 'world_0072_class_starts.sql',
                       'world_0078_class_starts.sql')
CLASS_START_MIGRATION = 'world_0087_class_starts.sql'
# Its characters-database companion (ruling 2026-09-23, Q2 option a).
CLASS_START_LEGACY_MIGRATION = 'world_0010_class_start_legacy.sql'
PUBLISHED_CLASS_START = re.compile(r"^INSERT INTO dc_class_start VALUES \((\d+),", re.M)


def render_class_start_legacy(module_root, classes):
    """Characters of a class that had no start profile before this migration.

    Ruling 2026-09-23 (diablocraft-class-parity Q2 option a): a character made
    before its class had a profile - Wiztest - gets its mode and account set up
    on login and nothing else: no kit, no Satchels, nothing destroyed or
    replaced. The updater applies this before any login, so every character of
    a newly profiled class that exists then predates the profile; recording its
    start as complete (and its bags as handled, 0 granted) is what keeps
    Start's retry and the bag sweep away from it. Newly profiled = in the
    sheet, but in none of the applied class-start migrations."""
    updates = module_root / 'data/sql/db-world/updates'
    earlier = set()
    for name in CLASS_START_APPLIED:
        text = (updates / name).read_text(encoding='utf-8')
        found = {int(n) for n in PUBLISHED_CLASS_START.findall(text)}
        if not found:
            raise DataError(f'{name}: no dc_class_start rows could be read')
        earlier |= found
    added = sorted(set(classes) - earlier)
    lines = ['-- Generated from data/d3/class_starts.csv by generate_sql.py --class-starts.',
             '-- ruling 2026-09-23 (diablocraft-class-parity Q2 option a): characters that existed',
             '-- before their class had a start profile get mode and account setup on login',
             '-- (dc_world.cpp Setup) and never the kit or the starter Satchels. Existing rows',
             '-- are kept (INSERT IGNORE), so a recorded start or bag grant is never changed.']
    if added:
        ids = ','.join(map(str, added))
        lines += [f'INSERT IGNORE INTO dc_character_start (guid,complete) SELECT guid,1 FROM characters WHERE class IN ({ids});',
                  f'INSERT IGNORE INTO dc_character_bag_grant (guid,granted) SELECT guid,0 FROM characters WHERE class IN ({ids});']
    return '\n'.join(lines) + '\n', added


def generate_class_starts(module_root=MODULE_ROOT, rendered=None):
    sql, count = rendered if rendered is not None else render_class_starts(module_root)
    legacy, added = render_class_start_legacy(module_root, class_start_rows(module_root / 'data/d3/class_starts.csv'))
    target = module_root / 'data/sql/db-world/updates' / CLASS_START_MIGRATION
    (module_root / 'data/generated/class_starts.sql').write_text(sql, encoding='utf-8', newline='\n')
    write_migration(module_root, target, sql)
    write_migration(module_root, module_root / 'data/sql/db-characters/updates' / CLASS_START_LEGACY_MIGRATION, legacy)
    print(f'class starts: {count} class profiles; {CLASS_START_MIGRATION}; '
          f'legacy characters of newly profiled classes {added} recorded as set up without a kit')


# --- class-keyed base stats (diablocraft-wizard-resource) --------------------
# Ruling Q7 (decisions.md 2026-09-22): the stats path reads each class's
# <class>_base_stats.csv by class, with the main stat from class_map.csv. One
# table keyed by class_map.csv's class_id holds every class, so the module
# loads them with one query and names no class. The applied
# 0001_dc_barbarian_base_stats.sql is left as it is; these rows are new output
# in a new migration.
#
# A sheet's resource column is its one `*_max` column: fury_max on the
# Barbarian's (the name the applied table keeps), resource_max on the Wizard's; where a sheet has resource_max
# it is that one, and a second pool's column (the Demon Hunter's discipline_max) is read by the resource registry.
# The class's damage reduction and all-resistance-per-Intelligence are
# class_primary_stats.csv's numeric transcriptions, the same cells the
# Barbarian's numeric rules read (generate_numeric_data.py).
CLASS_BASE_COLUMNS = ("level", "str", "dex", "int", "vit", "base_life", "life_per_vit", "base_armor")
# stats_0001 (the Barbarian and the Wizard) is applied and frozen; the Monk (diablocraft-1cuvw) renders the full
# tables into the next number. A class added later is a new number again: stats_0003 is applied, so the Necromancer
# (diablocraft-im7mr.1) renders the full tables into stats_0005; stats_0005 is applied, so the Crusader's are stats_0006;
# stats_0006 is applied, so the Demon Hunter's are stats_0007; stats_0007 is applied, so the Witch Doctor's are stats_0008; stats_0008 is applied, so the Shaman's are stats_0009.
CLASS_BASE_MIGRATION = "stats_0009_class_base_stats.sql"


def class_base_rows(module_root=MODULE_ROOT, classes=None):
    """[(class_id, d3_class, rules, [(level, values..., resource_max)])] in class_map order.

    `classes` limits the output to those d3_class names; None is every row of
    class_map.csv. A class_map.csv row without a base sheet is an error.
    """
    d3 = module_root / "data/d3"
    with (d3 / "class_map.csv").open(encoding="utf-8-sig", newline="") as stream:
        class_map = list(csv.DictReader(stream))
    with (d3 / "class_primary_stats.csv").open(encoding="utf-8-sig", newline="") as stream:
        rules = {row["class"]: row for row in csv.DictReader(stream)}
    out = []
    for entry in class_map:
        name = entry["d3_class"]
        if classes is not None and name not in classes:
            continue
        path = d3 / f"{sheet_stem(name)}_base_stats.csv"
        if not path.is_file():
            raise DataError(f"class_map.csv: {name} has no {path.name}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            header = reader.fieldnames or []
            resource = [column for column in header if column.endswith("_max")]
            if "resource_max" in resource:
                resource = ["resource_max"]    # a second pool's column (discipline_max) sits beside it and is not read here
            missing = [column for column in CLASS_BASE_COLUMNS if column not in header]
            if len(resource) != 1 or missing:
                raise DataError(f"{path.name}: expected {', '.join(CLASS_BASE_COLUMNS)} and one *_max "
                                f"column, got {header}")
            levels = []
            for line, row in enumerate(reader, start=2):
                try:
                    values = [int(row[column]) for column in CLASS_BASE_COLUMNS + (resource[0],)]
                except ValueError:
                    raise DataError(f"{path.name}:{line}: every base stat must be a whole number")
                level, strength, dexterity, _int, vitality, base_life, per_vit, armor, _max = values
                if level != len(levels) + 1:
                    raise DataError(f"{path.name}:{line}: levels must run 1, 2, 3... without gaps")
                if armor != strength + dexterity:
                    raise DataError(f"{path.name}:{line}: base_armor must equal str + dex")
                if "total_life" in row and int(row["total_life"]) != base_life + vitality * per_vit:
                    raise DataError(f"{path.name}:{line}: total_life must equal base_life + vit x life_per_vit")
                levels.append(values)
        if not levels:
            raise DataError(f"{path.name}: no levels")
        rule = rules.get(name)
        if rule is None or not rule["innate_dr_pct"] or not rule["all_res_per_int"]:
            raise DataError(f"class_primary_stats.csv: {name} needs innate_dr_pct and all_res_per_int")
        if rule["primary_stat"] != entry["primary_stat"]:
            raise DataError(f"{name}: class_map.csv and class_primary_stats.csv disagree on the main stat")
        out.append((int(entry["class_id"]), name,
                    (Decimal(rule["innate_dr_pct"]), Decimal(rule["all_res_per_int"])), levels))
    return out


def render_class_base_stats(module_root=MODULE_ROOT, classes=None):
    rows = class_base_rows(module_root, classes)
    lines = ["-- Generated by generate_sql.py from class_map.csv, class_primary_stats.csv and",
             "-- each class's <class>_base_stats.csv; edit the CSVs and rerun.",
             "-- Apply to the world database.",
             "SET NAMES utf8mb4;",
             "DROP TABLE IF EXISTS `dc_class_base_stats`;",
             "CREATE TABLE `dc_class_base_stats` (",
             "  `class_id` INT UNSIGNED NOT NULL,",
             *[f"  `{column}` INT UNSIGNED NOT NULL," for column in CLASS_BASE_COLUMNS],
             "  `resource_max` INT UNSIGNED NOT NULL,",
             "  PRIMARY KEY (`class_id`, `level`)",
             ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
             "DROP TABLE IF EXISTS `dc_class_stat_rules`;",
             "CREATE TABLE `dc_class_stat_rules` (",
             "  `class_id` INT UNSIGNED NOT NULL,",
             "  `class_dr_pct` DOUBLE NOT NULL,",
             "  `all_res_per_int` DOUBLE NOT NULL,",
             "  PRIMARY KEY (`class_id`)",
             ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"]
    columns = ", ".join(f"`{column}`" for column in ("class_id",) + CLASS_BASE_COLUMNS + ("resource_max",))
    for class_id, name, (class_dr, all_res), levels in rows:
        lines.append(f"-- {name}")
        lines.append(f"INSERT INTO `dc_class_base_stats` ({columns}) VALUES")
        lines.append(",\n".join("(" + ", ".join(str(value) for value in (class_id, *values)) + ")"
                                for values in levels) + ";")
        lines.append("INSERT INTO `dc_class_stat_rules` (`class_id`, `class_dr_pct`, `all_res_per_int`) "
                     f"VALUES ({class_id}, {class_dr}, {all_res});")
    return "\n".join(lines) + "\n", sum(len(levels) for *_, levels in rows)


def generate_class_base_stats(module_root=MODULE_ROOT, rendered=None):
    sql, count = rendered if rendered is not None else render_class_base_stats(module_root)
    (module_root / "data/generated/class_base_stats.sql").write_text(sql, encoding="utf-8", newline="\n")
    write_migration(module_root, module_root / "data/sql/db-world/updates" / CLASS_BASE_MIGRATION, sql)
    print(f"class base stats: {count} rows; {CLASS_BASE_MIGRATION}")


# --- Item system (05-items) -------------------------------------------------
# base_items.csv, affix_pools.csv and gems.csv were extracted from the D3Planner
# sources; every row carries the file it came from. These three feed 05 §2-§6.
ITEM_TABLES = {
    "affix_pools": ("dc_affix_pool", (
        "value_min value_max value_min2 value_max2 value_step is_percent display_order", "",
        "slot affix_id affix_name kind item_level_bracket source_file weapon_class")),
    # G1 (diablocraft-weapon-elemental-build): the ONE sourced type -> weapon-class map, from
    # slots.js `affixes.weapon` (the roller and the Blacksmith preview both read this, and no
    # C++ or Lua keeps its own type list). dc_base_item carries only `type`, so the class is
    # looked up, not stored per base.
    "weapon_classes": ("dc_weapon_class", (
        "source_line", "",
        "weapon_type weapon_class matched_type source_file")),
    "gems": ("dc_gem", (
        "effect_value is_legendary", "",
        "gem_id gem_name colour tier slot_class effect_stat source_file")),
}
# An item table whose 0002 migration is applied and frozen renders into the
# next migration named here instead (applied migrations never change). Issue
# #56 added value_step, the sourced roll step, to the affix pool; the next
# change to the pool is a new number here, and the generator refuses to rewrite
# this one once it differs.
ITEM_MIGRATIONS = {"affix_pools": "items_0040_quiver_attack_speed.sql",
                   # G1: the weapon-class map, in the item system's numbered series like the rest.
                   # items_0019 is applied; the Shaman's Ritual Mace (diablocraft-xnrvn.3) renders the whole table again.
                   "weapon_classes": "items_0059_weapon_class.sql"}
# G1: the dc_base_item.preset_affixes delta's home. Fixed, not next-numbered, so a rerun rewrites
# the same file instead of minting a fresh duplicate each time; a later preset change is a new
# number here, and write_migration refuses to rewrite this one once it is applied. items_0017 (G1) is applied;
# The allres respelling is items_0030, which repeats 0017's UPDATEs (each sets a value, so a no-op rerun).
BASE_PRESET_MIGRATION = "items_0030_base_item_presets.sql"
# The dc_base_item.craft_only delta's home (diablocraft-0vt07.15 made the Hellfire Ring and Amulet craft-only after 0002
# shipped). Fixed like the preset delta: a rerun rewrites the same file, a later craft_only change is a new number here.
BASE_CRAFT_ONLY_MIGRATION = "items_0056_base_item_craft_only.sql"
# The dc_base_item.usable_by delta's home (diablocraft-xnrvn.3 listed the Shaman on the draft's weapon types and the shield after
# 0002 shipped). Fixed like the others: a rerun rewrites the same file, a later usable_by change is a new number here.
BASE_USABLE_BY_MIGRATION = "items_0060_base_item_usable_by.sql"
# The templates: 0002_dc_item_template and the shells' items_0007 are applied
# and frozen, and later migrations change other columns of the same rows
# (crafting_0003: Flags, ItemLevel, MaxDurability). So Miscellaneous armor
# (ruling 2026-09-23, diablocraft-class-parity Q1 option B) ships as targeted
# subclass UPDATEs against each applied render (render_subclass_delta), never
# as a full DELETE + INSERT that would reset those columns. The full current
# render stays in the data/generated mirror only.
TEMPLATE_MIGRATION = "items_0009_item_template_misc_armor.sql"
SHELL_MIGRATION = "items_0010_unidentified_shells_misc_armor.sql"
TEMPLATE_APPLIED = "0002_dc_item_template.sql"
SHELL_APPLIED = "items_0007_unidentified_shells.sql"
ALLOWABLE_MIGRATION = "items_0011_item_allowable_class.sql"
SET_WEAR_MIGRATION = "items_0020_set_wear_class.sql"
# items_0011 and items_0020 are applied and frozen, rendered when the Barbarian and the Wizard were the classes in
# class_map.csv. They keep rendering for those two (APPLIED_WEAR_CLASSES); a class added later (the Monk,
# diablocraft-1cuvw) changes the masks in ADDED_WEAR_MIGRATION, a delta against both, and the next class
# is a new number again: items_0028 (the Monk's) is applied, so the Necromancer's (diablocraft-im7mr.1) renders the
# whole delta, the Monk's entries included, into items_0041 (items_0040 is fzrqh's Quiver); items_0041 is applied, so
# the Crusader's renders the whole delta again into items_0046; items_0046 is applied, so the Demon Hunter's is items_0050; items_0050 is
# applied, so the Witch Doctor's is items_0053 (items_0051 and items_0052 are others'); items_0053 is applied, so the
# Shaman's (diablocraft-xnrvn.3, the draft's weapon types listing her) is items_0058 (items_0057 inserts her item types).
APPLIED_WEAR_CLASSES = ("barbarian", "wizard")
ADDED_WEAR_MIGRATION = "items_0058_item_allowable_class_added.sql"
DESCRIPTION_MIGRATION = "items_0013_item_descriptions.sql"
SELL_PRICE_MIGRATION = "items_0021_item_sell_price.sql"
SHEATH_MIGRATION = "items_0022_item_sheath.sql"
# item_template.description is varchar(255). Rule (diablocraft-item-descriptions):
# the power comes first and is never cut; the flavour is dropped whole when the
# pair does not fit; a power that alone does not fit gets no native description
# and the addon keeps drawing it. Nothing is ever truncated mid-sentence.
DESCRIPTION_LIMIT = 255
TEMPLATE_ROW = re.compile(r"^\((\d+), (\d+), (\d+), (.*?)\)[,;]?$", re.M)


def shipped_entries(path):
    """The entry ids of the dc_base_item rows the applied 0002 migration holds, read from the sql tree beside `path`
    (data/d3/base_items.csv); None when the tree has none, which is every entry. The renders of the frozen migrations
    (the wear masks, the sell price, the sheath, the descriptions) cover these only: a base item added since gets
    all of that from the added-base migration (render_added_base_items), so a frozen render never changes."""
    applied = path.parents[1] / "sql/db-world/updates/0002_dc_base_item.sql"
    if not applied.is_file():
        return None
    return {int(entry) for entry, _d3_id in PUBLISHED_ROW.findall(applied.read_text(encoding="utf-8"))}


def scoped_rows(path, rows, entries, only=None):
    """`rows` (dicts with d3_id) kept to the entries in `only`, else to the shipped ones, in their order."""
    scope = shipped_entries(path) if only is None else only
    return rows if scope is None else [row for row in rows if entries[row["d3_id"]] in scope]


def shipped_rows(path, rows, entries):
    """`rows` (dicts with d3_id) kept to the shipped entries, in their order."""
    return scoped_rows(path, rows, entries)


def base_wear_mask(row, bits):
    """The AllowableClass a base gets from its own class lists (-1 when it names none); the one
    rule behind both the applied items_0011 render and the set-wear delta."""
    listed, designated = row["usable_by"], row["designated_class"]
    if not listed and not designated:
        return -1
    mask = 0
    for key, bit in bits.items():
        if (not listed or key in listed.split(";")) and (not designated or designated == key):
            mask |= bit
    return mask


def class_bits(path, only=None):
    """{class key: WoW class bit} from class_map.csv beside `path`; `only` limits it to those keys."""
    with path.with_name("class_map.csv").open(encoding="utf-8-sig", newline="") as stream:
        return {item_key(row["d3_class"]): 1 << (int(row["wow_class_id"]) - 1)
                for row in csv.DictReader(stream, strict=True)
                if only is None or item_key(row["d3_class"]) in only}


def render_allowable_class(path):
    """Targeted AllowableClass UPDATEs for every base item template.

    Ruling 2026-09-23 (diablocraft-class-parity Q3 option a, and shields per
    item 1): who may WEAR a base follows its own D3 class list - base_items.csv
    usable_by and designated_class, taken from D3Planner data.json itemTypes
    (`classes` list, or the one `class` of a class-only type such as Wizard Hat,
    Mighty Belt, Source) - through class_map.csv to WoW class bits. A class may
    wear a base when usable_by is empty or names it, and designated_class is
    empty or is it: the start kit's own rule (dc_world.cpp Usable). This is a
    wear rule only; what may drop for whom is the loot roller's.

    A base with neither list names no class and stays -1 (unrestricted, the
    template default). A base whose classes are all absent from class_map.csv
    gets 0: no playable class may wear it until its class is added, and the
    core names each such template once at startup (ObjectMgr.cpp:3587). Only
    AllowableClass is written; every other column stays as the applied
    migrations left it."""
    # render_base_items has already validated both sheets in full by this point.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, strict=True))
    entries = read_base_item_ids(path.with_name("base_item_ids.csv"), {row["d3_id"] for row in rows})
    bits = class_bits(path, APPLIED_WEAR_CLASSES)
    groups = {}
    for row in shipped_rows(path, rows, entries):
        groups.setdefault(base_wear_mask(row, bits), []).append(entries[row["d3_id"]])
    lines = ["-- Generated by generate_sql.py from base_items.csv usable_by/designated_class and class_map.csv.",
             "-- ruling 2026-09-23 (diablocraft-class-parity Q3 option a): who may wear each base; only",
             "-- AllowableClass is written. -1 = the base names no class; 0 = none of its classes is playable yet."]
    for mask, found in sorted(groups.items()):
        found.sort()
        for offset in range(0, len(found), 200):
            lines.append(f"UPDATE `item_template` SET `AllowableClass`={mask} WHERE `entry` IN "
                         f"({','.join(map(str, found[offset:offset + 200]))});")
    return "\n".join(lines) + "\n", {mask: len(found) for mask, found in groups.items()}


def render_set_wear_class(path, applied_path):
    """Targeted AllowableClass UPDATEs that lock every piece of a class set to its set's class.

    Ruling 2026-10-03 (q-1003-28, diablocraft-9rhz): "Lock each piece to its set's class". The key is
    the one the drop fix reads, data/d3/set_classes.csv (set -> class, sourced from D3Planner), so
    no set or class is named here: a piece's mask is its own base mask (base_wear_mask) kept only
    where it is the set class's bit, 0 when that class is not in class_map.csv yet, and a
    classless set (empty class_key) keeps the base mask. items_0011 is applied and frozen, so this
    renders a delta against it: only entries whose mask changes get an UPDATE, and the base mask
    each starts from must equal what items_0011 holds, or generation stops. Returns the SQL and
    the number of entries it changes."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, strict=True))
    entries = read_base_item_ids(path.with_name("base_item_ids.csv"), {row["d3_id"] for row in rows})
    bits = class_bits(path, APPLIED_WEAR_CLASSES)
    with path.with_name("set_classes.csv").open(encoding="utf-8-sig", newline="") as stream:
        set_class = {row["set_name"]: row["class_key"] for row in csv.DictReader(stream, strict=True)}
    applied = {}
    for mask, found in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)",
                                  applied_path.read_text(encoding="utf-8")):
        for entry in found.split(","):
            applied[int(entry)] = int(mask)
    groups = {}
    for row in shipped_rows(path, rows, entries):
        if row["rarity"] != "set":
            continue
        if row["set_name"] not in set_class:
            raise DataError(f"set_classes.csv has no row for the set {row['set_name']!r}")
        entry, base = entries[row["d3_id"]], base_wear_mask(row, bits)
        if applied.get(entry) != base:
            raise DataError(f"{row['d3_id']}: base mask {base} is not what {applied_path.name} holds "
                            f"({applied.get(entry)}); the applied migration and the sheets disagree")
        key = set_class[row["set_name"]]
        if not key:
            continue
        mask = bits.get(key, 0) if base == -1 else base & bits.get(key, 0)
        if mask != base:
            groups.setdefault(mask, []).append(entry)
    lines = ["-- Generated by generate_sql.py from base_items.csv, class_map.csv and set_classes.csv.",
             "-- ruling 2026-10-03 (q-1003-28, diablocraft-9rhz): every piece of a class set is worn only by that",
             "-- set's class. A delta against items_0011 (applied, frozen): only AllowableClass, only set entries.",
             "-- 0 = the set's class is not playable yet."]
    for mask, found in sorted(groups.items()):
        found.sort()
        for offset in range(0, len(found), 200):
            lines.append(f"UPDATE `item_template` SET `AllowableClass`={mask} WHERE `entry` IN "
                         f"({','.join(map(str, found[offset:offset + 200]))});")
    return "\n".join(lines) + "\n", sum(len(found) for found in groups.values())


def wear_masks(path, bits):
    """{entry: AllowableClass} for every base once items_0011 and the set lock (items_0020) are applied, for the
    classes in `bits`: the two applied renders' rules in one place."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, strict=True))
    entries = read_base_item_ids(path.with_name("base_item_ids.csv"), {row["d3_id"] for row in rows})
    with path.with_name("set_classes.csv").open(encoding="utf-8-sig", newline="") as stream:
        set_class = {row["set_name"]: row["class_key"] for row in csv.DictReader(stream, strict=True)}
    masks = {}
    for row in shipped_rows(path, rows, entries):
        mask = base_wear_mask(row, bits)
        key = set_class.get(row["set_name"], "") if row["rarity"] == "set" else ""
        if key:
            mask = bits.get(key, 0) if mask == -1 else mask & bits.get(key, 0)
        masks[entries[row["d3_id"]]] = mask
    return masks


def render_added_wear_class(path, applied_paths):
    """AllowableClass UPDATEs for the bases whose mask changes when the classes added since items_0011 are playable.

    A delta against items_0011 and items_0020 (applied, frozen): the masks those two leave (read back from the files)
    must equal the rule over APPLIED_WEAR_CLASSES, or generation stops; then every entry whose mask over all of
    class_map.csv differs gets one UPDATE. Without it the Monk (class 12) wears nothing: a base listing it got 0 or a
    mask without its bit, and the start kit's CanEquipItem refuses it. Returns the SQL and the entries changed."""
    applied = {}
    for applied_path in applied_paths:
        for mask, found in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)",
                                      applied_path.read_text(encoding="utf-8")):
            for entry in found.split(","):
                applied[int(entry)] = int(mask)
    before = wear_masks(path, class_bits(path, APPLIED_WEAR_CLASSES))
    for entry, mask in before.items():
        if mask != -1 and applied.get(entry) != mask:
            raise DataError(f"entry {entry}: AllowableClass {mask} is not what the applied migrations hold "
                            f"({applied.get(entry)}); the applied migrations and the sheets disagree")
    after = wear_masks(path, class_bits(path))
    groups = {}
    for entry, mask in after.items():
        if mask != before[entry]:
            groups.setdefault(mask, []).append(entry)
    lines = ["-- Generated by generate_sql.py from base_items.csv, class_map.csv and set_classes.csv.",
             "-- A delta against items_0011 and items_0020 (applied, frozen): who may wear each base once the classes",
             "-- added since (the Monk, the Crusader, the Necromancer, the Demon Hunter, the Witch Doctor, the Shaman) are playable.",
             "-- Only AllowableClass, only changed entries."]
    for mask, found in sorted(groups.items()):
        found.sort()
        for offset in range(0, len(found), 200):
            lines.append(f"UPDATE `item_template` SET `AllowableClass`={mask} WHERE `entry` IN "
                         f"({','.join(map(str, found[offset:offset + 200]))});")
    return "\n".join(lines) + "\n", sum(len(found) for found in groups.values())


def check_weapon_classes(module_root):
    """Every weapon type base_items.csv uses must have a class (G1).

    weapon_classes.csv is the ONE sourced type -> weapon_class map (slots.js `affixes.weapon`;
    the roller and the Blacksmith preview both read the dc_weapon_class table it generates, so
    neither keeps its own type list). A weapon type missing there could roll no elemental
    damage and no bracket, so generation stops rather than ship an unclassed weapon.
    """
    with (module_root / "data/d3/base_items.csv").open(encoding="utf-8-sig", newline="") as stream:
        used = sorted({row["type"].strip() for row in csv.DictReader(stream, strict=True)
                       if row["slot"].strip() in {"onehand", "twohand"} and row["type"].strip()})
    with (module_root / "data/d3/weapon_classes.csv").open(encoding="utf-8-sig", newline="") as stream:
        known = {row["weapon_type"].strip() for row in csv.DictReader(stream, strict=True)}
    missing = [weapon_type for weapon_type in used if weapon_type not in known]
    if missing:
        raise DataError("weapon_classes.csv has no weapon_class for base_items type(s): "
                        + ", ".join(missing))
    return len(used)


def base_item_rows(text):
    """Every (entry, ...) row of a dc_base_item render, parsed with ''-escaped quotes.

    Only rows whose first field is an integer and whose width reaches preset_affixes are taken:
    the CREATE's `PRIMARY KEY (`entry`)` is not a row, and `DECIMAL(3,2)` parses as a two-field
    `(3,2)` match that must not be mistaken for one."""
    out = {}
    for match in re.finditer(r"\((?:[^()']|'(?:[^']|'')*')*\)", text):
        fields = next(csv.reader([match.group(0)[1:-1]], skipinitialspace=True, quotechar="'"))
        if fields and fields[0].strip().isdigit() and len(fields) > BASE_ITEM_PRESET_INDEX:
            out[int(fields[0])] = [field.strip() for field in fields]
    return out


# base_items.csv columns with entry first: 0 entry, 1 d3_id ... 11 weapon_aps, 12 preset_affixes ... 17 craft_only.
BASE_ITEM_PRESET_INDEX = 12
BASE_ITEM_CRAFT_ONLY_INDEX = 17
BASE_ITEM_USABLE_BY_INDEX = 6


def base_item_changes(module_root, base_item_sql, index):
    """(entry, value) for every dc_base_item row whose column `index` differs from the applied 0002 render.

    No entry of 0002 may be missing and the row width is unchanged; an entry added since (the added-base migration
    inserts it whole) is not compared."""
    applied = base_item_rows((module_root / "data/sql/db-world/updates/0002_dc_base_item.sql").read_text(encoding="utf-8"))
    current = base_item_rows(base_item_sql)
    if not applied.keys() <= current.keys():
        raise DataError("base_items entries removed against 0002_dc_base_item.sql: "
                        f"{sorted(applied.keys() - current.keys())[:10]}")
    current = {entry: current[entry] for entry in applied}
    changes = []
    for entry in sorted(current):
        old, new = applied[entry], current[entry]
        if len(old) != len(new):
            raise DataError(f"base item {entry}: row width changed against 0002_dc_base_item.sql")
        if new[index] != old[index]:
            changes.append((entry, new[index]))
    return changes


def emit_base_item_preset_delta(module_root, base_item_sql, updates):
    """A new migration carrying dc_base_item.preset_affixes corrections (G1).

    base_items.csv is the source; 0002_dc_base_item.sql is applied and immutable, and later
    migrations ALTER and UPDATE dc_base_item (crafting_0001/0003/0005/0007 change
    pool_version/designated_class, items_0015 adds the bottomless potion), so a re-render would
    reset them. Only preset_affixes is carried - the applied file's other columns are legitimately
    older than the CSV, so a whole-row comparison would refuse every regeneration. Every row's
    entry ids must be identical (nothing added or removed) and preset_affixes has no later owner."""
    changes = base_item_changes(module_root, base_item_sql, BASE_ITEM_PRESET_INDEX)
    if not changes:
        return None
    lines = ["-- Generated by generate_sql.py from base_items.csv: preset_affixes corrections.",
             "-- Targeted UPDATEs against the applied 0002_dc_base_item.sql; no other column moves,",
             "-- so the later dc_base_item migrations are untouched.",
             "-- G1 (diablocraft-weapon-elemental-build, applied as items_0017): the Atrophy / Hallowed Baton preset typos.",
             "-- Five set shoulders' allres respelled resall, the pool's id for All Resistance.",
             "SET NAMES utf8mb4;"]
    for entry, value in changes:
        lines.append(f"UPDATE `dc_base_item` SET `preset_affixes`={sql_text(value)} WHERE `entry`={entry};")
    target = updates / BASE_PRESET_MIGRATION
    write_migration(module_root, target, "\n".join(lines) + "\n")
    return target


def emit_base_item_craft_only_delta(module_root, base_item_sql, updates):
    """A new migration carrying dc_base_item.craft_only corrections (diablocraft-j6g2v).

    base_items.csv is the source; 0002_dc_base_item.sql is applied and immutable, so a craft_only edit
    in the CSV reaches the world DB as a targeted UPDATE against it, the way the preset_affixes delta
    does. Only craft_only is carried: the applied file's other columns are legitimately older than the
    CSV. The value is read as the rendered SQL literal's text, so 'yes' and 'no' round-trip."""
    changes = base_item_changes(module_root, base_item_sql, BASE_ITEM_CRAFT_ONLY_INDEX)
    if not changes:
        return None
    lines = ["-- Generated by generate_sql.py from base_items.csv: craft_only corrections.",
             "-- Targeted UPDATEs against the applied 0002_dc_base_item.sql; no other column moves,",
             "-- so the later dc_base_item migrations are untouched.",
             "SET NAMES utf8mb4;"]
    by_value = {}
    for entry, value in changes:
        by_value.setdefault(value, []).append(entry)
    for value in sorted(by_value):
        entries = ", ".join(str(entry) for entry in by_value[value])
        lines.append(f"UPDATE `dc_base_item` SET `craft_only`={sql_text(value)} WHERE `entry` IN ({entries});")
    target = updates / BASE_CRAFT_ONLY_MIGRATION
    write_migration(module_root, target, "\n".join(lines) + "\n")
    return target


def emit_base_item_usable_by_delta(module_root, base_item_sql, updates):
    """A new migration carrying dc_base_item.usable_by corrections (diablocraft-xnrvn.3).

    base_items.csv is the source; 0002_dc_base_item.sql is applied and immutable, so a class added to a type's
    usable_by list reaches the world DB as a targeted UPDATE against it, the way the preset_affixes and craft_only
    deltas do. The roller's drop rule reads this column (RollClass::Eligible), so without it a class listed in the
    sheet would never roll the type. Only usable_by is carried."""
    changes = base_item_changes(module_root, base_item_sql, BASE_ITEM_USABLE_BY_INDEX)
    if not changes:
        return None
    lines = ["-- Generated by generate_sql.py from base_items.csv: usable_by corrections.",
             "-- Targeted UPDATEs against the applied 0002_dc_base_item.sql; no other column moves,",
             "-- so the later dc_base_item migrations are untouched.",
             "SET NAMES utf8mb4;"]
    by_value = {}
    for entry, value in changes:
        by_value.setdefault(value, []).append(entry)
    for value in sorted(by_value):
        entries = ", ".join(str(entry) for entry in by_value[value])
        lines.append(f"UPDATE `dc_base_item` SET `usable_by`={sql_text(value)} WHERE `entry` IN ({entries});")
    target = updates / BASE_USABLE_BY_MIGRATION
    write_migration(module_root, target, "\n".join(lines) + "\n")
    return target


def row_fields(rest, expected, label):
    """The fields between `subclass` and the closing paren of one generated row.

    `rest` is TEMPLATE_ROW's fourth group. Only the unidentified shells render
    passes through here, and its name and description hold no comma (SHELL_NAME
    and f"An unidentified {rarity} {slot}."), so splitting on ", " is exact -
    and the field count is checked, so a comma added to either text trips here
    instead of silently shifting a column."""
    fields = [field.strip() for field in rest.split(",")]
    if len(fields) != expected:
        raise DataError(f"{label}: a row has {len(fields)} fields after subclass, expected {expected}")
    return fields


def render_subclass_delta(applied_path, current_sql, label, carry_fields=None, allow_added=False):
    """UPDATEs that move the applied item_template rows to the current render's
    subclass, and touch nothing else.

    Each UPDATE names its entries, their class and the subclass they had, so it
    changes exactly the rows the applied migration wrote and is a no-op when
    rerun. Only subclass may differ: any other column difference, or a row
    added or dropped, is a change this migration was not approved to carry,
    and generation stops naming it.

    `carry_fields` names the further columns the caller has decided to carry, as
    (index among the fields after subclass, name, fields_in_a_row) each. Those
    differences come back as the third element, {entry: {name: (old, new)}}, for
    the caller to ship as a migration of its own - the unidentified shells' carry
    limit, 2026-10-02 (diablocraft-unid-shell-unique) - and every other column is
    still refused.

    `allow_added` lets the current render hold entries the applied file never had (a base item added since, which its
    own migration inserts): only the applied entries are compared.
    """
    applied = {int(e): (int(c), int(sc), rest) for e, c, sc, rest in
               TEMPLATE_ROW.findall(applied_path.read_text(encoding="utf-8"))}
    current = {int(e): (int(c), int(sc), rest) for e, c, sc, rest in TEMPLATE_ROW.findall(current_sql)}
    if not applied or not current:
        raise DataError(f"{label}: could not read item_template rows to compare")
    if allow_added:
        if not applied.keys() <= current.keys():
            raise DataError(f"{label}: entries removed against {applied_path.name}: "
                            f"{sorted(applied.keys() - current.keys())[:10]}")
        current = {entry: current[entry] for entry in applied}
    if applied.keys() != current.keys():
        raise DataError(f"{label}: entries added or removed against {applied_path.name}: "
                        f"{sorted(applied.keys() ^ current.keys())[:10]}")
    carry = {}
    groups = {}
    for entry in sorted(current):
        (old_class, old_sub, old_rest), (new_class, new_sub, new_rest) = applied[entry], current[entry]
        if carry_fields:
            old_fields = row_fields(old_rest, carry_fields[0][2], label) if carry_fields else None
            new_fields = row_fields(new_rest, carry_fields[0][2], label) if carry_fields else None
            for index, name, _expected in carry_fields:
                if old_fields[index] != new_fields[index]:
                    carry.setdefault(entry, {})[name] = (old_fields[index], new_fields[index])
                    old_fields[index] = new_fields[index] = ""
            old_rest, new_rest = ", ".join(old_fields), ", ".join(new_fields)
        if (old_class, old_rest) != (new_class, new_rest):
            raise DataError(f"{label}: entry {entry} differs from {applied_path.name} beyond subclass")
        if old_sub != new_sub:
            groups.setdefault((new_class, old_sub, new_sub), []).append(entry)
    lines = [f"-- Generated by generate_sql.py: {label}.",
             f"-- Targeted subclass UPDATEs against the applied {applied_path.name}; every other",
             "-- column (Flags, ItemLevel, MaxDurability from crafting_0003, ...) is left as it is.",
             "-- ruling 2026-09-23 (diablocraft-class-parity Q1 option B): armor is Miscellaneous."]
    for (item_class, old_sub, new_sub), entries in sorted(groups.items()):
        for offset in range(0, len(entries), 200):
            chunk = ",".join(map(str, entries[offset:offset + 200]))
            lines.append(f"UPDATE `item_template` SET `subclass`={new_sub} WHERE `class`={item_class} "
                         f"AND `subclass`={old_sub} AND `entry` IN ({chunk});")
    return "\n".join(lines) + "\n", sum(len(e) for e in groups.values()), carry
def next_items_number(updates, module_root):
    """The next free items_<NNNN> number, the item system's own series (above any dev reserves)."""
    number = reserved_number(module_root, "items")
    for path in updates.glob("items_*_*.sql"):
        match = re.match(r"items_(\d+)_", path.name)
        if match:
            number = max(number, int(match.group(1)))
    return number + 1


# The columns of one shell row after class/subclass, and the one the carry-limit
# fix moves: name, displayid, Quality, InventoryType, ItemLevel, RequiredLevel,
# maxcount, stackable, bonding, spellid_1, spelltrigger_1, description.
SHELL_CARRY_FIELDS = ((6, "maxcount", 12),)
SHELL_NO_LIMIT_STEM = "unidentified_shells_no_limit"


def emit_shell_no_limit(module_root, carry):
    """The migration that removes the shells' carry limit from a live database.

    items_0007/items_0010 are applied and immutable and their render is where the
    limit was written, so the difference against them is permanent: this writes
    the change once and then leaves it alone (a rerun finds the file already
    current), and it is a no-op on a database that already has maxcount 0 because
    each UPDATE names the value it replaces.
    """
    if not carry:
        return None
    updates = module_root / "data/sql/db-world/updates"
    entries = sorted(carry)
    columns = sorted({name for changes in carry.values() for name in changes})
    replaces, sets = [], []
    for name in columns:
        moves = {changes[name] for changes in carry.values() if name in changes}
        if len(moves) != 1:
            raise DataError(f"unidentified shells: {name} moves more than one value at a time")
        old_value, new_value = moves.pop()
        sets.append(f"`{name}`={new_value}")
        replaces.append(f"`{name}`={old_value}")
    for entry in entries:
        for name in columns:
            if name not in carry[entry]:
                raise DataError(f"unidentified shells: entry {entry} changes {name} but the rest do not")
    if not sets:
        return None
    last = shell_entry(len(SHELL_SLOTS) - 1, len(SHELL_RARITIES) - 1)
    lines = [
        "-- Generated by generate_sql.py: unidentified shells carry no limit.",
        "-- P1 diablocraft-unid-shell-unique (ruling 2026-10-02): every shell",
        f"-- {SHELL_ENTRY_BASE}-{last} was written maxcount 1 (Unique), so a second shell of the",
        "-- same slot and rarity could not be picked up (EQUIP_ERR_ITEM_MAX_COUNT,",
        "-- which the client draws as the red \"Inventory is full.\"). D3 lets you",
        "-- carry any number of them, each in its own bag slot: maxcount 0. stackable",
        "-- is left at 1, one per slot - 0 would mean unlimited stacking in this core.",
        "-- items_0007_unidentified_shells.sql / items_0010_unidentified_shells_misc_armor.sql",
        "-- are applied and immutable, so the change lands here.",
        "SET NAMES utf8mb4;",
    ]
    for offset in range(0, len(entries), 200):
        chunk = ",".join(map(str, entries[offset:offset + 200]))
        lines.append(f"UPDATE `item_template` SET {', '.join(sets)} "
                     f"WHERE {' AND '.join(replaces)} AND `entry` IN ({chunk});")
    content = "\n".join(lines) + "\n"
    existing = sorted(updates.glob(f"items_*_{SHELL_NO_LIMIT_STEM}.sql"))
    target = existing[-1] if existing else updates / f"items_{next_items_number(updates, module_root):04d}_{SHELL_NO_LIMIT_STEM}.sql"
    encoded = content.encode("utf-8")
    if target.is_file() and target.read_bytes() == encoded:
        return None
    return target if write_migration(module_root, target, content) else None


def item_description(power, flavour, source="item"):
    """The native description for one base: (text, status).

    status is "" (shipped whole), "flavour_dropped" or "power_too_long". A token
    the fill step missed stops the build (text_guard), naming `source`.
    CRLF becomes LF: the client wants one."""
    power, flavour = power.replace("\r\n", "\n").strip(), flavour.replace("\r\n", "\n").strip()
    refuse_unfilled(source, power, flavour)
    if len(power) > DESCRIPTION_LIMIT:
        return "", "power_too_long"
    if not flavour:
        return power, ""
    full = power + "\n" + flavour if power else flavour
    if len(full) <= DESCRIPTION_LIMIT:
        return full, ""
    return power, "flavour_dropped"


def render_item_descriptions(path, only=None):
    """Targeted `description` UPDATEs for every base that has power or flavour text.

    The text is dc_item_tooltip's (generate_crafting.item_tooltip_rows), so the
    addon and the native tooltip read one source. Returns the SQL and a report:
    text count, longest power+flavour pair, the flavours dropped and the powers
    too long to ship. `only` names the entries to cover instead of the shipped ones."""
    from generate_crafting import item_tooltip_rows, ROOT as REPO
    reference = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))
    tooltips = item_tooltip_rows(reference)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, strict=True))
    entries = read_base_item_ids(path.with_name("base_item_ids.csv"), {row["d3_id"] for row in rows})
    lines = ["-- Generated by generate_sql.py from dc_item_tooltip (reference/d3planner data.json).",
             "-- diablocraft-item-descriptions: a legendary's power and flavour text as the item's own",
             "-- description, so every window draws it. Only `description` is written."]
    report = {"texts": 0, "longest": (0, ""), "flavour_dropped": [], "power_too_long": []}
    for row in sorted(scoped_rows(path, rows, entries, only), key=lambda r: entries[r["d3_id"]]):
        found = tooltips.get(row["d3_id"])
        if not found or not (found[2] or found[3]):
            continue
        power, flavour = found[2], found[3]
        pair = len(power) + len(flavour) + (1 if power and flavour else 0)
        report["longest"] = max(report["longest"], (pair, row["d3_id"]))
        text, status = item_description(power, flavour, row["d3_id"])
        if status:
            report[status].append(row["d3_id"])
        if not text:
            continue
        report["texts"] += 1
        lines.append(f"UPDATE `item_template` SET `description`={sql_text(text)} WHERE `entry`={entries[row['d3_id']]};")
    return "\n".join(lines) + "\n", report


def read_base_item_costs(path, d3_ids):
    """The D3 `ItemTable.Cost` of every base item: base_item_costs.csv, one line per d3_id.

    Verified D3 data with its pin on every line (`source`). A cost that is not a whole number of 0 or
    more, a line with no source, a d3_id twice, a d3_id that is no base item and a base item with no
    line each stop generation: a price is never filled in from a default."""
    header, rows = read_csv(path, {"d3_id", "d3_gamebalance_id", "match_type", "d3_cost", "source"})
    index = {column: position for position, column in enumerate(header)}
    costs = {}
    for line, row in rows:
        d3_id = row[index["d3_id"]]
        value = number(row[index["d3_cost"]], False, path, line, row, "d3_cost")
        if value is None or value != value.to_integral_value() or value < 0:
            fail(path, line, row, "d3_cost must be a whole number of 0 or more")
        if not row[index["source"]].strip():
            fail(path, line, row, "source: a cost names where it came from")
        if d3_id in costs:
            fail(path, line, row, f"duplicate d3_id {d3_id!r}")
        if d3_id not in d3_ids:
            fail(path, line, row, f"{d3_id!r} is not a base item")
        costs[d3_id] = int(value)
    missing = sorted(set(d3_ids) - costs.keys())
    if missing:
        fail(path, 1, header, "no d3_cost for " + ", ".join(missing[:5])
             + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""))
    return costs


def render_sell_price(path, only=None):
    """Targeted `SellPrice` UPDATEs for every base item template (diablocraft-item-base-sell-price).

    Ruling 2026-10-04 (q-1004-08, option a: "a base price and then eventually we can move to the
    correct price model"): a vendor pays D3's base price for an item, floor(ItemTable.Cost / divisor),
    the cost from base_item_costs.csv and the divisor from economy.csv item_sell_divisor (D3's vendor
    pays 1/25, docs/research/item-sell-prices.md 2.2). Only SellPrice is written: BuyPrice stays as
    the templates have it, and an item's rolled affixes add nothing (D3's full price, base plus each
    affix's cost, is a later task). The stock core refuses to buy an item worth 0, so this is what
    lets a vendor buy a base item at all. Returns the SQL and the number of items priced."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        d3_ids = {row["d3_id"] for row in csv.DictReader(stream, strict=True)}
    entries = read_base_item_ids(path.with_name("base_item_ids.csv"), d3_ids)
    costs = read_base_item_costs(path.with_name("base_item_costs.csv"), d3_ids)
    divisor = tunable_integer("economy", "item_sell_divisor", minimum=1, module=path.parents[2])
    # ponytail: the base cost only; D3 adds every rolled affix's cost, which needs server C++ and a
    # per-item price, so a rare sells like its white base. The designer's later bead (q-1004-08).
    scope = shipped_entries(path) if only is None else only
    groups = {}
    for d3_id, cost in costs.items():
        if scope is None or entries[d3_id] in scope:
            groups.setdefault(cost // divisor, []).append(entries[d3_id])
    lines = ["-- Generated by generate_sql.py from base_item_costs.csv and economy.csv item_sell_divisor.",
             "-- ruling 2026-10-04 (q-1004-08, diablocraft-item-base-sell-price): a vendor pays D3's base price,",
             f"-- floor(ItemTable.Cost / {divisor}). Only SellPrice is written; BuyPrice stays as it is."]
    for price, found in sorted(groups.items()):
        found.sort()
        for offset in range(0, len(found), 200):
            lines.append(f"UPDATE `item_template` SET `SellPrice`={price} WHERE `entry` IN "
                         f"({','.join(map(str, found[offset:offset + 200]))});")
    return "\n".join(lines) + "\n", sum(len(found) for found in groups.values())


# Where the client hangs a sheathed weapon (diablocraft-b3gs1, ruling 2026-10-11: weapons showed only drawn).
# item_template.sheath by (class, subclass, InventoryType), each the commonest non-zero value among the stock
# items of that kind (entry < 60000); a kind stock has no item of (bows, crossbows and wands are ranged-slot
# items in stock, ours are hand weapons) takes its InventoryType's commonest value. test_item_sheath.py
# rederives every value from the stock rows. Every other base item keeps 0.
SHEATH = {
    (2, 0, 13): 3, (2, 1, 17): 1, (2, 2, 17): 1, (2, 4, 13): 3, (2, 5, 17): 1, (2, 6, 17): 2,
    (2, 7, 13): 3, (2, 8, 17): 1, (2, 10, 17): 2, (2, 13, 13): 7, (2, 14, 13): 7, (2, 15, 13): 3,
    (2, 18, 13): 3, (2, 18, 17): 1, (2, 19, 13): 3,
    (4, 0, 14): 4, (4, 0, 23): 7,
}


def render_sheath(path, only=None):
    """Targeted `sheath` UPDATEs for every weapon and off-hand base item (diablocraft-b3gs1). The templates'
    own migration is applied and frozen, so this is a delta like SellPrice. Raises on a weapon or off-hand kind
    SHEATH has no value for. Returns the SQL and the number of items written."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, strict=True))
    entries = read_base_item_ids(path.with_name("base_item_ids.csv"), {row["d3_id"] for row in rows})
    scope = shipped_entries(path) if only is None else only
    groups = {}
    for line, row in enumerate(rows, start=2):
        if row["slot"] not in ("onehand", "twohand", "offhand"):
            continue
        if scope is not None and entries[row["d3_id"]] not in scope:
            continue
        kind = classify(row, path, line, row)
        if kind not in SHEATH:
            fail(path, line, row, f"no sheath for (class, subclass, InventoryType) {kind}")
        groups.setdefault(SHEATH[kind], []).append(entries[row["d3_id"]])
    lines = ["-- Generated by generate_sql.py from base_items.csv and its SHEATH table (diablocraft-b3gs1); never edit.",
             "-- Where a sheathed weapon hangs: each kind takes the stock items' value. Only sheath is written."]
    for sheath, found in sorted(groups.items()):
        found.sort()
        for offset in range(0, len(found), 200):
            lines.append(f"UPDATE `item_template` SET `sheath`={sheath} WHERE `entry` IN "
                         f"({','.join(map(str, found[offset:offset + 200]))});")
    return "\n".join(lines) + "\n", sum(len(found) for found in groups.values())


BASE_ITEM_COLUMNS = (
    "item_level level_req weapon_min weapon_max weapon_aps", "",
    "d3_id d3_name slot type rarity usable_by preset_affixes set_name source_file pool_version designated_class craft_only")

# Our reserved item_template range (05 §10). Entries are assigned by sorted
# d3_id so a rerun never renumbers an item that already exists in the world DB.
ENTRY_BASE = 100000

# The constants below are the core's own enums, read from
# azerothcore-wotlk/src/server/game/Entities/Item/ItemTemplate.h.
ITEM_CLASS_WEAPON, ITEM_CLASS_ARMOR = 2, 4
ARMOR_MISC, ARMOR_CLOTH, ARMOR_PLATE, ARMOR_SHIELD = 0, 1, 4, 6
INVTYPE_SHIELD, INVTYPE_HOLDABLE = 14, 23
INVENTORY_TYPE = {
    "head": 1, "neck": 2, "shoulders": 3, "torso": 5, "waist": 6, "legs": 7,
    "feet": 8, "wrists": 9, "hands": 10, "finger": 11, "onehand": 13, "twohand": 17,
}
# D3 rarity -> WoW quality, picked so the client's link colour matches the D3
# colour in I4. The tooltip colour itself is ours (AIO), never this flag. D3's
# yellow has no WoW equivalent, but no base item is Rare - rare is a roll
# outcome, never a base. "ethereal" is not named in I4; it is a Legendary-tier
# quality in the source data, so it takes the Legendary colour.
QUALITY = {"": 1, "magic": 3, "set": 2, "legendary": 5, "ethereal": 5}
# D3 weapon type -> nearest WoW weapon subclass, so the client gives the item a
# weapon skill a Warrior actually has. Types with no melee equivalent (offhand
# caster weapons, Demon Hunter launchers) fall through to WEAPON_MISC.
WEAPON_SUBCLASS = {
    "Axe": 0, "Flying Axe": 0, "Scythe": 0,
    "Two-Handed Axe": 1,
    "Bow": 2, "Hydra Bow": 2, "Ballista": 2,
    "Mace": 4, "Mighty Weapon": 4, "Mighty Scepter": 4, "Flail": 4, "Caduceus": 4, "Ritual Mace": 4,
    "Two-Handed Mace": 5, "Two-Handed Mighty Weapon": 5, "Two-Handed Flail": 5,
    "Polearm": 6, "Two-Handed Scythe": 6,
    "Sword": 7, "Champion Sword": 7, "Ancient Blade": 7, "Wrist Sword": 7, "Cinquedeas": 7,
    "Two-Handed Sword": 8, "Colossus Blade": 8,
    "Staff": 10, "Daibo": 10, "Archon Staff": 10,
    "Fist Weapon": 13, "Battle Cestus": 13, "Greater Talons": 13,
    "Dagger": 15, "Ceremonial Knife": 15, "Bone Knife": 15, "Legend Spike": 15,
    # WoW subclass 17 is obsolete and resolves to the rogue Assassination skill.
    # WoW polearms also prohibit any off-hand, even with InventoryType=onehand.
    # D3 spears are one-handed: use Swords proficiency, retaining spear displays.
    "Spear": 7, "Hyperion Spear": 7,
    "Crossbow": 18, "Hand Crossbow": 18, "Repeating Crossbow": 18,
    "Wand": 19, "Grave Wand": 19,
}
WEAPON_SUBCLASS_MISC = 14
# crafting_0003 sets this on the Flags of every base item (the item_template Flags bit, 0x8000000).
BASE_ITEM_FLAGS = 134217728
SHIELDS = {"Shield", "Crusader Shield"}
# Only these item_template columns are written; every other column keeps its
# schema default, which is exactly what "zero WoW stats" (01-stats S2) needs -
# no stat_type/stat_value pair is emitted at all.
TEMPLATE_COLUMNS = ("entry", "class", "subclass", "name", "displayid", "Quality", "InventoryType",
                    "ItemLevel", "RequiredLevel", "dmg_min1", "dmg_max1", "dmg_type1", "delay")


# --- unidentified shells (decisions.md 2026-09-17) --------------------------
#
# A legendary or set drop is delivered as one of these, not as its real base
# item. The real item lives only in dc_item_unidentified until the player
# identifies it, so the client is never told what it is - there is nothing in
# the item template to data-mine and nothing for the tooltip to leak.
#
# One row per (inventory type, rarity): the inventory type is what makes the
# client draw the right slot line ("Head", "Two-Hand"), and the rarity is what
# gives the bag icon the right border colour without any client work. The AIO
# tooltip draws "Unidentified" in the same colour on top.
#
# The bag icon needs a REAL displayid. The 3.3.5 client resolves it as
# displayid -> ItemDisplayInfo.dbc -> InventoryIcon; displayid 0 has no row and
# draws nothing (the "empty box with a rarity border" bug, 2026-09-17), and it
# does NOT fall back to the class/subclass icon. SHELL_DISPLAY_ID is one generic
# question mark with no model, so it shows something and leaks nothing.
#
# spellid_1 is the identify shell, and it is what draws the native green
# "Use: Right click to identify this item" line and a real cast bar - but only
# once the rebuilt client patch has shipped it, because both come from the
# CLIENT's Spell.dbc. It does NOT fire on a right-click while the shell is
# equippable: the 3.3.5 client equips an equippable item and the Use spell
# never wins. The Torment inventory screen sends Identify itself; in the default
# WoW bags the client equips and the server refuses with "Identify it first."
# Whether shells should stop being equippable is the designer's call.
SHELL_ENTRY_BASE = 199900
SHELL_SPELL_ID = 81203            # generate_spells.py IDENTIFY_ITEM_SPELL
# ItemDisplayInfo.dbc row 1240: InventoryIcon INV_Misc_QuestionMark, no model.
SHELL_DISPLAY_ID = 1240
SHELL_NAME = "Unidentified"
# (slot label, InventoryType, class, subclass) - the same classification
# classify() gives the real items, so the shell sits in the same slot. Armor
# shells are Miscellaneous like the real armor (diablocraft-class-parity).
SHELL_SLOTS = (
    ("head", 1, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("neck", 2, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("shoulders", 3, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("torso", 5, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("waist", 6, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("legs", 7, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("feet", 8, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("wrists", 9, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("hands", 10, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("finger", 11, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("onehand", 13, ITEM_CLASS_WEAPON, WEAPON_SUBCLASS_MISC),
    ("shield", INVTYPE_SHIELD, ITEM_CLASS_ARMOR, ARMOR_MISC),
    ("twohand", 17, ITEM_CLASS_WEAPON, WEAPON_SUBCLASS_MISC),
    ("offhand", INVTYPE_HOLDABLE, ITEM_CLASS_ARMOR, ARMOR_MISC),
)
# QUALITY above maps the D3 rarity to the WoW colour flag; only these two ever
# arrive as a shell, because rares and below are rolled at drop as before.
SHELL_RARITIES = ("legendary", "set")


def shell_entry(slot_index, rarity_index):
    return SHELL_ENTRY_BASE + slot_index * len(SHELL_RARITIES) + rarity_index


def render_unidentified_shells():
    """item_template rows for every (slot, rarity) shell, and nothing else."""
    columns = ("entry", "class", "subclass", "name", "displayid", "Quality", "InventoryType",
               "ItemLevel", "RequiredLevel", "maxcount", "stackable", "bonding",
               "spellid_1", "spelltrigger_1", "description")
    rows = []
    for slot_index, (slot, inventory, item_class, subclass) in enumerate(SHELL_SLOTS):
        for rarity_index, rarity in enumerate(SHELL_RARITIES):
            rows.append((
                shell_entry(slot_index, rarity_index), item_class, subclass, SHELL_NAME,
                # A real displayid so the bag draws a "?"; 0 draws nothing at
                # all. SHELL_DISPLAY_ID has no model, so the base item cannot be
                # read from it.
                SHELL_DISPLAY_ID, QUALITY[rarity], inventory,
                # Item level and required level stay 0: both are the real
                # item's and neither may be visible before the roll.
                # maxcount 0: a shell has no carry limit. It was 1 (Unique)
                # until 2026-10-02, which refused a second shell of the same slot
                # and rarity with EQUIP_ERR_ITEM_MAX_COUNT - the designer could not pick
                # up a second set head (P1 diablocraft-unid-shell-unique). D3
                # lets you carry any number, each in its own bag slot.
                # stackable stays 1, which IS one per slot: the pinned core's
                # ItemTemplate::GetMaxStackSize() returns 0x7FFFFFFE when
                # Stackable <= 0 (ItemTemplate.h:729), so 0 would mean unlimited
                # stacking, not none.
                0, 0, 0, 1,
                # No bind on pickup - a shell can be traded like the item it
                # will become; nothing here decides the trading rule.
                0,
                SHELL_SPELL_ID, 0,
                f"An unidentified {rarity} {slot}.",
            ))
    lines = [
        "-- Generated by generate_sql.py; do not hand-edit.",
        "-- decisions.md 2026-09-17: legendary and set drops arrive as unrolled",
        "-- shells. The real base item is in dc_item_unidentified, never here.",
        "SET NAMES utf8mb4;",
        f"DELETE FROM `item_template` WHERE `entry` BETWEEN {SHELL_ENTRY_BASE} "
        f"AND {shell_entry(len(SHELL_SLOTS) - 1, len(SHELL_RARITIES) - 1)};",
        "INSERT INTO `item_template` (" + ", ".join(f"`{c}`" for c in columns) + ") VALUES",
    ]
    def value(field):
        return sql_text(field) if isinstance(field, str) else str(field)

    lines.append(",\n".join("(" + ", ".join(value(field) for field in row) + ")" for row in rows) + ";")
    return "\n".join(lines) + "\n", len(rows)


def classify(fields, path, line, row):
    """Return (class, subclass, InventoryType) for one base item.

    Every armor piece, shields included, is Miscellaneous armor (the designer,
    2026-09-23, diablocraft-class-parity Q1 option B): D3 has no armor
    proficiencies, and WoW's Plate/Cloth subclasses asked for a skill a Mage
    does not have, while stock code lets only a Paladin, Warrior or Shaman
    equip the Shield subclass (PlayerStorage.cpp:2463). The inventory type
    still puts the item in its slot, and D3 block is the module's own
    (dc_combat.cpp), never WoW's, so a shield loses nothing."""
    slot, kind = fields["slot"], fields["type"]
    if slot in ("onehand", "twohand"):
        return ITEM_CLASS_WEAPON, WEAPON_SUBCLASS.get(kind, WEAPON_SUBCLASS_MISC), INVENTORY_TYPE[slot]
    if slot == "offhand":
        if kind in SHIELDS:
            return ITEM_CLASS_ARMOR, ARMOR_MISC, INVTYPE_SHIELD
        return ITEM_CLASS_ARMOR, ARMOR_MISC, INVTYPE_HOLDABLE
    if slot not in INVENTORY_TYPE:
        fail(path, line, row, f"slot: no inventory type for {slot!r}")
    return ITEM_CLASS_ARMOR, ARMOR_MISC, INVENTORY_TYPE[slot]


def read_item_displays(path):
    required = {"slot", "type", "wow_item_name", "wow_item_id", "wow_display_id",
                "inventory_type", "fit", "notes", "source_url"}
    header, rows = read_csv(path, required)
    displays = {}
    for line, row in rows:
        fields = dict(zip(header, row))
        key = fields["slot"], fields["type"]
        if key in displays:
            fail(path, line, row, "duplicate slot/type display mapping")
        value = number(fields["wow_display_id"], False, path, line, row, "wow_display_id")
        if value is None or value != value.to_integral_value() or not 0 < value < 2**32:
            fail(path, line, row, "wow_display_id must be a positive unsigned integer")
        displays[key] = int(value)
    return displays


def read_base_item_ids(path, d3_ids):
    """The published `d3_id` -> `item_entry` map: seeded once, append-only after.

    An entry id used to be the row's position in d3_id order, so inserting one
    base item renumbered every item sorting after it - and with them every
    stash row, every equipped item and every mail attachment a character holds.
    The sheet is the contract now. Adding a base item means adding a line here
    with the next free entry; it never means renumbering a line that shipped.
    """
    header, rows = read_csv(path, {"d3_id", "item_entry"})
    index = {column: position for position, column in enumerate(header)}
    mapping, owner = {}, {}
    for line, row in rows:
        d3_id = row[index["d3_id"]]
        value = number(row[index["item_entry"]], False, path, line, row, "item_entry")
        if value is None or value != value.to_integral_value():
            fail(path, line, row, "item_entry must be a whole number")
        entry = int(value)
        # Staying below the shell block keeps an append from colliding with the
        # unidentified shells, which own their own range from SHELL_ENTRY_BASE.
        if not ENTRY_BASE <= entry < SHELL_ENTRY_BASE:
            fail(path, line, row,
                 f"item_entry must be between {ENTRY_BASE} and {SHELL_ENTRY_BASE - 1}")
        if d3_id in mapping:
            fail(path, line, row, f"duplicate d3_id {d3_id!r}")
        if entry in owner:
            fail(path, line, row, f"item_entry {entry} is already {owner[entry]!r}")
        mapping[d3_id] = entry
        owner[entry] = d3_id
    missing = sorted(set(d3_ids) - mapping.keys())
    if missing:
        fail(path, 1, header, "no item_entry for " + ", ".join(missing[:5])
             + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""))
    return mapping


# A published `dc_base_item` row, and the shape of any line that claims to be
# one. The second pattern exists so that a row this file cannot parse is a
# failure rather than a row that silently does not get checked.
PUBLISHED_ROW = re.compile(r"^\((\d+), '((?:[^']|'')*)', ", re.M)
PUBLISHED_ROW_CANDIDATE = re.compile(r"^\(", re.M)


def check_published_item_entries(mapping, published, sheet):
    """A shipped entry id cannot change value, only be joined by a new one.

    The already-applied `dc_base_item` migration is the record of what the
    database was told, so it is the thing the sheet has to still agree with.
    It is read before the generator overwrites it, which is why a renumbering
    fails instead of quietly republishing itself.

    Every way of NOT having that record is an error, never a pass. A check
    whose authority is missing, unreadable, empty or only partly parsed is not
    a weaker check, it is no check at all - and it would fail open exactly when
    something had already gone wrong with the migration. The coverage test is
    the point of the second pattern: matching one row proves the regex works,
    not that it read every row the file holds.
    """
    if not published.exists():
        raise DataError(
            f"{published}: the published dc_base_item migration is missing. It is the "
            f"record of which entry ids have already shipped, and {sheet} cannot be "
            f"checked for renumbering without it. Restore it rather than generating.")
    try:
        text = published.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise DataError(f"{published}: the published dc_base_item migration cannot be "
                        f"read as the append-only authority: {error}") from error
    if "INSERT INTO `dc_base_item`" not in text:
        raise DataError(f"{published}: this is not a dc_base_item migration - it has no "
                        f"INSERT INTO `dc_base_item`, so it cannot be the authority for "
                        f"published entry ids")
    rows = PUBLISHED_ROW.findall(text)
    candidates = len(PUBLISHED_ROW_CANDIDATE.findall(text))
    if not rows:
        raise DataError(f"{published}: no published (entry, d3_id) rows could be parsed "
                        f"out of the dc_base_item migration; it is empty or malformed, "
                        f"and an unparsed authority is not a passed check")
    if len(rows) != candidates:
        raise DataError(f"{published}: parsed {len(rows)} published rows but the file has "
                        f"{candidates} lines that begin a row; {candidates - len(rows)} "
                        f"could not be read, so the published ids are not fully checked")
    seen = {}
    for entry, raw in rows:
        entry, d3_id = int(entry), raw.replace("''", "'")
        if d3_id in seen:
            raise DataError(f"{published}: {d3_id!r} is published twice, as item_entry "
                            f"{seen[d3_id]} and {entry}; the authority is inconsistent")
        seen[d3_id] = entry
        if d3_id not in mapping:
            raise DataError(f"{sheet}: {d3_id!r} was published as item_entry {entry} "
                            f"and has no line; a published id is never removed")
        if mapping[d3_id] != entry:
            raise DataError(f"{sheet}: {d3_id!r} was published as item_entry {entry} "
                            f"but the sheet says {mapping[d3_id]}; published ids are "
                            f"append-only and never renumbered")
    return len(rows)


def base_item_data(path):
    """The parsed base_items.csv every base-item render starts from: header, column groups, the rows in d3_id order,
    their published entry ids and the item_template row of each (entry first, TEMPLATE_COLUMNS after)."""
    numeric, percentages, text = (set(group.split()) for group in BASE_ITEM_COLUMNS)
    header, rows = read_csv(path, numeric | percentages | text)
    index = {column: position for position, column in enumerate(header)}
    if len({row[index["d3_id"]] for _, row in rows}) != len(rows):
        fail(path, 1, header, "d3_id is not unique; entry ids would not be stable")
    ordered = sorted(rows, key=lambda item: item[1][index["d3_id"]])
    sheet = path.with_name("base_item_ids.csv")
    entries = read_base_item_ids(sheet, {row[index["d3_id"]] for _, row in rows})
    check_published_item_entries(
        entries, path.parents[1] / "sql/db-world/updates/0002_dc_base_item.sql", sheet)
    displays = read_item_displays(path.with_name("item_display.csv"))

    def integer(row, column, line, default=0):
        value = row[index[column]]
        if value == "":
            return default
        return int(number(value, False, path, line, row, column))

    templates, defaulted = {}, set()
    for line, row in ordered:
        fields = {column: row[index[column]] for column in header}
        item_class, subclass, inventory = classify(fields, path, line, row)
        if item_class == ITEM_CLASS_WEAPON and fields["type"] not in WEAPON_SUBCLASS:
            defaulted.add(fields["type"])
        if fields["rarity"] not in QUALITY:
            fail(path, line, row, f"rarity: no quality mapping for {fields['rarity']!r}")
        aps = number(fields["weapon_aps"], False, path, line, row, "weapon_aps")
        # D3 stores attacks per second; the client wants the swing time in ms.
        delay = int(round(1000 / float(aps))) if aps else 0
        display = displays.get((fields["slot"], fields["type"]))
        if display is None:
            fail(path, line, row, "no item_display.csv mapping for this slot/type")
        templates[entries[fields["d3_id"]]] = (
            entries[fields["d3_id"]], item_class, subclass, sql_text(fields["d3_name"]), display,
            QUALITY[fields["rarity"]], inventory,
            integer(row, "item_level", line), integer(row, "level_req", line),
            integer(row, "weapon_min", line), integer(row, "weapon_max", line), 0, delay)
    if defaulted:
        print("  weapon types defaulted to WEAPON_MISC: " + ", ".join(sorted(defaulted)))
    return dict(path=path, numeric=numeric, header=header, index=index, ordered=ordered, entries=entries,
                templates=templates)


def base_item_value_rows(data, wanted):
    """(columns, definitions, converted) of the dc_base_item rows named in `wanted`, in d3_id order: the INSERT's
    column list, the CREATE's column definitions and, per column, the SQL literals of those rows."""
    path, header, index, numeric = data["path"], data["header"], data["index"], data["numeric"]
    ordered = [item for item in data["ordered"] if data["entries"][item[1][index["d3_id"]]] in wanted]
    definitions = ["  `entry` BIGINT NOT NULL"]
    columns = ["`entry`"]
    converted = [[str(data["entries"][row[index["d3_id"]]]) for _, row in ordered]]
    for column in header:
        columns.append(f"`{column}`")
        if column in numeric:
            values = [number(row[index[column]], False, path, line, row, column) for line, row in ordered]
            converted.append(["NULL" if item is None else format(item, "f") for item in values])
            definitions.append(f"  `{column}` {numeric_type(values, column)} NULL")
        else:
            converted.append([sql_text(row[index[column]]) for _, row in ordered])
            definitions.append(f"  `{column}` LONGTEXT NOT NULL")
    return columns, definitions, converted, ordered


def render_base_items(path):
    """Emit dc_base_item (carrying our entry ids) and the item_template rows."""
    data = base_item_data(path)
    entries, templates = data["entries"], data["templates"]
    columns, definitions, converted, ordered = base_item_value_rows(data, set(entries.values()))
    definitions.append("  PRIMARY KEY (`entry`)")
    lines = [
        f"-- Generated from data/d3/{path.name}; edit the CSV and rerun generate_sql.py.",
        f"-- Apply to the world database. Entries are assigned by sorted d3_id from {ENTRY_BASE}.",
        "SET NAMES utf8mb4;",
        "DROP TABLE IF EXISTS `dc_base_item`;",
        "CREATE TABLE `dc_base_item` (",
        ",\n".join(definitions),
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
    ]
    for offset in range(0, len(ordered), 100):
        lines.append(f"INSERT INTO `dc_base_item` ({', '.join(columns)}) VALUES")
        lines.append(",\n".join("(" + ", ".join(group[position] for group in converted) + ")"
                                for position in range(offset, min(offset + 100, len(ordered)))) + ";")

    rows = [templates[entries[row[data["index"]["d3_id"]]]] for _, row in ordered]
    template_lines = [
        f"-- Generated from data/d3/{path.name}; edit the CSV and rerun generate_sql.py.",
        "-- Apply to the world database. One template per base item, zero WoW stats",
        "-- (01-stats S2); displayid is joined from item_display.csv by slot/type.",
        "SET NAMES utf8mb4;",
    ]
    # One DELETE per run of consecutive entries: the set caches (and other generators' items) sit between the base items
    # that shipped and the ones added since, and a range over both would delete their rows.
    run_start = previous = None
    for entry in sorted(row[0] for row in rows) + [None]:
        if run_start is not None and (entry is None or entry != previous + 1):
            template_lines.append(f"DELETE FROM `item_template` WHERE `entry` BETWEEN {run_start} AND {previous};")
            run_start = None
        if entry is not None and run_start is None:
            run_start = entry
        previous = entry
    header_sql = "INSERT INTO `item_template` (" + ", ".join(f"`{column}`" for column in TEMPLATE_COLUMNS) + ") VALUES"
    for offset in range(0, len(rows), 100):
        template_lines.append(header_sql)
        template_lines.append(",\n".join("(" + ", ".join(str(field) for field in template) + ")"
                                         for template in rows[offset:offset + 100]) + ";")
    return "\n".join(lines) + "\n", "\n".join(template_lines) + "\n", len(ordered)


# Base items added to base_items.csv after the applied 0002_dc_base_item.sql: the sheet holds them (the start kit, the
# proficiencies and the drop rules read the sheet) and this migration inserts them, whole, with what the later migrations
# gave every base (the Flags, item level and durability of crafting_0003, the wear mask, the sell price, the sheath).
# It is the Shaman's Ritual Mace and Totem (diablocraft-xnrvn.3). Applied, it freezes like the others: a base added
# later renders into the next number, and the entries of this one are then left to it.
ADDED_BASE_MIGRATION = "items_0057_shaman_item_types.sql"


def added_entries(path):
    """The entry ids base_items.csv holds that no applied migration inserted: the added-base migration's."""
    shipped = shipped_entries(path)
    if shipped is None:
        return set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        d3_ids = {row["d3_id"] for row in csv.DictReader(stream, strict=True)}
    return set(read_base_item_ids(path.with_name("base_item_ids.csv"), d3_ids).values()) - shipped


def added_d3_ids(path):
    """The d3_ids of the base items an added-base migration inserts whole (their designation, flags and durability
    included), which the older migrations that set those per row must not name."""
    wanted = added_entries(path)
    if not wanted:
        return set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        d3_ids = {row["d3_id"] for row in csv.DictReader(stream, strict=True)}
    return {d3 for d3, entry in read_base_item_ids(path.with_name("base_item_ids.csv"), d3_ids).items() if entry in wanted}


def render_added_base_items(path):
    """(sql, rows) of the migration inserting the added base items, or None when there are none.

    `rows` is one (entry, class, subclass, displayid, InventoryType, sheath) per added item, for the client's Item.dbc.
    Everything a shipped base got from its several migrations is written here in one place, from the same rules:
    the Flags and item level crafting_0003 sets on every dc_base_item row, the durability it copies from the stock
    items of the same class and slot, the wear mask (base_wear_mask over every playable class), the sell price
    (base_item_costs.csv) and the sheath (SHEATH)."""
    wanted = added_entries(path)
    if not wanted:
        return None
    data = base_item_data(path)
    columns, _definitions, converted, ordered = base_item_value_rows(data, wanted)
    entries, templates, index = data["entries"], data["templates"], data["index"]
    ids = [entries[row[index["d3_id"]]] for _, row in ordered]
    id_list = ",".join(map(str, ids))
    lines = ["-- Generated by generate_sql.py from base_items.csv, base_item_ids.csv, item_display.csv, base_item_costs.csv",
             "-- and class_map.csv; edit the sheets and rerun. Base items added after 0002_dc_base_item.sql shipped (the",
             "-- Shaman's Ritual Mace and Totem, diablocraft-xnrvn.3): the dc_base_item row, the item_template row and what",
             "-- the later migrations gave every base item. Entries are base_item_ids.csv's.",
             "SET NAMES utf8mb4;",
             f"DELETE FROM `dc_base_item` WHERE `entry` IN ({id_list});",
             f"INSERT INTO `dc_base_item` ({', '.join(columns)}) VALUES",
             ",\n".join("(" + ", ".join(group[position] for group in converted) + ")"
                        for position in range(len(ordered))) + ";",
             f"DELETE FROM `item_template` WHERE `entry` IN ({id_list});",
             "INSERT INTO `item_template` (" + ", ".join(f"`{column}`" for column in TEMPLATE_COLUMNS) + ") VALUES",
             ",\n".join("(" + ", ".join(str(field) for field in templates[entry]) + ")" for entry in ids) + ";",
             "-- crafting_0003: every base item carries the flag and item level 70 and the stock durability of its kind.",
             f"UPDATE `item_template` SET `Flags`=`Flags`|{BASE_ITEM_FLAGS}, `ItemLevel`=70 WHERE `entry` IN ({id_list});",
             "CREATE TEMPORARY TABLE dc_native_durability_added AS SELECT class,InventoryType,MAX(MaxDurability) durability "
             "FROM item_template WHERE entry<100000 AND ItemLevel BETWEEN 60 AND 70 GROUP BY class,InventoryType;",
             "UPDATE `item_template` i JOIN dc_native_durability_added d ON d.class=i.class AND d.InventoryType=i.InventoryType "
             f"SET i.MaxDurability=d.durability WHERE i.entry IN ({id_list});",
             "DROP TEMPORARY TABLE dc_native_durability_added;"]
    bits = class_bits(path)
    masks = {}
    for _, row in ordered:
        fields = dict(zip(data["header"], row))
        masks.setdefault(base_wear_mask(fields, bits), []).append(entries[fields["d3_id"]])
    for mask, found in sorted(masks.items()):
        lines.append(f"UPDATE `item_template` SET `AllowableClass`={mask} WHERE `entry` IN ({','.join(map(str, sorted(found)))});")
    # The two renders return their own header comments first; the UPDATEs are what moves.
    lines += [line for line in render_sell_price(path, only=wanted)[0].splitlines() if line.startswith("UPDATE")]
    lines += [line for line in render_sheath(path, only=wanted)[0].splitlines() if line.startswith("UPDATE")]
    lines += [line for line in render_item_descriptions(path, only=wanted)[0].splitlines() if line.startswith("UPDATE")]
    rows = []
    for entry in ids:
        _, item_class, subclass, _name, display, _quality, inventory = templates[entry][:7]
        rows.append((entry, item_class, subclass, display, inventory, SHEATH.get((item_class, subclass, inventory), 0)))
    return "\n".join(lines) + "\n", rows


def added_item_dbc(module_root, rows):
    """The client's Item.dbc with a row for each added base item: where the 3.3.5a client takes the bag icon and the equip
    slot from (client-patch/dbc/README.md). Ours replaced where they sit, a new one appended; every field is the
    item_template row's (class, subclass, displayid, InventoryType, sheath), as build_item.py reads them."""
    from dbc_store import Store, schema
    root = module_root.parent
    items = Store((root / "client-patch/dbc/Item.dbc").read_bytes(), schema(root, "item_dbc"))
    for entry, item_class, subclass, display, inventory, sheath in rows:
        items.encode({"ID": entry, "ClassID": item_class, "SubclassID": subclass, "Sound_Override_Subclassid": -1,
                      "Material": 0, "DisplayInfoID": display, "InventoryType": inventory, "SheatheType": sheath})
    return items.bytes()


def emit_loot_tuning(module_root, sql):
    """Make the migrations reproduce loot_tuning.csv, not just the generated file.

    0001_dc_loot_tuning.sql is merged and immutable, and it is not what the
    migrations as a whole leave in the table: later additive migrations widen
    and retune single columns, so editing a drop rate in the CSV and rerunning
    the generator used to write only data/generated/loot_tuning.sql, which the
    core updater never reads. Instead, when the CSV render differs from 0001 and
    from the newest loot_tuning_NNNN migration we emitted, write the next
    numbered one. The render is a full, self-contained table, so it is correct
    placed after every additive migration, and it is skipped when nothing
    changed, so a rerun never adds a file.
    """
    updates = module_root / "data/sql/db-world/updates"
    base = updates / "0001_dc_loot_tuning.sql"
    encoded = sql.encode("utf-8")
    if not base.exists():                       # fresh checkout: 0001 is current
        write_migration(module_root, base, encoded)
        return None
    if base.read_bytes() == encoded:
        return None
    emitted = sorted(updates.glob("loot_tuning_*_*.sql"))
    if emitted and emitted[-1].read_bytes() == encoded:
        return None
    number = max(1, reserved_number(module_root, "loot_tuning") + 1)
    for path in emitted:
        match = re.match(r"loot_tuning_(\d+)_", path.name)
        if match:
            number = max(number, int(match.group(1)) + 1)
    target = updates / f"loot_tuning_{number:04d}_csv.sql"
    write_migration(module_root, target, encoded)
    return target


def generate(module_root=MODULE_ROOT):
    generated = module_root / "data/generated"
    updates = module_root / "data/sql/db-world/updates"
    # Validate every file before writing anything, including overwrites on rerun.
    special = {"world_areas": render_world_areas}
    class_starts = render_class_starts(module_root)
    class_base_stats = render_class_base_stats(module_root)
    results = {name: (special[name](source_csv(module_root, name)) if name in special
                      else render_table(source_csv(module_root, name), spec,
                                        source_rows=fill_tooltips(module_root, name, source_csv(module_root, name),
                                                                  spec) if name in TOOLTIP_CELLS else None))
               for name, spec in TABLES.items()}
    # Applied migrations are frozen centrally by write_migration: a changed
    # render warns and is not written, so no per-table preflight is needed here.
    items = {name: (table, render_table(source_csv(module_root, name), spec, table))
             for name, (table, spec) in ITEM_TABLES.items()}
    base_item_sql, template_sql, base_item_count = render_base_items(module_root / "data/d3/base_items.csv")
    added_base = render_added_base_items(module_root / "data/d3/base_items.csv")
    sell_price_sql, priced = render_sell_price(module_root / "data/d3/base_items.csv")
    sheath_sql, sheathed = render_sheath(module_root / "data/d3/base_items.csv")
    weapon_types = check_weapon_classes(module_root)
    print(f"weapon classes: {weapon_types} weapon types all mapped")
    shell_sql, shell_count = render_unidentified_shells()
    # Every render above, checked before the first write below.
    for label, sql in ([(name, sql) for name, (sql, _count) in results.items()]
                       + [(name, sql) for name, (_table, (sql, _count)) in items.items()]
                       + [("base_items", base_item_sql), ("item_template", template_sql),
                          ("unidentified_shells", shell_sql),
                          ("class_starts", class_starts[0]), ("class_base_stats", class_base_stats[0])]):
        refuse_placeholders(label, sql)
    generated.mkdir(parents=True, exist_ok=True)
    updates.mkdir(parents=True, exist_ok=True)
    for name, (sql, count) in results.items():
        output = generated / f"{name}.sql"
        output.write_bytes(sql.encode("utf-8"))
        migration = updates / f"0001_dc_{name}.sql"
        if name == "loot_tuning":
            # The tunables change through next-numbered migrations, never by
            # rewriting the already-shipped 0001 (see emit_loot_tuning).
            emitted = emit_loot_tuning(module_root, sql)
            if emitted:
                print(f"dc_loot_tuning: CSV differs; wrote {emitted.name}")
        # Paragon upgrades existing loot tuning through its additive migration.
        # Keep the already-shipped 0001 migration immutable on regeneration;
        # write_migration enforces that for every applied file.
        elif name not in {"world_areas"} or not migration.exists():
            write_migration(module_root, migration, sql)
        print(f"dc_{name}: {count} rows")
    counts = {name: count for name, (_, count) in results.items()}
    # The item system lands in its own numbered migration so the reference
    # tables above keep their 0001 slot (data/sql/README.md).
    for name, (table, (sql, count)) in items.items():
        output = generated / f"{name}.sql"
        output.write_bytes(sql.encode("utf-8"))
        write_migration(module_root, updates / ITEM_MIGRATIONS.get(name, f"0002_{table}.sql"), sql)
        print(f"{table}: {count} rows")
        counts[name] = count
    for stem, table, sql in (("base_items", "dc_base_item", base_item_sql),
                             ("item_template", "dc_item_template", template_sql)):
        output = generated / f"{stem}.sql"
        output.write_bytes(sql.encode("utf-8"))
        if stem == "item_template":
            delta, changed, _ = render_subclass_delta(updates / TEMPLATE_APPLIED, sql, "base item templates", allow_added=True)
            write_migration(module_root, updates / TEMPLATE_MIGRATION, delta)
            print(f"{table}: {base_item_count} rows; {changed} subclass updates in {TEMPLATE_MIGRATION}")
            allowable, masks = render_allowable_class(module_root / "data/d3/base_items.csv")
            write_migration(module_root, updates / ALLOWABLE_MIGRATION, allowable)
            print(f"AllowableClass: {dict(sorted(masks.items()))} in {ALLOWABLE_MIGRATION}")
            set_wear, set_wear_changed = render_set_wear_class(module_root / "data/d3/base_items.csv",
                                                               updates / ALLOWABLE_MIGRATION)
            write_migration(module_root, updates / SET_WEAR_MIGRATION, set_wear)
            print(f"set wear: {set_wear_changed} set pieces locked to their set's class in {SET_WEAR_MIGRATION}")
            added_wear, added_changed = render_added_wear_class(module_root / "data/d3/base_items.csv",
                                                                [updates / ALLOWABLE_MIGRATION, updates / SET_WEAR_MIGRATION])
            write_migration(module_root, updates / ADDED_WEAR_MIGRATION, added_wear)
            print(f"added classes: {added_changed} base items change who may wear them in {ADDED_WEAR_MIGRATION}")
            described, report = render_item_descriptions(module_root / "data/d3/base_items.csv")
            write_migration(module_root, updates / DESCRIPTION_MIGRATION, described)
            print(f"item descriptions: {report['texts']} in {DESCRIPTION_MIGRATION}; longest pair "
                  f"{report['longest'][0]} ({report['longest'][1]}); flavour dropped for "
                  f"{len(report['flavour_dropped'])}; power too long, no native text: "
                  f"{report['power_too_long']}")
            write_migration(module_root, updates / SELL_PRICE_MIGRATION, sell_price_sql)
            print(f"SellPrice: {priced} base items priced in {SELL_PRICE_MIGRATION}")
            write_migration(module_root, updates / SHEATH_MIGRATION, sheath_sql)
            print(f"sheath: {sheathed} weapons and off-hands in {SHEATH_MIGRATION}")
            if added_base:
                added_sql, added_rows = added_base
                write_migration(module_root, updates / ADDED_BASE_MIGRATION, added_sql)
                # A tree with no client patch (a test fixture) has no Item.dbc to add the rows to.
                if (module_root.parent / "client-patch/dbc/Item.dbc").is_file():
                    write_coupled_outputs(module_root, updates / ADDED_BASE_MIGRATION, added_sql,
                                          [(module_root.parent / "client-patch/dbc/Item.dbc", added_item_dbc(module_root, added_rows))],
                                          label="added base items' client Item.dbc rows")
                print(f"added base items: {len(added_rows)} inserted by {ADDED_BASE_MIGRATION}")
            continue
        write_migration(module_root, updates / f"0002_{table}.sql", sql)
        preset_delta = emit_base_item_preset_delta(module_root, sql, updates)
        craft_only_delta = emit_base_item_craft_only_delta(module_root, sql, updates)
        usable_by_delta = emit_base_item_usable_by_delta(module_root, sql, updates)
        print(f"{table}: {base_item_count} rows"
              + (f"; preset fixes in {preset_delta.name}" if preset_delta else "")
              + (f"; craft_only fixes in {craft_only_delta.name}" if craft_only_delta else "")
              + (f"; usable_by fixes in {usable_by_delta.name}" if usable_by_delta else ""))
    counts["base_items"] = base_item_count
    # The shells land in their own numbered migration rather than beside the
    # base items: 0002_dc_item_template is already applied and immutable, and
    # these are a separate feature that can be regenerated on its own.
    (generated / "unidentified_shells.sql").write_bytes(shell_sql.encode("utf-8"))
    shell_delta, _, shell_carry = render_subclass_delta(updates / SHELL_APPLIED, shell_sql,
                                                        "unidentified shells", carry_fields=SHELL_CARRY_FIELDS)
    write_migration(module_root, updates / SHELL_MIGRATION, shell_delta)
    no_limit = emit_shell_no_limit(module_root, shell_carry)
    print(f"unidentified shells: {shell_count} item templates "
          f"({len(SHELL_SLOTS)} slots x {len(SHELL_RARITIES)} rarities)"
          + (f"; carry limit removed in {no_limit.name}" if no_limit else "; no carry limit left to remove"))
    counts["unidentified_shells"] = shell_count
    generate_class_starts(module_root, class_starts)
    counts["class_starts"] = class_starts[1]
    generate_class_base_stats(module_root, class_base_stats)
    counts["class_base_stats"] = class_base_stats[1]
    return counts


USAGE = """usage: generate_sql.py [option]

With no option, regenerate every reference table and item-system migration.
Options select one writer instead:
  --class-starts      rolled starter kits and proficiencies
  --class-base-stats  per-class base stats and stat rules
  --world-areas       CSV-owned world area rules
  --jeweler           jeweler recipes and outputs
  --account-economy   account economy schema and conversion metadata
  --paragon           paragon rules, pools and shared base XP
  --class-catalogue   class catalogue, passives and labels
  -h, --help          show this message and exit without writing anything

An unknown option is refused. Generation only writes files when it is given a
supported invocation, so applied migrations stay immutable."""


if __name__ == "__main__":
    try:
        argument = sys.argv[1:]
        if len(argument) > 1:
            raise SystemExit(f"unknown arguments: {' '.join(argument)}\n\n{USAGE}")
        if argument in (['-h'], ['--help']):
            print(USAGE)
        elif argument == ['--class-starts']:
            generate_class_starts()
        elif argument == ['--class-base-stats']:
            generate_class_base_stats()
        elif argument == ['--world-areas']:
            generate_world_areas()
        elif argument == ['--jeweler']:
            from generate_jeweler import generate as generate_jeweler
            generate_jeweler()
        elif argument == ['--account-economy']:
            from generate_account_economy import generate as generate_account_economy
            generate_account_economy()
        elif argument == ['--paragon']:
            from generate_paragon import generate as generate_paragon
            generate_paragon()
        elif argument == ['--class-catalogue']:
            # Runs after the spell shells: it joins their generated index.
            from generate_class_catalogue import generate as generate_class_catalogue
            generate_class_catalogue()
        elif not argument:
            generate()
        else:
            raise SystemExit(f"unknown argument: {argument[0]}\n\n{USAGE}")
    except (DataError, AppliedStateError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
