// The real dc_necromancer_siphon_blood_math.h. The rune names and numbers come from argv (read from the sheets and
// tunables by test_necromancer_siphon_blood.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_siphon_blood_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::SiphonBlood;

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
    // argv: the seconds between strikes before attack speed, the damage, Power Shift's bonus and stacks, the Essence of
    // a strike and at full health, then the five runes A to E
    if (argc < 12)
        return 2;
    double const base = std::atof(argv[1]), damage = std::atof(argv[2]), bonus = std::atof(argv[3]),
                 gained = std::atof(argv[5]), atFull = std::atof(argv[6]);
    unsigned const maxStacks = unsigned(std::atoi(argv[4]));
    std::string const suppress = argv[7], purity = argv[8], drain = argv[9], shift = argv[10], sucker = argv[11];

    expect(RuneOf(suppress) == Rune::Suppress && RuneOf(purity) == Rune::PurityOfEssence &&
               RuneOf(drain) == Rune::DrainLife && RuneOf(shift) == Rune::PowerShift &&
               RuneOf(sucker) == Rune::BloodSucker,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {suppress, purity, drain, shift, sucker})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Siphon Blood") == Rune::None,
           "the base skill and a stranger are no rune");

    // The cadence: the base seconds shortened by the attack speed.
    expect(near(TickSeconds(base, 1.0), base), "at one attack a second the base", TickSeconds(base, 1.0), base);
    expect(near(TickSeconds(base, 2.0), base / 2), "twice as fast, half the seconds", TickSeconds(base, 2.0), base / 2);
    expect(near(TickSeconds(base, 0), 0) && near(TickSeconds(0, 1.0), 0) && near(TickSeconds(-1, 1.0), 0),
           "no speed or no base, no strikes");

    // A strike carries its share of the second.
    expect(near(TickPct(damage, 1.0), damage), "a second of channel is the damage", TickPct(damage, 1.0), damage);
    expect(near(TickPct(damage, base), damage * base), "a strike is the share of the seconds between strikes",
           TickPct(damage, base), damage * base);
    expect(near(TickPct(damage, -1.0), 0), "no negative strike");

    // Power Shift: more with each strike, up to the cap, and never less.
    expect(near(PowerShiftPct(damage, bonus, 0), damage), "the first strike is the plain damage");
    expect(near(PowerShiftPct(damage, bonus, 3), damage * (1 + 3 * bonus / 100)), "three strikes on, three bonuses",
           PowerShiftPct(damage, bonus, 3), damage * (1 + 3 * bonus / 100));
    expect(near(PowerShiftPct(damage, -20, 3), damage), "a negative bonus is none");
    unsigned stacks = 0;
    for (unsigned i = 0; i < maxStacks + 5; ++i)
        stacks = NextStacks(stacks, maxStacks);
    expect(stacks == maxStacks, "stacks stop at the cap", stacks, maxStacks);
    expect(NextStacks(0, maxStacks) == 1 && NextStacks(maxStacks - 1, maxStacks) == maxStacks, "a stack a strike");

    // Purity of Essence: more only at full health.
    expect(near(EssenceOfTick(gained, atFull, true), atFull), "full health pays the larger",
           EssenceOfTick(gained, atFull, true), atFull);
    expect(near(EssenceOfTick(gained, atFull, false), gained), "less than full pays the plain",
           EssenceOfTick(gained, atFull, false), gained);
    expect(near(EssenceOfTick(gained, 0, true), gained), "no larger number stated, the plain at full health");

    // The clock: whole intervals, the rest kept.
    double clock = 0;
    expect(Due(clock, 100, 350) == 0 && near(clock, 100), "not yet due keeps the time");
    expect(Due(clock, 260, 350) == 1 && near(clock, 10), "one due, the rest kept", clock, 10);
    clock = 0;
    expect(Due(clock, 1000, 350) == 2 && near(clock, 300), "two due in a long update", clock, 300);
    clock = 0;
    expect(Due(clock, 350, 350) == 1 && near(clock, 0), "a strike is due on the moment");
    clock = 50;
    expect(Due(clock, 100, 0) == 0 && near(clock, 0), "no interval, none due");
    clock = 0;
    expect(Due(clock, 100000, 350) == 20, "never more than the cap at once");
    expect(Due(clock, 0, 350) == 0, "nothing to add, nothing due");

    // Held: the real loop's clocks over ten seconds of server updates of 50 ms at one attack a second and at two. The channel
    // keeps striking at the cadence and heals every second for as long as it is held.
    for (double attacksPerSecond : {1.0, 2.0})
    {
        double strikeClock = 0, healClock = 0;
        unsigned strikes = 0, heals = 0;
        double const interval = TickSeconds(base, attacksPerSecond) * 1000.0;
        for (int update = 0; update < 200; ++update)
        {
            strikes += Due(strikeClock, 50, interval);
            heals += Due(healClock, 50, 1000.0);
        }
        double const expected = 10.0 / TickSeconds(base, attacksPerSecond);
        expect(std::fabs(double(strikes) - expected) <= 1.0, "ten seconds held, it strikes at the cadence", double(strikes), expected);
        expect(heals == 10, "ten seconds held, it heals every second", double(heals), 10);
    }

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
