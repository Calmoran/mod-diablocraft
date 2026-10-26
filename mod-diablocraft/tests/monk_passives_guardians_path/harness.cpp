// diablocraft-m6v00 (Monk 2.4.2): the real dc_monk_passives_guardians_path.h. Every number comes from argv (the sheets' and the
// numeric rules', read by test_monk_passives_guardians_path.py); nothing is typed in here. Prints "cases=N" and exits 0, or
// names the failing cases and exits 1.
#include "classes/monk/dc_monk_passives_guardians_path.h"
#include "combat/dc_damage_buckets.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Passives242;

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
    // argv: Guardian's Path dodge %, its Spirit generation %, Determination per enemy %, its maximum %, Relentless
    // Assault %, Beacon of Ytar %, Alacrity %, the attack speed cap
    if (argc < 9)
        return 2;
    double const dodge = std::atof(argv[1]), regen = std::atof(argv[2]), per = std::atof(argv[3]),
                 max = std::atof(argv[4]), relentless = std::atof(argv[5]), beacon = std::atof(argv[6]),
                 alacrity = std::atof(argv[7]), cap = std::atof(argv[8]);

    // The Guardian's Path: dodge only while dual wielding; Spirit only with a two-hander.
    expect(GuardianDodge(true, dodge) == dodge, "dual wielding dodges", GuardianDodge(true, dodge), dodge);
    expect(GuardianDodge(false, dodge) == 0, "one weapon, no dodge");
    expect(GenerationFactor(true, regen) == 1.0 + regen / 100.0, "a two-hander generates more",
           GenerationFactor(true, regen), 1.0 + regen / 100.0);
    expect(GenerationFactor(false, regen) == 1.0, "anything else generates as it did");
    expect(GenerationFactor(true, 0) == 1.0, "no percent, no change");

    // Sixth Sense: everything but Physical.
    expect(SixthSenseReduces(false) && !SixthSenseReduces(true), "non-Physical only");

    // Determination: per enemy, up to the maximum.
    expect(Determination(0, per, max) == 0, "no enemy, no bonus");
    expect(Determination(1, per, max) == per, "one enemy", Determination(1, per, max), per);
    expect(Determination(3, per, max) == 3 * per || 3 * per > max, "three enemies add");
    unsigned const enough = unsigned(max / per) + 1;
    expect(Determination(enough, per, max) == max, "past the cap it stops", Determination(enough, per, max), max);
    expect(Determination(1000, per, max) == max, "a crowd is the cap");
    expect(Determination(unsigned(max / per), per, max) == max, "exactly at the cap");

    // Relentless Assault: any one of the three conditions.
    expect(RelentlessAssault(true, false, false, relentless) == relentless, "blind",
           RelentlessAssault(true, false, false, relentless), relentless);
    expect(RelentlessAssault(false, true, false, relentless) == relentless, "frozen");
    expect(RelentlessAssault(false, false, true, relentless) == relentless, "stunned");
    expect(RelentlessAssault(true, true, true, relentless) == relentless, "all three is not more");
    expect(RelentlessAssault(false, false, false, relentless) == 0, "none of them, nothing");

    // Determination and Relentless Assault are separate multipliers (decisions.md 2bb8979d7): each puts its own factor
    // on the hit, so together they multiply (1.2 x 1.2) and do not add (1.4), and neither joins the additive pool.
    DC::Combat::Factors factors;
    DC::Combat::AddFactor(factors, "Determination", Determination(unsigned(max / per), per, max));
    DC::Combat::AddFactor(factors, "Relentless Assault", RelentlessAssault(false, false, true, relentless));
    expect(factors.size() == 2, "one factor each");
    expect(std::abs(factors[0].second - (1 + max / 100)) < 1e-9, "Determination at the cap is one factor",
           factors[0].second, 1 + max / 100);
    expect(std::abs(factors[1].second - (1 + relentless / 100)) < 1e-9, "Relentless Assault is one factor",
           factors[1].second, 1 + relentless / 100);
    expect(std::abs(DC::Combat::Product(factors) - (1 + max / 100) * (1 + relentless / 100)) < 1e-9,
           "together they multiply", DC::Combat::Product(factors), (1 + max / 100) * (1 + relentless / 100));
    expect(std::abs(DC::Combat::Product(factors) - (1 + (max + relentless) / 100)) > 1e-9, "and do not add");

    // Beacon of Ytar: the sheet takes 0 to 100.
    expect(CooldownContribution(beacon) == beacon, "the passive's number", CooldownContribution(beacon), beacon);
    expect(CooldownContribution(-5) == 0 && CooldownContribution(250) == 100, "held to the sheet's range");

    // Alacrity: its share joins the sum the speed was built from.
    double const aps = 1.2, ias = 20;
    double const want = aps * (1 + (ias + alacrity) / 100) / (1 + ias / 100);
    expect(std::abs(AlacrityAps(aps, ias, alacrity, cap) - want) < 1e-9, "added to the sum of attack speed bonuses",
           AlacrityAps(aps, ias, alacrity, cap), want);
    expect(std::abs(AlacrityAps(1.0, 0, alacrity, cap) - (1 + alacrity / 100)) < 1e-9,
           "from nothing it is the passive alone");
    expect(AlacrityAps(cap, ias, alacrity, cap) == cap, "at the cap it stays");
    expect(AlacrityAps(cap - 0.01, ias, alacrity, cap) == cap, "and never goes over it");
    expect(AlacrityAps(cap + 1, ias, alacrity, cap) == cap + 1, "a speed already past the cap is not pulled down");
    expect(AlacrityAps(aps, ias, 0, cap) == aps && AlacrityAps(aps, ias, -10, cap) == aps, "no bonus, no change");
    expect(AlacrityAps(0, ias, alacrity, cap) == 0, "no speed stays none");
    expect(AlacrityAps(aps, ias, alacrity, cap) > aps, "faster than before");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
