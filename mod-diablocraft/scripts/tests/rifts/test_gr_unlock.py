"""Greater Rift unlocks (diablocraft-hudw, greater-rifts brief part 6).

Compiles the production pieces against core doubles:
  - dc_gr_unlock.h as it is (the bonus a time left earns, what one beaten run does to a character);
  - GreaterRiftLevels, GreaterRiftBeatenSolo and RecordGreaterRiftBeaten cut out of dc_gr_level.cpp, against
    a small table double, with the chart read from data/tunables/rifts.csv;
  - the tier gate, MeetsTierUnlock, as dc_tiers.h writes it;
and runs the very INSERT the store writes against a real MySQL (the fixture mysqld, skipped with a line
when it is down) on the real table the migrations build, to prove it only ever raises a column.

Cross-source: the chart in rifts.csv against greater_rifts.csv's corrected rows and the brief's own table;
the highest solo requirement in difficulty_tiers.csv against the Greater Rift cap; the migration's column
against the SQL the code writes. Source scans cover what a double cannot reach (the Guardian's death calls
the grant, the tier picker passes the solo level).

DC_GR_UNLOCK_HEADER and DC_GR_LEVEL_SOURCE point the compile at mutated copies (mutation runs)."""
from pathlib import Path
import csv
import os
import re
import shutil
import subprocess
import tempfile
import uuid

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
HEADER = Path(os.environ.get('DC_GR_UNLOCK_HEADER', MODULE / 'src/rifts/dc_gr_unlock.h'))
LEVEL = Path(os.environ.get('DC_GR_LEVEL_SOURCE', MODULE / 'src/rifts/dc_gr_level.cpp'))
SOURCE = LEVEL.read_text(encoding='utf-8')
CHARS = MODULE / 'data/sql/db-characters/updates'


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def body(text: str, start: str, end: str) -> str:
    first = text.index(start)
    return text[first:text.index(end, first)]


def seconds(clock: str) -> int:
    minutes, rest = clock.split(':')
    return int(minutes) * 60 + int(rest)


# --- cross-source: the chart ------------------------------------------------------------------------
cap = int(tunables_csv.value('rifts', 'greater_rift_max_level'))
chart = [int(tunables_csv.value('rifts', 'gr_unlock_plus_%d_min_seconds_left' % k)) for k in range(1, 11)]
rows = {r['name']: r for r in csv.DictReader((MODULE / 'data/tunables/rifts.csv').open(encoding='utf-8', newline=''))}
for k in range(1, 11):
    row = rows['gr_unlock_plus_%d_min_seconds_left' % k]
    assert row['d3_value'] and not row['value'], k   # a sourced number, the designer's to tune
assert chart == sorted(chart) and len(set(chart)) == 10 and chart[0] == 0, chart

# greater_rifts.csv: after the fix each chart row carries its own bonus, +1 on the first to +10 on the last
d3 = list(csv.DictReader((MODULE / 'data/d3/greater_rifts.csv').open(encoding='utf-8', newline='')))
chart_rows = [r for r in d3 if r['item'] in ('rank', 'ranks')]
assert len(chart_rows) == 10, len(chart_rows)
bonuses = [int(re.search(r'keystone \+(\d+)', r['notes']).group(1)) for r in chart_rows]
assert bonuses == list(range(1, 11)), bonuses            # the column no longer sits one row late
rule = next(r for r in d3 if r['item'] == 'keystone_upgrade_rule')
assert 'keystone +' not in rule['notes'], rule['notes']  # the +1 that trailed the rule row is gone
# each row starts at the clock it names ("4:31-6:00" at 4:31); the first row ("4:30 or less") at 0 and the CSV's own
# "11:30-12:00" row, which the brief writes as 11:31-12:00, one second after the clock it names
firsts = [seconds(re.findall(r'(\d+:\d+)', r['value'])[0]) for r in chart_rows]
derived = [0] + [firsts[i] + (1 if i == 8 else 0) for i in range(1, 10)]
assert chart == derived, (chart, derived)
assert firsts[0] == 270 and re.search(r'12:01 or more', chart_rows[9]['value'])

# the brief's own table (ruling 2026-10-04)
brief = read('docs/briefs/greater-rifts-brief.md')
table = body(brief, '4:30 or less left +1', '.\n\n')
by_bonus = {}
for first, bound, bonus in re.findall(r'(\d+:\d+)(?:-\d+:\d+)?(?: (or less|or more))?(?: left)? \+(\d+)', table):
    by_bonus[int(bonus)] = 0 if bound == 'or less' else seconds(first)
