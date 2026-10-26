// The real dc_witch_doctor_wall_of_death.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_wall_of_death.py); nothing is typed in here but distances to try. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_wall_of_death.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::WallOfDeath;

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
    // argv: the five runes A to E, the wall's width, Wall of Zombies' width, the capsule's radius, the tick, the
    // damage, its seconds and the seconds a burn lasts.
    if (argc < 13)
        return 2;
    std::string const surrounded = argv[1], ring = argv[2], spirits = argv[3], zombies = argv[4], fire = argv[5];
    double const width = std::atof(argv[6]), wide = std::atof(argv[7]), capsule = std::atof(argv[8]),
                 tick = std::atof(argv[9]), damage = std::atof(argv[10]), seconds = std::atof(argv[11]),
                 burn = std::atof(argv[12]);
    constexpr double Pi = 3.14159265358979323846;

    expect(RuneOf(surrounded) == Rune::SurroundedByDeath && RuneOf(ring) == Rune::RingOfPoison &&
               RuneOf(spirits) == Rune::CommuningWithSpirits && RuneOf(zombies) == Rune::WallOfZombies &&
               RuneOf(fire) == Rune::FireWall,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {surrounded, ring, spirits, zombies, fire})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The wall faces north (heading pi/2): its line runs east and west, across the aim.
    double const heading = Pi / 2;
    expect(WallReach(width, capsule) == width / 2 + capsule && WallReach(wide, capsule) > WallReach(width, capsule),
           "the reach is half the width and the capsule", WallReach(width, capsule), width / 2 + capsule);
    expect(InWall(0, 0, heading, width, capsule), "the middle is in the wall");
    expect(InWall(width / 2 - 0.1, 0, heading, width, capsule), "near the end of the line is in the wall");
    expect(InWall(0, capsule - 0.1, heading, width, capsule) && InWall(0, -(capsule - 0.1), heading, width, capsule),
           "within the capsule, either side");
    expect(!InWall(0, capsule + 0.1, heading, width, capsule), "past the capsule is out");
    expect(InWall(width / 2 + capsule - 0.1, 0, heading, width, capsule),
           "the capsule's rounded end reaches past the line");
    expect(!InWall(width / 2 + capsule + 0.1, 0, heading, width, capsule), "past the end is out");
    expect(!InWall(width / 2 + capsule * 0.8, capsule * 0.8, heading, width, capsule), "the end is round, not square");
    expect(InWall(width / 2 + 0.5 * capsule, 0.5 * capsule, heading, width, capsule),
           "the round end holds what is near it");
    expect(InWall(wide / 2 - 1, 0, heading, wide, capsule) && !InWall(wide / 2 - 1, 0, heading, width, capsule),
           "the wide wall reaches farther along", wide, width);
    // A wall across another aim: the same stands for any heading.
    expect(InWall(std::cos(0.0) * 0 + 5, 0, 0, width, capsule) == true && InWall(0, width / 2 - 0.1, 0, width, capsule),
           "aimed east, the line runs north and south");

    // In front of the wall: between the Witch Doctor and the wall, no farther to a side than the wall's end.
    expect(InFront(-3, 0, width) && InFront(-3, width / 2, width),
           "before the wall's middle and within its width is in front");
    expect(!InFront(3, 0, width) && !InFront(0, 0, width), "behind it or on it is not in front");
    expect(!InFront(-3, width / 2 + 0.1, width), "to a side beyond the width is not in front");
    expect(KnockYards(-3, capsule) == capsule + 3 && KnockYards(-3, capsule) > KnockYards(-1, capsule),
           "the shove carries an enemy past the wall's far edge, the more the farther it is", KnockYards(-3, capsule),
           capsule + 3);

    // The wall's ticks together deal its damage.
    unsigned const ticks = unsigned(std::floor(seconds / tick + 1e-9));
    expect(ticks > 1 && std::fabs(TickPct(damage, seconds, tick) * ticks - damage) < 1e-6, "the ticks make the damage",
           TickPct(damage, seconds, tick) * ticks, damage);
    expect(TickPct(damage, seconds, 0) == 0, "no tick, no damage");

    // Fire Wall burns an enemy again only when its last burn is over.
    std::uint64_t const ms = std::uint64_t(burn * 1000.0);
    expect(BurnsAgain(std::nullopt, 5000, ms), "an enemy not yet burnt burns");
    expect(!BurnsAgain(std::uint64_t(1000), 1000 + ms - 1, ms), "an enemy still burning does not burn again");
    expect(BurnsAgain(std::uint64_t(1000), 1000 + ms, ms), "an enemy whose burn is over burns again");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
