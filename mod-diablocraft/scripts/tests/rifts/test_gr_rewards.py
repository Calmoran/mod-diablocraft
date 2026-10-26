"""Greater Rift Guardian rewards by level (diablocraft-yxsa, greater-rifts brief part 8).

Compiles the production pieces against core doubles:
  - dc_gr_rewards.h as it is (curve A, the legendary count, the gold and XP factors, the gem pick);
  - the whole body of dc_gr_rewards.cpp, with the tunables and the character's unowned-gem list replaced by
    doubles: GuardianReward and GuardianXpFactor driven the way RewardGuardian and GreaterRiftXp drive them,
    with every number read from data/tunables/rifts.csv, the sheet the code reads at run time;
and checks the proposal's sample values (GR 10 1.1, 25 3.1, 50 6.4, 75 9.9, 85 11.3, 90+ 12) and the average
over many kills. Source scans cover what a double cannot reach (the loot roll's use of the reward, the gem
drop's delivery, the ownership query, the reward call); the test says so below.

Cross-source: the start is the brief's own derivation (loot_tuning.csv elite legendary rate x the
rift_guardian row's average item count); the XP bands and the gold rate are greater_rifts.csv's own text;
the XP table is as long as its last level says, and blank (the designer's); the rows are in the generated SQL.

DC_GR_REWARDS_SOURCE and DC_GR_REWARDS_HEADER point the compile at mutated copies (mutation runs)."""
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
import harness_env
import loot_source
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
CPP = Path(os.environ.get('DC_GR_REWARDS_SOURCE', MODULE / 'src/rifts/dc_gr_rewards.cpp'))
HEADER = Path(os.environ.get('DC_GR_REWARDS_HEADER', MODULE / 'src/rifts/dc_gr_rewards.h'))
SOURCE = CPP.read_text(encoding='utf-8')


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def body(text: str, start: str, end: str) -> str:
    """The text from `start` up to (not including) the next `end` after it."""
    first = text.index(start)
    return text[first:text.index(end, first)]


def value(name: str) -> float:
    return tunables_csv.value('rifts', name)


# --- cross-source: the rows the code reads exist, with the numbers the sources name -------------------------
rows = {r['name']: r for r in csv.DictReader((MODULE / 'data/tunables/rifts.csv').open(encoding='utf-8', newline=''))}
read_names = set(re.findall(r'Row\("(gr_\w+)"\)', SOURCE))
assert read_names == {'gr_legendary_start', 'gr_legendary_bend', 'gr_legendary_cap', 'gr_legendary_cap_level',
                      'gr_gold_per_level', 'gr_xp_table_last_level', 'gr_xp_mid_last_level', 'gr_xp_per_level_mid',
                      'gr_xp_per_level_high'}, read_names
assert 'gr_xp_level_%02u' in SOURCE
for name in read_names:
    assert name in rows, name

# curve A: start = the general legendary rate x the Guardian's item count (brief part 8: 1% x 4 = 0.04)
loot = {r['source']: r for r in csv.DictReader((MODULE / 'data/tunables/loot_tuning.csv').open(encoding='utf-8', newline=''))}
rate = float(loot['elite']['legendary_base_pct']) / 100
items = (float(loot['rift_guardian']['drops_min']) + float(loot['rift_guardian']['drops_max'])) / 2
assert abs(value('gr_legendary_start') - rate * items) < 1e-12 and (rate, items) == (0.01, 4.0)
assert (value('gr_legendary_bend'), value('gr_legendary_cap_level'), value('gr_legendary_cap')) == (1.05, 90, 12)
proposal = read('docs/proposals/greater-rifts.md')
assert 'start + (12 − start) × ((level − 1) / 89) ^ 1.05' in proposal
assert 'GR 10 1.1, 25 3.1, 50 6.4, 75 9.9,' in proposal and '85 11.3, 90+ 12' in proposal
assert 'No guaranteed legendary' in proposal
for name in ('gr_legendary_start', 'gr_legendary_bend', 'gr_legendary_cap_level', 'gr_legendary_cap'):
    assert rows[name]['d3_value'] == '' and rows[name]['value'] and 'ruling 2026-10-04' in rows[name]['notes'], name

