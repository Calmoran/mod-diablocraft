// The real dc_necromancer_devour_math.h and the shared dc_corpses_math.h. The rune names and numbers come from argv
// (read from the sheets by test_necromancer_devour.py); the corpse cap and lifetime, blank until the designer answers, are set
// here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_devour_math.h"
#include "combat/dc_corpses_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::Devour;
using DC::Combat::Corpses::Pile;
using DC::Combat::Corpses::Spot;

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
    // argv: the reach, the Essence of a corpse, Cannibalize's heal, the aura's radius and share of the pickup radius,
    // then the five runes A to E
    if (argc < 11)
        return 2;
    double const reach = std::atof(argv[1]), perCorpse = std::atof(argv[2]), heal = std::atof(argv[3]),
                 auraRadius = std::atof(argv[4]), share = std::atof(argv[5]);
    std::string const cannibalize = argv[6], ruthless = argv[7], voracious = argv[8], aura = argv[9],
                      satiated = argv[10];

    expect(RuneOf(cannibalize) == Rune::Cannibalize && RuneOf(ruthless) == Rune::Ruthless &&
               RuneOf(voracious) == Rune::Voracious && RuneOf(aura) == Rune::DevouringAura &&
               RuneOf(satiated) == Rune::Satiated,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {cannibalize, ruthless, voracious, aura, satiated})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Devour") == Rune::None, "the base skill and a stranger are no rune");

    // The Essence: for each one consumed.
    expect(near(EssenceOf(perCorpse, 4), perCorpse * 4), "four corpses, four shares", EssenceOf(perCorpse, 4),
           perCorpse * 4);
    expect(near(EssenceOf(perCorpse, 0), 0) && near(EssenceOf(0, 4), 0) && near(EssenceOf(-2, 4), 0),
           "none consumed or none stated, none");

    // Cannibalize: a share of maximum Life for each corpse.
    expect(near(HealOf(10000, heal, 3), 10000 * heal / 100 * 3), "three corpses, three shares", HealOf(10000, heal, 3),
           10000 * heal / 100 * 3);
    expect(near(HealOf(10000, heal, 0), 0) && near(HealOf(0, heal, 3), 0) && near(HealOf(10000, 0, 3), 0),
           "no corpse, no Life or no percent heals nothing");

    // The aura's radius: its own, and a share of the gold pickup radius.
    expect(near(AuraRadius(auraRadius, share, 10, 0), auraRadius + 10 * share / 100),
           "the radius and a share of the pickup radius", AuraRadius(auraRadius, share, 10, 0),
           auraRadius + 10 * share / 100);
    expect(near(AuraRadius(auraRadius, share, 0, 0), auraRadius) && near(AuraRadius(auraRadius, 0, 10, 0), auraRadius),
           "no pickup radius or no share adds nothing");
    expect(near(AuraRadius(auraRadius, -50, 10, 0), auraRadius) && near(AuraRadius(auraRadius, share, -10, 0), auraRadius),
           "a negative share or radius adds nothing");

    // The increase from the pickup radius is held to the power's most.
    expect(near(AuraRadius(auraRadius, share, 100, 20), auraRadius + 20), "the increase is held to the most", AuraRadius(auraRadius, share, 100, 20),
           auraRadius + 20);
    expect(near(AuraRadius(auraRadius, share, 10, 20), auraRadius + 10 * share / 100), "a small increase is left alone");

    // Whether the cast may begin.
    expect(CanDevour(Rune::None, 1, 0) && CanDevour(Rune::Cannibalize, 3, 5), "a corpse is enough");
    expect(!CanDevour(Rune::None, 0, 4) && !CanDevour(Rune::Voracious, 0, 4),
           "minions alone are not, but for Ruthless");
    expect(CanDevour(Rune::Ruthless, 0, 4), "Ruthless may consume minions alone");
    expect(!CanDevour(Rune::Ruthless, 0, 0), "nothing to consume, no cast");
    expect(TogglesAnAura(Rune::DevouringAura) && !TogglesAnAura(Rune::None) && !TogglesAnAura(Rune::Ruthless),
           "only the aura rune is an aura");

    // The aura's clock.
    double clock = 0;
    expect(PulsesDue(clock, 400, 0.5) == 0 && near(clock, 400), "not yet a pulse keeps the time");
    expect(PulsesDue(clock, 150, 0.5) == 1 && near(clock, 50), "one pulse, the rest kept", clock, 50);
    clock = 0;
    expect(PulsesDue(clock, 1600, 0.5) == 3 && near(clock, 100), "three pulses in a long update", clock, 100);
    clock = 0;
    expect(PulsesDue(clock, 500, 0.5) == 1 && near(clock, 0), "a pulse is due on the moment");
    clock = 70;
    expect(PulsesDue(clock, 100, 0) == 0 && near(clock, 0), "no pulse length, none");

    // The shared pile with the cap and lifetime set here: a cast takes every corpse within the reach.
    Pile pile;
    std::uint64_t const lifetime = 60000;
    for (int i = 0; i < 12; ++i)
        pile.Leave(Spot{float(i * 3), 0, 0, 0}, 1000 + i, 30, lifetime);
    pile.Leave(Spot{float(reach) + 4, 0, 0, 0}, 1100, 30, lifetime);
    auto const all = pile.Take(0, 0, float(reach), std::numeric_limits<std::size_t>::max(), 2000, lifetime);
    expect(all.size() == 12, "every corpse within the reach goes", double(all.size()), 12);
    expect(pile.Size() == 1, "the one beyond stays", double(pile.Size()), 1);
    expect(near(EssenceOf(perCorpse, all.size()), perCorpse * 12), "their Essence is the share for each",
           EssenceOf(perCorpse, all.size()), perCorpse * 12);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
