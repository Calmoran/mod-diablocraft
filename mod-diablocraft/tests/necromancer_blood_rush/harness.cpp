// The real dc_necromancer_blood_rush_math.h and dc_charge_store.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_necromancer_blood_rush.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/necromancer/dc_necromancer_blood_rush_math.h"
#include "combat/dc_charge_store.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::BloodRush;
using DC::Combat::ChargeStore;

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
    // argv: the five runes A to E; the Life cost, Metabolism's; Transfusion's heal and collision radius; Metabolism's charges and recharge seconds
    if (argc < 12)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const base = std::atof(argv[6]), doubled = std::atof(argv[7]), heal = std::atof(argv[8]), radius = std::atof(argv[9]);
    unsigned const cap = unsigned(std::atoi(argv[10]));
    std::uint64_t const period = std::uint64_t(std::atof(argv[11]) * 1000);

    expect(RuneOf(names[0]) == Rune::Transfusion && RuneOf(names[1]) == Rune::Hemostasis && RuneOf(names[2]) == Rune::Metabolism &&
               RuneOf(names[3]) == Rune::Potency && RuneOf(names[4]) == Rune::Molting,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Blood Rush") == Rune::None && RuneOf("molting") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // The Life the cast costs.
    expect(near(LifeCostPct(Rune::None, base, doubled), base) && near(LifeCostPct(Rune::Potency, base, doubled), base) &&
               near(LifeCostPct(Rune::Transfusion, base, doubled), base) && near(LifeCostPct(Rune::Molting, base, doubled), base),
           "the skill and most runes cost the base");
    expect(LifeCostPct(Rune::Hemostasis, base, doubled) == 0.0, "Hemostasis removes the cost");
    expect(near(LifeCostPct(Rune::Metabolism, base, doubled), doubled) && near(doubled, 2 * base), "Metabolism doubles the cost", doubled, 2 * base);
    expect(LifeCostPct(Rune::None, -3, doubled) == 0.0, "a negative cost costs nothing");

    // The enemies passed through: within the radius of the segment of the rush.
    expect(PassedThrough(0, 0, 40, 0, 20, 0, radius), "an enemy on the way is passed");
    expect(PassedThrough(0, 0, 40, 0, 20, radius, radius) && !PassedThrough(0, 0, 40, 0, 20, radius + 0.01, radius), "the edge of the radius counts, past it does not");
    expect(PassedThrough(0, 0, 40, 0, 40 + radius, 0, radius) && !PassedThrough(0, 0, 40, 0, 40 + radius + 0.01, 0, radius),
           "the end of the rush is measured from the end point");
    expect(PassedThrough(0, 0, 40, 0, -radius, 0, radius) && !PassedThrough(0, 0, 40, 0, -radius - 0.01, 0, radius),
           "and the start from the start point");
    expect(PassedThrough(0, 0, 0, 40, 0, 20, radius) && !PassedThrough(0, 0, 0, 40, 30, 20, radius), "the way runs whichever direction the rush does");
    expect(PassedThrough(3, 3, 3, 3, 3, 3, radius) && !PassedThrough(3, 3, 3, 3, 3 + radius + 1, 3, radius), "a rush of no length passes what is within the radius of it");
    expect(near(TransfusionHeal(100000, heal, 3), 3 * 100000 * heal / 100.0), "each enemy passed heals its share", TransfusionHeal(100000, heal, 3),
           3 * 100000 * heal / 100.0);
    expect(TransfusionHeal(100000, heal, 0) == 0.0 && TransfusionHeal(0, heal, 3) == 0.0 && TransfusionHeal(100000, 0, 3) == 0.0 &&
               TransfusionHeal(100000, -2, 3) == 0.0,
           "no enemy, no Life or no percent: no heal");

    // Metabolism's charges: full at first, the last spent holds the button, one lands each period.
    ChargeStore store;
    std::uint64_t wait = 0;
    for (unsigned i = 0; i < cap; ++i)
        wait = store.Spend(0, cap, period);
    expect(wait == period && store.count == 0, "the last charge spent holds the button for the recharge", double(wait), double(period));
    expect(store.Refill(period, cap, period) == 1 && store.Refill(period * 2, cap, period) == 2, "a charge lands each period");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
