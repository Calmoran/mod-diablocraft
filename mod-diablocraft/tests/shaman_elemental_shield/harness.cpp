// The real dc_shaman_elemental_shield.h, no core. Every number comes from argv (test_shaman_elemental_shield.py reads
// the sheet): charges, the damage a hit loses in percent, seconds between strikes back, Stoneskin's charges, its absorb
// percent of maximum Life and seconds, Lightning Shield's chance in percent and most charges, the burn's per-second
// percent and its tick seconds. Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_elemental_shield.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::ElementalShield;

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

static Shield Worn(unsigned charges, std::uint64_t until, Rune rune = Rune::None)
{
    Shield shield;
    shield.spellId = 86310;
    shield.rune = rune;
    shield.charges = charges;
    shield.until = until;
    return shield;
}

int main(int argc, char** argv)
{
    if (argc < 11)
        return 2;
    unsigned const charges = unsigned(std::atof(argv[1]));
    double const reduction = std::atof(argv[2]);
    std::uint64_t const interval = std::uint64_t(std::atof(argv[3]) * 1000.0);
    unsigned const stoneCharges = unsigned(std::atof(argv[4]));
    double const absorbPct = std::atof(argv[5]), absorbSeconds = std::atof(argv[6]), chance = std::atof(argv[7]);
    unsigned const most = unsigned(std::atof(argv[8]));
    double const burnPerSecond = std::atof(argv[9]), tick = std::atof(argv[10]);

    // The five runes by name, and nothing else.
    expect(RuneOf("Lightning Shield") == Rune::LightningShield && RuneOf("Stoneskin") == Rune::Stoneskin &&
               RuneOf("Water Shield") == Rune::WaterShield && RuneOf("Flame Shield") == Rune::FlameShield &&
               RuneOf("Totemic Ward") == Rune::TotemicWard,
           "each rune by its name");
    expect(RuneOf("") == Rune::None && RuneOf("Astral Shift") == Rune::None, "the skill and a stranger are no rune");
    expect(stoneCharges > charges && most > charges,
           "Stoneskin has more charges than the skill, and Lightning Shield may grow past them");

    // A hit spends a charge and lowers the damage by the percent.
    std::uint64_t const start = 1000, end = start + 30000;
    Shield shield = Worn(charges, end);
    expect(Active(shield, start), "a worn shield is active");
    Spent first = Hit(shield, start, interval);
    expect(first.used && first.strike && !first.broke && shield.charges == charges - 1,
           "a hit spends one charge and strikes back", shield.charges, charges - 1);
    expect(Lowered(100, reduction) == 100 - reduction, "the hit is lowered by the percent", Lowered(100, reduction),
           100 - reduction);
    expect(Lowered(0, reduction) == 0, "no damage stays none");

    // At most one strike back every interval; the charge is spent all the same.
    Spent soon = Hit(shield, start + interval - 1, interval);
    expect(soon.used && !soon.strike && shield.charges == charges - 2,
           "a second hit inside the interval spends a charge and does not strike", shield.charges, charges - 2);
    Spent later = Hit(shield, start + interval, interval);
    expect(later.used && later.strike, "a hit one interval after the last strike strikes again");

    // The last charge breaks the shield.
    Shield last = Worn(1, end);
    Spent broke = Hit(last, start, interval);
    expect(broke.used && broke.broke && last.charges == 0 && !Active(last, start), "the last charge breaks it");
    Spent none = Hit(last, start + 5000, interval);
    expect(!none.used && !none.strike && !none.broke, "a broken shield spends nothing");

    // Time: gone from the moment it ends.
    Shield timed = Worn(charges, end);
    expect(Active(timed, end - 1) && !Active(timed, end), "gone at its end");
    expect(!Hit(timed, end, interval).used, "an ended shield spends nothing");
    expect(!Active(Shield{}, start), "no shield at all is no shield");

    // Charges added: up to the most, never to a broken or ended shield.
    Shield grown = Worn(charges, end, Rune::LightningShield);
    expect(AddCharge(grown, start, most) && grown.charges == charges + 1, "a charge is added", grown.charges,
           charges + 1);
    grown.charges = most;
    expect(!AddCharge(grown, start, most) && grown.charges == most, "and not past the most", grown.charges, most);
    Shield dead = Worn(0, end);
    expect(!AddCharge(dead, start, most), "a broken shield gains nothing");
    Shield over = Worn(charges, end);
    expect(!AddCharge(over, end + 1, most), "an ended shield gains nothing");

    // The roll: a roll under the chance adds.
    expect(Rolled(chance - 0.001, chance) && !Rolled(chance, chance) && !Rolled(100, chance) && Rolled(0, chance),
           "a roll under the chance adds");

    // Paying waits for the hit to land: a swing that was mitigated and never landed leaves its note unclaimed and the shield whole.
    Pending note;
    Note(note, 7, 5000, true);
    Shield missed = Worn(charges, end);
    expect(missed.charges == charges, "a noted swing that never lands leaves every charge", missed.charges, charges);
    expect(!Claim(note, 8, 5000), "another attacker's hit does not pay the note");
    expect(!Claim(note, 7, 5001), "a hit at another time does not pay it");
    auto const paid = Claim(note, 7, 5000);
    expect(paid && paid->charge, "the hit it was noted for pays it");
    expect(!Claim(note, 7, 5000), "and it is paid once");
    Pending empty;
    expect(!Claim(empty, 0, 0), "no note, nothing to pay");
    Note(note, 0, 5000, false);
    expect(Claim(note, 0, 5000).has_value(), "a hit with no attacker is noted and paid as one");

    // The burn: the per-second percent of one tick, the ticks adding back to a second.
    expect(std::abs(TickPct(burnPerSecond, tick) / tick - burnPerSecond) < 1e-9,
           "a burn tick is the per-second percent of a tick", TickPct(burnPerSecond, tick), burnPerSecond * tick);

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
