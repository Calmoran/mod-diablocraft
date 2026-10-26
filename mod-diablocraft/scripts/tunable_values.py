"""Read effective generator inputs from the designer's category CSVs; never use defaults.

Generators consume the sheet at generation time. Runtime `.dc tunables set`
does not regenerate templates, placements or client assets.
"""
import math
from pathlib import Path
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from generate_tunables import read_category

MODULE = Path(__file__).resolve().parents[1]


def value(category, name, module=MODULE):
    rows = read_category(module / 'data/tunables' / (category + '.csv'))
    matches = [row for row in rows if row[1] == name]
    if len(matches) != 1:
        raise ValueError(f'Missing generator tunable: {category}/{name}')
    _, _, published, tuned, _, _ = matches[0]
    result = tuned if tuned is not None else published
    if result is None or not math.isfinite(result):
        raise ValueError(f'Unset generator tunable: {category}/{name}')
    return result


def integer(category, name, minimum=0, maximum=None, module=MODULE):
    result = value(category, name, module)
    if result != math.floor(result) or result < minimum or (maximum is not None and result > maximum):
        raise ValueError(f'Invalid integer generator tunable: {category}/{name}')
    return int(result)


def positive(category, name, module=MODULE):
    result = value(category, name, module)
    if result <= 0:
        raise ValueError(f'Nonpositive generator tunable: {category}/{name}')
    return result
