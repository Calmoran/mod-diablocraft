#!/usr/bin/env python3
"""Check the real Normal/T6 rift spawn measurements against the source CSVs.

Run the in-game sequence in docs/test-rifts.md section 7 first. This reads the
server log; it does not simulate AutoBalance or create synthetic passing data.
"""
import argparse
import csv
from decimal import Decimal
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def rows(name):
    with (ROOT / 'mod-diablocraft/data/d3' / name).open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))


def pct(value):
    return Decimal(value.removesuffix('%')) / 100


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # Named, so a bare run says what it wants rather than only that something is
    # missing. This reads a worldserver log; it is not a self-contained harness
    # like test_rift_entry and test_rift_keeper, so it cannot gate a refactor.
    parser.add_argument('log', type=Path,
                        help='worldserver log holding [DC tier creature] lines, e.g. '
                             'azerothcore-wotlk/build/server/logs/Server.log')
    parser.add_argument('--players', type=int, choices=range(1, 5), default=1,
                        help='party size the log was produced at (default 1)')
    args = parser.parse_args()
    measurements = []
    for line in args.log.read_text(encoding='utf-8', errors='strict').splitlines():
        if '[DC tier creature]' in line:
            row = dict(re.findall(r'(\w+)=([^\s]+)', line))
            if int(row.get('instance', '0')):
                measurements.append(row)

    def last(tier, players):
        candidates = [r for r in measurements if r['entry'] == '448'
                      and int(r['tier']) == tier and int(r['players']) == players]
        if not candidates:
            raise SystemExit(f'Missing actual Hogger measurement: tier {tier}, players {players}')
        return candidates[-1]

    normal, torment = last(1, 1), last(10, args.players)
    assert normal['instance'] != torment['instance'], 'Must test two distinct rifts'
    assert normal['level'] == torment['level'] == '11', 'Native level changed (possible dungeon scaling)'
    assert normal['baseLife'] == torment['baseLife'], 'Different unscaled baselines'
    assert normal['claimed'] == torment['claimed'] == 'true', 'AutoBalance module ownership missing'
    tiers = {r['tier']: r for r in rows('difficulty_tiers.csv')}
    party = next(r for r in rows('party_scaling.csv')
                 if r['context'] == 'open_world' and int(r['players']) == args.players)
    base = int(normal['baseLife'])
    assert int(normal['Life']) == base, 'Normal regular-monster defaults are not 1'
    health = pct(tiers['Torment VI']['monster_health_multiplier']) * pct(party['monster_life_multiplier'])
    damage = pct(tiers['Torment VI']['monster_damage_multiplier']) * pct(party['monster_damage_multiplier'])
    assert int(torment['Life']) == int(base * health), 'Incorrect tier/party Life product'
    assert Decimal(normal['damageMultiplier']) == 1
    assert abs(Decimal(torment['damageMultiplier']) - damage) < Decimal('0.000001')
    native = [r for r in measurements if r['instance'] == torment['instance'] and int(r['spawn']) > 0]
    assert native and all(r['claimed'] == 'true' for r in native), 'Missing claimed native grid spawn'
    print(f"PASS: Hogger base/Normal {base}; T6 players={args.players} Life={torment['Life']} "
          f"(x{health}, floor); damage x{damage}; native grid spawn claimed.")


if __name__ == '__main__':
    main()
