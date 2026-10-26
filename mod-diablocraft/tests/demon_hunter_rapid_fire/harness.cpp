// The real dc_demon_hunter_rapid_fire.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_rapid_fire.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_rapid_fire.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::RapidFire;

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
    // argv: the five runes A to E, the shots in a second of attack speed and Bombardment's, the channel's Hatred a second,
    // the skill's damage and Bombardment's, the rockets a second.
    if (argc < 12)
        return 2;
    std::string const bombardment = argv[1], velocity = argv[2], support = argv[3], withering = argv[4], frost = argv[5];
    double const shots = std::atof(argv[6]), grenades = std::atof(argv[7]), channelCost = std::atof(argv[8]),
                 damage = std::atof(argv[9]), grenadeDamage = std::atof(argv[10]), rockets = std::atof(argv[11]);

    expect(RuneOf(bombardment) == Rune::Bombardment && RuneOf(velocity) == Rune::HighVelocity && RuneOf(support) == Rune::FireSupport &&
               RuneOf(withering) == Rune::WitheringFire && RuneOf(frost) == Rune::FrostShots,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {bombardment, velocity, support, withering, frost})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Rapid Fire") == Rune::None, "the base skill and a stranger are no rune");

    // The cadence: a second of attack speed holds the shots.
    expect(near(ShotSeconds(shots, 1.0), 1.0 / shots), "at one attack a second, a sixth of a second a shot", ShotSeconds(shots, 1.0), 1.0 / shots);
    expect(near(ShotSeconds(shots, 2.0), 0.5 / shots), "twice as fast, half the seconds", ShotSeconds(shots, 2.0), 0.5 / shots);
    expect(near(ShotSeconds(grenades, 1.0), 1.0 / grenades) && ShotSeconds(grenades, 1.0) > ShotSeconds(shots, 1.0),
           "Bombardment's grenades are slower than the arrows");
    expect(near(ShotSeconds(shots, 0), 0) && near(ShotSeconds(0, 1.0), 0), "no speed or no shots, no cadence");

    // A shot carries its share of the second's damage and Hatred.
    expect(near(ShotPct(damage, shots) * shots, damage), "the shots of a second deal the sheet's damage", ShotPct(damage, shots) * shots, damage);
    expect(near(ShotPct(grenadeDamage, grenades) * grenades, grenadeDamage), "and Bombardment's");
    expect(near(ShotCost(channelCost, shots) * shots, channelCost), "the shots of a second cost the channel's Hatred", ShotCost(channelCost, shots) * shots, channelCost);
    expect(near(ShotCost(channelCost, grenades) * grenades, channelCost) && ShotCost(channelCost, grenades) > ShotCost(channelCost, shots),
           "a grenade costs more than an arrow, the same for a second");
    expect(near(ShotPct(damage, 0), 0) && near(ShotCost(channelCost, 0), 0), "no shots, no share");

    expect(near(RocketSeconds(rockets), 1.0 / rockets) && near(RocketSeconds(0), 0), "the rockets of a second are spaced");

    // The clock: whole intervals, the rest kept.
    double clock = 0;
    expect(Due(clock, 100, 250) == 0 && near(clock, 100), "not yet due keeps the time");
    expect(Due(clock, 200, 250) == 1 && near(clock, 50), "one due, the rest kept", clock, 50);
    clock = 0;
    expect(Due(clock, 500, 250) == 2 && near(clock, 0), "two due on the moment");
    clock = 0;
    expect(Due(clock, 100, 0) == 0 && near(clock, 0), "no interval, none due");
    clock = 0;
    expect(Due(clock, 1e9, 250) == 40, "never more than the cap at once");

    // Held: ten seconds of server updates of 50 ms. The channel keeps shooting at the cadence and spends the Hatred a second
    // the sheet says; a grenade channel the same, at half the rate and twice the cost.
    for (double attacksPerSecond : {1.0, 1.5})
    {
        double clockA = 0, clockB = 0;
        unsigned arrows = 0, bombs = 0;
        for (int update = 0; update < 200; ++update)
        {
            arrows += Due(clockA, 50, ShotSeconds(shots, attacksPerSecond) * 1000.0);
            bombs += Due(clockB, 50, ShotSeconds(grenades, attacksPerSecond) * 1000.0);
        }
        expect(std::fabs(double(arrows) - 10.0 * attacksPerSecond * shots) <= 1.0, "ten seconds held, the arrows keep coming", double(arrows),
               10.0 * attacksPerSecond * shots);
        expect(std::fabs(double(arrows) * ShotCost(channelCost, shots) - 10.0 * attacksPerSecond * channelCost) <= 1.0 * ShotCost(channelCost, shots),
               "and cost the Hatred a second the sheet says");
        expect(std::fabs(double(bombs) * ShotCost(channelCost, grenades) - 10.0 * attacksPerSecond * channelCost) <= ShotCost(channelCost, grenades),
               "the grenades cost the same for a second");
    }

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