assert sorted(by_bonus) == list(range(1, 11)), by_bonus
assert [by_bonus[k] for k in range(1, 11)] == chart, (by_bonus, chart)    # +2 starts at 4:31 and so on, as written
assert 'capped at 150' in brief                                           # the brief says 150; the designer's card moved the cap to the tunable

# --- cross-source: the tiers ------------------------------------------------------------------------
tiers = list(csv.DictReader((MODULE / 'data/d3/difficulty_tiers.csv').open(encoding='utf-8', newline='')))
solo = [(t['tier'], int(t['unlock_solo_gr']), int(t['unlock_character_level'])) for t in tiers if int(t['unlock_solo_gr'])]
assert [t[0] for t in solo] == ['Torment ' + n for n in ('VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI')]
assert [t[1] for t in solo] == list(range(30, 80, 5)) and {t[2] for t in solo} == {70}
assert max(t[1] for t in solo) <= cap, 'Torment XVI would need a Greater Rift above the cap'
generated = read('mod-diablocraft/data/generated/difficulty_tiers.sql')
for name, level, character in solo:
    line = next(l for l in generated.splitlines() if l.startswith("('%s'," % name))
    assert re.search(r", %d, 0, %d, (NULL|\d+)\),?;?$" % (character, level), line), name   # the generated unlock_solo_gr column

# --- cross-source: the table and the SQL --------------------------------------------------------------
migration = (CHARS / 'rifts_0009_gr_beaten_solo.sql').read_text(encoding='utf-8')
assert re.search(r'ADD COLUMN `beaten_solo` SMALLINT UNSIGNED NOT NULL DEFAULT 0', migration)
upsert = body(SOURCE, 'GrUnlock RecordGreaterRiftBeaten(', 'class GrLevelPlayer')
sql_text = ''.join(re.findall(r'"([^"]*)"', body(upsert, 'DirectExecute(', 'guid, ModeKey(guid)')))
assert sql_text.startswith('INSERT INTO dc_character_gr (guid,mode,unlocked,beaten,beaten_solo) VALUES ({},\'{}\',{},{},{}) ')
for column in ('unlocked', 'beaten', 'beaten_solo'):
    assert '%s=GREATEST(%s,VALUES(%s))' % (column, column, column) in sql_text, column
assert 'DELETE FROM dc_character_gr WHERE guid=' in SOURCE        # a deleted character still loses its row

# --- where the other modules call it ------------------------------------------------------------------
progress = read('mod-diablocraft/src/rifts/dc_gr_progress.cpp')
grant = body(progress, 'void GrantGreaterUnlocks(Rift const& rift)', 'void ForgetGreaterOrbs')
assert 'rift.outcome != Gr::OutcomeName(true)' in grant and 'EnrolledGuids(rift.id)' in grant
assert 'RecordGreaterRiftBeaten(guid.GetCounter(), rift.grRank, rift.timeLeft, solo)' in grant
assert 'bool const solo = rift.players == 1;' in grant
record = body(progress, 'void RecordGuardianResult(Rift& rift)', 'void GrantGreaterUnlocks')
assert record.index('StoreResult(rift, rift.outcome.c_str(), rift.timeLeft);') < record.index('GrantGreaterUnlocks(rift);')
assert 'if (beaten)\n                GrantGreaterUnlocks(rift);' in record      # only a beaten run, only when the result is first set
difficulty = read('mod-diablocraft/src/difficulty/dc_difficulty.cpp')
select = body(difficulty, 'bool SelectTier(Player* player, unsigned id, std::string& error)', 'if (group)\n    {')
assert 'Rifts::GreaterRiftBeatenSolo(player->GetGUID().GetCounter())' in select
assert 'TierUnlocked(id, player->GetLevel(), accountLevel, beatenSolo)' in select
tiers_h = read('mod-diablocraft/src/common/dc_tiers.h')
assert 'beatenSoloGreaterRift >= rule.soloGreaterRift' in tiers_h and '!rule.soloGreaterRift' not in tiers_h
assert 'unsigned GreaterRiftBeatenSolo(std::uint32_t guid);' in read('mod-diablocraft/src/rifts/dc_rifts.h')

HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <tuple>
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
#include "%(header)s"
#include "dc_gr_level.h"
#include "dc_tiers.h"

