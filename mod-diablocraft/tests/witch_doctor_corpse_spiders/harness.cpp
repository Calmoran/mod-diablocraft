// The real dc_witch_doctor_corpse_spiders.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_corpse_spiders.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_corpse_spiders.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::CorpseSpiders;

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
    // argv: the five runes A to E, then the spiders' total damage, the spiders, the bites each, their life in seconds, the queen's total, her
    // seconds and pulse, and Medusa Spiders' chance.
    if (argc < 14)
        return 2;
    std::string const blazing = argv[1], queen = argv[2], leaping = argv[3], widow = argv[4], medusa = argv[5];
    double const total = std::atof(argv[6]), life = std::atof(argv[9]), queenTotal = std::atof(argv[10]), queenSeconds = std::atof(argv[11]),
                 pulse = std::atof(argv[12]), chance = std::atof(argv[13]);
    unsigned const spiders = unsigned(std::atoi(argv[7])), bites = unsigned(std::atoi(argv[8]));

    expect(RuneOf(blazing) == Rune::BlazingSpiders && RuneOf(queen) == Rune::SpiderQueen && RuneOf(leaping) == Rune::LeapingSpiders &&
               RuneOf(widow) == Rune::Widowmakers && RuneOf(medusa) == Rune::MedusaSpiders,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {blazing, queen, leaping, widow, medusa})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The bites together deal the total.
    expect(spiders > 1 && bites > 1, "several spiders biting several times", spiders, bites);
    expect(near(BiteShare(total, spiders, bites) * spiders * bites, total) && near(BiteShare(total, spiders, bites), total / (spiders * bites)),
           "the bites make the sheet's total", BiteShare(total, spiders, bites) * spiders * bites, total);
    expect(BiteShare(total, 0, bites) == 0 && BiteShare(total, spiders, 0) == 0, "no spiders or no bites, no damage");

    // Each bite falls inside the spider's life, evenly.
    std::uint32_t const first = BiteMs(0, bites, life), last = BiteMs(bites - 1, bites, life);
    expect(first > 0 && last < std::uint32_t(life * 1000.0), "the bites fall inside the life", last, life * 1000.0);
    bool even = true;
    for (unsigned bite = 2; bite < bites; ++bite)
        even = even && std::llabs(std::int64_t(BiteMs(bite, bites, life)) - std::int64_t(BiteMs(bite - 1, bites, life)) -
                                  (std::int64_t(BiteMs(1, bites, life)) - std::int64_t(BiteMs(0, bites, life)))) <= 1;
    expect(even && BiteMs(1, bites, life) > first, "an even gap between bites, later bites later");
    expect(BiteMs(0, 0, life) == 0 && BiteMs(0, bites, 0) == 0, "no bites or no life, at once");

    // The queen: her pulses make her total, the first one an interval after the jar, the last at her end.
    unsigned const pulses = PeriodicStrike::Ticks(queenSeconds, pulse);
    expect(pulses > 1 && near(PeriodicStrike::TickPct(queenTotal, pulses) * pulses, queenTotal), "the pulses make the queen's total", PeriodicStrike::TickPct(queenTotal, pulses) * pulses, queenTotal);
    expect(PulseMs(0, pulse) == std::uint32_t(pulse * 1000.0 + 0.5) && PulseMs(pulses - 1, pulse) == std::uint32_t(queenSeconds * 1000.0 + 0.5),
           "the first pulse after an interval, the last at her end", PulseMs(pulses - 1, pulse), queenSeconds * 1000.0);
    expect(PulseMs(3, 0) == 0, "no interval, at once");

    // Medusa Spiders' slow chance, and the pick of an enemy.
    expect(Slows(0.0, chance) && Slows(chance - 0.01, chance) && !Slows(chance, chance) && !Slows(0.0, 0.0), "a roll under the chance slows");
    expect(PickAt(0.0, 5) == 0 && PickAt(1.0, 5) == 4 && PickAt(0.5, 0) == 0, "a roll picks among the enemies there are");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
