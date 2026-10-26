// The real dc_witch_doctor_piranhas.h. The rune names and numbers come from argv (read from the sheets and the tunables
// by test_witch_doctor_piranhas.py); nothing is typed in here but distances to try. Prints "cases=N" and exits 0, or
// names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_piranhas.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::Piranhas;

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
    // argv: the five runes A to E, the pool's radius, the leap radius, the tick, the damage, its seconds, the tornado's
    // seconds, the wave's offset, length, yards a second, distance and width, the vacuum radius.
    if (argc < 18)
        return 2;
    std::string const bogadile = argv[1], zombie = argv[2], tornado = argv[3], wave = argv[4], frozen = argv[5];
    double const pool = std::atof(argv[6]), leap = std::atof(argv[7]), tick = std::atof(argv[8]),
                 damage = std::atof(argv[9]), seconds = std::atof(argv[10]), tornadoSeconds = std::atof(argv[11]),
                 offset = std::atof(argv[12]), length = std::atof(argv[13]), speed = std::atof(argv[14]),
                 distance = std::atof(argv[15]), width = std::atof(argv[16]), vacuum = std::atof(argv[17]);
    constexpr double Pi = 3.14159265358979323846;

    expect(RuneOf(bogadile) == Rune::Bogadile && RuneOf(zombie) == Rune::ZombiePiranhas &&
               RuneOf(tornado) == Rune::Piranhado && RuneOf(wave) == Rune::WaveOfMutilation &&
               RuneOf(frozen) == Rune::FrozenPiranhas,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {bogadile, zombie, tornado, wave, frozen})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Only the Bogadile's bite takes the rune's Physical: the pool stays Poison.
    expect(!PoolTakesRuneElement(Rune::Bogadile) && PoolTakesRuneElement(Rune::FrozenPiranhas) &&
               PoolTakesRuneElement(Rune::Piranhado) && PoolTakesRuneElement(Rune::None),
           "only the Bogadile's pool keeps the skill's element");

    // The pool's ticks: the sheet's damage over its seconds, half as much for a pool that stands half as long.
    unsigned const ticks = unsigned(std::floor(seconds / tick + 1e-9));
    expect(ticks > 1 && std::fabs(TickPct(damage, seconds, tick) * ticks - damage) < 1e-6, "the ticks make the damage",
           TickPct(damage, seconds, tick) * ticks, damage);
    unsigned const tornadoTicks = unsigned(std::floor(tornadoSeconds / tick + 1e-9));
    expect(tornadoSeconds < seconds &&
               std::fabs(TickPct(damage, seconds, tick) * tornadoTicks - damage * tornadoSeconds / seconds) < 1e-6,
           "a pool that stands for the tornado's seconds deals its share",
           TickPct(damage, seconds, tick) * tornadoTicks, damage * tornadoSeconds / seconds);
    expect(TickPct(damage, 0, tick) == 0, "no seconds, no damage");

    // The reach: Zombie Piranhas leap farther than the pool.
    expect(PoolReach(Rune::None, pool, leap) == pool && PoolReach(Rune::FrozenPiranhas, pool, leap) == pool,
           "the pool reaches its radius", pool, 0);
    expect(PoolReach(Rune::ZombiePiranhas, pool, leap) == leap && leap > pool, "Zombie Piranhas leap farther", leap,
           pool);

    // The wave runs north (heading pi/2): ahead is north, across is east-west.
    double const heading = Pi / 2;
    expect(std::fabs(Ahead(0, 10, heading) - 10) < 1e-9 && std::fabs(Across(5, 0, heading) + 5) < 1e-9,
           "ahead is the aim, across is a side", Ahead(0, 10, heading), 10);
    expect(WaveCovers(10, 0, distance, width) && WaveCovers(distance, width / 2, distance, width) &&
               WaveCovers(0, 0, distance, width),
           "the wave covers what is ahead within its distance and width, ends and all");
    expect(!WaveCovers(-1, 0, distance, width) && !WaveCovers(distance + 0.1, 0, distance, width) &&
               !WaveCovers(10, width / 2 + 0.1, distance, width),
           "not what is behind, past its distance or beyond its width");

    // When the wave reaches an enemy: what lies within its first stretch at once, the rest after the run.
    expect(WaveReachesMs(offset + length, offset, length, speed) == 0 && WaveReachesMs(1, offset, length, speed) == 0,
           "within its first stretch the wave hits at once");
    expect(WaveReachesMs(offset + length + speed, offset, length, speed) == 1000,
           "a second's run past it, a second later",
           double(WaveReachesMs(offset + length + speed, offset, length, speed)), 1000);
    expect(WaveReachesMs(distance, offset, length, speed) > WaveReachesMs(offset + length + 1, offset, length, speed),
           "the farther the later");
    expect(WaveReachesMs(distance, offset, length, 0) == 0, "no speed, no wait");

    // The tornado sucks in what is within its vacuum radius.
    expect(Sucked(vacuum, vacuum) && Sucked(0, vacuum) && !Sucked(vacuum + 0.01, vacuum),
           "the tornado sucks in what is within its radius, ends and all");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
