// The real dc_necromancer_skeletal_mage_math.h. The rune names and numbers come from argv (read from the sheets by
// test_necromancer_skeletal_mage.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/necromancer/dc_necromancer_skeletal_mage_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::SkeletalMage;

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
    // argv: Singularity's bonus for each point, the skill's cost and seconds, Life Support's more seconds, then the
    // five runes A to E
    if (argc < 10)
        return 2;
    double const perPoint = std::atof(argv[1]), cost = std::atof(argv[2]), seconds = std::atof(argv[3]),
                 extra = std::atof(argv[4]);
    std::string const gift = argv[5], singularity = argv[6], support = argv[7], contamination = argv[8],
                      archer = argv[9];

    expect(RuneOf(gift) == Rune::GiftOfDeath && RuneOf(singularity) == Rune::Singularity &&
               RuneOf(support) == Rune::LifeSupport && RuneOf(contamination) == Rune::Contamination &&
               RuneOf(archer) == Rune::SkeletonArcher,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {gift, singularity, support, contamination, archer})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Skeletal Mage") == Rune::None,
           "the base skill and a stranger are no rune");

    // Singularity: the bonus for every point consumed.
    expect(near(SingularityBonusPct(perPoint, 100), perPoint * 100), "a hundred points, a hundred bonuses",
           SingularityBonusPct(perPoint, 100), perPoint * 100);
    expect(near(SingularityBonusPct(perPoint, 0), 0) && near(SingularityBonusPct(perPoint, -5), 0),
           "no points, no bonus");
    expect(near(SingularityBonusPct(0, 100), 0) && near(SingularityBonusPct(-1, 100), 0),
           "no bonus stated, none given");
    expect(near(SingularityBonusPct(perPoint, 1), perPoint), "one point, one bonus");

    // "Consumes all Essence": what the module takes beyond the cost the core takes.
    expect(near(EssenceBeyondCost(150, cost), 150 - cost), "the pool less the cost", EssenceBeyondCost(150, cost),
           150 - cost);
    expect(near(EssenceBeyondCost(cost, cost), 0), "a pool of exactly the cost leaves nothing more");
    expect(near(EssenceBeyondCost(cost - 1, cost), 0), "a pool below the cost takes nothing more");
    expect(near(EssenceBeyondCost(100, -10), 100), "a negative cost is none");

    // Life Support: the skill's seconds and the rune's more, for that rune only.
    expect(near(LifeSeconds(seconds, extra, true), seconds + extra), "Life Support adds its seconds",
           LifeSeconds(seconds, extra, true), seconds + extra);
    expect(near(LifeSeconds(seconds, extra, false), seconds), "another rune keeps the skill's seconds",
           LifeSeconds(seconds, extra, false), seconds);
    expect(near(LifeSeconds(seconds, -3, true), seconds) && near(LifeSeconds(-1, extra, true), extra),
           "no negative time");

    // Where the mage rises: a share of the way to the enemy, held to the way itself.
    expect(near(Along(10, 20, 0.3), 13) && near(Along(20, 10, 0.3), 17), "a share of the way, either direction", Along(10, 20, 0.3), 13);
    expect(near(Along(10, 20, 1.0), 20) && near(Along(10, 20, 0.0), 10), "all the way and none of it");
    expect(near(Along(10, 20, 2.5), 20) && near(Along(10, 20, -1), 10), "never past the enemy or behind the Necromancer");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
