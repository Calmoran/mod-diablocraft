// The real dc_crusader_consecration.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_consecration.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/crusader/dc_crusader_consecration.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Consecration;

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
    // argv: the radius, Bed of Nails' share, Fearful's chance, then the five runes A to E
    if (argc < 9)
        return 2;
    double const radius = std::atof(argv[1]), share = std::atof(argv[2]), chance = std::atof(argv[3]);
    std::string const aegis = argv[4], nails = argv[5], bathed = argv[6], shattered = argv[7], fearful = argv[8];

    expect(RuneOf(aegis) == Rune::AegisPurgatory && RuneOf(nails) == Rune::BedOfNails &&
               RuneOf(bathed) == Rune::BathedInLight && RuneOf(shattered) == Rune::ShatteredGround &&
               RuneOf(fearful) == Rune::Fearful,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {aegis, nails, bathed, shattered, fearful})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Sanctify") == Rune::None, "the base skill and a stranger are no rune");

    // Standing on the ground: within the radius, edge included; no radius, no ground.
    expect(OnGround(radius, radius) && OnGround(0, radius), "the edge and the centre are on the ground", radius, 0);
    expect(!OnGround(radius + 0.01, radius), "past the edge is off it", radius, 0);
    expect(!OnGround(0, 0), "no radius, no ground");

    // Aegis Purgatory: crossing the edge either way is caught, staying on a side is not.
    expect(Crossed(true, radius + 0.5, radius), "an enemy leaving the ground has crossed", radius, 0);
    expect(Crossed(false, radius - 0.5, radius), "an enemy entering it has crossed", radius, 0);
    expect(!Crossed(true, radius - 0.5, radius) && !Crossed(false, radius + 0.5, radius),
           "an enemy keeping its side has not");
    expect(!Crossed(true, radius, radius), "an enemy on the edge is still inside", radius, 0);

    // Bed of Nails: the share of the Thorns.
    expect(ThornsShare(1000, share) == 1000 * share / 100, "the share is that part of the Thorns",
           ThornsShare(1000, share), 1000 * share / 100);
    expect(ThornsShare(1000, 50) == 500, "half the share is half the Thorns", ThornsShare(1000, 50), 500);
    expect(ThornsShare(0, share) == 0 && ThornsShare(1000, 0) == 0, "no Thorns or no share deals nothing");

    // Fearful's roll: under the chance procs, at it does not; a sure chance never fails.
    expect(Procs(chance - 0.01, chance) && !Procs(chance, chance), "a roll under the chance feared", chance, 0);
    expect(Procs(99.99, 100), "a sure chance always procs");
    expect(!Procs(0, 0), "no chance never procs");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
