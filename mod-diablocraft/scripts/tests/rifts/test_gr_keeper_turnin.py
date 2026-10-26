#!/usr/bin/env python3
"""The Greater Rift quest turns in at the Rift Keeper and starts its 30 second countdown (diablocraft-b3wi).

The designer's dev check 2026-10-07: the Greater Rift quest could not be turned in at the Keeper. Cause, measured on the
fixture world copy: `creature_questender` held only the three Nephalem quests (910020-22) for the Keeper (910003);
rifts_0011 wrote no relation for the Greater ones (910023-25), so the core refused the turn-in
(Object::hasInvolvedQuest) and nothing ever started the countdown 09-rifts 2 step 6 and 7.9.7 hang on it.

1. SQL, on the fixture mysqld (TEMPORARY table, nothing persistent): the Keeper's ender rows after rifts_0011 miss every
   Greater quest id of data/d3/rift_quests.csv; after rifts_0018 it ends all six, and applying 0018 twice changes nothing.
2. The production `HandleTurnIn` (extracted from dc_rift_quests.cpp, compiled against doubles): the first turn-in of a
   Greater Rift starts the countdown and pays once, writes no outcome (the Guardian's result is the outcome), a second
   turn-in does not restart it, a member's Urshi tries stop it, a Nephalem Rift still writes its outcome.
3. The open lock, by scan: a run that is counting down is still a run its members are enrolled in (only a closed run
   is not), so the Greater Rift opening refuses them; `HandleTurnIn` never closes the run (the countdown's end does).

DC_KEEPER_TURNIN_SOURCE and DC_KEEPER_TURNIN_SQL point the checks at a mutated copy for the mutation runs.
Red on the base: rifts_0018 and rift_keeper.sql do not exist.
"""
from pathlib import Path
import csv
import os
import re
import shutil
import subprocess
import tempfile

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402
import fixture_db
import harness_env

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
KEEPER = 910003
QUESTS = Path(os.environ.get('DC_KEEPER_TURNIN_SQL', MODULE / 'data/sql/db-world/updates/rifts_0018_gr_keeper_turnin.sql'))
QUEST_SOURCE = Path(os.environ.get('DC_KEEPER_TURNIN_SOURCE', MODULE / 'src/rifts/dc_rift_quests.cpp'))


def read(path) -> str:
    return Path(path).read_text(encoding='utf-8')


def body(text: str, start: str, end: str) -> str:
    first = text.index(start)
    return text[first:text.index(end, first)]


