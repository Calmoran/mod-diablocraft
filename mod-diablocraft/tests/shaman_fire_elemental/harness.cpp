// The real dc_shaman_fire_elemental.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_fire_elemental.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/shaman/dc_shaman_fire_elemental.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::FireElemental;

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
    // argv: the five runes A to E, Primal Fire Elemental's seconds, the skill's seconds, Magma Elemental's own seconds,
    // the aura's and the echo's damage percent, Storm Elemental's share, Water Elemental's Life percent, the tick
    // seconds, the radius of the aura.
    if (argc < 14)
        return 2;
    std::string const primal = argv[1], meteor = argv[2], storm = argv[3], water = argv[4], magma = argv[5];
    double const primalSeconds = std::atof(argv[6]), baseSeconds = std::atof(argv[7]),
                 magmaSeconds = std::atof(argv[8]), aura = std::atof(argv[9]), echo = std::atof(argv[10]),
                 share = std::atof(argv[11]), heal = std::atof(argv[12]), tick = std::atof(argv[13]);

    expect(RuneOf(primal) == Rune::PrimalFireElemental && RuneOf(meteor) == Rune::MeteorCall &&
               RuneOf(storm) == Rune::StormElemental && RuneOf(water) == Rune::WaterElemental &&
               RuneOf(magma) == Rune::MagmaElemental,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Fire Elemental") == Rune::None &&
               RuneOf("Earth Elemental") == Rune::None,
           "and nothing else is");

    // How long it lasts.
    expect(Lifetime(Rune::PrimalFireElemental, primalSeconds, baseSeconds) == primalSeconds &&
               primalSeconds > baseSeconds,
           "Primal Fire Elemental lasts longer");
    expect(Lifetime(Rune::None, 0, baseSeconds) == baseSeconds &&
               Lifetime(Rune::MagmaElemental, magmaSeconds, baseSeconds) == baseSeconds &&
               Lifetime(Rune::MeteorCall, 99, baseSeconds) == baseSeconds,
           "every other rune lasts the skill's seconds, Magma Elemental's own seconds being the knock down's");

    // What a tick and an echo deal: above 0, and the ticks of a second add up to the sheet's per-second number.
    double const perTick = AuraPerTick(aura, tick);
    expect(perTick > 0 && std::fabs(perTick / tick - aura) < 1e-9 && AuraPerTick(0, tick) == 0 &&
               AuraPerTick(aura, 0) == 0,
           "a tick of the aura deals above 0 and adds up per second");
    expect(echo > 0 && std::fabs(ChainedPct(echo, share) - echo * share / 100.0) < 1e-9 &&
               ChainedPct(echo, share) < echo && ChainedPct(0, share) == 0 && ChainedPct(echo, 0) == 0,
           "a chained echo is its share of the echo");
    expect(std::fabs(HealPerTick(1000, heal, tick) - 1000 * heal / 100.0 * tick) < 1e-9 &&
               HealPerTick(0, heal, tick) == 0 && HealPerTick(1000, 0, tick) == 0 && HealPerTick(1000, heal, 0) == 0,
           "Water Elemental heals its percent of the maximum Life per second");
    // The same at a tick of half the length: the second still adds up.
    expect(std::fabs(AuraPerTick(aura, 0.5) * 2 - aura) < 1e-9 && std::fabs(HealPerTick(1000, heal, 0.5) * 2 - 1000 * heal / 100.0) < 1e-9,
           "and a shorter tick deals less of the second");
    expect(ChillSeconds(tick) == tick * 2 && ChillSeconds(0) == 0 && ChillSeconds(-1) == 0,
           "the chill lasts through the next tick");

    // Which casts it echoes.
    expect(Echoes("Secondary", true) && !Echoes("Secondary", false) && !Echoes("Primary", true) &&
               !Echoes("Primal", true) && !Echoes("", true),
           "only a Secondary cast is echoed, and only while it stands");

    std::uint64_t const start = 3000, ends = start + std::uint64_t(baseSeconds * 1000.0);
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0), "it stands until its seconds are over");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
