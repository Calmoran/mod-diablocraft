// The real dc_witch_doctor_poison_dart.h and the shared damage-over-time arithmetic (dc_periodic_strike.h). The rune names and numbers come
// from argv (read from the sheets and the tunables by test_witch_doctor_poison_dart.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_poison_dart.h"
#include "combat/dc_periodic_strike.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor::PoisonDart;

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
    // argv: the five runes A to E, then the poison's damage and seconds, Flaming Dart's damage and seconds, the tick, Splinters' darts and the
    // delay between them, Snake to the Face's chance.
    if (argc < 13)
        return 2;
    std::string const flaming = argv[1], splinters = argv[2], numbing = argv[3], spined = argv[4], snake = argv[5];
    double const poison = std::atof(argv[6]), poisonSeconds = std::atof(argv[7]), fire = std::atof(argv[8]), fireSeconds = std::atof(argv[9]),
                 tick = std::atof(argv[10]), delay = std::atof(argv[12]);
    unsigned const darts = unsigned(std::atoi(argv[11]));
    double const chance = argc > 13 ? std::atof(argv[13]) : 35;

    expect(RuneOf(flaming) == Rune::FlamingDart && RuneOf(splinters) == Rune::Splinters && RuneOf(numbing) == Rune::NumbingDart &&
               RuneOf(spined) == Rune::SpinedDart && RuneOf(snake) == Rune::SnakeToTheFace,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {flaming, splinters, numbing, spined, snake})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The poison and the fire: their ticks make their damage.
    unsigned const poisonTicks = PeriodicStrike::Ticks(poisonSeconds, tick), fireTicks = PeriodicStrike::Ticks(fireSeconds, tick);
    expect(poisonTicks > 1 && fireTicks > poisonTicks, "the fire ticks longer than the poison", fireTicks, poisonTicks);
    expect(near(PeriodicStrike::TickPct(poison, poisonTicks) * poisonTicks, poison) && near(PeriodicStrike::TickPct(fire, fireTicks) * fireTicks, fire),
           "the ticks make the damage", PeriodicStrike::TickPct(fire, fireTicks) * fireTicks, fire);
    expect(poisonTicks == unsigned(std::lround(poisonSeconds / tick)) && fireTicks == unsigned(std::lround(fireSeconds / tick)), "every tick that fits is struck", poisonTicks, poisonSeconds / tick);
    expect(PeriodicStrike::TickPct(poison, 0) == 0 && PeriodicStrike::Ticks(poisonSeconds, 0) == 0 && PeriodicStrike::Ticks(0, tick) == 0, "no tick, no damage");

    // Splinters: the first dart with the cast, the others a delay apart.
    expect(darts > 1, "more than one dart", darts, 2);
    expect(DartDelayMs(0, delay) == 0, "the first dart leaves with the cast");
    expect(DartDelayMs(darts - 1, delay) == std::uint32_t(delay * 1000.0 * (darts - 1) + 0.5), "the last a delay apiece after", DartDelayMs(darts - 1, delay), delay * 1000.0 * (darts - 1));
    expect(DartDelayMs(1, 0) == 0 && DartDelayMs(2, -1) == 0, "no delay, all at once");

    // Snake to the Face: a roll under the chance stuns.
    expect(Stuns(0.0, chance) && Stuns(chance - 0.01, chance) && !Stuns(chance, chance) && !Stuns(99.9, chance) && !Stuns(0.0, 0.0), "a roll under the chance stuns");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
