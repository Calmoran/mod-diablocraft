// The real dc_crusader_laws_of_hope.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_laws_of_hope.py); nothing else is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_laws_of_hope.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::LawsOfHope;

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
    // argv: the heal per second, the heal per point of Wrath, then the five runes A to E
    if (argc < 8)
        return 2;
    double const perSecond = std::atof(argv[1]), perPoint = std::atof(argv[2]);
    std::string const runes[5] = {argv[3], argv[4], argv[5], argv[6], argv[7]};

    expect(RuneOf(runes[0]) == Rune::WingsOfAngels && RuneOf(runes[1]) == Rune::EternalHope &&
               RuneOf(runes[2]) == Rune::HopefulCry && RuneOf(runes[3]) == Rune::FaithsReward &&
               RuneOf(runes[4]) == Rune::PromiseOfFaith,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : runes)
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Rust") == Rune::None, "the base skill and a stranger are no rune");

    // A pulse heals the per-second rate for the seconds it stands for.
    expect(HealPerPulse(perSecond, 1.0) == perSecond, "a one second pulse heals the rate", HealPerPulse(perSecond, 1.0), perSecond);
    expect(HealPerPulse(perSecond, 0.5) == perSecond / 2, "a half second pulse heals half");
    expect(HealPerPulse(perSecond, 0) == 0 && HealPerPulse(perSecond, -1) == 0 && HealPerPulse(0, 1) == 0, "no time or no rate heals nothing");

    // Faith's Reward: Life for every point of Wrath spent.
    expect(HealForWrath(perPoint, 30) == perPoint * 30, "30 Wrath heal 30 times the number", HealForWrath(perPoint, 30), perPoint * 30);
    expect(HealForWrath(perPoint, 0) == 0 && HealForWrath(perPoint, -5) == 0 && HealForWrath(0, 30) == 0, "no Wrath spent heals nothing");

    // Which elements a reduction rune covers: Hopeful Cry the Physical, Promise of Faith the rest, nobody else any.
    bool physicalOnly = true, others = true, none = true;
    for (unsigned e = 0; e < DC::ElementCount; ++e)
    {
        DC::Element const element = DC::Element(e);
        bool const physical = element == DC::Element::Physical;
        physicalOnly = physicalOnly && (ReducesElement(Rune::HopefulCry, element) == physical);
        others = others && (ReducesElement(Rune::PromiseOfFaith, element) == !physical);
        for (Rune rune : {Rune::None, Rune::WingsOfAngels, Rune::EternalHope, Rune::FaithsReward})
            none = none && !ReducesElement(rune, element);
    }
    expect(physicalOnly, "Hopeful Cry covers Physical and only Physical");
    expect(others, "Promise of Faith covers every element but Physical");
    expect(none, "no other rune reduces any element");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
