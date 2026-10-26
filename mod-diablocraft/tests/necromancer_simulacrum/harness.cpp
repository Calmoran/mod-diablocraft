// The real dc_necromancer_simulacrum_math.h and dc_necromancer_curses_math.h. The rune names, the sheets' categories and the numbers
// come from argv (read from the sheets by test_necromancer_simulacrum.py); nothing is typed in here. Prints "cases=N" and exits 0, or
// names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_curses_math.h"
#include "classes/necromancer/dc_necromancer_simulacrum_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <vector>

using namespace DC::Combat::Necromancer::Simulacrum;
using DC::Combat::Necromancer::Curses::Lifts;

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
    // argv: the five runes A to E; Blood Debt's cost reduction percent; Reservoir's maximum increase percent; the three Secondary
    // skills; the three curses
    if (argc < 14)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const reduction = std::atof(argv[6]), increase = std::atof(argv[7]);
    std::vector<std::string> const secondaries = {argv[8], argv[9], argv[10]}, curses = {argv[11], argv[12], argv[13]};

    expect(RuneOf(names[0]) == Rune::Reservoir && RuneOf(names[1]) == Rune::CursedForm && RuneOf(names[2]) == Rune::BloodDebt &&
               RuneOf(names[3]) == Rune::BloodAndBone && RuneOf(names[4]) == Rune::SelfSacrifice,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Simulacrum") == Rune::None && RuneOf("blood debt") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // Blood Debt: the Life costs are cut by the sheet's share, by no other rune.
    expect(near(LifeCostShare(Rune::BloodDebt, reduction), 1.0 - reduction / 100.0), "Blood Debt cuts the cost by its share",
           LifeCostShare(Rune::BloodDebt, reduction), 1.0 - reduction / 100.0);
    expect(LifeCostShare(Rune::Reservoir, reduction) == 1.0 && LifeCostShare(Rune::None, reduction) == 1.0 &&
               LifeCostShare(Rune::SelfSacrifice, reduction) == 1.0,
           "no other rune cuts a cost");
    expect(LifeCostShare(Rune::BloodDebt, 150) == 0.0, "a cut past the whole cost leaves nothing to pay");
    expect(LifeCostShare(Rune::BloodDebt, -20) == 1.0, "a negative cut never makes a cost dearer");

    // Reservoir: the maximum raised by the sheet's share.
    expect(near(EssenceAdded(200, increase), 200 * increase / 100.0), "the maximum is raised by its share", EssenceAdded(200, increase),
           200 * increase / 100.0);
    expect(EssenceAdded(0, increase) == 0.0 && EssenceAdded(-5, increase) == 0.0, "no pool takes nothing");
    expect(EssenceAdded(200, 0) == 0.0 && EssenceAdded(200, -50) == 0.0, "no share, or a negative one, adds nothing");

    // The Secondary skills are repeated, the others are not; two are cast at an enemy and the nova around the Necromancer.
    bool all = true;
    for (auto const& skill : secondaries)
        all = all && IsSecondary(skill);
    expect(all, "each Secondary skill is repeated");
    expect(!IsSecondary("Bone Spikes") && !IsSecondary("Corpse Lance") && !IsSecondary("Simulacrum") && !IsSecondary(""),
           "a Primary, a Corpses skill and Simulacrum itself are not repeated");
    expect(!NeedsTarget("Death Nova") && NeedsTarget("Bone Spear") && NeedsTarget("Skeletal Mage"), "the nova is cast around the Necromancer");

    // Cursed Form: each curse adds the other two.
    all = true;
    for (auto const& curse : curses)
    {
        all = all && IsCurse(curse);
        auto const other = OtherCurses(curse);
        std::set<std::string> got = {std::string(other[0]), std::string(other[1])}, want(curses.begin(), curses.end());
        want.erase(curse);
        all = all && got == want && std::string(other[0]) != curse && std::string(other[1]) != curse;
    }
    expect(all, "a curse adds exactly the other two");
    expect(!IsCurse("Bone Spear") && !IsCurse("") && !IsCurse("Simulacrum"), "a Secondary is no curse");

    // Self Sacrifice: only a blow that takes all the Life that is left.
    expect(Fatal(100, 100) && Fatal(150, 100) && !Fatal(99.9, 100), "a blow of the whole Life or more is fatal");
    expect(!Fatal(10, 0) && !Fatal(0, 0), "nothing is fatal to a body without Life");

    // The curses: which one a new curse takes off. A curse of the same skill is replaced by another record of it, never by itself.
    expect(Lifts(false, true, true, 5, 6), "the same skill's other record is replaced");
    expect(!Lifts(false, true, true, 6, 6), "the same record again lifts nothing");
    expect(Lifts(false, false, true, 5, 6), "another skill's curse is replaced when the curses do not stand together");
    expect(!Lifts(true, false, true, 5, 6), "another skill's curse stays when they stand together");
    expect(Lifts(true, true, true, 5, 6), "the same skill's is replaced even when they stand together");
    expect(!Lifts(false, true, false, 5, 6) && !Lifts(false, false, false, 5, 6), "a curse that ran out is not lifted");
    expect(!Lifts(false, true, true, 0, 6) && !Lifts(false, false, true, 0, 6), "no curse held, none lifted");

    if (failures)
        return 1;
    std::printf("cases=%d\n", cases);
    return 0;
}
