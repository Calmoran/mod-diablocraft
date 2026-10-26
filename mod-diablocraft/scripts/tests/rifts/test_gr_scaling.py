"""Greater Rift levels and difficulty (diablocraft-5o8y, greater-rifts brief part 3).

Compiles the production pieces against core doubles and feeds them the values of the data files:
  - dc_gr_scaling.h as it is (Life x per level, the three damage bands, party Life; no Life cap since the 64-bit pool, diablocraft-12in);
  - GreaterNumbers, GreaterScaling and GreaterRiftDamage cut out of dc_difficulty.cpp, reading the
    rifts tunables (from data/tunables/rifts.csv) and the tier rows (from difficulty_tiers.csv and
    dc_tier_phase), exactly what TierBalance multiplies a Greater Rift monster by;
  - both AffixDamage definitions cut out of dc_affix_common.cpp, with their declarations from dc_affix_internal.h (an elite's affix damage inside a
    Greater Rift follows the level, outside it the tier).
Cross-source: the tunables equal what greater_rifts.csv and party_scaling.csv publish. The brief's
anchors (GR 1 = Hard, GR 10 = Torment I, GR 25 = Torment VI) are checked, not used: ANCHOR_MARGIN.
What it does NOT cover (needs the server): TierBalance itself, the map lookup behind
GreaterRiftLevel, AutoBalance applying the multipliers; a source scan checks they are wired.

DC_GR_SCALING_HEADER, DC_GR_DIFFICULTY_SOURCE, DC_GR_ELITES_SOURCE (a copy of src) and DC_GR_RIFTS_SOURCE point the compile
and the scans at mutated copies (mutation runs)."""
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
from split_sources import affixes_text  # noqa: E402
import harness_env
import tunables_csv

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
D3 = MODULE / 'data/d3'
HEADER = Path(os.environ.get('DC_GR_SCALING_HEADER', MODULE / 'src/difficulty/dc_gr_scaling.h'))
DIFFICULTY = Path(os.environ.get('DC_GR_DIFFICULTY_SOURCE', MODULE / 'src/difficulty/dc_difficulty.cpp'))
ELITES = Path(os.environ.get('DC_GR_ELITES_SOURCE', MODULE / 'src'))
DIFF_SRC = DIFFICULTY.read_text(encoding='utf-8')
ELITE_SRC = affixes_text(ELITES)
RIFTS_SRC = Path(os.environ.get('DC_GR_RIFTS_SOURCE', MODULE / 'src/rifts/dc_rifts.cpp')).read_text(encoding='utf-8')

# The stated margin: how far GR 10 / GR 25 may sit from Torment I / VI (Life and damage).
ANCHOR_MARGIN = 0.02


def rows(name):
    with (D3 / name).open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))


def pct(text):
    return float(text.rstrip('%')) / 100


