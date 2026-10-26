// The real dc_crusader_smite.h. The rune names, the chain radius and counts, Shared Fate's distance and the binding's
// length come from argv (read from the sheets and the tunables by test_crusader_smite.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_smite.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Smite;

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
    // argv: chain radius, additional enemies, Surge's additional enemies, Shared Fate's distance, the binding in
    // seconds, then the five runes A to E
    if (argc < 11)
        return 2;
    double const radius = std::atof(argv[1]), distance = std::atof(argv[4]), seconds = std::atof(argv[5]);
    std::size_t const count = std::size_t(std::atoi(argv[2])), surge = std::size_t(std::atoi(argv[3]));
    std::string const fate = argv[6], shackle = argv[7], shatter = argv[8], reaping = argv[9], surgeRune = argv[10];

    expect(RuneOf(fate) == Rune::SharedFate && RuneOf(shackle) == Rune::Shackle && RuneOf(shatter) == Rune::Shatter &&
               RuneOf(reaping) == Rune::Reaping && RuneOf(surgeRune) == Rune::Surge,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {fate, shackle, shatter, reaping, surgeRune})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crush") == Rune::None, "the base skill and a stranger are no rune");

    // The chains: the nearest enemies inside the radius, up to the count.
    std::vector<double> around{radius + 1, 4, radius, 12, 2, 7, 5};
    auto const three = Chained(around, radius, count);
    expect(three.size() == count, "up to the count are chained", double(three.size()), double(count));
    expect(three.size() >= 3 && around[three[0]] == 2 && around[three[1]] == 4 && around[three[2]] == 5,
           "the nearest come first", count >= 3 ? around[three[0]] : -1, 2);
    for (std::size_t index : three)
        expect(around[index] <= radius, "none is past the radius", around[index], radius);
    auto const five = Chained(around, radius, surge);
    expect(five.size() == std::min<std::size_t>(surge, 6), "Surge chains more, up to those inside", double(five.size()),
           double(surge));
    expect(Chained(around, radius, count)[0] == 4, "the nearest enemy is index 4");
    expect(std::find(five.begin(), five.end(), std::size_t(0)) == five.end(),
           "an enemy past the radius is never chained");
    expect(Chained(around, radius, 100).size() == 6, "with room for all, the six inside are chained and the seventh is not",
           double(Chained(around, radius, 100).size()), 6);
    expect(Chained({}, radius, count).empty() && Chained(around, radius, 0).empty(),
           "nobody, or no count, chains nobody");
    expect(Chained({radius}, radius, 1).size() == 1, "the edge of the radius is inside");
    std::vector<double> tie{3, 3, 3};
    auto const kept = Chained(tie, radius, 2);
    expect(kept.size() == 2 && kept[0] == 0 && kept[1] == 1, "a tie keeps the candidate order");

    // Shared Fate: moving apart by the distance since the binding.
    expect(MovedApart(10 + distance, 10, distance), "a gap that grew by the distance has moved apart", 10 + distance,
           distance);
    expect(!MovedApart(10 + distance - 0.1, 10, distance), "a gap that grew less has not");
    expect(!MovedApart(30, 30, distance), "a gap that did not change has not");
    expect(!MovedApart(100, 10, 0), "no distance, no stun");
    expect(!MovedApart(5, 25, distance), "enemies that came closer have not moved apart");

    // A binding lasts to its end time.
    std::uint64_t const until = 1000 + std::uint64_t(seconds * 1000);
    expect(Bound(until - 1, until) && !Bound(until, until), "bound to the last millisecond, not past it");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
