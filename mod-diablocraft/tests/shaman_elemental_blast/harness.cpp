// The real dc_shaman_elemental_blast.h and dc_shaman_damage_mark.h. The rune names and numbers come from argv (read
// from the sheets by test_shaman_elemental_blast.py); nothing is typed in here. Prints "cases=N" and exits 0, or names
// the first failing case and exits 1.
#include "classes/shaman/dc_shaman_damage_mark.h"
#include "classes/shaman/dc_shaman_elemental_blast.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::ElementalBlast;
namespace DamageMark = DC::Combat::Shaman::DamageMark;

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
    // argv: the five runes A to E, the buff's critical hit chance, the rune's damage bonus, Unstable Elements' share,
    // Primal Wellspring's refund, the blast's damage percent, the mark's percent and seconds.
    if (argc < 13)
        return 2;
    std::string const cycle = argv[1], echo = argv[2], unstable = argv[3], mastery = argv[4], wellspring = argv[5];
    double const crit = std::atof(argv[6]), bonus = std::atof(argv[7]), share = std::atof(argv[8]),
                 gain = std::atof(argv[9]), hit = std::atof(argv[10]), markPct = std::atof(argv[11]),
                 markSeconds = std::atof(argv[12]);

    expect(RuneOf(cycle) == Rune::PrismaticCycle && RuneOf(echo) == Rune::ElementalEcho &&
               RuneOf(unstable) == Rune::UnstableElements && RuneOf(mastery) == Rune::ElementalMastery &&
               RuneOf(wellspring) == Rune::PrimalWellspring,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Elemental Blast") == Rune::None &&
               RuneOf("Elemental Weapon") == Rune::None,
           "and nothing else is");

    // Prismatic Cycle's order is Fire, Lightning, Cold, Physical, Fire.
    expect(NextElement("fire") == "lightning" && NextElement("lightning") == "cold" &&
               NextElement("cold") == "physical" && NextElement("physical") == "fire" && !NextElement("").has_value() &&
               !NextElement("poison").has_value(),
           "the Attunement moves Fire, Lightning, Cold, Physical, Fire");

    // Elemental Echo by element.
    expect(EchoOf("fire") == Echo::Burn && EchoOf("lightning") == Echo::Arc && EchoOf("cold") == Echo::Freeze &&
               EchoOf("physical") == Echo::Knock && !EchoOf("poison").has_value(),
           "Elemental Echo adds a burn, an arc, a freeze or a knockback by element");

    // The buff: critical hit chance for every rune but Elemental Mastery, whose buff gives damage of the Attunement's
    // element instead.
    expect(CritBonus(Rune::None, crit) == crit && CritBonus(Rune::PrismaticCycle, crit) == crit &&
               CritBonus(Rune::UnstableElements, crit) == crit && CritBonus(Rune::ElementalMastery, crit) == 0 &&
               CritBonus(Rune::None, 0) == 0,
           "the buff gives critical hit chance except under Elemental Mastery");
    expect(DamageBonus(Rune::ElementalMastery, true, bonus) == bonus &&
               DamageBonus(Rune::ElementalMastery, false, bonus) == 0 && DamageBonus(Rune::None, true, bonus) == 0 &&
               DamageBonus(Rune::PrismaticCycle, true, bonus) == 0 && DamageBonus(Rune::ElementalMastery, true, 0) == 0,
           "Elemental Mastery raises hits of the Attunement's element only");

    // Unstable Elements' splash and Primal Wellspring's refund.
    expect(std::fabs(SplashPct(hit, share) - hit * share / 100.0) < 1e-9 && SplashPct(hit, share) < hit &&
               SplashPct(0, share) == 0 && SplashPct(hit, 0) == 0,
           "the splash is its share of the blast's damage");
    expect(Refund(true, false, gain) == gain && Refund(false, true, gain) == gain && Refund(true, true, gain) == gain &&
               Refund(false, false, gain) == 0 && Refund(true, false, 0) == 0,
           "Primal Wellspring refunds for a kill or an elite");

    // The element a hit deals: the seam's (the blast deals the Attunement), else the record's school.
    expect(DealtElement("fire", "lightning") == "fire" && DealtElement(nullptr, "lightning") == "lightning" && DealtElement("", "cold") == "cold" &&
               DealtElement("physical", "physical") == "physical",
           "a hit deals the element the seam names, else its record's school");

    // The buff and the shared mark hold for their seconds.
    std::uint64_t const start = 4000, ends = start + std::uint64_t(markSeconds * 1000.0);
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0), "the buff holds for its seconds");
    expect(DamageMark::Bonus(true, markPct) == markPct && DamageMark::Bonus(false, markPct) == 0 &&
               DamageMark::Bonus(true, 0) == 0,
           "a mark raises a marked enemy's hit");
    expect(DamageMark::Holds(ends - 1, ends) && !DamageMark::Holds(ends, ends) && !DamageMark::Holds(start, 0) &&
               markSeconds > 0,
           "a mark holds for its seconds");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
