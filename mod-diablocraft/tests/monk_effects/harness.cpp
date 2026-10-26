// diablocraft-ucv5p (Monk timed effects): the real dc_monk_effects.h. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1. Times are in ms; the seconds and percentages are made up here, since the header holds no
// sheet number.
#include "classes/monk/dc_monk_effects.h"

#include <cmath>
#include <cstdio>

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

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

int main()
{
    Book book;
    expect(near(book.Total(0), 0), "an empty book is worth nothing");
    expect(near(book.LessFactor(0), 1.0), "an empty book cuts nothing");

    // A bonus lasts its time and not a millisecond more.
    book.Apply(1, 15, 1000, 10000);
    expect(near(book.Total(1000), 15), "a bonus counts at once");
    expect(near(book.Total(10999), 15), "a bonus counts until the last millisecond", book.Total(10999), 15);
    expect(near(book.Total(11000), 0), "a bonus is gone at its end", book.Total(11000), 0);
    expect(book.Empty(), "an expired entry is dropped");

    // Casting a key again refreshes it and does not stack with maxStacks 1.
    Book refresh;
    refresh.Apply(7, 10, 0, 5000);
    refresh.Apply(7, 10, 4000, 5000);
    expect(near(refresh.Total(4500), 10), "a refreshed key is not stacked", refresh.Total(4500), 10);
    expect(near(refresh.Total(8999), 10), "a refresh moves the end", refresh.Total(8999), 10);
    expect(near(refresh.Total(9000), 0), "and the new end is exact", refresh.Total(9000), 0);

    // Stacks: each cast adds one up to the cap, and the whole entry's end moves.
    Book stacks;
    for (int i = 0; i < 5; ++i)
        stacks.Apply(3, 5, i * 1000, 10000, 3);
    expect(stacks.Stacks(3, 5000) == 3, "stacks stop at the cap", stacks.Stacks(3, 5000), 3);
    expect(near(stacks.Total(5000), 15), "stacks add up", stacks.Total(5000), 15);
    expect(near(stacks.Total(13999), 15), "the refresh kept every stack", stacks.Total(13999), 15);
    expect(stacks.Stacks(3, 14000) == 0, "all stacks go together", stacks.Stacks(3, 14000), 0);
    Book one;
    one.Apply(3, 5, 0, 1000, 0); // a cap of 0 still holds one
    expect(one.Stacks(3, 0) == 1, "a cap of 0 is a cap of 1", one.Stacks(3, 0), 1);

    // Two keys add up; removing one leaves the other.
    Book two;
    two.Apply(1, 15, 0, 10000);
    two.Apply(2, 5, 0, 20000);
    expect(near(two.Total(5000), 20), "two keys add up", two.Total(5000), 20);
    expect(near(two.Total(15000), 5), "the shorter one ends alone", two.Total(15000), 5);
    two.Remove(2);
    expect(near(two.Total(15000), 0), "a removed key is gone", two.Total(15000), 0);

    // "Deals x% less": each entry cuts on its own, and nothing goes below 0.
    Book less;
    less.Apply(1, 20, 0, 10000);
    expect(near(less.LessFactor(0), 0.8), "20% less is 0.8", less.LessFactor(0), 0.8);
    less.Apply(2, 50, 0, 10000);
    expect(near(less.LessFactor(0), 0.4), "cuts multiply", less.LessFactor(0), 0.4);
    Book over;
    over.Apply(1, 60, 0, 1000, 2);
    over.Apply(1, 60, 0, 1000, 2);
    expect(near(over.LessFactor(0), 0.0), "two stacks of 60% cut to nothing, not below", over.LessFactor(0), 0);
    expect(near(over.LessFactor(1000), 1.0), "and are over after the time", over.LessFactor(1000), 1);

    // The ledger: one book per holder, reads never create one, and a big table is swept of the books that ran out.
    Ledger ledger(4);
    ledger.Of(10, 0).Apply(1, 10, 0, 1000);
    expect(ledger.Peek(11) == nullptr, "a read of a stranger makes no book");
    expect(ledger.Size() == 1, "and does not grow the table", ledger.Size(), 1);
    expect(ledger.Peek(10) && near(ledger.Peek(10)->Total(500), 10), "the holder's book is its own");
    ledger.Of(11, 0).Apply(1, 10, 0, 1000);
    ledger.Of(12, 0).Apply(1, 10, 0, 1000);
    ledger.Of(13, 0).Apply(1, 10, 0, 5000);
    expect(ledger.Size() == 4, "four holders", ledger.Size(), 4);
    ledger.Of(14, 2000).Apply(1, 10, 2000, 1000);
    expect(ledger.Size() == 2, "at the limit the books that ran out are swept", ledger.Size(), 2);
    expect(ledger.Peek(13) != nullptr && ledger.Peek(10) == nullptr, "the live one stays and the dead are gone");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
