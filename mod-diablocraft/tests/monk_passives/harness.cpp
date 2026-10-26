// diablocraft-x7gp9 (the Monk's passives of 2.4.1): the real dc_monk_passives.h. Prints "cases=N" and exits 0, or names
// the first failing case and exits 1. Pools and times are made up here; 75 and 50 are the sheet's threshold and cut.
#include "classes/monk/dc_monk_passives.h"

#include <cmath>
#include <cstdio>

using namespace DC::Combat::Monk::Passive;

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

int main()
{
    // Transcendence's meter: a fall of the pool is Spirit spent.
    {
        SpendMeter m;
        expect(near(m.Look(200, 250), 0), "the first look only learns the pool");
        expect(near(m.Look(150, 250), 50), "a fall of 50 is 50 spent", m.last, 150);
        expect(near(m.Look(164, 250), 0), "a gain is no spend");
        expect(near(m.Look(164, 250), 0), "no change, no spend");
        expect(near(m.Look(100, 250), 64), "the next fall counts from the last look");
    }
    // A lowered maximum (Exalted Soul taken off: 300 -> 250) clamps the pool: no spend.
    {
        SpendMeter m;
        m.Look(300, 300);
        expect(near(m.Look(250, 250), 0), "a clamp to a lower maximum is no spend");
        m.Look(280, 300);
        expect(near(m.Look(200, 250), 50), "a clamp and a spend together: only the spend from under the new maximum", 0,
               0);
    }
    // The Spirit a second: whole seconds, the rest carried.
    {
        std::uint64_t clock = 0;
        expect(WholeSeconds(clock, 999) == 0, "under a second pays nothing");
        expect(WholeSeconds(clock, 1) == 1 && clock == 0, "the second is paid when it completes");
        expect(WholeSeconds(clock, 2500) == 2 && clock == 500, "every whole second, the rest kept");
    }
    // Seize the Initiative: "above 75% Life".
    expect(Above(75.01, 75), "just above the threshold counts");
    expect(!Above(75, 75), "at the threshold is not above");
    expect(!Above(10, 75), "below does not count");
    // The stat rows: add what is wanted and missing, remove what is there and not wanted.
    {
        Change c = Reconcile(FleetFooted | Seize, FleetFooted | ExaltedSoul);
        expect(c.add == ExaltedSoul, "a newly wanted row is added", c.add, ExaltedSoul);
        expect(c.remove == Seize, "a row no longer wanted is removed", c.remove, Seize);
        Change none = Reconcile(FleetFooted, FleetFooted);
        expect(!none.add && !none.remove, "nothing changes when nothing changed");
        Change login = Reconcile(FleetFooted | ExaltedSoul | Seize, 0);
        expect(login.remove == (FleetFooted | ExaltedSoul | Seize),
               "a first look with nothing wanted clears every row");
    }
    // Chant of Resonance: half of what the mantra paid comes back.
    expect(near(PaidBack(50, 50), 25), "50 paid at 50% is 25 back");
    expect(near(PaidBack(50, 150), 50), "never more than was paid");
    expect(near(PaidBack(-5, 50), 0), "nothing paid, nothing back");

    if (failures)
        return 1;
    std::printf("cases=%d\n", cases);
    return 0;
}
