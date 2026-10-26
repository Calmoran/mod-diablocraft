// The real dc_crusader_buffs.h. The numbers come from argv (Celerity's, Rebirth's and Hardened Senses' sheet rows, read
// by test_crusader_buffs.py); nothing is typed in here.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_buffs.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Crusader::Buffs;

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
    // argv: seconds, per-stack number, max stacks
    if (argc < 4)
        return 2;
    std::uint64_t const ms = std::uint64_t(std::atof(argv[1]) * 1000.0);
    double const each = std::atof(argv[2]);
    unsigned const cap = unsigned(std::atoi(argv[3]));

    // A fresh buff has no stacks and is over.
    Held held;
    expect(Over(held, 0) && Worth(held, 0, each) == 0, "nothing is worn before the first cast");

    // The first cast is one stack for the whole time.
    expect(Add(held, 1000, ms, cap) == 1, "the first cast is one stack");
    expect(!Over(held, 1000 + ms - 1), "it lasts to the last millisecond", double(1000 + ms - 1), double(held.until));
    expect(Over(held, 1000 + ms), "it is over at the end time", double(1000 + ms), double(held.until));
    expect(Worth(held, 1000, each) == each, "one stack is worth its number", Worth(held, 1000, each), each);
    expect(Worth(held, 1000 + ms, each) == 0, "a buff that ran out is worth nothing");

    // A second cast inside the time adds a stack up to the cap and restarts the whole time.
    Held stacked;
    unsigned last = 0;
    for (unsigned cast = 0; cast < cap + 2; ++cast)
        last = Add(stacked, 5000 + cast * 100, ms, cap);
    expect(last == cap, "stacks stop at the cap", last, cap);
    expect(Worth(stacked, 5000, each) == each * cap, "the worth is the number for every stack", Worth(stacked, 5000, each),
           each * cap);
    expect(stacked.until == 5000 + (cap + 1) * 100 + ms, "a later cast restarts the whole time", double(stacked.until),
           double(5000 + (cap + 1) * 100 + ms));

    // A buff that ran out starts again from one stack, not from the old count.
    Held again;
    for (unsigned cast = 0; cast < cap; ++cast)
        Add(again, 9000, ms, cap);
    expect(Add(again, 9000 + ms + 1, ms, cap) == 1, "after it ran out the next cast is one stack again");

    // A cast that brings several stacks (one for each enemy hit) adds them all, up to the cap, and 0 is one.
    Held pack;
    expect(Add(pack, 0, ms, cap, 2) == (cap < 2 ? cap : 2), "two enemies add two stacks, up to the cap");
    Held many;
    expect(Add(many, 0, ms, cap, cap + 5) == cap, "a crowd stops at the cap", Add(many, 1, ms, cap, cap + 5), cap);
    Held none;
    expect(Add(none, 0, ms, cap, 0) == 1, "no count is one stack");

    // A cap of 0 never means no stacks.
    Held lone;
    expect(Add(lone, 0, ms, 0) == 1 && Add(lone, 1, ms, 0) == 1, "a cap below one is one");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
