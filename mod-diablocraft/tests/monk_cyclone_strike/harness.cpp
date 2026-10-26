// diablocraft-56z6v (Monk 2.3.11): the real dc_monk_cyclone_strike.h. Every number comes from argv (the tunables
// sheet's and monk_skill_values.csv's, read by test_monk_cyclone_strike.py); nothing is typed in here. Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_cyclone_strike.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::CycloneStrike;

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
    // argv: target_count, pull radius, Implosion pull radius, landing min, landing spread, blast radius
    if (argc < 7)
        return 2;
    unsigned const maxTargets = unsigned(std::atoi(argv[1]));
    double const pull = std::atof(argv[2]), implosion = std::atof(argv[3]), minYards = std::atof(argv[4]),
                 spread = std::atof(argv[5]), blast = std::atof(argv[6]);

    // The pull takes the nearest `maxTargets` enemies, nearest first.
    std::vector<double> distances;
    for (int i = 0; i < 20; ++i)
        distances.push_back(30 - i); // 30, 29, ... 11: the nearest is the last
    auto const picked = Nearest(distances, maxTargets);
    expect(picked.size() == 16 && maxTargets == 16, "up to 16 enemies", picked.size(), 16);
    expect(picked.front() == 19 && picked.back() == 4, "the nearest 16, nearest first", picked.front(), 19);
    expect(Nearest({5, 6}, maxTargets).size() == 2, "fewer enemies than the cap: all of them");
    std::vector<double> tied(60, 7.0);
    std::vector<std::size_t> firstFive{0, 1, 2, 3, 4};
    expect(Nearest(tied, 5) == firstFive, "a tie keeps the earlier enemies, in order");
    expect(Nearest({}, maxTargets).empty() && Nearest({1, 2}, 0).empty(), "no enemy or no cap: none");

    // The radii: Implosion pulls from farther than the skill, and the blast is not larger than either.
    expect(pull == 24 && implosion == 34 && implosion > pull, "Implosion pulls from 34 yards, the skill from 24",
           implosion, pull);
    expect(blast == 10, "the blast is 10 yards", blast, 10);

    // Landing: between the minimum and minimum + spread, on the line the enemy came along, inside the blast.
    expect(near(LandingYards(minYards, spread, 0), 1) && near(LandingYards(minYards, spread, 1), 9),
           "lands 1 to 9 yards out");
    expect(near(LandingYards(minYards, spread, 5), 9) && near(LandingYards(minYards, spread, -1), 1),
           "the share is clamped");
    expect(LandingYards(minYards, spread, 1) <= blast, "every landing is inside the blast",
           LandingYards(minYards, spread, 1), blast);
    Point const monk{100, 200};
    Point const land = Landing(monk, {100, 230}, 4);
    expect(near(land.x, 100) && near(land.y, 204), "it lands on the line towards where it was", land.y, 204);
    Point const diagonal = Landing(monk, {130, 240}, 5);
    expect(near(std::hypot(diagonal.x - 100, diagonal.y - 200), 5), "5 yards out in any direction");
    expect(near(diagonal.x - 100, 3) && near(diagonal.y - 200, 4), "the 3-4-5 line keeps its direction", diagonal.x,
           103);
    Point const onTop = Landing(monk, monk, 3);
    expect(near(onTop.x, 103) && near(onTop.y, 200), "an enemy on the Monk lands straight ahead");

    // The blast.
    expect(InBlast(monk, blast, {100 + blast, 200}), "the blast's edge is struck");
    expect(!InBlast(monk, blast, {100 + blast + 0.5, 200}), "past the edge is not");
    expect(InBlast(monk, blast, Landing(monk, {100, 260}, LandingYards(minYards, spread, 1))),
           "a pulled enemy is always struck");
    expect(!InBlast(monk, blast, {100, 224}), "an enemy that was not pulled and stays 24 yards away is not");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
