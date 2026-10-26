// The real dc_demon_hunter_vengeance.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_demon_hunter_vengeance.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_vengeance.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <vector>

using namespace DC::Combat::DemonHunter::Vengeance;

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
    // argv: the five runes A to E, the sheet's side guns, the guns' multiplier, the cannons' multiplier, the spread's
    // start and width, the guns' share of an attack, Seethe's Hatred a second and its tick, the mortar's near and far
    // range.
    if (argc < 15)
        return 2;
    std::string const shadows = argv[1], heart = argv[2], mortar = argv[3], cannons = argv[4], seethe = argv[5];
    double const guns = std::atof(argv[6]), gunMultiplier = std::atof(argv[7]), cannonMultiplier = std::atof(argv[8]),
                 spreadMin = std::atof(argv[9]), spreadWidth = std::atof(argv[10]), share = std::atof(argv[11]),
                 perSecond = std::atof(argv[12]), tick = std::atof(argv[13]), nearYards = std::atof(argv[14]);
    double const farYards = argc > 15 ? std::atof(argv[15]) : 60;

    expect(RuneOf(shadows) == Rune::FromTheShadows && RuneOf(heart) == Rune::DarkHeart &&
               RuneOf(mortar) == Rune::PersonalMortar && RuneOf(cannons) == Rune::SideCannons &&
               RuneOf(seethe) == Rune::Seethe,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {shadows, heart, mortar, cannons, seethe})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The guns: the sheet's count for every rune but Side Cannons, whose multiplier gives a share of them.
    expect(GunCount(Rune::None, guns, gunMultiplier, cannonMultiplier) == unsigned(guns), "the guns the sheet counts",
           GunCount(Rune::None, guns, gunMultiplier, cannonMultiplier), guns);
    expect(GunCount(Rune::Seethe, guns, gunMultiplier, cannonMultiplier) == unsigned(guns),
           "a rune that changes no gun keeps them");
    expect(GunCount(Rune::SideCannons, guns, gunMultiplier, cannonMultiplier) ==
               unsigned(std::lround(guns * cannonMultiplier / gunMultiplier)),
           "the cannons are the multiplier's share", GunCount(Rune::SideCannons, guns, gunMultiplier, cannonMultiplier),
           guns * cannonMultiplier / gunMultiplier);
    expect(GunCount(Rune::None, 0, gunMultiplier, cannonMultiplier) == 0 &&
               GunCount(Rune::SideCannons, guns, 0, cannonMultiplier) == 0,
           "no guns, none");

    // A shot's angle: the start at roll 0, the far side of the spread at roll 1, a clamp beyond them.
    expect(near(Spread(spreadMin, spreadWidth, 0), spreadMin), "the spread starts where the file says",
           Spread(spreadMin, spreadWidth, 0), spreadMin);
    expect(near(Spread(spreadMin, spreadWidth, 1), spreadMin + spreadWidth), "and ends a width on",
           Spread(spreadMin, spreadWidth, 1), spreadMin + spreadWidth);
    expect(near(Spread(spreadMin, spreadWidth, 0.5), spreadMin + spreadWidth / 2), "the middle is the middle");
    expect(near(Spread(spreadMin, spreadWidth, 7), spreadMin + spreadWidth) &&
               near(Spread(spreadMin, spreadWidth, -7), spreadMin),
           "a roll past either end is held to it");

    // How often: the guns wait a share of an attack, the volley an attack, and faster attacks wait less.
    expect(near(GunCooldownSeconds(share, 1.0), share) && near(GunCooldownSeconds(share, 2.0), share / 2),
           "the guns wait their share of an attack", GunCooldownSeconds(share, 2.0), share / 2);
    expect(GunCooldownSeconds(share, 0) == 0 && GunCooldownSeconds(0, 1.0) == 0, "no attack speed, no wait");
    expect(near(VolleySeconds(1.0), 1.0) && near(VolleySeconds(4.0), 0.25), "the volley waits one attack",
           VolleySeconds(4.0), 0.25);
    expect(VolleySeconds(0) == 0, "no attack speed, no wait for the volley");
    expect(Ready(0, 5000, 10) && Ready(1000, 2000, 1.0) && !Ready(1000, 1999, 1.0), "ready on the moment, not before");
    expect(!Ready(5000, 4000, 1.0) && Ready(5000, 4000, 0), "a clock that ran back waits, and no wait is ready");

    // The second weapon's enemies: the nearest first, each shot the next, round again when there are fewer enemies than
    // shots.
    std::vector<double> distances{30.0, 5.0, 61.0, 12.0, 45.0};
    auto const three = Nearest(distances, 60, 3);
    expect(three.size() == 3 && three[0] == 1 && three[1] == 3 && three[2] == 0, "the nearest three, nearest first");
    auto const wrapped = Nearest({10.0, 20.0}, 60, 5);
    expect(wrapped.size() == 5 && wrapped[0] == 0 && wrapped[1] == 1 && wrapped[2] == 0 && wrapped[3] == 1 &&
               wrapped[4] == 0,
           "round again past the last enemy");
    expect(Nearest({61.0, 90.0}, 60, 2).empty() && Nearest({}, 60, 2).empty() && Nearest(distances, 60, 0).empty(),
           "no enemy near, none shot at");
    expect(Nearest({60.0}, 60, 1).size() == 1, "an enemy at the edge is within");

    // Personal Mortar's enemies: outside melee range, inside the far range, the edges included.
    auto const band = InBand({nearYards - 0.1, nearYards, 33.0, farYards, farYards + 0.1, 5.0}, nearYards, farYards);
    expect(band.size() == 3 && band[0] == 1 && band[1] == 2 && band[2] == 3,
           "the band includes both edges and nothing outside");
    expect(InBand({}, nearYards, farYards).empty(), "no enemy, no band");

    // Seethe and From the Shadows' freeze.
    expect(near(SeethePerTick(perSecond, tick), perSecond * tick), "a tick pays its share of the second",
           SeethePerTick(perSecond, tick), perSecond * tick);
    expect(SeethePerTick(perSecond, 0) == 0 && SeethePerTick(0, tick) == 0 && SeethePerTick(-3, tick) == 0,
           "no tick or no Hatred, none");
    expect(near(SeethePerTick(perSecond, tick) * (1.0 / tick), perSecond), "the ticks of a second pay the second");
    expect(FreezeReady(0, 100) && FreezeReady(100, 100) && !FreezeReady(101, 100), "a freeze waits for its cooldown");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
