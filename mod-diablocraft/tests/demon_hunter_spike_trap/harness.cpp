// The real dc_demon_hunter_spike_trap.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_spike_trap.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and
// exits 1.
#include "classes/demon_hunter/dc_demon_hunter_spike_trap.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter::SpikeTrap;

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
    // argv: the five runes A to E, the arming seconds, Impaling Spines' extra, Custom Trigger's arming, the blast radius, Custom
    // Trigger's and Lightning Rod's extra yards, the Scatter spacing, the traps Scatter lays, the gap between blasts in seconds,
    // the chain yards, the chain's targets, the hits and the damage of Lightning Rod.
    if (argc < 19)
        return 2;
    std::string const impaling = argv[1], echoing = argv[2], custom = argv[3], scatter = argv[4], rod = argv[5];
    double const arm = std::atof(argv[6]), extra = std::atof(argv[7]), customArm = std::atof(argv[8]), radius = std::atof(argv[9]),
                 customBonus = std::atof(argv[10]), rodBonus = std::atof(argv[11]), spacing = std::atof(argv[12]),
                 gap = std::atof(argv[14]), chain = std::atof(argv[15]);
    unsigned const count = unsigned(std::atoi(argv[13])), targets = unsigned(std::atoi(argv[16])), hits = unsigned(std::atoi(argv[17]));
    double const damage = std::atof(argv[18]);

    expect(RuneOf(impaling) == Rune::ImpalingSpines && RuneOf(echoing) == Rune::EchoingBlast && RuneOf(custom) == Rune::CustomTrigger &&
               RuneOf(scatter) == Rune::Scatter && RuneOf(rod) == Rune::LightningRod,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {impaling, echoing, custom, scatter, rod})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Arming: Impaling Spines takes longer, Custom Trigger its own, the rest the skill's.
    expect(ArmSeconds(Rune::None, arm, extra, customArm) == arm && ArmSeconds(Rune::EchoingBlast, arm, extra, customArm) == arm,
           "the skill and most runes arm in the skill's time", arm, 0);
    expect(ArmSeconds(Rune::ImpalingSpines, arm, extra, customArm) == arm + extra, "Impaling Spines arms later", arm + extra, 0);
    expect(ArmSeconds(Rune::CustomTrigger, arm, extra, customArm) == customArm, "Custom Trigger arms in its own time", customArm, 0);

    // The blast: Custom Trigger and Lightning Rod reach further, nothing else.
    expect(BlastRadius(Rune::None, radius, customBonus, rodBonus) == radius &&
               BlastRadius(Rune::Scatter, radius, customBonus, rodBonus) == radius,
           "the skill's blast is its radius", radius, 0);
    expect(BlastRadius(Rune::CustomTrigger, radius, customBonus, rodBonus) == radius + customBonus, "Custom Trigger reaches further",
           radius + customBonus, 0);
    expect(BlastRadius(Rune::LightningRod, radius, customBonus, rodBonus) == radius + rodBonus, "Lightning Rod reaches further",
           radius + rodBonus, 0);

    // Scatter: its traps lie side by side, centred on the aim, a spacing apart.
    auto laid = Layout(count, spacing);
    expect(laid.size() == count && count == 2, "Scatter lays the sheet's traps", double(laid.size()), double(count));
    expect(std::fabs(laid[0] + laid[1]) < 1e-9 && std::fabs(laid[1] - laid[0] - spacing) < 1e-9, "centred, a spacing apart",
           laid[1] - laid[0], spacing);
    expect(Layout(1, spacing).size() == 1 && Layout(1, spacing)[0] == 0, "one trap lies on the point");

    // The chain reaction: the first goes at once, the next a gap later, in order.
    expect(ExplosionDelayMs(0, gap) == 0, "the first trap goes at once");
    expect(ExplosionDelayMs(1, gap) == std::uint32_t(gap * 1000.0 + 0.5), "the second a gap later", double(ExplosionDelayMs(1, gap)),
           gap * 1000.0);
    expect(ExplosionDelayMs(3, gap) == std::uint32_t(3 * gap * 1000.0 + 0.5), "the fourth three gaps later");
    expect(ExplosionDelayMs(2, 0) == 0, "no gap, all at once");

    // What detonates: another spender, never the trap itself; a generator only for Custom Trigger.
    expect(Detonates(false, true, false, Rune::None), "a spender detonates");
    expect(!Detonates(true, true, false, Rune::None), "Spike Trap does not detonate itself");
    expect(!Detonates(false, false, true, Rune::None) && !Detonates(false, false, true, Rune::Scatter), "a generator alone does not");
    expect(Detonates(false, false, true, Rune::CustomTrigger), "with Custom Trigger a generator does");
    expect(!Detonates(false, false, false, Rune::CustomTrigger), "a skill that is neither does not");

    // Lightning Rod: the nearest within the chain yards, up to the sheet's targets, nearest first.
    std::vector<double> const field = {chain + 1, 3, 1, chain, 7, 2};
    auto picked = Chain(field, chain, targets);
    expect(picked.size() == targets && targets == 3, "the chain takes the sheet's targets", double(picked.size()), double(targets));
    expect(picked.size() == 3 && picked[0] == 2 && picked[1] == 5 && picked[2] == 1, "nearest first");
    expect(Chain(field, chain, 9).size() == 5, "an enemy beyond the chain yards is left out", double(Chain(field, chain, 9).size()), 5);
    expect(Chain({}, chain, targets).empty(), "no enemies, no chain");

    // The hits together deal the rune's damage.
    expect(std::fabs(HitPct(damage, hits) * hits - damage) < 1e-9, "the hits make the damage", HitPct(damage, hits) * hits, damage);
    expect(HitPct(damage, 0) == 0, "no hits, no damage");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
