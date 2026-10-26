// The real dc_demon_hunter_smoke_screen.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_demon_hunter_smoke_screen.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_smoke_screen.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter::SmokeScreen;

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
    // argv: the five runes A to E, then every rune's speed, Displacement's speed, Healing Vapors' Life a second, the
    // base and the Lingering Fog seconds, then the tick the tunable gives.
    if (argc < 12)
        return 2;
    std::string const powder = argv[1], fog = argv[2], vapors = argv[3], recipe = argv[4], displacement = argv[5];
    double const baseSpeed = std::atof(argv[6]), displacementSpeed = std::atof(argv[7]), regen = std::atof(argv[8]),
                 seconds = std::atof(argv[9]), fogSeconds = std::atof(argv[10]),
                 tick = std::atof(argv[11]);

    expect(RuneOf(powder) == Rune::VanishingPowder && RuneOf(fog) == Rune::LingeringFog &&
               RuneOf(vapors) == Rune::HealingVapors && RuneOf(recipe) == Rune::SpecialRecipe &&
               RuneOf(displacement) == Rune::Displacement,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {powder, fog, vapors, recipe, displacement})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The speed: Displacement states its own, every other rune the file's.
    expect(SpeedPct(RuneOf(displacement), displacementSpeed, baseSpeed) == displacementSpeed,
           "Displacement's own speed", SpeedPct(RuneOf(displacement), displacementSpeed, baseSpeed), displacementSpeed);
    for (auto const& rune : {powder, fog, vapors, recipe, std::string()})
        expect(SpeedPct(RuneOf(rune), 0.0, baseSpeed) == baseSpeed, "every other rune the base speed",
               SpeedPct(RuneOf(rune), 0.0, baseSpeed), baseSpeed);

    // Healing Vapors: the ticks of the invisibility together give the percent of the maximum Life for each second.
    double const maxLife = 10000;
    unsigned const ticks = unsigned(seconds / tick + 0.5);
    expect(std::fabs(RegenPerTick(maxLife, regen, tick) * ticks - maxLife * regen / 100.0 * seconds) < 1e-6,
           "the ticks make the Life", RegenPerTick(maxLife, regen, tick) * ticks, maxLife * regen / 100.0 * seconds);
    expect(RegenPerTick(0, regen, tick) == 0 && RegenPerTick(maxLife, 0, tick) == 0 &&
               RegenPerTick(maxLife, regen, 0) == 0,
           "no Life, no percent or no tick, nothing");

    // The cooldown is held back for the whole invisibility, Lingering Fog's longer one included.
    expect(CooldownDelayMs(seconds) == std::uint64_t(seconds * 1000.0 + 0.5), "the cooldown waits the seconds",
           double(CooldownDelayMs(seconds)), seconds * 1000.0);
    expect(CooldownDelayMs(fogSeconds) == std::uint64_t(fogSeconds * 1000.0 + 0.5) &&
               CooldownDelayMs(fogSeconds) > CooldownDelayMs(seconds),
           "and Lingering Fog's more", double(CooldownDelayMs(fogSeconds)), fogSeconds * 1000.0);
    expect(CooldownDelayMs(0) == 0 && CooldownDelayMs(-3) == 0, "no seconds, no wait");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
