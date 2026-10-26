// The real dc_necromancer_command_golem_math.h. The rune names and the numbers come from argv (read from the sheets and the
// tunables by test_necromancer_command_golem.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first
// failing case and exits 1.
#include "classes/necromancer/dc_necromancer_command_golem_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::CommandGolem;

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
    // argv: the five runes A to E; the Bone Golem's stun seconds, its pulse interval and pulse percent where it stops, the
    // sheet's total for the rune; the Blood Golem's vein and rip percents and the sheet's total; the Decay Golem's percent per
    // corpse and the most corpses
    if (argc < 17)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const stun = std::atof(argv[6]), interval = std::atof(argv[7]), pulsePct = std::atof(argv[8]),
                 boneTotal = std::atof(argv[9]), veinPct = std::atof(argv[10]), ripPct = std::atof(argv[11]),
                 bloodTotal = std::atof(argv[12]), perCorpse = std::atof(argv[13]);
    unsigned const most = unsigned(std::atoi(argv[14]));
    double const knockback = std::atof(argv[15]), maxScale = std::atof(argv[16]);

    expect(RuneOf(names[0]) == Rune::BoneGolem && RuneOf(names[1]) == Rune::BloodGolem &&
               RuneOf(names[2]) == Rune::DecayGolem && RuneOf(names[3]) == Rune::FleshGolem &&
               RuneOf(names[4]) == Rune::IceGolem,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Command Golem") == Rune::None && RuneOf("bone golem") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // The pile of corpses: the skill and Flesh Golem collapse; no other rune does.
    expect(Collapses(Rune::None) && Collapses(Rune::FleshGolem), "the skill and Flesh Golem collapse");
    expect(!Collapses(Rune::BoneGolem) && !Collapses(Rune::BloodGolem) && !Collapses(Rune::DecayGolem) &&
               !Collapses(Rune::IceGolem),
           "the other runes do not");

    // Which record the Golem strikes as: the rune's where the rune changes the school.
    expect(BlowsUseRuneRecord(Rune::DecayGolem) && BlowsUseRuneRecord(Rune::IceGolem), "Poison and Cold come from the rune");
    expect(!BlowsUseRuneRecord(Rune::None) && !BlowsUseRuneRecord(Rune::BoneGolem) && !BlowsUseRuneRecord(Rune::BloodGolem) &&
               !BlowsUseRuneRecord(Rune::FleshGolem),
           "the other runes' numbers are their active's");

    // The tornado's trip: yards over speed times the scalar, none for nothing to go.
    expect(near(TravelSeconds(100, 7, 2), 100.0 / 14.0), "the trip is yards over the scaled speed", TravelSeconds(100, 7, 2),
           100.0 / 14.0);
    expect(near(TravelSeconds(100, 7, 2), TravelSeconds(200, 14, 2)), "twice the way at twice the speed is the same time");
    expect(TravelSeconds(0, 7, 2) == 0.0 && TravelSeconds(-5, 7, 2) == 0.0 && TravelSeconds(100, 0, 2) == 0.0 &&
               TravelSeconds(100, 7, 0) == 0.0,
           "no way, no speed or no scalar: no trip");

    // The pulses: a tick is not lost to rounding; where it stops they make the sheet's total.
    expect(Pulses(0.3, 0.1) == 3, "a pulse is not lost to rounding", Pulses(0.3, 0.1), 3);
    expect(Pulses(2.0, 0.5) == 4 && Pulses(1.9, 0.5) == 3, "pulses fit the time");
    expect(Pulses(0, 0.5) == 0 && Pulses(2, 0) == 0 && Pulses(-1, 0.5) == 0, "no time or no interval, no pulses");
    expect(near(Pulses(stun, interval) * pulsePct, boneTotal), "the pulses where it stops make the sheet's total",
           Pulses(stun, interval) * pulsePct, boneTotal);

    // The way: the point a share along, held between the ends.
    expect(near(Along(10, 20, 0), 10) && near(Along(10, 20, 1), 20) && near(Along(10, 20, 0.25), 12.5), "a share of the way");
    expect(near(Along(10, 20, -1), 10) && near(Along(10, 20, 3), 20), "the share is held between none and the whole");

    // The veins: the first at once, each later one a gap after the one before; the strikes make the sheet's total.
    expect(VeinAt(0, 0.07) == 0.0 && near(VeinAt(3, 0.07), 0.21) && VeinAt(4, 0) == 0.0, "the veins follow one another");
    expect(near(veinPct + ripPct, bloodTotal), "the vein and the rip make the sheet's total", veinPct + ripPct, bloodTotal);

    // The Decay Golem's meal: a bonus for each corpse eaten, none past the most.
    expect(near(CorpseBonusPct(4, perCorpse, most), 4 * perCorpse), "each corpse adds its percent");
    expect(near(CorpseBonusPct(most + 5, perCorpse, most), most * perCorpse), "no corpse past the most counts");
    expect(CorpseBonusPct(0, perCorpse, most) == 0.0 && CorpseBonusPct(3, -10, most) == 0.0, "no corpse, no bonus");

    // Blood Golem's knockback (argv 15): inside the radius is pushed to the edge, the edge and beyond stay.
    expect(near(PushedTo(2, knockback), knockback) && near(PushedTo(0, knockback), knockback), "inside the radius is pushed to its edge");
    expect(near(PushedTo(knockback, knockback), knockback) && near(PushedTo(knockback + 3, knockback), knockback + 3),
           "the edge and beyond stay");
    expect(near(PushedTo(2, 0), 2) && near(PushedTo(2, -3), 2), "no radius, no push");

    // Decay Golem's growth (argv 16): in proportion to the corpses, none past the most, none for no corpse or no size.
    expect(near(ScaleBonusPct(most, most, maxScale), maxScale), "the most corpses give the whole growth", ScaleBonusPct(most, most, maxScale), maxScale);
    expect(near(ScaleBonusPct(most / 2, most, maxScale), maxScale / 2), "half the corpses, half the growth");
    expect(near(ScaleBonusPct(most + 7, most, maxScale), maxScale), "no growth past the most");
    expect(ScaleBonusPct(0, most, maxScale) == 0.0 && ScaleBonusPct(3, 0, maxScale) == 0.0 && ScaleBonusPct(3, most, -5) == 0.0,
           "no corpse, no most or no size: no growth");

    // Decay Golem's size is given back by the last meal's event, whatever the clocks say (the 1 ms edge): the stamp is a counter.
    expect(NextMeal(0) == 1 && NextMeal(41) == 42, "a meal takes the next number");
    unsigned long long const first = NextMeal(0), second = NextMeal(first);
    expect(first != second, "two meals in one millisecond are two meals");
    expect(ResetDue(first, first), "the event of the meal held gives the size back, a millisecond early or not");
    expect(!ResetDue(second, first), "the event of an earlier meal gives nothing back while a later one is held");
    expect(ResetDue(second, second), "the later meal's event does");
    expect(!ResetDue(0, first) && !ResetDue(0, 0), "nothing held, nothing to give back");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
