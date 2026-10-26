// The real dc_shaman_lava_burst.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_lava_burst.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/shaman/dc_shaman_lava_burst.h"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::LavaBurst;

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
    // argv: the five runes A to E and the number of Volcanic Lightning's strikes.
    if (argc < 7)
        return 2;
    std::string const path = argv[1], pyro = argv[2], obsidian = argv[3], steam = argv[4], volcanic = argv[5];
    std::size_t const strikes = std::size_t(std::atoi(argv[6]));

    expect(RuneOf(path) == Rune::PathOfFlames && RuneOf(pyro) == Rune::Pyroclasm &&
               RuneOf(obsidian) == Rune::ObsidianBurst && RuneOf(steam) == Rune::SteamBurst &&
               RuneOf(volcanic) == Rune::VolcanicLightning,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Lava Burst") == Rune::None && RuneOf("Lightning Bolt") == Rune::None,
           "and nothing else is");

    // Only Obsidian Burst's own damage is its hit.
    expect(HitIsRunes(Rune::ObsidianBurst) && !HitIsRunes(Rune::None) && !HitIsRunes(Rune::PathOfFlames) &&
               !HitIsRunes(Rune::Pyroclasm) && !HitIsRunes(Rune::SteamBurst) && !HitIsRunes(Rune::VolcanicLightning),
           "only Obsidian Burst's own damage is the lava's hit");

    // The flat bonus: a Burning enemy, a chilled one for Steam Burst only, never for Obsidian Burst.
    expect(BonusApplies(Rune::None, true, false) && BonusApplies(Rune::PathOfFlames, true, false) &&
               BonusApplies(Rune::Pyroclasm, true, true) && BonusApplies(Rune::VolcanicLightning, true, false) &&
               BonusApplies(Rune::SteamBurst, true, false),
           "a Burning enemy takes the bonus");
    expect(!BonusApplies(Rune::None, false, false) && !BonusApplies(Rune::PathOfFlames, false, false) &&
               !BonusApplies(Rune::Pyroclasm, false, true),
           "and an enemy that is not Burning does not, chilled or not");
    expect(BonusApplies(Rune::SteamBurst, false, true) && !BonusApplies(Rune::SteamBurst, false, false),
           "Steam Burst counts a chilled enemy");
    expect(!BonusApplies(Rune::ObsidianBurst, true, true) && !BonusApplies(Rune::ObsidianBurst, true, false),
           "Obsidian Burst's damage replaces the bonus");

    // Path of Flames spreads from a Burning target only.
    expect(Spreads(Rune::PathOfFlames, true) && !Spreads(Rune::PathOfFlames, false) && !Spreads(Rune::None, true) &&
               !Spreads(Rune::Pyroclasm, true),
           "Path of Flames spreads a burn from a Burning target");

    // Volcanic Lightning's pick.
    expect(Pick(0.0, 4) == 0u && Pick(0.999, 4) == 3u && Pick(1.0, 4) == 3u && Pick(0.5, 4) == 2u &&
               Pick(0.3, 1) == 0u && !Pick(0.5, 0).has_value() && Pick(-1.0, 4) == 0u,
           "a strike picks one of the enemies near, at random");
    expect(strikes >= 1, "Volcanic Lightning strikes at least once");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
