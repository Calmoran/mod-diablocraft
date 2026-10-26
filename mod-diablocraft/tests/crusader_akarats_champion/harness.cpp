// The real dc_crusader_akarats_champion.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_akarats_champion.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/crusader/dc_crusader_akarats_champion.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::AkaratsChampion;

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
    // argv: the damage bonus, the duration, the burn's gap factor, the Rally cut, then the five runes A to E
    if (argc < 10)
        return 2;
    double const bonus = std::atof(argv[1]), duration = std::atof(argv[2]), factor = std::atof(argv[3]),
                 cut = std::atof(argv[4]);
    std::string const fire = argv[5], embodiment = argv[6], rally = argv[7], prophet = argv[8], hasteful = argv[9];

    expect(RuneOf(fire) == Rune::FireStarter && RuneOf(embodiment) == Rune::EmbodimentOfPower &&
               RuneOf(rally) == Rune::Rally && RuneOf(prophet) == Rune::Prophet && RuneOf(hasteful) == Rune::Hasteful,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {fire, embodiment, rally, prophet, hasteful})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Akarat's Champion") == Rune::None, "the base skill and a stranger are no rune");

    // The transformation lasts until its time is over, and not a moment longer.
    expect(Active(1000, 1001) && !Active(1000, 1000) && !Active(1000, 999) && !Active(1000, 0),
           "active until the time is over");
    expect(DamageBonusPct(true, bonus) == bonus && DamageBonusPct(false, bonus) == 0 && DamageBonusPct(true, 0) == 0 &&
               DamageBonusPct(true, -5) == 0,
           "the bonus is the sheet's while it lasts and nothing else", DamageBonusPct(true, bonus), bonus);

    // One payment of Wrath for each whole second.
    expect(Payments(duration) == unsigned(duration), "a payment for each second", double(Payments(duration)), duration);
    expect(Payments(2.5) == 2 && Payments(0) == 0 && Payments(-4) == 0 && Payments(0.9) == 0,
           "only whole seconds are paid");

    // Fire Starter: the same enemy burns again after the gap, the first time at once.
    expect(BurnGapMs(2.0, factor) == std::uint64_t(factor / 2.0 * 1000.0 + 0.5), "the gap is the factor over the speed",
           double(BurnGapMs(2.0, factor)), factor / 2.0 * 1000.0);
    expect(BurnGapMs(0, factor) == 0 && BurnGapMs(2.0, 0) == 0, "no speed or factor, no gap");
    expect(BurnDue(false, 5000, 0, 450), "the first burn is due");
    expect(!BurnDue(true, 5000, 4700, 450) && BurnDue(true, 5000, 4550, 450) && BurnDue(true, 5000, 4000, 450),
           "the next waits for the gap");

    // Rally: the cut is the sheet's seconds, never more than is left.
    expect(CutMs(60000, cut) == cut * 1000.0, "a cooldown is cut by the seconds", double(CutMs(60000, cut)), cut * 1000.0);
    expect(CutMs(3000, cut) == 3000, "no more than is left", double(CutMs(3000, cut)), 3000);
    expect(CutMs(0, cut) == 0 && CutMs(60000, 0) == 0 && CutMs(60000, -2) == 0, "nothing left or no cut, nothing taken");

    // Prophet: the first fatal blow only, and only that rune.
    expect(Saves(Rune::Prophet, false, 100, 100) && Saves(Rune::Prophet, false, 500, 100),
           "a blow that takes all the Life is saved");
    expect(!Saves(Rune::Prophet, false, 99, 100), "a blow that leaves Life is not fatal");
    expect(!Saves(Rune::Prophet, true, 500, 100), "only the first");
    expect(!Saves(Rune::Rally, false, 500, 100) && !Saves(Rune::None, false, 500, 100), "no other rune saves");
    expect(!Saves(Rune::Prophet, false, 500, 0), "no Life, no save");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
