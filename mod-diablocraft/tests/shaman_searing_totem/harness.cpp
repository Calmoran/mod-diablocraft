// The Searing Totem's rune rules (src/classes/shaman/dc_shaman_searing_totem_math.h), driven with the sheet's own
// numbers. Prints "cases=N failures=M" and exits 0, or names the failing case and exits 1.
#include "classes/shaman/dc_shaman_searing_totem_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace DC::Combat::Shaman::Searing;

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
    // argv: Searing Flames' most stacks, the percent each stack adds and the seconds they last, Frostflame's trigger
    // count, Stoneclaw's damage reduction percent and Capacitor's target count.
    if (argc < 7)
        return 2;
    unsigned const most = unsigned(std::atoi(argv[1]));
    double const perStack = std::atof(argv[2]), seconds = std::atof(argv[3]);
    unsigned const every = unsigned(std::atoi(argv[4]));
    double const reduction = std::atof(argv[5]);
    unsigned const jumps = unsigned(std::atoi(argv[6]));

    // Searing Flames: a stack a bolt, to the most, all ending together `seconds` after the last.
    std::uint64_t const lasts = Millis(seconds);
    Flames flames;
    flames = Stack(flames, 1000, most, seconds);
    expect(flames.stacks == 1 && Live(flames, 1000) == 1, "the first bolt is one stack");
    for (unsigned i = 1; i < most + 4; ++i)
        flames = Stack(flames, 1000 + i, most, seconds);
    expect(flames.stacks == most && Live(flames, 1100) == most, "stacks stop at the most");
    std::uint64_t const last = 1000 + most + 3;
    expect(Live(flames, last + lasts - 1) == most && Live(flames, last + lasts) == 0,
           "all stacks end the seconds after the last bolt");
    Flames again = Stack(flames, last + lasts, most, seconds);
    expect(again.stacks == 1 && Live(again, last + lasts) == 1, "stacks that ended start again at one");
    Flames kept = Stack(Stack(Flames{}, 0, most, seconds), lasts - 1, most, seconds);
    expect(kept.stacks == 2 && kept.untilMs == lasts - 1 + lasts, "a bolt in time adds a stack and moves the end");
    expect(Stack(Flames{}, 0, 0, seconds).stacks == 0, "no most, no stack");
    expect(Live(Flames{}, 0) == 0 && Live(Flames{}, 999999) == 0, "no flames, no stacks");
    expect(std::fabs(MorePct(most, perStack) - most * perStack) < 1e-12 && MorePct(0, perStack) == 0 &&
               MorePct(3, 0) == 0 && MorePct(3, -2) == 0,
           "each stack adds its percent, never a negative one");
    expect(Millis(0) == 0 && Millis(-1) == 0 && Millis(0.5) == 500, "seconds are milliseconds");

    // Frostflame: every Nth bolt freezes and the count starts again.
    unsigned bolts = 0;
    bool froze = false;
    for (unsigned i = 1; i < every; ++i)
        froze = froze || Freezes(bolts, every);
    expect(!froze && bolts == every - 1, "the bolts before the Nth do not freeze");
    expect(Freezes(bolts, every) && bolts == 0, "the Nth freezes and the count starts again");
    expect(!Freezes(bolts, every) && bolts == 1, "the next bolt is the first again");
    bolts = 3;
    expect(!Freezes(bolts, 0) && bolts == 0, "no count, no freeze");

    // Stoneclaw: the damage the Shaman takes while it stands.
    expect(std::fabs(TakenFactorOf(reduction) - (1.0 - reduction / 100.0)) < 1e-12 && TakenFactorOf(reduction) < 1.0,
           "the totem takes its percent off");
    expect(TakenFactorOf(0) == 1.0 && TakenFactorOf(-10) == 1.0 && TakenFactorOf(250) == 0.0,
           "no less than none and no more than all");

    // Capacitor: the bolt jumps to the nearest enemy it has not been on, `jumps` times. Enemies are numbers on a line
    // at their own place.
    std::vector<double> const place{0, 4, 9, 5, 30, 6.5};
    auto const near = [&](int)
    { return std::vector<int>{0, 1, 2, 3, 5}; }; // the enemies in reach of any (the far one, 4, is not)
    auto const distance = [&](int a, int b) { return std::fabs(place[std::size_t(a)] - place[std::size_t(b)]); };
    std::vector<int> const walk = Walk(0, jumps, near, distance);
    expect(walk.size() == jumps, "it jumps as many times as it is told");
    expect(walk.size() >= 2 && walk[0] == 1 && walk[1] == 3, "each jump goes to the nearest enemy it has not been on");
    bool repeats = false;
    for (std::size_t i = 0; i < walk.size(); ++i)
        for (std::size_t j = i + 1; j < walk.size(); ++j)
            repeats = repeats || walk[i] == walk[j];
    expect(!repeats && std::find(walk.begin(), walk.end(), 0) == walk.end(),
           "it never goes back to an enemy it has been on, the first included");
    expect(Walk(0, 0, near, distance).empty(), "no jumps, no walk");
    expect(Walk(0, 99, near, distance).size() == 4, "it stops when no enemy is left");
    auto const nobody = [&](int) { return std::vector<int>{0}; };
    expect(Walk(0, jumps, nobody, distance).empty(), "an enemy alone is not jumped from");
    expect(Next({}) == -1 && Next({{3.0, true}, {1.0, true}}) == -1, "none to go to, none chosen");
    expect(Next({{5.0, false}, {2.0, false}, {2.0, false}}) == 1, "the nearest, the first of equals");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
