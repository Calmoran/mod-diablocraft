// The real dc_shaman_lightning_bolt.h. The rune names and numbers come from argv (read from the sheets by test_shaman_lightning_bolt.py);
// nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/shaman/dc_shaman_lightning_bolt.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::LightningBolt;

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
    // argv: the five runes A to E, Overload's chance percent, Hailstone's extra Maelstrom, Earthen Spike's percent and seconds,
    // Stormcaller's extra Maelstrom, and the runes whose record the loader would give no hit (comma-separated; empty for the skill).
    if (argc < 12)
        return 2;
    std::string const overload = argv[1], lava = argv[2], hail = argv[3], spike = argv[4], storm = argv[5];
    double const chance = std::atof(argv[6]), chilledGain = std::atof(argv[7]), markPct = std::atof(argv[8]), markSeconds = std::atof(argv[9]),
                 critGain = std::atof(argv[10]);

    expect(RuneOf(overload) == Rune::Overload && RuneOf(lava) == Rune::LavaBeam && RuneOf(hail) == Rune::Hailstone &&
               RuneOf(spike) == Rune::EarthenSpike && RuneOf(storm) == Rune::Stormcaller,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Lightning Bolt") == Rune::None && RuneOf("Chain Lightning") == Rune::None, "and nothing else is");

    // Overload comes up below its percent.
    expect(Overloads(0.0, chance) && Overloads(chance / 100.0 - 0.001, chance) && !Overloads(chance / 100.0, chance) && !Overloads(0.99, chance) &&
               !Overloads(0.0, 0) && !Overloads(0.0, -5),
           "an Overload comes up below its chance");

    // The Maelstrom the runes add.
    expect(ChilledGain(true, chilledGain) == chilledGain && ChilledGain(false, chilledGain) == 0 && ChilledGain(true, 0) == 0 && ChilledGain(true, -2) == 0,
           "Hailstone adds Maelstrom against a chilled enemy only");
    expect(CriticalGain(true, critGain) == critGain && CriticalGain(false, critGain) == 0 && CriticalGain(true, 0) == 0, "Stormcaller adds Maelstrom on a critical hit only");

    // The mark adds its percent to a Physical hit on a marked enemy.
    expect(MarkBonus(true, true, markPct) == markPct && MarkBonus(false, true, markPct) == 0 && MarkBonus(true, false, markPct) == 0 && MarkBonus(true, true, 0) == 0,
           "the mark raises a Physical hit on the marked enemy");
    std::uint64_t const start = 5000, ends = start + std::uint64_t(markSeconds * 1000.0);
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0) && markSeconds > 0, "the mark holds for its seconds");

    // Every record the loader would give no hit of its own (it states a duration) is claimed by the skill.
    std::string waiting = argv[11];
    int claimed = 0;
    for (std::size_t from = 0; from <= waiting.size();)
    {
        std::size_t to = waiting.find(',', from);
        if (to == std::string::npos)
            to = waiting.size();
        std::string const name = waiting.substr(from, to - from);
        expect(ClaimsHit(RuneOf(name)), name.c_str());
        ++claimed;
        from = to + 1;
    }
    expect(claimed >= 1, "at least one record waits");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
