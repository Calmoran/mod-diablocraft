// diablocraft-348cz (Monk 2.3.10): the real dc_monk_sweeping_wind.h. Every number comes from argv (the sheets' and the
// tunables', read by test_monk_sweeping_wind.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_sweeping_wind.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Wind;

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
    // argv: damage per stack %, max damage %, max stacks, tick s, tornado s, tornado tick s, consecutive s, freeze ICD s
    if (argc < 9)
        return 2;
    double const base = std::atof(argv[1]), maximum = std::atof(argv[2]), tick = std::atof(argv[4]),
                 tornado = std::atof(argv[5]), arc = std::atof(argv[6]), need = std::atof(argv[7]),
                 freezeIcd = std::atof(argv[8]);
    unsigned const most = unsigned(std::atof(argv[3]));

    // The damage: a second of the vortex at full stacks is the sheet's maximum, in ticks.
    double second = 0;
    for (unsigned i = 0; i < unsigned(1.0 / tick + 0.5); ++i)
        second += TickPct(base, most, tick);
    expect(std::fabs(second - maximum) < 1e-9, "a second at full stacks deals the sheet's maximum", second, maximum);
    expect(TickPct(base, 1, tick) * 3 == TickPct(base, 3, tick), "damage grows with the stacks");
    expect(TickPct(base, 0, tick) == 0, "no stacks, no damage");
    expect(TickPct(base, 1, tick) < base, "one tick is a share of a second's worth", TickPct(base, 1, tick), base);

    // The stacks: only an attack of a Spirit Generator adds one, and never past the maximum.
    expect(StacksAfter(1, most, true) == 2 && StacksAfter(2, most, true) == 3, "a Spirit Generator's attack adds a stack");
    expect(StacksAfter(most, most, true) == most, "and never past the maximum", StacksAfter(most, most, true), most);
    expect(StacksAfter(1, most, false) == 1, "an attack that generates no Spirit adds none");

    // Cyclone's tornado: a Spirit Generator's attack at the maximum.
    expect(SpawnsTornado(most, most, true), "a Spirit Generator at full stacks spawns the tornado");
    expect(!SpawnsTornado(most - 1, most, true), "below the maximum it adds a stack instead");
    expect(!SpawnsTornado(most, most, false), "an attack that generates no Spirit spawns none");

    // A tornado's arcs.
    expect(Ticks(tornado, arc) == unsigned(tornado / arc), "the tornado's arcs that fit its time", Ticks(tornado, arc),
           tornado / arc);
    expect(Ticks(0, arc) == 0 && Ticks(tornado, 0) == 0, "no time or no interval, no arcs");

    // Inner Storm's Spirit: once a whole second, never twice, in the vortex's tick count.
    unsigned paid = 0;
    unsigned const perSecond = unsigned(1.0 / tick + 0.5);
    for (unsigned i = 1; i <= perSecond * 6; ++i)
        paid += PaysSpirit(i, tick) ? 1 : 0;
    expect(paid == 6, "six seconds pay six times", paid, 6);
    expect(!PaysSpirit(1, tick) && PaysSpirit(perSecond, tick), "the pay falls on the tick that completes a second");
    expect(!PaysSpirit(0, tick) && !PaysSpirit(1, 0), "no tick, no pay");

    // Master of Wind: damaged for `need` seconds in a row freezes, once in `freezeIcd`.
    std::uint64_t const tickMs = std::uint64_t(tick * 1000 + 0.5), needMs = std::uint64_t(need * 1000 + 0.5),
                        icdFreeze = std::uint64_t(freezeIcd * 1000 + 0.5);
    {
        Streak streak;
        std::uint64_t t = 10000;
        bool froze = false;
        unsigned at = 0, i = 0;
        for (; i < 40 && !froze; ++i, t += tickMs)
            froze = streak.Damaged(t, tickMs, needMs, icdFreeze), at = i + 1;
        expect(froze && at * tickMs == needMs, "the run freezes on the tick that completes the seconds", at * tickMs,
               needMs);
    }
    {
        Streak streak; // one tick short of the time is not enough
        std::uint64_t t = 10000;
        bool froze = false;
        for (unsigned i = 0; i < needMs / tickMs - 1; ++i, t += tickMs)
            froze |= streak.Damaged(t, tickMs, needMs, icdFreeze);
        expect(!froze, "a tick short does not freeze");
    }
    {
        Streak streak; // a gap breaks the run
        std::uint64_t t = 10000;
        bool froze = false;
        for (unsigned i = 0; i < needMs / tickMs - 2; ++i, t += tickMs)
            froze |= streak.Damaged(t, tickMs, needMs, icdFreeze);
        t += 4 * tickMs; // out of the vortex for a second
        for (unsigned i = 0; i < needMs / tickMs - 2; ++i, t += tickMs)
            froze |= streak.Damaged(t, tickMs, needMs, icdFreeze);
        expect(!froze, "a gap starts the run over");
    }
    {
        // frozen once, not again inside the cooldown: with the sheet's numbers the run takes as long as the cooldown, so the
        // cooldown is exercised with a shorter run
        Streak streak;
        std::uint64_t const shortNeed = needMs / 3;
        std::uint64_t t = 10000;
        unsigned froze = 0;
        std::uint64_t firstAt = 0, secondAt = 0;
        for (unsigned i = 0; i < 200; ++i, t += tickMs)
            if (streak.Damaged(t, tickMs, shortNeed, icdFreeze))
            {
                ++froze;
                if (froze == 1) firstAt = t; else if (froze == 2) secondAt = t;
            }
        expect(froze >= 2, "a long run freezes again", froze, 2);
        expect(secondAt - firstAt >= icdFreeze, "but not inside the cooldown", double(secondAt - firstAt), double(icdFreeze));
    }

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
