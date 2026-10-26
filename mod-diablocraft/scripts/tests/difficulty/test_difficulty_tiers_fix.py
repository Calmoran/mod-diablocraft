import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
path = ROOT / 'mod-diablocraft/data/d3/difficulty_tiers.csv'
rows = list(csv.DictReader(path.open(newline='', encoding='utf-8')))
torment = [row for row in rows if row['tier'].startswith('Torment ')]
assert len(torment) == 16
def pct(row, key):
    return int(row[key].rstrip('%'))
xp = [pct(row, 'xp_bonus_pct') for row in torment]
gold = [pct(row, 'gold_bonus_pct') for row in torment]
assert xp == sorted(xp)
assert gold == sorted(gold)
assert all(g >= x for x, g in zip(xp, gold))
expected = {
    'Torment VII': (1850, 1900), 'Torment VIII': (2150, 2425),
    'Torment IX': (2500, 3100), 'Torment X': (2900, 4000),
    'Torment XI': (3350, 5000), 'Torment XII': (3900, 6400),
    'Torment XIII': (4500, 8200), 'Torment XIV': (5200, 10500),
    'Torment XV': (6050, 13400), 'Torment XVI': (7000, 17000),
}
for row in torment:
    if row['tier'] in expected:
        assert (pct(row, 'xp_bonus_pct'), pct(row, 'gold_bonus_pct')) == expected[row['tier']]
print('PASS: Torment I-XVI XP/gold monotonicity, gold >= XP, and sourced T7-T16 values')
