// diablocraft-80cml / n152h: the real dc_monk_mantras.h, the one "only one Mantra" state of the Monk's four Mantras.
// Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/monk/dc_monk_mantras.h"

#include <cstdint>
#include <cstdio>

using namespace DC::Combat::Monk;

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

int main()
{
    // The four Mantras' base spell ids stand in as 1..4 (Salvation, Retribution, Healing, Conviction); the Monks as
    // 10, 20.
    constexpr std::uint32_t mantras[4] = {1, 2, 3, 4};
    constexpr std::uint64_t one = 10, two = 20;
    constexpr std::uint64_t boostMs = 3000;

    // Nothing cast: every slotted Mantra's passive is on, at login with no press.
    for (std::uint32_t m : mantras)
        expect(Mantras::On(one, m), "nothing cast yet: this Mantra's passive is on");
    for (std::uint32_t m : mantras)
        expect(!Mantras::Boosted(one, m, 0), "and none is boosted");

    // A cast of any one turns the other three off, whichever files they live in.
    for (std::uint32_t cast : mantras)
    {
        Mantras::Cast(one, cast, 1000, boostMs);
        for (std::uint32_t m : mantras)
            expect(Mantras::On(one, m) == (m == cast), "only the Mantra cast last is on");
    }

    // The boost window: opens at the cast, runs its seconds, belongs to the cast Mantra only, a second press renews it.
    Mantras::Cast(one, 2, 5000, boostMs);
    expect(Mantras::Boosted(one, 2, 5000), "the window opens at the cast");
    expect(Mantras::Boosted(one, 2, 5000 + boostMs - 1), "it runs to the last millisecond");
    expect(!Mantras::Boosted(one, 2, 5000 + boostMs), "it ends after its seconds");
    expect(!Mantras::Boosted(one, 1, 5001), "another Mantra is never boosted by it");
    Mantras::Cast(one, 2, 6000, boostMs);
    expect(Mantras::Boosted(one, 2, 6000 + boostMs - 1), "a second press renews the window");
    Mantras::Cast(one, 4, 6500, boostMs);
    expect(!Mantras::Boosted(one, 2, 6501) && Mantras::Boosted(one, 4, 6501),
           "a cast of another ends the first window");

    // Two Monks do not share it.
    expect(Mantras::On(two, 1) && Mantras::On(two, 2) && !Mantras::Boosted(two, 4, 6501),
           "a second Monk that cast nothing has every passive on");
    Mantras::Cast(two, 3, 7000, boostMs);
    expect(Mantras::On(two, 3) && !Mantras::On(two, 4) && Mantras::On(one, 4) && !Mantras::On(one, 3),
           "each Monk has its own Mantra in force");

    // Logout: the next login starts with nothing cast.
    Mantras::Forget(one);
    expect(Mantras::On(one, 1) && Mantras::On(one, 3) && !Mantras::Boosted(one, 4, 6501),
           "a Monk who left starts afresh");
    expect(!Mantras::On(two, 1), "and the other Monk is untouched");

    // The id on an ally's stat contribution: one per Monk and per rune.
    expect(Mantras::Key(one, 500) != Mantras::Key(two, 500), "two Monks give an ally two contributions");
    expect(Mantras::Key(one, 500) != Mantras::Key(one, 501), "one Monk's two runes are two contributions");
    expect(Mantras::Key(one, 500) == Mantras::Key(one, 500), "and the key is stable");
    expect(Mantras::Key(0, 500) == 500, "a zero guid leaves the rune id as it was");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
