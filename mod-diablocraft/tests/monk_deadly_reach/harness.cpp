// diablocraft-cvm3v (Monk 2.3.02): the real dc_monk_deadly_reach.h. Every number comes from argv (the tunables sheet's
// and monk_skill_values.csv's, read by test_monk_deadly_reach.py); nothing is typed in here but geometry. Prints
// "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_deadly_reach.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk;

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
    // argv: line yards (12), third hit reach (25), width (4), fists (6), cost reduction per enemy (8), Piercing Trident's
    // area percent (50)
    if (argc < 7)
        return 2;
    double const from = std::atof(argv[1]), to = std::atof(argv[2]), width = std::atof(argv[3]);
    unsigned const fists = unsigned(std::atof(argv[4]));
    double const perEnemy = std::atof(argv[5]);
    double const areaPct = std::atof(argv[6]);
    double const pi = std::acos(-1.0);

    // The longer line, facing +x from the origin: between `from` and `to` ahead, inside half the width to either side.
    auto in = [&](double dir, double x, double y) { return InCapsule(0, 0, dir, from, to, width, x, y); };
    expect(in(0, from + 1, 0), "an enemy just past the cast's own line is in");
    expect(in(0, to, 0), "the far end is in");
    expect(!in(0, to + 0.5, 0), "past the far end is out");
    expect(!in(0, from - 1, 0), "inside the cast's own line is not an extra");
    expect(in(0, 18, width / 2), "the edge of the width is in");
    expect(!in(0, 18, width / 2 + 0.1), "past the edge is out");
    expect(in(0, 18, -width / 2), "the other edge is in");
    expect(!in(0, 18, -width / 2 - 0.1), "and past it is out");
    expect(!in(0, -18, 0), "behind the Monk is out");
    // Turned: facing +y, the same enemy at (0, 18) is in and (18, 0) is out.
    expect(in(pi / 2, 0, 18), "the line follows the direction");
    expect(!in(pi / 2, 18, 0), "and what is beside it is out");
    // An origin that is not (0, 0).
    expect(InCapsule(100, -50, pi, from, to, width, 100 - 18, -50), "the origin moves the line");

    // Scattered Blows: the fists, on enemies picked at random.
    auto first = [](std::size_t) { return std::size_t(0); };
    auto last = [](std::size_t n) { return n - 1; };
    auto beyond = [](std::size_t n) { return n + 5; };
    expect(ScatterFists(0, fists, first).empty(), "no enemy, no fist");
    expect(ScatterFists(3, fists, first).size() == fists, "one fist per fist", ScatterFists(3, fists, first).size(),
           fists);
    expect(ScatterFists(1, fists, last).size() == fists, "one enemy takes them all",
           ScatterFists(1, fists, last).size(), fists);
    bool inside = true;
    for (std::size_t index : ScatterFists(4, fists, last))
        inside = inside && index == 3;
    expect(inside, "the pick says which enemy");
    inside = true;
    for (std::size_t index : ScatterFists(4, fists, beyond))
        inside = inside && index < 4;
    expect(inside, "a pick past the end is held to the last enemy");
    expect(ScatterFists(4, 0, first).empty(), "no fists, no hits");

    // Strike from Beyond: the discount of the enemies struck, capped, spent by one spender.
    NextSpender next;
    next.Add(perEnemy * 3);
    expect(std::fabs(next.pct - perEnemy * 3) < 1e-9, "three enemies, three discounts", next.pct, perEnemy * 3);
    next.Add(perEnemy);
    expect(std::fabs(next.pct - perEnemy * 4) < 1e-9, "a second third hit adds", next.pct, perEnemy * 4);
    next.Add(1000);
    expect(next.pct == 100.0, "the discount is the whole cost at most", next.pct, 100);
    next.Add(-5);
    expect(next.pct == 100.0, "a negative number takes nothing off");
    expect(next.Take() == 100.0, "the spender takes it");
    expect(next.pct == 0.0 && next.Take() == 0.0, "and it is spent");

    // The refund: the Spirit the discount takes off a cost of 50.
    expect(std::fabs(Refund(50, perEnemy) - 50 * perEnemy / 100) < 1e-9, "the refund is the share of the cost",
           Refund(50, perEnemy), 50 * perEnemy / 100);
    expect(std::fabs(Refund(50, 250) - 50) < 1e-9, "never more than the cost", Refund(50, 250), 50);
    expect(Refund(0, perEnemy) == 0.0 && Refund(50, 0) == 0.0, "no cost or no discount, nothing back");

    // Piercing Trident: the second and third hits' line is wider by the percent; nothing else is.
    double const wide = width * (1 + areaPct / 100);
    expect(std::fabs(WidenedWidth(width, areaPct, 2, true) - wide) < 1e-9, "the second hit's line is wider", WidenedWidth(width, areaPct, 2, true), wide);
    expect(std::fabs(WidenedWidth(width, areaPct, 3, true) - wide) < 1e-9, "the third hit's line is wider", WidenedWidth(width, areaPct, 3, true), wide);
    expect(WidenedWidth(width, areaPct, 1, true) == width, "the first hit's is not");
    expect(WidenedWidth(width, areaPct, 3, false) == width, "another rune's is not");
    expect(WidenedWidth(width, 0, 3, true) == width && WidenedWidth(width, -20, 3, true) == width, "no percent, no widening");
    // a strip 'wide' across holds an enemy beside the line that the plain strip misses
    expect(!InCapsule(0, 0, 0, 0, from, width, 5, width / 2 + 0.5) && InCapsule(0, 0, 0, 0, from, wide, 5, width / 2 + 0.5),
           "an enemy just beside the plain line is in the wider one");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
