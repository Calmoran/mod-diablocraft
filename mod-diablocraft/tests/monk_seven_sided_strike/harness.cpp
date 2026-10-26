// diablocraft-7kbmf (Monk 2.3.12): the real dc_monk_seven_sided_strike.h. Every number comes from argv (the tunables
// sheet's and monk_skill_values.csv's, read by test_monk_seven_sided_strike.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_seven_sided_strike.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace DC::Combat::Monk::SevenSided;

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
    return std::fabs(a - b) < 1e-6;
}

// Who the `strikes` strikes go to over `standing` enemies, as the cast's event queue runs them.
static std::vector<int> Run(unsigned strikes, std::vector<bool> standing)
{
    std::vector<int> struck;
    int last = -1;
    for (unsigned i = 0; i < strikes; ++i)
    {
        last = NextTarget(last, standing);
        struck.push_back(last);
    }
    return struck;
}

int main(int argc, char** argv)
{
    // argv: skill damage %, Sudden Assault damage %, strikes, first strike s, interval s, burn %, burn s
    if (argc < 8)
        return 2;
    double const total = std::atof(argv[1]), assault = std::atof(argv[2]), strikes = std::atof(argv[3]),
                 first = std::atof(argv[4]), interval = std::atof(argv[5]), burn = std::atof(argv[6]),
                 burnSeconds = std::atof(argv[7]);
    unsigned const count = unsigned(strikes);

    // A strike is the total over the strikes: 5677 / 7 = 811 (the power file's SF_3 8.11), 8285 / 7.
    expect(near(StrikePct(total, strikes), total / 7), "a strike is a seventh of the skill", StrikePct(total, strikes),
           total / 7);
    expect(near(StrikePct(total, strikes) * count, total), "seven strikes deal the whole",
           StrikePct(total, strikes) * count, total);
    expect(std::fabs(StrikePct(total, strikes) - 811) < 0.5, "811% a strike (SF_3 8.11)", StrikePct(total, strikes),
           811);
    expect(near(StrikePct(assault, strikes), assault / 7), "Sudden Assault's strike", StrikePct(assault, strikes),
           assault / 7);
    expect(StrikePct(total, 0) == 0, "no strikes, no damage");

    // The timing: 0.1 s, then 0.15 s apart; the seventh at 1.0 s, inside the power's 1.3 s with its 0.3 s end.
    expect(StrikeAtMs(0, first * 1000, interval * 1000) == 100, "the first strike at 100 ms",
           double(StrikeAtMs(0, first * 1000, interval * 1000)), 100);
    expect(StrikeAtMs(1, first * 1000, interval * 1000) == 250, "the second at 250 ms",
           double(StrikeAtMs(1, first * 1000, interval * 1000)), 250);
    expect(StrikeAtMs(count - 1, first * 1000, interval * 1000) == 1000, "the seventh at 1000 ms",
           double(StrikeAtMs(count - 1, first * 1000, interval * 1000)), 1000);
    expect(StrikeAtMs(3, 0, 0) == 0, "open tunables: every strike at once");

    // The targets: one enemy takes all seven.
    std::vector<int> one = Run(count, {true});
    bool allOne = one.size() == count;
    for (int t : one)
        allOne &= t == 0;
    expect(allOne, "one enemy takes every strike");
    // Three enemies: 0 1 2 0 1 2 0 - three, two and two strikes.
    std::vector<int> three = Run(count, {true, true, true});
    int const want3[] = {0, 1, 2, 0, 1, 2, 0};
    bool ok3 = three.size() == 7;
    for (unsigned i = 0; ok3 && i < 7; ++i)
        ok3 &= three[i] == want3[i];
    expect(ok3, "three enemies are struck in turn, round and round");
    // Ten enemies: the first seven, one strike each.
    std::vector<int> ten = Run(count, std::vector<bool>(10, true));
    bool ok10 = true;
    for (unsigned i = 0; i < 7; ++i)
        ok10 &= ten[i] == int(i);
    expect(ok10, "ten enemies: the first seven, once each");
    // A fallen enemy is passed over, the list wraps.
    expect(NextTarget(-1, {false, true, true}) == 1, "the first standing one first");
    expect(NextTarget(1, {true, false, true}) == 2, "a fallen one is skipped");
    expect(NextTarget(2, {true, true, true}) == 0, "after the last, the first again");
    expect(NextTarget(0, {true, false, false}) == 0, "the only one standing again");
    expect(NextTarget(-1, {false, false}) == -1, "nobody standing, no target");
    expect(NextTarget(-1, {}) == -1, "no enemies, no target");

    // Incinerate's burn: the open tick builds none; a tick splits the total over whole ticks.
    expect(BurnTicks(burnSeconds, 0) == 0, "no tick length, no burn");
    expect(BurnTicks(burnSeconds, 0.5) == 6, "3 s at 0.5 s is 6 ticks", BurnTicks(burnSeconds, 0.5), 6);
    expect(BurnTicks(burnSeconds, 1.0) == 3, "3 s at 1 s is 3 ticks", BurnTicks(burnSeconds, 1.0), 3);
    expect(BurnTicks(burnSeconds, 0.7) == 4, "whole ticks only: 3 s at 0.7 s is 4", BurnTicks(burnSeconds, 0.7), 4);
    expect(near(TickPct(burn, 6) * 6, burn), "the ticks add up to the burn", TickPct(burn, 6) * 6, burn);
    expect(TickPct(burn, 0) == 0, "no ticks, no damage");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
