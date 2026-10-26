// The real dc_witch_doctor_passive_rules.h. The numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_passives_decay.py); nothing is typed in here but costs, damages and times to try. Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_passive_rules.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string_view>
#include <vector>

using namespace DC::Combat::WitchDoctor::Passive::Rules;

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
    // argv: Pierce the Veil's cost increase, Spirit Vessel's seconds and cooldown, Rush of Essence's gain and seconds, Vision Quest's
    // regeneration and the class's own.
    if (argc < 20)
        return 2;
    double const costPct = std::atof(argv[1]), vesselSeconds = std::atof(argv[2]), cooldownSeconds = std::atof(argv[3]),
                 gain = std::atof(argv[4]), seconds = std::atof(argv[5]), questPct = std::atof(argv[6]), classRegen = std::atof(argv[7]);
    // The third group: Tribal Rites' share, Grave Injustice's share, seconds and radius, Creeping Death's seconds, Swampland Attunement's points
    // for each level and most enemies, Fierce Loyalty's two speeds, Confidence Ritual's radius, its reach, a pickup radius.
    double const tribal = std::atof(argv[8]), graveShare = std::atof(argv[9]), graveSeconds = std::atof(argv[10]), graveRadius = std::atof(argv[11]),
                 creeping = std::atof(argv[12]), perLevel = std::atof(argv[13]), baseSpeed = std::atof(argv[15]), idleSpeed = std::atof(argv[16]),
                 confidenceRadius = std::atof(argv[17]), reach = std::atof(argv[18]), pickup = std::atof(argv[19]);
    unsigned const mostEnemies = unsigned(std::atoi(argv[14]));

    // Pierce the Veil's cost.
    expect(std::fabs(ExtraCost(100, costPct) - costPct) < 1e-9, "a cost of 100 pays the percent more",
           ExtraCost(100, costPct), costPct);
    expect(ExtraCost(0, costPct) == 0 && ExtraCost(-5, costPct) == 0 && ExtraCost(100, 0) == 0, "no cost, no extra");
    expect(ExtraCost(250, costPct) > ExtraCost(150, costPct), "a dearer skill pays more", ExtraCost(250, costPct),
           ExtraCost(150, costPct));

    // The skills a tooltip names.
    constexpr std::array<std::string_view, 3> names = {"Haunt", "Horrify", "Spirit Walk"};
    expect(Listed(names, "Horrify") && !Listed(names, "Hex") && !Listed(names, ""),
           "a listed skill is listed, a stranger is not");

    // Spirit Vessel.
    expect(Fatal(100, 100) && Fatal(150, 100) && !Fatal(99, 100), "a blow at least the Life left is fatal", 100, 100);
    expect(!Fatal(10, 0), "no Life left is no blow to save from");
    std::uint64_t const cooldown = std::uint64_t(cooldownSeconds * 1000.0),
                        lasts = std::uint64_t(vesselSeconds * 1000.0);
    expect(Ready(std::nullopt, 0, cooldown), "the first time is ready");
    expect(!Ready(std::uint64_t(1000), 1000 + cooldown - 1, cooldown) &&
               Ready(std::uint64_t(1000), 1000 + cooldown, cooldown),
           "ready again after the cooldown, not a moment before");
    expect(Open(5000, 5000, lasts) && Open(5000, 5000 + lasts - 1, lasts) && !Open(5000, 5000 + lasts, lasts),
           "the window is open for its seconds");

    // Rush of Essence.
    std::vector<std::uint64_t> ends = {1000, 2000, 3000};
    expect(Running(ends, 0) == 3 && Running(ends, 1000) == 2 && Running(ends, 2500) == 1 && Running(ends, 3000) == 0,
           "the streams still running", Running(ends, 1000), 2);
    Prune(ends, 2000);
    expect(ends.size() == 1 && ends[0] == 3000, "the ended streams are dropped", double(ends.size()), 1);
    expect(std::fabs(PerSecond(gain, seconds) * seconds - gain) < 1e-9, "a stream over its seconds pays its gain",
           PerSecond(gain, seconds) * seconds, gain);
    expect(PerSecond(gain, 0) == 0, "no seconds, no regeneration");

    // Vision Quest.
    expect(std::fabs(RegenBonus(classRegen, questPct) - classRegen * questPct / 100.0) < 1e-9 &&
               RegenBonus(classRegen, questPct) > 0,
           "the quest adds its share of the class's own regeneration", RegenBonus(classRegen, questPct),
           classRegen * questPct / 100.0);
    expect(RegenBonus(0, questPct) == 0 && RegenBonus(classRegen, 0) == 0,
           "no regeneration or no percent, nothing added");

    // Tribal Rites.
    expect(CooldownCut(10000, tribal) == std::uint32_t(10000 * tribal / 100.0) && CooldownCut(0, tribal) == 0, "a cooldown loses the share of what is left",
           CooldownCut(10000, tribal), 10000 * tribal / 100.0);
    expect(CooldownCut(10000, 150) == 10000 && CooldownCut(10000, -5) == 0, "no more than all of it, no less than none");

    // Grave Injustice.
    expect(CooledBy(5000, graveSeconds) == 5000 - std::uint32_t(graveSeconds * 1000.0 + 0.5), "a cooldown loses the seconds", CooledBy(5000, graveSeconds), 5000 - graveSeconds * 1000.0);
    expect(CooledBy(100, graveSeconds) == 0 && CooledBy(0, graveSeconds) == 0, "a cooldown never goes below nothing");
    expect(std::fabs(Share(1000, graveShare) - 1000 * graveShare / 100.0) < 1e-9 && Share(0, graveShare) == 0 && Share(1000, 0) == 0, "a share of the maximum",
           Share(1000, graveShare), 1000 * graveShare / 100.0);
    expect(Near(graveRadius, graveRadius, 0) && !Near(graveRadius + 0.1, graveRadius, 0) && Near(graveRadius + pickup, graveRadius, pickup),
           "within the radius and what widens it", graveRadius, pickup);
    expect(Near(confidenceRadius + reach, confidenceRadius, reach) && !Near(confidenceRadius + reach + 0.1, confidenceRadius, reach), "within the radius and the reach");
    expect(Near(8, 10, -3), "a widening is never negative");

    // Creeping Death.
    expect(Lasting(true, 1, creeping) == creeping && Lasting(false, 1, creeping) == 1 && Lasting(true, creeping + 50, creeping) == creeping + 50,
           "the debuff lasts the passive's seconds while it is on, never shorter than it was", Lasting(true, 1, creeping), creeping);

    // Swampland Attunement.
    expect(std::fabs(ResistPoints(70, perLevel, 1, mostEnemies) - 70 * perLevel) < 1e-9, "a level 70 enemy gives the sheet's points", ResistPoints(70, perLevel, 1, mostEnemies), 70 * perLevel);
    expect(ResistPoints(70, perLevel, 3, mostEnemies) == 3 * ResistPoints(70, perLevel, 1, mostEnemies), "each enemy gives its points");
    expect(ResistPoints(70, perLevel, mostEnemies + 10, mostEnemies) == ResistPoints(70, perLevel, mostEnemies, mostEnemies), "no more than the most are counted");
    expect(ResistPoints(70, perLevel, 0, mostEnemies) == 0 && ResistPoints(35, perLevel, 2, mostEnemies) < ResistPoints(70, perLevel, 2, mostEnemies), "none without enemies, fewer at a lower level");

    // Fierce Loyalty.
    expect(FierceSpeed(false, true, baseSpeed, idleSpeed) == 0 && FierceSpeed(true, false, baseSpeed, idleSpeed) == baseSpeed && FierceSpeed(true, true, baseSpeed, idleSpeed) == idleSpeed,
           "no speed without a pet, the base with one, the more while one is out of combat", FierceSpeed(true, true, baseSpeed, idleSpeed), idleSpeed);
    expect(idleSpeed > baseSpeed, "the out-of-combat speed is the greater", idleSpeed, baseSpeed);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