std::map<std::string, std::optional<double>> tunables;
namespace DC::Tunables {
    double Get(std::string const& category, std::string const& name) {
        assert(category == "rifts");
        auto found = tunables.find(name);
        assert(found != tunables.end());
        return found->second.value_or(0.0);
    }
    bool Has(std::string const& category, std::string const& name) {
        assert(category == "rifts");
        auto found = tunables.find(name);
        return found != tunables.end() && found->second.has_value();
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
struct Row { unsigned unlocked = 0, beaten = 0, solo = 0; };
struct Db {
    std::map<std::pair<std::uint32_t, std::string>, Row> rows;
    unsigned writes = 0;
    std::optional<Fields> Query(char const* sql, std::uint32_t guid, char const* mode) {
        std::string const text(sql);
        auto found = rows.find({guid, mode});
        if (found == rows.end()) return std::nullopt;
        if (text.rfind("SELECT unlocked, beaten FROM dc_character_gr WHERE guid={} AND mode='{}'", 0) == 0)
            return Fields{found->second.unlocked, found->second.beaten};
        assert(text.rfind("SELECT beaten_solo FROM dc_character_gr WHERE guid={} AND mode='{}'", 0) == 0);
        return Fields{found->second.solo, 0};
    }
    void DirectExecute(char const* sql, std::uint32_t guid, char const* mode, unsigned unlocked, unsigned beaten, unsigned solo) {
        std::string const text(sql);
        assert(text.rfind("INSERT INTO dc_character_gr (guid,mode,unlocked,beaten,beaten_solo)", 0) == 0);
        Row& row = rows[{guid, mode}];   // ON DUPLICATE KEY UPDATE ... GREATEST: one row per key, a column only rises
        row.unlocked = std::max(row.unlocked, unlocked); row.beaten = std::max(row.beaten, beaten); row.solo = std::max(row.solo, solo);
        ++writes;
    }
    // the tier-picker's own select is not called here
    void DirectExecute(char const*, std::uint32_t, char const*, unsigned, unsigned) { assert(false); }
} CharacterDatabase;

namespace DC::Rifts {
%(unlockrows)s
// RaiseAccountSolo (the account's best, which caps Blood Shards) is the production helper cut out as a recorder:
// its own statement runs on a real table in test_blood_shards.py. Here only the call and its level are checked.
unsigned accountRaised = 0;
void RaiseAccountSolo(std::uint32_t, unsigned level) { accountRaised = std::max(accountRaised, level); }
'''

definitions = ''
for marker in ('unsigned Level(', 'char const* ModeKey(', 'GrLevels GreaterRiftLevels(', 'unsigned GreaterRiftBeatenSolo(',
               'GrUnlock RecordGreaterRiftBeaten('):
    start = SOURCE.index(marker)
    opening = SOURCE.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    definitions += SOURCE[start:end] + '\n'
unlockrows = re.search(r'constexpr unsigned UnlockRows = \d+;', SOURCE).group(0)
assert unlockrows == 'constexpr unsigned UnlockRows = 10;'

MAIN = r'''
}
using namespace DC::Rifts;
namespace G = DC::Rifts::Gr;
unsigned const CHART[10] = {%(chart)s};
unsigned const CAP = %(cap)d;

void reset() {
    tunables.clear();
    tunables["greater_rift_start_level"] = 1; tunables["greater_rift_max_level"] = CAP;
%(setchart)s
    CharacterDatabase.rows.clear(); CharacterDatabase.writes = 0; accountRaised = 0;
    DC::Hardcore::current = DC::Hardcore::Mode::Normal; DC::Hardcore::realm = DC::Hardcore::Mode::Normal;
}

int main() {
    // ---- header: the bonus a time left earns, at every edge of the chart ----
    assert(G::UnlockBonus(0, CHART, 10) == 1 && G::UnlockBonus(270, CHART, 10) == 1);      // 4:30 or less: +1
    for (unsigned k = 2; k <= 10; ++k) {
        assert(G::UnlockBonus(CHART[k - 1], CHART, 10) == k);                              // the first second of the row
        assert(G::UnlockBonus(CHART[k - 1] - 1, CHART, 10) == k - 1);                      // one second short of it
    }
    assert(G::UnlockBonus(721, CHART, 10) == 10 && G::UnlockBonus(900, CHART, 10) == 10);  // 12:01 or more: +10
    assert(G::UnlockBonus(360, CHART, 10) == 2 && G::UnlockBonus(361, CHART, 10) == 3);    // 6:00 is +2, 6:01 is +3
    assert(G::UnlockBonus(690, CHART, 10) == 8 && G::UnlockBonus(691, CHART, 10) == 9);    // 11:30 is +8, 11:31 is +9
    unsigned const none[2] = {~0u, ~0u};
    assert(G::UnlockBonus(900, none, 2) == 0);                                              // a missing row is out of reach
    unsigned const jumbled[3] = {500, 0, 100};
    assert(G::UnlockBonus(150, jumbled, 3) == 3 && G::UnlockBonus(50, jumbled, 3) == 2);   // a high row is never lost to a later one
    assert(G::UnlockBonus(10, CHART, 0) == 0);

    // ---- header: what a beaten run does ----
    G::Reach start;                                                                        // unlocked 1, nothing beaten
    G::Reach one = G::Beat(start, 10, 3, false, CAP);
    assert(one.unlocked == 13 && one.beaten == 10 && one.beatenSolo == 0);                  // may open the beaten level plus the bonus
    G::Reach solo = G::Beat(start, 10, 3, true, CAP);
    assert(solo.unlocked == 13 && solo.beaten == 10 && solo.beatenSolo == 10);              // alone: the solo level rises too
    G::Reach higher{40, 30, 25};
    G::Reach lower = G::Beat(higher, 10, 10, true, CAP);
    assert(lower.unlocked == 40 && lower.beaten == 30 && lower.beatenSolo == 25);           // beating a lower level never lowers anything
    G::Reach again = G::Beat(one, 10, 3, false, CAP);
    assert(again.unlocked == one.unlocked && again.beaten == one.beaten && again.beatenSolo == one.beatenSolo);   // a repeat changes nothing
    G::Reach capped = G::Beat(start, CAP - 2, 10, false, CAP);
    assert(capped.unlocked == CAP && capped.beaten == CAP - 2);                             // never past the cap
    G::Reach top = G::Beat(start, CAP, 5, true, CAP);
    assert(top.unlocked == CAP && top.beaten == CAP && top.beatenSolo == CAP);
    G::Reach over = G::Beat(start, CAP + 50, 5, true, CAP);                                 // a run above a lowered cap counts as the cap
    assert(over.unlocked == CAP && over.beaten == CAP && over.beatenSolo == CAP && over.beaten <= over.unlocked);
    G::Reach nobonus = G::Beat(start, 7, 0, false, CAP);
    assert(nobonus.unlocked == 7 && nobonus.beaten == 7);                                   // no bonus row reached: still the beaten level

    // ---- the store: a character beats runs ----
    reset();
    {
        GrUnlock done = RecordGreaterRiftBeaten(7, 10, 300, false);                         // 5:00 left: 4:31-6:00, +2
        assert(done.before.unlocked == 1 && done.before.beaten == 0);
        assert(done.after.unlocked == 12 && done.after.beaten == 10);
        assert(GreaterRiftLevels(7).unlocked == 12 && GreaterRiftLevels(7).beaten == 10 && GreaterRiftBeatenSolo(7) == 0);
        done = RecordGreaterRiftBeaten(7, 12, 800, true);                                   // 13:20 left: +10, alone
        assert(done.before.unlocked == 12 && done.after.unlocked == 22 && done.after.beaten == 12);
        assert(GreaterRiftBeatenSolo(7) == 12);
        done = RecordGreaterRiftBeaten(7, 5, 800, true);                                    // a lower run: nothing falls
        assert(done.after.unlocked == 22 && GreaterRiftLevels(7).unlocked == 22 && GreaterRiftLevels(7).beaten == 12);
        assert(GreaterRiftBeatenSolo(7) == 12);
        unsigned const writes = CharacterDatabase.writes;
        RecordGreaterRiftBeaten(7, 12, 800, true);                                          // the same run again
        assert(GreaterRiftLevels(7).unlocked == 22 && GreaterRiftBeatenSolo(7) == 12 && CharacterDatabase.writes == writes + 1);
        assert(GreaterRiftBeatenSolo(99) == 0);                                             // a character with no row
        // the cap is the tunable's: lower it and the unlock stops there
        tunables["greater_rift_max_level"] = 15;
        done = RecordGreaterRiftBeaten(8, 14, 800, false);
        assert(done.after.unlocked == 15 && GreaterRiftLevels(8).unlocked == 15);
        tunables["greater_rift_max_level"] = CAP;
    }
    reset();   // a half-loaded chart grants less, never more
    {
        tunables["gr_unlock_plus_10_min_seconds_left"] = std::nullopt;
        tunables.erase("gr_unlock_plus_9_min_seconds_left");
        GrUnlock done = RecordGreaterRiftBeaten(3, 10, 899, false);
        assert(done.after.unlocked == 18);                                                  // the +8 row is the highest it has
    }
    reset();   // per realm mode: a hardcore run never raises a normal row
    {
        RecordGreaterRiftBeaten(5, 20, 800, true);
        DC::Hardcore::current = DC::Hardcore::Mode::Hardcore;
        assert(GreaterRiftLevels(5).unlocked == 1 && GreaterRiftBeatenSolo(5) == 0);
        RecordGreaterRiftBeaten(5, 3, 800, false);
        DC::Hardcore::current = DC::Hardcore::Mode::Normal;
        assert(GreaterRiftLevels(5).unlocked == 30 && GreaterRiftBeatenSolo(5) == 20);
        assert(CharacterDatabase.rows.size() == 2);
        assert(accountRaised == 20);                       // the account's best follows the character's solo level
    }

    // ---- the tier gate ----
    using DC::TierUnlockRule;
    TierUnlockRule seven{70, 0, 30}, sixteen{70, 0, 75}, none_{0, 0, 0}, six{60, 0, 0};
    assert(!DC::MeetsTierUnlock(seven, 70, 70) && !DC::MeetsTierUnlock(seven, 70, 70, 0));  // no beaten run: fail closed, as before
    assert(!DC::MeetsTierUnlock(seven, 70, 70, 29) && DC::MeetsTierUnlock(seven, 70, 70, 30) && DC::MeetsTierUnlock(seven, 70, 70, 80));
    assert(!DC::MeetsTierUnlock(seven, 69, 70, 75));                                       // the level still counts
    assert(!DC::MeetsTierUnlock(sixteen, 70, 70, 74) && DC::MeetsTierUnlock(sixteen, 70, 70, 75));
    assert(DC::MeetsTierUnlock(none_, 1, 1) && DC::MeetsTierUnlock(six, 60, 1, 0) && !DC::MeetsTierUnlock(six, 59, 1, 75));
    return 0;
}
''' % {'chart': ', '.join(str(n) for n in chart), 'cap': cap,
       'setchart': '\n'.join('    tunables["gr_unlock_plus_%d_min_seconds_left"] = CHART[%d];' % (k, k - 1) for k in range(1, 11))}

code = (HARNESS % {'header': HEADER.as_posix(), 'unlockrows': unlockrows}) + definitions + MAIN

compiler = shutil.which('g++') or shutil.which('c++')
if not compiler:
    raise SystemExit('g++ is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-unlock-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    subprocess.run([compiler, '-std=c++20', '-UNDEBUG', '-Wall', '-Wno-unused', '-I', str(MODULE / 'src/rifts'),
                    '-I', str(MODULE / 'src/common'), '-o', str(folder / 'gr_unlock'), str(folder / 'test.cpp')], check=True)
    harness_env.run([str(folder / 'gr_unlock')], check=True)


# --- the production INSERT, on a real table ------------------------------------------------------------
def mysql(*args, stdin=None):
    return subprocess.run([fixture_db.mysql_exe(), '--defaults-file=' + str(fixture_db.defaults_file()), '--no-login-paths', *args],
                          input=stdin, capture_output=True, text=True)


if mysql('-e', 'SELECT 1').returncode != 0:
    print('SKIP real-SQL check: the fixture mysqld is down (fixture_mysql.sh start)')
else:
    db = 'gr_unlock_' + uuid.uuid4().hex[:10]
    assert mysql('-e', 'CREATE DATABASE ' + db).returncode == 0
    try:
        for name in ('rifts_0007_greater_rift_level.sql', 'rifts_0009_gr_beaten_solo.sql'):
            result = mysql(db, stdin=(CHARS / name).read_text(encoding='utf-8'))
            assert result.returncode == 0, name + ': ' + result.stderr

        def write(unlocked, beaten, beaten_solo):
            statement = sql_text.replace("{}", "%s")
            statement = statement % (7, 'normal', unlocked, beaten, beaten_solo)
            result = mysql(db, '-e', statement)
            assert result.returncode == 0, result.stderr

        def row():
            out = mysql(db, '-N', '-e', 'SELECT unlocked, beaten, beaten_solo FROM dc_character_gr WHERE guid=7').stdout.split()
            return tuple(int(n) for n in out)

        write(12, 10, 0);   assert row() == (12, 10, 0), row()
        write(22, 12, 12);  assert row() == (22, 12, 12), row()
        write(15, 5, 5);    assert row() == (22, 12, 12), row()      # a lower run lowers nothing
        write(22, 12, 0);   assert row() == (22, 12, 12), row()      # a party run never clears the solo level
        write(30, 12, 12);  assert row() == (30, 12, 12), row()
        assert mysql(db, '-N', '-e', 'SELECT COUNT(*) FROM dc_character_gr').stdout.strip() == '1'
    finally:
        mysql('-e', 'DROP DATABASE IF EXISTS ' + db)
print('PASS: Greater Rift unlocks: the chart, the beaten run, the store, the tier gate, the real INSERT, wiring.')
