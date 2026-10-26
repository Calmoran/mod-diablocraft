// The real dc_crusader_blessed_hammer.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_crusader_blessed_hammer.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/crusader/dc_crusader_blessed_hammer.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::BlessedHammer;

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
    // argv: the reach, Limitless's increase, the most pools, a pool's seconds, its tick, the hammer's life, its loops,
    // the look step, Limitless's life factor, then the five runes A to E
    if (argc < 16)
        return 2;
    double const reach = std::atof(argv[1]), increase = std::atof(argv[2]), poolSeconds = std::atof(argv[4]),
                 poolTick = std::atof(argv[5]), life = std::atof(argv[6]), loops = std::atof(argv[7]),
                 step = std::atof(argv[8]), factor = std::atof(argv[9]);
    std::size_t const most = std::size_t(std::atoi(argv[3]));
    std::string const burning = argv[10], thunder = argv[11], limitless = argv[12], brute = argv[13],
                      dominion = argv[14];
    double const hitRadius = std::atof(argv[15]);
    double const pi = 3.14159265358979323846;

    expect(RuneOf(burning) == Rune::BurningWrath && RuneOf(thunder) == Rune::Thunderstruck &&
               RuneOf(limitless) == Rune::Limitless && RuneOf(brute) == Rune::BruteForce &&
               RuneOf(dominion) == Rune::Dominion,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {burning, thunder, limitless, brute, dominion})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Zeal") == Rune::None, "the base skill and a stranger are no rune");

    // Limitless: the reach with the increase and the longer life, no other rune.
    expect(Reach(Rune::Limitless, reach, increase) == reach + increase, "Limitless reaches further",
           Reach(Rune::Limitless, reach, increase), reach + increase);
    expect(Reach(Rune::None, reach, increase) == reach && Reach(Rune::BurningWrath, reach, increase) == reach &&
               Reach(Rune::Dominion, reach, increase) == reach,
           "no other rune reaches further");
    expect(Lifetime(Rune::Limitless, life, factor) == life * factor, "Limitless lasts longer",
           Lifetime(Rune::Limitless, life, factor), life * factor);
    expect(Lifetime(Rune::BruteForce, life, factor) == life && Lifetime(Rune::None, life, factor) == life,
           "no other rune lasts longer");

    // The spiral: from the Crusader, out to the reach evenly over its life, turning the loops from the heading it
    // started at.
    Offset const start = Orbit(0, life, reach, loops, 0);
    expect(std::hypot(start.x, start.y) < 1e-9, "the hammer starts at the Crusader");
    Offset const end = Orbit(life, life, reach, loops, 0);
    expect(std::fabs(std::hypot(end.x, end.y) - reach) < 1e-9, "it ends at the reach", std::hypot(end.x, end.y), reach);
    Offset const half = Orbit(life / 2, life, reach, loops, 0);
    expect(std::fabs(std::hypot(half.x, half.y) - reach / 2) < 1e-9, "halfway through its life it is halfway out",
           std::hypot(half.x, half.y), reach / 2);
    Offset const past = Orbit(life * 5, life, reach, loops, 0);
    expect(std::fabs(std::hypot(past.x, past.y) - reach) < 1e-9, "past its life it stays at the end");
    // Half a loop in is on the other side (at one loop the hammer is back on its heading, at a half loop opposite).
    Offset const quarter = Orbit(life / (loops * 2), life, reach, loops, 0);
    expect(quarter.x < 0 && std::fabs(quarter.y) < 1e-9, "half a loop in it is on the far side", quarter.x, quarter.y);
    Offset const turned = Orbit(life / (loops * 4), life, reach, loops, pi / 2);
    expect(std::fabs(turned.x + std::hypot(turned.x, turned.y)) < 1e-9 || turned.x < 0,
           "the spiral turns from the Crusader's heading", turned.x, turned.y);
    Offset const instant = Orbit(life, 0, reach, loops, 0);
    expect(std::fabs(std::hypot(instant.x, instant.y) - reach) < 1e-9, "a hammer of no life is at its reach at once");

    // The touch and the entry.
    expect(Touches(2, 3) && Touches(3, 3) && !Touches(3.01, 3), "within the hit radius is a touch", 3, 3.01);
    expect(!Touches(0, 0) && !Touches(1, 0), "no hit radius, no touch");
    // The designer's size for the hammer: 5 yards.
    expect(Touches(hitRadius, hitRadius) && !Touches(hitRadius + 0.01, hitRadius), "the hammer hits within its hit radius and no further", hitRadius, hitRadius + 0.01);
    expect(SegmentDistance(5, hitRadius, 0, 0, 10, 0) <= hitRadius && SegmentDistance(5, hitRadius + 0.1, 0, 0, 10, 0) > hitRadius,
           "an arc catches the enemies within the hit radius of its line", hitRadius, 0);
    expect(Enters(false, true) && !Enters(true, true) && !Enters(false, false) && !Enters(true, false),
           "an enemy is hit as the hammer reaches it, once");

    // Thunderstruck's arc: the distance from a point to the segment from the Crusader to the hammer.
    expect(SegmentDistance(5, 3, 0, 0, 10, 0) == 3, "beside the segment", SegmentDistance(5, 3, 0, 0, 10, 0), 3);
    expect(SegmentDistance(-4, 3, 0, 0, 10, 0) == 5, "past the near end it is the end's distance",
           SegmentDistance(-4, 3, 0, 0, 10, 0), 5);
    expect(SegmentDistance(14, 3, 0, 0, 10, 0) == 5, "past the far end too");
    expect(SegmentDistance(3, 4, 1, 1, 1, 1) == std::hypot(2, 3), "a segment of no length is a point");

    // The looks the hammer takes over its life.
    expect(Steps(life, step) == unsigned(life / step + 1e-9), "the looks that fit its life", Steps(life, step),
           life / step);
    expect(Steps(life, 0) == 0 && Steps(0, step) == 0, "no step or no life, no looks");
    expect(Steps(3.0, 0.1) == 30, "thirty tenths despite the float", Steps(3.0, 0.1), 30);

    // The pools: room while fewer than the most burn, and the ticks a pool has.
    expect(PoolRoom(0, most) && PoolRoom(most - 1, most) && !PoolRoom(most, most) && !PoolRoom(most + 3, most),
           "a pool may be laid while fewer than the most burn", double(most), 0);
    expect(!PoolRoom(0, 0), "no room with a most of none");
    expect(PoolTicks(poolSeconds, poolTick) == unsigned(poolSeconds / poolTick), "the ticks that fit the seconds",
           PoolTicks(poolSeconds, poolTick), poolSeconds / poolTick);
    expect(PoolTicks(poolSeconds, 0) == 0 && PoolTicks(0, poolTick) == 0, "no tick length or no seconds, no ticks");
    expect(PoolTicks(1.0, 0.1) == 10, "ten tenths despite the float", PoolTicks(1.0, 0.1), 10);
    expect(PoolTicks(poolSeconds, poolSeconds * 3) == 0, "a tick longer than the pool never lands");

    // The pool's schedule, driven as the production code drives it: it fires each of its ticks, the last one included.
    unsigned fired = 0, left = PoolTicks(poolSeconds, poolTick);
    while (PoolFires(left) && fired < 100)
    {
        ++fired;
        left = PoolLeftAfter(left);
    }
    expect(fired == PoolTicks(poolSeconds, poolTick), "a pool fires every one of its ticks", fired,
           PoolTicks(poolSeconds, poolTick));
    expect(fired == 2, "the sheet's pool fires twice", fired, 2);
    expect(!PoolFires(0) && PoolFires(1) && PoolLeftAfter(1) == 0 && PoolLeftAfter(0) == 0,
           "the last tick fires and nothing follows it");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
