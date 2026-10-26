// The real dc_shaman_overcharge.h, no core. Every number comes from argv (test_shaman_maelstrom.py reads combat.csv and
// the Storm Surge passive's sheet row): points per stack, base cap, Storm Surge's cap, damage per stack, seconds.
// Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_overcharge.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::Overcharge;

static int failures = 0;
static int cases = 0;

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
    if (argc < 6)
        return 2;
    double const perStack = std::atof(argv[1]);
    unsigned const base = unsigned(std::atof(argv[2])), surge = unsigned(std::atof(argv[3]));
    double const perStackPct = std::atof(argv[4]);
    std::uint64_t const ms = std::uint64_t(std::atof(argv[5]) * 1000.0);

    // The cap: the base, or Storm Surge's maximum for a Shaman who has the passive, never below the base.
    expect(Cap(base, false, surge) == base, "no passive: the base cap", Cap(base, false, surge), base);
    expect(Cap(base, true, surge) == surge, "Storm Surge raises the cap to its maximum", Cap(base, true, surge), surge);
    expect(Cap(base, true, 0) == base, "a passive that states no maximum leaves the base", Cap(base, true, 0), base);
    expect(surge > base, "Storm Surge's maximum is above the base", surge, base);

    // Nothing banked below a stack's worth; the points wait for the next overflow.
    Bank bank;
    expect(Add(bank, 1000, perStack - 1, perStack, base, ms) == 0, "9 points are no stack", bank.stacks, 0);
    expect(Add(bank, 1500, 1, perStack, base, ms) == 1, "the tenth point makes one", bank.stacks, 1);
    expect(bank.until == 1500 + ms, "the first stack starts the time", double(bank.until), double(1500 + ms));
    // Overflow in small pieces adds up as one big piece does: the pulse hands over tenths, and a hundred tenths of a
    // point are no exact binary fraction of ten.
    Bank pieces;
    unsigned const tenths = unsigned(perStack * 10);
    for (unsigned i = 0; i < tenths; ++i)
        Add(pieces, 1000, 0.1, perStack, 1000, ms);
    expect(pieces.stacks == 1, "a stack's worth of tenths is one stack", pieces.stacks, 1);
    Bank pieces5;
    for (int i = 0; i < 100; ++i)
        Add(pieces5, 1000, 0.5, perStack, 1000, ms);
    Bank whole;
    Add(whole, 1000, 50, perStack, 1000, ms);
    expect(pieces5.stacks == whole.stacks && whole.stacks == unsigned(50 / perStack), "pieces add up as a whole does",
           pieces5.stacks, whole.stacks);
    // One big overflow gives every stack it fills at once.
    Bank big;
    expect(Add(big, 0, perStack * 3 + 2, perStack, base, ms) == 3, "three stacks' worth gives three", big.stacks, 3);

    // The cap: more overflow than fits gains nothing past it, and the carry does not wait behind it.
    Bank capped;
    expect(Add(capped, 0, perStack * 100 + 3, perStack, base, ms) == base, "capped at the base", capped.stacks, base);
    expect(capped.stacks == base, "and the bank itself holds no more", capped.stacks, base);
    expect(capped.carry == 0, "nothing waits behind the cap", capped.carry);
    // The same overflow with Storm Surge reaches its maximum.
    Bank raised;
    expect(Add(raised, 0, perStack * 100, perStack, Cap(base, true, surge), ms) == surge,
           "Storm Surge's maximum is reachable", raised.stacks, surge);
    // A cap that fell with the passive takes the extra when the stacks are read.
    expect(Held(raised, 1, base) == base, "a lost passive cuts the held stacks to the base", Held(raised, 1, base),
           base);

    // A new stack restarts the time of all of them; a gain below a stack does not.
    Bank refresh;
    Add(refresh, 0, perStack, perStack, base, ms);
    std::uint64_t const first = refresh.until;
    Add(refresh, ms / 2, perStack / 2, perStack, base, ms);
    expect(refresh.until == first, "points short of a stack leave the time alone", double(refresh.until),
           double(first));
    Add(refresh, ms / 2, perStack / 2, perStack, base, ms);
    expect(refresh.stacks == 2 && refresh.until == ms / 2 + ms, "the second stack restarts the time for both",
           double(refresh.until), double(ms / 2 + ms));

    // Time: the stacks are gone from the moment they expire, and a late overflow starts from nothing.
    Bank lapse;
    Add(lapse, 0, perStack * 2, perStack, base, ms);
    expect(Held(lapse, ms - 1, base) == 2, "still held a moment before the end", Held(lapse, ms - 1, base), 2);
    expect(Held(lapse, ms, base) == 0 && Over(lapse, ms), "gone at the end", Held(lapse, ms, base), 0);
    expect(Add(lapse, ms + 1, perStack, perStack, base, ms) == 1, "an old bank starts again from one", lapse.stacks, 1);
    // The points toward a stack expire as a stack would.
    Bank stale;
    Add(stale, 0, perStack - 1, perStack, base, ms);
    expect(Add(stale, ms + 1, 1, perStack, base, ms) == 0, "stale points do not complete a stack", stale.stacks, 0);

    // Taking: a Secondary spends every stack, once.
    Bank spend;
    Add(spend, 0, perStack * 4, perStack, base, ms);
    expect(Take(spend, 1, base) == 4, "the next Secondary takes every stack", spend.stacks, 4);
    expect(Take(spend, 2, base) == 0, "and the one after finds none", Take(spend, 2, base), 0);
    Bank expired;
    Add(expired, 0, perStack * 4, perStack, base, ms);
    expect(Take(expired, ms + 1, base) == 0, "expired stacks are not taken", Take(expired, ms + 1, base), 0);

    // The damage: perStackPct for each stack taken, none for none.
    expect(DamagePct(0, perStackPct) == 0, "no stack, no bonus");
    expect(DamagePct(3, perStackPct) == 3 * perStackPct, "three stacks, three times the bonus",
           DamagePct(3, perStackPct), 3 * perStackPct);
    expect(DamagePct(surge, perStackPct) == surge * perStackPct, "a full Storm Surge bank, its maximum times the bonus",
           DamagePct(surge, perStackPct), surge * perStackPct);

    // The seconds shown: the time left, nothing when there are no stacks.
    Bank shown;
    expect(SecondsLeft(shown, 5) == 0, "no stacks, no seconds");
    Add(shown, 0, perStack, perStack, base, ms);
    expect(SecondsLeft(shown, 2000) == double(ms - 2000) / 1000.0, "the seconds left", SecondsLeft(shown, 2000),
           double(ms - 2000) / 1000.0);

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
