"""Execute the actual static artisan/tooltip SELECTs against a migrated world DB."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
LITERAL = r'"(?:[^"\\]|\\.)*"'


def cpp_queries(source, call='WorldDatabase.Query'):
    """Every query a C++ call site passes, adjacent literals joined.

    clang-format (hook 5a) wraps a long query across several adjacent string
    literals, which the compiler concatenates and this has to as well - reading
    only the first one silently tests a truncated query.
    """
    out = []
    for match in re.finditer(re.escape(call) + r'\(\s*((?:' + LITERAL + r'\s*)+)', source):
        out.append(''.join(json.loads(piece) for piece in re.findall(LITERAL, match[1])))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mysql', default=None)
    parser.add_argument('--defaults-file', default=None)
    parser.add_argument('--database', default='acore_world')
    args = parser.parse_args()
    if not (args.mysql and args.defaults_file):
        import fixture_db
        fixture_mysql, fixture_defaults = fixture_db.mysql_and_defaults([])
        args.mysql, args.defaults_file = args.mysql or fixture_mysql, args.defaults_file or fixture_defaults
    module = Path(__file__).resolve().parents[3]
    count = 0
    for name in ('dc_crafting.lua', 'dc_tooltip.lua'):
        source = (module / 'lua/aio' / name).read_text(encoding='utf-8-sig')
        literals = re.findall(r'WorldDBQuery\(("(?:[^"\\]|\\.)*")\)', source)
        for literal in literals:
            query = json.loads(literal)
            assert query.startswith('SELECT '), query
            result = subprocess.run([
                args.mysql, '--defaults-file=' + str(Path(args.defaults_file).resolve()),
                '--no-login-paths', '--batch', args.database, '-e', query],
                env={k.upper(): v for k, v in os.environ.items()},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                raise RuntimeError(name + ': ' + query + '\n' + result.stderr.decode('utf-8', errors='replace'))
            count += 1
        print(f'PASS {name}: {len(literals)} actual startup/reference queries')
    assert count >= 10, 'Static query collection unexpectedly empty'
    print(f'PASS {count} actual MySQL queries; no collation/DISTINCT errors')

    # Exercise the production C++ eligibility predicate against every live recipe.
    # Generic CSV bases have NULL level_req, which must mean unrestricted.
    source = crafting_source.source()
    queries = cpp_queries(source)
    templates = [value for value in queries
                 if value.startswith('SELECT b.entry FROM dc_base_item b JOIN dc_blacksmith_rule r ')]
    assert len(templates) == 1, 'Crafting eligibility query changed; review this regression'

    # 12-ui section 2 and bugs.md 2026-09-15: one source of truth for the enchant
    # price. The formula lives in dc_crafting.cpp CostOf and nowhere else, and the
    # Mystic screen never reads the tuning it is built from.
    screen = (module / 'lua/aio/dc_crafting.lua').read_text(encoding='utf-8-sig')
    assert 'mystic_base_gold' not in screen, \
        'dc_crafting.lua reads the Mystic price tuning again; C++ owns the price (12-ui section 2)'
    assert 'mystic_cost_multiplier' not in screen, \
        'dc_crafting.lua reads the Mystic price multiplier again; C++ owns the price'
    tuning = [value for value in queries if 'mystic_base_gold' in value]
    assert len(tuning) == 1, \
        f'The enchant price must be computed in exactly one place; found {len(tuning)} tuning reads'
    # diablocraft-xw2m: the price is mystic_base_gold times D3's scalar table, no multiplier any more.
    assert 'mystic_cost_multiplier' not in source, \
        'The retired enchant multiplier is read again in dc_crafting.cpp'
    # The quote the screen renders and the charge Roll takes come from the same call.
    assert source.count('CostOf(player, instance)') == 2, \
        'Roll() and MysticState() must both price through CostOf, and nothing else may'
    # Passed as an argument, not merely quoted in the comment that explains it.
    assert not re.search(r'[,(]\s*"Not enough materials\."', source), \
        'A missing material must be named (bugs.md 2026-09-07), not reported generically'
    print('PASS: one enchant price formula in C++, none on the screen, quote and charge share it')

    def select(query):
        return subprocess.check_output([
            args.mysql, '--defaults-file=' + str(Path(args.defaults_file).resolve()),
            '--no-login-paths', '--batch', '--skip-column-names', args.database, '-e', query],
            env={k.upper(): v for k, v in os.environ.items()}, text=True).splitlines()

    recipes = select('SELECT id,slot,rarity,item_level FROM dc_blacksmith_recipe ORDER BY id')
    assert len(recipes) == 10, 'Expected 10 Blacksmith recipes; jewelry is excluded'
    failures = []
    for row in recipes:
        recipe_id, slot, rarity, level = row.split('\t')
        assert slot not in ('neck','leftfinger','rightfinger'), ('Jeweler recipe exposed', row)
        assert re.fullmatch(r'[a-z]+', slot), ('Unexpected recipe slot', row)
        assert re.fullmatch(r'[a-z]+', rarity) and level.isdigit(), row
        query = templates[0].format(slot, rarity, level)
        assert 'usable_by' not in query and 'class' not in query.lower()
        entries = select(query)
        if not entries:
            failures.append((recipe_id, slot))
        print(f'Recipe {recipe_id} {slot}: {len(entries)} eligible bases')
    assert not failures, ('Recipes have no eligible base', failures)
    assert select("SELECT DISTINCT rarity FROM dc_blacksmith_recipe") == ['rare']
    print('PASS: all 10 rare Blacksmith recipes use the same class-neutral matrix; jewelry absent')


if __name__ == '__main__':
    main()