d3 = {r['item']: r['value'] for r in csv.DictReader((MODULE / 'data/d3/greater_rifts.csv').open(encoding='utf-8', newline=''))}
assert d3['gold_gain_per_rank'].startswith('+1.03% per rank (multiplicative)') and value('gr_gold_per_level') == 1.0103
assert d3['xp_gain_per_rank'].startswith('GR1-25 hand-picked per rank (NOT PUBLISHED as a formula); x1.08 per rank GR26-70; '
                                         'x1.05 per rank GR71-150')
assert (value('gr_xp_per_level_mid'), value('gr_xp_per_level_high')) == (1.08, 1.05)
assert (value('gr_xp_table_last_level'), value('gr_xp_mid_last_level')) == (25, 70)
assert value('gr_xp_table_last_level') == value('gr_damage_low_last_level')       # the same GR1-25 band the sheet names
assert value('gr_xp_mid_last_level') == value('gr_damage_mid_last_level')         # and GR26-70
table_rows = ['gr_xp_level_%02d' % level for level in range(2, int(value('gr_xp_table_last_level')) + 1)]
assert len(table_rows) == 24
for name in table_rows:                                                           # the designer's: nobody published them
    assert name in rows and rows[name]['d3_value'] == '' and rows[name]['value'] == '' and 'ALEX SETS IT' in rows[name]['notes'], name
assert not [n for n in rows if n.startswith('gr_xp_level_') and n not in table_rows]
generated = read('mod-diablocraft/data/generated/tunables_0008.sql')
migration = read('mod-diablocraft/data/sql/db-world/updates/tunables_0008.sql')
for sql in (generated, migration):
    for name in sorted(read_names | set(table_rows)):
        assert re.search(r"\('rifts', '%s', " % name, sql), name


def effective(name):
    try:
        return repr(value(name))
    except tunables_csv.MissingTunable:
        return 'std::nullopt'


SEED = ',\n    '.join('{"%s", %s}' % (name, effective(name)) for name in rows)

# Blood Shards (Kadala part 2): the Greater formula is kadala.csv's own text, ten Nephalem rows, all in the generated SQL
kadala = {r['rule']: r['value'] for r in csv.DictReader((MODULE / 'data/d3/kadala.csv').open(encoding='utf-8', newline=''))}
assert kadala['blood_shard_drop_gr_formula'] == 'Blood Shards = (GR Level * 3) + 127'
assert (rows['blood_shards_gr_base']['d3_value'], rows['blood_shards_gr_per_level']['d3_value']) == ('127', '3')
assert re.findall(r'Row\("(blood_shards_\w+)"\)', SOURCE) == ['blood_shards_gr_base', 'blood_shards_gr_per_level']
assert [n for n in rows if n.startswith('blood_shards_nr_tier_')] == ['blood_shards_nr_tier_%02d' % t for t in range(1, 11)]
assert read('mod-diablocraft/data/tunables/monsters.csv').count('launch_tier_count,,10,') == 1      # ten tiers, Normal to Torment VI
generated = read('mod-diablocraft/data/generated/tunables_0012.sql')
assert generated.count("('rifts', 'blood_shards_") == 12 and generated == read('mod-diablocraft/data/sql/db-world/updates/tunables_0012.sql')

