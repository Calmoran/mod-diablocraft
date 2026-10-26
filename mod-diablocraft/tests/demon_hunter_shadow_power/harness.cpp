// The real dc_demon_hunter_shadow_power.h. The rune names and numbers come from argv (read from the sheets, the
// tunables and the Healing table by test_demon_hunter_shadow_power.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_shadow_power.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter::ShadowPower;

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
    // argv: the five runes A to E, then the healing share, the Healing table at level 70 and at a lower level, the Life
    // per Kill share and the sheet's Life per Hit.
    if (argc < 11)
        return 2;
    std::string const bane = argv[1], glide = argv[2], gloom = argv[3], well = argv[4], moon = argv[5];
    double const share = std::atof(argv[6]), healingTop = std::atof(argv[7]), healingLow = std::atof(argv[8]),
                 killShare = std::atof(argv[9]), sheetLife = std::atof(argv[10]);

    expect(RuneOf(bane) == Rune::NightBane && RuneOf(glide) == Rune::ShadowGlide && RuneOf(gloom) == Rune::Gloom &&
               RuneOf(well) == Rune::WellOfDarkness && RuneOf(moon) == Rune::BloodMoon,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {bane, glide, gloom, well, moon})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The Life per Hit is the share of the Healing table at the level, and at level 70 the sheet's number.
    double const top = LifePerHit(Rune::None, share, healingTop, killShare, 0);
    expect(std::fabs(top - sheetLife) < 1.0, "at level 70 it is the sheet's number", top, sheetLife);
    expect(LifePerHit(Rune::None, share, healingLow, killShare, 0) < top, "a lower level gives less");
    expect(std::fabs(LifePerHit(Rune::None, share, healingLow, killShare, 0) - share * healingLow) < 1e-9,
           "and is the share of its row", LifePerHit(Rune::None, share, healingLow, killShare, 0), share * healingLow);

    // Life per Kill adds its share.
    expect(std::fabs(LifePerHit(Rune::None, share, healingTop, killShare, 1000) - top - killShare / 100.0 * 1000) <
               1e-9,
           "a share of Life per Kill is added", LifePerHit(Rune::None, share, healingTop, killShare, 1000) - top,
           killShare / 100.0 * 1000);

    // Blood Moon doubles the total, every other rune gives the base.
    expect(std::fabs(LifePerHit(Rune::BloodMoon, share, healingTop, killShare, 1000) -
                     2.0 * LifePerHit(Rune::None, share, healingTop, killShare, 1000)) < 1e-9,
           "Blood Moon doubles the total");
    for (auto const& rune : {bane, glide, gloom, well})
        expect(LifePerHit(RuneOf(rune), share, healingTop, killShare, 1000) ==
                   LifePerHit(Rune::None, share, healingTop, killShare, 1000),
               "every other rune gives the base");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
