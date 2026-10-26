// diablocraft-exsmi (Monk 2.3.16): the real dc_monk_breath_of_heaven.h. Every number comes from argv (the sheets', read
// by test_monk_breath_of_heaven.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/monk/dc_monk_breath_of_heaven.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Breath;

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
    // argv: heal min, heal max, Circle of Life min, Circle of Life max, globe share %, Infused gain, window seconds,
    // Zephyr %
    if (argc < 9)
        return 2;
    double const lo = std::atof(argv[1]), hi = std::atof(argv[2]), bigLo = std::atof(argv[3]),
                 bigHi = std::atof(argv[4]), share = std::atof(argv[5]), gain = std::atof(argv[6]),
                 window = std::atof(argv[7]), speed = std::atof(argv[8]);

    // The heal: a roll of 0 is the minimum, 1 the maximum, in between a share of the spread.
    expect(HealAmount(lo, hi, 0.0, share, 0) == lo, "the lowest roll heals the minimum",
           HealAmount(lo, hi, 0.0, share, 0), lo);
    expect(HealAmount(lo, hi, 1.0, share, 0) == hi, "the highest roll heals the maximum",
           HealAmount(lo, hi, 1.0, share, 0), hi);
    expect(std::fabs(HealAmount(lo, hi, 0.5, share, 0) - (lo + hi) / 2) < 1e-9, "a middle roll heals the middle");
    expect(HealAmount(lo, hi, 2.0, share, 0) == hi && HealAmount(lo, hi, -1.0, share, 0) == lo,
           "a roll out of range is held");
    expect(HealAmount(bigLo, bigHi, 0.0, share, 0) == bigLo && bigLo > lo && bigHi > hi, "Circle of Life heals more",
           bigLo, lo);
    expect(std::fabs(bigLo - 2 * lo) <= 1.0 && std::fabs(bigHi - 2 * hi) <= 1.0, "twice, as the power file's SF_6 says",
           bigLo, 2 * lo);
    // The Health Globe Healing Bonus: the sheet's share of it, a flat Life number, on top.
    expect(std::fabs(HealAmount(lo, hi, 0.0, share, 1000) - (lo + share / 100.0 * 1000)) < 1e-9,
           "the Health Globe Healing Bonus adds its share", HealAmount(lo, hi, 0.0, share, 1000), lo + share * 10);
    expect(HealAmount(lo, hi, 0.0, share, 0) == lo, "no bonus, no addition");

    // Infused with Light: the window and the extra Spirit.
    std::uint64_t const until = 10000 + std::uint64_t(window * 1000);
    expect(InWindow(10000, until) && InWindow(until - 1, until), "inside the window");
    expect(!InWindow(until, until) && !InWindow(until + 5000, until), "at its end and after, outside");
    expect(ExtraSpirit(true, true, gain) == gain, "a generating attack in the window pays the extra",
           ExtraSpirit(true, true, gain), gain);
    expect(ExtraSpirit(false, true, gain) == 0, "outside the window nothing");
    expect(ExtraSpirit(true, false, gain) == 0, "an attack that generates no Spirit nothing");
    expect(ExtraSpirit(true, true, 0) == 0, "no gain, no extra");

    // Zephyr: a positive amount.
    expect(SpeedAmount(speed) == int(speed), "the speed is a positive amount", SpeedAmount(speed), speed);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
