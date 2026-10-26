// The real dc_demon_hunter_cluster_arrow.h and the shared pick. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_demon_hunter_cluster_arrow.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_cluster_arrow.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::ClusterArrow;

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
    return std::fabs(a - b) < 1e-6;
}

int main(int argc, char** argv)
{
    // argv: the five runes A to E, then a grenade's least distance and the extra it may add, the bombs, their line's yards, the seconds
    // between them and the side they may stray, Maelstrom's heal share and Dazzling Arrow's stun chance.
    if (argc < 14)
        return 2;
    std::string const loaded = argv[1], stars = argv[2], bombsRune = argv[3], maelstrom = argv[4], dazzling = argv[5];
    double const minimum = std::atof(argv[6]), delta = std::atof(argv[7]), line = std::atof(argv[9]), interval = std::atof(argv[10]),
                 spread = std::atof(argv[11]), heal = std::atof(argv[12]), chance = std::atof(argv[13]);
    unsigned const bombs = unsigned(std::atoi(argv[8]));
    double const quarter = 0.25;

    expect(RuneOf(loaded) == Rune::LoadedForBear && RuneOf(stars) == Rune::ShootingStars && RuneOf(bombsRune) == Rune::ClusterBombs &&
               RuneOf(maelstrom) == Rune::Maelstrom && RuneOf(dazzling) == Rune::DazzlingArrow,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {loaded, stars, bombsRune, maelstrom, dazzling})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A grenade lands the least distance up to the least plus the extra from the impact, in any direction.
    Spot east = GrenadeLanding(10, 20, 0.0, 0.0, minimum, delta);
    expect(near(east.x, 10 + minimum) && near(east.y, 20), "heading east at the least distance", east.x, 10 + minimum);
    Spot north = GrenadeLanding(10, 20, quarter, 1.0, minimum, delta);
    expect(near(north.x, 10) && near(north.y, 20 + minimum + delta), "a quarter turn is north, at the farthest", north.y, 20 + minimum + delta);
    Spot west = GrenadeLanding(10, 20, 0.5, 0.5, minimum, delta);
    expect(near(west.x, 10 - (minimum + delta / 2)) && near(west.y, 20), "half a turn is west, half way out", west.x, 10 - (minimum + delta / 2));
    bool within = true;
    for (int heading = 0; heading < 40; ++heading)
        for (int distance = 0; distance <= 10; ++distance)
        {
            Spot spot = GrenadeLanding(0, 0, heading / 40.0, distance / 10.0, minimum, delta);
            double const yards = std::hypot(spot.x, spot.y);
            within = within && yards >= minimum - 1e-9 && yards <= minimum + delta + 1e-9;
        }
    expect(within, "every landing is inside the ring");

    // Cluster Bombs: spread evenly along the line, the last at its end, strayed to the side within the spread.
    expect(bombs > 1, "more than one bomb", bombs, 2);
    Spot first = BombLanding(0, 0, 0.0, 0, bombs, line, 0.5, spread), last = BombLanding(0, 0, 0.0, bombs - 1, bombs, line, 0.5, spread);
    expect(near(first.x, line / bombs) && near(first.y, 0), "the first bomb a share along the line", first.x, line / bombs);
    expect(near(last.x, line) && near(last.y, 0), "the last bomb at its end", last.x, line);
    Spot left = BombLanding(0, 0, 0.0, 0, bombs, line, 1.0, spread), right = BombLanding(0, 0, 0.0, 0, bombs, line, 0.0, spread);
    expect(near(left.y, spread) && near(right.y, -spread), "to either side by the spread", left.y, spread);
    Spot up = BombLanding(0, 0, 3.14159265358979323846 / 2, bombs - 1, bombs, line, 0.5, spread);
    expect(near(up.x, 0) && near(up.y, line), "along a line heading north", up.y, line);
    expect(near(BombLanding(0, 0, 0.0, 0, 0, line, 0.5, spread).x, 0), "no bombs, no distance");
    expect(BombDelayMs(0, interval) == 0 && BombDelayMs(bombs - 1, interval) == std::uint32_t(interval * 1000.0 * (bombs - 1) + 0.5),
           "a bomb every interval from the cast", BombDelayMs(bombs - 1, interval), interval * 1000.0 * (bombs - 1));
    expect(BombDelayMs(4, 0) == 0 && BombDelayMs(4, -1) == 0, "no interval, all at once");

    // The rockets: the nearest enemies to the impact, nearest first, a tie keeping its order.
    std::vector<double> const distances{9, 2, 5, 2, 30};
    auto const near3 = NearestFirst(distances, 3);
    expect(near3.size() == 3 && near3[0] == 1 && near3[1] == 3 && near3[2] == 2, "the nearest three, nearest first");
    expect(NearestFirst(distances, 99).size() == distances.size() && NearestFirst(distances, 0).empty() && NearestFirst({}, 3).empty(),
           "more asked for than there are, none asked for, none there");

    // Maelstrom's heal and Dazzling Arrow's stun.
    expect(near(Healed(1000, heal), 1000 * heal / 100.0), "the share of the maximum Life", Healed(1000, heal), 1000 * heal / 100.0);
    expect(Healed(0, heal) == 0 && Healed(1000, 0) == 0 && Healed(-4, heal) == 0 && Healed(1000, -2) == 0, "no Life, no share, no heal");
    expect(Stuns(0.0, chance) && Stuns(chance - 0.01, chance) && !Stuns(chance, chance) && !Stuns(0.0, 0.0), "a roll under the chance stuns, at it does not");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
