// The real dc_witch_doctor_big_bad_voodoo_math.h. The numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_big_bad_voodoo.py). Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_big_bad_voodoo_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::WitchDoctor::BigBadVoodoo;

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
    // argv: the pause between two looks and what the gifts last beyond it; Ghost Trance's heal a second and damage
    // reduction; the ritual's radius; Boogie Man's chance.
    if (argc < 7)
        return 2;
    double const tick = std::atof(argv[1]), linger = std::atof(argv[2]), heal = std::atof(argv[3]),
                 reduction = std::atof(argv[4]), radius = std::atof(argv[5]), chance = std::atof(argv[6]);

    // The gifts.
    std::uint64_t const gift = GiftMs(tick, linger);
    expect(gift == std::uint64_t((tick + linger) * 1000.0 + 0.5) && gift > std::uint64_t(tick * 1000.0),
           "the gifts outlast the pause between looks", double(gift), (tick + linger) * 1000.0);
    expect(GiftMs(0, linger) == 0 && GiftMs(-1, linger) == 0, "no pause, no gifts");
    expect(GiftMs(tick, -5) == std::uint64_t(tick * 1000.0 + 0.5), "a negative linger adds nothing");
    expect(Holds(1000, 999) && !Holds(1000, 1000) && !Holds(1000, 1001), "the gifts hold until their time, not at it");

    // Ghost Trance.
    expect(near(TickHeal(1000, heal, tick), 1000 * heal / 100.0 * tick), "a look heals its share of the maximum Life",
           TickHeal(1000, heal, tick), 1000 * heal / 100.0 * tick);
    expect(near(TickHeal(1000, heal, tick) / tick, 1000 * heal / 100.0),
           "the looks of a second add up to the percent a second");
    expect(TickHeal(0, heal, tick) == 0 && TickHeal(1000, 0, tick) == 0 && TickHeal(1000, heal, 0) == 0 &&
               TickHeal(-5, heal, tick) == 0 && TickHeal(1000, -5, tick) == 0 && TickHeal(1000, heal, -1) == 0,
           "no Life, no percent or no pause, nothing healed");
    expect(near(Taken(1000, reduction), 1000 * (1.0 - reduction / 100.0)) && Taken(1000, reduction) < 1000,
           "a blow loses the reduction", Taken(1000, reduction), 1000 * (1.0 - reduction / 100.0));
    expect(Taken(1000, 0) == 1000 && Taken(1000, -10) == 1000, "no reduction, the whole blow");
    expect(Taken(1000, 150) == 0, "never more than the whole blow");
    expect(Taken(0, reduction) == 0 && Taken(-5, reduction) == -5, "no blow stays none");

    // The ritual's reach.
    expect(Inside(radius, radius) && Inside(0, radius) && !Inside(radius + 0.1, radius),
           "within the radius, its edge included");

    // Boogie Man.
    expect(Rises(0.0, chance) && Rises(chance - 0.01, chance) && !Rises(chance, chance) && !Rises(99.9, chance),
           "a roll under the chance rises");
    expect(!Rises(0.0, 0) && !Rises(0.0, -5) && !Rises(-10.0, 0), "no chance, nothing rises");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
