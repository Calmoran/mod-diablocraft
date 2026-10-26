// The real dc_witch_doctor_zombie_charger.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_zombie_charger.py); nothing is typed in here. Prints "cases=N" and exits 0, or names
// the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_zombie_charger.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <vector>

using namespace DC::Combat::WitchDoctor::ZombieCharger;

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
    // argv: the five runes A to E, the path's length and width, the bears' count and spacing, the cold zombies' count,
    // the tower's reach and distance, Undeath's most.
    if (argc < 14)
        return 2;
    std::string const bears = argv[1], cold = argv[2], pile = argv[3], undeath = argv[4], beast = argv[5];
    double const length = std::atof(argv[6]), width = std::atof(argv[7]), spacing = std::atof(argv[9]),
                 reach = std::atof(argv[11]), distance = std::atof(argv[12]);
    unsigned const bearCount = unsigned(std::atoi(argv[8])), coldCount = unsigned(std::atoi(argv[10])),
                   most = unsigned(std::atoi(argv[13]));

    expect(RuneOf(bears) == Rune::ZombieBears && RuneOf(cold) == Rune::LumberingCold && RuneOf(pile) == Rune::PileOn &&
               RuneOf(undeath) == Rune::Undeath && RuneOf(beast) == Rune::ExplosiveBeast,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {bears, cold, pile, undeath, beast})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A zombie's path: ahead of it, within its length, within half its width on each side; heading east.
    expect(OnPath(length / 2, 0, 0, length, width) && OnPath(length, 0, 0, length, width) &&
               OnPath(0, 0, 0, length, width),
           "the path's ends are on it");
    expect(!OnPath(length + 0.1, 0, 0, length, width) && !OnPath(-0.1, 0, 0, length, width), "and nothing past them");
    expect(OnPath(10, width / 2, 0, length, width) && !OnPath(10, width / 2 + 0.1, 0, length, width) &&
               OnPath(10, -width / 2, 0, length, width),
           "within half the width each side");
    expect(!OnPath(10, 0, 0, length, 0) && !OnPath(10, 0, 0, length, -1), "a path with no width reaches nobody");
    expect(OnPath(0, 5, 3.14159265358979323846 / 2, length, width) &&
               !OnPath(0, -5, 3.14159265358979323846 / 2, length, width),
           "it follows its heading");

    // Zombie Bears: side by side and centred.
    auto const offsets = BearOffsets(bearCount, spacing);
    expect(offsets.size() == bearCount, "one offset for each bear", double(offsets.size()), bearCount);
    double sum = 0;
    for (double offset : offsets)
        sum += offset;
    expect(near(sum, 0), "centred on the aim", sum, 0);
    expect(offsets.size() < 2 || near(offsets[1] - offsets[0], spacing), "a spacing apart",
           offsets.size() < 2 ? 0 : offsets[1] - offsets[0], spacing);
    expect(BearOffsets(0, spacing).empty() && BearOffsets(1, spacing).size() == 1 &&
               near(BearOffsets(1, spacing)[0], 0),
           "none for none, one in the middle");

    // Lumbering Cold: evenly round from the aim.
    auto const headings = RunningHeadings(coldCount, 0.5);
    expect(headings.size() == coldCount && near(headings[0], 0.5), "the first runs along the aim",
           headings.empty() ? 0 : headings[0], 0.5);
    expect(headings.size() > 1 && near(headings[1] - headings[0], 6.28318530717958647692 / coldCount),
           "the rest are evenly round");
    expect(near(headings.back() - headings.front(), 6.28318530717958647692 * (coldCount - 1) / coldCount),
           "all the way round and no more");

    // Pile On: on the aimed enemy within reach, else ahead by the distance.
    expect(near(TowerDistance(reach - 1, reach, distance), reach - 1), "on the enemy within reach",
           TowerDistance(reach - 1, reach, distance), reach - 1);
    expect(near(TowerDistance(reach, reach, distance), reach), "and at the edge of it");
    expect(near(TowerDistance(reach + 0.1, reach, distance), distance) &&
               near(TowerDistance(std::nullopt, reach, distance), distance),
           "beyond it or with none aimed, ahead by the distance");

    // Undeath: a kill reanimates until the most.
    expect(Reanimates(true, 0, most) && Reanimates(true, most - 1, most) && !Reanimates(true, most, most),
           "reanimates up to the most", most, most);
    expect(!Reanimates(false, 0, most), "no kill, no reanimation");
    expect(NearestWithin({30.0, 12.0, 5.0}, 22).value_or(99) == 2 && NearestWithin({22.0}, 22).value_or(99) == 0 &&
               !NearestWithin({22.1, 40.0}, 22) && !NearestWithin({}, 22),
           "the nearest enemy within the search range");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
