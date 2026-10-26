// The real dc_crusader_heavens_fury.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_heavens_fury.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_heavens_fury.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::HeavensFury;

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
    // argv: the ray's total and seconds, the tick, the ray's radius, a beam's radius, the beam's distance and radius, then
    // the five runes A to E
    if (argc < 13)
        return 2;
    double const total = std::atof(argv[1]), seconds = std::atof(argv[2]), tick = std::atof(argv[3]),
                 area = std::atof(argv[4]), beam = std::atof(argv[5]), distance = std::atof(argv[6]),
                 radius = std::atof(argv[7]);
    std::string const ascendancy = argv[8], blessed = argv[9], split = argv[10], pass = argv[11], fires = argv[12];

    expect(RuneOf(ascendancy) == Rune::Ascendancy && RuneOf(blessed) == Rune::BlessedGround &&
               RuneOf(split) == Rune::SplitFury && RuneOf(pass) == Rune::ThouShaltNotPass &&
               RuneOf(fires) == Rune::FiresOfHeaven,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {ascendancy, blessed, split, pass, fires})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Heaven's Fury") == Rune::None, "the base skill and a stranger are no rune");

    // The skill's own ray stays for the skill and the two runes that add to it, and no other.
    expect(KeepsBaseRay(Rune::None) && KeepsBaseRay(Rune::BlessedGround) && KeepsBaseRay(Rune::ThouShaltNotPass),
           "the skill, Blessed Ground and Thou Shalt Not Pass keep the ray");
    expect(!KeepsBaseRay(Rune::Ascendancy) && !KeepsBaseRay(Rune::SplitFury) && !KeepsBaseRay(Rune::FiresOfHeaven),
           "Ascendancy, Split Fury and Fires of Heaven put their own in its place");

    // The ticks pay the whole total.
    unsigned const ticks = unsigned(std::floor(seconds / tick + 1e-9));
    expect(near(PctPerTick(total, seconds, tick) * ticks, total), "the ticks add up to the total",
           PctPerTick(total, seconds, tick) * ticks, total);
    expect(near(PctPerTick(total, seconds, 0.4) * 15, total), "a tick that does not divide the time still pays the total");
    expect(PctPerTick(0, seconds, tick) == 0 && PctPerTick(total, 0, tick) == 0 && PctPerTick(total, seconds, 0) == 0 &&
               PctPerTick(-total, seconds, tick) == 0,
           "no total, time or tick pays nothing");

    // Split Fury: the ring is the area less a beam, and the beams are evenly round it.
    expect(near(RingYards(area, beam), area - beam), "the ring is the area less a beam", RingYards(area, beam),
           area - beam);
    expect(RingYards(beam - 1, beam) == 0, "no negative ring");
    expect(near(BeamHeading(0, 3, 0.5), 0.5), "the first beam is at the start");
    expect(near(BeamHeading(1, 3, 0.5) - BeamHeading(0, 3, 0.5), 2.0 * M_PI / 3.0) &&
               near(BeamHeading(2, 3, 0.5) - BeamHeading(1, 3, 0.5), 2.0 * M_PI / 3.0),
           "the beams are a third of the circle apart");
    expect(near(BeamHeading(2, 0, 0.5), 0.5), "no beams, no division by nothing");

    // Fires of Heaven: along and across turn with the heading, and the beam is a strip.
    expect(near(Along(10, 2, 0), 10) && near(Across(10, 2, 0), 2), "straight east, the point is along and across by its parts");
    expect(near(Along(0, 10, M_PI / 2), 10) && near(Across(0, 10, M_PI / 2), 0), "straight north turns it");
    expect(near(Along(3, 4, 1.1) * Along(3, 4, 1.1) + Across(3, 4, 1.1) * Across(3, 4, 1.1), 25), "a turn keeps the distance");
    expect(InBeam(0, 0, distance, radius) && InBeam(distance, radius, distance, radius) &&
               InBeam(distance / 2, -radius, distance, radius),
           "the edges of the strip are in it");
    expect(!InBeam(-0.01, 0, distance, radius) && !InBeam(distance + 0.01, 0, distance, radius) &&
               !InBeam(1, radius + 0.01, distance, radius) && !InBeam(1, -radius - 0.01, distance, radius),
           "behind, beyond and to the side are out");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
