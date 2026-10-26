// The real dc_crusader_laws_of_justice.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_laws_of_justice.py); nothing else is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/crusader/dc_crusader_laws_of_justice.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::LawsOfJustice;

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
    // argv: the share redirected, the enemy damage cut per stack, the most it stacks to, then the five runes A to E
    if (argc < 9)
        return 2;
    double const share = std::atof(argv[1]), each = std::atof(argv[2]), most = std::atof(argv[3]);
    std::string const runes[5] = {argv[4], argv[5], argv[6], argv[7], argv[8]};

    expect(RuneOf(runes[0]) == Rune::ProtectTheInnocent && RuneOf(runes[1]) == Rune::ImmovableObject &&
               RuneOf(runes[2]) == Rune::FaithsArmor && RuneOf(runes[3]) == Rune::DecayingStrength &&
               RuneOf(runes[4]) == Rune::Bravery,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : runes)
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Rust") == Rune::None, "the base skill and a stranger are no rune");

    // Protect the Innocent: the share of a hit goes to the Crusader, the rest stays with the ally.
    expect(Redirected(1000, share) == 1000 * share / 100, "a hit sends its share to the Crusader", Redirected(1000, share),
           1000 * share / 100);
    expect(Redirected(1000, share) < 1000 && Redirected(1000, share) > 0, "and neither all nor nothing of it");
    expect(Redirected(0, share) == 0 && Redirected(-5, share) == 0, "no hit, nothing sent");
    expect(Redirected(1000, 0) == 0 && Redirected(1000, -10) == 0, "no share, nothing sent");
    expect(Redirected(1000, 250) == 1000, "never more than the hit", Redirected(1000, 250), 1000);

    // Decaying Strength: whole stacks that fit the maximum.
    expect(MaxStacks(most, each) == unsigned(most / each), "the stacks that make the maximum", double(MaxStacks(most, each)),
           most / each);
    expect(MaxStacks(most, each) > 1, "it does stack");
    expect(MaxStacks(50, 15) == 3 && MaxStacks(60, 15) == 4, "a partial stack does not count");
    expect(MaxStacks(10, 15) == 1 && MaxStacks(60, 0) == 1 && MaxStacks(0, 15) == 1, "at least one stack");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
