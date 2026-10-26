// The real dc_shaman_maelstrom.h, no core. Prints "cases=N failures=M" and exits 0, or names each failing case and
// exits 1.
#include "classes/shaman/dc_shaman_maelstrom.h"

#include <cstdio>

using namespace DC::Combat::Shaman::Maelstrom;

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

int main()
{
    // A gain that fits is paid whole; one at the maximum is banked whole; one that straddles it splits.
    Gain fits = Split(50, 100, 12);
    expect(fits.paid == 12 && fits.overflow == 0, "a gain that fits is paid whole", fits.paid, fits.overflow);
    Gain full = Split(100, 100, 12);
    expect(full.paid == 0 && full.overflow == 12, "a gain at the maximum is all overflow", full.paid, full.overflow);
    Gain straddle = Split(95, 100, 12);
    expect(straddle.paid == 5 && straddle.overflow == 7, "a gain across the maximum splits", straddle.paid,
           straddle.overflow);
    expect(straddle.paid + straddle.overflow == 12, "and loses nothing", straddle.paid + straddle.overflow, 12);
    Gain exact = Split(88, 100, 12);
    expect(exact.paid == 12 && exact.overflow == 0, "a gain that just fills it has no overflow", exact.paid,
           exact.overflow);
    // A bar above its maximum (a maximum that fell) takes nothing, all of it overflows.
    Gain above = Split(110, 100, 4);
    expect(above.paid == 0 && above.overflow == 4, "a bar over its maximum banks it all", above.paid, above.overflow);
    Gain none = Split(10, 100, 0);
    expect(none.paid == 0 && none.overflow == 0, "no gain, nothing");
    Gain negative = Split(10, 100, -5);
    expect(negative.paid == 0 && negative.overflow == 0, "a loss is no gain");

    // What a cast pays: the sheet's number, plus a Primary's flat points, times the generation percent.
    expect(Generated(12, true, 0, 0) == 12, "the sheet's number", Generated(12, true, 0, 0), 12);
    expect(Generated(12, true, 2, 0) == 14, "a Primary adds its flat points", Generated(12, true, 2, 0), 14);
    expect(Generated(20, false, 2, 0) == 20, "another category does not", Generated(20, false, 2, 0), 20);
    expect(Generated(12, true, 0, 50) == 18, "the percent multiplies", Generated(12, true, 0, 50), 18);
    expect(Generated(12, true, 2, 50) == 21, "the flat points are inside the percent", Generated(12, true, 2, 50), 21);
    expect(Generated(0, true, 2, 50) == 0, "a skill that generates nothing gets nothing added");
    expect(Generated(12, true, -3, 0) == 12, "a negative flat is ignored", Generated(12, true, -3, 0), 12);

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
