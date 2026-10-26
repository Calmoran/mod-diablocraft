// The real dc_demon_hunter_hungering_arrow.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_demon_hunter_hungering_arrow.py); nothing is typed in here. Prints "cases=N" and exits 0, or names
// the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_hungering_arrow.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::HungeringArrow;

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
    // argv: the five runes A to E, the arrow's damage percent, Devouring Arrow's bonus, the arrow count of the split,
    // the seek radius after a pierce, the split's seek radius, its cone in degrees, the travel limit.
    if (argc < 13)
        return 2;
    std::string const serrated = argv[1], shatter = argv[2], devouring = argv[3], puncturing = argv[4], spray = argv[5];
    double const damage = std::atof(argv[6]), bonus = std::atof(argv[7]);
    std::size_t const arrows = std::size_t(std::atoi(argv[8]));
    double const seek = std::atof(argv[9]), splitSeek = std::atof(argv[10]), cone = std::atof(argv[11]),
                 travel = std::atof(argv[12]);
    constexpr double Pi = 3.14159265358979323846;

    expect(RuneOf(serrated) == Rune::SerratedArrow && RuneOf(shatter) == Rune::ShatterShot &&
               RuneOf(devouring) == Rune::DevouringArrow && RuneOf(puncturing) == Rune::PuncturingArrow &&
               RuneOf(spray) == Rune::SprayOfTeeth,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {serrated, shatter, devouring, puncturing, spray})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Devouring Arrow: the arrow's damage grows by the bonus for each pierce.
    expect(PiercedDamagePct(damage, bonus, 0) == damage, "the first enemy takes the arrow's own damage",
           PiercedDamagePct(damage, bonus, 0), damage);
    expect(PiercedDamagePct(damage, bonus, 1) == damage * (1 + bonus / 100), "one pierce adds the bonus once",
           PiercedDamagePct(damage, bonus, 1), damage * (1 + bonus / 100));
    expect(PiercedDamagePct(damage, bonus, 3) == damage * (1 + 3 * bonus / 100), "three pierces add it three times");
    expect(PiercedDamagePct(damage, 0, 5) == damage, "a rune with no bonus never raises the damage");

    // The cone behind the enemy: a half on each side of the heading, and 360 is every direction.
    expect(InCone(0, 0, cone) && InCone(0, cone * Pi / 360 - 0.001, cone) && InCone(0, -cone * Pi / 360 + 0.001, cone),
           "a bearing inside half the cone to either side is in it");
    expect(!InCone(0, cone * Pi / 360 + 0.001, cone) && !InCone(0, -cone * Pi / 360 - 0.001, cone),
           "a bearing past half the cone is out");
    expect(!InCone(0, Pi, cone), "straight back is out");
    expect(InCone(2 * Pi - 0.01, 0.01, cone), "the cone wraps past a full turn");
    expect(InCone(1, 1 + Pi, 360) && InCone(0, 3, 400), "360 degrees or more is every direction");

    // The seek: the nearest enemy not struck yet inside the radius.
    std::vector<double> around{seek + 1, 9, 3, 15, seek};
    std::vector<double> bearings(around.size(), 0.0);
    std::vector<bool> none(around.size(), false);
    auto next = Seek(around, bearings, none, seek, 0, 360, 1);
    expect(next.size() == 1 && next[0] == 2, "the nearest enemy inside the radius is next",
           next.empty() ? -1 : double(next[0]), 2);
    std::vector<bool> nearestHit{false, false, true, false, false};
    next = Seek(around, bearings, nearestHit, seek, 0, 360, 1);
    expect(next.size() == 1 && next[0] == 1, "an enemy already struck is passed over",
           next.empty() ? -1 : double(next[0]), 1);
    std::vector<bool> inside{true, true, true, true, false};
    next = Seek(around, bearings, inside, seek, 0, 360, 1);
    expect(next.size() == 1 && next[0] == 4, "the edge of the radius is inside", next.empty() ? -1 : double(next[0]),
           4);
    std::vector<bool> all(around.size(), true);
    expect(Seek(around, bearings, all, seek, 0, 360, 1).empty(), "no enemy left, no seek");
    expect(Seek({seek + 0.1}, {0.0}, {false}, seek, 0, 360, 1).empty(), "an enemy past the radius is not sought");
    expect(Seek({}, {}, {}, seek, 0, 360, 1).empty(), "nobody around, no seek");

    // The split: the arrows' worth of enemies, nearest first, behind the enemy in the cone and inside its seek radius.
    std::vector<double> crowd{4, 2, 6, 8, 1, splitSeek + 1};
    std::vector<double> behind(crowd.size(), 0.0);
    std::vector<bool> fresh(crowd.size(), false);
    auto split = Seek(crowd, behind, fresh, splitSeek, 0, cone, arrows);
    expect(split.size() == arrows, "the arrow splits into as many arrows as the sheet says", double(split.size()),
           double(arrows));
    expect(split.size() == 3 && split[0] == 4 && split[1] == 1 && split[2] == 0,
           "the nearest enemies take the arrows, nearest first");
    std::vector<double> sideways = behind;
    sideways[4] = Pi / 2;
    split = Seek(crowd, sideways, fresh, splitSeek, 0, cone, arrows);
    expect(split.size() == arrows && split[0] == 1 && split[1] == 0 && split[2] == 2,
           "an enemy beside the enemy, outside the cone, takes no arrow");
    std::vector<bool> oneStruck = fresh;
    oneStruck[4] = true;
    split = Seek(crowd, behind, oneStruck, splitSeek, 0, cone, arrows);
    expect(split.size() == arrows && split[0] == 1, "an enemy already struck takes no arrow");
    expect(Seek({2.0, 3.0}, {0.0, 0.0}, {false, false}, splitSeek, 0, cone, arrows).size() == 2,
           "fewer enemies than arrows, fewer hits");
    expect(Seek({2.0, 3.0}, {0.0, 0.0}, {false, false}, splitSeek, 0, cone, 0).empty(), "no arrows, no hits");

    // The travel limit.
    expect(Reachable(travel, travel) && Reachable(0, travel), "an enemy within the travel limit is reached");
    expect(!Reachable(travel + 0.1, travel), "an enemy past it is not");
    expect(Reachable(1000, 0), "no limit stated, no limit");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
