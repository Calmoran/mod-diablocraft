// diablocraft-i7ixi (Monk 2.4.3): the real dc_monk_passives_harmony.h. Every number comes from argv
// (monk_passive_values.csv and monk.csv, read by test_monk_passives_harmony.py). Prints "cases=N" and exits 0, or names
// the first failing case and exits 1.
#include "classes/monk/dc_monk_passives_harmony.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::PassivesHarmony;

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
    // argv: harmony share 40, combination pct 10, combination seconds 3, near death cooldown 60, immunity seconds 2,
    // heal pct 35, unity self 5, unity max 20, unity ally 5, ally stacks 4, momentum yards 25, momentum pct 20
    // (unused), momentum seconds 6, rhythm generator hits 3, rhythm damage 40
    if (argc < 16)
        return 2;
    double const share = std::atof(argv[1]), comboPct = std::atof(argv[2]);
    std::uint64_t const comboMs = std::uint64_t(std::atof(argv[3]) * 1000),
                        cooldownMs = std::uint64_t(std::atof(argv[4]) * 1000),
                        immuneMs = std::uint64_t(std::atof(argv[5]) * 1000);
    double const healPct = std::atof(argv[6]), perAlly = std::atof(argv[7]), maxPct = std::atof(argv[8]),
                 allyPct = std::atof(argv[9]);
    unsigned const allyStacks = unsigned(std::atof(argv[10]));
    double const yards = std::atof(argv[11]);
    std::uint64_t const momentumMs = std::uint64_t(std::atof(argv[13]) * 1000);
    unsigned const rhythmHits = unsigned(std::atof(argv[14]));
    double const rhythmPct = std::atof(argv[15]);

    // Harmony: 40% of each element's item resistance comes off it and goes to All Resistance, the six shares together.
    std::array<double, 7> items{0, 100, 50, 0, 0, 0, 25};
    HarmonyResult h = Harmony(items, share);
    expect(near(h.single[1], -40) && near(h.single[2], -20) && near(h.single[6], -10),
           "each element gives up its share");
    expect(near(h.single[0], 0) && near(h.single[3], 0), "an element with no item resistance gives up none");
    expect(near(h.all, 70), "All Resistance gets the sum of the shares", h.all, 70);
    expect(near(Harmony(items, 0).all, 0), "no share, no change");
    expect(near(Harmony({-30, 0, 0, 0, 0, 0, 0}, share).all, 0), "a negative item resistance converts nothing");

    // Combination Strike: one `pct` per DIFFERENT generator used and still running; the same one again only renews.
    Combination combo;
    expect(near(combo.Bonus(0, comboPct), 0), "nothing used, no bonus");
    combo.Use(1, 1000, comboMs);
    expect(near(combo.Bonus(1001, comboPct), comboPct), "one generator used adds one", combo.Bonus(1001, comboPct), comboPct);
    combo.Use(3, 1100, comboMs);
    expect(near(combo.Bonus(1200, comboPct), 2 * comboPct), "each different generator adds one");
    combo.Use(1, 1500, comboMs);
    expect(combo.Active(1500) == 2 && near(combo.Bonus(1500, comboPct), 2 * comboPct),
           "using the same one again renews, not stacks");
    expect(near(combo.Bonus(1100 + comboMs, comboPct), comboPct), "the second use has run out, the renewed one has not");
    expect(near(combo.Bonus(1500 + comboMs, comboPct), 0), "all have run out");

    // Mythic Rhythm: every third Spirit Generator hit arms the sheet's damage on the next Spirit Spender, which spends it.
    Rhythm rhythm;
    expect(near(rhythm.Bonus(rhythmPct), 0), "no hits, no bonus");
    for (unsigned i = 1; i < rhythmHits; ++i)
        rhythm.Hit(rhythmHits);
    expect(!rhythm.armed && near(rhythm.Bonus(rhythmPct), 0), "the hits before the third arm nothing");
    rhythm.Hit(rhythmHits);
    expect(rhythm.armed && near(rhythm.Bonus(rhythmPct), rhythmPct), "the third hit arms the sheet's damage",
           rhythm.Bonus(rhythmPct), rhythmPct);
    rhythm.Hit(rhythmHits);
    expect(near(rhythm.Bonus(rhythmPct), rhythmPct), "a hit while armed adds nothing");
    for (unsigned i = 1; i < rhythmHits; ++i)
        rhythm.Hit(rhythmHits);
    expect(near(rhythm.Bonus(rhythmPct), rhythmPct), "a second third while armed is still one spender's bonus");
    rhythm.Hit(rhythmHits);
    expect(rhythm.Spend() && !rhythm.armed && near(rhythm.Bonus(rhythmPct), 0), "a spender spends it");
    expect(!rhythm.Spend(), "and only once");
    for (unsigned i = 2; i < rhythmHits; ++i)
        rhythm.Hit(rhythmHits);
    expect(!rhythm.armed, "the hits before the next third arm nothing");
    rhythm.Hit(rhythmHits);
    expect(rhythm.armed, "the count runs on from the last third, not from the spend");
    Rhythm none;
    for (unsigned i = 0; i < 2 * rhythmHits; ++i)
        none.Hit(0);
    expect(!none.armed, "a count of none arms nothing");

    // diablocraft-2wf3x: a spender whose hits come after its cast (Seven-Sided Strike's strikes) spends the bonus with
    // the cast, and its own hits carry what the cast found.
    Rhythm seven;
    for (unsigned i = 0; i < rhythmHits; ++i)
        seven.Hit(rhythmHits);
    seven.Carry();
    expect(!seven.armed && near(seven.Bonus(rhythmPct), 0), "the delayed spender's cast spends it");
    expect(near(seven.Bonus(rhythmPct, true), rhythmPct), "and its strikes carry the sheet's damage",
           seven.Bonus(rhythmPct, true), rhythmPct);
    expect(!seven.Spend(), "the next spender finds nothing armed");
    for (unsigned i = 0; i < rhythmHits; ++i)
        seven.Hit(rhythmHits);
    expect(near(seven.Bonus(rhythmPct, true), rhythmPct) && near(seven.Bonus(rhythmPct), rhythmPct),
           "a third hit during the strikes arms the next spender and leaves the strikes as they were");
    seven.Carry();
    expect(near(seven.Bonus(rhythmPct, true), rhythmPct) && !seven.armed, "the next delayed cast takes that one");
    seven.Carry();
    expect(near(seven.Bonus(rhythmPct, true), 0), "a delayed cast that found nothing armed carries nothing");
    Rhythm idle;
    expect(near(idle.Bonus(rhythmPct, true), 0), "strikes with no cast behind them carry nothing");
    for (unsigned i = 0; i < rhythmHits; ++i)
        idle.Hit(rhythmHits);
    expect(near(idle.Bonus(rhythmPct, true), 0), "a delayed spender's strikes never read the armed bonus itself");

    // Momentum: yards add up across samples; every `yards` starts the buff, the rest is kept.
    Momentum momentum;
    momentum.Moved(10, 1000, yards, momentumMs);
    momentum.Moved(10, 1100, yards, momentumMs);
    expect(!momentum.On(1100), "20 yards is not enough");
    momentum.Moved(7, 1200, yards, momentumMs);
    expect(momentum.On(1200) && momentum.On(1200 + momentumMs - 1), "25 yards starts the buff");
    expect(!momentum.On(1200 + momentumMs), "the buff ends after its seconds");
    expect(near(momentum.yards, 2), "the yards over 25 are kept", momentum.yards, 2);
    momentum.Moved(-5, 5000, yards, momentumMs);
    momentum.Moved(0, 5000, yards, momentumMs);
    expect(near(momentum.yards, 2), "standing still adds nothing");
    momentum.Moved(23, 9000, yards, momentumMs);
    expect(momentum.On(9000) && near(momentum.yards, 0), "the next 25 yards renew it");

    // Unity: 5% each ally up to 20%; an ally has 5% for each Monk, up to the stack cap.
    expect(near(UnitySelf(3, perAlly, maxPct), 15), "three allies, 15%");
    expect(near(UnitySelf(9, perAlly, maxPct), maxPct), "never past the maximum");
    expect(near(UnitySelf(0, perAlly, maxPct), 0), "no allies, nothing");
    expect(near(UnityAlly(1, allyPct, allyStacks), allyPct), "an ally of one Monk has 5%");
    expect(near(UnityAlly(allyStacks + 3, allyPct, allyStacks), allyStacks * allyPct),
           "an ally's stacks stop at the cap");

    // Near Death Experience: fatal damage, once per cooldown, with the immunity window.
    NearDeath near_death;
    expect(!near_death.Save(1000, 99, 100, cooldownMs, immuneMs), "damage under the Life is not fatal");
    expect(near_death.Save(1000, 100, 100, cooldownMs, immuneMs), "damage equal to the Life is fatal");
    expect(near_death.Immune(1000) && near_death.Immune(1000 + immuneMs - 1) && !near_death.Immune(1000 + immuneMs),
           "the immunity lasts its seconds");
    expect(!near_death.Save(1000 + immuneMs + 1, 500, 100, cooldownMs, immuneMs), "not again inside the cooldown");
    expect(!near_death.Save(1000 + cooldownMs - 1, 500, 100, cooldownMs, immuneMs),
           "not on the last millisecond of it");
    expect(near_death.Save(1000 + cooldownMs, 500, 100, cooldownMs, immuneMs), "ready again after it");
    expect(NearDeathHealth(10, 1000, healPct) == 360, "35% of the maximum on top of the Life");
    expect(NearDeathHealth(900, 1000, healPct) == 1000, "never past the maximum");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
