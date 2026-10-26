// diablocraft-7k24o (Monk 2.3.15): the real dc_monk_blinding_flash.h. The sheets' numbers come from argv (read by
// test_monk_blinding_flash.py). Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/monk/dc_monk_blinding_flash.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::BlindingFlash;

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
    // argv: blind seconds (3), Self Reflection's blind seconds (6), miss chance (30), Crippling Light's wait is the
    // blind
    if (argc < 4)
        return 2;
    double const blind = std::atof(argv[1]), longBlind = std::atof(argv[2]), miss = std::atof(argv[3]);

    // An ordinary enemy is disoriented for the whole blind, an elite only as long as the tunable says (none: not at
    // all).
    expect(near(DisorientSeconds(false, blind, 0), blind), "an ordinary enemy is disoriented the whole blind", blind,
           blind);
    expect(near(DisorientSeconds(false, longBlind, 1), longBlind), "Self Reflection's blind is the longer one");
    expect(near(DisorientSeconds(true, blind, 0), 0), "an elite with no recovery set is not disoriented");
    expect(near(DisorientSeconds(true, blind, 1.5), 1.5), "an elite is disoriented as long as the tunable says");
    expect(near(DisorientSeconds(true, blind, 10), blind), "and never past the blind");
    expect(near(DisorientSeconds(true, blind, -2), 0), "a negative recovery is none");
    expect(near(DisorientSeconds(false, 0, 0), 0) && near(DisorientSeconds(true, -1, 5), 0), "no blind, no disorient");

    // Only an elite misses.
    expect(near(MissPct(true, miss), miss), "an elite misses the sheet's percent", MissPct(true, miss), miss);
    expect(near(MissPct(false, miss), 0), "an ordinary enemy does not");
    expect(near(MissPct(true, 0), 0), "no percent, no miss");

    // The blind book.
    Blind book;
    expect(near(book.Chance(7, 0), 0), "nobody is blind at first");
    book.Set(7, 5000, miss);
    expect(near(book.Chance(7, 4999), miss), "the blind elite misses until the end of the blind", book.Chance(7, 4999),
           miss);
    expect(near(book.Chance(7, 5000), 0), "and not from the end of it");
    book.Set(7, 9000, miss);
    expect(near(book.Chance(7, 6000), miss), "a new flash on a run-out blind starts it again", book.Chance(7, 6000), miss);
    book.Set(8, 7000, miss);
    expect(near(book.Chance(8, 6500), miss) && near(book.Chance(9, 6500), 0), "each enemy is its own");
    book.Set(8, 12000, miss);
    expect(near(book.Chance(8, 10000), miss), "a new flash starts the blind over", book.Chance(8, 10000), miss);
    book.Set(8, 15000, 0);
    expect(near(book.Chance(8, 11000), 0), "an ordinary enemy blinded again no longer misses");

    // Crippling Light waits for the end of the blind.
    expect(WeakenAfterMs(blind) == 3000, "the weakening begins when the 3 second blind ends", WeakenAfterMs(blind),
           3000);
    expect(WeakenAfterMs(longBlind) == 6000, "and the 6 second one", WeakenAfterMs(longBlind), 6000);
    expect(WeakenAfterMs(0) == 0 && WeakenAfterMs(-1) == 0, "no blind, no wait");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
