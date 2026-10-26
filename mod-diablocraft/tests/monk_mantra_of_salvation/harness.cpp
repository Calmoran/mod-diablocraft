// diablocraft-puvah (Monk 2.3.19): the real dc_monk_mantra_of_salvation.h. Every number comes from argv (the sheets'
// and the tunables', read by test_monk_mantra_of_salvation.py); nothing is typed in here. Prints "cases=N" and exits 0,
// or names the first failing case and exits 1.
#include "classes/monk/dc_monk_mantra_of_salvation.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Salvation;

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
    // argv: passive resistance %, Perseverance's resistance %, active resistance %, Divine Protection threshold %,
    // its internal cooldown seconds, its shield seconds, a pulse's hold seconds
    if (argc < 8)
        return 2;
    double const passive = std::atof(argv[1]), perseverance = std::atof(argv[2]), active = std::atof(argv[3]),
                 threshold = std::atof(argv[4]), icd = std::atof(argv[5]), shield = std::atof(argv[6]),
                 hold = std::atof(argv[7]);

    // Perseverance replaces the passive's number; any other rune keeps it.
    expect(PassivePct(passive, std::nullopt) == passive, "no rune number, the skill's",
           PassivePct(passive, std::nullopt), passive);
    expect(PassivePct(passive, perseverance) == perseverance, "Perseverance's number replaces",
           PassivePct(passive, perseverance), perseverance);

    // The resistance gained is that percent of what the holder resists.
    expect(ResistanceGain(200, passive) == 200 * passive / 100, "a share of the baseline", ResistanceGain(200, passive),
           200 * passive / 100);
    expect(ResistanceGain(0, passive) == 0 && ResistanceGain(-50, passive) == 0, "no resistance, nothing gained");
    expect(ResistanceGain(200, 0) == 0 && ResistanceGain(200, -5) == 0, "no percent, nothing gained");

    // The active adds to the passive; Perseverance's passive and the active together.
    expect(TotalResistancePct(passive, active) == passive + active, "passive plus the active",
           TotalResistancePct(passive, active), passive + active);
    expect(TotalResistancePct(perseverance, active) == perseverance + active, "Perseverance plus the active");
    expect(TotalResistancePct(passive, 0) == passive && TotalResistancePct(0, active) == active, "either alone");
    expect(TotalResistancePct(-10, active) == active, "a negative number takes nothing off");

    // A pulse's hold: live up to its last millisecond, gone at its end.
    std::uint64_t const now = 50000, until = now + Millis(hold);
    expect(Millis(hold) > 0 && Millis(-1) == 0 && Millis(0) == 0, "seconds to milliseconds", double(Millis(hold)),
           hold * 1000);
    expect(Live(now, until) && Live(until - 1, until), "inside the hold");
    expect(!Live(until, until) && !Live(until + 5000, until), "at its end and after, gone");
    Timed worn{perseverance, until};
    expect(worn.Of(now) == perseverance && worn.Of(until - 1) == perseverance, "a worn number reads as itself");
    expect(worn.Of(until) == 0 && Timed{}.Of(now) == 0, "an ended or never worn number reads zero");

    // Divine Protection: strictly below the threshold, and once per cooldown.
    expect(ShieldOpens(threshold - 0.1, threshold, now, 0), "below the threshold opens it");
    expect(!ShieldOpens(threshold, threshold, now, 0), "exactly at it does not (reduced BELOW)");
    expect(!ShieldOpens(threshold + 40, threshold, now, 0), "above it does not");
    std::uint64_t const ready = now + Millis(icd);
    expect(!ShieldOpens(1, threshold, now, ready), "not before the cooldown ends");
    expect(!ShieldOpens(1, threshold, ready - 1, ready), "not a millisecond early");
    expect(ShieldOpens(1, threshold, ready, ready), "at the end of the cooldown again");
    Timed shielded{shield, now + Millis(shield)};
    expect(shielded.Of(now + Millis(shield) - 1) == shield && shielded.Of(now + Millis(shield)) == 0,
           "the shield lasts its seconds", shielded.Of(now + Millis(shield) - 1), shield);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
