// The real dc_crusader_bombardment.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_bombardment.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/crusader/dc_crusader_bombardment.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Bombardment;

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
    // argv: the sphere count, the skill's total and radius, the single ball's total and radius, the least wait, what Barrels
    // of Spikes and Mine Field add, the extra wait, the Thorns share, the critical chance, the nearest and farthest mine,
    // the mine radius, then the five runes A to E
    if (argc < 19)
        return 2;
    unsigned const count = unsigned(std::atoi(argv[1]));
    double const total = std::atof(argv[2]), radius = std::atof(argv[3]), ballTotal = std::atof(argv[4]),
                 ballRadius = std::atof(argv[5]), wait = std::atof(argv[6]), barrels = std::atof(argv[7]),
                 mines = std::atof(argv[8]), extra = std::atof(argv[9]), share = std::atof(argv[10]),
                 crit = std::atof(argv[11]), nearest = std::atof(argv[12]), farthest = std::atof(argv[13]),
                 mineRadius = std::atof(argv[14]);
    std::string const a = argv[15], b = argv[16], c = argv[17], d = argv[18], e = argv[19];

    expect(RuneOf(a) == Rune::BarrelsOfSpikes && RuneOf(b) == Rune::Annihilate && RuneOf(c) == Rune::MineField &&
               RuneOf(d) == Rune::ImpactfulBombardment && RuneOf(e) == Rune::Targeted,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {a, b, c, d, e})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Bombardment") == Rune::None, "the base skill and a stranger are no rune");

    // How many fall and what each deals.
    expect(Impacts(Rune::None, count) == count && Impacts(Rune::Targeted, count) == count &&
               Impacts(Rune::MineField, count) == count,
           "every rune but the big ball drops the skill's count", double(Impacts(Rune::None, count)), count);
    expect(Impacts(Rune::ImpactfulBombardment, count) == 1, "the big ball is one");
    expect(near(PctEach(Rune::None, total, ballTotal, count) * count, total), "the spheres share the skill's total",
           PctEach(Rune::None, total, ballTotal, count) * count, total);
    expect(near(PctEach(Rune::ImpactfulBombardment, total, ballTotal, 1), ballTotal), "the big ball deals its own total",
           PctEach(Rune::ImpactfulBombardment, total, ballTotal, 1), ballTotal);
    expect(PctEach(Rune::None, total, ballTotal, 0) == 0 && PctEach(Rune::None, 0, ballTotal, count) == 0,
           "no impacts or no total deals nothing");
    expect(ImpactRadius(Rune::None, radius, ballRadius) == radius && ImpactRadius(Rune::MineField, radius, ballRadius) == radius &&
               ImpactRadius(Rune::ImpactfulBombardment, radius, ballRadius) == ballRadius,
           "only the big ball strikes a wider area");

    // The wait before the next sphere.
    expect(near(MinWait(Rune::None, wait, barrels, mines), wait) && near(MinWait(Rune::Annihilate, wait, barrels, mines), wait),
           "most runes wait the least");
    expect(near(MinWait(Rune::BarrelsOfSpikes, wait, barrels, mines), wait + barrels), "Barrels of Spikes adds its own");
    expect(near(MinWait(Rune::MineField, wait, barrels, mines), wait + mines), "Mine Field adds its own");
    expect(near(Wait(wait, extra, 0), wait) && near(Wait(wait, extra, 1), wait + extra) && near(Wait(wait, extra, 0.5), wait + extra / 2),
           "the wait is the least and a part of the extra");
    expect(near(Wait(wait, extra, 7), wait + extra) && near(Wait(wait, extra, -1), wait) && near(Wait(wait, -3, 1), wait),
           "the roll and the extra stay in bounds");

    // Barrels of Spikes and Annihilate.
    expect(near(BarrelBonus(Rune::BarrelsOfSpikes, 1000, share), 1000 * share / 100.0), "a barrel adds the share of Thorns",
           BarrelBonus(Rune::BarrelsOfSpikes, 1000, share), 1000 * share / 100.0);
    expect(BarrelBonus(Rune::None, 1000, share) == 0 && BarrelBonus(Rune::Targeted, 1000, share) == 0 &&
               BarrelBonus(Rune::BarrelsOfSpikes, 0, share) == 0 && BarrelBonus(Rune::BarrelsOfSpikes, 1000, 0) == 0,
           "no other rune, no Thorns and no share add nothing");
    expect(CritBonusPct(Rune::Annihilate, crit) == crit && CritBonusPct(Rune::None, crit) == 0 &&
               CritBonusPct(Rune::MineField, crit) == 0 && CritBonusPct(Rune::Annihilate, 0) == 0,
           "only Annihilate adds critical chance", CritBonusPct(Rune::Annihilate, crit), crit);

    // The picks and the mines.
    expect(!Pick(0, 0.5).has_value() && Pick(4, 0.0) == 0u && Pick(4, 0.26) == 1u && Pick(4, 1.0) == 3u && Pick(4, -1) == 0u,
           "a roll picks its place and stays inside");
    expect(near(MineDistance(nearest, farthest, 0), nearest) && near(MineDistance(nearest, farthest, 1), farthest) &&
               near(MineDistance(nearest, farthest, 0.5), (nearest + farthest) / 2),
           "a mine lies between the nearest and the farthest");
    expect(near(MineDistance(nearest, nearest - 2, 1), nearest), "no negative reach");
    expect(MineGoesOff(mineRadius, mineRadius) && MineGoesOff(0, mineRadius) && !MineGoesOff(mineRadius + 0.01, mineRadius) &&
               !MineGoesOff(0, 0),
           "an enemy within the radius sets the mine off");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
