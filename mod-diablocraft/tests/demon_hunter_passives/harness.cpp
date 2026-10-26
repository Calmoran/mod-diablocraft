// The real dc_demon_hunter_passives.h. The names and numbers come from argv (read from the sheets by
// test_demon_hunter_passives.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_passives.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using namespace DC::Combat::DemonHunter::Passive;

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
    // argv: Night Stalker's addition, a primary's generation, Steady Aim's radius, its duration, Cull the Weak's percent, Brooding's most
    // stacks and reset seconds, Custom Engineering's duration percent and its most Sentries and Spike Traps, then
    // Ballistics' damage percent and proc chance, Ambush's threshold and percent, Awareness's heal percent and seconds, Single Out's
    // yards, Grenadier's radius percent, Sharpshooter's reset delay and its crit chance for a stack, Grenadier's damage percent, then the skills Tactical Advantage
    // answers.
    if (argc < 24)
        return 2;
    double const bonus = std::atof(argv[1]), generated = std::atof(argv[2]), radius = std::atof(argv[3]), seconds = std::atof(argv[4]),
                 cull = std::atof(argv[5]), reset = std::atof(argv[7]), engineering = std::atof(argv[8]),
                 sentries = std::atof(argv[9]), traps = std::atof(argv[10]);
    unsigned const most = unsigned(std::atoi(argv[6]));
    double const rocketPct = std::atof(argv[11]), procPct = std::atof(argv[12]), threshold = std::atof(argv[13]),
                 ambush = std::atof(argv[14]), healPct = std::atof(argv[15]), vanish = std::atof(argv[16]),
                 alone = std::atof(argv[17]), grenadier = std::atof(argv[18]), delay = std::atof(argv[19]),
                 perStack = std::atof(argv[20]), leechShare = std::atof(argv[21]), grenadierPct = std::atof(argv[22]);
    std::vector<std::string> skills;
    for (int i = 23; i < argc; ++i)
        skills.push_back(argv[i]);

    // A Hatred spender is no Primary and costs Hatred, in the record or paid by the module.
    expect(SpendsHatred(false, true, false), "a skill with a Hatred cost");
    expect(SpendsHatred(false, false, true), "a skill whose Hatred the module pays");
    expect(!SpendsHatred(false, false, false), "a skill with no Hatred cost is no spender");
    expect(!SpendsHatred(true, true, true), "a Primary is no spender");

    // Tactical Advantage answers the tooltip's skills and no other.
    for (auto const& skill : skills)
        expect(TacticalAdvantageSkill(skill), "a skill the tooltip names");
    expect(skills.size() == 3, "the tooltip names three skills", double(skills.size()), 3);
    for (char const* other : {"Caltrops", "Hungering Arrow", "Evasive Fire", "Chakram", "", "Vengeance"})
        expect(!TacticalAdvantageSkill(other), "a skill the tooltip does not name");

    // Night Stalker: a Primary's generation and the addition; nothing for a skill that generates none or is no Primary.
    expect(std::fabs(GeneratedWith(true, generated, bonus) - (generated + bonus)) < 1e-9,
           "a Primary generates the addition too", GeneratedWith(true, generated, bonus), generated + bonus);
    expect(GeneratedWith(false, generated, bonus) == generated, "a skill that is no Primary gains nothing");
    expect(GeneratedWith(true, 0, bonus) == 0, "a Primary that generates nothing gains nothing");
    expect(GeneratedWith(true, generated, -3) == generated, "no negative addition");

    // Steady Aim: no enemy within the radius, the edge counted as within.
    expect(Clear({}, radius) && Clear({radius + 0.1, 40.0}, radius), "no enemy near is clear");
    expect(!Clear({radius, 40.0}, radius) && !Clear({1.0}, radius), "an enemy at the edge or inside is not");
    expect(Until(1000, seconds) == 1000 + std::uint64_t(std::llround(seconds * 1000.0)), "the bonus lasts its seconds",
           double(Until(1000, seconds)), 1000 + seconds * 1000.0);
    expect(Until(1000, 0) == 1000 && Until(1000, -2) == 1000, "no seconds, no time");

    // Cull the Weak: the percent against a slowed or chilled enemy, nothing against any other.
    expect(CullPct(true, cull) == cull && CullPct(false, cull) == 0 && CullPct(true, -5) == 0,
           "the percent against the slowed only");


    // Brooding: a stack for each whole second standing still, up to the most; moving holds them until the reset time has passed in one go.
    Still state;
    for (int i = 0; i < 25; ++i)
        state = BroodingStep(state, false, 100, most, reset);
    expect(state.stacks == 2, "two and a half seconds still is two stacks", state.stacks, 2);
    for (int i = 0; i < 100; ++i)
        state = BroodingStep(state, false, 100, most, reset);
    expect(state.stacks == most, "and no more than the most", state.stacks, most);
    state = BroodingStep(state, true, reset * 1000.0 - 100, most, reset);
    expect(state.stacks == most, "moving for less than the reset time keeps them", state.stacks, most);
    Still paused = BroodingStep(state, false, 100, most, reset);
    expect(paused.stacks == most && paused.movingMs == 0, "standing still again cancels the reset");
    state = BroodingStep(state, true, 100, most, reset);
    expect(state.stacks == 0, "moving on for the whole reset time takes them", state.stacks, 0);
    expect(BroodingStep(Still{}, true, 5000, most, reset).stacks == 0, "moving from nothing is nothing");

    // Archery: the weapon kinds in the hands.
    expect(WeaponOf(2, false) == Weapon::Bow && WeaponOf(2, true) == Weapon::Bow, "a bow is a bow in either grip");
    expect(WeaponOf(18, false) == Weapon::Crossbow && WeaponOf(18, true) == Weapon::HandCrossbow, "a crossbow is a hand crossbow when one-handed");
    expect(WeaponOf(7, true) == Weapon::None && WeaponOf(0, false) == Weapon::None, "no other weapon is one of them");
    expect(ArcheryOf(Weapon::Bow, Weapon::None).bow && !ArcheryOf(Weapon::Bow, Weapon::None).crossbow, "a bow gives the damage");
    expect(ArcheryOf(Weapon::Crossbow, Weapon::None).crossbow && !ArcheryOf(Weapon::Crossbow, Weapon::None).hand, "a crossbow gives the critical damage");
    expect(ArcheryOf(Weapon::HandCrossbow, Weapon::None).hand && !ArcheryOf(Weapon::HandCrossbow, Weapon::None).second,
           "a hand crossbow gives the critical chance");
    expect(ArcheryOf(Weapon::HandCrossbow, Weapon::HandCrossbow).hand && ArcheryOf(Weapon::HandCrossbow, Weapon::HandCrossbow).second,
           "a second hand crossbow gives the Hatred too");
    expect(ArcheryOf(Weapon::None, Weapon::HandCrossbow).hand, "a hand crossbow in the off hand gives the critical chance too");
    expect(!ArcheryOf(Weapon::None, Weapon::None).bow && !ArcheryOf(Weapon::None, Weapon::None).hand, "no weapon, nothing");

    // Numbing Traps and Custom Engineering.
    for (char const* skill : {"Fan of Knives", "Spike Trap", "Caltrops", "Grenade", "Sentry"})
        expect(NumbingTrapsSkill(skill), "a skill the tooltip names for Numbing Traps");
    expect(!NumbingTrapsSkill("Impale") && !NumbingTrapsSkill("Smoke Screen"), "and no other");
    expect(std::fabs(DurationFactorOf(true, "Caltrops", engineering) - (1.0 + engineering / 100.0)) < 1e-9, "Custom Engineering lengthens Caltrops");
    expect(DurationFactorOf(true, "Sentry", engineering) > 1 && DurationFactorOf(true, "Marked for Death", engineering) > 1, "and the other three");
    expect(DurationFactorOf(false, "Caltrops", engineering) == 1 && DurationFactorOf(true, "Vengeance", engineering) == 1, "not off, not another skill");
    expect(MostStandingOf(true, 2, sentries) == unsigned(sentries) && MostStandingOf(true, 4, traps) == unsigned(traps), "the larger numbers");
    expect(MostStandingOf(false, 2, sentries) == 2 && MostStandingOf(true, 9, traps) == 9, "off, or already more, it stays");


    // Grenadier: the grenades, their larger explosion and the ring it adds.
    expect(GrenadeSkill("Grenade", "") && GrenadeSkill("Grenade", "Cold Grenade") && GrenadeSkill("Rapid Fire", "Bombardment") &&
               GrenadeSkill("Vengeance", "Personal Mortar"),
           "the grenades");
    expect(GrenadeSkill("Strafe", "Demolition") && GrenadeSkill("Rain of Vengeance", "Anathema"), "Demolition's and Anathema's grenades");
    expect(!GrenadeSkill("Rapid Fire", "Frost Shots") && !GrenadeSkill("Vengeance", "Seethe") && !GrenadeSkill("Impale", ""), "and no other skill");
    expect(!GrenadeSkill("Strafe", "Rocket Storm") && !GrenadeSkill("Strafe", "") && !GrenadeSkill("Rain of Vengeance", "Stampede") && !GrenadeSkill("Rain of Vengeance", ""),
           "the other runes of those skills are no grenades");
    // Cluster Arrow's hits are not all grenades (its impact and rockets are not), so its grenades ask the factor themselves: no record-wide answer.
    expect(!GrenadeSkill("Cluster Arrow", "") && !GrenadeSkill("Cluster Arrow", "Cluster Bombs"), "Cluster Arrow is no grenade as a whole");
    expect(GrenadeRadiusSkill("Cluster Arrow", "") && GrenadeRadiusSkill("Cluster Arrow", "Cluster Bombs") && GrenadeRadiusSkill("Strafe", "Demolition") &&
               GrenadeRadiusSkill("Grenade", "") && !GrenadeRadiusSkill("Strafe", "Rocket Storm") && !GrenadeRadiusSkill("Multishot", ""),
           "but its grenades' explosion grows");
    // Spike Trap: the blast of every rune grows, and its damage is not a grenade's.
    expect(GrenadeRadiusSkill("Spike Trap", "") && GrenadeRadiusSkill("Spike Trap", "Scatter") && GrenadeRadiusSkill("Spike Trap", "Custom Trigger"),
           "the Spike Trap's blast grows with Grenadier");
    expect(!GrenadeSkill("Spike Trap", "") && !GrenadeSkill("Spike Trap", "Lightning Rod") && !GrenadeRadiusSkill("Caltrops", "") && !GrenadeRadiusSkill("Sentry", ""),
           "but its damage does not, and no other trap's blast");
    expect(std::fabs(GrenadierFactorOf(true, grenadierPct) - (1.0 + grenadierPct / 100.0)) < 1e-9 && GrenadierFactorOf(false, grenadierPct) == 1 &&
               GrenadierFactorOf(true, -5) == 1 && grenadierPct > 0,
           "the grenades do more");
    expect(std::fabs(RadiusFactor(true, true, grenadier) - (1.0 + grenadier / 100.0)) < 1e-9 && RadiusFactor(false, true, grenadier) == 1 &&
               RadiusFactor(true, false, grenadier) == 1 && RadiusFactor(true, true, -5) == 1,
           "a larger explosion for a grenade only");
    auto const ring = Ring({3.0, 8.0, 8.5, 8.7, 9.6, 10.0}, 8.0, 8.0 * RadiusFactor(true, true, grenadier));
    expect(ring.size() == 2 && ring[0] == 2 && ring[1] == 3 && grenadier > 9.0 && grenadier < 10.0, "the ring is beyond the engine's radius and within the grown one", double(ring.size()), 2);

    // Sharpshooter: a stack for each tick, the reset a delay after a critical hit.
    Sharp sharp;
    for (int i = 0; i < 3; ++i)
        sharp = SharpTick(sharp, 1000 * (i + 1));
    expect(sharp.stacks == 3 && SharpWorth(sharp, 3500, perStack) == 3 * perStack, "three ticks, three stacks", sharp.stacks, 3);
    sharp = SharpCrit(sharp, 4000, delay);
    expect(SharpWorth(sharp, 4000 + std::uint64_t(delay * 1000) - 1, perStack) == 3 * perStack, "a critical hit does not take the stacks at once");
    expect(SharpWorth(sharp, 4000 + std::uint64_t(delay * 1000), perStack) == 0, "they are gone when the delay is over");
    expect(SharpTick(sharp, 4000 + std::uint64_t(delay * 1000)).stacks == 1, "and the next tick starts again from one", SharpTick(sharp, 4000 + std::uint64_t(delay * 1000)).stacks, 1);

    // Ballistics, Leech, Ambush, Awareness and Single Out.
    expect(std::fabs(RocketFactorOf(true, rocketPct) - (1.0 + rocketPct / 100.0)) < 1e-9 && RocketFactorOf(false, rocketPct) == 1, "rockets do more");
    expect(Procs(0.0, procPct) && Procs(procPct / 100.0 - 0.001, procPct) && !Procs(procPct / 100.0, procPct) && !Procs(0.0, 0), "the proc chance");
    expect(std::fabs(LeechLifePerHit(leechShare, 1000.0, 75, 200.0) - (leechShare * 1000.0 + 150.0)) < 1e-9, "Leech: the table's share and a share of the Life per Kill");
    expect(AmbushPct(threshold + 0.1, threshold, ambush) == ambush && AmbushPct(threshold, threshold, ambush) == 0 && AmbushPct(100, threshold, -3) == 0,
           "Ambush above the threshold only");
    expect(Saves(100, 100, true) && Saves(100, 500, true) && !Saves(100, 99, true) && !Saves(100, 500, false), "a fatal blow is saved when ready");
    double const per = AwarenessPerTick(10000, healPct, vanish, 0.5);
    expect(std::fabs(per * (vanish / 0.5) - 10000 * healPct / 100.0) < 1e-6, "the ticks of the vanish regenerate the percent", per * (vanish / 0.5), 10000 * healPct / 100.0);
    expect(AwarenessPerTick(10000, healPct, vanish, 0) == 0 && AwarenessPerTick(0, healPct, vanish, 0.5) == 0, "no tick or no Life, none");
    expect(Isolated({alone + 0.1, 90.0}, alone) && Isolated({}, alone) && !Isolated({alone, 90.0}, alone) && !Isolated({3.0}, alone), "alone: no other enemy within the yards");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
