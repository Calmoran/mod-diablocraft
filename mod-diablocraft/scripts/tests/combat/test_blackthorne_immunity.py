"""N-BLACKTHORNE (diablocraft-nxp9m): a player Combat marks is passed by Desecrator, Molten and Plagued ground effects.

The worldserver cannot run here, so this holds the wiring as source checks (an anchor that moved fails loudly, never skips):
both hazard readers ask before they touch a player, only the three affixes are named, the export is declared and the contract
names it. DC_BLACKTHORNE_RIFTS points the read at src/rifts in a copy of src (mutation runs)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import affixes_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
RIFTS = Path(os.environ.get('DC_BLACKTHORNE_RIFTS', ROOT / 'mod-diablocraft/src/rifts'))
ELITES = affixes_text(RIFTS.parent)
HEADER = (RIFTS / 'dc_rifts.h').read_text(encoding='utf-8')
CONTRACT = (ROOT / 'docs/contracts/legendary-world-pieces.md').read_text(encoding='utf-8')


def body(source, anchor):
    start = source.find(anchor)
    assert start >= 0, 'anchor missing (renamed or moved; update this test): ' + anchor
    brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError('unbalanced braces after ' + anchor)


rule = body(ELITES, 'bool PassesGroundEffect(')
for name in ('Desecrator', 'Molten', 'Plagued'):
    assert f'"{name}"' in rule, name
assert rule.count('affixName !=') == 3, 'exactly the three affixes are named'

apply = body(ELITES, 'void ApplyHazard(')
assert 'PassesGroundEffect(h, player)' in apply
assert apply.index('PassesGroundEffect') < apply.index('DealMonsterHit'), 'the skip must come before the hit'
assert apply.index('PassesGroundEffect') < apply.index('EscalatedStacks'), 'and before a stack is earned'

observe = body(ELITES, 'void ObservePoolContact(')
assert 'PassesGroundEffect(h, player)' in observe, 'a marked player earns no stacks'

assert 'void SetGroundEffectImmune(Player const* player, bool immune);' in HEADER
assert 'SetGroundEffectImmune' in CONTRACT and 'N-BLACKTHORNE' in CONTRACT
print('blackthorne immunity: ok')
