// The real dc_shaman_bloodlust.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_bloodlust.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/shaman/dc_shaman_bloodlust.h"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::Bloodlust;

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
    // argv: the five runes A to E, Thirst for Battle's extension and its cap in seconds.
    if (argc < 8)
        return 2;
    std::string const heroism = argv[1], fury = argv[2], thirst = argv[3], fervor = argv[4], rage = argv[5];
    double const extend = std::atof(argv[6]), cap = std::atof(argv[7]);

    expect(RuneOf(heroism) == Rune::Heroism && RuneOf(fury) == Rune::AncestralFury &&
               RuneOf(thirst) == Rune::ThirstForBattle && RuneOf(fervor) == Rune::ElementalFervor &&
               RuneOf(rage) == Rune::PrimalRage,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Bloodlust") == Rune::None && RuneOf("Ascendance") == Rune::None,
           "and nothing else is");

    // What each rune adds.
    expect(AddsOf(Rune::Heroism) == Adds::DamageReduction && AddsOf(Rune::AncestralFury) == Adds::DamageBonus &&
               AddsOf(Rune::ElementalFervor) == Adds::MaelstromGeneration &&
               AddsOf(Rune::PrimalRage) == Adds::CooldownReduction,
           "each rune adds its own number");
    expect(AddsOf(Rune::None) == Adds::Nothing && AddsOf(Rune::ThirstForBattle) == Adds::Nothing,
           "the base and Thirst for Battle add no number");

    // Thirst for Battle's extension: a step a kill, never past the cap.
    auto const step = std::uint64_t(extend * 1000.0), limit = std::uint64_t(cap * 1000.0);
    expect(Extension(Rune::ThirstForBattle, 0, extend, cap) == step, "a kill extends the buff by the step",
           double(Extension(Rune::ThirstForBattle, 0, extend, cap)), double(step));
    expect(Extension(Rune::ThirstForBattle, limit - 1, extend, cap) == 1 &&
               Extension(Rune::ThirstForBattle, limit, extend, cap) == 0 &&
               Extension(Rune::ThirstForBattle, limit + 5000, extend, cap) == 0,
           "and never past the cap");
    expect(Extension(Rune::None, 0, extend, cap) == 0 && Extension(Rune::Heroism, 0, extend, cap) == 0 &&
               Extension(Rune::PrimalRage, 0, extend, cap) == 0,
           "no other rune extends it");
    expect(Extension(Rune::ThirstForBattle, 0, 0, cap) == 0 && Extension(Rune::ThirstForBattle, 0, extend, 0) == 0,
           "and a missing number extends nothing");
    // The cap is reached after exactly cap / extend kills.
    std::uint64_t total = 0;
    unsigned kills = 0;
    while (std::uint64_t more = Extension(Rune::ThirstForBattle, total, extend, cap))
    {
        total += more;
        ++kills;
        if (kills > 1000)
            break;
    }
    expect(total == limit && kills == unsigned(cap / extend), "the extra seconds add up to the cap", double(total),
           double(limit));

    std::uint64_t const start = 6000, ends = start + 15000;
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0), "the buff holds until it ends");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
