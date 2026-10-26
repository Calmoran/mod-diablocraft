// The Earthbind Totem's rules (src/classes/shaman/dc_shaman_earthbind_totem_math.h), driven with the sheet's own
// numbers. Prints "cases=N failures=M" and exits 0, or names the failing case and exits 1.
#include "classes/shaman/dc_shaman_earthbind_totem_math.h"

#include <cstdio>
#include <cstdlib>
#include <unordered_set>

using namespace DC::Combat::Shaman::Earthbind;

static int failures = 0;
static int cases = 0;

static void expect(bool ok, char const* what)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s\n", what);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    // argv: the totem's radius in yards, Glacial Ground's damage taken percent and how long a mark holds in seconds.
    if (argc < 4)
        return 2;
    double const radius = std::atof(argv[1]), glacial = std::atof(argv[2]), hold = std::atof(argv[3]);

    // Earthgrab: each enemy is met for the first time once.
    std::unordered_set<std::uint64_t> seen;
    expect(FirstEntry(seen, 7), "the first time the totem meets an enemy");
    expect(!FirstEntry(seen, 7) && !FirstEntry(seen, 7), "never the second time");
    expect(FirstEntry(seen, 8) && seen.size() == 2, "another enemy is its own first time");

    // A mark holds for the seconds from the look that put it, and not a millisecond longer.
    std::uint64_t const until = HeldUntil(5000, hold);
    expect(until == 5000 + Millis(hold) && Millis(hold) > 0, "a mark ends the hold after the look");
    expect(Marked(until, until - 1) && !Marked(until, until) && !Marked(until, until + 1),
           "marked until the end and no longer");
    expect(HeldUntil(5000, 0) == 0 && HeldUntil(5000, -1) == 0 && !Marked(HeldUntil(5000, 0), 5000),
           "no hold, no mark");
    expect(Millis(0.5) == 500 && Millis(0) == 0 && Millis(-2) == 0, "seconds are milliseconds");

    // The radius: the edge is within, past it is not, no radius reaches nothing.
    expect(Within(radius, radius) && Within(0, radius) && !Within(radius + 0.01, radius),
           "the edge of the radius is within it");
    expect(!Within(1, 0) && !Within(0, 0) && !Within(1, -5), "no radius reaches nothing");

    // Glacial Ground: a marked enemy takes the rune's percent more, an unmarked one nothing, and a negative percent
    // never less.
    expect(MorePct(true, glacial) == glacial && glacial > 0, "a marked enemy takes the percent");
    expect(MorePct(false, glacial) == 0, "an unmarked enemy takes nothing more");
    expect(MorePct(true, 0) == 0 && MorePct(true, -4) == 0, "no percent, and never a negative one");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