def block(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def tunable(name):
    return tunables_csv.value('rifts', name)


# --- cross-source 1: the tunables are what greater_rifts.csv and party_scaling.csv publish ----------
gr = {r['item']: r for r in rows('greater_rifts.csv') if r['item'] not in ('rank', 'ranks')}
assert tunable('gr_life_per_level') == float(re.search(r'x([\d.]+) per rank GR1-150', gr['monster_health_scaling_bands']['value']).group(1))
bands = re.findall(r'x([\d.]+) per rank GR(\d+)-(\d+)', gr['monster_damage_scaling_per_rank']['value'])
# D3's last band runs to GR150; ours stops at the cap tunable (75 since the designer's card q-1006-01, diablocraft-e4zf)
assert int(bands[-1][2]) >= int(tunable('greater_rift_max_level'))
assert [(float(b), int(lo), min(int(hi), int(tunable('greater_rift_max_level')))) for b, lo, hi in bands] == [
    (tunable('gr_damage_per_level_low'), 1, int(tunable('gr_damage_low_last_level'))),
    (tunable('gr_damage_per_level_mid'), int(tunable('gr_damage_low_last_level')) + 1, int(tunable('gr_damage_mid_last_level'))),
    (tunable('gr_damage_per_level_high'), int(tunable('gr_damage_mid_last_level')) + 1, int(tunable('greater_rift_max_level'))),
], bands
assert re.match(r'\+100% monster Life per player beyond the first', gr['multiplayer_life_scaling']['value'])
assert tunable('gr_party_life_pct_per_extra_member') == 100
# party_scaling.csv's greater_rift rows, relative to the solo row, are the same +100% per member.
party = {int(r['players']): pct(r['monster_life_multiplier']) for r in rows('party_scaling.csv') if r['context'] == 'greater_rift'}
assert sorted(party) == [1, 2, 3, 4], party
assert all(party[n] / party[1] == 1 + tunable('gr_party_life_pct_per_extra_member') / 100 * (n - 1) for n in party), party
assert all(pct(r['monster_damage_multiplier']) == 1 for r in rows('party_scaling.csv') if r['context'] == 'greater_rift')

# --- cross-source 2: gr_level_one_tier is the tier greater_rifts.csv names for GR 1 -----------------
phase = dict((int(i), name) for i, _, name in re.findall(
    r"\((\d+),(\d+),'([^']+)'\)", (MODULE / 'data/sql/db-world/updates/difficulty_0001_tier_phase.sql').read_text(encoding='utf-8')))
assert phase[int(tunable('gr_level_one_tier'))] == gr['equivalent_tier_gr1']['value'] == 'Hard', phase
tier_rows = {r['tier']: r for r in rows('difficulty_tiers.csv')}
TIERS = {i: (pct(tier_rows[n]['monster_health_multiplier']), pct(tier_rows[n]['monster_damage_multiplier'])) for i, n in phase.items()}

# --- cross-source 3: every tunable the C++ reads exists, and nothing else is read ----------------------
read = set(re.findall(r'Tunables::Get\("rifts", "(gr_\w+)"\)', block(DIFF_SRC, 'bool GreaterNumbers(')))
assert read == {'gr_life_per_level', 'gr_damage_per_level_low', 'gr_damage_per_level_mid', 'gr_damage_per_level_high',
                'gr_damage_low_last_level', 'gr_damage_mid_last_level', 'gr_party_life_pct_per_extra_member',
                'gr_level_one_tier'}, read
generated = (MODULE / 'data/generated/tunables_0008.sql').read_text(encoding='utf-8')
for name in read:
    assert re.search(r"\('rifts', '%s'," % name, generated), name

# --- source scans: what a double cannot reach ---------------------------------------------------------
balance = block(DIFF_SRC, 'bool OnModuleCreatureScaling(')
assert 'Rifts::GreaterRiftLevel(creature->FindMap())' in balance
assert 'GreaterScaling(level, count, tierHealth, partyHealth, tierDamage, partyDamage, error)' in balance
# 64-bit Life (diablocraft-12in, native since diablocraft-88i0): the Life cap and the 32-bit ceiling are gone, every Life goes
# through ScaleCreatureLife and is handed to AutoBalance as the real Life (no pool, no scaled copy), and a Guardian takes the
# one Guardian Life from the tunable
assert 'GrLifeCap' not in DIFF_SRC and 'CREATURE_LIFE_CEILING' not in DIFF_SRC and 'GrLifeCap' not in HEADER.read_text(encoding='utf-8')
assert 'ScaleCreatureLife(info->moduleBaseHealth, base, tierHealth, partyHealth, health)' in balance
assert 'health = scaling.health;' in balance
assert 'BigLife' not in DIFF_SRC and 'BigLife' not in (MODULE / 'src/common/dc_tiers.h').read_text(encoding='utf-8')   # the core holds the Life
assert re.search(r'Rifts::IsGuardianEntry\(creature->GetEntry\(\)\)\s*\?\s*Tunables::Get\("rifts", "guardian_base_life"\)\s*:\s*info->moduleBaseHealth', balance)
assert 'damage *= tierDamage * partyDamage;' in balance
assert tunable('guardian_base_life') > 0
assert re.search(r"\('rifts', 'guardian_base_life',", (MODULE / 'data/generated/tunables_0012.sql').read_text(encoding='utf-8'))
# an unusable table refuses the way the tier path does, not by scaling by zero
assert re.search(r'if \(!GreaterScaling\(.*?\)\)\s*\{.*?quiet_NaN.*?return true;', balance, re.S)
level_fn = block(RIFTS_SRC, 'unsigned GreaterRiftLevel(')
assert 'run->mode != "gr"' in level_fn and 'return run->grRank;' in level_fn
# every elite affix damage call names the level; only the two definitions and the forward do not
calls = [m for m in re.findall(r'AffixDamage\([^;]*', ELITE_SRC) if not m.startswith('AffixDamage(AffixNumbers const&')]
assert len(calls) >= 19, len(calls)
assert all('grLevel' in c for c in calls if not c.startswith('AffixDamage(n, tier, name, parameter)')), [c for c in calls if 'grLevel' not in c]
# the level reaches the elite, its members, its bursts and its hazards
assert 'state->grLevel = DC::Rifts::GreaterRiftLevel(map);' in ELITE_SRC
assert 'mine->grLevel = state->grLevel;' in ELITE_SRC and 'burst.grLevel = state->grLevel;' in ELITE_SRC
assert 'h.grLevel = rift.mode == "gr" ? rift.grRank : 0;' in ELITE_SRC

HARNESS = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include "dc_tiers.h"
#include "dc_gr_scaling.h"

namespace DC::Tunables {
    std::unordered_map<std::string, double> table;
    double Get(std::string const& category, std::string const& name) {
        assert(category == "rifts");
        auto found = table.find(name);
        return found == table.end() ? 0.0 : found->second;
    }
}
struct AffixNumbers {
    std::unordered_map<std::string, double> value;
    std::unordered_map<unsigned, double> tierDamage;
};
namespace DC::Difficulty {
    std::vector<DC::Tier> tiers;
    bool ready = true;
%(greater_numbers)s
%(greater_scaling)s
%(greater_damage)s
}
%(affix_tier)s
%(affix_gr)s

using namespace DC::Difficulty;
static bool near(double a, double b, double rel) { return std::fabs(a - b) <= rel * std::fabs(b); }
// What mod-autobalance does with the handed multiplier (patch 0003): long double product, floored, as the creature's max Life.
// Exact for any Life under 2^52; above it the double multiplier is the limit, so the error is at most life / 2^52 + 1.
static bool handsOver(std::uint64_t moduleBase, DC::CreatureScaling const& s) {
    std::uint64_t core = static_cast<std::uint64_t>(std::floor(static_cast<long double>(moduleBase) * s.health));
    if (s.life < (1ull << 52)) return core == s.life;
    std::uint64_t diff = core > s.life ? core - s.life : s.life - core;
    return diff <= (s.life >> 52) + 1;
}
static double scaled(unsigned level, unsigned players, double& partyLife, double& partyDamage, double& damage) {
    double life = 0; std::string error;
    assert(GreaterScaling(level, players, life, partyLife, damage, partyDamage, error));
    return life;
}
int main() {
%(setup)s
    double pl = 0, pd = 0, dmg = 0;

    // 1. Level 1 is the base tier's, exactly: Life and damage of Hard.
    double life1 = scaled(1, 1, pl, pd, dmg), dmg1 = dmg;
    assert(life1 == tiers[BASE].health && dmg1 == tiers[BASE].damage && pl == 1.0 && pd == 1.0);

    // 2. The anchors, within the stated margin: GR 10 ~ Torment I, GR 25 ~ Torment VI, Life and damage.
    for (auto const& a : ANCHORS) {
        double life = scaled(a[0], 1, pl, pd, dmg);
        assert(near(life, tiers[a[1]].health, MARGIN));
        assert(near(dmg, tiers[a[1]].damage, MARGIN));
    }

    // 3. Life x1.17 per level, damage x the number of the band each level falls in (python parsed the bands
    //    out of greater_rifts.csv); every step from 1 to the cap.
    double previousLife = life1, previousDamage = dmg1;
    for (unsigned level = 2; level <= CAP; ++level) {
        double life = scaled(level, 1, pl, pd, dmg);
        assert(near(life / previousLife, LIFE_STEP, 1e-9));
        assert(near(dmg / previousDamage, DAMAGE_STEP[level], 1e-9));
        previousLife = life; previousDamage = dmg;
    }

    // 4. Party: each member beyond the first adds the share, counted from the headcount at the open; damage unchanged.
    for (unsigned players = 1; players <= 4; ++players) {
        scaled(30, players, pl, pd, dmg);
        assert(near(pl, PARTY[players], 1e-12) && pd == 1.0);
    }
    double soloLife = scaled(60, 1, pl, pd, dmg), soloDamage = dmg;
    double fullLife = scaled(60, 4, pl, pd, dmg);
    assert(fullLife == soloLife && dmg == soloDamage);   // the party sits in its own slot: level terms unchanged

    // 5. GreaterRiftDamage (what elite affix damage multiplies by) is the same damage the monsters get.
    for (unsigned level : {1u, 10u, 25u, 26u, 70u, 71u, 150u}) {
        scaled(level, 1, pl, pd, dmg);
        assert(GreaterRiftDamage(level) == dmg);
    }

    // 6. Unusable numbers are refused, not scaled by: bands out of order, a factor below 1, a base tier that
    //    is not loaded; GreaterRiftDamage answers 0 for them and before the tiers are ready.
    {
        auto saved = DC::Tunables::table;
        std::string error;
        double a, b, c, d;
        DC::Tunables::table["gr_damage_low_last_level"] = DC::Tunables::table["gr_damage_mid_last_level"] + 1;
        assert(!GreaterScaling(10, 1, a, b, c, d, error) && !error.empty() && GreaterRiftDamage(10) == 0.0);
        DC::Tunables::table = saved; error.clear();
        DC::Tunables::table["gr_life_per_level"] = 0.5;
        assert(!GreaterScaling(10, 1, a, b, c, d, error) && !error.empty());
        DC::Tunables::table = saved; error.clear();
        for (double bad : {0.0, double(tiers.size())}) {
            DC::Tunables::table["gr_level_one_tier"] = bad;
            assert(!GreaterScaling(10, 1, a, b, c, d, error) && !error.empty());
            error.clear();
        }
        DC::Tunables::table = saved;
        ready = false; assert(GreaterRiftDamage(10) == 0.0); ready = true;
        assert(GreaterRiftDamage(10) > 0.0);
    }

    // 7. No Life cap (diablocraft-12in): every level to 150 and party size is accepted for the stock templates up to the
    //    worst case (139,450,000), the true Life is exactly base x tier x party and never falls as the level rises, and
    //    what the AutoBalance patch gets is the multiplier that makes it floor(moduleBase x health) = the real Life, exactly
    //    below 2^52 and within one part in 2^52 above (a double multiplier cannot name every whole number past that).
    for (double base : {20000.0, 5000000.0, 14154175.0, 139450000.0}) {
        std::uint32_t const moduleBase = static_cast<std::uint32_t>(base);
        std::uint64_t previous = 0;
        for (unsigned level = 1; level <= 150; ++level) {
            for (unsigned players = 1; players <= 4; ++players) {
                double life = scaled(level, players, pl, pd, dmg);
                DC::CreatureScaling s = DC::ScaleCreatureLife(moduleBase, base, life, pl, 1.0);   // must not throw
                assert(s.life == static_cast<std::uint64_t>(std::floor(base * life * pl * 1.0)));
                assert(handsOver(moduleBase, s));
                if (players == 1) { assert(s.life >= previous); previous = s.life; }
            }
        }
    }
    {   // the worst case at GR 150 in a party of 4 is under 2^64 (the report's 1.6e19); past 2^64 is refused
        double life = scaled(150, 4, pl, pd, dmg);
        assert(DC::ScaleCreatureLife(139450000, 139450000.0, life, pl, 1.0).life > 9223372036854775808ull);
        bool refused = false;
        try { DC::ScaleCreatureLife(139450000, 139450000.0, life * 1000, pl, 1.0); } catch (std::out_of_range const&) { refused = true; }
        assert(refused);
    }
    for (unsigned level : {5u, 40u}) {   // the Guardian: one base for all, whatever its template, so the 27 differ by nothing but the multipliers
        double life = scaled(level, 1, pl, pd, dmg);   // 5 stays under the core's 1e9, 40 passes it
        std::uint64_t first = 0;
        for (std::uint32_t templateLife : {8300u, 2390220u, 14154175u}) {
            DC::CreatureScaling s = DC::ScaleCreatureLife(templateLife, GUARDIAN_BASE, life, pl, 1.0);
            assert(s.life == static_cast<std::uint64_t>(std::floor(GUARDIAN_BASE * life * pl)));
            if (!first) first = s.life;
            assert(s.life == first);
            // a small template still reaches the Guardian's Life through the multiplier
            assert(handsOver(templateLife, s));
        }
    }

    // 8. Elite affix damage: outside a Greater Rift the tier's factor, inside it the level's.
    {
        AffixNumbers n;
        n.value["Mortar|base_damage"] = 10; n.value["Mortar|base_explosion_damage"] = 7;
        n.tierDamage[5] = 3;
        unsigned const outside = 0, tier = 5;   // a literal 0 would also fit the std::string parameter
        assert(AffixDamage(n, tier, outside, "Mortar") == 30);
        assert(AffixDamage(n, tier, 30u, "Mortar") == 10 * GreaterRiftDamage(30));
        assert(AffixDamage(n, tier, 30u, "Mortar", "base_explosion_damage") == 7 * GreaterRiftDamage(30));
        assert(AffixDamage(n, tier, 150u, "Mortar") > AffixDamage(n, tier, 30u, "Mortar"));
        assert(AffixDamage(n, tier, 30u, "Nothing") == 0 && AffixDamage(n, tier, outside, "Nothing") == 0);
        ready = false; assert(AffixDamage(n, tier, 30u, "Mortar") == 0); ready = true;   // no table, no damage
    }
}
'''


def fmt(value):
    return repr(float(value))


# Parse the damage band of every level out of greater_rifts.csv's own text (not the tunables).
step = {}
for factor, lo, hi in bands:
    for level in range(int(lo), min(int(hi), int(tunable('greater_rift_max_level'))) + 1):
        if level > 1:
            step[level] = float(factor)
CAP = int(tunable('greater_rift_max_level'))
assert sorted(step) == list(range(2, CAP + 1))
life_step = float(re.search(r'x([\d.]+) per rank GR1-150', gr['monster_health_scaling_bands']['value']).group(1))
tier_id = {name: i for i, name in phase.items()}
anchors = [(int(re.match(r'equivalent_tier_gr(\d+)', k).group(1)), tier_id[v['value']])
           for k, v in gr.items() if re.match(r'equivalent_tier_gr(10|25)$', k)]
assert sorted(anchors) == [(10, tier_id['Torment I']), (25, tier_id['Torment VI'])], anchors

diff_cut = {
    'greater_numbers': block(DIFF_SRC, 'bool GreaterNumbers('),
    'greater_scaling': block(DIFF_SRC, 'bool GreaterScaling('),
    'greater_damage': block(DIFF_SRC, 'double GreaterRiftDamage('),
}
setup = ['    using DC::Tunables::table;']
for name in sorted(read):
    setup.append('    table["%s"] = %s;' % (name, fmt(tunable(name))))
setup.append('    tiers.resize(%d);' % (max(TIERS) + 1))
for i, (health, damage) in TIERS.items():
    setup.append('    tiers[%d].health = %s; tiers[%d].damage = %s;' % (i, fmt(health), i, fmt(damage)))
setup += [
    '    const unsigned BASE = %d, CAP = %d;' % (int(tunable('gr_level_one_tier')), CAP),
    '    const double GUARDIAN_BASE = %s;' % fmt(tunable('guardian_base_life')),
    '    const double MARGIN = %s, LIFE_STEP = %s;' % (fmt(ANCHOR_MARGIN), fmt(life_step)),
    '    const unsigned ANCHORS[][2] = {%s};' % ', '.join('{%d, %d}' % a for a in anchors),
    '    double DAMAGE_STEP[%d] = {0, 0, %s};' % (CAP + 1, ', '.join(fmt(step[l]) for l in range(2, CAP + 1))),
    '    double PARTY[5] = {0, %s};' % ', '.join(fmt(party[n] / party[1]) for n in range(1, 5)),
]
code = HARNESS % {
    **diff_cut,
    'affix_tier': '\n'.join(re.findall(r'double AffixDamage\([^;{]*\);', ELITE_SRC)) + '\n' + block(ELITE_SRC, 'double AffixDamage(AffixNumbers const& n, unsigned tier, std::string const& name,'),
    'affix_gr': block(ELITE_SRC, 'double AffixDamage(AffixNumbers const& n, unsigned tier, unsigned grLevel,'),
    'setup': '\n'.join(setup),
}
# the cut definitions need their return types and signatures back (block() starts at the marker)
cmake = shutil.which('cmake')
if not cmake:
    raise SystemExit('cmake is not on PATH; this harness compiles a small C++ program')
with tempfile.TemporaryDirectory(prefix='dc-gr-scaling-') as directory:
    folder = Path(directory)
    shutil.copy(HEADER, folder / 'dc_gr_scaling.h')
    (folder / 'test.cpp').write_text(code, encoding='utf-8')
    (folder / 'CMakeLists.txt').write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject(gr_scaling LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 20)\n'
        'add_executable(gr_scaling test.cpp)\n'
        'target_include_directories(gr_scaling PRIVATE ' + str(folder) + ' ' + str(MODULE / 'src/common') + ')\n'
        'target_compile_options(gr_scaling PRIVATE -UNDEBUG)\n', encoding='utf-8')
    env = dict(os.environ)
    subprocess.run([cmake, '-S', directory, '-B', str(folder / 'build')], env=env, check=True, capture_output=True)
    subprocess.run([cmake, '--build', str(folder / 'build')], env=env, check=True)
    harness_env.run([str(folder / 'build' / 'gr_scaling')], env=env, check=True)
print('PASS: Greater Rift scaling: Life x1.17 and the three damage bands per level, party Life, anchors within %d%%, '
      'no Life cap to 150 and the shared Guardian Life, elite affix damage, tunables = greater_rifts.csv / party_scaling.csv.' % round(ANCHOR_MARGIN * 100))
