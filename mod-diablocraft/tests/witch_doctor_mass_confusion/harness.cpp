// The real dc_witch_doctor_mass_confusion.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_mass_confusion.py); nothing is typed in here. Prints "cases=N" and exits 0, or names
// the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_mass_confusion.h"
#include "combat/dc_periodic_strike.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::MassConfusion;

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
    // argv: the five runes A to E, then the share of the enemies the confusion takes, the most Mass Hysteria stuns, the
    // confusion's seconds, the spirit's tick, its speed a frame, its damage a second, Devolution's chance.
    if (argc < 13)
        return 2;
    std::string const paranoia = argv[1], hysteria = argv[2], hallucination = argv[3], realm = argv[4],
                      devolution = argv[5];
    double const proportion = std::atof(argv[6]), most = std::atof(argv[7]), seconds = std::atof(argv[8]),
                 tick = std::atof(argv[9]), speed = std::atof(argv[10]), damage = std::atof(argv[11]),
                 chance = std::atof(argv[12]);

    expect(RuneOf(paranoia) == Rune::Paranoia && RuneOf(hysteria) == Rune::MassHysteria &&
               RuneOf(hallucination) == Rune::MassHallucination && RuneOf(realm) == Rune::UnstableRealm &&
               RuneOf(devolution) == Rune::Devolution,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {paranoia, hysteria, hallucination, realm, devolution})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The confusion takes an enemy whose roll is under the proportion, and no one when there is no proportion.
    expect(Affected(0.0, proportion) && Affected(proportion - 0.001, proportion) && !Affected(proportion, proportion) &&
               !Affected(0.99, proportion),
           "an enemy under the proportion is taken", proportion, 0);
    expect(!Affected(0.0, 0.0) && !Affected(0.0, -1.0), "no proportion takes no one");

    // Mass Hysteria stuns up to its count of the enemies the confusion missed.
    expect(ToStun(3, unsigned(most)) == 3 && ToStun(unsigned(most) + 6, unsigned(most)) == unsigned(most) &&
               ToStun(0, unsigned(most)) == 0,
           "as many as were missed up to the count", ToStun(unsigned(most) + 6, unsigned(most)), most);

    // The spirit's speed is yards per frame at 60 frames a second: the file's 0.3 is 18 yards a second, so a quarter
    // second is 4.5.
    expect(near(StepYards(speed, 1.0), speed * 60.0) && near(StepYards(speed, tick), speed * 60.0 * tick),
           "a step is the speed a second over the tick", StepYards(speed, tick), speed * 60.0 * tick);
    expect(StepYards(0, tick) == 0 && StepYards(speed, 0) == 0 && StepYards(-1, tick) == 0,
           "no speed or tick, no step");
    // It walks towards the enemy, stops there and does not pass it.
    Spot const a = Advance({0, 0}, {10, 0}, 4.0);
    expect(near(a.x, 4.0) && near(a.y, 0.0), "it walks a step towards the enemy", a.x, 4.0);
    Spot const b = Advance({0, 0}, {3, 4}, 10.0);
    expect(near(b.x, 3.0) && near(b.y, 4.0), "it stops at an enemy nearer than a step", b.x, 3.0);
    Spot const c = Advance({1, 1}, {4, 5}, 2.5);
    expect(near(c.x, 1 + 3.0 / 5.0 * 2.5) && near(c.y, 1 + 4.0 / 5.0 * 2.5), "it keeps the direction", c.x,
           1 + 3.0 / 5.0 * 2.5);
    Spot const d = Advance({2, 2}, {9, 9}, 0.0);
    expect(near(d.x, 2.0) && near(d.y, 2.0), "no step, it stays");

    // The spirit walks for the confusion's seconds, a tick at a time, each tick a share of its damage a second.
    unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
    expect(ticks > 1 && near(PerTick(damage, tick) * ticks, damage * seconds),
           "its ticks make its damage over the seconds", PerTick(damage, tick) * ticks, damage * seconds);

    // Devolution: an enemy counts as confused for the confusion's seconds and no longer, and a roll under the chance
    // leaves a dog.
    std::uint64_t const held = HeldMs(seconds);
    expect(held == std::uint64_t(seconds * 1000.0 + 0.5) && HeldMs(0) == 0 && HeldMs(-3) == 0,
           "an enemy counts as confused for the confusion's seconds", double(held), seconds * 1000.0);
    expect(Confused(1000 + held - 1, 1000 + held) && !Confused(1000 + held, 1000 + held) && Confused(1000, 1000 + held),
           "a death ends the count when the confusion does", double(held), 0);
    expect(Rises(0.0, chance) && Rises(chance - 0.01, chance) && !Rises(chance, chance) && !Rises(100.0, chance),
           "a roll below the chance leaves a dog", chance, 0);
    expect(!Rises(0.0, 0.0) && !Rises(0.0, -5.0), "no chance, no dog");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
