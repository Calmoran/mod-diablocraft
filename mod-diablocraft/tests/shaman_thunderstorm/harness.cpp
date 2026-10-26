// The real dc_shaman_thunderstorm.h, no core. Every number comes from argv (test_shaman_thunderstorm.py reads the
// sheets and combat.csv): knockback yards, Gale Force's factor, its stun seconds, Frost Storm's freeze seconds, the
// storm's tick seconds, the storm's per-second percent and seconds, the ring's tick seconds, per-second percent and
// seconds, Sandstorm's miss percent and blind seconds. Prints "cases=N failures=M" and exits 0, or names each failing
// case and exits 1.
#include "classes/shaman/dc_shaman_thunderstorm.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::Thunderstorm;

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
    if (argc < 13)
        return 2;
    double const knock = std::atof(argv[1]), factor = std::atof(argv[2]), stun = std::atof(argv[3]),
                 freeze = std::atof(argv[4]), stormTick = std::atof(argv[5]), stormPct = std::atof(argv[6]),
                 stormSeconds = std::atof(argv[7]), ringTick = std::atof(argv[8]), ringPct = std::atof(argv[9]),
                 ringSeconds = std::atof(argv[10]), missPct = std::atof(argv[11]), blindSeconds = std::atof(argv[12]);

    // The five runes by name, and nothing else.
    expect(RuneOf("Eye of the Storm") == Rune::EyeOfTheStorm && RuneOf("Gale Force") == Rune::GaleForce &&
               RuneOf("Frost Storm") == Rune::FrostStorm && RuneOf("Sandstorm") == Rune::Sandstorm &&
               RuneOf("Volcanic Gale") == Rune::VolcanicGale,
           "each rune by its name");
    expect(RuneOf("") == Rune::None && RuneOf("Chain Frost") == Rune::None, "the skill and a stranger are no rune");

    // The skill and Volcanic Gale knock back and keep it; nothing else is added.
    for (Rune rune : {Rune::None, Rune::VolcanicGale})
    {
        Hold const hold = HoldOf(rune, knock, factor, stun, freeze);
        expect(hold.knockYards == knock && hold.stunSeconds == 0 && hold.freezeSeconds == 0 && !hold.blind,
               "the plain thunderclap only knocks back", hold.knockYards, knock);
    }
    // Gale Force: the knockback doubled and a stun.
    Hold const gale = HoldOf(Rune::GaleForce, knock, factor, stun, freeze);
    expect(gale.knockYards == knock * factor && factor == 2 && gale.stunSeconds == stun && gale.freezeSeconds == 0 &&
               !gale.blind,
           "Gale Force doubles the knockback and stuns", gale.knockYards, knock * factor);
    // Frost Storm: frozen in place of the knockback.
    Hold const frost = HoldOf(Rune::FrostStorm, knock, factor, stun, freeze);
    expect(frost.knockYards == 0 && frost.freezeSeconds == freeze && frost.stunSeconds == 0 && !frost.blind,
           "Frost Storm freezes in place of the knockback", frost.knockYards, frost.freezeSeconds);
    // Eye of the Storm: no knockback, nothing held.
    Hold const eye = HoldOf(Rune::EyeOfTheStorm, knock, factor, stun, freeze);
    expect(eye.knockYards == 0 && eye.stunSeconds == 0 && eye.freezeSeconds == 0 && !eye.blind,
           "Eye of the Storm trades the knockback away");
    // Sandstorm: the knockback kept, an ordinary enemy blinded, an elite or a boss only slowed.
    Hold const sand = HoldOf(Rune::Sandstorm, knock, factor, stun, freeze);
    expect(sand.knockYards == knock && sand.blind && Blinds(sand, false) && !Blinds(sand, true),
           "Sandstorm blinds an ordinary enemy and spares an elite the blind");
    expect(!Blinds(gale, false) && !Blinds(frost, false) && !Blinds(eye, false), "no other rune blinds");

    // The storm and the ring: "N% weapon damage per second" in ticks, the ticks adding back to the seconds' worth.
    unsigned const stormTicks = Ticks(stormSeconds, stormTick);
    expect(stormTicks > 0 && stormTicks * stormTick <= stormSeconds + 1e-9, "the storm's ticks fit its seconds",
           stormTicks, stormSeconds);
    expect(std::abs(stormTicks * TickPct(stormPct, stormTick) - stormPct * stormTicks * stormTick) < 1e-9,
           "a storm tick is the per-second percent of a tick", TickPct(stormPct, stormTick), stormPct);
    expect(TickPct(stormPct, 1.0) == stormPct, "at one tick a second a tick is the percent itself");
    unsigned const ringTicks = Ticks(ringSeconds, ringTick);
    expect(ringTicks == unsigned(ringSeconds / ringTick + 1e-9), "the ring ticks twice a second for its seconds",
           ringTicks, ringSeconds / ringTick);
    expect(std::abs(ringTicks * TickPct(ringPct, ringTick) - ringPct * ringSeconds) < 1e-9,
           "the ring deals its per-second percent over its seconds", ringTicks * TickPct(ringPct, ringTick),
           ringPct * ringSeconds);
    expect(Ticks(0, ringTick) == 0 && Ticks(4, 0) == 0, "no seconds or no tick length, no ticks");

    // The blind: a miss chance for its seconds, nothing for another enemy, nothing once it is over, and a new blind
    // replaces.
    Blind blind;
    std::uint64_t const start = 5000, end = start + std::uint64_t(blindSeconds * 1000);
    blind.Set(7, start, end, missPct);
    expect(blind.Chance(7, start) == missPct && blind.Chance(7, end - 1) == missPct,
           "the blinded enemy misses its percent", blind.Chance(7, start), missPct);
    expect(blind.Chance(8, start) == 0, "another enemy misses as usual");
    expect(blind.Chance(7, end) == 0 && blind.Chance(7, end + 1) == 0, "and sees again at the end",
           blind.Chance(7, end), 0);
    blind.Set(7, end, end + 5000, missPct / 2);
    expect(blind.Chance(7, end + 1) == missPct / 2, "a second blind takes the place of the first",
           blind.Chance(7, end + 1), missPct / 2);

    // An enemy that dies blind does not stay: the next blind sweeps the entries whose time is up.
    Blind swept;
    swept.Set(1, start, end, missPct);
    swept.Set(2, start, end, missPct);
    expect(swept.Size() == 2, "two blinded enemies are held", double(swept.Size()), 2);
    swept.Set(3, end + 1, end + 5000, missPct);
    expect(swept.Size() == 1 && swept.Chance(3, end + 2) == missPct, "a later blind sweeps the ones whose time is up", double(swept.Size()), 1);

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
