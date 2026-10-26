// The real dc_witch_doctor_firebomb.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_firebomb.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_firebomb.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor::Firebomb;

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
    // argv: the five runes A to E, then the explosion's damage, Flash Fire's reduction a bounce and bounces, its delay, the Pyrogeists' total,
    // seconds, tick and most at a time, the pool's total, seconds and tick, Roll the Bones' reach.
    if (argc < 17)
        return 2;
    std::string const ghost = argv[1], bones = argv[2], pit = argv[3], geist = argv[4], flash = argv[5];
    double const base = std::atof(argv[6]), reduction = std::atof(argv[7]), delay = std::atof(argv[9]), geistTotal = std::atof(argv[10]),
                 geistSeconds = std::atof(argv[11]), geistTick = std::atof(argv[12]), pitTotal = std::atof(argv[14]), pitSeconds = std::atof(argv[15]),
                 pitTick = std::atof(argv[16]);
    unsigned const bounces = unsigned(std::atoi(argv[8]));
    std::size_t const most = std::size_t(std::atoi(argv[13]));
    double const reach = argc > 17 ? std::atof(argv[17]) : 14;

    expect(RuneOf(ghost) == Rune::GhostBomb && RuneOf(bones) == Rune::RollTheBones && RuneOf(pit) == Rune::FirePit && RuneOf(geist) == Rune::Pyrogeist &&
               RuneOf(flash) == Rune::FlashFire,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {ghost, bones, pit, geist, flash})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The next bounce: the nearest enemy not yet hit and within reach.
    std::vector<double> const distances{9, 2, 5, 30};
    expect(NextBounce(distances, {false, false, false, false}, reach) == 1, "the nearest enemy");
    expect(NextBounce(distances, {false, true, false, false}, reach) == 2, "not the one already hit");
    expect(NextBounce(distances, {true, true, true, false}, reach) == distances.size(), "nothing within reach is none", NextBounce(distances, {true, true, true, false}, reach), distances.size());
    expect(NextBounce({reach, reach}, {false, false}, reach) == 0 && NextBounce({reach + 0.01}, {false}, reach) == 1, "the edge of the reach is in, a hair past it is out");
    expect(NextBounce({}, {}, reach) == 0, "no enemies, none");

    // Flash Fire: each bounce takes the reduction off the base once more, never below none.
    expect(bounces > 1, "more than one bounce", bounces, 2);
    expect(near(FlashPct(base, 0, reduction), base) && near(FlashPct(base, 1, reduction), base * (1.0 - reduction / 100.0)),
           "the first bounce takes one reduction off", FlashPct(base, 1, reduction), base * (1.0 - reduction / 100.0));
    expect(near(FlashPct(base, bounces, reduction), base * std::max(0.0, 1.0 - reduction / 100.0 * bounces)), "the last bounce takes them all off the base");
    expect(FlashPct(base, 100, reduction) == 0 && near(FlashPct(base, 3, 0), base) && near(FlashPct(base, 3, -5), base), "never below none, and no reduction takes none");
    expect(BounceMs(0, delay) == std::uint32_t(delay * 1000.0 + 0.5) && BounceMs(3, delay) == std::uint32_t(delay * 1000.0 * 4 + 0.5), "a bounce a delay after the last", BounceMs(3, delay), delay * 4000.0);

    // The Pyrogeists: how many give way, and their spews making the total.
    expect(Retired(most - 1, most) == 0 && Retired(most, most) == 1 && Retired(most + 2, most) == 3 && Retired(5, 0) == 0, "the oldest give way so that no more than the most stand");
    unsigned const spews = PeriodicStrike::Ticks(geistSeconds, geistTick);
    expect(spews > 1 && near(PeriodicStrike::TickPct(geistTotal, spews) * spews, geistTotal), "the spews make the total", PeriodicStrike::TickPct(geistTotal, spews) * spews, geistTotal);
    expect(SpewMs(0, geistTick) == std::uint32_t(geistTick * 1000.0 + 0.5) && SpewMs(spews - 1, geistTick) == std::uint32_t(geistSeconds * 1000.0 + 0.5),
           "the first spew a tick after, the last at the end", SpewMs(spews - 1, geistTick), geistSeconds * 1000.0);

    // The pool's ticks make its total.
    unsigned const burns = PeriodicStrike::Ticks(pitSeconds, pitTick);
    expect(burns > 1 && near(PeriodicStrike::TickPct(pitTotal, burns) * burns, pitTotal), "the pool's ticks make the total", PeriodicStrike::TickPct(pitTotal, burns) * burns, pitTotal);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
