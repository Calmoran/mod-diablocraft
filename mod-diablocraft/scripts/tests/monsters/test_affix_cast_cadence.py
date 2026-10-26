"""The elite affix cast cadence leaves the cooldown of an affix without a tick action alone (diablocraft-a1krm).

Knockback, Electrified and the Illusionist have no tick action: they fire from a landed hit or a struck hit and keep their
own cooldown in EliteState::nextCastFor[<behaviour>]. The tick loop used to call AffixTick::Due for them as well, and Due
re-arms that very slot to the cast interval whenever it has run out, so the real cooldown ran up to the cast interval longer
than the tuned one (Electrified: 0.1 s tuned, 6 s real).

The production tick dispatch is run: AffixTick::Due, the TICK_AFFIXES table and the affix loop of OnUnitUpdate are cut out of
dc_affix_unit_script.cpp and compiled against stubs of the core types, fed the cooldowns and cast intervals read from
elite_affix_parameters.csv and the behaviour names from generate_rift_affixes.py. The three affixes' own cooldown checks are
restated in the harness (each is a few lines inside a function that needs the core), and the source check below pins that the
files still arm the slot the harness assumes. Not covered: the real hit and struck callbacks, which need the worldserver
(docs/test-diablocraft-a1krm.md has the dev steps).

DC_AFFIX_CAST_CADENCE_SRC points the read at a copy of mod-diablocraft/src (mutation runs)."""
import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / 'mod-diablocraft'
sys.path.insert(0, str(MODULE / 'scripts'))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_rift_affixes as affixes  # noqa: E402

SRC = Path(os.environ.get('DC_AFFIX_CAST_CADENCE_SRC', MODULE / 'src'))
UNIT = (SRC / 'monsters/affixes/dc_affix_unit_script.cpp').read_text(encoding='utf-8')

params = {}
with (MODULE / 'data/tunables/elite_affix_parameters.csv').open(encoding='utf-8', newline='') as stream:
    for row in csv.DictReader(stream):
        if row['tuned_value'] or row['d3_value']:                  # a blank row is a placeholder
            params[(row['affix_name'], row['parameter'])] = float(row['tuned_value'] or row['d3_value'])
GLOBAL_CAST = params[('_global', 'cast_interval')]

# (affix, the parameter its own cooldown reads, the slot it arms, the source that does it)
OWN_COOLDOWN = (
    ('Knockback', 'cooldown', 'monsters/affixes/dc_affix_knockback.cpp',
     ('now < pack->nextCastFor["knockback"]', 'pack->nextCastFor["knockback"] =\n        now + Ms(n.Parameter("Knockback|cooldown"))')),
    ('Electrified', 'internal_cooldown', 'monsters/affixes/dc_affix_electrified.cpp',
     ('std::uint32_t& next = state->nextCastFor["reflect"];\n    if (now >= next)',
      'next = now + std::max<std::uint32_t>(1,\n            Ms(n.Parameter("Electrified|internal_cooldown")))')),
    ('Illusionist', 'cooldown', 'monsters/affixes/dc_affix_illusionist.cpp',
     ('std::uint32_t& next = state->nextCastFor["illusionist"];\n        if (now >= next)',
      'next = now + std::max<std::uint32_t>(1,\n                Ms(n.Parameter("Illusionist|cooldown")))')),
)
SLOT = {'Knockback': 'knockback', 'Electrified': 'reflect', 'Illusionist': 'illusionist'}
for name, parameter, source, shapes in OWN_COOLDOWN:
    assert affixes.IMPLEMENTED[name] == SLOT[name], name              # the slot the harness arms is the affix's behaviour
    text = (SRC / source).read_text(encoding='utf-8')
    for shape in shapes:
        assert text.count(shape) == 1, (name, shape)
    assert params[(name, parameter)] > 0, name

# --- the production pieces, cut out of the unit script ------------------------------------------------------------------
due = UNIT[UNIT.index('bool AffixTick::Due(Affix const& affix) const'):]
due = due[:due.index('\n}\n') + 3]
struct = UNIT[UNIT.index('struct TickAffix'):]
table_end = struct.index('};\n', struct.index('constexpr TickAffix TICK_AFFIXES[]')) + 3
table = struct[:table_end]
loop_start = UNIT.index('for (Affix const& affix : state->affixes)', UNIT.index('void OnUnitUpdate('))
loop = UNIT[loop_start:UNIT.index('\n    }\n\n    void OnDamage(Unit* attacker', loop_start)].rstrip()   # up to OnUnitUpdate's own brace
assert loop.endswith('}') and 'tick.Due(affix)' in loop and 'entry->tick(tick, affix)' in loop

tick_names = sorted(set(name for name in (word.strip(' ,}') for word in table.replace('{', ' ').replace('}', ' ').split())
                        if name.endswith('Tick') and name[0].isupper()))
assert len(tick_names) == 16, tick_names

harness = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <iterator>
#include <string>
#include <unordered_map>
#include <vector>

