// diablocraft-tnqei (Dashing Strike): the real dc_monk_dashing_strike.h and the shared dc_charge_store.h. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1. Times are in ms. The 2 and 3 charges, 8000 ms, 975% over 2 s and the 0.1 s tick are
// the sheet's and the power file's, passed in as the game passes them.
#include "classes/monk/dc_monk_dashing_strike.h"
#include "combat/dc_charge_store.h"

#include <cmath>
#include <cstdio>

using namespace DC::Combat::Monk::DashingStrike;
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

int main()
{
    // A Monk starts with every charge.
    {
        ChargeStore c;
        expect(c.Refill(0, 2, 8000) == 2, "a Monk starts full", c.count, 2);
        expect(c.next == 0, "nothing recharges while full", double(c.next), 0);
    }
    // Two dashes, then the button waits for the first charge back; charges come back one at a time.
    {
        ChargeStore c;
        expect(c.Spend(1000, 2, 8000) == 0, "the first of two dashes leaves a charge: no wait");
        expect(c.count == 1, "one charge left", c.count, 1);
        expect(c.next == 9000, "the spent charge lands one period later", double(c.next), 9000);
        std::uint64_t const wait = c.Spend(2000, 2, 8000);
        expect(c.count == 0, "two dashes empty two charges", c.count, 0);
        expect(wait == 7000, "the empty button waits until the next charge lands", double(wait), 7000);
        expect(c.Refill(8999, 2, 8000) == 0, "not a millisecond early", c.count, 0);
        expect(c.Refill(9000, 2, 8000) == 1, "the first charge lands on time", c.count, 1);
        expect(c.next == 17000, "the second starts as the first lands", double(c.next), 17000);
        expect(c.Refill(17000, 2, 8000) == 2, "the second lands one period later", c.count, 2);
        expect(c.next == 0, "full again: nothing recharging", double(c.next), 0);
    }
    // A long wait catches up all at once and stops at the cap.
    {
        ChargeStore c;
        c.Spend(0, 3, 8000);
        c.Spend(0, 3, 8000);
        c.Spend(0, 3, 8000);
        expect(c.count == 0, "Quicksilver: three dashes empty three charges", c.count, 0);
        expect(c.Refill(100000, 3, 8000) == 3, "a long wait refills to the cap and no further", c.count, 3);
    }
    // The period is the one in force when the recharge started (cooldown reduction then), as Furious Charge's.
    {
        ChargeStore c;
        c.Spend(0, 2, 8000);
        c.Spend(0, 2, 4000);
        expect(c.next == 8000, "a running recharge keeps its period", double(c.next), 8000);
        c.Refill(8000, 2, 4000);
        expect(c.next == 16000, "the next charge keeps the snapshot too", double(c.next), 16000);
    }
    // A smaller cap (the rune swapped off Quicksilver) clamps the count.
    {
        ChargeStore c;
        c.Refill(0, 3, 8000);
        expect(c.Refill(10, 2, 8000) == 2, "three charges under a cap of two are two", c.count, 2);
    }
    // A cap raised at full starts a recharge toward it.
    {
        ChargeStore c;
        c.Refill(0, 2, 8000);
        expect(c.Refill(100, 3, 8000) == 2 && c.next == 8100, "a higher cap starts a recharge", double(c.next), 8100);
    }

    // Barrage: 975% over 2 s in 0.1 s ticks is 20 ticks of 48.75%, the whole total.
    {
        Ticks t = Split(975, 2, 0.1);
        expect(t.count == 20, "20 ticks", t.count, 20);
        expect(std::fabs(t.pctEach - 48.75) < 1e-9, "48.75% a tick", t.pctEach, 48.75);
        expect(std::fabs(t.pctEach * t.count - 975) < 1e-9, "the ticks pay the whole total", t.pctEach * t.count, 975);
        Ticks none = Split(975, 2, 0);
        expect(none.count == 0, "no tick rate, no ticks (an empty tunable deals nothing)", none.count, 0);
        Ticks one = Split(975, 0.05, 0.1);
        expect(one.count == 1 && std::fabs(one.pctEach - 975) < 1e-9,
               "a duration under a tick is one tick of all of it");
    }

    if (failures)
        return 1;
    std::printf("cases=%d\n", cases);
    return 0;
}
