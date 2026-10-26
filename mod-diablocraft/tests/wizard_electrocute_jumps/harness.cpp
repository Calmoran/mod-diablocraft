// diablocraft-d00zm: the real dc_wizard_chain.h. The numbers come from argv (wizard_skill_values.csv's target_count for
// the skill and for Chain Lightning, and the tunable jump radius, read by test_wizard_electrocute_jumps.py); the
// enemies are points on a line. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/wizard/dc_wizard_chain.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace DC::Combat::Wizard::Chain;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s\n", what);
        ++failures;
    }
}

// The walk over enemies standing at `xs` (index 0 is the one the bolt hits first); `near` names every enemy within the
// radius of the one it is on, as Combat::Enemies does.
static std::vector<int> Jumps(std::vector<double> const& xs, unsigned jumps, double radius, bool mayRehit = false)
{
    auto distance = [&](int a, int b) { return std::fabs(xs[a] - xs[b]); };
    auto near = [&](int on)
    {
        std::vector<int> out;
        for (int i = 0; i < int(xs.size()); ++i)
            if (distance(on, i) <= radius)
                out.push_back(i);
        return out;
    };
    return Walk(0, jumps, mayRehit, near, distance);
}

int main(int argc, char** argv)
{
    // argv: the skill's target_count, Chain Lightning's target_count, the jump radius in yards
    if (argc < 4)
        return 2;
    double const skill = std::atof(argv[1]), chain = std::atof(argv[2]), radius = std::atof(argv[3]);
    unsigned const base = JumpCount("", skill), lightning = JumpCount("Chain Lightning", chain);

    // How many: 2 more enemies (3 in all), Chain Lightning 10 in all (9 more), the two runes that do not jump none.
    expect(base == 2, "the skill jumps to 2 more enemies");
    expect(lightning == 9, "Chain Lightning electrocutes 10 in all");
    expect(JumpCount("Surge of Power", skill) == 2 && JumpCount("Forked Lightning", skill) == 2,
           "Surge of Power and Forked Lightning jump as the skill");
    expect(JumpCount("Lightning Blast", skill) == 0, "Lightning Blast's streaks do not jump");
    expect(JumpCount("Arc Lightning", skill) == 0, "Arc Lightning's cone does not jump");
    expect(JumpCount("", 0) == 0, "no count, no jump");

    double const step = radius / 3; // three steps to a jump's reach
    std::vector<double> row;
    for (int i = 0; i < 12; ++i)
        row.push_back(i * step);

    expect(Jumps({0}, base, radius).empty(), "a lone target: no jump");
    expect(Jumps({0, step}, base, radius) == std::vector<int>{1}, "a jump hits a second enemy");
    expect(Jumps(row, base, radius) == std::vector<int>({1, 2}), "the skill: two jumps down the line");
    expect(Jumps(row, lightning, radius) == std::vector<int>({1, 2, 3, 4, 5, 6, 7, 8, 9}),
           "Chain Lightning reaches nine more down the line");
    expect(Jumps(row, lightning, radius).size() > Jumps(row, base, radius).size(), "Chain Lightning reaches more");
    expect(Jumps({0, radius + 1}, base, radius).empty(), "an enemy beyond the radius is out of reach");
    expect(Jumps({0, radius}, base, radius) == std::vector<int>{1}, "an enemy at the radius is in reach");
    expect(Jumps({0, 2 * step, step}, base, radius) == std::vector<int>({2, 1}), "the nearest first");
    expect(Jumps({0, 2 * step, 4 * step}, base, radius) == std::vector<int>({1, 2}),
           "each jump measures from the enemy it is on, not the first");
    expect(Jumps({0, step}, base, radius) == std::vector<int>{1}, "no jump back to an enemy already hit");
    expect(Jumps({0, step}, base, radius, true) == std::vector<int>({1, 0}),
           "may re-hit (Myken's Ball of Hate): back to the first, never to itself");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
