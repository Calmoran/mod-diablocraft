// The follower skills' shared rules (src/classes/follower/dc_follower_skill_rules.h), compiled alone and driven with numbers read from
// data/d3/followers_skill_numbers.csv and the Healing table by test_follower_skills.py. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/follower/dc_follower_skill_rules.h"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Classes::Follower;

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
    // argv: the main stat cap, Guardian's heal from and to (percent), Intervene's taunt from and to (seconds), Heal's Life percent,
    // Heal's table share, Charge's percent, the Healing table at 70, the two skill ids of a tier, then Inspire's generated percent.
    if (argc < 13)
        return 2;
    double const cap = std::atof(argv[1]), healLow = std::atof(argv[2]), healHigh = std::atof(argv[3]), tauntLow = std::atof(argv[4]),
                 tauntHigh = std::atof(argv[5]), belowPct = std::atof(argv[6]), share = std::atof(argv[7]), chargePct = std::atof(argv[8]),
                 table = std::atof(argv[9]);
    std::string const first = argv[10], second = argv[11];
    double const inspirePct = std::atof(argv[12]);

    // A number scales with the main stat from none to the cap and no further.
    expect(MainStatShare(0, cap) == 0 && MainStatShare(cap, cap) == 1 && MainStatShare(cap * 3, cap) == 1 && MainStatShare(-5, cap) == 0,
           "the share is 0 at none and 1 from the cap");
    expect(std::fabs(MainStatShare(cap / 2, cap) - 0.5) < 1e-12, "half the cap is half the way");
    expect(MainStatShare(100, 0) == 0, "no cap, no share");
    expect(Scaled(tauntLow, tauntHigh, 0) == tauntLow && Scaled(tauntLow, tauntHigh, 1) == tauntHigh, "a taunt runs from its low to its high");
    expect(std::fabs(Scaled(tauntLow, tauntHigh, 0.5) - (tauntLow + tauntHigh) / 2) < 1e-12 && tauntHigh > tauntLow, "and is the middle at half");
    expect(Scaled(healLow, healHigh, 2) == healHigh && Scaled(healLow, healHigh, -1) == healLow, "never past either end");
    expect(Scaled(5, 0, 1) == 5 && Scaled(5, 5, 1) == 5, "a number with no maximum does not scale");
    expect(healHigh > healLow && Scaled(healLow, healHigh, MainStatShare(cap / 4, cap)) > healLow, "a quarter of the cap gives more than none");

    // Tiers and picks.
    expect(!TierOpen(4, 5) && TierOpen(5, 5) && TierOpen(70, 20), "a tier opens at its level");
    expect(Active(true, false, true) && !Active(false, false, true) && !Active(true, false, false), "a pick in an open tier is on");
    expect(Active(false, true, true) && !Active(false, true, false), "the relic gives every skill of an open tier");
    expect(ChoiceOf("1", first, second) == 0 && ChoiceOf("2", first, second) == 1 && ChoiceOf(first, first, second) == 0 &&
               ChoiceOf(second, first, second) == 1,
           "a pick names a choice by its number or its id");
    expect(ChoiceOf("3", first, second) == -1 && ChoiceOf("", first, second) == -1 && ChoiceOf("nothing", first, second) == -1, "and nothing else");

    // Cooldowns.
    expect(CooldownMs(30, false) == 30000 && CooldownMs(30, true) == 15000 && CooldownMs(0, true) == 0, "a cooldown, halved by the relic");
    expect(Ready(100, 100) && !Ready(99, 100) && Ready(101, 100), "ready when the time is reached");

    // Heals, hits and fatal blows.
    expect(Below(49, 100, belowPct) && !Below(belowPct, 100, belowPct) && !Below(0, 100, belowPct) && !Below(10, 0, belowPct),
           "a heal is asked below the share of Life and not for the dead");
    expect(std::fabs(TableHeal(share, table) - share * table) < 1e-9 && TableHeal(0, table) == 0 && TableHeal(share, 0) == 0,
           "a heal is its share of the table");
    expect(std::fabs(LifeHeal(1000, healLow) - 1000 * healLow / 100) < 1e-9 && LifeHeal(0, healLow) == 0 && LifeHeal(1000, -3) == 0,
           "a heal of a percent of the Life");
    expect(std::fabs(WeaponHit(chargePct, 100, 200, 0) - chargePct) < 1e-9 && std::fabs(WeaponHit(chargePct, 100, 200, 1) - 2 * chargePct) < 1e-9,
           "a hit is the percent of the swing, low to high");
    expect(WeaponHit(chargePct, 200, 100, 0.5) == chargePct / 100.0 * 200 && WeaponHit(0, 100, 200, 0.5) == 0 && WeaponHit(chargePct, 0, 0, 0.5) == 0,
           "a swing the wrong way round is its low, and no swing, no hit");
    expect(Fatal(100, 100) && Fatal(100, 500) && !Fatal(100, 99) && !Fatal(100, 0), "a blow is fatal when it takes all the Life");

    // Pulses and range.
    double clock = 0;
    expect(Pulses(clock, 999, 1000) == 0 && Pulses(clock, 1, 1000) == 1 && clock == 0, "a pulse is due at its period");
    expect(Pulses(clock, 2500, 1000) == 2 && clock == 500, "two whole periods and the rest kept");
    expect(Pulses(clock, 10, 0) == 0, "no period, no pulse");
    expect(InRange(8, 8) && !InRange(8.01, 8) && !InRange(1, 0), "within range is within the yards");

    // A critical hit, a roll, a bonus and a window.
    expect(CritMultiplier(150) == 2.5 && CritMultiplier(0) == 1 && CritMultiplier(-4) == 1, "a critical hit is one plus the sheet's damage");
    expect(Rolls(0.0, 1.8) && Rolls(0.017, 1.8) && !Rolls(0.0181, 1.8) && !Rolls(0.0, 0) && Rolls(0.99, 100), "a chance comes up below its percent");
    expect(std::fabs(MoreDamage(3) - 1.03) < 1e-12 && MoreDamage(0) == 1 && MoreDamage(-2) == 1, "a bonus is one plus the percent");
    expect(std::fabs(GeneratedFactor(inspirePct) - (1.0 + inspirePct / 100.0)) < 1e-12 && GeneratedFactor(0) == 1 && GeneratedFactor(-5) == 1,
           "Inspire's generated percent is one plus the percent, and no percent no scale");
    expect(Holds(99, 100) && !Holds(100, 100) && !Holds(5, 0), "a shield, a cloud or a bonus holds until its time");

    // A shot that pierces hits what stands on the line and not what stands beside it.
    expect(OnLine(0, 0, 40, 0, 20, 1.9, 2) && !OnLine(0, 0, 40, 0, 20, 2.1, 2) && OnLine(0, 0, 40, 0, 20, -2, 2), "a point beside the line, within the width");
    expect(OnLine(0, 0, 40, 0, 41, 0, 2) && !OnLine(0, 0, 40, 0, 42.1, 0, 2) && !OnLine(0, 0, 40, 0, -2.1, 0, 2), "and the ends are the line's ends");
    expect(OnLine(5, 5, 5, 5, 5, 6, 2) && !OnLine(0, 0, 40, 0, 20, 0, 0), "a line of no length is a point; no width hits nothing");

    // A volley takes the enemies in turn.
    expect(BoltTarget(0, 3) == 0 && BoltTarget(2, 3) == 2 && BoltTarget(3, 3) == 0 && BoltTarget(4, 2) == 0 && BoltTarget(1, 1) == 0 &&
               BoltTarget(1, 0) == 0,
           "the bolts go round the enemies");

    // A pool's ticks, a ranged reduction, an amplified bonus.
    expect(std::fabs(PerTick(330, 5, 0.5) - 33) < 1e-9 && std::fabs(PerTick(330, 5, 10) - 330) < 1e-9 && PerTick(330, 0, 0.5) == 0 && PerTick(0, 5, 0.5) == 0 &&
               PerTick(330, 5, 0) == 0,
           "a pool's ticks add up to its total");
    expect(std::fabs(PerTick(330, 6, 0.5) * 12 - 330) < 1e-9, "whatever its seconds");
    expect(std::fabs(RangedFactor(6, false) - 0.94) < 1e-12 && RangedFactor(6, true) == 1 && RangedFactor(200, false) == 0 && RangedFactor(-5, false) == 1,
           "a ranged blow is reduced and a melee blow is not");
    expect(std::fabs(Amplified(40, 5) - 2) < 1e-12 && Amplified(0, 5) == 0 && Amplified(40, 0) == 0 && Amplified(-3, 5) == 0, "a bonus amplified by a percent of itself");
    double const elements[] = {0, 12, 30, 30, 7};
    expect(Highest(elements, 5) == 2 && Highest(elements, 2) == 1 && Highest(elements, 0) == 0 && Highest(elements, 1) == 0, "the highest bonus, the first of equals");

    // A pool laid on one map and instance does not reach another.
    expect(SamePlace(33, 7, 33, 7) && !SamePlace(33, 7, 34, 7) && !SamePlace(33, 7, 33, 8) && !SamePlace(33, 7, 34, 8) && SamePlace(0, 0, 0, 0),
           "a place is the same map and the same instance");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
