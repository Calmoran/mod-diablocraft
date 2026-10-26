// The real dc_proc_math.h Scaled(): what a hit pays or heals, scaled by the proc coefficient of the skill that landed it. The
// numbers come from argv (read from the sheets by test_proc_scaling.py); nothing is typed in here. Prints "cases=N" and exits 0,
// or names the first failing case and exits 1.
#include "combat/dc_proc_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <optional>

using DC::Combat::Proc::Scaled;

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

int main(int argc, char** argv)
{
    // argv: Mortal Enemy's Hatred, Death Toll's percent of Life, the Demon Hunter's maximum Life, then the coefficients of
    // three attacks (a full one, Hungering Arrow's, Rapid Fire's smallest)
    if (argc < 7)
        return 2;
    double const hatred = std::atof(argv[1]), healPct = std::atof(argv[2]), maxLife = std::atof(argv[3]),
                 full = std::atof(argv[4]), arrow = std::atof(argv[5]), rapid = std::atof(argv[6]);
    double const heal = maxLife * healPct / 100.0;

    expect(near(Scaled(full, hatred), hatred * full), "a full attack pays the stated Hatred", Scaled(full, hatred), hatred * full);
    expect(near(Scaled(0.5, hatred), hatred / 2), "a half-coefficient hit pays half the Hatred", Scaled(0.5, hatred), hatred / 2);
    expect(near(Scaled(arrow, hatred), hatred * arrow), "Hungering Arrow pays its share", Scaled(arrow, hatred), hatred * arrow);
    expect(near(Scaled(rapid, hatred), hatred * rapid), "Rapid Fire pays a sliver", Scaled(rapid, hatred), hatred * rapid);
    expect(near(Scaled(0.5, heal), heal / 2), "a half-coefficient hit heals half", Scaled(0.5, heal), heal / 2);
    expect(near(Scaled(full, heal), heal * full), "a full attack heals the stated share", Scaled(full, heal), heal * full);
    expect(Scaled(rapid, hatred) < Scaled(arrow, hatred), "a smaller coefficient pays less");
    expect(Scaled(std::nullopt, hatred) == 0.0, "a hit that states no coefficient pays nothing");
    expect(Scaled(std::nullopt, heal) == 0.0, "a hit that states no coefficient heals nothing");
    expect(Scaled(0.0, hatred) == 0.0, "a zero coefficient pays nothing");
    expect(Scaled(-0.5, hatred) == 0.0, "a negative coefficient pays nothing");
    expect(Scaled(full, 0.0) == 0.0, "no amount, nothing");
    expect(Scaled(full, -3.0) == 0.0, "a negative amount is nothing, never a drain");
    expect(near(Scaled(2.0, hatred), hatred * 2), "a coefficient above one pays more", Scaled(2.0, hatred), hatred * 2);

    // the coefficient a landing hit rolls: a pet's blow its own attack's (none if its attack states none), any other hit its spell's
    using DC::Combat::Proc::Landing;
    expect(Landing(false, 1.0, 0.25) == std::optional<double>(0.25), "an ordinary hit rolls its spell's");
    expect(Landing(true, 1.0, 0.25) == std::optional<double>(1.0), "a pet's blow rolls its own attack's, not the skill's");
    expect(!Landing(true, std::nullopt, 0.25).has_value(), "a pet whose attack states none rolls none, not the skill's");
    expect(!Landing(false, 1.0, std::nullopt).has_value(), "an ordinary hit that states none rolls none");
    expect(Landing(true, 0.0, 0.25) == std::optional<double>(0.0), "a pet whose attack states 0 rolls 0");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
