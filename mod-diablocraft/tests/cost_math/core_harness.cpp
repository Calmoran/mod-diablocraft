/*
 * The payment path, run through the core's own arithmetic (spell rewrite
 * step 5).
 *
 * Everything a Fury cost goes through is here and none of it is a copy: the
 * module's conversions are its own `src/combat/dc_cost_math.h`, and the
 * combine that applies the player's modifiers is `Player::ApplySpellMod`
 * itself, extracted from the core pin with or without `core-patches/0014` and
 * compiled in. `core_shim.h` says how that is put together.
 *
 * So this harness answers two questions at once: what the patch does to the
 * arithmetic (the `stack` and `cooldown` cases below), and what the module's
 * own conversions cost in precision on the way through it (`cost` and
 * `tick`). `scripts/tests/combat/test_cost_math.py` drives it and states the bounds.
 *
 *     core_harness <cases.tsv>
 *
 * cases.tsv: kind, then the case's numbers.
 *   cost     <fury> <percent>                -> the Fury a cast is charged
 *   stack    <fury> <percent...>             -> the same with several auras
 *   casts    <fury> <percent> <count>        -> the Fury `count` casts take, the core's charge and the part it
 *                                               dropped carried (dc_resource_carry.h)
 *   tick     <speed term> <flat term> <attacks per second> <frames> <fps> <pct>
 *                                            -> the Fury one channel tick debits
 *   schedule <frames> <attacks per second>   -> frames until the next tick
 *   costflat <cost> <flat> <percent>         -> a cost with a flat and a percentage reduction
 *   cooldown <milliseconds> <flat ms> <percent>  -> the cooldown that is set
 *   duration <milliseconds> <percent>        -> the duration that is applied
 */

#include "core_shim.h"
#include "../../src/classes/dc_resource_carry.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace
{
    using DC::Combat::CostMath::ChannelRate;
    using DC::Combat::CostMath::CostScaleSeconds;
    using DC::Combat::CostMath::Fury;
    using DC::Combat::CostMath::Rage;
    using DC::Combat::CostMath::ScheduleFrames;

    // A cast: the record's Rage units through the core, back to Fury.
    double Cast(double fury, std::vector<double> const& percents)
    {
        return Fury(DCTest::CostThroughCore(Rage(fury), percents));
    }

    // A channel tick: the module asks the core what its modifiers make of a
    // probe cost, applies that to the Fury-per-second rate and scales it by the
    // frames the tick covers. The pool takes its whole Rage units and carries
    // the rest to the next tick (Resources::WholeUnits, the registry harness).
    double Tick(double speedTerm, double flatTerm, double attacks, double frames,
                double framesPerSecond, double percent)
    {
        double const reduced = ChannelRate(speedTerm, flatTerm, attacks) *
                               DCTest::FactorThroughCore({percent});
        return reduced * CostScaleSeconds(frames, framesPerSecond);
    }
}

int main(int argc, char** argv)
{
    if (argc != 2)
    {
        std::fprintf(stderr, "usage: core_harness <cases.tsv>\n");
        return 2;
    }
    std::ifstream stream(argv[1]);
    std::string line;
    while (std::getline(stream, line))
    {
        if (line.empty())
            continue;
        std::istringstream cells(line);
        std::string kind;
        cells >> kind;
        if (kind == "cost" || kind == "stack")
        {
            double fury = 0;
            cells >> fury;
            std::vector<double> percents;
            for (double percent = 0; cells >> percent;)
                percents.push_back(percent);
            std::printf("%.6f\n", Cast(fury, percents));
        }
        else if (kind == "casts")
        {
            double fury = 0, percent = 0;
            int count = 0;
            cells >> fury >> percent >> count;
            double owed = 0, taken = 0;
            for (int cast = 0; cast < count; ++cast)
            {
                int32 const charged = DCTest::CostThroughCore(Rage(fury), {percent});
                float const exact = DCTest::ExactCostThroughCore(Rage(fury), {percent});
                taken += charged + DC::Resources::Carry::Whole(owed, DC::Resources::Carry::Dropped(exact, charged));
            }
            std::printf("%.6f\n", taken / DC::Combat::CostMath::RagePerFury);
        }
        else if (kind == "tick")
        {
            double speed = 0, flat = 0, attacks = 0, frames = 0, rate = 0, percent = 0;
            cells >> speed >> flat >> attacks >> frames >> rate >> percent;
            std::printf("%.6f\n", Tick(speed, flat, attacks, frames, rate, percent));
        }
        else if (kind == "schedule")
        {
            double frames = 0, attacks = 0;
            cells >> frames >> attacks;
            std::printf("%.6f\n", ScheduleFrames(frames, attacks));
        }
        else if (kind == "costflat")
        {
            int32 cost = 0, flat = 0;
            double percent = 0;
            cells >> cost >> flat >> percent;
            std::printf("%d\n", DCTest::CostFlatThroughCore(cost, flat, percent));
        }
        else if (kind == "cooldown")
        {
            int32 base = 0, flat = 0;
            double percent = 0;
            cells >> base >> flat >> percent;
            std::printf("%d\n", DCTest::CooldownThroughCore(base, flat, percent));
        }
        else if (kind == "duration")
        {
            int32 base = 0, percent = 0;
            cells >> base >> percent;
            std::printf("%d\n", DCTest::DurationThroughCore(base, percent));
        }
        else
        {
            std::fprintf(stderr, "unknown case: %s\n", kind.c_str());
            return 2;
        }
    }
    return 0;
}
