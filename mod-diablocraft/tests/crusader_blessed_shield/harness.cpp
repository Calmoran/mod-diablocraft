// The real dc_crusader_blessed_shield.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_crusader_blessed_shield.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/crusader/dc_crusader_blessed_shield.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::BlessedShield;

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
    // argv: the bounce radius, the first enemy's stun chance, the reduction for each after it, then the five runes A to
    // E
    if (argc < 10)
        return 2;
    double const radius = std::atof(argv[1]), base = std::atof(argv[2]), reduction = std::atof(argv[3]);
    double const lane = std::atof(argv[9]);
    std::string const stagger = argv[4], combust = argv[5], aegis = argv[6], shatter = argv[7], pierce = argv[8];

    expect(RuneOf(stagger) == Rune::StaggeringShield && RuneOf(combust) == Rune::Combust &&
               RuneOf(aegis) == Rune::DivineAegis && RuneOf(shatter) == Rune::ShatteringThrow &&
               RuneOf(pierce) == Rune::PiercingShield,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {stagger, combust, aegis, shatter, pierce})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The ricochet: the nearest enemy not hit yet inside the radius.
    std::vector<double> around{radius + 1, 9, 3, 15, radius};
    std::vector<bool> none(around.size(), false);
    expect(NextBounce(around, none, radius) == 2, "the nearest enemy inside the radius is next",
           NextBounce(around, none, radius), 2);
    std::vector<bool> nearestHit{false, false, true, false, false};
    expect(NextBounce(around, nearestHit, radius) == 1, "an enemy already hit is passed over",
           NextBounce(around, nearestHit, radius), 1);
    std::vector<bool> inside{true, true, true, true, false};
    expect(NextBounce(around, inside, radius) == 4, "the edge of the radius is inside",
           NextBounce(around, inside, radius), 4);
    std::vector<bool> all(around.size(), true);
    expect(NextBounce(around, all, radius) == -1, "no enemy left, no bounce");
    expect(NextBounce({radius + 0.1}, {false}, radius) == -1, "an enemy past the radius is not bounced to");
    expect(NextBounce({}, {}, radius) == -1, "nobody around, no bounce");

    // Staggering Shield: the first enemy's chance, falling by the reduction for each after it, never below nothing.
    expect(StunChance(base, reduction, 0) == base, "the first enemy has the base chance",
           StunChance(base, reduction, 0), base);
    expect(StunChance(base, reduction, 1) == base - reduction, "the second has less", StunChance(base, reduction, 1),
           base - reduction);
    expect(StunChance(base, reduction, 3) == base - 3 * reduction, "the fourth has three reductions less");
    expect(StunChance(base, reduction, 1000) == 0, "the chance never goes below nothing");

    // Piercing Shield: the line it flies along.
    expect(OnLine(30, 1, 70, 4) && OnLine(70, 2, 70, 4), "an enemy on the line is pierced");
    expect(!OnLine(71, 0, 70, 4) && !OnLine(-1, 0, 70, 4), "past the length or behind is not");
    expect(!OnLine(30, 2.01, 70, 4) && OnLine(30, -1.99, 70, 4), "the width is half each side");
    expect(!OnLine(30, 0, 70, 0), "no width, no pierce");
    // The designer's width for Piercing Shield: 3 yards, a yard and a half each side.
    expect(OnLine(30, lane / 2 - 0.01, 70, lane) && OnLine(30, -lane / 2 + 0.01, 70, lane), "an enemy within half the width of the line is pierced", lane, 0);
    expect(!OnLine(30, lane / 2 + 0.01, 70, lane) && !OnLine(30, -lane / 2 - 0.01, 70, lane), "an enemy past half the width is not", lane, 0);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
