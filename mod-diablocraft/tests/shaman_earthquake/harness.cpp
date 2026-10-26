// The real dc_shaman_earthquake.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_earthquake.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/shaman/dc_shaman_earthquake.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::Earthquake;

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
    // argv: the five runes A to E, the skill's damage, Thundering Earth's damage, the seconds, the tick seconds, the
    // radius of the skill and of Rolling Quake, Magma Chamber's percent, Earth Shock's extra Maelstrom, Frozen Tundra's
    // interval seconds, Thundering Earth's strikes a tick.
    if (argc < 16)
        return 2;
    std::string const after = argv[1], rolling = argv[2], magma = argv[3], tundra = argv[4], thunder = argv[5];
    double const damage = std::atof(argv[6]), thunderDamage = std::atof(argv[7]), seconds = std::atof(argv[8]),
                 tick = std::atof(argv[9]), radius = std::atof(argv[10]), rollingRadius = std::atof(argv[11]),
                 magmaPct = std::atof(argv[12]), gain = std::atof(argv[13]), interval = std::atof(argv[14]);
    std::size_t const most = std::size_t(std::atoi(argv[15]));

    expect(RuneOf(after) == Rune::Aftershock && RuneOf(rolling) == Rune::RollingQuake &&
               RuneOf(magma) == Rune::MagmaChamber && RuneOf(tundra) == Rune::FrozenTundra &&
               RuneOf(thunder) == Rune::ThunderingEarth,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Earthquake (Shaman)") == Rune::None &&
               RuneOf("Earthquake") == Rune::None,
           "and nothing else is");

    // Whose damage the ticks deal, who follows, who strikes everyone.
    expect(OwnsTickDamage(Rune::ThunderingEarth) && !OwnsTickDamage(Rune::None) && !OwnsTickDamage(Rune::Aftershock) &&
               !OwnsTickDamage(Rune::MagmaChamber),
           "only Thundering Earth states the ticks' damage");
    expect(Follows(Rune::RollingQuake) && !Follows(Rune::None) && !Follows(Rune::Aftershock) &&
               !Follows(Rune::ThunderingEarth),
           "only Rolling Quake follows the Shaman");
    expect(StrikesAll(Rune::None) && StrikesAll(Rune::FrozenTundra) && !StrikesAll(Rune::ThunderingEarth),
           "only Thundering Earth leaves some enemies alone");
    expect(Struck(Rune::None, 7, most) == 7 && Struck(Rune::ThunderingEarth, 7, most) == most &&
               Struck(Rune::ThunderingEarth, 1, most) == 1 && Struck(Rune::ThunderingEarth, 0, most) == 0,
           "a tick strikes all that stand inside, or a few of them");

    // The hit of a tick is above 0 for every rune, from the sheet's damage over its seconds.
    unsigned const ticks = DC::Combat::PeriodicStrike::Ticks(seconds, tick);
    expect(ticks >= 1, "the seconds hold at least one tick", double(ticks), 1);
    double const base = DC::Combat::PeriodicStrike::TickPct(damage, ticks),
                 thunderTick = DC::Combat::PeriodicStrike::TickPct(thunderDamage, ticks);
    expect(base > 0 && thunderTick > 0 && std::fabs(base * ticks - damage) < 1e-9 &&
               std::fabs(thunderTick * ticks - thunderDamage) < 1e-9,
           "a tick deals above 0 and the ticks add up to the sheet's damage", base, damage / ticks);

    // Inside: the area is round.
    expect(Inside(0, 0, radius - 0.1, 0, radius) && Inside(0, 0, 0, -radius, radius) &&
               !Inside(0, 0, radius + 0.1, 0, radius) && !Inside(0, 0, 0, 0, 0) &&
               Inside(10, 10, 10 + rollingRadius * 0.7, 10 + rollingRadius * 0.7, rollingRadius) &&
               !Inside(10, 10, 10 + rollingRadius * 0.8, 10 + rollingRadius * 0.8, rollingRadius),
           "an enemy inside is within the radius of the centre");
    expect(rollingRadius < radius, "Rolling Quake is smaller");

    // Frozen Tundra.
    expect(ChillSeconds(tick) == tick * 2 && ChillSeconds(0) == 0 && ChillSeconds(-1) == 0,
           "the chill lasts through the next tick");
    std::uint64_t const gap = std::uint64_t(interval * 1000.0);
    expect(FreezeDue(7000, 0, interval) && !FreezeDue(7000 + gap - 1, 7000, interval) &&
               FreezeDue(7000 + gap, 7000, interval) && !FreezeDue(7000, 0, 0),
           "a freeze comes every interval");

    // Magma Chamber and Earth Shock.
    expect(MagmaBonus(Rune::MagmaChamber, true, magmaPct) == magmaPct &&
               MagmaBonus(Rune::MagmaChamber, false, magmaPct) == 0 && MagmaBonus(Rune::None, true, magmaPct) == 0 &&
               MagmaBonus(Rune::FrozenTundra, true, magmaPct) == 0 && MagmaBonus(Rune::MagmaChamber, true, 0) == 0,
           "Magma Chamber raises Lava Burst for an enemy inside, no other rune does");
    expect(EarthShockGain(true, gain) == gain && EarthShockGain(false, gain) == 0 && EarthShockGain(true, 0) == 0 &&
               EarthShockGain(true, -1) == 0,
           "Earth Shock adds Maelstrom for a target inside the Earthquake");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
