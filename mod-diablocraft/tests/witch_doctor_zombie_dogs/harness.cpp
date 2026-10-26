// The real dc_witch_doctor_zombie_dogs_math.h. The numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_zombie_dogs.py, the blow and the Life on Hit are the test's own samples). Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_zombie_dogs_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::WitchDoctor::ZombieDogs;

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
    // argv: Burning Dogs' weapon damage a second and the pause between two pulses; Life Link's share; Leeching Beasts'
    // share; a blow and a Life on Hit to try them on; the dogs' blow and the blow Midnight Feast makes of it.
    if (argc < 9)
        return 2;
    double const perSecond = std::atof(argv[1]), tick = std::atof(argv[2]), absorb = std::atof(argv[3]),
                 leech = std::atof(argv[4]), blow = std::atof(argv[5]), lifePerHit = std::atof(argv[6]),
                 baseBlow = std::atof(argv[7]), feastBlow = std::atof(argv[8]);

    // Burning Dogs.
    expect(near(PulsePct(perSecond, tick), perSecond * tick), "a pulse deals its share of the second's damage",
           PulsePct(perSecond, tick), perSecond * tick);
    expect(near(PulsePct(perSecond, tick) / tick, perSecond), "the pulses of a second add up to the sheet's damage",
           PulsePct(perSecond, tick) / tick, perSecond);
    expect(PulsePct(perSecond, 0) == 0 && PulsePct(perSecond, -1) == 0, "no pause, no pulse");
    expect(PulsePct(0, tick) == 0 && PulsePct(-5, tick) == 0, "no damage, no pulse");

    // Life Link.
    expect(near(LinkedShare(blow, absorb), blow * absorb / 100.0) && LinkedShare(blow, absorb) > 0 &&
               LinkedShare(blow, absorb) < blow,
           "the dogs take the share of a blow", LinkedShare(blow, absorb), blow * absorb / 100.0);
    expect(near(LinkedShare(blow, 150), blow), "never more than the blow", LinkedShare(blow, 150), blow);
    expect(LinkedShare(0, absorb) == 0 && LinkedShare(-5, absorb) == 0 && LinkedShare(blow, 0) == 0 &&
               LinkedShare(blow, -5) == 0,
           "no blow or no share, nothing taken");
    expect(near(PerDog(LinkedShare(blow, absorb), 3) * 3, LinkedShare(blow, absorb)),
           "the dogs' parts add up to the share");
    expect(near(PerDog(90, 3), 30) && near(PerDog(90, 1), 90), "an equal part for each dog");
    expect(PerDog(90, 0) == 0, "no dog, no part");

    // Leeching Beasts.
    expect(near(Leeched(lifePerHit, leech), lifePerHit * leech / 100.0) && Leeched(lifePerHit, leech) > 0,
           "an attack heals the share of the Life on Hit", Leeched(lifePerHit, leech), lifePerHit * leech / 100.0);
    expect(near(Leeched(lifePerHit, 50), lifePerHit / 2), "half the share, half the Life");
    expect(Leeched(0, leech) == 0 && Leeched(-5, leech) == 0 && Leeched(lifePerHit, 0) == 0 &&
               Leeched(lifePerHit, -5) == 0,
           "no Life on Hit or no share, nothing healed");

    // Midnight Feast's raise reaching a rune.
    expect(near(Raised(80, baseBlow, feastBlow), 80 * feastBlow / baseBlow),
           "a rune's damage is raised by the dogs' factor", Raised(80, baseBlow, feastBlow), 80 * feastBlow / baseBlow);
    expect(near(Raised(80, baseBlow, baseBlow), 80), "nothing raised, nothing changed");
    expect(Raised(80, 0, feastBlow) == 80 && Raised(80, baseBlow, 0) == 80 && Raised(80, baseBlow, -3) == 80,
           "no blow to compare, the rune's damage as it is");
    expect(Raised(80, baseBlow, feastBlow) > Raised(80, baseBlow, baseBlow), "a larger blow raises it");

    // A new rune, new dogs.
    expect(KeepsDogs(7, 7) && !KeepsDogs(7, 8), "dogs of the same rune stay, those of another go");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
