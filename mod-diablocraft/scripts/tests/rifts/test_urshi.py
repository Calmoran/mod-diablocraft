"""Urshi, the legendary gem upgrader (diablocraft-z94g, greater-rifts brief part 11).

Compiles the production dc_gr_urshi.h as it is, against nothing but the standard library (it has no core in it), and
drives it with the sheet's own numbers: the tries (3, +1 for a member who did not die, Hardcore always), the upgrade
chance by level minus rank for every band of greater_rifts.csv gem_upgrade_chance, the roll, the max-rank test, the
order of the list (worn first, then bags and stash, each by rank highest first), the gem id and the line that names who
holds the rift open.

Cross-source: the rifts.csv chance and tries rows equal greater_rifts.csv's own rows, in the band order the header
numbers; the contract's prefix, records, rows and refusal texts equal the ones the code sends. Source scans cover what a
double cannot reach (the Guardian-kill hook, the three ways of closing, the leave/kick/logout hooks, the gem places read,
the stash and rank writes, the route and the creature template); the test says so below.

Mutation runs: every mutant of the header below must make the harness fail. DC_URSHI_HEADER points the compile at a copy.
"""
from pathlib import Path
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from split_sources import rifts_text  # noqa: E402
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
HEADER = Path(os.environ.get('DC_URSHI_HEADER', MODULE / 'src/rifts/dc_gr_urshi.h'))


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def body(text: str, start: str, end: str) -> str:
    first = text.index(start)
    return text[first:text.index(end, first)]


def value(name: str) -> float:
    return tunables_csv.value('rifts', name)


# --- cross-source: the sheet rows are greater_rifts.csv's own -------------------------------------------------------
d3_rows = list(csv.DictReader((MODULE / 'data/d3/greater_rifts.csv').open(encoding='utf-8', newline='')))
published = [(r['item'], int(r['value'].rstrip('%'))) for r in d3_rows if r['item'].startswith('gem_upgrade_chance')]
assert len(published) == 12, published
BANDS = ['plus_10_or_more', 'plus_9', 'plus_8', 'plus_7', 'plus_0_to_6', 'minus_1', 'minus_2', 'minus_3', 'minus_4',
         'minus_5', 'minus_6_to_15', 'minus_16_or_less']
LABELS = ['+10 or higher', '+9)', '+8)', '+7)', '0 to +6', '−1)', '−2)', '−3)', '−4)', '−5)',
          '−6 to −15', '−16 or lower']
for (item, percent), band, label in zip(published, BANDS, LABELS):
    assert label in item, (label, item)                              # the band the header numbers is the one the sheet row names
    assert value('gr_gem_chance_' + band) == percent, (band, percent)
rows = {r['name']: r for r in csv.DictReader((MODULE / 'data/tunables/rifts.csv').open(encoding='utf-8', newline=''))}
for band in BANDS:
    row = rows['gr_gem_chance_' + band]
    assert row['value'] == '' and row['d3_value'] != '' and 'diablocraft-z94g' in row['notes'], band   # the published number, nobody's override
attempts = next(r['value'] for r in d3_rows if r['item'] == 'gem_upgrade_attempts')
assert attempts.startswith('3 base attempts; +1 if no death in the rift') and 'Hardcore always qualifies' in attempts
assert (value('gr_urshi_tries_base'), value('gr_urshi_tries_no_death_bonus')) == (3, 1)
assert (value('urshi_burst'), value('urshi_per_second')) == (10, 5)           # the other window routes' values (q-0930-49), copied
assert rows['gr_urshi_display_id']['value'] == '29710' and 'ALEX JUDGES IT ON DEV' in rows['gr_urshi_display_id']['notes']
generated = read('mod-diablocraft/data/generated/tunables_0012.sql')
migration = read('mod-diablocraft/data/sql/db-world/updates/tunables_0012.sql')
urshi_rows = [n for n in rows if (n.startswith('gr_gem_chance_') or n.startswith('gr_urshi_') or n.startswith('urshi_')) and not n.startswith('gr_urshi_spawn_')]   # the spawn rows are a later migration (test_urshi_spawn.py)
assert len(urshi_rows) == 12 + 3 + 2, urshi_rows
for sql in (generated, migration):
    for name in urshi_rows:
        assert re.search(r"\('rifts', '%s', " % name, sql), name
