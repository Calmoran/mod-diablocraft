// The real dc_demon_hunter_grenade.h. The rune names and numbers come from argv (read from the sheets and the tunables
// by test_demon_hunter_grenade.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_grenade.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter::Grenade;

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
    // argv: the five runes A to E, Grenade Cache's grenades, the fan's spread, Cluster Grenades' pulses, the gap
    // between pulses and its total damage percent, the minimum throw and Cluster Grenades'.
    if (argc < 14)
        return 2;
    std::string const cold = argv[1], cluster = argv[2], cache = argv[3], tinkerer = argv[4], stun = argv[5];
    std::size_t const grenades = std::size_t(std::atoi(argv[6]));
    double const spread = std::atof(argv[7]), gap = std::atof(argv[9]), total = std::atof(argv[10]),
                 minimum = std::atof(argv[11]), clusterMinimum = std::atof(argv[12]);
    unsigned const pulses = unsigned(std::atoi(argv[8]));
    double const edge = std::atof(argv[13]);

    expect(RuneOf(cold) == Rune::ColdGrenade && RuneOf(cluster) == Rune::ClusterGrenades &&
               RuneOf(cache) == Rune::GrenadeCache && RuneOf(tinkerer) == Rune::Tinkerer &&
               RuneOf(stun) == Rune::StunGrenade,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {cold, cluster, cache, tinkerer, stun})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Grenade Cache: one grenade at the point aimed at and the rest balanced on either side of the line.
    auto fan = FanOffsets(grenades, spread);
    expect(fan.size() == grenades - 1, "one grenade is thrown at the point aimed at, the rest fan out",
           double(fan.size()), double(grenades - 1));
    expect(fan.size() == 2 && fan[0] == -spread && fan[1] == spread, "three grenades are one each side",
           fan.empty() ? 0 : fan[0], spread);
    auto four = FanOffsets(4, spread);
    expect(four.size() == 4 && four[0] == -1.5 * spread && four[1] == -0.5 * spread && four[2] == 0.5 * spread &&
               four[3] == 1.5 * spread,
           "an even count has none on the line");
    expect(FanOffsets(1, spread).empty() && FanOffsets(0, spread).empty(), "one grenade or none, no fan");

    // Cluster Grenades: the total shared by the pulses, the first at once and each after it a gap later.
    expect(std::fabs(PulsePct(total, pulses) * pulses - total) < 1e-9, "the pulses together deal the rune's total",
           PulsePct(total, pulses) * pulses, total);
    expect(PulsePct(total, 0) == total, "no pulses, the total at once");
    expect(PulseAfter(0, gap) == 0, "the first pulse is at once");
    expect(std::fabs(PulseAfter(2, gap) - 2 * gap) < 1e-9, "each pulse after it a gap later", PulseAfter(2, gap),
           2 * gap);

    // The minimum throw: a grenade aimed nearer lands that far away, one aimed at it or beyond lands where it was aimed.
    expect(ThrownYards(0, minimum) == minimum && ThrownYards(minimum - 0.5, minimum) == minimum, "a grenade aimed nearer is thrown the minimum",
           ThrownYards(minimum - 0.5, minimum), minimum);
    expect(ThrownYards(minimum, minimum) == minimum && ThrownYards(minimum + 0.5, minimum) == minimum + 0.5 && ThrownYards(75, minimum) == 75,
           "one aimed at the minimum or farther lands where it was aimed");
    expect(clusterMinimum > minimum && ThrownYards(minimum + 1, clusterMinimum) == clusterMinimum,
           "Cluster Grenades' minimum is the larger", clusterMinimum, minimum);

    // The falloff: all of the damage at the middle, the tunable's share at the edge and beyond, a straight line between.
    expect(KeptPct(0, 8, edge) == 100.0, "the middle takes all of it", KeptPct(0, 8, edge), 100);
    expect(std::fabs(KeptPct(8, 8, edge) - edge) < 1e-9 && std::fabs(KeptPct(20, 8, edge) - edge) < 1e-9, "the edge and beyond keep the edge's share",
           KeptPct(8, 8, edge), edge);
    expect(std::fabs(KeptPct(4, 8, edge) - (100.0 + edge) / 2.0) < 1e-9, "halfway out, halfway between", KeptPct(4, 8, edge), (100.0 + edge) / 2.0);
    expect(KeptPct(2, 8, edge) > KeptPct(6, 8, edge) && KeptPct(6, 8, edge) > edge, "the farther the less", KeptPct(2, 8, edge), KeptPct(6, 8, edge));
    expect(std::fabs((KeptPct(2, 8, edge) - KeptPct(4, 8, edge)) - (KeptPct(4, 8, edge) - KeptPct(6, 8, edge))) < 1e-9, "equal steps lose equal shares");
    expect(KeptPct(5, 0, edge) == 100.0 && KeptPct(5, -3, edge) == 100.0, "a blast with no radius loses nothing");
    expect(KeptPct(-1, 8, edge) == 100.0, "a point at the middle's far side is the middle");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
