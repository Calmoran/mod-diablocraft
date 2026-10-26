// The real dc_crusader_fist_of_the_heavens.h and dc_crusader_dot.h. The rune names and numbers come from argv (read
// from the sheets and the tunables by test_crusader_fist_of_the_heavens.py); nothing is typed in here. Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_dot.h"
#include "classes/crusader/dc_crusader_fist_of_the_heavens.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader;
using namespace DC::Combat::Crusader::FistOfTheHeavens;

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
    // argv: the bolts, their travel, the fissure's seconds, its tick, its damage over time, the zap radius, then the
    // five runes A to E
    if (argc < 13)
        return 2;
    double const lane = std::atof(argv[12]);
    unsigned const bolts = unsigned(std::atoi(argv[1]));
    double const travel = std::atof(argv[2]), seconds = std::atof(argv[3]), tick = std::atof(argv[4]),
                 total = std::atof(argv[5]), zap = std::atof(argv[6]);
    std::string const tempest = argv[7], reverb = argv[8], fissure = argv[9], well = argv[10], retribution = argv[11];
    double const pi = 3.14159265358979323846;

    expect(RuneOf(tempest) == Rune::HeavensTempest && RuneOf(reverb) == Rune::Reverberation &&
               RuneOf(fissure) == Rune::Fissure && RuneOf(well) == Rune::DivineWell &&
               RuneOf(retribution) == Rune::Retribution,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {tempest, reverb, fissure, well, retribution})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The bolts: evenly round the circle from the first.
    expect(std::fabs(BoltHeading(0, bolts, 0.5) - 0.5) < 1e-9, "the first bolt goes where it is aimed");
    expect(std::fabs(BoltHeading(1, bolts, 0) - 2 * pi / bolts) < 1e-9, "the next is a sixth round",
           BoltHeading(1, bolts, 0), 2 * pi / bolts);
    expect(std::fabs(BoltHeading(bolts / 2, bolts, 0) - pi) < 1e-9, "half the bolts on, the opposite way",
           BoltHeading(bolts / 2, bolts, 0), pi);
    expect(BoltHeading(0, 0, 1.25) == 1.25, "no bolts, no turning");
    std::set<long> headings;
    for (unsigned k = 0; k < bolts; ++k)
        headings.insert(std::lround(BoltHeading(k, bolts, 0) * 1e6));
    expect(headings.size() == bolts, "every bolt has a heading of its own", double(headings.size()), bolts);

    // A bolt's lane: within the travel and half the width.
    expect(OnBolt(travel, 1, travel, 4) && OnBolt(0, 2, travel, 4), "the end and the edge of the lane are on it");
    expect(!OnBolt(travel + 0.1, 0, travel, 4) && !OnBolt(-0.1, 0, travel, 4),
           "past the end or behind the start is off it");
    expect(!OnBolt(10, 2.01, travel, 4) && OnBolt(10, -1.99, travel, 4), "the width is half each side");
    expect(!OnBolt(10, 0, travel, 0), "no width, no strike");
    // The designer's lane for the bolts, the fist and the arcs: 3 yards wide.
    expect(OnBolt(20, lane / 2 - 0.01, travel, lane) && OnBolt(20, -lane / 2 + 0.01, travel, lane), "an enemy within half the lane of a bolt is struck", lane, 0);
    expect(!OnBolt(20, lane / 2 + 0.01, travel, lane) && !OnBolt(20, -lane / 2 - 0.01, travel, lane), "an enemy past half the lane is not", lane, 0);

    // Divine Well's zaps: the distance from the ray.
    expect(RayDistance(10, 3, travel) == 3, "beside the ray", RayDistance(10, 3, travel), 3);
    expect(RayDistance(-3, 4, travel) == 5, "behind the start it is the start's distance", RayDistance(-3, 4, travel),
           5);
    expect(RayDistance(travel + 3, 4, travel) == 5, "past the end it is the end's distance");
    expect(RayDistance(10, -zap, travel) <= zap && RayDistance(10, zap + 0.1, travel) > zap,
           "the zap reaches its radius and no further", zap, 0);

    // Fissure: its burn over its seconds.
    expect(Dot::Ticks(seconds, tick) == unsigned(seconds / tick + 1e-9), "the fissure's ticks fit its seconds",
           Dot::Ticks(seconds, tick), seconds / tick);
    expect(std::fabs(Dot::TickPct(total, Dot::Ticks(seconds, tick)) * Dot::Ticks(seconds, tick) - total) < 1e-9,
           "the ticks add up to the total");
    expect(Dot::Ticks(seconds, 0) == 0, "no tick length, no ticks");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
