"""Greater Rift level per character (diablocraft-kv2d): compile the production
GreaterRiftLevels / SetGreaterRiftLevels against core doubles, with the start level and the cap
read from data/tunables/rifts.csv, and check the store; then cross-check the SQL the code writes
against rifts_0007_greater_rift_level.sql, the delete hook and the dc_rift.gr_rank write.

DC_GR_LEVEL_SOURCE points the compile at a mutated copy of dc_gr_level.cpp (mutation runs)."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
PATH = Path(os.environ.get('DC_GR_LEVEL_SOURCE', MODULE / 'src/rifts/dc_gr_level.cpp'))
SOURCE = PATH.read_text(encoding='utf-8')
MIGRATION = (MODULE / 'data/sql/db-characters/updates/rifts_0007_greater_rift_level.sql').read_text(encoding='utf-8')
RIFTS = rifts_text()

START = int(tunables_csv.value('rifts', 'greater_rift_start_level'))
CAP = int(tunables_csv.value('rifts', 'greater_rift_max_level'))
assert (START, CAP) == (1, 75), (START, CAP)  # the brief: start 1; max 75 since the designer's card q-1006-01 (was 150)


def definition(marker: str) -> str:
    start = SOURCE.index(marker)
    opening = SOURCE.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[start:end]


# Cross-source: the columns the production SQL names are the migration's columns.
table = re.search(r'CREATE TABLE IF NOT EXISTS `dc_character_gr` \((.*?)\n\)', MIGRATION, re.S).group(1)
columns = re.findall(r'^\s*`(\w+)`', table, re.M)
insert = re.search(r'INSERT INTO dc_character_gr \(([\w,]+)\)', SOURCE).group(1).split(',')
select = re.search(r'SELECT ([\w, ]+) FROM dc_character_gr', SOURCE).group(1).split(', ')
assert all(c in columns for c in insert + select + ['guid', 'mode']), (columns, insert, select)
assert re.search(r'DELETE FROM dc_character_gr WHERE guid=', SOURCE), 'a deleted character must lose its row'
assert re.search(r'PRIMARY KEY \(`guid`, `mode`\)', MIGRATION)
# dc_rift.gr_rank is written on the open path, and NULL unless the run is a Greater Rift.
assert 'mode,gr_rank,state' in RIFTS and 'rift.mode == "gr" ? std::to_string(rift.grRank) : "NULL"' in RIFTS

HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <algorithm>
#include <map>
#include <optional>
#include <string>
#include <tuple>
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
#include "dc_gr_level.h"

namespace DC::Tunables {
    unsigned start = %(start)d, cap = %(cap)d;
    double Get(std::string const& category, std::string const& name) {
        assert(category == "rifts");
        if (name == "greater_rift_start_level") return start;
        assert(name == "greater_rift_max_level");
        return cap;
    }
}
namespace DC::Hardcore {
    enum class Mode { Unchosen, Normal, Hardcore };
    Mode current = Mode::Normal, realm = Mode::Normal;
    Mode ModeOf(std::uint32_t) { return current; }
    Mode RealmMode() { return realm; }
}

struct Cell { unsigned v; template <typename T> T Get() const { return static_cast<T>(v); } };
struct Fields { unsigned a, b; Cell operator[](int i) const { return {i ? b : a}; } };
struct Db {
    std::map<std::pair<std::uint32_t, std::string>, std::pair<unsigned, unsigned>> rows;
    unsigned writes = 0;
    std::optional<Fields> Query(char const* sql, std::uint32_t guid, char const* mode) {
        assert(std::string(sql).find("FROM dc_character_gr WHERE guid={} AND mode='{}'") != std::string::npos);
        auto found = rows.find({guid, mode});
        if (found == rows.end()) return std::nullopt;
        return Fields{found->second.first, found->second.second};
    }
    void DirectExecute(char const* sql, std::uint32_t guid, char const* mode, unsigned unlocked, unsigned beaten) {
        assert(std::string(sql).rfind("INSERT INTO dc_character_gr (guid,mode,unlocked,beaten)", 0) == 0);
        rows[{guid, mode}] = {unlocked, beaten};  // ON DUPLICATE KEY UPDATE: one row per key
        ++writes;
    }
} CharacterDatabase;

namespace DC::Rifts {
'''

MAIN = r'''
}
using namespace DC::Rifts;
int main() {
    std::string error;
    // 1. No row: the start level, nothing beaten.
    GrLevels fresh = GreaterRiftLevels(7);
    assert(fresh.unlocked == DC::Tunables::start && fresh.beaten == 0);

    // 2. What was set reads back, and a second set replaces it (one row).
    assert(SetGreaterRiftLevels(7, 12, 9, error));
    GrLevels got = GreaterRiftLevels(7);
    assert(got.unlocked == 12 && got.beaten == 9);
    assert(SetGreaterRiftLevels(7, 20, 0, error));
    got = GreaterRiftLevels(7);
    assert(got.unlocked == 20 && got.beaten == 0 && CharacterDatabase.rows.size() == 1);

    // 3. The ends of the range are allowed; one outside is refused and writes nothing.
    assert(SetGreaterRiftLevels(7, DC::Tunables::start, 0, error));
    assert(SetGreaterRiftLevels(7, DC::Tunables::cap, DC::Tunables::cap, error));
    unsigned before = CharacterDatabase.writes;
    assert(!SetGreaterRiftLevels(7, DC::Tunables::cap + 1, 0, error) && !error.empty());
    assert(!SetGreaterRiftLevels(7, DC::Tunables::start - 1, 0, error));
    assert(!SetGreaterRiftLevels(7, 10, 11, error));   // beaten above unlocked
    assert(CharacterDatabase.writes == before);
    assert(GreaterRiftLevels(7).unlocked == DC::Tunables::cap);

    // 4. The cap is the tunable's, not a literal: lower it and a stored level is held inside it.
    DC::Tunables::cap = 10;
    got = GreaterRiftLevels(7);
    assert(got.unlocked == 10 && got.beaten == 10);
    assert(!SetGreaterRiftLevels(7, 11, 0, error));
    DC::Tunables::cap = %(cap)d;
    //    and so is the start: a level below a raised start is lifted to it.
    assert(SetGreaterRiftLevels(8, 2, 0, error));
    DC::Tunables::start = 5;
    assert(GreaterRiftLevels(8).unlocked == 5 && GreaterRiftLevels(9).unlocked == 5);
    DC::Tunables::start = %(start)d;

    // 5. Per realm mode: a hardcore row and a normal row of one guid never meet.
    assert(SetGreaterRiftLevels(30, 40, 30, error));
    DC::Hardcore::current = DC::Hardcore::Mode::Hardcore;
    got = GreaterRiftLevels(30);
    assert(got.unlocked == DC::Tunables::start && got.beaten == 0);
    assert(SetGreaterRiftLevels(30, 60, 50, error));
    got = GreaterRiftLevels(30);
    assert(got.unlocked == 60 && got.beaten == 50);
    DC::Hardcore::current = DC::Hardcore::Mode::Normal;
    got = GreaterRiftLevels(30);
    assert(got.unlocked == 40 && got.beaten == 30);

    // 5b. A stored level above the cap (the cap was 150 once) reads as the cap, and beaten never passes unlocked.
    CharacterDatabase.rows[{40, "normal"}] = {150, 120};
    got = GreaterRiftLevels(40);
    assert(got.unlocked == DC::Tunables::cap && got.beaten == DC::Tunables::cap);
    CharacterDatabase.rows[{41, "normal"}] = {DC::Tunables::cap + 1, 3};
    assert(GreaterRiftLevels(41).unlocked == DC::Tunables::cap && GreaterRiftLevels(41).beaten == 3);

    // 6. A character with no mode yet takes the realm's.
    DC::Hardcore::current = DC::Hardcore::Mode::Unchosen;
    DC::Hardcore::realm = DC::Hardcore::Mode::Hardcore;
    got = GreaterRiftLevels(30);
    assert(got.unlocked == 60 && got.beaten == 50);
}
''' % {'start': START, 'cap': CAP}

code = (HARNESS % {'start': START, 'cap': CAP}) + definition('unsigned Level(') + definition('char const* ModeKey(') \
    + definition('GrLevels GreaterRiftLevels(') + definition('bool SetGreaterRiftLevels(') + MAIN

cmake = shutil.which('cmake')
if not cmake:
    raise SystemExit('cmake is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-level-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(gr_level LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 20)\n'
        'add_executable(gr_level test.cpp)\n'
        'target_include_directories(gr_level PRIVATE ' + str(MODULE / 'src/rifts') + ')\n'
        'target_compile_options(gr_level PRIVATE -UNDEBUG)\n', encoding='utf-8')
    env = dict(os.environ)
    subprocess.run([cmake, '-S', directory, '-B', str(folder / 'build')], env=env, check=True)
    subprocess.run([cmake, '--build', str(folder / 'build')], env=env, check=True)
    harness_env.run([str(folder / 'build' / 'gr_level')], env=env, check=True)
print('PASS: Greater Rift levels: start, cap, refusals, per realm mode, SQL columns, delete hook, gr_rank write.')
