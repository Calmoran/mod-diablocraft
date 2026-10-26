// diablocraft-dkf8w (Monk 2.3.07): the real dc_monk_wave_of_light.h. Every number comes from argv (the tunables sheet's
// and monk_skill_values.csv's, read by test_monk_wave_of_light.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_wave_of_light.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::WaveOfLight;

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
    // argv: dot damage_pct, dot seconds, tick seconds, bell offset, pillar radius, line start, line end, bell damage_pct,
    //       Empowered Wave damage_pct, bell ticks
    if (argc < 11)
        return 2;
    double const dotPct = std::atof(argv[1]), dotSeconds = std::atof(argv[2]), tickSeconds = std::atof(argv[3]),
                 offset = std::atof(argv[4]), radius = std::atof(argv[5]), start = std::atof(argv[6]),
                 end = std::atof(argv[7]);

    // Pillar of the Ancients: 3 seconds at 0.5 is 6 ticks, and the ticks add up to the sheet's 785%.
    unsigned const ticks = Ticks(dotSeconds, tickSeconds);
    expect(ticks == 6, "3 s at 0.5 s is 6 ticks", ticks, 6);
    expect(near(TickPct(dotPct, ticks) * ticks, dotPct), "the ticks add up to the damage over time",
           TickPct(dotPct, ticks) * ticks, dotPct);
    expect(Ticks(0, tickSeconds) == 0 && Ticks(dotSeconds, 0) == 0, "an open input gives no tick");
    expect(Ticks(1.0, 0.3) == 3, "a part tick is not a tick", Ticks(1.0, 0.3), 3);
    expect(TickPct(dotPct, 0) == 0, "no ticks, no damage");

    // The bell: the sheet's 835% (1045% empowered) is the total of 3 ticks, spread across 1 / attacks per second.
    double const bellPct = std::atof(argv[8]), empoweredPct = std::atof(argv[9]);
    unsigned const bellTicks = unsigned(std::atoi(argv[10]));
    expect(bellTicks == 3, "the bell has 3 ticks", bellTicks, 3);
    expect(near(TickPct(bellPct, bellTicks) * bellTicks, bellPct), "the bell's ticks add up to 835%", TickPct(bellPct, bellTicks) * bellTicks, bellPct);
    expect(near(TickPct(empoweredPct, bellTicks) * bellTicks, empoweredPct), "and to 1045% empowered");
    expect(TickGapMs(1.0, bellTicks) == 333 && TickGapMs(1.5, bellTicks) == 222, "the ticks are a third of 1 / aps apart", TickGapMs(1.0, bellTicks), 333);
    expect(TickGapMs(1.2, bellTicks) == 278, "the gap rounds to the nearest millisecond", TickGapMs(1.2, bellTicks), 278);
    expect(TickGapMs(0, bellTicks) == 0 && TickGapMs(1.0, 0) == 0, "an open input gives no gap");
    expect(TickGapMs(1.0, 1) == 1000, "one tick spans the whole second");

    // The direction and the point ahead: the bell falls `offset` yards towards the aimed point.
    Point const monk{100, 200};
    expect(near(Heading(monk, {110, 200}, 1.234), 0.0), "aimed along +x");
    expect(near(Heading(monk, {100, 250}, 1.234), M_PI / 2), "aimed along +y");
    expect(near(Heading(monk, monk, 1.234), 1.234), "aimed at the Monk's own feet: the facing");
    Point const bell = Ahead(monk, Heading(monk, {130, 200}, 0), offset);
    expect(near(bell.x, 100 + offset) && near(bell.y, 200), "the bell is `offset` ahead, not at the cursor", bell.x,
           100 + offset);
    Point const diagonal = Ahead(monk, M_PI / 4, offset);
    expect(near(std::hypot(diagonal.x - monk.x, diagonal.y - monk.y), offset),
           "ahead is `offset` away in any direction");

    // The pillar's circle.
    expect(InCircle(bell, radius, {bell.x + radius, bell.y}), "the circle's edge is struck");
    expect(!InCircle(bell, radius, {bell.x + radius + 0.5, bell.y}), "past the edge is not");
    expect(InCircle(bell, radius, monk) == (offset <= radius),
           "the Monk is inside when the pillar is closer than its radius");

    // Shattering Light's line: from `start` to `end` ahead, a test width of 6 (the real one is the designer's).
    expect(InLine(monk, 0, start, end, 6, {100 + end, 202.9}), "the line's far end, inside its width");
    expect(!InLine(monk, 0, start, end, 6, {100 + end + 0.5, 200}), "past the end is out");
    expect(!InLine(monk, 0, start, end, 6, {100 + start - 0.5, 200}), "before the start is out");
    expect(!InLine(monk, 0, start, end, 6, {120, 203.5}), "outside the width is out");
    expect(!InLine(monk, 0, start, end, 6, {90, 200}), "behind the Monk is out");
    expect(InLine(monk, M_PI / 2, start, end, 6, {101, 230}) && !InLine(monk, M_PI / 2, start, end, 6, {130, 201}),
           "the line turns with the heading");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
