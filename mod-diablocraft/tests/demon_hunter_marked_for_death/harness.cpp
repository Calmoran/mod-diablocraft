// The real dc_demon_hunter_marked_for_death.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_marked_for_death.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/demon_hunter/dc_demon_hunter_marked_for_death.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::MarkedForDeath;

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
    // argv: the five runes A to E, then the mark's seconds, Grim Reaper's share, Contagion's targets, Valley of Death's radius and tick
    // seconds and area seconds, Death Toll's heal.
    if (argc < 13)
        return 2;
    std::string const grim = argv[1], contagion = argv[2], valley = argv[3], mortal = argv[4], toll = argv[5];
    double const seconds = std::atof(argv[6]), share = std::atof(argv[7]);
    std::size_t const targets = std::size_t(std::atoi(argv[8]));
    double const radius = std::atof(argv[9]), tick = std::atof(argv[10]), areaSeconds = std::atof(argv[11]), heal = std::atof(argv[12]);

    expect(RuneOf(grim) == Rune::GrimReaper && RuneOf(contagion) == Rune::Contagion && RuneOf(valley) == Rune::ValleyOfDeath &&
               RuneOf(mortal) == Rune::MortalEnemy && RuneOf(toll) == Rune::DeathToll,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {grim, contagion, valley, mortal, toll})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A mark runs for its seconds from the moment it is made.
    std::uint64_t const made = 1000, ends = EndsAt(made, seconds);
    expect(ends == made + std::uint64_t(seconds * 1000.0), "a mark ends its seconds after it was made", double(ends), double(made) + seconds * 1000.0);
    expect(On(ends, ends - 1) && !On(ends, ends) && !On(ends, ends + 1), "it is on up to its last millisecond", double(ends), 0);
    expect(!On(EndsAt(made, 0), made) && EndsAt(made, -5) == made, "no seconds, no mark");

    // Grim Reaper: the share of a hit divided evenly among the other enemies.
    double const each = SharePerEnemy(1000, share, 3);
    expect(std::fabs(each - 1000 * share / 100.0 / 3) < 1e-9, "each enemy takes an even part of the share", each, 1000 * share / 100.0 / 3);
    expect(std::fabs(each * 3 - 1000 * share / 100.0) < 1e-9, "the parts make the share", each * 3, 1000 * share / 100.0);
    expect(SharePerEnemy(1000, share, 0) == 0 && SharePerEnemy(0, share, 3) == 0 && SharePerEnemy(-4, share, 3) == 0 && SharePerEnemy(1000, 0, 3) == 0,
           "nobody to share with, nothing to share, no share: nothing");

    // Contagion: the nearest few, nearest first, a tie keeping its order.
    std::vector<double> const distances{9, 2, 5, 2, 30};
    auto const near = Nearest(distances, targets);
    expect(near.size() == targets, "as many as asked for", double(near.size()), double(targets));
    expect(near.size() == 3 && near[0] == 1 && near[1] == 3 && near[2] == 2, "the nearest are chosen nearest first, a tie in its order",
           near.empty() ? -1.0 : double(near[0]), 1);
    expect(Nearest(distances, 99).size() == distances.size(), "fewer enemies than asked for, all of them");
    expect(Nearest(distances, 0).empty() && Nearest({}, 3).empty(), "none asked for or none there, none chosen");

    // Valley of Death: the area's reach and its ticks over its seconds.
    expect(InArea(radius, radius) && InArea(0, radius) && !InArea(radius + 0.01, radius), "the edge of the area is in it");
    expect(!InArea(0, 0), "an area with no radius holds nothing");
    double clock = 0;
    unsigned struck = 0;
    int const updates = int(areaSeconds * 1000.0 / 67.0);
    for (int update = 0; update < updates; ++update)
        struck += Due(clock, 67, tick * 1000.0);
    expect(std::fabs(double(struck) - updates * 0.067 / tick) < 1.0, "a tick every interval in server updates of 67 ms", double(struck),
           updates * 0.067 / tick);

    // Death Toll: the share of the attacker's maximum Life.
    expect(std::fabs(LifeBack(1000, heal) - 1000 * heal / 100.0) < 1e-9, "the share of the maximum Life", LifeBack(1000, heal), 1000 * heal / 100.0);
    expect(LifeBack(0, heal) == 0 && LifeBack(1000, 0) == 0 && LifeBack(-5, heal) == 0 && LifeBack(1000, -3) == 0, "no Life, no share, no heal");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
