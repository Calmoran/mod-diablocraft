// The real dc_witch_doctor_firebats.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_firebats.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_firebats.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::Firebats;

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
    // argv: the five runes A to E, then the ticks in a second of attack speed (skill, Dire, Hungry, Cloud), the Mana a second costs, the damage a second
    // deals, the cone's degrees, the plague's most stacks, its damage at them, the cloud's bonus a second, its most seconds, its base and its most damage.
    if (argc < 19)
        return 2;
    std::string const dire = argv[1], hungry = argv[2], plague = argv[3], vampire = argv[4], cloud = argv[5];
    double const ticks = std::atof(argv[6]), direTicks = std::atof(argv[7]), hungryTicks = std::atof(argv[8]), cloudTicks = std::atof(argv[9]),
                 cost = std::atof(argv[10]), damage = std::atof(argv[11]), degrees = std::atof(argv[12]), most = std::atof(argv[13]),
                 plagueMost = std::atof(argv[14]), bonus = std::atof(argv[15]), cloudMost = std::atof(argv[16]), cloudBase = std::atof(argv[17]),
                 cloudMax = std::atof(argv[18]);

    expect(RuneOf(dire) == Rune::DireBats && RuneOf(hungry) == Rune::HungryBats && RuneOf(plague) == Rune::PlagueBats &&
               RuneOf(vampire) == Rune::VampireBats && RuneOf(cloud) == Rune::CloudOfBats,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {dire, hungry, plague, vampire, cloud})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A tick is a share of a second of attack speed, and the ticks of a second make the second's Mana and damage.
    expect(near(TickSeconds(ticks, 1.0) * ticks, 1.0) && near(TickSeconds(ticks, 2.0) * 2.0 * ticks, 1.0), "the ticks of a second fill it", TickSeconds(ticks, 1.0), 1.0 / ticks);
    expect(TickSeconds(ticks, 2.0) < TickSeconds(ticks, 1.0), "faster attacks tick sooner", TickSeconds(ticks, 2.0), TickSeconds(ticks, 1.0));
    expect(TickSeconds(0, 1.0) == 0 && TickSeconds(ticks, 0) == 0 && TickSeconds(ticks, -1) == 0, "no speed or no ticks, no tick");
    expect(near(TickShare(cost, ticks) * ticks, cost) && near(TickShare(damage, ticks) * ticks, damage), "the ticks make the second's cost and damage", TickShare(cost, ticks) * ticks, cost);
    expect(TickShare(cost, 0) == 0, "no ticks, no share");
    expect(near(TickShare(cost, direTicks), cost) && near(TickShare(cost, hungryTicks), cost / hungryTicks) && near(TickShare(cost, cloudTicks), cost / cloudTicks),
           "Dire Bats' single tick carries the whole second", TickShare(cost, direTicks), cost);
    expect(TickSeconds(direTicks, 1.0) > TickSeconds(hungryTicks, 1.0), "Dire Bats tick slower than Hungry Bats", TickSeconds(direTicks, 1.0), TickSeconds(hungryTicks, 1.0));

    // The cone: an enemy straight ahead and one at the edge are in; one just past is out; either side.
    double const half = degrees * 3.14159265358979323846 / 360.0;
    expect(InCone(0.0, degrees) && InCone(half, degrees) && InCone(-half, degrees), "the middle and both edges are in the cone");
    expect(!InCone(half + 0.01, degrees) && !InCone(-half - 0.01, degrees), "past either edge is out");
    expect(!InCone(0.0, 0.0), "no cone, nothing in it");

    // Plague Bats: each tick that hits an enemy adds a stack, up to the most; a stack lapsed starts again; damage grows with the stacks to the sheet's most.
    unsigned const cap = unsigned(most);
    expect(PlagueStacks(0, 0, 100, cap) == 1 && PlagueStacks(1, 10, 100, cap) == 2, "each tick adds a stack");
    expect(PlagueStacks(cap, 10, 100, cap) == cap, "stacks stop at the most", PlagueStacks(cap, 10, 100, cap), cap);
    expect(PlagueStacks(2, 500, 100, cap) == 1, "stacks that lapsed start again", PlagueStacks(2, 500, 100, cap), 1);
    expect(PlagueStacks(2, 100, 100, cap) == 3 || cap < 3, "a tick exactly in time keeps the stacks");
    expect(near(PlaguePct(plagueMost, cap, cap), plagueMost) && PlaguePct(plagueMost, 1, cap) < PlaguePct(plagueMost, 2, cap) &&
               PlaguePct(plagueMost, 2, cap) < plagueMost,
           "the damage grows with the stacks to the most", PlaguePct(plagueMost, cap, cap), plagueMost);
    expect(PlaguePct(plagueMost, cap + 5, cap) == plagueMost && PlaguePct(plagueMost, 1, 0) == 0, "no stacks past the most");

    // Cloud of Bats: the damage rises by the bonus each whole second to the most, reaching the sheet's maximum.
    unsigned const seconds = unsigned(cloudMost);
    expect(near(CloudFactor(0.0, bonus, seconds), 1.0) && near(CloudFactor(0.99, bonus, seconds), 1.0), "the first second is the base");
    expect(near(CloudFactor(1.0, bonus, seconds), 1.0 + bonus) && near(CloudFactor(2.5, bonus, seconds), 1.0 + 2.0 * bonus), "each whole second adds the bonus");
    expect(near(CloudFactor(60.0, bonus, seconds), 1.0 + bonus * cloudMost), "the bonus stops at the most", CloudFactor(60.0, bonus, seconds), 1.0 + bonus * cloudMost);
    expect(std::fabs(cloudBase * CloudFactor(60.0, bonus, seconds) - cloudMax) < 1.0, "the base grows to the sheet's maximum", cloudBase * CloudFactor(60.0, bonus, seconds), cloudMax);
    expect(near(CloudFactor(-5.0, bonus, seconds), 1.0), "no negative seconds");

    // The clock: how many ticks fall due, the rest kept.
    double clock = 0;
    expect(Due(clock, 100, 40) == 2 && near(clock, 20), "two ticks fall due and the rest is kept", clock, 20);
    expect(Due(clock, 10, 40) == 0 && near(clock, 30), "a short step adds up");
    expect(Due(clock, 10, 40) == 1 && near(clock, 0), "and falls due", clock, 0);
    double idle = 5;
    expect(Due(idle, 100, 0) == 0 && idle == 0, "no interval, none due");
    double late = 0;
    unsigned const stalled = Due(late, 1e6, 10, 40);
    expect(stalled == 40 && late == 0, "a long stall never fires more than the cap", stalled, 40);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
