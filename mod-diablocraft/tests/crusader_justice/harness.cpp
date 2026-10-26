// The real dc_crusader_justice.h. The rune names and the numbers come from argv (read from the sheets by
// test_crusader_justice.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_justice.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Justice;

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
    // argv: the skill's damage, Hammer of Pursuit's damage, Burst's damage, Holy Bolt's smallest and largest heal, then
    // the five runes A to E
    if (argc < 11)
        return 2;
    double const skill = std::atof(argv[1]), pursuit = std::atof(argv[2]), burst = std::atof(argv[3]),
                 low = std::atof(argv[4]), high = std::atof(argv[5]);
    std::string const sword = argv[6], crack = argv[7], pursuitRune = argv[8], burstRune = argv[9], bolt = argv[10];

    expect(RuneOf(sword) == Rune::SwordOfJustice && RuneOf(crack) == Rune::Crack &&
               RuneOf(pursuitRune) == Rune::HammerOfPursuit && RuneOf(burstRune) == Rune::Burst &&
               RuneOf(bolt) == Rune::HolyBolt,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {sword, crack, pursuitRune, burstRune, bolt})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Shackle") == Rune::None, "the base skill and a stranger are no rune");

    // The hammer's own hit: Hammer of Pursuit's number, and the skill's for every other rune (Burst's 60% is the
    // explosion).
    expect(HitPct(Rune::HammerOfPursuit, skill, pursuit) == pursuit, "Hammer of Pursuit hits for its own number",
           HitPct(Rune::HammerOfPursuit, skill, pursuit), pursuit);
    expect(HitPct(Rune::Burst, skill, burst) == skill, "Burst's hit is the skill's", HitPct(Rune::Burst, skill, burst),
           skill);
    expect(HitPct(Rune::Crack, skill, skill) == skill && HitPct(Rune::None, skill, 0) == skill &&
               HitPct(Rune::SwordOfJustice, skill, 0) == skill && HitPct(Rune::HolyBolt, skill, 0) == skill,
           "every other rune hits for the skill's number");
    expect(pursuit > skill && burst < skill, "the sheet's numbers order as the runes say", pursuit, skill);

    // Holy Bolt's heal is a roll between the two ends and never outside them.
    expect(HealAmount(low, high, 0) == low && HealAmount(low, high, 1) == high, "the ends are the sheet's",
           HealAmount(low, high, 0), low);
    expect(HealAmount(low, high, 0.5) == (low + high) / 2, "the middle roll is the middle", HealAmount(low, high, 0.5),
           (low + high) / 2);
    expect(HealAmount(low, high, -3) == low && HealAmount(low, high, 7) == high,
           "a roll outside 0 to 1 is held to the ends");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
