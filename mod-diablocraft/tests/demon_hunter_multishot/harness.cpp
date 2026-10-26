// The real dc_demon_hunter_multishot.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_multishot.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/demon_hunter/dc_demon_hunter_multishot.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Multishot;

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
    // argv: the five runes A to E, then Wind Chill's seconds, the enemies Suppression Fire knocks back, Arsenal's rockets, their warmup
    // and the seconds between them.
    if (argc < 11)
        return 2;
    std::string const broadside = argv[1], chill = argv[2], arsenal = argv[3], will = argv[4], suppression = argv[5];
    double const seconds = std::atof(argv[6]), warmup = std::atof(argv[9]), interval = std::atof(argv[10]);
    unsigned const count = unsigned(std::atoi(argv[7])), rockets = unsigned(std::atoi(argv[8]));

    expect(RuneOf(broadside) == Rune::FullBroadside && RuneOf(chill) == Rune::WindChill && RuneOf(arsenal) == Rune::Arsenal &&
               RuneOf(will) == Rune::FireAtWill && RuneOf(suppression) == Rune::SuppressionFire,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {broadside, chill, arsenal, will, suppression})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Wind Chill's window: open for its seconds from the moment of the hit, shut after.
    std::uint64_t const hit = 5000, closes = ClosesAt(hit, seconds);
    expect(closes == hit + std::uint64_t(seconds * 1000.0), "a window closes its seconds after the hit", double(closes), hit + seconds * 1000.0);
    expect(Open(closes, closes - 1) && !Open(closes, closes) && !Open(closes, closes + 1), "it is open up to its last millisecond");
    expect(!Open(ClosesAt(hit, 0), hit) && ClosesAt(hit, -2) == hit, "no seconds, no window");

    // Suppression Fire: the first few hits of the volley, nearest first.
    expect(KnockedBack(1, count) && KnockedBack(count, count), "the first enemy and the last of the count are knocked back");
    expect(!KnockedBack(count + 1, count), "the next one is not", count + 1, count);
    expect(!KnockedBack(0, count), "a hit outside a cast's enemies is not");

    // Arsenal: the first rocket after the warmup, the rest an interval apart.
    expect(rockets > 1, "more than one rocket", rockets, 2);
    expect(RocketDelayMs(0, warmup, interval) == std::uint32_t(warmup * 1000.0 + 0.5), "the first rocket leaves after the warmup", RocketDelayMs(0, warmup, interval), warmup * 1000.0);
    for (unsigned index = 1; index < rockets; ++index)
        expect(RocketDelayMs(index, warmup, interval) - RocketDelayMs(index - 1, warmup, interval) == std::uint32_t(interval * 1000.0 + 0.5),
               "each rocket an interval after the last", index, interval * 1000.0);
    expect(RocketDelayMs(2, 0, 0) == 0 && RocketDelayMs(0, -1, -1) == 0, "no warmup and no interval, at once");

    // The random pick of an enemy for a rocket (the shared rule).
    expect(PickAt(0.0, 5) == 0 && PickAt(1.0, 5) == 4 && PickAt(0.5, 0) == 0, "a roll picks among the enemies there are");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
