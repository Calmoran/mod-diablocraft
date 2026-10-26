// diablocraft-fcmj0 (Monk 2.3.03): the real dc_monk_crippling_wave.h. Every number comes from argv (the sheets' and the
// tunables', read by test_monk_crippling_wave.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_crippling_wave.h"
#include "classes/monk/dc_monk_fists.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk;

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
    // argv: window frames, frames per second, base yards, Tsunami yards, cone degrees, Rising Tide Spirit, slow %,
    // attack speed %
    if (argc < 9)
        return 2;
    double const frames = std::atof(argv[1]), fps = std::atof(argv[2]), base = std::atof(argv[3]),
                 tsunami = std::atof(argv[4]), degrees = std::atof(argv[5]), tide = std::atof(argv[6]),
                 slow = std::atof(argv[7]), attacks = std::atof(argv[8]);

    // The third hit alone carries the daze, the freeze and the longer reach.
    expect(!Wave::IsThird(1) && !Wave::IsThird(2) && Wave::IsThird(3), "only stage 3 is the third hit");

    // The combo is Fists of Thunder's counter, one of this skill's own: 1 2 3 1 2 3 at a swing a second, and a pause
    // past the window starts it again.
    std::uint64_t const window = ComboWindowMs(frames, fps, 1.0);
    Combo combo;
    unsigned expected[] = {1, 2, 3, 1, 2, 3};
    bool steady = true;
    for (int i = 0; i < 6; ++i)
        steady &= combo.Advance(1000 + i * 1000, window) == expected[i];
    expect(steady, "a swing a second counts 1 2 3 1 2 3");
    Combo paused;
    paused.Advance(1000, window);
    expect(paused.Advance(1000 + window + 1, window) == 1, "a pause past the window starts again");

    // Reach: the sheet's 11 for every swing; Tsunami's 17 for the third only.
    expect(Wave::Reach(1, base, 0) == base && Wave::Reach(2, base, 0) == base && Wave::Reach(3, base, 0) == base,
           "a rune with no radius of its own keeps the base reach", Wave::Reach(3, base, 0), base);
    expect(Wave::Reach(1, base, tsunami) == base && Wave::Reach(2, base, tsunami) == base,
           "Tsunami's first two swings keep the base reach", Wave::Reach(2, base, tsunami), base);
    expect(Wave::Reach(3, base, tsunami) == tsunami, "Tsunami's third swing reaches further",
           Wave::Reach(3, base, tsunami), tsunami);
    expect(tsunami > base, "Tsunami's range is an increase", tsunami, base);
    expect(Wave::Reach(3, base, base) == base, "the base skill's own radius row is not an increase");

    // The arc: degrees to the radians the core's HasInArc takes.
    expect(std::fabs(Wave::ArcRadians(degrees) - 3.14159265358979323846 * degrees / 180.0) < 1e-9, "degrees to radians",
           Wave::ArcRadians(degrees), degrees);
    expect(std::fabs(Wave::ArcRadians(180.0) - 3.14159265358979323846) < 1e-9, "a half circle is pi");

    // Rising Tide: the extra is paid for each enemy hit.
    expect(Wave::RisingTideSpirit(tide, 0) == 0, "no enemy, no extra Spirit");
    expect(Wave::RisingTideSpirit(tide, 1) == tide, "one enemy pays once", Wave::RisingTideSpirit(tide, 1), tide);
    expect(Wave::RisingTideSpirit(tide, 4) == 4 * tide, "four enemies pay four times", Wave::RisingTideSpirit(tide, 4),
           4 * tide);
    expect(Wave::RisingTideSpirit(0, 4) == 0, "a rune that states no number pays none");

    // The slow's amounts are negative aura amounts.
    expect(Wave::SlowAmount(slow) == -int(slow), "movement slow is a negative amount", Wave::SlowAmount(slow), -slow);
    expect(Wave::SlowAmount(attacks) == -int(attacks), "attack speed slow is a negative amount",
           Wave::SlowAmount(attacks), -attacks);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
