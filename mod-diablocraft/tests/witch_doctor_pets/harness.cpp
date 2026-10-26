// The real dc_witch_doctor_pets_math.h. The numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_pets.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/witch_doctor/dc_witch_doctor_pets_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::WitchDoctor::Pets;

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
    // argv: the skill's Max Dogs; what Zombie Handler, Fierce Loyalty and Midnight Feast each add; a dog's Life share and Zombie
    // Handler's percent; a dog's blow and Midnight Feast's percent; the ring's two edges; the cleave's reach and angle; the most
    // Sycophants; the Gargantuan's seconds between swings; the seconds between two Fetishes
    if (argc < 16)
        return 2;
    double const count = std::atof(argv[1]), handlerAdd = std::atof(argv[2]), feastAdd = std::atof(argv[3]),
                 loyaltyAdd = std::atof(argv[4]), lifeShare = std::atof(argv[5]), handlerLife = std::atof(argv[6]),
                 blow = std::atof(argv[7]), feast = std::atof(argv[8]), low = std::atof(argv[9]),
                 high = std::atof(argv[10]), yards = std::atof(argv[11]), degrees = std::atof(argv[12]),
                 most = std::atof(argv[13]), swing = std::atof(argv[14]), interval = std::atof(argv[15]);

    // the dogs
    expect(DogCap(count, 0) == 3, "the skill alone allows its three", DogCap(count, 0), 3);
    expect(DogCap(count, handlerAdd) == 4, "one passive allows a fourth", DogCap(count, handlerAdd), 4);
    expect(DogCap(count, handlerAdd + feastAdd + loyaltyAdd) == 6, "all three passives allow six",
           DogCap(count, handlerAdd + feastAdd + loyaltyAdd), 6);
    expect(DogCap(-2, 0) == 0, "a negative count allows none");
    expect(DogCap(count, -5) == 3, "a negative passive takes none away");

    // Life and blow
    expect(near(LifePct(lifeShare, 0), lifeShare), "a dog's Life is its share", LifePct(lifeShare, 0), lifeShare);
    expect(near(LifePct(lifeShare, handlerLife), lifeShare * (1 + handlerLife / 100)), "Zombie Handler raises the Life",
           LifePct(lifeShare, handlerLife), lifeShare * (1 + handlerLife / 100));
    expect(near(LifePct(lifeShare, -50), lifeShare), "a negative percent lowers no Life", LifePct(lifeShare, -50), lifeShare);
    expect(near(LifePct(-1, 20), 0), "no negative Life");
    expect(near(BlowPct(blow, 0), blow), "a dog's blow is the sheet's", BlowPct(blow, 0), blow);
    expect(near(BlowPct(blow, feast), blow * (1 + feast / 100)), "Midnight Feast raises the blow", BlowPct(blow, feast),
           blow * (1 + feast / 100));
    expect(near(BlowPct(blow, -50), blow), "a negative percent lowers no blow");
    expect(near(BlowPct(-1, 50), 0), "no negative blow");

    // the ring
    for (int a = 0; a < 20; ++a)
        for (int r = 0; r <= 10; ++r)
        {
            Offset const point = RingPoint(low, high, a / 20.0, r / 10.0);
            double const radius = std::sqrt(point.x * point.x + point.y * point.y);
            expect(radius >= low - 1e-9 && radius <= high + 1e-9, "a Fetish is on its ring", radius, low);
        }
    expect(near(RingPoint(low, high, 0, 0).x, low) && near(RingPoint(low, high, 0, 0).y, 0), "angle 0, radius 0: the inner edge east");
    expect(near(RingPoint(low, high, 0, 1).x, high), "radius 1: the outer edge", RingPoint(low, high, 0, 1).x, high);
    expect(near(RingPoint(low, high, 0.25, 0).y, low) && std::fabs(RingPoint(low, high, 0.25, 0).x) < 1e-9,
           "a quarter turn is north", RingPoint(low, high, 0.25, 0).y, low);
    expect(near(RingPoint(low, high, 0.5, 0).x, -low), "half a turn is west", RingPoint(low, high, 0.5, 0).x, -low);
    double const middle = std::sqrt((low * low + high * high) / 2);
    expect(near(RingPoint(low, high, 0, 0.5).x, middle), "the ring's area is covered evenly", RingPoint(low, high, 0, 0.5).x, middle);
    expect(near(RingPoint(low, low - 3, 0, 1).x, low), "an upside-down ring is the inner circle", RingPoint(low, low - 3, 0, 1).x, low);
    expect(near(RingPoint(low, high, 0, 7).x, high), "a draw past 1 stays on the ring");

    // the cleave
    expect(InCleave(0, 0, 1, yards, degrees), "straight ahead is in");
    expect(InCleave(0, 0, yards, yards, degrees), "the reach's end is in", yards);
    expect(!InCleave(0, 0, yards + 0.01, yards, degrees), "past the reach is out");
    expect(InCleave(1.5707963267948966, 0, 5, yards, degrees), "a half-turn arc holds the side (90 degrees)");
    expect(!InCleave(1.6, 0, 5, yards, degrees), "past the side is out");
    expect(!InCleave(3.141592653589793, 0, 5, yards, degrees), "behind is out");
    expect(InCleave(6.2, 0.1, 5, yards, degrees), "the angle wraps round the circle");
    expect(!InCleave(0, 0, 5, yards, 0), "no angle, nothing in");
    expect(!InCleave(0, 0, 5, 0, degrees), "no reach, nothing in");
    expect(!InCleave(0, 0, -1, yards, degrees), "a negative distance is out");
    expect(InCleave(2.5, 0, 5, yards, 360), "a whole circle holds them all");
    expect(near(AngleBetween(0.1, 6.2), 0.1 + 6.283185307179586 - 6.2), "the angle between wraps");

    // the Sycophants
    expect(MaySummonSycophant(0, (unsigned)most), "none standing may summon one");
    expect(MaySummonSycophant((unsigned)most - 1, (unsigned)most), "one short of the most may summon one");
    expect(!MaySummonSycophant((unsigned)most, (unsigned)most), "the most standing summons no more");
    expect(!MaySummonSycophant(0, 0), "no cap, none");

    // the times
    expect(Millis(swing) == 3000, "the Gargantuan's three seconds", Millis(swing), 3000);
    expect(Millis(interval) == 100, "a Fetish every tenth of a second", Millis(interval), 100);
    expect(Millis(0.0006) == 1, "a time over half a millisecond rounds up", Millis(0.0006), 1);
    expect(Millis(0.0004) == 0, "a time under half a millisecond is none");
    expect(Millis(0) == 0 && Millis(-1) == 0, "no time is none");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
