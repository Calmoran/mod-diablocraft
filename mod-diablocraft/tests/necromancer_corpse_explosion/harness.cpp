// The real dc_necromancer_corpse_explosion_math.h and the shared dc_corpses_math.h. The rune names and numbers come
// from argv (read from the sheets and tunables by test_necromancer_corpse_explosion.py); the corpse cap and lifetime,
// which are blank until the designer answers, are set here for the test. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/necromancer/dc_necromancer_corpse_explosion_math.h"
#include "combat/dc_corpses_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::CorpseExplosion;
using DC::Combat::Corpses::Pile;
using DC::Combat::Corpses::Spot;

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
    // argv: the corpses a cast explodes, the corpse range, the explosion radius, Final Embrace's cost for each corpse,
    // the cone's width, then the five runes A to E
    if (argc < 11)
        return 2;
    std::size_t const most = std::size_t(std::atoi(argv[1]));
    double const range = std::atof(argv[2]), radius = std::atof(argv[3]), perCorpse = std::atof(argv[4]),
                 cone = std::atof(argv[5]);
    std::string const shrapnel = argv[6], embrace = argv[7], close = argv[8], mess = argv[9], cold = argv[10];

    expect(RuneOf(shrapnel) == Rune::Shrapnel && RuneOf(embrace) == Rune::FinalEmbrace &&
               RuneOf(close) == Rune::CloseQuarters && RuneOf(mess) == Rune::BloodyMess &&
               RuneOf(cold) == Rune::DeadCold,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {shrapnel, embrace, close, mess, cold})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Corpse Explosion") == Rune::None,
           "the base skill and a stranger are no rune");

    // Where the corpses are taken: around the Necromancer for Close Quarters only.
    expect(TakesNearTheNecromancer(Rune::CloseQuarters), "Close Quarters takes the corpses near you");
    expect(!TakesNearTheNecromancer(Rune::None) && !TakesNearTheNecromancer(Rune::Shrapnel) &&
               !TakesNearTheNecromancer(Rune::BloodyMess),
           "the others take them near the point aimed at");

    // The cone: opens along (1, 0) from a corpse at the origin.
    expect(InCone(0, 0, 1, 0, 10, 0, 90), "an enemy dead ahead is in the cone");
    expect(InCone(0, 0, 1, 0, 10, 9, 90), "an enemy just inside the half angle is in the cone");
    expect(!InCone(0, 0, 1, 0, 10, 11, 90), "an enemy just past the half angle is not");
    expect(!InCone(0, 0, 1, 0, -10, 0, 90), "an enemy behind the corpse is not");
    expect(InCone(0, 0, 1, 0, -10, 0, 360) && InCone(0, 0, 1, 0, -10, 0, 0), "no angle stated, the whole circle");
    expect(InCone(0, 0, 1, 0, 0, 0, 90), "an enemy on the corpse is in the cone");
    expect(InCone(0, 0, 0, 1, 0, 10, cone > 0 ? cone : 60) && !InCone(0, 0, 0, 1, 10, 0, 60),
           "the cone follows its direction");

    // The nearest enemy a corpse pulls itself toward.
    std::vector<double> const near3 = {9.0, 4.0, 4.0, radius + 1};
    expect(NearestWithin(near3, radius) == 1, "the nearest enemy, the first of a tie",
           double(NearestWithin(near3, radius)), 1);
    expect(NearestWithin({radius + 1, radius + 2}, radius) == std::size_t(-1), "no enemy inside the radius, none");
    expect(NearestWithin({}, radius) == std::size_t(-1), "no enemies, none");
    expect(NearestWithin({radius}, radius) == 0, "an enemy at the radius counts");

    // Final Embrace: the cost for each corpse exploded.
    expect(near(LifeCostPct(perCorpse, 3), perCorpse * 3), "three corpses, three costs", LifeCostPct(perCorpse, 3),
           perCorpse * 3);
    expect(near(LifeCostPct(perCorpse, 0), 0) && near(LifeCostPct(0, 3), 0) && near(LifeCostPct(-1, 3), 0),
           "no corpse or no cost, none");

    // The shared pile, with the cap and the lifetime set here: a cast takes up to `most` corpses within the range,
    // nearest first.
    Pile pile;
    std::uint64_t const lifetime = 60000;
    for (int i = 0; i < 8; ++i)
        pile.Leave(Spot{float(i), 0, 0, 0}, 1000 + i, 20, lifetime);
    pile.Leave(Spot{float(range) + 5.0f, 0, 0, 0}, 1100, 20, lifetime);
    expect(pile.Count(0, 0, float(range), 2000, lifetime) == 8, "eight corpses within the range",
           double(pile.Count(0, 0, float(range), 2000, lifetime)), 8);
    auto const taken = pile.Take(0, 0, float(range), most, 2000, lifetime);
    expect(taken.size() == most, "a cast takes up to the most", double(taken.size()), double(most));
    expect(taken.size() >= 2 && taken[0].x == 0 && taken[1].x == 1, "nearest first");
    expect(pile.Count(0, 0, float(range) + 10, 2000, lifetime) == 9 - most, "the rest stay",
           double(pile.Count(0, 0, float(range) + 10, 2000, lifetime)), double(9 - most));
    expect(near(radius, std::atof(argv[3])), "the explosion radius is the sheet's");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
