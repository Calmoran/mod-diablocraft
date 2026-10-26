"""The highest Greater Rift level is one tunable, 75 (diablocraft-e4zf, the designer's card q-1006-01).

No compile: what must hold is data and wiring.
  - rifts.csv's greater_rift_max_level is 75, the designer's card is its source, and the generated tunables SQL carries it;
  - nothing in the rifts, difficulty or tier code names the cap as a number (every reader asks the tunable);
  - the readers of the cap are the store (dc_gr_level.cpp: reads, the GM set, the unlock clamp) and, through it,
    the opener's level box (dc_gr_open.cpp) - none keeps a copy;
  - the highest level anything asks for (Torment XVI's solo Greater Rift) fits inside it;
  - the stored-level clamp the card asks for ("a character above 75 reads as 75") is test_gr_level.py's step 5b."""
from pathlib import Path
import csv
import re

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


# --- the row ---------------------------------------------------------------------------------------------
rows = {r['name']: r for r in csv.DictReader((MODULE / 'data/tunables/rifts.csv').open(encoding='utf-8', newline=''))}
row = rows['greater_rift_max_level']
assert tunables_csv.value('rifts', 'greater_rift_max_level') == 75
assert row['value'] == '75' and row['d3_value'] == '' and row['unit'] == 'level'
assert 'q-1006-01' in row['notes'] and 'decisions.md 2026-10-06' in row['notes'], row['notes']
assert 'gr_max_level' not in rows, 'one tunable: the store already reads greater_rift_max_level'
decisions = read('docs/decisions.md')
assert re.search(r'2026-10-06 Greater Rift levels and difficulty \(the designer, card q-1006-01.*Greater Rifts stop at level 75', decisions)
for path in ('mod-diablocraft/data/generated/tunables_0008.sql', 'mod-diablocraft/data/sql/db-world/updates/tunables_0008.sql'):
    assert re.search(r"\('rifts', 'greater_rift_max_level', NULL, 75\.0, 'level', ", read(path)), path

# --- nothing names the cap as a number ----------------------------------------------------------------------
files = list((MODULE / 'src/rifts').glob('*')) + [MODULE / 'src/difficulty/dc_difficulty.cpp', MODULE / 'src/difficulty/dc_gr_scaling.h',
                                                   MODULE / 'src/common/dc_tiers.h', MODULE / 'src/common/dc_tiers.cpp']
for path in files:
    code = path.read_text(encoding='utf-8')
    code = re.sub(r'//[^\n]*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    assert not re.search(r'\b(150|149|75|74)\b', code), '%s names a Greater Rift level as a number' % path.name

# --- who reads the cap ------------------------------------------------------------------------------------------
readers = sorted(p.name for p in (MODULE / 'src').rglob('*') if p.suffix in ('.cpp', '.h') and 'greater_rift_max_level' in p.read_text(encoding='utf-8'))
assert readers == ['dc_gr_level.cpp', 'dc_gr_level.h'], readers      # the store (and its header's comment); nobody keeps a copy
level = read('mod-diablocraft/src/rifts/dc_gr_level.cpp')
assert level.count('Level("greater_rift_max_level")') >= 2            # the read clamp and the GM set bound
opener = read('mod-diablocraft/src/rifts/dc_gr_open.cpp')
assert 'GreaterRiftLevels(' in opener                                # the level box is bounded by the store's clamped number

# --- the highest level anything asks for fits -------------------------------------------------------------------
tiers = list(csv.DictReader((MODULE / 'data/d3/difficulty_tiers.csv').open(encoding='utf-8', newline='')))
highest = max(int(t['unlock_solo_gr']) for t in tiers)
assert highest == 75 and highest <= tunables_csv.value('rifts', 'greater_rift_max_level'), highest
print('PASS: the highest Greater Rift level is the one tunable, 75; no reader keeps a copy; Torment XVI fits.')