# --- what the doubles cannot reach: the roll, the gem's delivery, the ownership, the reward call --------------
loot_cpp = loot_source.source()   # R4: the roll and hooks (dc_loot.cpp) and DeliverGemDrop (dc_loot_delivery.cpp)
roll = body(loot_cpp, 'Result RollLoot(Player* player, Source source', '    // L10 Death')
assert 'GreaterReward const* greater' in roll
assert 'DC::Rifts::Gr::LegendaryCount(greater->legendaries, Roll())' in roll
assert 'index < drops + legendaries' in roll
assert 'index == 0 && !greater' in roll                          # no guaranteed legendary in a Greater Rift
assert 'index >= drops ||' in roll and '(!greater && Roll() * 100.0 < legendaryPct)' in roll
assert roll.index('index >= drops') < roll.index('PickNonLegendary')
assert 'DC::Rifts::Gr::PickGem(greater->gems, Roll())' in roll and 'DeliverGemDrop(player, gem, monsterLevel' in roll
assert roll.index('DeliverGemDrop') > roll.index('PlayerEconomy::Fail(); result.ok = false;')   # after the item loop
assert 'greater->goldFactor' in body(loot_cpp, '// L10 gold: our roll', '// L10 Death')
gem_drop = body(loot_cpp, 'void DeliverGemDrop(', '// L5, one material row')
assert gem_drop.index('if (corpse)') < gem_drop.index('else if (ground)') < gem_drop.index('DeliverGem(player,gem)')
assert 'BufferGem(player,gem,level)' in gem_drop                 # a full bag holds the gem, as every other gem
assert loot_cpp.count('DeliverGemDrop(') == 4                    # the definition, the Guardian's, the kill hook's, the Broken Crown extra gem's
assert re.search(r'if \(std::uint32_t const extra = BrokenCrownGem\(member, gem\)\)\s*DeliverGemDrop\(member, extra,', loot_cpp)   # the fourth call is that one
loot_h = read('mod-diablocraft/src/loot/dc_loot.h')
assert 'Position const* dropOrigin = nullptr, GreaterReward const* greater = nullptr);' in loot_h

ai = read('mod-diablocraft/src/monsters/dc_monster_ai.cpp')
reward = body(ai, 'bool PayGuardianMember(', 'bool IsGuardianEntry')   # the member's payout, which the kill and the corpse's first open both run (F7)
assert 'if (rift.mode == "gr")' in reward and 'greater = GuardianReward(member, rift);' in reward
assert 'rift.mode == "gr" ? &greater : nullptr' in reward
assert 'outcome' not in reward and 'expired' not in reward      # the gem drops on a failed run too (ruling 6)
rules = read('mod-diablocraft/src/rifts/dc_gr_rules.cpp')
xp = body(rules, 'std::uint64_t GreaterRiftXp(', 'void RegisterGreaterRiftRuleScripts')
assert 'Gr::ScaleXp(scaled, GuardianXpFactor(level))' in xp and 'if (!guardian)' in xp
assert xp.index('if (!guardian)') < xp.index('GuardianXpFactor')
internal = read('mod-diablocraft/src/rifts/dc_rifts_internal.h')
assert 'DC::Loot::GreaterReward GuardianReward(Player* member, Rift const& rift);' in internal
assert 'double GuardianXpFactor(unsigned level);' in internal

items_cpp = read('mod-diablocraft/src/items/dc_items_gems.cpp')
owned = body(items_cpp, 'std::vector<std::uint32_t> UnownedLegendaryGems(Player* player)', '\nstd::uint32_t LegendaryGemRankOf')
assert 'player->GetItemByEntry(gem.first)' in owned                                    # bags and worn, as the server holds them
assert 'SELECT itemEntry FROM item_instance WHERE owner_guid={}' in owned                # everything the character owns, the bank too
assert "a.kind='gem' AND a.legendary_rank IS NOT NULL" in owned and 'i.owner_guid={}' in owned   # socketed in what it owns
assert owned.count('FROM dc_account_stash_item s') == 2 and owned.count("s.mode='{}'") == 2   # and in its stash, this mode's
assert owned.count('IN (" + entries + ")') == 2
assert 'DC::Hardcore::ModeOf(player) == DC::Hardcore::Mode::Hardcore' in owned
assert '!owned.count(gem.first)' in owned
items_h = read('mod-diablocraft/src/items/dc_items.h')
assert 'std::vector<std::uint32_t> UnownedLegendaryGems(Player* player);' in items_h
table = read('mod-diablocraft/data/sql/db-world/updates/legendary_gems_0002_items.sql')
assert len(re.findall(r'INSERT INTO `dc_legendary_gem_item`', table)) == 21               # 21 gems to pick from

HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "%(loot)s"
#include "%(header)s"

