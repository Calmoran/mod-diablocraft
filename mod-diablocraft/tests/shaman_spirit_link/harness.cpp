// The real dc_shaman_spirit_link.h, no core. Every number comes from argv (test_shaman_spirit_link.py reads the sheet and
// combat.csv): the skill's and Ancestral Chains' link size, the share and Thunder Link's, the elite share, Spirit Harvest's
// extension and cap, the link's damage and the two ticks. Prints "cases=N failures=M" and exits 0, or names each failing
// case and exits 1.
#include "classes/shaman/dc_shaman_spirit_link.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::SpiritLink;

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
    if (argc < 11)
        return 2;
    std::size_t const count = std::size_t(std::atof(argv[1])), chainsCount = std::size_t(std::atof(argv[2]));
    double const share = std::atof(argv[3]), thunder = std::atof(argv[4]), elitePct = std::atof(argv[5]),
                 extend = std::atof(argv[6]), cap = std::atof(argv[7]), perSecond = std::atof(argv[8]),
                 aura = std::atof(argv[9]), burn = std::atof(argv[10]);

    expect(RuneOf("Ancestral Chains") == Rune::AncestralChains && RuneOf("Searing Link") == Rune::SearingLink &&
               RuneOf("Frozen Link") == Rune::FrozenLink && RuneOf("Thunder Link") == Rune::ThunderLink &&
               RuneOf("Spirit Harvest") == Rune::SpiritHarvest,
           "each rune by its name");
    expect(RuneOf("") == Rune::None && RuneOf("Chain Frost") == Rune::None, "the skill and a stranger are no rune");

    // Who is linked: the target (distance 0) first, then the nearest, up to the cap.
    std::vector<double> distances = {9, 0, 14, 3, 7, 12, 1, 5, 11, 2, 13, 4, 6, 8, 10, 15, 6.5, 0.5};
    auto const members = Members(distances, count);
    expect(members.size() == count, "a cast links the skill's count", double(members.size()), double(count));
    expect(!members.empty() && members.front() == 1, "the target is linked first");
    bool nearest = true;
    for (std::size_t i = 1; i < members.size(); ++i)
        nearest = nearest && distances[members[i - 1]] <= distances[members[i]];
    expect(nearest, "nearest first");
    double farthestKept = 0;
    for (std::size_t index : members)
        farthestKept = std::max(farthestKept, distances[index]);
    unsigned closer = 0;
    for (double d : distances)
        closer += d < farthestKept;
    expect(closer <= members.size(), "nothing nearer is left out", double(closer), double(members.size()));
    expect(Members(distances, chainsCount).size() == std::min(chainsCount, distances.size()), "Ancestral Chains' count");
    expect(chainsCount > count, "Ancestral Chains links more");
    expect(Members({0, 4}, count).size() == 2, "fewer enemies than the cap link all of them");
    expect(Members({}, count).empty(), "no enemies, no link");

    // The share.
    expect(std::abs(Shared(1000, share, false, elitePct) - 1000 * share / 100) < 1e-9, "an ordinary enemy takes the share",
           Shared(1000, share, false, elitePct), 1000 * share / 100);
    expect(std::abs(Shared(1000, share, true, elitePct) - 1000 * share / 100 * elitePct / 100) < 1e-9,
           "an elite or a boss takes half", Shared(1000, share, true, elitePct), 1000 * share / 100 * elitePct / 100);
    expect(Shared(1000, share, true, elitePct) < Shared(1000, share, false, elitePct), "an elite takes less");
    expect(Shared(0, share, false, elitePct) == 0 && Shared(-5, share, false, elitePct) == 0 &&
               Shared(1000, 0, false, elitePct) == 0,
           "no damage or no share, nothing");
    expect(ShareOf(Rune::ThunderLink, share, thunder) == thunder && thunder > share, "Thunder Link's larger share");
    for (Rune rune : {Rune::None, Rune::AncestralChains, Rune::SearingLink, Rune::FrozenLink, Rune::SpiritHarvest})
        expect(ShareOf(rune, share, thunder) == share, "every other rune shares the skill's");

    // What is shared: a share and the link's own damage are not.
    expect(Shares(false, false), "a hit is shared");
    expect(!Shares(true, false), "a share is not shared again");
    expect(!Shares(false, true), "the link's own damage is not shared");

    // Spirit Harvest: each death adds its seconds, never past the cap.
    double extra = 0;
    for (int death = 0; death < 20; ++death)
    {
        double const next = Extended(extra, extend, cap);
        expect(next >= extra && next <= cap, "the extension only grows and stops at the cap", next, cap);
        extra = next;
    }
    expect(extra == cap, "enough deaths reach the cap", extra, cap);
    expect(Extended(0, extend, cap) == std::min(cap, extend), "one death adds its seconds", Extended(0, extend, cap), extend);

    // The link's own damage: the second's percent in ticks of the tick's seconds.
    expect(std::abs(TickPct(perSecond, aura) - perSecond * aura) < 1e-9, "a tick is the second's percent of its seconds");
    expect(std::abs(TickPct(perSecond, burn) - perSecond * burn) < 1e-9 && TickPct(perSecond, burn) < TickPct(perSecond, aura),
           "a burn tick is shorter");
    expect(TickSeconds(Rune::SearingLink, aura, burn) == burn, "Searing Link burns");
    for (Rune rune : {Rune::None, Rune::AncestralChains, Rune::FrozenLink, Rune::ThunderLink, Rune::SpiritHarvest})
        expect(TickSeconds(rune, aura, burn) == aura, "every other rune pulses");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
