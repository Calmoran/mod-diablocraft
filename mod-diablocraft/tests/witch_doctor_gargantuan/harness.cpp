// The real dc_witch_doctor_gargantuan_math.h. The numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_gargantuan.py). Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_gargantuan_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::WitchDoctor::GargantuanRunes;

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
    // argv: Restless Giant's enemies and cooldown seconds; Big Stinker's weapon damage a second and the pause between
    // two pulses; the Gargantuan's swing seconds and Wrathful Protector's factor; the height of the smash's lift.
    if (argc < 8)
        return 2;
    unsigned const most = unsigned(std::atoi(argv[1]));
    double const cooldownSeconds = std::atof(argv[2]), perSecond = std::atof(argv[3]), tick = std::atof(argv[4]),
                 swingSeconds = std::atof(argv[5]), factor = std::atof(argv[6]), height = std::atof(argv[7]);

    // Restless Giant.
    expect(Enraged(most, most, false) && Enraged(most + 3, most, false), "a crowd of enough enrages it");
    expect(!Enraged(most - 1, most, false) && !Enraged(0, most, false), "a smaller crowd does not");
    expect(Enraged(0, most, true) && Enraged(1, most, true), "an elite enrages it alone");
    expect(!Enraged(1000, 0, false), "no number of enemies named, no crowd");
    std::uint64_t const cooldown = std::uint64_t(cooldownSeconds * 1000.0);
    expect(OffCooldown(std::nullopt, 0, cooldown), "the first time is free");
    expect(!OffCooldown(std::uint64_t(1000), 1000 + cooldown - 1, cooldown) &&
               OffCooldown(std::uint64_t(1000), 1000 + cooldown, cooldown),
           "free again after the cooldown, not a moment before");

    // Big Stinker.
    expect(near(PulsePct(perSecond, tick), perSecond * tick), "a pulse deals its share of the second's damage",
           PulsePct(perSecond, tick), perSecond * tick);
    expect(near(PulsePct(perSecond, 0.5) * 2, perSecond), "the pulses of a second add up to the sheet's damage");
    expect(PulsePct(perSecond, 0) == 0 && PulsePct(perSecond, -1) == 0 && PulsePct(0, tick) == 0 &&
               PulsePct(-5, tick) == 0,
           "no pause or no damage, no pulse");

    // Wrathful Protector.
    double const swing = swingSeconds * 1000.0;
    expect(near(Quickened(swing, factor), swing / factor) && Quickened(swing, factor) < swing,
           "a swing comes faster by the factor", Quickened(swing, factor), swing / factor);
    expect(Quickened(swing, 0) == swing && Quickened(swing, -1) == swing, "no factor, the normal swing");
    expect(Quickened(0, factor) == 0, "no swing stays none");
    Lift const lift = LiftSpeeds(height);
    expect(lift.z > 0 && near(lift.z * lift.z / (2 * 19.29110527038574), height),
           "the speed lifts the enemy the height", lift.z * lift.z / (2 * 19.29110527038574), height);
    expect(lift.xy > MinimumSpeedXY, "above the core's least sideways speed", lift.xy, MinimumSpeedXY);
    expect(LiftSpeeds(0).z == 0 && LiftSpeeds(-2).z == 0 && LiftSpeeds(height, 0).z == 0 && LiftSpeeds(height, -1).z == 0,
           "no height or no gravity, no lift");
    expect(LiftSpeeds(height * 2).z > lift.z, "a greater height needs a greater speed");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
