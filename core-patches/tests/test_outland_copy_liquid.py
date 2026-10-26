"""Core patch 0023 (the Outland copy's liquid, bounty acts A6 diablocraft-hyoic.9; the designer, decisions 2026-10-12 answer 5).

Map.cpp is copied out of the core into scratch and the patch is applied there (when the core already carries it, the copy
is checked as it is). The check reads the patched text: the client's map-530 rule (liquid type 2 is 15, green lava) is
asked through one helper at all four places the core had it, the helper names Outland and the copy and nothing else,
and the copy's id is the Map row of the Outland sheet (mod-diablocraft/data/d3/world_open_rift_outland_dbc.csv), cloned
from map 530, so the two cannot drift. The helper is compiled and run: Outland and 753 read green lava, Kalimdor's and
the Eastern Kingdoms' copies, the continents and an Outland dungeon (Hellfire Ramparts, 543) do not. Then it proves it can
fail: each single-rule mutant of the patched text must be refused.

TORMENT_CORE overrides the core (default: this repo's azerothcore-wotlk). Nothing in the core is written.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
CORE = Path(os.environ.get('TORMENT_CORE') or REPO / 'azerothcore-wotlk')
PATCH = REPO / 'core-patches/0023-outland-copy-liquid.patch'
OUT = REPO / 'azerothcore-wotlk/build/_agent-scratch/scripts/outland-copy-liquid'
MAP = 'src/server/game/Maps/Map.cpp'
sys.path.insert(0, str(REPO / 'mod-diablocraft/scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_open_rift_map as clones  # noqa: E402
import harness_env  # noqa: E402


def patched(reverse=False):
    """Map.cpp's text with 0023 applied (or, `reverse`, without it)."""
    OUT.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(dir=OUT))
    try:
        (tree / MAP).parent.mkdir(parents=True)
        shutil.copy(CORE / MAP, tree / MAP)
        applied = subprocess.run(['git', 'apply', '--reverse', '--check', str(PATCH)], cwd=tree, capture_output=True)
        if (applied.returncode != 0) != reverse:
            done = subprocess.run(['git', 'apply', *(['--reverse'] if reverse else []), str(PATCH)], cwd=tree,
                                  capture_output=True, text=True)
            assert done.returncode == 0, '0023 does not apply to the core:\n' + done.stderr
        return (tree / MAP).read_text(encoding='utf-8')
    finally:
        shutil.rmtree(tree)


HELPER = re.compile(r'static constexpr uint32 MAP_OUTLAND_COPY = (\d+);\n\nstatic bool HasOutlandLiquid\(uint32 mapId\)\n\{\n(.*?)\n\}',
                    re.S)
DRIVER = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
using uint32 = std::uint32_t;
constexpr uint32 MAP_OUTLAND = 530;
%s
int main()
{
    assert(HasOutlandLiquid(530) && HasOutlandLiquid(753));
    for (uint32 other : {0u, 1u, 543u, 571u, 750u, 751u, 752u, 754u})
        assert(!HasOutlandLiquid(other));
    return 0;
}
'''


def problems(source):
    """What is wrong with the patched Map.cpp; empty when the rule is right."""
    out = []
    if 'GetId() == MAP_OUTLAND' in source:
        out.append('a place still asks for map 530 alone')
    for rule in ('if (HasOutlandLiquid(GetId()) && vmapData.liquidInfo->type == 2)\n                vmapData.liquidInfo->type = 15;',
                 'if (HasOutlandLiquid(GetId()) && liquidEntry == 2)\n                    liquidEntry = 15;',
                 'if (HasOutlandLiquid(GetId()) && liquidType == 2) // gotta love blizzard hacks\n            liquidType = 15;',
                 'if (HasOutlandLiquid(GetId()) && liquidEntry == 2)\n                liquidEntry = 15;'):
        if rule not in source:
            out.append('the rule is not asked through the helper here: ' + rule.split('\n')[0])
    if source.count('HasOutlandLiquid(GetId())') != 4:
        out.append('the helper is asked at %d places, not the four' % source.count('HasOutlandLiquid(GetId())'))
    found = HELPER.search(source)
    if not found:
        return out + ['the helper or the copy constant is missing']
    clone, parent, _ = clones.map_row(clones.OUTLAND_SOURCE)
    if (int(found.group(1)), parent) != (clone, 530):
        out.append(f'the copy constant {found.group(1)} is not the Outland sheet\'s Map row {clone} (cloned from {parent})')
    with tempfile.TemporaryDirectory(dir=OUT) as folder:
        cpp = Path(folder) / 'liquid.cpp'
        cpp.write_text(DRIVER % found.group(0), encoding='utf-8')
        built = subprocess.run(['c++', '-std=c++17', '-o', str(Path(folder) / 'liquid'), str(cpp)], capture_output=True, text=True)
        if built.returncode != 0:
            return out + ['the helper does not compile: ' + built.stderr[-300:]]
        if harness_env.run([str(Path(folder) / 'liquid')], capture_output=True).returncode != 0:
            out.append('the helper answers green lava for the wrong maps')
    return out


MUTANTS = (
    ('the copy is left out', 'return mapId == MAP_OUTLAND || mapId == MAP_OUTLAND_COPY;', 'return mapId == MAP_OUTLAND;'),
    ('Outland itself is left out', 'return mapId == MAP_OUTLAND || mapId == MAP_OUTLAND_COPY;', 'return mapId == MAP_OUTLAND_COPY;'),
    ('every map reads green lava', 'return mapId == MAP_OUTLAND || mapId == MAP_OUTLAND_COPY;', 'return true;'),
    ('the constant is another map', 'static constexpr uint32 MAP_OUTLAND_COPY = 753;', 'static constexpr uint32 MAP_OUTLAND_COPY = 752;'),
    ('one place keeps the stock rule', 'if (HasOutlandLiquid(GetId()) && liquidType == 2)', 'if (GetId() == MAP_OUTLAND && liquidType == 2)'),
    ('the liquid type is not checked', 'if (HasOutlandLiquid(GetId()) && vmapData.liquidInfo->type == 2)',
     'if (HasOutlandLiquid(GetId()))'),
)


class OutlandCopyLiquid(unittest.TestCase):
    def test_the_patch_holds_every_rule(self):
        self.assertEqual(problems(patched()), [])

    def test_the_stock_core_fails_the_check(self):
        self.assertIn('a place still asks for map 530 alone', problems(patched(reverse=True)))

    def test_each_rule_fails_when_broken(self):
        source = patched()
        for name, old, new in MUTANTS:
            with self.subTest(mutation=name):
                self.assertEqual(source.count(old), 1, f'{old!r} is not unique')
                self.assertTrue(problems(source.replace(old, new)), f'the check passed with: {name}')


if __name__ == '__main__':
    unittest.main()
