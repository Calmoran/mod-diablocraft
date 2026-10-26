// The real dc_necromancer_army_of_the_dead_math.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_necromancer_army_of_the_dead.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/necromancer/dc_necromancer_army_of_the_dead_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::ArmyOfTheDead;

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
    // argv: the five runes A to E; the skill's total and blasts; Blighted Grasp's total and hits; Frozen Army's total and
    // waves; Unconventional Warfare's total and attacks and seconds; Dead Storm's total, ticks and seconds; Death Valley's
    // start, end, segment and seconds
    if (argc < 23)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const baseTotal = std::atof(argv[6]), graspTotal = std::atof(argv[8]), armyTotal = std::atof(argv[10]),
                 warTotal = std::atof(argv[12]), warSeconds = std::atof(argv[14]), stormTotal = std::atof(argv[15]),
                 stormSeconds = std::atof(argv[17]), start = std::atof(argv[18]), end = std::atof(argv[19]),
                 size = std::atof(argv[20]), pullSeconds = std::atof(argv[21]);
    unsigned const baseBlasts = unsigned(std::atoi(argv[7])), graspHits = unsigned(std::atoi(argv[9])),
                   waves = unsigned(std::atoi(argv[11])), attacks = unsigned(std::atoi(argv[13])),
                   ticks = unsigned(std::atoi(argv[16]));
    (void)argv[22];

    expect(RuneOf(names[0]) == Rune::BlightedGrasp && RuneOf(names[1]) == Rune::FrozenArmy &&
               RuneOf(names[2]) == Rune::UnconventionalWarfare && RuneOf(names[3]) == Rune::DeathValley &&
               RuneOf(names[4]) == Rune::DeadStorm,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Army of the Dead") == Rune::None && RuneOf("dead storm") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // The totals cut into blows add back to the sheet's numbers.
    expect(near(Share(baseTotal, baseBlasts) * baseBlasts, baseTotal), "the blasts add back to the skill's damage");
    expect(near(Share(graspTotal, graspHits) * graspHits, graspTotal), "the hands add back to the rune's damage");
    expect(near(Share(armyTotal, waves) * waves, armyTotal), "the waves add back to the rune's damage");
    expect(near(Share(warTotal, attacks) * attacks, warTotal), "the attacks add back to the rune's damage");
    expect(near(Share(stormTotal, ticks) * ticks, stormTotal), "the ticks add back to the rune's damage");
    expect(Share(baseTotal, 0) == 0.0, "no parts, no blow");

    // When each blow comes: the first at once, the last before the end, evenly.
    expect(OffsetSeconds(0, warSeconds, attacks) == 0.0, "the first attack comes at once");
    expect(near(OffsetSeconds(attacks - 1, warSeconds, attacks), warSeconds - warSeconds / attacks), "the last comes a step before the end",
           OffsetSeconds(attacks - 1, warSeconds, attacks), warSeconds - warSeconds / attacks);
    expect(near(OffsetSeconds(1, stormSeconds, ticks), stormSeconds / ticks), "the ticks are evenly spaced");
    expect(OffsetSeconds(3, 5, 0) == 0.0 && OffsetSeconds(3, 0, 5) == 0.0 && OffsetSeconds(3, -1, 5) == 0.0,
           "no parts or no time: all at once");

    // Frozen Army's line: from the start along the direction, the edge counted.
    expect(OnLine(0, 0, 1, 0, 10, 0, 45, 34), "an enemy on the line");
    expect(OnLine(0, 0, 1, 0, 45, 17, 45, 34), "the far corner is on it (the edge counts)");
    expect(!OnLine(0, 0, 1, 0, 45.01, 0, 45, 34) && !OnLine(0, 0, 1, 0, 10, 17.01, 45, 34) && !OnLine(0, 0, 1, 0, -0.01, 0, 45, 34),
           "past the end, to the side or behind is off it");
    expect(OnLine(0, 0, 0, 1, 0, 20, 45, 34) && !OnLine(0, 0, 0, 1, 20, 0, 45, 34), "the direction is the line's");

    // Death Valley's pull closes from the start radius to the end radius in steps of the segment.
    unsigned const steps = PullSteps(start, end, size);
    expect(steps == unsigned(std::ceil((start - end) / size)) && steps > 0, "the pull has the steps the radii and the segment make", steps, 0);
    expect(near(PullRadius(1, start, end, size), start - size), "the first step closes one segment");
    expect(near(PullRadius(steps, start, end, size), end), "the last step reaches the end radius");
    expect(near(PullRadius(steps + 5, start, end, size), end), "no step goes inside the end radius");
    expect(near(OffsetSeconds(steps, pullSeconds, steps), pullSeconds), "the last step is at the pull's time");
    expect(PullSteps(40, 12, 5) == 6 && PullSteps(40, 10, 7) == 5, "a last short step is still a step");
    expect(PullSteps(10, 40, 5) == 0 && PullSteps(40, 10, 0) == 0 && PullSteps(40, 10, -5) == 0, "no steps for nothing to close");
    expect(Drawn(12, 10) && !Drawn(10, 10) && !Drawn(3, 10), "outside the radius is drawn in, the edge and inside are not");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
