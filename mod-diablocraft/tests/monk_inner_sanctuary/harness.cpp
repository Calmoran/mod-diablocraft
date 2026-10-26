// diablocraft-yyglx (Monk 2.3.18): the real dc_monk_inner_sanctuary.h. Every number comes from argv (monk_skill_values.csv's,
// skill_targeting.csv's and the tunables sheet's, read by test_monk_inner_sanctuary.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_inner_sanctuary.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Sanctuary;

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
    return std::fabs(a - b) < 1e-6;
}

int main(int argc, char** argv)
{
    if (argc != 9)
    {
        std::printf("usage: reduction absorb heal share duration sanctified tick radius\n");
        return 2;
    }
    double const reduction = std::atof(argv[1]), absorb = std::atof(argv[2]), heal = std::atof(argv[3]),
                 share = std::atof(argv[4]), duration = std::atof(argv[5]), sanctified = std::atof(argv[6]),
                 tick = std::atof(argv[7]), radius = std::atof(argv[8]);

    // The cut: 55% less, one cut however many circles.
    expect(near(TakenFactor(reduction), 1 - reduction / 100), "the circle's cut", TakenFactor(reduction), 1 - reduction / 100);
    expect(near(1000 * TakenFactor(reduction), 450), "a 1000 hit takes 450", 1000 * TakenFactor(reduction), 450);
    expect(TakenFactor(150) == 0 && TakenFactor(-10) == 1, "the factor stays in 0..1");

    // The circle: in at the edge, out past it, out on another map or instance, out once it has run out.
    Zone zone;
    zone.map = 1;
    zone.instance = 7;
    zone.x = 100;
    zone.y = 200;
    zone.radius = radius;
    zone.until = 6000;
    expect(Covers(zone, 1, 7, 100, 200, 0), "the centre is in");
    expect(Covers(zone, 1, 7, 100 + radius, 200, 0), "the edge is in");
    expect(!Covers(zone, 1, 7, 100 + radius + 0.01, 200, 0), "past the edge is out");
    expect(Covers(zone, 1, 7, 100 + radius * 0.7, 200 + radius * 0.7, 0), "a diagonal inside is in");
    expect(!Covers(zone, 1, 7, 100 + radius * 0.8, 200 + radius * 0.8, 0), "a diagonal past the edge is out");
    expect(!Covers(zone, 2, 7, 100, 200, 0), "another map is out");
    expect(!Covers(zone, 1, 8, 100, 200, 0), "another instance is out");
    expect(Covers(zone, 1, 7, 100, 200, 5999), "the last ms is in");
    expect(!Covers(zone, 1, 7, 100, 200, 6000), "the end is out");

    // Intervene's shield: takes what it can, lets the rest through.
    double left = absorb;
    expect(near(Absorb(absorb / 2, left), 0) && near(left, absorb / 2), "half the shield absorbs a half hit", left, absorb / 2);
    expect(near(Absorb(absorb, left), absorb / 2) && near(left, 0), "the rest goes through once it is spent", left, 0);
    expect(near(Absorb(500, left), 500), "a spent shield takes nothing");
    double whole = absorb;
    expect(near(Absorb(-5, whole), -5) && near(whole, absorb), "no damage, nothing taken");

    // The ticks: 6 s at 0.3 s is 20, Sanctified Ground's 8 s is 26 (a part tick does not count); a blank tick is none.
    expect(Ticks(duration, tick) == unsigned(std::floor(duration / tick + 1e-9)), "the circle's ticks", Ticks(duration, tick),
           std::floor(duration / tick + 1e-9));
    expect(Ticks(6, 0.3) == 20, "6 s at 0.3 s is 20", Ticks(6, 0.3), 20);
    expect(Ticks(sanctified, tick) == 26, "Sanctified Ground's ticks", Ticks(sanctified, tick), 26);
    expect(Ticks(duration, 0) == 0, "a blank tick is none");

    // Safe Haven: the per-second heal plus the share of Life per Second, paid per tick; a whole second's ticks pay it.
    double const lps = 10000;
    expect(near(HealPerTick(heal, 0, share, tick), heal * tick), "a tick pays its share of a second", HealPerTick(heal, 0, share, tick), heal * tick);
    expect(near(HealPerTick(heal, lps, share, 1), heal + lps * share / 100), "Life per Second adds its share",
           HealPerTick(heal, lps, share, 1), heal + lps * share / 100);
    expect(near(Ticks(duration, tick) * HealPerTick(heal, 0, share, tick), heal * duration), "the circle's life heals per second x seconds",
           Ticks(duration, tick) * HealPerTick(heal, 0, share, tick), heal * duration);
    expect(HealPerTick(heal, lps, share, 0) == 0, "no tick, no heal");

    // Sanctified Ground: an enemy inside goes to the edge; one outside stays.
    expect(near(PushYards(radius - 3, radius), 3), "3 yd inside is pushed 3", PushYards(radius - 3, radius), 3);
    expect(near(PushYards(0, radius), radius), "the centre is pushed the radius");
    expect(PushYards(radius, radius) == 0 && PushYards(radius + 4, radius) == 0, "the edge and past it stay");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