assert "'gr_gem_chance_plus_0_to_6'" not in read('mod-diablocraft/data/sql/db-world/updates/tunables_0008.sql')   # a new migration, 0008 is applied

SEED = ', '.join(str(int(value('gr_gem_chance_' + band))) for band in BANDS)

HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include "%(header)s"

namespace G = DC::Rifts::Gr;

int main() {
    G::ChanceTable const table = {%(seed)s};

    // ---- the chance: every band of the sheet, at its edges, from the level and the gem's rank ----
    // difference = Greater Rift level - gem rank
    struct Case { long long difference; unsigned percent; };
    Case const cases[] = {
        {150, 100}, {11, 100}, {10, 100}, {9, 90}, {8, 80}, {7, 70}, {6, 60}, {3, 60}, {0, 60},
        {-1, 30}, {-2, 15}, {-3, 8}, {-4, 4}, {-5, 2}, {-6, 1}, {-10, 1}, {-15, 1}, {-16, 0}, {-17, 0}, {-100, 0}};
    for (Case const& c : cases) {
        unsigned level = 50, rank = static_cast<unsigned>(50 - c.difference);
        if (c.difference < 0) { level = 50; rank = static_cast<unsigned>(50 - c.difference); }
        if (c.difference > 49) { level = static_cast<unsigned>(c.difference); rank = 0; }
        assert(static_cast<long long>(level) - static_cast<long long>(rank) == c.difference);
        assert(G::UpgradeChance(level, rank, table) == c.percent);
    }
    assert(G::UpgradeChance(20, 0, table) == 100);                       // a fresh gem in a level 20 run: +20
    assert(G::UpgradeChance(1, 0, table) == 60);                         // level 1, rank 0: +1
    assert(G::UpgradeChance(10, 11, table) == 30);                       // the gem is one above the level
    // the chance follows the gem's CURRENT rank: it falls as the gem climbs past the level
    unsigned last = 101;
    for (unsigned rank = 0; rank < 40; ++rank) { unsigned c = G::UpgradeChance(20, rank, table); assert(c <= last); last = c; }
    // a table row above 100 never gives more than a sure thing
    G::ChanceTable wild = table; wild[0] = 250; assert(G::UpgradeChance(60, 0, wild) == 100);

    // ---- the roll: 100%% always lands, 0%% never, a roll below the chance lands ----
    assert(G::Succeeds(100, 0.0) && G::Succeeds(100, 0.999999));
    assert(!G::Succeeds(0, 0.0) && !G::Succeeds(0, 0.999999));
    assert(G::Succeeds(60, 0.5999) && !G::Succeeds(60, 0.6) && !G::Succeeds(60, 0.9));
    assert(G::Succeeds(1, 0.0099) && !G::Succeeds(1, 0.01));
    { unsigned hits = 0; for (unsigned i = 0; i < 100000; ++i) hits += G::Succeeds(30, (i + 0.5) / 100000); assert(hits == 30000); }

    // ---- the tries: 3, +1 if the member did not die, Hardcore always +1 ----
    assert(G::Tries(3, 1, 0, false) == 4);
    assert(G::Tries(3, 1, 1, false) == 3 && G::Tries(3, 1, 7, false) == 3);
    assert(G::Tries(3, 1, 0, true) == 4 && G::Tries(3, 1, 5, true) == 4);
    assert(G::Tries(0, 0, 0, false) == 0);                                  // numbers nobody set: no tries, not a crash
    assert(G::Tries(3, 0, 0, false) == 3);

    // ---- the maximum rank: a cap of 0 is no cap; at the cap is full, below is not ----
    assert(!G::AtMaxRank(500, 0) && !G::AtMaxRank(0, 0));
    assert(G::AtMaxRank(50, 50) && G::AtMaxRank(51, 50) && !G::AtMaxRank(49, 50));

    // ---- the order: worn first by rank, then bags and stash together by rank; ties keep the order read ----
    auto gem = [](std::string id, G::Where where, unsigned rank) { G::GemRow r; r.id = id; r.where = where; r.rank = rank; return r; };
    std::vector<G::GemRow> rows = {
        gem("b1", G::Where::Bags, 30), gem("w1", G::Where::Worn, 5), gem("s1", G::Where::Stash, 40),
        gem("w2", G::Where::Worn, 12), gem("b2", G::Where::Bags, 40), gem("w3", G::Where::Worn, 12),
        gem("s2", G::Where::Stash, 1), gem("w4", G::Where::Worn, 0)};
    G::OrderGems(rows);
    std::vector<std::string> ids; for (auto const& r : rows) ids.push_back(r.id);
    assert((ids == std::vector<std::string>{"w2", "w3", "w1", "w4", "s1", "b2", "b1", "s2"}));
    // a worn gem of rank 0 still comes before a bag gem of rank 99
    rows = {gem("b", G::Where::Bags, 99), gem("w", G::Where::Worn, 0)}; G::OrderGems(rows); assert(rows[0].id == "w");
    rows = {}; G::OrderGems(rows); assert(rows.empty());
    // ties keep the order they were read in, however many there are
    rows.clear();
    for (unsigned i = 0; i < 200; ++i) rows.push_back(gem(std::to_string(1000 + i), i %% 3 ? G::Where::Bags : G::Where::Stash, (i * 7) %% 4));
    G::OrderGems(rows);
    for (std::size_t i = 1; i < rows.size(); ++i) {
        assert(rows[i - 1].rank >= rows[i].rank);
        if (rows[i - 1].rank == rows[i].rank) assert(std::stoul(rows[i - 1].id) < std::stoul(rows[i].id));
    }

    // ---- the gem id ----
    assert(G::BagGemId(123456) == "g123456" && G::BagGemId(4294967295ull) == "g4294967295");
    assert(G::WornGemId(987, 0) == "w987_0" && G::WornGemId(987, 3) == "w987_3");

    // ---- who holds the rift open ----
    assert(G::NameList({"Anna"}) == "Anna" && G::NameList({"Anna", "Bo"}) == "Anna and Bo");
    assert(G::NameList({"Anna", "Bo", "Cy"}) == "Anna, Bo and Cy" && G::NameList({}).empty());
    assert(G::CloseRefusal({"Anna"}) == "Your rift cannot be closed while Anna still has upgrade attempts left with Urshi.");
    assert(G::CloseRefusal({"Anna", "Bo"}) == "Your rift cannot be closed while Anna and Bo still have upgrade attempts left with Urshi.");
    std::puts("harness ok");
    return 0;
}
'''


def run_harness(header: Path) -> subprocess.CompletedProcess:
    compiler = shutil.which('g++') or shutil.which('c++')
    if not compiler:
        raise SystemExit('g++ is not on PATH; this harness compiles a small C++ program')
    with tempfile.TemporaryDirectory(prefix='dc-urshi-') as directory:
        folder = Path(directory)
        (folder / 'test.cpp').write_text(HARNESS % {'header': header.as_posix(), 'seed': SEED}, encoding='utf-8')
        subprocess.run([compiler, '-std=c++20', '-UNDEBUG', '-Wall', '-Wno-unused', '-o', str(folder / 'urshi'),
                        str(folder / 'test.cpp')], check=True)
        return harness_env.run([str(folder / 'urshi')], capture_output=True, text=True)


ran = run_harness(HEADER)
assert ran.returncode == 0 and 'harness ok' in ran.stdout, ran.stdout + ran.stderr

# --- what the doubles cannot reach: the wiring --------------------------------------------------------------------------
urshi = read('mod-diablocraft/src/rifts/dc_gr_urshi.cpp')
internal = read('mod-diablocraft/src/rifts/dc_rifts_internal.h')
ai = read('mod-diablocraft/src/monsters/dc_monster_ai.cpp')
rifts = rifts_text()
quests = read('mod-diablocraft/src/rifts/dc_rift_quests.cpp')
progress = read('mod-diablocraft/src/rifts/dc_gr_progress.cpp')
rules = read('mod-diablocraft/src/rifts/dc_gr_rules.cpp')

# the Guardian's kill brings her, after the result is written and before the reward, once per run
kill = body(ai, 'bool CompleteGuardianKill(', '// 09 \u00a72 step 2.')
assert kill.index('RecordGuardianResult(rift);') < kill.index('BeginUrshi(dead, rift);') < kill.index('RewardGuardian(credit, dead, rift)')
begin = body(urshi, 'void BeginUrshi(', 'std::string UrshiBlocksClose')
assert 'rift.outcome != Gr::OutcomeName(true)' in begin                       # only an in-time kill: a late one gets none
assert 'if (runs.count(rift.instanceId))' in begin                           # a retried payout does not spawn her twice
assert 'EnrolledGuids(rift.id)' in begin and 'ObjectAccessor::FindPlayer(guid)' in begin       # members enrolled and online
assert 'GreaterRiftDeaths(rift.id, guid.GetCounter())' in begin and 'DC::Hardcore::IsHardcore(member)' in begin
assert 'Count("gr_urshi_tries_base"), Count("gr_urshi_tries_no_death_bonus")' in begin
assert 'SummonCreature(' in begin and 'URSHI_ENTRY, UrshiSpot(guardian,' in begin       # near where the Guardian died (test_urshi_spawn.py)
assert re.search(r'GreaterRiftDeaths\(std::uint64_t runId, std::uint32_t character\)', rules)
assert 'deaths.find({runId, character})' in rules                          # the counter rule 5 already keeps

# every way of closing is refused while a member has tries
close = body(rifts, 'bool Close(Player* player, std::string& error)', '// --- elite packs')
assert close.index('OwnedRift(player, rift)') < close.index('UrshiBlocksClose(rift.id)') < close.index('pendingCloses.emplace')
turn_in = body(quests, 'void HandleTurnIn(', '// Guardian death (7.4)')
assert turn_in.index('UrshiBlocksClose(rift.id)') < turn_in.index('pendingCloses.emplace')
keeper = body(quests, 'class RiftKeeper final', 'bool OnGossipSelect')
assert 'UrshiBlocksClose(rift.id)' in keeper and keeper.index('UrshiBlocksClose') < keeper.index('AddMenuItem')
assert keeper.count('AddMenuItem') == 1
# nothing else sets pendingCloses or closes a run on a player's say-so
assert len(re.findall(r'pendingCloses\.emplace', rifts + quests)) == 2         # Close() and HandleTurnIn: both guarded above
assert len(re.findall(r'\bQueueClose\(', rifts + quests)) == 3                  # its definition, the countdown's end, the last logout

# leave / kick / logout lose the tries; the map's end and tick
detach = body(quests, 'void DetachMember(', 'void HandleLogout(')
assert 'UrshiMemberLeft(rift.id, guid, player);' in detach             # leave and kick both reach DetachMember
assert 'DetachMember(rift, guid, left, kicked ? "kicked" : "left"' in quests
logout = body(quests, 'void HandleLogout(', '// 7.5\'s login sweep')
assert logout.index('UrshiMemberLeft(rift.id, player->GetGUID(), nullptr);') < logout.index('QueueClose(rift)')
assert logout.index('UrshiMemberLeft') < logout.index('bool const solo')       # before either branch, so a party member's logout counts too
assert 'EndUrshi(map->GetInstanceId());' in body(rifts, 'void OnDestroyMap(Map* map) override', 'class ')
assert 'UrshiTick(map);' in body(progress, 'void GreaterTick(Map* map)', 'std::vector<Orb> lying')
assert 'RegisterUrshiScripts();' in body(rifts, 'void RegisterScripts()', 'new RiftCommand();')
for declaration in ('void BeginUrshi(Creature* guardian, Rift const& rift);', 'std::string UrshiBlocksClose(std::uint64_t runId);',
                    'void UrshiMemberLeft(std::uint64_t runId, ObjectGuid member, Player* notify);',
                    'void UrshiTick(Map* map);', 'void EndUrshi(std::uint32_t instanceId);', 'void RegisterUrshiScripts();',
                    'unsigned GreaterRiftDeaths(std::uint64_t runId, std::uint32_t character);'):
    assert declaration in internal, declaration

# the places the list reads, the writes of a success, the order of a request
gems = body(urshi, 'std::vector<Gr::GemRow> ReadGems(', 'struct Seat')
assert "kind='gem' AND legendary_rank IS NOT NULL AND item_guid IN" in gems            # worn: the socket rows of the worn items
assert 'EQUIPMENT_SLOT_START' in gems and 'INVENTORY_SLOT_ITEM_START' in gems and 'INVENTORY_SLOT_BAG_START' in gems
assert "s.account_id={} AND s.mode='{}'" in gems and 'dc_account_stash_item' in gems   # the stash, this account and mode
assert 'owner_guid' not in gems and 'BANK' not in gems.upper()                         # other characters' gems and the bank are not read
assert 'Gr::OrderGems(out);' in gems
assert 'dc_legendary_gem_rank WHERE item_guid IN' in gems                              # a gem with no row is rank 0
upgrade = body(urshi, 'void Upgrade(', 'void Handle(')
assert upgrade.index('AtMaxRank') < upgrade.index('--member->left') < upgrade.index('Gr::Succeeds(')   # a full gem costs no try; the try is spent before the roll
assert 'Roll()' in upgrade and 'Chances()' in upgrade and 'found->rank, Chances()' in upgrade       # the chance of the rank now
assert upgrade.index('RemoveContributions(&player, host)') < upgrade.index('UPDATE dc_item_affix SET legendary_rank') < upgrade.index('RefreshContributions(&player, host)')
assert 'REPLACE INTO dc_legendary_gem_rank(item_guid,gem_rank)' in upgrade
assert upgrade.count('--member->left') == 1 and 'left = 0' in upgrade                  # one try, no refund on a failure
assert upgrade.index('Send(&player, {"U"') < upgrade.index('SendList(player, after, gems)')
assert 'That gem is not there any more.' in upgrade and ' is at its maximum rank.' in upgrade
handle = body(urshi, 'void Handle(', 'class UrshiCreature')
assert 'request.Count() == 1' in handle and 'request.Count() == 2' in handle and 'DC::Bridge::TextMalformed' in handle
assert 'Routes().Add(PREFIX, {"rifts", "urshi_burst", "urshi_per_second"}, Handle)' in urshi
assert 'CreatureScript("dc_urshi")' in urshi

# the creature template matches the code
generator = read('mod-diablocraft/scripts/generate/rifts/generate_rifts.py')
entry = re.search(r'URSHI_ENTRY = (\d+)', urshi).group(1)
assert re.search(r'^URSHI_ENTRY = %s$' % entry, generator, re.M) and 'URSHI_SCRIPT = "dc_urshi"' in generator
sql = read('mod-diablocraft/data/sql/db-world/updates/rifts_0017_urshi.sql')
assert read('mod-diablocraft/data/generated/rift_urshi.sql') == sql
assert '`entry` = %s' % entry in sql and "`ScriptName` = 'dc_urshi'" in sql and '`npcflag` = 1' in sql and '(%s, 0, 29710,' % entry in sql
assert int(entry) not in {910000, 910001, 910002, 910003, 910004, 910015, 910018}

# the contract equals the code: prefix, every record letter and every refusal text
contract = read('docs/contracts/urshi-messages.md')
assert 'DCURSHI' in contract and 'PREFIX = "DCURSHI"' in urshi
for letter in ('W', 'L', 'G', 'E', 'U', 'C', 'X'):
    assert '`%s\\|' % letter in contract, letter
for letter in re.findall(r'Send\(&?(?:player|notify), \{"(\w)"', urshi):
    assert letter in 'WLGEUC', letter
for text in re.findall(r'Refusal\(\s*"([^"]+)"\)', urshi):
    assert text.replace('"', '') in contract or text.startswith('You cannot do that'), text
for text in ('Urshi is not near you.', 'Urshi has nothing more for you.', 'You have no upgrade attempts left.',
             'That gem is not there any more.', 'You cannot do that while dead.'):
    assert text in contract and text in urshi, text
assert 'Your rift cannot be closed while <names> still have upgrade attempts' in contract.replace('\n  ', ' ')

# --- mutation runs: every mutant of the header makes the harness fail ---------------------------------------------------
if 'DC_URSHI_HEADER' not in os.environ:
    text = HEADER.read_text(encoding='utf-8')
    mutants = {
        '+10 or more falls into the +9 band': ('if (difference >= 10)\n            return 0;', 'if (difference >= 10)\n            return 1;'),
        'the +7 band ends at +8': ('if (difference >= 7)', 'if (difference >= 8)'),
        'the 0 to +6 band is the +7 band': ('if (difference >= 0)\n            return 4;', 'if (difference >= 0)\n            return 3;'),
        'a gem one above the level is in the 0 band': ('if (difference >= -5)', 'if (difference >= -0)'),
        'the -6 to -15 band reaches -16': ('return difference >= -15 ? 10 : 11;', 'return difference >= -16 ? 10 : 11;'),
        'a chance over 100 is kept': ('return std::min(100u, table[', 'return (table['),
        'a roll equal to the chance lands': ('return roll * 100.0 < static_cast<double>(chancePercent);',
                                             'return roll * 100.0 <= static_cast<double>(chancePercent);'),
        'Hardcore gets no bonus': ('hardcore || deaths == 0 ? noDeathBonus : 0', 'deaths == 0 ? noDeathBonus : 0'),
        'a death costs nothing': ('hardcore || deaths == 0 ? noDeathBonus : 0', 'noDeathBonus'),
        'the cap is a rank too far': ('return maxRank > 0 && rank >= maxRank;', 'return maxRank > 0 && rank > maxRank;'),
        'a capless gem is full': ('return maxRank > 0 && rank >= maxRank;', 'return rank >= maxRank;'),
        'worn gems are not first': ('if (wornA != wornB)\n                                 return wornA;\n', ''),
        'ranks sort lowest first': ('return a.rank > b.rank;', 'return a.rank < b.rank;'),
        'the sort is not stable': ('std::stable_sort(', 'std::sort('),
        'the worn id loses its socket': ('"w" + std::to_string(hostGuid) + "_" + std::to_string(seq)', '"w" + std::to_string(hostGuid)'),
        'the refusal names nobody': ('"Your rift cannot be closed while " + NameList(holders)', '"Your rift cannot be closed while someone"'),
    }
    with tempfile.TemporaryDirectory(prefix='dc-urshi-mutants-') as directory:
        for name, (old, new) in mutants.items():
            assert text.count(old) >= 1, name
            mutated = Path(directory) / 'dc_gr_urshi.h'
            mutated.write_text(text.replace(old, new, 1), encoding='utf-8')
            try:
                outcome = run_harness(mutated)
                survived = outcome.returncode == 0
            except subprocess.CalledProcessError:
                survived = False                                  # does not even compile: killed
            assert not survived, 'mutant survived: ' + name
    print('mutants killed: %d' % len(mutants))

print('PASS: Urshi: tries, chance bands, roll, max rank, list order, ids, close refusal, wiring, rows, contract.')
