// The real dc_necromancer_bone_spikes_math.h. The rune names and numbers come from argv (read from the sheets and
// tunables by test_necromancer_bone_spikes.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_bone_spikes_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <vector>

using namespace DC::Combat::Necromancer::BoneSpikes;

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
    // argv: the line's length, the line's damage and its largest bonus, Bone Pillars' damage per second, Blood Spikes'
    // damage, duration and heal, then the five runes A to E
    if (argc < 14)
        return 2;
    double const length = std::atof(argv[1]), pathPct = std::atof(argv[2]), maxBonus = std::atof(argv[3]),
                 pillarsPct = std::atof(argv[4]), bleedPct = std::atof(argv[5]), bleedSeconds = std::atof(argv[6]),
                 healPct = std::atof(argv[7]);
    std::string const stun = argv[8], path = argv[9], pillars = argv[10], frost = argv[11], blood = argv[12];

    expect(RuneOf(stun) == Rune::SuddenImpact && RuneOf(path) == Rune::PathOfBones &&
               RuneOf(pillars) == Rune::BonePillars && RuneOf(frost) == Rune::FrostSpikes &&
               RuneOf(blood) == Rune::BloodSpikes,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {stun, path, pillars, frost, blood})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Bone Spikes") == Rune::None,
           "the base skill and a stranger are no rune");

    // Which runes deal their own hit (the engine's is none): the line and the pillars only.
    expect(DealsItsOwnHit(Rune::PathOfBones) && DealsItsOwnHit(Rune::BonePillars),
           "the line and the pillars deal their own");
    expect(!DealsItsOwnHit(Rune::None) && !DealsItsOwnHit(Rune::SuddenImpact) && !DealsItsOwnHit(Rune::FrostSpikes) &&
               !DealsItsOwnHit(Rune::BloodSpikes),
           "the others leave the engine's hit");

    // The line runs from (0,0) along +x, `length` long and 4 wide.
    expect(near(AlongTheLine(0, 0, 1, 0, 10, 1.5, length, 4), 10), "an enemy on the line is found at its distance", 10,
           0);
    expect(AlongTheLine(0, 0, 1, 0, 10, 2.5, length, 4) < 0, "an enemy past half the width is off the line");
    expect(AlongTheLine(0, 0, 1, 0, 10, 2.0, length, 4) >= 0, "an enemy at half the width is on the line");
    expect(AlongTheLine(0, 0, 1, 0, -1, 0, length, 4) < 0, "an enemy behind the start is off the line");
    expect(AlongTheLine(0, 0, 1, 0, length + 1, 0, length, 4) < 0, "an enemy past the end is off the line");
    expect(near(AlongTheLine(0, 0, 1, 0, length, 0, length, 4), length), "an enemy at the end is on the line", length,
           0);
    expect(near(AlongTheLine(0, 0, 0, 1, 0, 7, length, 4), 7), "the line follows its direction", 7, 0);
    expect(AlongTheLine(0, 0, 0, 1, 7, 0, length, 4) < 0, "an enemy beside a line pointing away is off it");
    expect(near(AlongTheLine(5, 5, 1, 0, 15, 5, length, 4), 10), "the line starts where the Necromancer stands", 10, 0);

    // The bonus grows with the distance: none at the start, the whole at the end, never beyond.
    expect(near(PathPct(pathPct, maxBonus, 0, length), pathPct), "no bonus at the Necromancer",
           PathPct(pathPct, maxBonus, 0, length), pathPct);
    expect(near(PathPct(pathPct, maxBonus, length, length), pathPct * (1 + maxBonus / 100)),
           "the whole bonus at the end", PathPct(pathPct, maxBonus, length, length), pathPct * (1 + maxBonus / 100));
    expect(near(PathPct(pathPct, maxBonus, length / 2, length), pathPct * (1 + maxBonus / 200)),
           "half the bonus halfway", PathPct(pathPct, maxBonus, length / 2, length), pathPct * (1 + maxBonus / 200));
    expect(near(PathPct(pathPct, maxBonus, length * 3, length), pathPct * (1 + maxBonus / 100)),
           "never more than the whole bonus");
    expect(near(PathPct(pathPct, -50, length, length), pathPct), "a negative bonus is none");
    expect(near(PathPct(pathPct, maxBonus, 10, 0), pathPct), "a line of no length has no bonus");

    // The pillars' enemies: the nearest, inside the reach, nearest first, no more than asked.
    std::vector<double> const around = {9.0, 3.0, 25.0, 3.0, 5.0};
    auto const two = Nearest(around, 20.0, 2);
    expect(two.size() == 2 && two[0] == 1 && two[1] == 3, "the two nearest, a tie keeping the candidate order");
    auto const all = Nearest(around, 20.0, 9);
    expect(all.size() == 4 && all[0] == 1 && all[3] == 0, "all inside the reach, none outside", double(all.size()), 4);
    expect(Nearest(around, 2.0, 2).empty(), "none inside a small reach");
    expect(Nearest({}, 20.0, 2).empty(), "no candidates, none");
    expect(Nearest(around, 20.0, 0).empty(), "none asked, none");
    expect(Nearest({20.0}, 20.0, 1).size() == 1, "an enemy at the reach is inside");

    // The bleed: whole ticks, equal shares, a heal split the same way.
    expect(Ticks(bleedSeconds, 1.0) == unsigned(bleedSeconds), "a tick a second fills the duration",
           Ticks(bleedSeconds, 1.0), bleedSeconds);
    expect(Ticks(bleedSeconds, bleedSeconds) == 1, "a tick as long as the duration is one tick");
    expect(Ticks(bleedSeconds, bleedSeconds * 2) == 0, "a tick longer than the duration is none");
    expect(Ticks(bleedSeconds, 0) == 0 && Ticks(0, 1.0) == 0 && Ticks(-1, 1.0) == 0,
           "no tick length or no time, no ticks");
    expect(Ticks(0.3, 0.1) == 3, "a tick is not lost to rounding", Ticks(0.3, 0.1), 3);
    expect(Ticks(2.0, 0.5) == 4, "ticks of half a second fill two seconds");
    unsigned const ticks = Ticks(bleedSeconds, 0.5);
    expect(near(TickShare(bleedPct, ticks) * ticks, bleedPct), "the ticks add back to the bleed",
           TickShare(bleedPct, ticks) * ticks, bleedPct);
    expect(near(TickShare(bleedPct, 0), 0), "no ticks, no share");
    expect(near(HealPerTick(100000, healPct, ticks) * ticks, 100000 * healPct / 100),
           "the heals add back to the share of Life", HealPerTick(100000, healPct, ticks) * ticks,
           100000 * healPct / 100);
    expect(near(HealPerTick(100000, healPct, 0), 0) && near(HealPerTick(0, healPct, 4), 0) &&
               near(HealPerTick(100000, 0, 4), 0),
           "no ticks, no Life or no percent: no heal");

    // Sudden Impact's internal cooldown (argv 13, in seconds): ready until the rune has stunned the enemy, then not ready
    // until the whole cooldown has passed, to the millisecond.
    std::uint64_t const icd = std::uint64_t(std::atof(argv[13]) * 1000 + 0.5);
    expect(icd > 0, "the cooldown is a time");
    expect(StunReady(false, 0, 0, icd), "an enemy never stunned is ready");
    expect(StunReady(false, 999999, 1, icd), "and its stale stamp does not matter");
    expect(!StunReady(true, 1000, 1000, icd), "just stunned: not ready");
    expect(!StunReady(true, 1000, 1000 + icd - 1, icd), "a millisecond short of the cooldown: not ready");
    expect(StunReady(true, 1000, 1000 + icd, icd), "at the cooldown: ready");
    expect(StunReady(true, 1000, 1000 + icd * 5, icd), "long after: ready");
    expect(!StunReady(true, 5000, 1000, icd), "a clock behind the stun is not ready");
    expect(StunReady(true, 1000, 1000, 0), "no cooldown: always ready");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
