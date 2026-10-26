// The real dc_witch_doctor_locust_swarm.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_locust_swarm.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_locust_swarm.h"
#include "combat/dc_periodic_strike.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::LocustSwarm;

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
    // argv: the five runes A to E, then the swarm's damage and seconds, Searing Locusts' damage, the tick, the jump's
    // least and delta seconds, the chance Pestilence jumps twice, the cloud's damage, seconds and tick.
    if (argc < 16)
        return 2;
    std::string const searing = argv[1], pestilence = argv[2], cloud = argv[3], devouring = argv[4], diseased = argv[5];
    double const total = std::atof(argv[6]), seconds = std::atof(argv[7]), searingTotal = std::atof(argv[8]),
                 tick = std::atof(argv[9]), least = std::atof(argv[10]), delta = std::atof(argv[11]),
                 chance = std::atof(argv[12]), cloudTotal = std::atof(argv[13]), cloudSeconds = std::atof(argv[14]),
                 cloudTick = std::atof(argv[15]);

    expect(RuneOf(searing) == Rune::SearingLocusts && RuneOf(pestilence) == Rune::Pestilence &&
               RuneOf(cloud) == Rune::CloudOfInsects && RuneOf(devouring) == Rune::DevouringSwarm &&
               RuneOf(diseased) == Rune::DiseasedSwarm,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {searing, pestilence, cloud, devouring, diseased})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The swarm's ticks make its damage, and only Searing Locusts changes the total.
    unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
    expect(ticks > 1 && near(PeriodicStrike::TickPct(total, ticks) * ticks, total), "the ticks make the sheet's damage",
           PeriodicStrike::TickPct(total, ticks) * ticks, total);
    expect(SwarmTotal(Rune::SearingLocusts, total, searingTotal) == searingTotal &&
               SwarmTotal(Rune::DiseasedSwarm, total, cloudTotal) == total &&
               SwarmTotal(Rune::None, total, searingTotal) == total &&
               SwarmTotal(Rune::Pestilence, total, searingTotal) == total,
           "Searing Locusts alone has its own total", SwarmTotal(Rune::SearingLocusts, total, searingTotal),
           searingTotal);
    double left = seconds;
    unsigned count = 0;
    while (left > 0 && count < 1000)
    {
        left = Left(left, tick);
        ++count;
    }
    expect(count == ticks && left == 0, "the swarm ends on its last tick", count, ticks);

    // The jump waits the least plus up to the delta.
    expect(near(JumpDelay(least, delta, 0.0), least) && near(JumpDelay(least, delta, 1.0), least + delta) &&
               near(JumpDelay(least, delta, 0.5), least + delta / 2),
           "a jump waits the least plus a roll of the delta", JumpDelay(least, delta, 0.5), least + delta / 2);
    expect(near(JumpDelay(least, delta, 7.0), least + delta) && near(JumpDelay(least, delta, -3.0), least) &&
               JumpDelay(-1, -1, 0.5) == 0,
           "the roll and the seconds stay in their ranges");

    // Pestilence jumps to two when its roll is under its chance, every other swarm to one.
    expect(Jumps(Rune::Pestilence, chance, 0.0) == 2 && Jumps(Rune::Pestilence, chance, chance - 0.01) == 2,
           "Pestilence jumps twice under its chance", Jumps(Rune::Pestilence, chance, 0.0), 2);
    expect(Jumps(Rune::Pestilence, 50, 50.0) == 1 && Jumps(Rune::Pestilence, 0, 0.0) == 1, "and once at or past it");
    expect(Jumps(Rune::None, 100, 0.0) == 1 && Jumps(Rune::SearingLocusts, 100, 0.0) == 1 &&
               Jumps(Rune::DiseasedSwarm, 100, 0.0) == 1,
           "no other swarm jumps twice");

    // Diseased Swarm leaves a cloud for an enemy found dead with swarm left, not for one that lived or whose swarm
    // ended.
    expect(LeavesCloud(Rune::DiseasedSwarm, true, 3.0) && !LeavesCloud(Rune::DiseasedSwarm, false, 3.0) &&
               !LeavesCloud(Rune::DiseasedSwarm, true, 0.0),
           "a cloud for a death while swarmed only");
    expect(!LeavesCloud(Rune::Pestilence, true, 3.0) && !LeavesCloud(Rune::None, true, 3.0),
           "and only Diseased Swarm leaves one");

    // The cloud's pulses make its damage; the first a pulse after it forms and the last at its end.
    unsigned const pulses = PeriodicStrike::Ticks(cloudSeconds, cloudTick);
    expect(pulses > 1 && near(PeriodicStrike::TickPct(cloudTotal, pulses) * pulses, cloudTotal),
           "the cloud's pulses make its damage", PeriodicStrike::TickPct(cloudTotal, pulses) * pulses, cloudTotal);
    expect(CloudPulseMs(0, cloudTick) == std::uint32_t(cloudTick * 1000.0 + 0.5) &&
               CloudPulseMs(pulses - 1, cloudTick) == std::uint32_t(cloudSeconds * 1000.0 + 0.5),
           "the first pulse a pulse after, the last at the end", CloudPulseMs(pulses - 1, cloudTick),
           cloudSeconds * 1000.0);
    expect(CloudPulseMs(3, 0) == 0, "no interval, at once");

    // The shared pieces: the nearest enemy and what a tick returns.
    expect(!Nearest({}) && *Nearest({9, 3, 7}) == 1, "the swarm jumps to the nearest enemy");
    expect(near(PerTick(25, 0.5), 12.5) && PerTick(25, 0) == 0 && PerTick(-1, 0.5) == 0,
           "a tick returns its share of the second");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
