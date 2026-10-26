// The real dc_demon_hunter_bolas.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_bolas.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_bolas.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter::Bolas;

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
    // argv: the five runes A to E, the fuse, Imminent Doom's fuse, the time between the bolas of a volley.
    if (argc < 9)
        return 2;
    std::string const volatileExplosives = argv[1], freezing = argv[2], thunder = argv[3], bitter = argv[4],
                      doom = argv[5];
    double const fuse = std::atof(argv[6]), doomFuse = std::atof(argv[7]), perShot = std::atof(argv[8]);

    expect(RuneOf(volatileExplosives) == Rune::VolatileExplosives && RuneOf(freezing) == Rune::FreezingStrike &&
               RuneOf(thunder) == Rune::ThunderBall && RuneOf(bitter) == Rune::BitterPill &&
               RuneOf(doom) == Rune::ImminentDoom,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {volatileExplosives, freezing, thunder, bitter, doom})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The bolas of a volley: the first at the fuse, each after it a shot later.
    expect(ExplodesAfter(fuse, perShot, 0) == fuse, "the first bola explodes at the fuse",
           ExplodesAfter(fuse, perShot, 0), fuse);
    expect(std::fabs(ExplodesAfter(fuse, perShot, 1) - (fuse + perShot)) < 1e-9, "the second one shot later",
           ExplodesAfter(fuse, perShot, 1), fuse + perShot);
    expect(std::fabs(ExplodesAfter(fuse, perShot, 2) - (fuse + 2 * perShot)) < 1e-9, "the third two shots later");
    expect(ExplodesAfter(doomFuse, perShot, 0) == doomFuse && doomFuse > fuse, "Imminent Doom's longer fuse", doomFuse,
           fuse);
    expect(ExplodesAfter(fuse, 0, 2) == fuse, "no time between the shots, all at the fuse");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
