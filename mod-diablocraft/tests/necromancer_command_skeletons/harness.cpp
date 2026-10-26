// The real dc_necromancer_command_skeletons_math.h. The rune names and the heal come from argv (read from the sheets by
// test_necromancer_command_skeletons.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/necromancer/dc_necromancer_command_skeletons_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::CommandSkeletons;

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
    // argv: the five runes A to E, then Dark Mending's heal (percent of total Life per hit)
    if (argc < 7)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const healPct = std::atof(argv[6]);
    expect(RuneOf(names[0]) == Rune::Enforcer && RuneOf(names[1]) == Rune::DarkMending &&
               RuneOf(names[2]) == Rune::FreezingGrasp && RuneOf(names[3]) == Rune::KillCommand &&
               RuneOf(names[4]) == Rune::Frenzy,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Command Skeletons") == Rune::None && RuneOf("enforcer") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // Which record the skeletons strike as: the skill's, for Kill Command alone.
    expect(BlowsUseSkillRecord(Rune::KillCommand), "Kill Command's blows come from the skill's record");
    expect(!BlowsUseSkillRecord(Rune::None) && !BlowsUseSkillRecord(Rune::Enforcer) && !BlowsUseSkillRecord(Rune::DarkMending) &&
               !BlowsUseSkillRecord(Rune::FreezingGrasp) && !BlowsUseSkillRecord(Rune::Frenzy),
           "every other rune's blows come from its own record");

    // Dark Mending: a share of the total Life per blow at the commanded target, nothing otherwise.
    expect(std::fabs(HealPerBlow(true, 100000, healPct) - 100000 * healPct / 100.0) < 1e-9, "a blow at the commanded target heals",
           HealPerBlow(true, 100000, healPct), 100000 * healPct / 100.0);
    expect(HealPerBlow(false, 100000, healPct) == 0.0, "a blow at another target heals nothing");
    expect(HealPerBlow(true, 0, healPct) == 0.0 && HealPerBlow(true, -5, healPct) == 0.0, "no Life, no heal");
    expect(HealPerBlow(true, 100000, 0) == 0.0 && HealPerBlow(true, 100000, -1) == 0.0, "no percent, no heal");
    expect(HealPerBlow(true, 200000, healPct) == 2 * HealPerBlow(true, 100000, healPct), "the heal grows with the Life");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
