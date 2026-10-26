// diablocraft-im88g (Monk 2.3.04): the real dc_monk_hundred_fists.h. Every number comes from argv (the tunables
// sheet's and monk_skill_values.csv's, read by test_monk_hundred_fists.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_hundred_fists.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk;
using namespace DC::Combat::Monk::HundredFists;

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
    // argv: window frames, fps, damage_pct, Hands of Lightning damage_pct, hits from, hits to, aoe radius, aoe offset,
    //       Fists of Fury damage_pct, dot seconds, max stacks, tick seconds, Blazing Fists max stacks, seconds
    if (argc < 15)
        return 2;
    double const frames = std::atof(argv[1]), fps = std::atof(argv[2]), total = std::atof(argv[3]),
                 lightning = std::atof(argv[4]);
    unsigned const from = unsigned(std::atoi(argv[5])), to = unsigned(std::atoi(argv[6]));
    double const radius = std::atof(argv[7]), offset = std::atof(argv[8]), furyPct = std::atof(argv[9]);
    std::uint64_t const dotMs = std::uint64_t(std::atof(argv[10]) * 1000),
                        tickMs = std::uint64_t(std::atof(argv[12]) * 1000);
    unsigned const cap = unsigned(std::atoi(argv[11]));

    // The combo: this skill's counter is the shared Combo; 1, 2, 3, then 1 again, inside the shared window.
    std::uint64_t const window = ComboWindowMs(frames, fps, 1.0);
    Combo combo;
    expect(combo.Advance(1000, window) == 1 && combo.Advance(1500, window) == 2 && combo.Advance(2000, window) == 3 &&
               combo.Advance(2500, window) == 1,
           "stages 1 2 3 1");
    Combo paused;
    paused.Advance(1000, window);
    paused.Advance(1500, window);
    expect(paused.Advance(1500 + window + 1, window) == 1, "a pause past the window restarts");

    // Hits: only stage 2 is a series; Hands of Lightning raises it from 7 to 10.
    expect(StageHits(1, false, from, to) == 1 && StageHits(3, true, from, to) == 1, "stages 1 and 3 are one hit");
    expect(StageHits(2, false, from, to) == from, "stage 2 base hits", StageHits(2, false, from, to), from);
    expect(StageHits(2, true, from, to) == to, "stage 2 Hands of Lightning hits", StageHits(2, true, from, to), to);
    expect(from == 7 && to == 10, "the sheet's 7 and 10", from, to);
    expect(StageHits(2, false, 0, 0) == 1, "an open hit count is one hit, never zero");

    // The total is shared by the series: 7 punches add up to 190%, 10 add up to 423%.
    expect(near(HitPct(2, total, from) * from, total), "7 punches add up to the skill's damage",
           HitPct(2, total, from) * from, total);
    expect(near(HitPct(2, lightning, to) * to, lightning), "10 punches add up to 423%", HitPct(2, lightning, to) * to,
           lightning);
    expect(HitPct(1, total, from) == total && HitPct(3, total, from) == total, "stages 1 and 3 deal the whole number");
    expect(lightning > total, "Hands of Lightning raises the damage", lightning, total);
    // the power file's per-punch scalars (SF_1 0.2714 and SF_12 0.4231) are those numbers divided out
    expect(std::fabs(HitPct(2, total, from) - 27.142857) < 1e-5, "27.14% a punch", HitPct(2, total, from));
    expect(std::fabs(HitPct(2, lightning, to) - 42.3) < 1e-9, "42.3% a punch", HitPct(2, lightning, to));

    // Stage 3's area sits `offset` in front of the Monk; a point inside the radius of that centre is struck.
    Point const monk{100, 200};
    Point const centre = AoeCentre(monk, 0.0, offset);
    expect(near(centre.x, 100 + offset) && near(centre.y, 200), "centre ahead along +x", centre.x, 100 + offset);
    Point const north = AoeCentre(monk, M_PI / 2, offset);
    expect(near(north.x, 100) && near(north.y, 200 + offset), "centre ahead along +y", north.y, 200 + offset);
    expect(InCircle(centre, radius, {100 + offset + radius, 200}), "the circle's edge is struck");
    expect(!InCircle(centre, radius, {100 + offset + radius + 0.5, 200}), "past the edge is not");
    expect(InCircle(centre, radius, {100 - (radius - offset), 200}), "behind the Monk reaches radius minus offset");
    expect(!InCircle(centre, radius, {100 - (radius - offset) - 0.5, 200}), "and no further behind");

    // The wave: a strip ahead of the Monk, `width` wide (a test width of 6; the real one is the designer's), 40 long.
    Point const at0{0, 0};
    expect(InStrip(at0, 0, 40, 6, {40, 3}), "the strip's far end, inside its width");
    expect(!InStrip(at0, 0, 40, 6, {40.5, 0}), "past the length is out");
    expect(!InStrip(at0, 0, 40, 6, {10, 3.5}), "outside the width is out");
    expect(!InStrip(at0, 0, 40, 6, {-1, 0}), "behind the Monk is out");
    expect(InStrip(at0, M_PI / 2, 40, 6, {2, 30}) && !InStrip(at0, M_PI / 2, 40, 6, {30, 2}), "the strip turns with the Monk");

    // Blazing Fists: a crit adds a stack up to the cap and renews the whole buff; it ends when its time passes.
    std::uint64_t const buffMs = std::uint64_t(std::atof(argv[14]) * 1000);
    unsigned const buffCap = unsigned(std::atoi(argv[13]));
    Stacked blaze;
    expect(blaze.Add(1000, buffMs, buffCap) == 1 && blaze.Add(2000, buffMs, buffCap) == 2, "crits stack");
    for (int i = 0; i < 5; ++i)
        blaze.Add(3000 + i, buffMs, buffCap);
    expect(blaze.stacks == buffCap, "never more than the cap", blaze.stacks, buffCap);
    expect(!blaze.Over(3004 + buffMs - 1) && blaze.Over(3004 + buffMs), "the last crit renews the time of every stack");
    expect(blaze.Add(3004 + buffMs, buffMs, buffCap) == 1, "a crit after the buff ran out starts at one stack");

    // Fists of Fury: stacks add, stop at the cap and replace the oldest; a tick pays the share of the time since the last
    // one, so the total of a stack is the sheet's 60% whatever the tick times were.
    FuryStacks fury;
    fury.Add(1000, dotMs, cap);
    fury.Add(1500, dotMs, cap);
    expect(fury.Count(1600) == 2, "two hits, two stacks", fury.Count(1600), 2);
    expect(fury.Count(1000 + dotMs) == 1, "the first stack ends at its time", fury.Count(1000 + dotMs), 1);
    expect(fury.Count(1500 + dotMs) == 0, "and the second", fury.Count(1500 + dotMs), 0);
    FuryStacks capped;
    for (unsigned i = 0; i < cap + 5; ++i)
        capped.Add(1000 + i, dotMs, cap);
    expect(capped.Count(1100) == cap, "never more than the cap of stacks", capped.Count(1100), cap);
    // cap + 5 hits one millisecond apart: the five oldest were replaced, so the 6th (hit number 5) ends first
    expect(capped.Count(1000 + dotMs + 4) == cap && capped.Count(1000 + dotMs + 5) == cap - 1,
           "at the cap the oldest is replaced, so the newest outlast it", capped.Count(1000 + dotMs + 4), cap);
    FuryStacks one;
    one.Add(1000, dotMs, cap);
    double paid = 0;
    std::uint64_t last = 1000;
    for (std::uint64_t now = 1000 + tickMs; last < 1000 + dotMs + tickMs; now += tickMs)
    {
        paid += one.Pay(last, now, furyPct, dotMs);
        last = now;
    }
    expect(near(paid, furyPct), "one stack pays the sheet's 60% in all", paid, furyPct);
    FuryStacks late;
    late.Add(1000, dotMs, cap);
    double paidLate = late.Pay(1000, 1000 + dotMs + 700, furyPct, dotMs);
    expect(near(paidLate, furyPct), "one late tick still pays only the stack's 60%", paidLate, furyPct);
    expect(late.Count(1000 + dotMs + 700) == 0, "and the stack is gone");
    FuryStacks two;
    two.Add(1000, dotMs, cap);
    two.Add(1000, dotMs, cap);
    expect(near(two.Pay(1000, 1000 + tickMs, furyPct, dotMs), 2 * furyPct * tickMs / double(dotMs)), "two stacks pay twice a tick");
    FuryStacks mid;
    mid.Add(1000 + tickMs / 2, dotMs, cap);
    expect(near(mid.Pay(1000, 1000 + tickMs, furyPct, dotMs), furyPct * (tickMs / 2.0) / dotMs),
           "a stack hit in the middle of a tick pays only the rest of it");
    expect(two.Pay(1000 + dotMs, 1000 + dotMs + tickMs, furyPct, dotMs) == 0, "no stack, no payment");
    FuryStacks open;
    open.Add(1000, dotMs, cap);
    expect(open.Pay(1000, 2000, furyPct, 0) == 0, "an open duration pays nothing");
    FuryStacks none;
    none.Add(1000, dotMs, 0);
    expect(none.Count(1000) == 0, "a cap of 0 holds no stack");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
