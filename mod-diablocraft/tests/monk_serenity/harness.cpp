// diablocraft-umi1o (Monk 2.3.17): the real dc_monk_serenity.h. Every number comes from argv (the tunables sheet's and
// monk_skill_values.csv's, read by test_monk_serenity.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_serenity.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Serenity;

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

int main(int argc, char** argv)
{
    // argv: base seconds, Ascension seconds, pulse seconds, heal min, heal max
    if (argc < 6)
        return 2;
    double const base = std::atof(argv[1]), ascension = std::atof(argv[2]), interval = std::atof(argv[3]),
                 healMin = std::atof(argv[4]), healMax = std::atof(argv[5]);

    // Unwelcome Disturbance: "every second" is 0.99 s, so a 3 second shield pulses 3 times, a 4 second one 4 times.
    expect(Pulses(base, interval) == 3, "3 seconds, 3 pulses", Pulses(base, interval), 3);
    expect(Pulses(ascension, interval) == 4, "4 seconds, 4 pulses", Pulses(ascension, interval), 4);
    expect(Pulses(0.98, interval) == 0, "a shield shorter than the interval pulses never");
    expect(Pulses(0, interval) == 0 && Pulses(base, 0) == 0, "an open input gives no pulse");
    expect(Pulses(0.6, 0.2) == 3, "three intervals exactly are three pulses (0.6 / 0.2 is 2.9999999999999996)", Pulses(0.6, 0.2), 3);

    // Peaceful Repose: the range is the sheet's, any share lands inside it.
    expect(HealRoll(healMin, healMax, 0) == healMin, "the lowest roll is the minimum", HealRoll(healMin, healMax, 0),
           healMin);
    expect(HealRoll(healMin, healMax, 1) == healMax, "the highest roll is the maximum", HealRoll(healMin, healMax, 1),
           healMax);
    expect(std::fabs(HealRoll(healMin, healMax, 0.5) - (healMin + healMax) / 2) < 1e-6, "the middle is the middle");
    expect(HealRoll(healMin, healMax, 3) == healMax && HealRoll(healMin, healMax, -3) == healMin,
           "a share outside 0 to 1 is clamped");
    expect(HealRoll(100, 50, 1) == 100, "a maximum under the minimum never heals less than the minimum");

    // The cooldown starts after the shield: pushed back by the shield's whole time.
    expect(CooldownDelayMs(base) == 3000 && CooldownDelayMs(ascension) == 4000, "the cooldown waits for the shield",
           CooldownDelayMs(base), 3000);
    expect(CooldownDelayMs(-1) == 0, "no negative delay");
    expect(CooldownDelayMs(0.0004) == 0 && CooldownDelayMs(0.0006) == 1, "rounded to the millisecond");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