namespace DC::Rifts
{
struct Affix { std::string name, behaviour; };
struct EliteState { std::unordered_map<std::string, std::uint32_t> nextCastFor; std::vector<Affix> affixes; };
struct AffixNumbers
{
    std::unordered_map<std::string, double> value;
    std::uint32_t castMs = @GLOBAL_MS@;
    bool Enabled(std::string const&) const { return true; }
    double Get(std::string const& key, double fallback) const { auto f = value.find(key); return f == value.end() ? fallback : f->second; }
};
std::uint32_t Ms(double seconds) { return static_cast<std::uint32_t>(seconds * 1000.0 + 0.5); }

struct AffixTick
{
    EliteState* state; AffixNumbers const& n; std::uint32_t now;
    bool Due(Affix const& affix) const;
};
static std::unordered_map<std::string, std::vector<std::uint32_t>> ticks;    // tick action name -> when it ran
constexpr std::uint32_t UPDATE_MS = 470;                    // the update tick, not a divisor of any cooldown here
@TICK_STUBS@

@DUE@

@TABLE@

// One elite carrying one affix, updated every UPDATE_MS; `event` is the hit or struck callback, tried every eventStep ms.
struct Run { std::vector<std::uint32_t> fired, ticked; };
template <typename Event>
static Run fight(AffixNumbers const& n, Affix affix, std::uint32_t lengthMs, Event event, std::uint32_t eventStep = 10)
{
    EliteState elite; elite.affixes.push_back(affix);
    EliteState* state = &elite;
    Run run;
    for (std::uint32_t now = 1000; now < 1000 + lengthMs; now += 10)
    {
        if (!((now - 1000) % UPDATE_MS))
        {
            // the update tick comes round before the hit that is waiting on the same millisecond
            AffixTick const tick{state, n, now};
@LOOP@
        }
        if (!((now - 1000) % eventStep) && event(elite, now))
            run.fired.push_back(now);
    }
    return run;
}
}

using namespace DC::Rifts;
int main()
{
    AffixNumbers n;
@VALUES@
    unsigned bad = 0;
@CASES@
    // An affix that does have a tick action still runs it on its cast cadence; an own-clock one on every update.
    {
        ticks.clear();
        fight(n, Affix{"Arcane Enchanted", "beam"}, 120000, [](EliteState&, std::uint32_t) { return false; });
        auto const& at = ticks["ArcaneEnchantedTick"];
        std::uint32_t shortest = ~0u, longest = 0;
        for (size_t i = 1; i < at.size(); ++i) { shortest = std::min(shortest, at[i] - at[i - 1]); longest = std::max(longest, at[i] - at[i - 1]); }
        std::printf("beam: cast interval @BEAM_MS@ ms, ran %zu times, gaps %u..%u ms\n", at.size(), shortest, longest);
        if (at.size() < 2 || shortest < @BEAM_MS@ || longest >= @BEAM_MS@ + UPDATE_MS) ++bad;
        ticks.clear();
        fight(n, Affix{"Molten", "trail"}, 120000, [](EliteState&, std::uint32_t) { return false; });
        std::printf("trail: ran %zu times in 120000 ms of %u ms updates\n", ticks["MoltenTick"].size(), UPDATE_MS);
        if (ticks["MoltenTick"].size() != (120000 + UPDATE_MS - 1) / UPDATE_MS) ++bad;
    }
    return bad ? 1 : 0;
}
'''

tick_stubs = '\n'.join(f'static void {name}(AffixTick const& t, Affix const&) {{ ticks["{name}"].push_back(t.now); }}' for name in tick_names)
values = '\n'.join(f'    n.value["{a}|{p}"] = {v!r};' for (a, p), v in params.items() if a in SLOT or p == 'cast_interval' and a != '_global')
cases = []
for name, parameter, source, shapes in OWN_COOLDOWN:
    slot, cooldown = SLOT[name], params[(name, parameter)]
    cast = params.get((name, 'cast_interval'), GLOBAL_CAST)
    cases.append(f'''    for (std::uint32_t step : {{10u, 70u, 130u}})
    {{
        ticks.clear();
        std::uint32_t const cooldown = Ms({cooldown!r});
        // the affix's own cooldown, as its file writes it: refuse inside the window, arm now + cooldown when it fires
        Run run = fight(n, Affix{{"{name}", "{slot}"}}, 120000, [&](EliteState& s, std::uint32_t now) {{
            std::uint32_t& next = s.nextCastFor["{slot}"];
            if (now < next) return false;
            next = now + cooldown;
            return true;
        }}, step);
        std::uint32_t longest = 0;
        for (size_t i = 1; i < run.fired.size(); ++i) longest = std::max(longest, run.fired[i] - run.fired[i - 1]);
        // the event is tried every `step` ms, so the real interval may exceed the cooldown by at most that much
        std::printf("{name}: tuned %u ms, cast interval {cast!r} s, tried every %u ms, longest real interval %u ms over %zu fires\\n", cooldown, step, longest, run.fired.size());
        if (run.fired.size() < 2 || longest > cooldown + step) ++bad;
        if (!ticks.empty()) ++bad;                            // and it has no tick action to run
    }}''')
cases = '\n'.join(cases)
beam_ms = int(params[('Arcane Enchanted', 'cast_interval')] * 1000)

code = (harness.replace('@GLOBAL_MS@', str(int(GLOBAL_CAST * 1000))).replace('@TICK_STUBS@', tick_stubs)
        .replace('@DUE@', due).replace('@TABLE@', table).replace('@LOOP@', loop).replace('@VALUES@', values)
        .replace('@CASES@', cases).replace('@BEAM_MS@', str(beam_ms)))
scratch = ROOT / 'azerothcore-wotlk/build/_agent-scratch'
with tempfile.TemporaryDirectory(prefix='affix-cast-cadence-', dir=scratch) as folder:
    cpp, exe = Path(folder) / 'cadence.cpp', Path(folder) / 'cadence'
    cpp.write_text(code, encoding='utf-8')
    subprocess.run(['c++', '-std=c++17', '-O0', '-UNDEBUG', '-Wall', '-Werror', '-Wno-unused-function', str(cpp), '-o', str(exe)], check=True)
    done = harness_env.run([str(exe)], capture_output=True, text=True)
    print(done.stdout, end='')
    assert done.returncode == 0, done.stdout + done.stderr
print('ok')
