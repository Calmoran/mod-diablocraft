// The real dc_shaman_purge.h, no core. Every number comes from argv (test_shaman_purge.py reads the sheet and
// combat.csv): the Maelstrom each removal pays, the burn's seconds and its tick seconds. Prints "cases=N failures=M"
// and exits 0, or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_purge.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::Purge;

static int failures = 0;
static int cases = 0;

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
    if (argc < 4)
        return 2;
    double const gain = std::atof(argv[1]), burnSeconds = std::atof(argv[2]), tick = std::atof(argv[3]);

    // The five runes by name, and nothing else.
    expect(RuneOf("Wind Shear") == Rune::WindShear && RuneOf("Greater Purge") == Rune::GreaterPurge &&
               RuneOf("Cleanse Spirit") == Rune::CleanseSpirit && RuneOf("Consuming Purge") == Rune::ConsumingPurge &&
               RuneOf("Earthen Purge") == Rune::EarthenPurge,
           "each rune by its name");
    expect(RuneOf("") == Rune::None && RuneOf("Chain Frost") == Rune::None, "the skill and a stranger are no rune");

    // Wind Shear interrupts every enemy and stuns what is not a boss, whether or not anything came off it.
    for (unsigned removed : {0u, 2u})
    {
        Effect const ordinary = EffectOf(Rune::WindShear, removed, false, false),
                     elite = EffectOf(Rune::WindShear, removed, true, false),
                     boss = EffectOf(Rune::WindShear, removed, true, true);
        expect(ordinary.interrupt && ordinary.stun && elite.interrupt && elite.stun,
               "Wind Shear interrupts and stuns an ordinary enemy and an elite", removed, 0);
        expect(boss.interrupt && !boss.stun, "and interrupts a boss without stunning it", removed, 0);
        expect(!ordinary.weaken && !ordinary.burn, "and does nothing else");
    }
    // Greater Purge weakens a purged elite, and only one: not an enemy nothing came off, not an ordinary one.
    expect(EffectOf(Rune::GreaterPurge, 1, true, false).weaken && EffectOf(Rune::GreaterPurge, 1, true, true).weaken,
           "Greater Purge weakens a purged elite or boss");
    expect(!EffectOf(Rune::GreaterPurge, 0, true, false).weaken, "not an elite nothing came off");
    expect(!EffectOf(Rune::GreaterPurge, 1, false, false).weaken, "and not an ordinary enemy");
    expect(!EffectOf(Rune::GreaterPurge, 1, true, false).interrupt &&
               !EffectOf(Rune::GreaterPurge, 1, true, false).stun,
           "Greater Purge holds nothing");
    // Consuming Purge burns an enemy that lost an effect, and no other.
    expect(EffectOf(Rune::ConsumingPurge, 1, false, false).burn && EffectOf(Rune::ConsumingPurge, 3, true, true).burn,
           "Consuming Purge burns an enemy that lost an effect");
    expect(!EffectOf(Rune::ConsumingPurge, 0, true, false).burn, "and not one that kept all of them");
    // The skill and the other two runes do nothing to an enemy beyond the hit.
    for (Rune rune : {Rune::None, Rune::CleanseSpirit, Rune::EarthenPurge})
    {
        Effect const effect = EffectOf(rune, 2, true, false);
        expect(!effect.interrupt && !effect.stun && !effect.weaken && !effect.burn,
               "the skill and its Cleanse and Earthen runes add nothing to an enemy");
    }

    // Only Consuming Purge and Greater Purge claim the skill's hit for their record.
    expect(ClaimsHit(Rune::ConsumingPurge) && ClaimsHit(Rune::GreaterPurge), "Consuming Purge and Greater Purge keep the skill's hit");
    for (Rune rune : {Rune::None, Rune::WindShear, Rune::CleanseSpirit, Rune::EarthenPurge})
        expect(!ClaimsHit(rune), "no other record is claimed");

    // The Maelstrom: each state taken off pays its share, over every enemy the shock reached.
    expect(Maelstrom(0, gain) == 0 && Maelstrom(1, gain) == gain && Maelstrom(3, gain) == 3 * gain,
           "each removal pays its share", Maelstrom(3, gain), 3 * gain);

    // The burn: the ticks of its seconds.
    unsigned const ticks = Ticks(burnSeconds, tick);
    expect(ticks > 0 && std::abs(ticks * tick - burnSeconds) < tick, "the burn's ticks fit its seconds", ticks,
           burnSeconds / tick);
    expect(Ticks(0, tick) == 0 && Ticks(burnSeconds, 0) == 0, "no seconds or no tick, no ticks");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
