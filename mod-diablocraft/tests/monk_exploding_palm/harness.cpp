// diablocraft-91siy (Monk 2.3.09): the real dc_monk_exploding_palm.h. The sheets' numbers come from argv (read by
// test_monk_exploding_palm.py). Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/monk/dc_monk_exploding_palm.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::ExplodingPalm;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

int main(int argc, char** argv)
{
    // argv: bleed total % (1200), palm seconds (9), burn total % (3260), burn seconds (3), burn tick seconds (0.25)
    if (argc < 6)
        return 2;
    double const bleed = std::atof(argv[1]), seconds = std::atof(argv[2]), burn = std::atof(argv[3]);
    double const burnSeconds = std::atof(argv[4]), burnTick = std::atof(argv[5]);

    // The ticks add up to the total, at any attack speed.
    for (double aps : {1.0, 1.2, 1.5, 2.0, 2.4})
    {
        unsigned const n = Ticks(seconds, aps);
        expect(n == unsigned(std::floor(seconds * aps + 1e-9)), "the ticks that fit the palm", n, seconds * aps);
        expect(near(TickPct(bleed, n) * n, bleed), "and they add up to the bleed", TickPct(bleed, n) * n, bleed);
    }
    unsigned const burnTicks = Ticks(burnSeconds, 1.0 / burnTick);
    expect(burnTicks == 12 || burnSeconds != 3 || burnTick != 0.25, "3 seconds at 0.25 s is 12 ticks", burnTicks, 12);
    expect(near(TickPct(burn, burnTicks) * burnTicks, burn), "the burn adds up", TickPct(burn, burnTicks) * burnTicks, burn);
    expect(Ticks(0, 2) == 0 && Ticks(9, 0) == 0 && Ticks(-1, 2) == 0, "no seconds or no rate, no ticks");
    expect(TickPct(100, 0) == 0, "no ticks, no share");
    expect(Ticks(2.4, 1.0) == 2, "a partial tick is not paid", Ticks(2.4, 1.0), 2);

    // The marks: live for the palm's seconds, then gone; the death takes them once.
    Marks marks;
    marks.Set(1, 100, 777, 5000);
    expect(marks.Live(1, 100, 777, 4999), "the palm is on before its end");
    expect(!marks.Live(1, 100, 777, 5000), "and gone at its end");
    expect(!marks.Live(2, 100, 777, 1000), "another Monk's palm is its own");
    expect(!marks.Live(1, 101, 777, 1000), "another enemy is unmarked");
    expect(!marks.Live(1, 100, 778, 1000), "another rune's palm does not answer for this one");
    marks.Set(1, 100, 778, 9000);
    expect(!marks.Live(1, 100, 777, 1000) && marks.Live(1, 100, 778, 1000), "a new palm replaces the old");
    marks.Set(2, 100, 777, 6000);
    marks.Set(3, 100, 777, 2000);
    marks.Set(1, 200, 777, 9000);
    auto taken = marks.Take(100, 4000);
    expect(taken.size() == 2, "the death takes every palm still on it", double(taken.size()), 2);
    bool one = false, two = false, three = false;
    for (auto const& m : taken)
    {
        one = one || (m.caster == 1 && m.spellId == 778);
        two = two || (m.caster == 2 && m.spellId == 777);
        three = three || m.caster == 3;
    }
    expect(one && two && !three, "the Monks and runes are the ones that cast, and the run-out palm is not among them");
    expect(marks.Take(100, 4000).empty(), "and takes them once");
    expect(marks.Live(1, 200, 777, 4000), "another enemy's palm stays");
    expect(marks.Take(300, 4000).empty(), "an enemy with none gives none");
    marks.Prune(10000);
    expect(marks.Size() == 0, "run-out palms are pruned", double(marks.Size()), 0);

    // The runs: a new run starts over and the old one's ticks stop.
    Runs runs;
    auto first = runs.Start(1, 100, 0);
    expect(runs.Live(1, 100, 0, first), "a run is live");
    auto second = runs.Start(1, 100, 0);
    expect(!runs.Live(1, 100, 0, first) && runs.Live(1, 100, 0, second), "a new run replaces the old");
    auto other = runs.Start(1, 100, 1);
    expect(runs.Live(1, 100, 0, second) && runs.Live(1, 100, 1, other), "the burn is its own run beside the bleed");
    runs.End(1, 100, 0, first);
    expect(runs.Live(1, 100, 0, second), "an old run cannot end the new one");
    runs.End(1, 100, 0, second);
    expect(!runs.Live(1, 100, 0, second), "a run ends");

    // Shocking Grasp: the nearest within the radius.
    expect(Nearest({400, 25, 100}, 15) == 1, "the nearest enemy is the arc's");
    expect(Nearest({400, 900}, 15) == -1, "none within the radius, no arc");
    expect(Nearest({225}, 15) == 0, "an enemy at the radius is in");
    expect(Nearest({}, 15) == -1, "no enemy, no arc");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
