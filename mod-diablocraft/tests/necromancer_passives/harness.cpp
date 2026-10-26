// The real dc_necromancer_passives_math.h. The numbers and the skill names come from argv (read from the passive sheet,
// the tunables and the skill sheets by test_necromancer_passives.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_passives_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

using namespace DC::Combat::Necromancer::Passive;

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
    // argv: Stand Alone's base and per-minion percent; Bone Prison's chance; Swift Harvesting's percent; Commander's
    // percent; Life from Death's chance, window seconds and cap; the three Bone Prison skills; the three Swift
    // Harvesting skills
    if (argc < 45)
        return 2;
    double const base = std::atof(argv[1]), per = std::atof(argv[2]), prison = std::atof(argv[3]),
                 swift = std::atof(argv[4]), commander = std::atof(argv[5]), lifeChance = std::atof(argv[6]);
    std::uint64_t const window = std::uint64_t(std::atof(argv[7]) * 1000);
    unsigned const cap = unsigned(std::atoi(argv[8]));
    std::vector<std::string> const prisoners = {argv[9], argv[10], argv[11]}, swifts = {argv[12], argv[13], argv[14]};
    // then: Extended Servitude's, Spreading Malediction's, Eternal Torment's forever seconds, Dark Reaping's, Final Service's seconds, heal and
    // wait; the two Extended Servitude skills; the three curses; the two scythe types and a type that is no scythe
    double const servitude = std::atof(argv[15]), malediction = std::atof(argv[16]), forever = std::atof(argv[17]), reap = std::atof(argv[18]);
    std::uint64_t const sustainMs = std::uint64_t(std::atof(argv[19]) * 1000), waitMs = std::uint64_t(std::atof(argv[21]) * 1000);
    double const serviceHeal = std::atof(argv[20]);
    std::vector<std::string> const servants = {argv[22], argv[23]}, curses = {argv[24], argv[25], argv[26]}, scythes = {argv[27], argv[28]};
    // then: Grisly Tribute's share, Draw Life's percent, Serration's percent, yards and maximum, Aberrant Animator's share, Blood for Blood's
    // stacks, Blood Is Power's threshold, Rathma's Shield's seconds and wait; the three Serration skills; the three Rathma's Shield skills
    double const tribute = std::atof(argv[29]), drawLife = std::atof(argv[30]), serrationPer = std::atof(argv[31]), serrationStep = std::atof(argv[32]),
                 serrationMax = std::atof(argv[33]), thornsShare = std::atof(argv[34]), threshold = std::atof(argv[36]);
    unsigned const stacksMax = unsigned(std::atoi(argv[35]));
    std::uint64_t const wardMs = std::uint64_t(std::atof(argv[37]) * 1000), wardWaitMs = std::uint64_t(std::atof(argv[38]) * 1000);
    std::vector<std::string> const serrated = {argv[39], argv[40], argv[41]}, rathmas = {argv[42], argv[43], argv[44]};

    // Stand Alone: the sheet's base less the sheet's share for each minion, never below nothing.
    expect(near(StandAloneArmorPct(base, per, 0), base), "no minion keeps the whole bonus");
    expect(near(StandAloneArmorPct(base, per, 3), base - 3 * per), "each minion takes its share off",
           StandAloneArmorPct(base, per, 3), base - 3 * per);
    expect(StandAloneArmorPct(base, per, 1000) == 0.0, "many minions leave nothing, never less");
    expect(StandAloneArmorPct(0, per, 2) == 0.0, "no base, no bonus");

    // Bone Prison and Swift Harvesting name their skills.
    bool all = true;
    for (auto const& skill : prisoners)
        all = all && BonePrisonSkill(skill);
    expect(all, "each of the three skills can trap");
    expect(!BonePrisonSkill("Grim Scythe") && !BonePrisonSkill("Death Nova") && !BonePrisonSkill(""),
           "no other skill traps");
    all = true;
    for (auto const& skill : swifts)
        all = all && SwiftHarvestingSkill(skill);
    expect(all, "each of the three skills is quickened");
    expect(!SwiftHarvestingSkill("Bone Spear") && !SwiftHarvestingSkill("Skeletal Mage") && !SwiftHarvestingSkill(""),
           "no other skill is quickened");

    // The chances: a roll under the chance holds it, the chance itself does not, none never.
    expect(Procs(prison - 0.001, prison) && !Procs(prison, prison) && !Procs(99.999, prison),
           "a roll under the chance procs");
    expect(!Procs(0, 0) && !Procs(0, -5) && Procs(0, 100) && !Procs(100, 100),
           "a chance of nothing never procs, of all always");

    // Swift Harvesting: the bonus joins the speed bonuses already in, keeps to the cap and never slows.
    expect(near(SwiftHarvestingAps(1.0, 0, swift, 5.0), 1.0 + swift / 100.0), "the bonus on a bare speed",
           SwiftHarvestingAps(1.0, 0, swift, 5.0), 1.0 + swift / 100.0);
    expect(near(SwiftHarvestingAps(1.5, 50, swift, 5.0), 1.5 * (1.0 + (50 + swift) / 100.0) / 1.5),
           "the bonus adds to the speed bonuses, it does not multiply them", SwiftHarvestingAps(1.5, 50, swift, 5.0),
           1.5 * (1.0 + (50 + swift) / 100.0) / 1.5);
    expect(SwiftHarvestingAps(4.9, 0, swift, 5.0) == 5.0, "the speed cap holds");
    expect(SwiftHarvestingAps(6.0, 0, swift, 5.0) == 6.0, "a speed already over the cap is not cut");
    expect(SwiftHarvestingAps(1.0, 0, 0, 5.0) == 1.0 && SwiftHarvestingAps(1.0, 0, -10, 5.0) == 1.0,
           "no bonus, or a negative one, changes nothing");
    expect(SwiftHarvestingAps(0, 0, swift, 5.0) == 0.0, "no speed stays none");

    // Commander of the Risen Dead: the share of the cooldown that goes (the cost cut is the cost cut piece's).
    expect(CooldownCut(45000, commander) == std::uint32_t(45000 * commander / 100.0), "the share of the cooldown goes");
    expect(CooldownCut(45000, 0) == 0 && CooldownCut(45000, -5) == 0 && CooldownCut(0, commander) == 0,
           "no share, or no cooldown, cuts nothing");
    expect(CooldownCut(45000, 250) == 45000, "no more than the cooldown is cut");

    // Life from Death: a chance per corpse, and at most the cap of globes in any window.
    expect(Procs(lifeChance - 0.001, lifeChance) && !Procs(lifeChance, lifeChance),
           "a corpse's roll holds the sheet's chance");
    GlobeWindow window_;
    unsigned spawned = 0;
    for (unsigned i = 0; i < cap + 5; ++i)
        spawned += window_.Allow(1000 + i, window, cap) ? 1 : 0;
    expect(spawned == cap, "no more than the cap spawn in one window", spawned, cap);
    expect(!window_.Allow(1000 + window - 1, window, cap), "the window does not end early");
    expect(window_.Allow(1000 + window, window, cap), "the next window opens when the first ends");
    unsigned second = 1;
    for (unsigned i = 0; i < cap + 5; ++i)
        second += window_.Allow(1000 + window + 1 + i, window, cap) ? 1 : 0;
    expect(second == cap, "the next window holds the cap too", second, cap);
    GlobeWindow none;
    expect(!none.Allow(5, window, 0), "a cap of none lets none through");

    // Extended Servitude: the two named skills' minions last the share longer, no other.
    all = true;
    for (auto const& skill : servants)
        all = all && ServitudeSkill(skill);
    expect(all, "Skeletal Mage and Revive minions are lengthened");
    expect(!ServitudeSkill("Command Skeletons") && !ServitudeSkill("Command Golem") && !ServitudeSkill("Simulacrum") && !ServitudeSkill(""),
           "no other minion is lengthened");
    expect(near(ServitudeFactor(servitude), 1.0 + servitude / 100.0), "a minion lasts one plus the share", ServitudeFactor(servitude), 1.0 + servitude / 100.0);
    expect(ServitudeFactor(0) == 1.0 && ServitudeFactor(-30) == 1.0, "no share, or a negative one, shortens nothing");

    // Rigor Mortis: a record of the Poison school, and no other.
    expect(PoisonMask(32u) && PoisonMask(32u | 1u), "a Poison record");
    expect(!PoisonMask(1u) && !PoisonMask(4u) && !PoisonMask(64u) && !PoisonMask(0u), "no other school is Poison");

    // Spreading Malediction: the share for each enemy cursed.
    expect(near(MaledictionPct(malediction, 7), 7 * malediction), "the bonus grows with the enemies cursed", MaledictionPct(malediction, 7), 7 * malediction);
    expect(MaledictionPct(malediction, 0) == 0.0 && MaledictionPct(-1, 5) == 0.0, "no enemy, or a negative share, gives nothing");

    // Eternal Torment: a curse of some seconds lasts forever, a curse of none stays none, and the passive off changes nothing.
    expect(near(CurseSeconds(true, 10, forever), forever), "a curse lasts forever with the passive", CurseSeconds(true, 10, forever), forever);
    expect(CurseSeconds(false, 10, forever) == 10.0, "the passive off keeps the seconds");
    expect(CurseSeconds(true, 0, forever) == 0.0, "no seconds stay none");
    expect(CurseSeconds(true, forever * 2, forever) == forever * 2, "a longer curse is not cut");
    all = true;
    for (auto const& curse : curses)
        all = all && CurseSkill(curse);
    expect(all, "the three curses are cut");
    expect(!CurseSkill("Bone Spear") && !CurseSkill("Command Skeletons") && !CurseSkill(""), "no other skill is cut");

    // Dark Reaping: a scythe of either hand, no other weapon; the share of a maximum.
    all = true;
    for (auto const& type : scythes)
        all = all && ScytheType(type);
    expect(all, "both scythes count");
    expect(!ScytheType("Grave Wand") && !ScytheType("Cinquedeas") && !ScytheType("Phylactery") && !ScytheType(""), "no other weapon counts");
    expect(near(ReapGain(200, reap), 200 * reap / 100.0), "the share of the maximum", ReapGain(200, reap), 200 * reap / 100.0);
    expect(ReapGain(0, reap) == 0.0 && ReapGain(200, 0) == 0.0 && ReapGain(200, -5) == 0.0, "no maximum, or no share, gives nothing");

    // Final Service: a blow of all the Life left starts the window; the window drops everything; the wait holds.
    Sustain sustain;
    expect(!sustain.Save(1000, 99, 100, waitMs, sustainMs), "a blow short of the Life is no save");
    expect(sustain.Save(1000, 100, 100, waitMs, sustainMs) && sustain.Active(1000), "a lethal blow starts the window");
    expect(sustain.Active(1000 + sustainMs - 1) && !sustain.Active(1000 + sustainMs), "the window lasts its seconds");
    expect(!sustain.Save(1000 + 1, 500, 100, waitMs, sustainMs), "no second save inside the window");
    expect(!sustain.Save(1000 + sustainMs, 500, 100, waitMs, sustainMs), "none in the wait");
    expect(!sustain.Save(1000 + waitMs - 1, 500, 100, waitMs, sustainMs), "none just before the wait ends");
    expect(sustain.Save(1000 + waitMs, 500, 100, waitMs, sustainMs), "one when the wait is over");
    Sustain dead;
    expect(!dead.Save(5, 500, 0, waitMs, sustainMs), "a body with no Life is not saved");
    expect(near(ServiceHeal(1000, serviceHeal, 3), 3 * 1000 * serviceHeal / 100.0), "the heal grows with the minions", ServiceHeal(1000, serviceHeal, 3),
           3 * 1000 * serviceHeal / 100.0);
    expect(ServiceHeal(1000, serviceHeal, 0) == 0.0 && ServiceHeal(0, serviceHeal, 3) == 0.0 && ServiceHeal(1000, -5, 3) == 0.0,
           "no minion, no Life, or a negative share heals nothing");

    // Grisly Tribute: the share of the Life on Hit.
    expect(near(TributeHeal(400, tribute), 400 * tribute / 100.0), "the share of the Life on Hit", TributeHeal(400, tribute), 400 * tribute / 100.0);
    expect(TributeHeal(0, tribute) == 0.0 && TributeHeal(400, 0) == 0.0 && TributeHeal(400, -5) == 0.0, "no Life on Hit, or no share, heals nothing");

    // Draw Life: the percent for each enemy.
    expect(near(DrawLifePct(drawLife, 6), 6 * drawLife), "the regeneration grows with the enemies", DrawLifePct(drawLife, 6), 6 * drawLife);
    expect(DrawLifePct(drawLife, 0) == 0.0 && DrawLifePct(-5, 4) == 0.0, "no enemy, or a negative share, adds nothing");

    // Serration: a whole step is a whole bonus, the bonus stops at the maximum, and the skills are the tooltip's.
    expect(SerrationPct(serrationStep - 0.01, serrationPer, serrationStep, serrationMax) == 0.0, "short of one step is no bonus");
    expect(near(SerrationPct(serrationStep, serrationPer, serrationStep, serrationMax), serrationPer), "one step is one bonus");
    expect(near(SerrationPct(serrationStep * 2.99, serrationPer, serrationStep, serrationMax), 2 * serrationPer), "a part of a step is not counted",
           SerrationPct(serrationStep * 2.99, serrationPer, serrationStep, serrationMax), 2 * serrationPer);
    expect(near(SerrationPct(1000, serrationPer, serrationStep, serrationMax), serrationMax), "the bonus stops at the maximum");
    expect(SerrationPct(0, serrationPer, serrationStep, serrationMax) == 0.0 && SerrationPct(-3, serrationPer, serrationStep, serrationMax) == 0.0 &&
               SerrationPct(10, serrationPer, 0, serrationMax) == 0.0 && SerrationPct(10, 0, serrationStep, serrationMax) == 0.0,
           "no distance, no step or no share gives nothing");
    all = true;
    for (auto const& skill : serrated)
        all = all && SerrationSkill(skill);
    expect(all, "each of the three skills is lengthened by distance");
    expect(!SerrationSkill("Grim Scythe") && !SerrationSkill("Death Nova") && !SerrationSkill(""), "no other skill is");

    // Aberrant Animator: the share of the Thorns.
    expect(near(MinionThorns(100, thornsShare), 100 * thornsShare / 100.0), "the minion has the share of the Thorns", MinionThorns(100, thornsShare),
           100 * thornsShare / 100.0);
    expect(MinionThorns(0, thornsShare) == 0.0 && MinionThorns(100, 0) == 0.0 && MinionThorns(100, -5) == 0.0, "no Thorns, or no share, gives none");

    // Blood for Blood: each globe a stack up to the most, each Blood spell spends one.
    FreeCosts free;
    expect(!free.Spend(), "no stack pays nothing");
    for (unsigned i = 0; i < stacksMax + 4; ++i)
        free.Gain(stacksMax);
    expect(free.stacks == stacksMax, "the stacks stop at the most", free.stacks, stacksMax);
    unsigned paid = 0;
    for (unsigned i = 0; i < stacksMax + 4; ++i)
        paid += free.Spend() ? 1 : 0;
    expect(paid == stacksMax && free.stacks == 0, "each stack pays one cost", paid, stacksMax);

    // Blood Is Power: the Life lost adds up, each whole threshold is one reduction, the rest carries over.
    LostLife lost;
    expect(lost.Add(50, 1000, threshold) == 0, "half a threshold is no reduction");
    expect(lost.Add(1000 * threshold / 100.0 - 50 - 0.001, 1000, threshold) == 0, "just short is none");
    expect(lost.Add(0.002, 1000, threshold) == 1, "the threshold is one reduction");
    expect(lost.Add(2.5 * 1000 * threshold / 100.0, 1000, threshold) == 2, "two and a half thresholds are two reductions");
    expect(lost.Add(0.5 * 1000 * threshold / 100.0, 1000, threshold) == 1, "the half left over completes the next");
    expect(lost.Add(0, 1000, threshold) == 0 && lost.Add(-10, 1000, threshold) == 0, "no loss, or a gain, is none");
    expect(lost.Add(1000 * threshold / 100.0, 1000, threshold) == 1, "a gain does not undo a loss");
    LostLife nothing;
    expect(nothing.Add(10, 0, threshold) == 0 && nothing.Add(10, 1000, 0) == 0, "no maximum, or no threshold, is none");

    // Rathma's Shield: the skills, the window and the wait.
    all = true;
    for (auto const& skill : rathmas)
        all = all && RathmaSkill(skill);
    expect(all, "each of the three skills opens the window");
    expect(!RathmaSkill("Blood Rush") && !RathmaSkill("Bone Armor") && !RathmaSkill(""), "no other skill does");
    Ward ward;
    expect(ward.Open(1000, wardMs, wardWaitMs) && ward.Active(1000), "a use opens the window");
    expect(ward.Active(1000 + wardMs - 1) && !ward.Active(1000 + wardMs), "the window lasts its seconds");
    expect(!ward.Open(1000 + wardMs, wardMs, wardWaitMs) && !ward.Active(1000 + wardMs), "no second window in the wait");
    expect(!ward.Open(1000 + wardWaitMs - 1, wardMs, wardWaitMs), "none just before the wait ends");
    expect(ward.Open(1000 + wardWaitMs, wardMs, wardWaitMs), "one when the wait is over");

    if (failures)
        return 1;
    std::printf("cases=%d\n", cases);
    return 0;
}
