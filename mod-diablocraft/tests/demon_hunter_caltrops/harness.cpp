// The real dc_demon_hunter_caltrops.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_caltrops.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/demon_hunter/dc_demon_hunter_caltrops.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Caltrops;

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
    // argv: the five runes A to E, then the most traps, Jagged Spikes' damage and seconds, the tick, the wait in seconds, the trap's seconds.
    if (argc < 12)
        return 2;
    std::string const jagged = argv[1], hooked = argv[2], torturous = argv[3], carved = argv[4], bait = argv[5];
    std::size_t const most = std::size_t(std::atoi(argv[6]));
    double const damage = std::atof(argv[7]), seconds = std::atof(argv[8]), tick = std::atof(argv[9]), wait = std::atof(argv[10]),
                 lasts = std::atof(argv[11]);

    expect(RuneOf(jagged) == Rune::JaggedSpikes && RuneOf(hooked) == Rune::HookedSpines && RuneOf(torturous) == Rune::TorturousGround &&
               RuneOf(carved) == Rune::CarvedStakes && RuneOf(bait) == Rune::BaitTheTrap,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {jagged, hooked, torturous, carved, bait})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Max Traps: laying one over the most takes away the oldest, one at a time, and the count never goes above the most.
    expect(Overflow(most - 1, most) == 0, "one under the most, nothing goes", double(Overflow(most - 1, most)), 0);
    expect(Overflow(most, most) == 1, "at the most, the oldest goes", double(Overflow(most, most)), 1);
    expect(Overflow(most + 2, most) == 3, "two over, three go", double(Overflow(most + 2, most)), 3);
    expect(Overflow(7, 0) == 0, "no limit, none go");
    std::size_t standing = 0, highest = 0;
    for (int laid = 0; laid < 3 * int(most); ++laid)
    {
        standing = standing - Overflow(standing, most) + 1;
        highest = standing > highest ? standing : highest;
    }
    expect(highest == most && standing == most, "laying trap after trap, no more than the most stand", double(highest), double(most));

    // Jagged Spikes: the ticks of the sprung trap together deal the sheet's damage.
    unsigned const ticks = Dot::Ticks(seconds, tick);
    expect(ticks > 1, "the trap ticks more than once", ticks, 2);
    expect(std::fabs(TickPct(damage, seconds, tick) * ticks - damage) < 1e-9, "the ticks make the damage", TickPct(damage, seconds, tick) * ticks, damage);
    expect(TickPct(damage, seconds, 0) == 0, "no tick length, no damage");

    // The wait: a trap goes away unsprung when its wait is over, and never when it has no limit.
    expect(!WaitedOut(wait * 1000 - 1, wait * 1000) && WaitedOut(wait * 1000, wait * 1000), "the wait is over at its limit");
    expect(!WaitedOut(1e12, 0), "no limit, it waits for ever");

    // A sprung trap held for its seconds in server updates of 67 ms (no divisor of the tick): it ticks at its cadence.
    double clock = 0;
    unsigned struck = 0;
    int const updates = int(lasts * 1000.0 / 67.0) + 1;
    for (int update = 0; update < updates; ++update)
        struck += Due(clock, 67, tick * 1000.0);
    expect(std::fabs(double(struck) - updates * 0.067 / tick) < 1.0, "a tick every interval", double(struck), updates * 0.067 / tick);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
