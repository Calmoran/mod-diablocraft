"""`.dc lineup` stands a family's monsters in a row in front of the GM (diablocraft-5p3n).

Compiles the production LineupAt out of src/monsters/dc_family_lineup.h and drives it; reads dc_family_lineup.cpp and
the generator for the rest: the command reads the table the generator creates, with the columns it creates, escapes
the family the GM typed, is a GM command, and is registered with the rift scripts. DC_FAMILY_LINEUP_HEADER points the
compile at a mutated copy (mutation runs)."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MONSTERS = ROOT / 'mod-diablocraft/src/monsters'
HEADER = Path(os.environ.get('DC_FAMILY_LINEUP_HEADER', MONSTERS / 'dc_family_lineup.h'))
CPP = (MONSTERS / 'dc_family_lineup.cpp').read_text(encoding='utf-8')
GENERATOR = (ROOT / 'mod-diablocraft/scripts/generate/monsters/generate_monster_models.py').read_text(encoding='utf-8')

# --- cross-source: the table and its columns are the generator's ---------------------------------------
create = re.search(r'CREATE TABLE IF NOT EXISTS `(\w+)` \(\s*"?,?\s*"?\s*`entry`[^"]*`family`[^"]*`monster`', GENERATOR)
assert create and create.group(1) == 'dc_monster_family'
query = re.search(r'"SELECT entry, monster FROM (\w+) WHERE family=\'\{\}\' ORDER BY entry LIMIT \{\}"', CPP)
assert query and query.group(1) == 'dc_monster_family'
assert 'WorldDatabase.EscapeString(escaped);' in CPP and CPP.index('EscapeString') < CPP.index('SELECT entry, monster')
assert '{"lineup", HandleLineup, SEC_GAMEMASTER, Console::No}' in CPP
assert 'TEMPSUMMON_TIMED_DESPAWN' in CPP and 'player->SummonCreature(' in CPP
assert 'RegisterFamilyLineupScripts();' in (ROOT / 'mod-diablocraft/src/rifts/dc_rift_scripts.cpp').read_text(encoding='utf-8')
assert 'void RegisterFamilyLineupScripts();' in HEADER.read_text(encoding='utf-8')

harness = r'''
#include <cassert>
#include <cmath>
#include "%s"
using namespace DC::Rifts;
int main() {
    auto near = [](float a, float b) { return std::fabs(a - b) < 1e-3f; };
    // One monster: straight ahead, facing the GM.
    LineupSpot one = LineupAt(0, 1, 100, 200, 0);
    assert(near(one.x, 100 + LINEUP_DISTANCE_YARDS) && near(one.y, 200) && near(one.facing, 3.14159265f));
    // Four monsters facing north (o = pi/2): a row across the line of sight, 4 yd apart, centred on it.
    float const north = 1.57079632679f;
    LineupSpot s[4];
    for (unsigned i = 0; i < 4; ++i) s[i] = LineupAt(i, 4, 0, 0, north);
    for (unsigned i = 0; i < 4; ++i) assert(near(s[i].y, LINEUP_DISTANCE_YARDS));               // all the same distance ahead
    for (unsigned i = 1; i < 4; ++i) assert(near(s[i - 1].x - s[i].x, LINEUP_GAP_YARDS));       // left to right is west to east when facing north
    assert(near(s[0].x + s[3].x, 0) && near(s[1].x + s[2].x, 0));                               // centred
    // The same row turned by any angle keeps its shape: neighbours stay one gap apart.
    float const o = 0.7f;
    for (unsigned i = 1; i < 6; ++i) {
        LineupSpot a = LineupAt(i - 1, 6, 10, 20, o), b = LineupAt(i, 6, 10, 20, o);
        assert(near(std::hypot(a.x - b.x, a.y - b.y), LINEUP_GAP_YARDS));
    }
    assert(LINEUP_MAX >= 8 && LINEUP_SECONDS > 0);                                               // a whole family fits
    return 0;
}
''' % HEADER
scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch/scripts'
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='family-lineup-', dir=scratch) as folder:
    cpp, exe = Path(folder) / 'test.cpp', Path(folder) / 'test.exe'
    cpp.write_text(harness, encoding='utf-8')
    subprocess.run(['clang++', '-std=c++17', str(cpp), '-o', str(exe)], check=True)
    harness_env.run([str(exe)], check=True)
print('PASS: family lineup: spots, table, command, registration.')
