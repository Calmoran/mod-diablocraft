// diablocraft-m2bk4 (Monk 2.3.05): the real dc_monk_lashing_tail_kick.h. The numbers the sheets and the power file
// state come from argv (read by test_monk_lashing_tail_kick.py); the column's width and the burn's tick are blank
// tunables, so the cases below use widths and ticks of their own to prove the geometry and the division, not a game
// value. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_lashing_tail_kick.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Kick;

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
    // argv: cone degrees, column yards, burn total %, burn seconds, slow %
    if (argc < 6)
        return 2;
    double const degrees = std::atof(argv[1]), length = std::atof(argv[2]), burn = std::atof(argv[3]),
                 seconds = std::atof(argv[4]), slow = std::atof(argv[5]);
    double const pi = 3.14159265358979323846;

    // The arc.
    expect(std::fabs(ArcRadians(degrees) - pi * degrees / 180.0) < 1e-9, "degrees to radians", ArcRadians(degrees),
           degrees);
    expect(std::fabs(ArcRadians(180.0) - pi) < 1e-9, "a half circle is pi");

    // The column: facing east (0) and facing north (pi / 2), a strip of 4 yards that runs `length` yards.
    double const width = 4;
    expect(InColumn(0, 0, 0, length, width, 10, 0), "an enemy dead ahead is in the column");
    expect(InColumn(0, 0, 0, length, width, length, 0), "the far end is in the column");
    expect(!InColumn(0, 0, 0, length, width, length + 1, 0), "past the end is out", length + 1, length);
    expect(!InColumn(0, 0, 0, length, width, -5, 0), "behind the Monk is out");
    expect(InColumn(0, 0, 0, length, width, 20, width / 2), "the edge of the strip is in");
    expect(!InColumn(0, 0, 0, length, width, 20, width / 2 + 0.5), "past the edge is out");
    expect(InColumn(0, 0, 0, length, width, 20, -width / 2), "the other edge is in");
    expect(InColumn(5, 5, pi / 2, length, width, 5, 30), "facing north the column runs north");
    expect(!InColumn(5, 5, pi / 2, length, width, 30, 5), "facing north an enemy to the east is out");
    expect(!InColumn(0, 0, 0, length, 0, 10, 0), "no width, no column");
    expect(!InColumn(0, 0, 0, 0, width, 10, 0), "no length, no column");

    // The burn: the ticks that fit, each with an equal share of the total.
    expect(DotTicks(seconds, 1.0) == unsigned(seconds), "one tick a second", DotTicks(seconds, 1.0), seconds);
    expect(DotTicks(seconds, 0.5) == unsigned(seconds * 2), "a tick every half second");
    expect(DotTicks(seconds, 2.0) == unsigned(seconds / 2), "a tick that does not fit twice is not rounded up");
    expect(DotTicks(seconds, 0) == 0, "no tick length, no ticks");
    expect(DotTicks(0, 1.0) == 0, "no duration, no ticks");
    expect(DotTicks(seconds, seconds + 1) == 0, "a tick longer than the burn never lands");
    unsigned const ticks = DotTicks(seconds, 0.5);
    double paid = 0;
    for (unsigned i = 0; i < ticks; ++i)
        paid += TickPct(burn, ticks);
    expect(std::fabs(paid - burn) < 1e-9, "the ticks add up to the sheet's total", paid, burn);
    expect(TickPct(burn, 0) == 0, "no ticks, no damage");

    // The knockback: every enemy struck that still lives; a dead one or one the kick missed is not thrown.
    expect(Knocks(true, true), "a struck living enemy is thrown");
    expect(!Knocks(true, false), "a dead enemy is not thrown");
    expect(!Knocks(false, true), "an enemy the kick missed is not thrown");

    // The slow is a negative aura amount.
    expect(SlowAmount(slow) == -int(slow), "the slow is a negative amount", SlowAmount(slow), -slow);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
