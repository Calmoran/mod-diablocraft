// The real dc_crusader_falling_sword.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_falling_sword.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/crusader/dc_crusader_falling_sword.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::FallingSword;

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
    // argv: the cooldown, the cut for each enemy, the floor, the burn's rate a second and seconds and tick, then the
    // five runes A to E
    if (argc < 12)
        return 2;
    double const cooldown = std::atof(argv[1]), perEnemy = std::atof(argv[2]), floorSeconds = std::atof(argv[3]),
                 rate = std::atof(argv[4]), seconds = std::atof(argv[5]), tick = std::atof(argv[6]);
    std::string const superheated = argv[7], clouds = argv[8], brothers = argv[9], descent = argv[10],
                      flurry = argv[11];

    expect(RuneOf(superheated) == Rune::Superheated && RuneOf(clouds) == Rune::PartTheClouds &&
               RuneOf(brothers) == Rune::RiseBrothers && RuneOf(descent) == Rune::RapidDescent &&
               RuneOf(flurry) == Rune::Flurry,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {superheated, clouds, brothers, descent, flurry})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Falling Sword") == Rune::None, "the base skill and a stranger are no rune");

    // The cooldown waits for what the rune leaves behind, and for nothing else.
    expect(WaitSeconds(Rune::Superheated, seconds) == seconds && WaitSeconds(Rune::PartTheClouds, seconds) == seconds &&
               WaitSeconds(Rune::RiseBrothers, seconds) == seconds && WaitSeconds(Rune::Flurry, seconds) == seconds,
           "the four runes with an effect wait for it", WaitSeconds(Rune::Flurry, seconds), seconds);
    expect(WaitSeconds(Rune::None, seconds) == 0 && WaitSeconds(Rune::RapidDescent, seconds) == 0,
           "the skill and Rapid Descent wait for nothing", WaitSeconds(Rune::None, seconds), 0);
    expect(WaitSeconds(Rune::Superheated, 0) == 0 && WaitSeconds(Rune::Superheated, -3) == 0, "no duration, no wait");

    // Rapid Descent: a second off for each enemy, never below the floor, and a short cooldown is not raised to it.
    expect(near(CooldownSeconds(Rune::RapidDescent, cooldown, 0, perEnemy, floorSeconds), cooldown), "no enemy, no cut",
           CooldownSeconds(Rune::RapidDescent, cooldown, 0, perEnemy, floorSeconds), cooldown);
    expect(near(CooldownSeconds(Rune::RapidDescent, cooldown, 3, perEnemy, floorSeconds), cooldown - 3 * perEnemy),
           "each enemy takes its seconds off", CooldownSeconds(Rune::RapidDescent, cooldown, 3, perEnemy, floorSeconds),
           cooldown - 3 * perEnemy);
    expect(near(CooldownSeconds(Rune::RapidDescent, cooldown, 500, perEnemy, floorSeconds), floorSeconds),
           "the cooldown stops at the floor", CooldownSeconds(Rune::RapidDescent, cooldown, 500, perEnemy, floorSeconds),
           floorSeconds);
    expect(near(CooldownSeconds(Rune::RapidDescent, floorSeconds - 4, 500, perEnemy, floorSeconds), floorSeconds - 4),
           "a cooldown already below the floor is not raised");
    expect(near(CooldownSeconds(Rune::Flurry, cooldown, 9, perEnemy, floorSeconds), cooldown) &&
               near(CooldownSeconds(Rune::None, cooldown, 9, perEnemy, floorSeconds), cooldown),
           "no other rune cuts it");
    expect(near(CooldownSeconds(Rune::RapidDescent, cooldown, 9, 0, floorSeconds), cooldown), "no cut per enemy, no cut");

    // A rate a second paid in ticks adds up to the rate times the seconds.
    unsigned const ticks = unsigned(std::floor(seconds / tick + 1e-9));
    expect(near(PctPerTick(rate, seconds, tick) * ticks, rate * seconds), "the ticks add up to the rate over the seconds",
           PctPerTick(rate, seconds, tick) * ticks, rate * seconds);
    expect(near(PctPerTick(rate, seconds, tick), rate * tick), "a tick is the rate's share of a second",
           PctPerTick(rate, seconds, tick), rate * tick);
    expect(PctPerTick(0, seconds, tick) == 0 && PctPerTick(rate, 0, tick) == 0 && PctPerTick(rate, seconds, 0) == 0 &&
               PctPerTick(-rate, seconds, tick) == 0,
           "no rate, time or tick pays nothing");

    // The storm's pick: every enemy can be picked, none out of range.
    expect(!Pick(0, 0.5).has_value(), "nobody under the storm, nobody picked");
    expect(Pick(4, 0.0) == 0u && Pick(4, 0.26) == 1u && Pick(4, 0.99) == 3u, "a roll picks its place");
    expect(Pick(4, 1.0) == 3u && Pick(1, 0.7) == 0u, "the top of the roll stays inside the enemies");
    expect(Pick(4, -1.0) == 0u, "a negative roll picks the first");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