// ---- doubles for the core and the sheet ----
struct Player {};
std::map<std::string, std::optional<double>> tunables = {
    %(seed)s
};
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
std::vector<std::uint32_t> unowned;
namespace DC::Items { std::vector<std::uint32_t> UnownedLegendaryGems(Player*) { return unowned; } }
namespace DC::Rifts {
    struct Rift { unsigned grRank = 0, tier = 1; std::string mode = "nr"; };
    DC::Loot::GreaterReward GuardianReward(Player* member, Rift const& rift);
    double GuardianXpFactor(unsigned level);
    std::uint64_t GuardianShards(Rift const& rift);
}
'''

BODY = SOURCE[SOURCE.index('namespace DC::Rifts'):]

MAIN = r'''
using namespace DC::Rifts;
namespace G = DC::Rifts::Gr;
std::map<std::string, std::optional<double>> const sheet = tunables;

double legendaries(unsigned level) { Player p; Rift r; r.grRank = level; return GuardianReward(&p, r).legendaries; }
bool near(double a, double b, double tolerance) { return std::fabs(a - b) <= tolerance; }

int main() {
    // ---- curve A, the proposal's sample values (the sheet's start, bend, cap and cap level) ----
    assert(near(legendaries(1), 0.04, 1e-12));
    assert(near(legendaries(10), 1.1, 0.05) && near(legendaries(25), 3.1, 0.05) && near(legendaries(50), 6.4, 0.05));
    assert(near(legendaries(75), 9.9, 0.05) && near(legendaries(85), 11.3, 0.05));
    assert(legendaries(90) == 12 && legendaries(91) == 12 && legendaries(100) == 12 && legendaries(150) == 12);
    assert(near(legendaries(89), 11.86, 0.01));                                       // just short of the cap, not above it
    for (unsigned level = 1; level < 90; ++level) assert(legendaries(level) < legendaries(level + 1));   // one smooth rise
    assert(near(legendaries(0), 0.04, 1e-12));                                        // no level: the start, never a crash
    // start, bend and cap level are tunables: the curve follows them
    tunables["gr_legendary_start"] = 1.0; assert(near(legendaries(1), 1.0, 1e-12));
    tunables["gr_legendary_cap_level"] = 50; assert(legendaries(50) == 12 && legendaries(49) < 12);
    tunables["gr_legendary_bend"] = 2.0; assert(near(legendaries(26), 1.0 + 11.0 * std::pow(25.0 / 49.0, 2.0), 1e-9));
    tunables = sheet;

    // ---- how many legendaries one kill drops: the whole part, the fraction a chance of one more ----
    assert(G::LegendaryCount(6.4, 0.0) == 7 && G::LegendaryCount(6.4, 0.39) == 7 && G::LegendaryCount(6.4, 0.41) == 6);
    assert(G::LegendaryCount(6.4, 0.9999) == 6);
    assert(G::LegendaryCount(12, 0.0) == 12 && G::LegendaryCount(12, 0.9999) == 12);  // a whole number never rolls an extra
    assert(G::LegendaryCount(0, 0.0) == 0 && G::LegendaryCount(-3, 0.0) == 0 && G::LegendaryCount(std::nan(""), 0.0) == 0);
    // no guaranteed legendary: at level 1 most kills drop none
    {
        unsigned none = 0, one = 0, more = 0; unsigned const kills = 100000;
        for (unsigned i = 0; i < kills; ++i) {
            unsigned const n = G::LegendaryCount(legendaries(1), (i + 0.5) / kills);
            none += n == 0; one += n == 1; more += n > 1;
        }
        assert(near(one / double(kills), 0.04, 1e-4) && none + one == kills && more == 0);
    }
    // the average over many kills is the curve, at every sample level; a level's count is its whole part or one more
    for (unsigned level : {1u, 10u, 25u, 50u, 75u, 85u, 90u, 120u}) {
        double const average = legendaries(level); unsigned const kills = 200000; double sum = 0;
        for (unsigned i = 0; i < kills; ++i) {
            unsigned const n = G::LegendaryCount(average, (i + 0.5) / kills);
            assert(n == unsigned(std::floor(average)) || n == unsigned(std::floor(average)) + 1);
            sum += n;
        }
        assert(near(sum / kills, average, 1e-3));
    }

    // ---- gold: x1.0103 per level above the first ----
    {
        Player p; Rift r;
        r.grRank = 1; assert(GuardianReward(&p, r).goldFactor == 1.0);
        r.grRank = 2; assert(near(GuardianReward(&p, r).goldFactor, 1.0103, 1e-12));
        r.grRank = 75; assert(near(GuardianReward(&p, r).goldFactor, std::pow(1.0103, 74), 1e-9));
        r.grRank = 0; assert(GuardianReward(&p, r).goldFactor == 1.0);
        tunables["gr_gold_per_level"] = std::nullopt; r.grRank = 50; assert(GuardianReward(&p, r).goldFactor == 1.0);   // no number: no scaling
        tunables = sheet;
    }

    // ---- XP: the designer's table to level 25, x1.08 per level to 70, x1.05 above ----
    assert(GuardianXpFactor(1) == 1.0);
    for (unsigned level = 1; level <= 25; ++level) assert(GuardianXpFactor(level) == 1.0);   // the table is blank: level 1's XP
    assert(near(GuardianXpFactor(26), 1.08, 1e-12) && near(GuardianXpFactor(27), 1.08 * 1.08, 1e-12));
    assert(near(GuardianXpFactor(70), std::pow(1.08, 45), 1e-9));
    assert(near(GuardianXpFactor(71), std::pow(1.08, 45) * 1.05, 1e-9) && near(GuardianXpFactor(75), std::pow(1.08, 45) * std::pow(1.05, 5), 1e-9));
    assert(near(GuardianXpFactor(150), std::pow(1.08, 45) * std::pow(1.05, 80), 1e-6));
    tunables["gr_xp_level_02"] = 1.1; tunables["gr_xp_level_03"] = 1.3; tunables["gr_xp_level_05"] = 2.0;
    assert(GuardianXpFactor(1) == 1.0 && GuardianXpFactor(2) == 1.1 && GuardianXpFactor(3) == 1.3);
    assert(GuardianXpFactor(4) == 1.3 && GuardianXpFactor(5) == 2.0 && GuardianXpFactor(25) == 2.0);   // a blank row repeats the one before
    assert(near(GuardianXpFactor(26), 2.0 * 1.08, 1e-12) && near(GuardianXpFactor(71), 2.0 * std::pow(1.08, 45) * 1.05, 1e-9));
    tunables["gr_xp_table_last_level"] = 4;                                          // the table is as long as the sheet says
    assert(GuardianXpFactor(4) == 1.3 && near(GuardianXpFactor(5), 1.3 * 1.08, 1e-12) && near(GuardianXpFactor(6), 1.3 * 1.08 * 1.08, 1e-12));
    tunables = sheet;
    tunables["gr_xp_per_level_mid"] = std::nullopt;                                  // a band with no number is no growth, not a crash
    assert(GuardianXpFactor(40) == 1.0 && near(GuardianXpFactor(75), std::pow(1.05, 5), 1e-9));
    tunables = sheet;

    // ---- Blood Shards (Kadala part 2): a Nephalem Guardian pays its tier's row, a Greater one 127 + 3 x level ----
    {
        Rift r;
        for (unsigned tier = 1; tier <= 10; ++tier) { r.tier = tier; assert(GuardianShards(r) == 50); }   // the placeholder, every tier
        tunables["blood_shards_nr_tier_04"] = 80; r.tier = 4; assert(GuardianShards(r) == 80);
        r.tier = 3; assert(GuardianShards(r) == 50);                                  // the other tiers keep their own row
        tunables["blood_shards_nr_tier_04"] = std::nullopt; r.tier = 4; assert(GuardianShards(r) == 0);   // a blank row pays nothing
        r.tier = 11; assert(GuardianShards(r) == 0);                                  // no tier 11 row
        r.tier = 0; assert(GuardianShards(r) == 0);
        tunables = sheet;
        r.mode = "gr"; r.tier = 1;
        r.grRank = 1; assert(GuardianShards(r) == 130);
        r.grRank = 25; assert(GuardianShards(r) == 202);
        r.grRank = 50; assert(GuardianShards(r) == 277);
        r.grRank = 75; assert(GuardianShards(r) == 352);                              // maxroll: 127 + 3 x level
        r.grRank = 100; assert(GuardianShards(r) == 427);
        tunables["blood_shards_gr_per_level"] = 4; r.grRank = 75; assert(GuardianShards(r) == 427);   // both numbers are the sheet's
        tunables["blood_shards_gr_base"] = 0; assert(GuardianShards(r) == 300);
        tunables = sheet;
        r.mode = "nr"; r.tier = 2; r.grRank = 75; assert(GuardianShards(r) == 50);    // the level is read only in a Greater Rift
        // the chat line
        assert(G::ShardLine(352, 0) == "You receive 352 Blood Shards.");
        assert(G::ShardLine(1, 0) == "You receive 1 Blood Shard.");
        assert(G::ShardLine(352, 100) == "You receive 252 Blood Shards. 100 Blood Shards were lost: you cannot hold more.");
        assert(G::ShardLine(352, 351) == "You receive 1 Blood Shard. 351 Blood Shards were lost: you cannot hold more.");
        assert(G::ShardLine(352, 1) == "You receive 351 Blood Shards. 1 Blood Shard was lost: you cannot hold more.");
        assert(G::ShardLine(352, 352) == "352 Blood Shards were lost: you cannot hold more.");   // at the cap: nothing arrives
        assert(G::ShardLine(50, 999) == "999 Blood Shards were lost: you cannot hold more.");   // a loss above the pay never wraps the received count
        assert(G::ShardsFor(127, 3, 75) == 352 && G::ShardsFor(-5, 0, 0) == 0 && G::ShardsFor(std::nan(""), 3, 1) == 0);
        assert(G::ShardsFor(50, 0, 0) == 50 && G::ShardsFor(49.9, 0, 0) == 49 && G::ShardsFor(1e30, 0, 0) == 0);
    }

    // ---- the gem: one the character does not own, evenly, none when it owns all ----
    {
        Player p; Rift r; r.grRank = 10;
        unowned = {103100, 103105, 103119};
        assert(GuardianReward(&p, r).gems == unowned);                               // exactly what the character is missing
        unowned = {};
        assert(GuardianReward(&p, r).gems.empty());
        std::vector<std::uint32_t> missing{103100, 103101, 103102, 103103, 103104};
        assert(G::PickGem({}, 0.5) == 0);                                            // owns all 21: no gem
        unsigned seen[5] = {0, 0, 0, 0, 0};
        for (unsigned i = 0; i < 50000; ++i) {
            std::uint32_t const gem = G::PickGem(missing, (i + 0.5) / 50000);
            assert(std::find(missing.begin(), missing.end(), gem) != missing.end());   // never one it owns
            ++seen[gem - 103100];
        }
        for (unsigned count : seen) assert(count == 10000);
        assert(G::PickGem(missing, 0.0) == 103100 && G::PickGem(missing, 1.0) == 103104 && G::PickGem(missing, 7.0) == 103104);
        assert(G::PickGem(missing, -1.0) == 103100);
    }

    // ---- XP scaling: whole XP, rounded down; a broken factor is no scaling ----
    assert(G::ScaleXp(1000, 2.5) == 2500 && G::ScaleXp(7, 1.5) == 10 && G::ScaleXp(0, 9.0) == 0);
    assert(G::ScaleXp(1000, 0.0) == 1000 && G::ScaleXp(1000, -2.0) == 1000 && G::ScaleXp(1000, std::nan("")) == 1000);
    assert(G::ScaleXp(1ull << 60, 1e30) == UINT64_MAX);                              // no wrap
    return 0;
}
'''

code = (HARNESS % {'loot': (MODULE / 'src/loot/dc_loot.h').as_posix(), 'header': HEADER.as_posix(), 'seed': SEED}) + BODY + MAIN

compiler = shutil.which('g++') or shutil.which('c++')
if not compiler:
    raise SystemExit('g++ is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-rewards-') as directory:
    folder = Path(directory)
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    subprocess.run([compiler, '-std=c++20', '-UNDEBUG', '-Wall', '-Wno-unused', '-o', str(folder / 'gr_rewards'),
                    str(folder / 'test.cpp')], check=True)
    harness_env.run([str(folder / 'gr_rewards')], check=True)
print('PASS: Greater Rift rewards: curve A samples and average, gold, XP table and bands, gem pick, wiring, tunables.')
