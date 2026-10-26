// diablocraft-a0vq0 (Mystic Ally): the real dc_monk_mystic_ally.h. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1. Record ids and times are made up here (the header holds no sheet number); the 15-yard wave,
// 5-yard radius and the 2-yard knock-up are monk.csv's, passed in as the game passes them.
#include "classes/monk/dc_monk_mystic_ally.h"

#include <cmath>
#include <cstdio>

using namespace DC::Combat::Monk::MysticAlly;

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
    return std::fabs(a - b) < 1e-6;
}

int main()
{
    constexpr std::uint32_t Base = 10, Fire = 11;

    // The ally follows the bar.
    expect(Decide(0, 0, 0, 0) == Act::Keep, "nothing slotted, nothing summoned: nothing to do");
    expect(Decide(Base, 0, 0, 1000) == Act::Summon, "slotted and none: summon it");
    expect(Decide(Base, Base, 0, 1000) == Act::Keep, "slotted and alive: keep it");
    expect(Decide(0, Base, 0, 1000) == Act::Despawn, "taken off the bar: send it away");
    expect(Decide(Fire, Base, 0, 1000) == Act::Replace, "another rune slotted: replace it");
    // "When the ally dies, it is reborn after 5 seconds."
    expect(Decide(Base, 0, 6000, 5999) == Act::Keep, "dead: not a millisecond early");
    expect(Decide(Base, 0, 6000, 6000) == Act::Summon, "dead: reborn on time");
    expect(Decide(0, 0, 6000, 7000) == Act::Keep, "dead and taken off the bar: nothing comes back");

    // Water Ally's wave: a strip 15 yards ahead, 5 either side, facing +x.
    Point const ally{0, 0};
    expect(InWave(ally, 0, 15, 5, {10, 0}), "straight ahead inside the length");
    expect(InWave(ally, 0, 15, 5, {15, 5}), "the far corner is in");
    expect(!InWave(ally, 0, 15, 5, {15.01, 0}), "past the length is out");
    expect(!InWave(ally, 0, 15, 5, {5, 5.01}), "past the side is out");
    expect(!InWave(ally, 0, 15, 5, {-1, 0}), "behind the ally is out");
    expect(InWave(ally, M_PI / 2, 15, 5, {0, 10}), "the strip turns with the facing");
    expect(!InWave(ally, M_PI / 2, 15, 5, {10, 0}), "and leaves what was ahead before");

    // Air Ally's Spirit: whole seconds, the rest carried.
    std::uint64_t clock = 0;
    expect(Seconds(clock, 999) == 0, "under a second pays nothing");
    expect(Seconds(clock, 1) == 1, "the second is paid when it completes");
    expect(clock == 0, "and nothing is carried after an exact second", double(clock), 0);
    expect(Seconds(clock, 2500) == 2 && clock == 500, "a long tick pays every whole second and keeps the rest");

    // Earth Ally's knock-up: 2 yards up (v^2 / 2g), straight up just over the core's floor, or carried a distance.
    Knock up = KnockUp(2, 0);
    expect(near(up.z * up.z / (2 * 19.29110527038574), 2), "the speed lifts the unit 2 yards", up.z, 0);
    expect(up.xy > CoreMinimumSpeedXY && up.xy < 0.2, "straight up moves just over the core's minimum", up.xy, 0);
    Knock away = KnockUp(2, 3);
    expect(near(2 * away.z / 19.29110527038574 * away.xy, 3), "a distance is carried in the time aloft", away.xy, 0);
    expect(KnockUp(0, 3).z == 0, "no height, no knock");

    if (failures)
        return 1;
    std::printf("cases=%d\n", cases);
    return 0;
}
