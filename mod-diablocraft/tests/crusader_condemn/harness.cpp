// The real dc_crusader_condemn.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_condemn.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_condemn.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Condemn;

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
    // argv: the build seconds, the explosion radius, the share in percent, the cooldown cut for each enemy, the Vacuum
    // interval and step, then the five runes A to E
    if (argc < 12)
        return 2;
    double const seconds = std::atof(argv[1]), radius = std::atof(argv[2]), share = std::atof(argv[3]),
                 cut = std::atof(argv[4]), interval = std::atof(argv[5]), step = std::atof(argv[6]);
    std::string const reciprocate = argv[7], vacuum = argv[8], eternal = argv[9], shattering = argv[10],
                      unleashed = argv[11];

    expect(RuneOf(reciprocate) == Rune::Reciprocate && RuneOf(vacuum) == Rune::Vacuum &&
               RuneOf(eternal) == Rune::EternalRetaliation && RuneOf(shattering) == Rune::ShatteringExplosion &&
               RuneOf(unleashed) == Rune::Unleashed,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {reciprocate, vacuum, eternal, shattering, unleashed})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Condemn") == Rune::None, "the base skill and a stranger are no rune");

    // The build: the sheet's seconds for every rune but Unleashed, which goes off at once.
    for (Rune rune : {Rune::None, Rune::Reciprocate, Rune::Vacuum, Rune::EternalRetaliation, Rune::ShatteringExplosion})
        expect(BuildSeconds(rune, seconds) == seconds, "the build is the sheet's seconds", BuildSeconds(rune, seconds),
               seconds);
    expect(BuildSeconds(Rune::Unleashed, seconds) == 0, "Unleashed builds no time");
    expect(BuildSeconds(Rune::None, -1) == 0, "a negative build is none");
    expect(Building(999, 1000) && !Building(1000, 1000) && !Building(1001, 1000),
           "the build lasts until its end moment");

    // Reciprocate: the share of the damage taken, for that rune only.
    expect(Reciprocated(Rune::Reciprocate, 1000, share) == 1000 * share / 100.0,
           "the share of the damage taken is added", Reciprocated(Rune::Reciprocate, 1000, share),
           1000 * share / 100.0);
    for (Rune rune : {Rune::None, Rune::Vacuum, Rune::EternalRetaliation, Rune::ShatteringExplosion, Rune::Unleashed})
        expect(Reciprocated(rune, 1000, share) == 0, "no other rune adds damage");
    expect(Reciprocated(Rune::Reciprocate, 0, share) == 0 && Reciprocated(Rune::Reciprocate, -5, share) == 0 &&
               Reciprocated(Rune::Reciprocate, 1000, 0) == 0,
           "no damage or no share adds nothing");

    // Vacuum: pulses that fit the build, and a reach that grows by the step.
    expect(Pulses(seconds, interval) == unsigned(seconds / interval + 1e-9),
           "the pulses are the build over the interval", Pulses(seconds, interval), seconds / interval);
    expect(Pulses(seconds, 0) == 0 && Pulses(0, interval) == 0, "no interval or no time, no pulse");
    expect(PullReach(radius, step, 0) == radius && PullReach(radius, step, 3) == radius + 3 * step,
           "the reach grows by the step each pulse", PullReach(radius, step, 3), radius + 3 * step);
    expect(PullReach(radius, -1, 4) == radius, "a negative step does not shrink it");
    double const reach = PullReach(radius, step, 1);
    expect(SuckedIn(radius + 0.01, radius, reach) && SuckedIn(reach, radius, reach),
           "an enemy beyond the explosion and inside the reach is taken");
    expect(!SuckedIn(radius, radius, reach) && !SuckedIn(radius - 1, radius, reach),
           "one inside the explosion is left");
    expect(!SuckedIn(reach + 0.01, radius, reach), "one past the reach is left");

    // Eternal Retaliation: the cut for each enemy hit.
    expect(CooldownCut(Rune::EternalRetaliation, 4, cut) == 4 * cut, "the cut is for each enemy hit",
           CooldownCut(Rune::EternalRetaliation, 4, cut), 4 * cut);
    expect(CooldownCut(Rune::EternalRetaliation, 0, cut) == 0 && CooldownCut(Rune::EternalRetaliation, 4, 0) == 0,
           "no enemy or no cut gives nothing");
    for (Rune rune : {Rune::None, Rune::Reciprocate, Rune::Vacuum, Rune::ShatteringExplosion, Rune::Unleashed})
        expect(CooldownCut(rune, 4, cut) == 0, "no other rune cuts the cooldown");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