def definition(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


# --- 1. the ender rows ---------------------------------------------------------------------------------------------------
rows = list(csv.reader(l for l in read(MODULE / 'data/d3/rift_quests.csv').splitlines() if l.startswith('quest,')))
by_mode = {'nr': [], 'gr': []}
for row in rows:
    by_mode[row[2]].append(int(row[1]))
assert len(by_mode['nr']) == 1 and len(by_mode['gr']) == 1, by_mode      # one bar per mode since monster spawning S3
everything = sorted(by_mode['nr'] + by_mode['gr'])

shipped = read(MODULE / 'data/sql/db-world/updates/rifts_0011_rift_quests.sql')
ender_0011 = re.search(r'DELETE FROM `creature_questender`.*?;\nINSERT INTO `creature_questender`.*?;', shipped, re.S).group(0)
migration = read(QUESTS)
one_bar = read(MODULE / 'data/sql/db-world/updates/rifts_0019_one_bar.sql')   # retires the other four variants and their relations
shipped_nr = [910020, 910021, 910022]                                          # what the frozen rifts_0011 relates to the Keeper
shipped_gr = [910023, 910024, 910025]                                          # what rifts_0018 (applied, b3wi) adds; it stays as it shipped
assert 'creature_questender' in migration and 'creature_template' not in migration   # only the relation, nothing else rewritten
assert re.sub(r'\s', '', read(MODULE / 'data/generated/rift_keeper.sql')) == re.sub(r'\s', '', read(
    MODULE / 'data/sql/db-world/updates/rifts_0018_gr_keeper_turnin.sql'))             # the mirror is the migration


def keeper_after(*scripts: str) -> list:
    mysql, defaults = fixture_db.mysql_and_defaults([])
    # the scripts run on a TEMPORARY copy of the table under another name, so the persistent one is never written
    sql = 'CREATE TEMPORARY TABLE dc_scratch_ender LIKE creature_questender;\n'
    sql += ''.join(s.replace('`creature_questender`', 'dc_scratch_ender').replace('INTO creature_questender', 'INTO dc_scratch_ender') + '\n'
                   for s in scripts)
    sql += f'SELECT quest FROM dc_scratch_ender WHERE id={KEEPER} ORDER BY quest;\n'
    ran = subprocess.run([mysql, '--defaults-file=' + defaults, '--no-login-paths', '--batch', '--skip-column-names', 'acore_world'],
                         input=sql, capture_output=True, text=True)
    assert ran.returncode == 0, ran.stderr
    return [int(line) for line in ran.stdout.split()]


before = keeper_after(ender_0011)
assert before == shipped_nr, before                                    # the bug: the Keeper ends the Nephalem quests only
assert not set(by_mode['gr']) & set(before)
after = keeper_after(ender_0011, migration)
assert after == shipped_nr + shipped_gr, after                          # now it ends the Greater ones too (0019 retires two)
assert 'IN (910023, 910024, 910025)' in migration                       # 0018 is the applied file, not rewritten for S3
assert keeper_after(ender_0011, migration, migration) == after         # applied twice: the same rows
assert keeper_after(ender_0011, migration, one_bar) == everything      # and after the one-bar migration only the two quests that remain
assert keeper_after(ender_0011, migration, one_bar, one_bar) == everything
# the world dump the fixture holds is the live shape: its Keeper rows, with 0018 and 0019 on top, are the same two
mysql, defaults = fixture_db.mysql_and_defaults([])
assert keeper_after(f'INSERT INTO creature_questender SELECT * FROM creature_questender WHERE id={KEEPER} '
                    f'AND quest NOT IN ({",".join(map(str, everything))});', ender_0011, migration, one_bar) == everything
# the obelisk still starts only the Nephalem ones: the ready check, not the obelisk, gives the Greater quest
assert 'queststarter' not in migration

# --- 2. the turn-in -------------------------------------------------------------------------------------------------------
turn_in = definition(read(QUEST_SOURCE), 'void HandleTurnIn(Player* player, std::uint32_t questId)')
HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
using uint32 = std::uint32_t;
struct ObjectGuid { unsigned v = 0; };
struct Session {};
struct Rift { std::uint64_t id = 0; std::uint32_t instanceId = 0, questId = 0; std::string mode = "nr"; };
struct Player { ObjectGuid guid; Session session; ObjectGuid GetGUID() const { return guid; } Session* GetSession() { return &session; } };
std::vector<std::string> said, announced, sql;
struct ChatHandler { explicit ChatHandler(Session*) {} void SendSysMessage(std::string const& t) { said.push_back(t); } };
Rift enrolled; bool isEnrolled = true;
bool EnrolledRun(ObjectGuid, Rift& out) { out = enrolled; return isEnrolled; }
std::string held;
std::string UrshiBlocksClose(std::uint64_t) { return held; }
std::mutex workMutex;
struct PendingClose { Rift rift; uint32 started; };
std::unordered_map<std::uint64_t, PendingClose> pendingCloses; // by run id
uint32 now = 1000;
uint32 getMSTime() { return now; }
uint32 RiftCloseMs() { return 30000; }
unsigned paid = 0;
void PayClosingReward(Rift const&) { ++paid; }
void Announce(Rift const&, std::string const& t) { announced.push_back(t); }
struct { template <class... A> void Execute(char const* f, A... a) {
    std::string out; std::ostringstream parts[sizeof...(A) + 1]; unsigned i = 0; ((parts[i++] << a), ...);
    i = 0; for (char const* c = f; *c; ++c) { if (c[0] == '{' && c[1] == '}') { out += parts[i++].str(); ++c; } else out += *c; }
    sql.push_back(out); } } CharacterDatabase;
// QueueClose is deliberately absent: a turn-in that closed the run itself would not compile.

%(turn_in)s

static void reset(std::string mode) {
    said.clear(); announced.clear(); sql.clear(); pendingCloses.clear(); paid = 0; held.clear(); now = 1000; isEnrolled = true;
    enrolled = Rift{}; enrolled.id = 7; enrolled.instanceId = 3; enrolled.questId = 910023; enrolled.mode = mode;
}
int main() {
    Player a, b;
    // a Greater Rift: the first turn-in starts the countdown, pays once, and leaves the outcome to the Guardian's result
    reset("gr");
    HandleTurnIn(&a, 910023);
    assert(pendingCloses.size() == 1 && pendingCloses.at(7).started == 1000 && pendingCloses.at(7).rift.mode == "gr");
    assert(paid == 1 && announced.size() == 1 && announced[0] == "The rift is closing.");
    assert(sql.size() == 1 && sql[0].find("closing_at=DATE_ADD(NOW(), INTERVAL 30 SECOND)") != std::string::npos);
    assert(sql[0].find("outcome") == std::string::npos && sql[0].find("WHERE id=7") != std::string::npos);
    assert(said.size() == 1 && said[0].find("30 seconds") != std::string::npos);
    // a second holder: no new countdown, no second payment, the first one's start is kept
    now = 5000; said.clear();
    HandleTurnIn(&b, 910023);
    assert(pendingCloses.size() == 1 && pendingCloses.at(7).started == 1000 && paid == 1 && sql.size() == 1);
    assert(said.size() == 1 && said[0] == "The rift is already closing.");
    // a member with Urshi tries: nothing starts, and the line says who
    reset("gr"); held = "Your rift cannot be closed while Anna still has upgrade attempts left with Urshi.";
    HandleTurnIn(&a, 910023);
    assert(pendingCloses.empty() && paid == 0 && sql.empty() && said.size() == 1 && said[0] == held);
    // a quest that is not the run's, or no run: nothing
    reset("gr"); HandleTurnIn(&a, 910020); assert(pendingCloses.empty() && sql.empty() && said.empty() && paid == 0);
    reset("gr"); isEnrolled = false; HandleTurnIn(&a, 910023); assert(pendingCloses.empty() && sql.empty() && paid == 0);
    // a Nephalem Rift still writes its outcome with the countdown
    reset("nr"); enrolled.questId = 910020;
    HandleTurnIn(&a, 910020);
    assert(pendingCloses.size() == 1 && sql.size() == 1 && sql[0].find(", outcome='success'") != std::string::npos);
    std::puts("harness ok");
    return 0;
}
'''
compiler = shutil.which('g++') or shutil.which('c++')
assert compiler, 'g++ is not on PATH; this harness compiles a small C++ program'
with tempfile.TemporaryDirectory(prefix='dc-keeper-turnin-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text('#include <cstdio>\n' + HARNESS % {'turn_in': turn_in}, encoding='utf-8')
    subprocess.run([compiler, '-std=c++20', '-UNDEBUG', '-Wall', '-Wno-unused', '-o', str(folder / 'turnin'), str(folder / 'test.cpp')],
                   check=True)
    ran = harness_env.run([str(folder / 'turnin')], capture_output=True, text=True)
assert ran.returncode == 0 and 'harness ok' in ran.stdout, ran.stdout + ran.stderr

# --- 3. the open lock, and the one thing that ends the countdown ---------------------------------------------------------
quests = read(QUEST_SOURCE)
rifts = rifts_text()
opening = read(MODULE / 'src/rifts/dc_gr_open.cpp')
enrolled_sql = body(quests, 'bool EnrolledRun(ObjectGuid player, Rift& result)', 'bool PartyRun(')
assert "r.state<>'closed'" in enrolled_sql and "m.state IN ('enrolled','offline')" in enrolled_sql
assert 'run->state == "closed"' in enrolled_sql               # a run that is only counting down is still live
validate = body(opening, 'std::string Validate(Player* opener', 'std::string Begin(')
assert 'EnrolledRun(member->GetGUID(), run) || Current(member, run)' in validate and 'ask.memberInRun = true' in validate
assert 'state = "closed"' not in turn_in and 'QueueClose' not in turn_in
# the run closes in exactly one place that is not a logout or a destroyed map: the countdown's end
assert len(re.findall(r'\bQueueClose\(', rifts + quests)) == 3
advance = body(rifts, 'void AdvanceClosure(Map* map)', 'void DrainClosures(Map* map)')
assert 'elapsed >= RiftCloseMs()' in advance and 'QueueClose(due)' in advance
# the Keeper offers the turn-in for a Greater Rift as for a Nephalem one: no mode test in its menu
keeper = body(quests, 'class RiftKeeper final', 'bool OnGossipSelect')
assert 'mode' not in keeper and 'QUEST_STATUS_COMPLETE' in keeper

print('PASS: the Keeper ends both rift quests (rifts_0011 + 0018 + 0019), the Greater Rift turn-in starts the 30 s countdown once, '
      'a counting-down run still locks the opening')
