// The real dc_shaman_passives.h. The numbers come from argv (read from the sheets by test_shaman_passives.py); nothing
// is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/shaman/dc_shaman_passives.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::Passive;

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
    // argv: Elemental Focus' cost cut, Call of Flame's damage percent and extra seconds, then Lightning Overload's chance and share, Frozen Power's
    // percent, Rooted in Earth's seconds and percent, Storm Surge's crit per stack.
    if (argc < 26)
        return 2;
    double const cut = std::atof(argv[1]), fire = std::atof(argv[2]), extra = std::atof(argv[3]);
    double const chance = std::atof(argv[4]), share = std::atof(argv[5]), frozen = std::atof(argv[6]);
    double const rootSeconds = std::atof(argv[7]), rootPct = std::atof(argv[8]), perStack = std::atof(argv[9]), steps = std::atof(argv[10]);
    // Then Reincarnation's floor, seconds and internal cooldown, Primal Wisdom's Maelstrom and seconds, Ancestral Guidance's percent per enemy and cap.
    double const floorPct = std::atof(argv[11]), lasts = std::atof(argv[12]), cooldown = std::atof(argv[13]);
    double const perStep = std::atof(argv[14]), cutSeconds = std::atof(argv[15]), perEnemy = std::atof(argv[16]), cap = std::atof(argv[17]);
    // Then Elemental Oath's radius, Echo of the Elements' percent, Elemental Equilibrium's percent and cap, Natural Harmony's percent and cap, Primal
    // Elementalist's damage and duration percent.
    double const radius = std::atof(argv[18]), echo = std::atof(argv[19]), eqPer = std::atof(argv[20]), eqMax = std::atof(argv[21]);
    double const natPer = std::atof(argv[22]), natMax = std::atof(argv[23]), elDamage = std::atof(argv[24]), elLasts = std::atof(argv[25]);

    // Elemental Focus.
    expect(FocusCut(true, cut) == cut && FocusCut(false, cut) == 0 && FocusCut(true, 0) == 0 && FocusCut(true, -5) == 0,
           "a focus that is ready cuts the cost, none otherwise");
    expect(SpendsFocus(true, 3, 4) && SpendsFocus(true, 3, 9) && !SpendsFocus(true, 3, 3) &&
               !SpendsFocus(false, 3, 4) && !SpendsFocus(true, 3, 2),
           "the next cast spends a focus, not the cast whose critical hit armed it");

    // Call of Flame.
    expect(FireBonus(true, "fire", fire) == fire && FireBonus(false, "fire", fire) == 0 &&
               FireBonus(true, "cold", fire) == 0 && FireBonus(true, "", fire) == 0 && FireBonus(true, "fire", 0) == 0,
           "Fire hits take the bonus while the passive is on, no other element does");
    expect(BurnSeconds(true, 6, extra) == 6 + extra && BurnSeconds(false, 6, extra) == 6 &&
               BurnSeconds(true, 0, extra) == 0 && BurnSeconds(true, 6, 0) == 6,
           "a burn lasts the extra seconds longer while the passive is on");
    double const longer = BurnSeconds(true, 6, extra);
    expect(std::fabs(BurnTotal(450, 6, longer) - 450 * longer / 6) < 1e-9 && BurnTotal(450, 6, longer) > 450 &&
               BurnTotal(450, 6, 6) == 450 && BurnTotal(450, 0, 8) == 450,
           "a longer burn deals the same damage each second for the longer time");

    // Lightning Overload: the roll under the chance casts again; the free cast deals the share, which is a smaller hit and still above 0.
    expect(Overloads(0.0, chance) && Overloads(chance / 100.0 - 0.001, chance) && !Overloads(chance / 100.0, chance) && !Overloads(0.99, chance) &&
               !Overloads(0.0, 0),
           "a roll under the chance casts again, none otherwise", chance);
    double const pct = OverloadPct(share);
    expect(pct < 0 && pct > -100 && std::fabs((100.0 + pct) - share) < 1e-9 && OverloadPct(100) == 0 && OverloadPct(0) == 0,
           "the free cast deals the share of the damage, which is above nothing", pct, share);
    expect(OverloadsElement("Secondary", "lightning") && !OverloadsElement("Secondary", "fire") && !OverloadsElement("Primary", "lightning") &&
               !OverloadsElement("Secondary", ""),
           "only a Lightning Secondary skill casts again");

    // Frozen Power.
    expect(FrozenBonus(true, frozen) == frozen && FrozenBonus(false, frozen) == 0 && FrozenBonus(true, 0) == 0,
           "a Chilled or Frozen enemy takes the bonus, no other");

    // Rooted in Earth: standing still for the seconds cuts the damage taken, moving puts it away.
    unsigned long long const stepMs = (unsigned long long)steps;
    unsigned long long stood = 0;
    bool cutEarly = false;
    for (unsigned long long ms = 0; ms + stepMs < (unsigned long long)(rootSeconds * 1000.0); ms += stepMs)
    {
        stood = StillMs(false, stood, stepMs);
        cutEarly |= RootedCut(stood, rootSeconds, rootPct) != 0;
    }
    stood = StillMs(false, stood, stepMs);
    stood = StillMs(false, stood, stepMs);
    expect(!cutEarly && RootedCut(stood, rootSeconds, rootPct) == rootPct, "standing still for the seconds cuts the damage taken, not before");
    expect(StillMs(true, stood, stepMs) == 0 && RootedCut(StillMs(true, stood, stepMs), rootSeconds, rootPct) == 0 && RootedCut(0, 0.0, rootPct) == 0,
           "moving ends it at once");

    // Storm Surge.
    expect(SurgeCrit(3, perStack) == 3 * perStack && SurgeCrit(0, perStack) == 0 && SurgeCrit(8, perStack) == 8 * perStack && SurgeCrit(3, 0) == 0,
           "each stack gives its crit chance");

    // Elemental Harmony.
    expect(HarmonyFactor(true) == 3.0 && HarmonyFactor(false) == 1.0, "the bonus is tripled with the passive, as it is without");

    // Reincarnation.
    expect(Fatal(100, 100) && Fatal(150, 100) && !Fatal(99, 100) && !Fatal(10, 0), "a blow that is at least the Life left is fatal");
    std::uint64_t const coolMs = (std::uint64_t)(cooldown * 1000.0), lastsMs = (std::uint64_t)(lasts * 1000.0);
    expect(CooledDown(0, 5, coolMs) && !CooledDown(1000, 1000 + coolMs - 1, coolMs) && CooledDown(1000, 1000 + coolMs, coolMs),
           "it may trigger once every internal cooldown");
    expect(Immune(1000, 1000, lastsMs) && Immune(1000, 1000 + lastsMs - 1, lastsMs) && !Immune(1000, 1000 + lastsMs, lastsMs) && !Immune(0, 5, lastsMs),
           "the window is open for its seconds after the save, not before one");
    expect(RestoredLife(10, 1000, floorPct) == 1000 * floorPct / 100.0 - 10 && RestoredLife(900, 1000, floorPct) == 0 && RestoredLife(10, 0, floorPct) == 0 &&
               RestoredLife(10, 1000, 0) == 0,
           "the Life restored brings the Shaman to the floor, none when above it");

    // Primal Wisdom.
    Wisdom one = WisdomSteps(0, perStep, perStep);
    Wisdom two = WisdomSteps(0, perStep * 0.6, perStep);
    Wisdom three = WisdomSteps(two.carried, perStep * 0.6, perStep);
    Wisdom many = WisdomSteps(perStep * 0.25, perStep * 3.0, perStep);
    expect(one.steps == 1 && one.carried == 0 && two.steps == 0 && std::fabs(two.carried - perStep * 0.6) < 1e-9 && three.steps == 1 &&
               std::fabs(three.carried - perStep * 0.2) < 1e-9 && many.steps == 3 && std::fabs(many.carried - perStep * 0.25) < 1e-9,
           "every step of Maelstrom spent makes a step, and what is left over carries");
    expect(WisdomSteps(5, 100, 0).steps == 0 && WisdomSteps(5, 0, perStep).steps == 0 && WisdomSteps(5, 0, perStep).carried == 5 && cutSeconds > 0,
           "nothing is spent, nothing is made");

    // Ancestral Guidance: one enemy heals the share, and the cast never heals past the cap.
    expect(GuidanceHeal(0, perEnemy, cap) == perEnemy && GuidanceHeal(cap, perEnemy, cap) == 0 && GuidanceHeal(0, 0, cap) == 0 && GuidanceHeal(0, perEnemy, 0) == 0,
           "an enemy hit heals the share, none at the cap");
    double healed = 0;
    for (int hit = 0; hit < 100; ++hit)
        healed += GuidanceHeal(healed, perEnemy, cap);
    expect(std::fabs(healed - cap) < 1e-9 && std::fabs(GuidanceHeal(cap - perEnemy / 2.0, perEnemy, cap) - perEnemy / 2.0) < 1e-9,
           "a cast heals up to the cap and the last enemy heals what is left", healed, cap);

    // Elemental Oath.
    expect(InOath(0, radius) && InOath(radius, radius) && !InOath(radius + 0.1, radius) && !InOath(5, 0) && !InOath(-1, radius),
           "a member inside the radius is in the aura, outside it is not");

    // Echo of the Elements.
    expect(EchoCut(1000, echo) == 1000 * echo / 100.0 && EchoCut(0, echo) == 0 && EchoCut(1000, 0) == 0 && EchoCut(1000, 250) == 1000,
           "a cooldown loses the percent of what it has left, never more than it has");

    // The elements dealt.
    expect(ElementIndex("fire") == 0 && ElementIndex("cold") == 1 && ElementIndex("lightning") == 2 && ElementIndex("physical") == 3 &&
               ElementIndex("") == -1 && ElementIndex("arcane") == -1,
           "the four elements have a slot each, no other");
    ElementTimes at = {100, 0, 300, 0};
    expect(ElementsWithin(at, -1, 1000, 5000) == 2 && ElementsWithin(at, 0, 1000, 5000) == 1 && ElementsWithin(at, 2, 1000, 5000) == 1 &&
               ElementsWithin(at, -1, 1000, 500) == 0 && ElementsWithin(at, -1, 100 + 5000, 5000) == 1 && ElementsWithin(at, -1, 100 + 4999, 5000) == 2 &&
               ElementsWithin({0, 0, 0, 0}, -1, 1000, 5000) == 0,
           "an element counts within its seconds, not at them, and never when it was never dealt");
    expect(ElementsBonus(2, eqPer, eqMax) == std::min(2 * eqPer, eqMax) && ElementsBonus(0, eqPer, eqMax) == 0 && ElementsBonus(1, eqPer, eqMax) == eqPer &&
               ElementsBonus(10, eqPer, eqMax) == eqMax && ElementsBonus(2, 0, eqMax) == 0 && ElementsBonus(2, eqPer, 0) == 0,
           "each element adds its percent, up to the cap");
    expect(ElementsBonus(4, natPer, natMax) == natMax && ElementsBonus(3, natPer, natMax) == std::min(3 * natPer, natMax) && ElementsBonus(4, natPer, natMax) == 4 * natPer,
           "all four elements give the Natural Harmony cap");

    // Primal Elementalist.
    expect(ElementalDamage(true, "Fire Elemental", elDamage) == elDamage && ElementalDamage(true, "Earth Elemental", elDamage) == elDamage &&
               ElementalDamage(true, "Lightning Bolt", elDamage) == 0 && ElementalDamage(false, "Fire Elemental", elDamage) == 0 && ElementalDamage(true, "Fire Elemental", 0) == 0,
           "only the elementals' hits take the damage, with the passive");
    expect(std::fabs(ElementalSeconds(true, 20, elLasts) - 20 * (1 + elLasts / 100.0)) < 1e-9 && ElementalSeconds(false, 20, elLasts) == 20 &&
               ElementalSeconds(true, 0, elLasts) == 0 && ElementalSeconds(true, 20, 0) == 20,
           "an elemental lasts the percent longer, with the passive");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
