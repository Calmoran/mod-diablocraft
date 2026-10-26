// The real dc_shaman_flame_shock.h and dc_shaman_burning.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_flame_shock.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/shaman/dc_shaman_burning.h"
#include "classes/shaman/dc_shaman_flame_shock.h"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::FlameShock;
namespace Burning = DC::Combat::Shaman::Burning;

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
    // argv: the five runes A to E, Frost Shock's extra Maelstrom, Primal Shock's percent and seconds, the burn's seconds.
    if (argc < 10)
        return 2;
    std::string const lava = argv[1], frost = argv[2], earth = argv[3], stat = argv[4], primal = argv[5];
    double const chilledGain = std::atof(argv[6]), markPct = std::atof(argv[7]), markSeconds = std::atof(argv[8]), burnSeconds = std::atof(argv[9]);

    expect(RuneOf(lava) == Rune::LavaShock && RuneOf(frost) == Rune::FrostShock && RuneOf(earth) == Rune::EarthShock &&
               RuneOf(stat) == Rune::StaticShock && RuneOf(primal) == Rune::PrimalShock,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Flame Shock") == Rune::None && RuneOf("Lightning Bolt") == Rune::None, "and nothing else is");

    // Where the cast's own hit takes its damage from.
    expect(HitOf(Rune::None) == HitFrom::Skill && HitOf(Rune::LavaShock) == HitFrom::Skill, "the base and Lava Shock hit for the skill's number");
    expect(HitOf(Rune::FrostShock) == HitFrom::RuneOnly && HitOf(Rune::EarthShock) == HitFrom::RuneOnly, "Frost and Earth Shock hit for their own");
    expect(HitOf(Rune::StaticShock) == HitFrom::RuneHit && HitOf(Rune::PrimalShock) == HitFrom::RuneHit, "Static and Primal Shock hit for their hit number");

    // The burn: the base and Lava Shock leave it, the other runes replace it.
    expect(Burns(Rune::None) && Burns(Rune::LavaShock) && !Burns(Rune::FrostShock) && !Burns(Rune::EarthShock) && !Burns(Rune::StaticShock) &&
               !Burns(Rune::PrimalShock),
           "only the base and Lava Shock leave the skill's burn");
    expect(Erupts(Rune::LavaShock, true) && !Erupts(Rune::LavaShock, false) && !Erupts(Rune::None, true) && !Erupts(Rune::PrimalShock, true),
           "Lava Shock erupts only on a Burning target");

    // Primal Shock's small effect follows the Attunement.
    expect(SmallOf("fire") == Small::Burn && SmallOf("cold") == Small::Chill && SmallOf("physical") == Small::Mark && SmallOf("lightning") == Small::Arc,
           "each Attunement adds its own small effect");
    expect(!SmallOf("").has_value() && !SmallOf("poison").has_value(), "and no other element adds one");

    // Frost Shock's extra Maelstrom.
    expect(ChilledGain(true, chilledGain) == chilledGain && ChilledGain(false, chilledGain) == 0 && ChilledGain(true, 0) == 0 && ChilledGain(true, -1) == 0,
           "Frost Shock adds Maelstrom against a chilled enemy only");

    // Primal Shock's mark.
    expect(MarkBonus(true, markPct) == markPct && MarkBonus(false, markPct) == 0 && MarkBonus(true, 0) == 0, "the mark raises the hit of a marked enemy only");
    std::uint64_t const start = 5000, ends = start + std::uint64_t(markSeconds * 1000.0);
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0) && markSeconds > 0, "the mark holds for its seconds");

    // Burning: a second burn extends it and never shortens it.
    std::uint64_t const first = Burning::Until(0, start, burnSeconds);
    expect(first == start + std::uint64_t(burnSeconds * 1000.0), "a burn lasts its seconds", double(first), double(start));
    expect(Burning::Until(first, start + 1000, burnSeconds) == start + 1000 + std::uint64_t(burnSeconds * 1000.0), "a later burn extends it");
    expect(Burning::Until(first, start, 1.0) == first, "a shorter burn does not shorten it");
    expect(Burning::Until(first, start, 0) == first && Burning::Until(0, start, -3) == 0, "no seconds, no burn");
    expect(Burning::Holds(first - 1, first) && !Burning::Holds(first, first) && !Burning::Holds(start, 0), "an enemy burns until the burn ends");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
