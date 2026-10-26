// The real dc_shaman_ghost_wolf.h, no core. Every number comes from argv (test_shaman_ghost_wolf.py reads the sheet and
// combat.csv): the skill's seconds, Spirit Walk's seconds, Wind Rush's charges and recharge seconds, Spectral
// Recovery's heal percent, the trail's per-second percent, its pulse seconds and its drop seconds. Prints "cases=N
// failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_ghost_wolf.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::GhostWolf;

static int failures = 0;
static int cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    if (argc < 9)
        return 2;
    double const skill = std::atof(argv[1]), walk = std::atof(argv[2]);
    unsigned const cap = unsigned(std::atof(argv[3]));
    std::uint64_t const period = std::uint64_t(std::atof(argv[4]) * 1000.0);
    double const healPct = std::atof(argv[5]), trailPct = std::atof(argv[6]), pulse = std::atof(argv[7]),
                 drop = std::atof(argv[8]);

    // The five runes by name, and nothing else.
    expect(RuneOf("Spirit Walk") == Rune::SpiritWalk && RuneOf("Wind Rush") == Rune::WindRush &&
               RuneOf("Thunderous Paws") == Rune::ThunderousPaws &&
               RuneOf("Spectral Recovery") == Rune::SpectralRecovery && RuneOf("Blazing Spirit") == Rune::BlazingSpirit,
           "each rune by its name");
    expect(RuneOf("") == Rune::None && RuneOf("Chain Frost") == Rune::None, "the skill and a stranger are no rune");

    // The form lasts the skill's seconds; only Spirit Walk lasts its own, however long another rune's own
    // `duration_seconds` is.
    expect(walk > skill, "Spirit Walk lasts longer than the plain form", walk, skill);
    expect(FormSeconds(Rune::None, skill, 99) == skill, "the plain form lasts the skill's seconds",
           FormSeconds(Rune::None, skill, 99), skill);
    expect(FormSeconds(Rune::SpiritWalk, skill, walk) == walk, "Spirit Walk lasts its own",
           FormSeconds(Rune::SpiritWalk, skill, walk), walk);
    for (Rune rune : {Rune::WindRush, Rune::ThunderousPaws, Rune::SpectralRecovery, Rune::BlazingSpirit})
        expect(FormSeconds(rune, skill, 99) == skill, "no other rune changes the form's seconds",
               FormSeconds(rune, skill, 99), skill);

    // Each rune's part is its own and no other's.
    expect(StripsControl(Rune::SpiritWalk) && !StripsControl(Rune::None) && !StripsControl(Rune::WindRush) &&
               !StripsControl(Rune::ThunderousPaws) && !StripsControl(Rune::SpectralRecovery) &&
               !StripsControl(Rune::BlazingSpirit),
           "only Spirit Walk strips control");
    expect(HealsAtEnd(Rune::SpectralRecovery) && !HealsAtEnd(Rune::BlazingSpirit) && !HealsAtEnd(Rune::None),
           "only Spectral Recovery heals at the end");
    expect(ExplodesAtEnd(Rune::BlazingSpirit) && !ExplodesAtEnd(Rune::SpectralRecovery) && !ExplodesAtEnd(Rune::None),
           "only Blazing Spirit explodes at the end");
    expect(LaysTrail(Rune::ThunderousPaws) && !LaysTrail(Rune::None) && !LaysTrail(Rune::BlazingSpirit),
           "only Thunderous Paws lays a trail");

    // The trail: a patch every drop for the form's seconds; each patch pulses the per-second percent of a pulse.
    unsigned const patches = Patches(skill, drop);
    expect(patches > 0 && patches * drop <= skill + 1e-9 && (patches + 1) * drop > skill - 1e-9,
           "the trail lays a patch every drop for the form's seconds", patches, skill / drop);
    expect(Patches(0, drop) == 0 && Patches(skill, 0) == 0, "no seconds or no drop, no patch");
    expect(std::abs(PulsePct(trailPct, pulse) - trailPct * pulse) < 1e-9 && PulsePct(trailPct, 1.0) == trailPct,
           "a pulse is the per-second percent of its seconds");

    expect(std::abs(PulsePct(trailPct, 0.5) - trailPct * 0.5) < 1e-9, "and at two pulses a second each is half of it", PulsePct(trailPct, 0.5), trailPct * 0.5);

    // The heal: the percent of the maximum Life.
    expect(HealOf(1000, healPct) == 1000 * healPct / 100.0 && HealOf(0, healPct) == 0,
           "the heal is a share of the maximum Life", HealOf(1000, healPct), 1000 * healPct / 100.0);

    // Casting another skill ends the form; casting Ghost Wolf does not (it starts a new one); nothing to end, nothing
    // ends.
    expect(EndsForm(true, false) && !EndsForm(true, true) && !EndsForm(false, false) && !EndsForm(false, true),
           "another skill ends the form, Ghost Wolf does not");

    // Wind Rush: the charges the sheet states, one recharging at a time, the button held only when none is left.
    DC::Combat::ChargeStore store;
    expect(cap >= 2, "Wind Rush stores at least two charges", cap, 2);
    std::uint64_t const start = 5000;
    expect(store.Spend(start, cap, period) == 0 && store.count == cap - 1, "the first cast leaves a charge and no wait",
           store.count, cap - 1);
    for (unsigned spent = 2; spent < cap; ++spent)
        store.Spend(start, cap, period);
    std::uint64_t const wait = store.Spend(start + 1000, cap, period);
    expect(store.count == 0 && wait == period - 1000, "the last charge holds the button until the next lands",
           double(wait), double(period - 1000));
    expect(store.Refill(start + period, cap, period) == 1, "a charge lands a period after the first cast", store.count,
           1);
    expect(store.Spend(start + period, cap, period) == period && store.count == 0, "and the button holds a full period again once it is spent", double(store.next - start - period), double(period));

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
