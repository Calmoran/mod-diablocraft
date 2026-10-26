// The real dc_crusader_phalanx.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_phalanx.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_phalanx.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::Phalanx;

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
    // argv: the base speed, Shield Charge's and Stampede's speed bonus, the stun chance, the fire rate, the internal
    // cooldown, the reach, then the five runes A to E, then the charge's yards a second
    if (argc < 14)
        return 2;
    double const base = std::atof(argv[1]), shieldBonus = std::atof(argv[2]), stampedeBonus = std::atof(argv[3]),
                 chance = std::atof(argv[4]), fire = std::atof(argv[5]), cooldown = std::atof(argv[6]),
                 reach = std::atof(argv[7]), yards = std::atof(argv[13]);
    std::string const bowmen = argv[8], charge = argv[9], stampede = argv[10], bearers = argv[11],
                      bodyguard = argv[12];

    expect(RuneOf(bowmen) == Rune::Bowmen && RuneOf(charge) == Rune::ShieldCharge &&
               RuneOf(stampede) == Rune::Stampede && RuneOf(bearers) == Rune::ShieldBearers &&
               RuneOf(bodyguard) == Rune::Bodyguard,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {bowmen, charge, stampede, bearers, bodyguard})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Phalanx") == Rune::None, "the base skill and a stranger are no rune");

    // What the avatars do: the skill and two runes charge, each of the others does its one thing.
    expect(BehaviorOf(Rune::None) == Behavior::Charge && BehaviorOf(Rune::ShieldCharge) == Behavior::Charge &&
               BehaviorOf(Rune::Stampede) == Behavior::Charge,
           "the skill, Shield Charge and Stampede charge");
    expect(BehaviorOf(Rune::Bowmen) == Behavior::Follow && BehaviorOf(Rune::ShieldBearers) == Behavior::Stand &&
               BehaviorOf(Rune::Bodyguard) == Behavior::Fight,
           "Bowmen follow, Shield Bearers stand, the Bodyguard fights");
    expect(HitsTheLine(Rune::None) && HitsTheLine(Rune::ShieldCharge) && HitsTheLine(Rune::Stampede),
           "the charges hit the line");
    expect(!HitsTheLine(Rune::Bowmen) && !HitsTheLine(Rune::ShieldBearers) && !HitsTheLine(Rune::Bodyguard),
           "the others send nothing down it");

    // The gated runes: the cooldown, for those three only.
    for (Rune rune : {Rune::Bowmen, Rune::ShieldBearers, Rune::Bodyguard})
        expect(CooldownSeconds(rune, cooldown) == cooldown, "a gated rune has its cooldown",
               CooldownSeconds(rune, cooldown), cooldown);
    for (Rune rune : {Rune::None, Rune::ShieldCharge, Rune::Stampede})
        expect(CooldownSeconds(rune, cooldown) == 0, "the charges have no cooldown");
    expect(CooldownSeconds(Rune::Bowmen, 0) == 0, "no cooldown gives nothing");

    // The charge speed: the plain charge is 1, the runes the power file's ratio.
    expect(SpeedRatio(Rune::None, base, shieldBonus, stampedeBonus) == 1.0, "the plain charge is the base speed");
    expect(SpeedRatio(Rune::ShieldCharge, base, shieldBonus, stampedeBonus) == (base + shieldBonus) / base,
           "Shield Charge runs at its ratio", SpeedRatio(Rune::ShieldCharge, base, shieldBonus, stampedeBonus),
           (base + shieldBonus) / base);
    expect(SpeedRatio(Rune::Stampede, base, shieldBonus, stampedeBonus) == (base + stampedeBonus) / base,
           "Stampede runs at its ratio", SpeedRatio(Rune::Stampede, base, shieldBonus, stampedeBonus),
           (base + stampedeBonus) / base);
    expect(SpeedRatio(Rune::Stampede, 0, shieldBonus, stampedeBonus) == 1.0, "no base speed, no ratio");
    expect(SpeedRatio(Rune::Stampede, base, shieldBonus, -1) == 1.0, "a negative bonus does not slow it");

    // The charge speed in yards a second: a creature that runs at 7 covers the sheet's number, and each rune's ratio on top.
    for (Rune rune : {Rune::None, Rune::ShieldCharge, Rune::Stampede})
    {
        double const ratio = SpeedRatio(rune, base, shieldBonus, stampedeBonus);
        double const covered = 7.0 * RunRate(yards, 7.0, ratio);
        expect(covered > yards * ratio - 1e-9 && covered < yards * ratio + 1e-9,
               "the avatars cover the sheet's yards a second times the rune's ratio", covered, yards * ratio);
    }
    expect(RunRate(0, 7.0, 1.5) == 1.5 && RunRate(-1, 7.0, 1.5) == 1.5, "no speed set, the creature's own speed times the ratio");
    expect(RunRate(yards, 0, 1.0) == 1.0, "no creature speed to compare, the creature's own");

    // Stampede's stun: under the chance, never at it, for that rune only.
    expect(Stuns(Rune::Stampede, chance - 0.01, chance) && !Stuns(Rune::Stampede, chance, chance) &&
               !Stuns(Rune::Stampede, 100, chance),
           "a roll under the chance stuns", chance, 0);
    expect(!Stuns(Rune::Stampede, 0, 0) && !Stuns(Rune::Stampede, 0, -5), "no chance never stuns");
    for (Rune rune : {Rune::None, Rune::Bowmen, Rune::ShieldCharge, Rune::ShieldBearers, Rune::Bodyguard})
        expect(!Stuns(rune, 0, chance), "no other rune stuns");

    // The bowmen's shot: once the clock has run the fire rate.
    expect(ShotDue(fire * 1000.0, fire) && ShotDue(fire * 1000.0 + 1, fire) && !ShotDue(fire * 1000.0 - 1, fire),
           "a shot is due at the fire rate");
    expect(!ShotDue(10000, 0) && !ShotDue(10000, -1), "no fire rate, no shot");

    // Where the run ends: the point, or the reach along the way to it.
    expect(RunShare(reach / 2, reach) == 1.0 && RunShare(reach, reach) == 1.0, "a point within the reach is run to");
    expect(RunShare(reach * 2, reach) == 0.5, "a point twice as far is run half way", RunShare(reach * 2, reach), 0.5);
    expect(RunShare(0, reach) == 0 && RunShare(10, 0) == 0, "no distance or no reach, no run");

    // Side by side, centred on the line.
    expect(Abreast(0, 1, 2) == 0, "one avatar is on the line");
    expect(Abreast(0, 2, 2) == -1 && Abreast(1, 2, 2) == 1, "two stand one yard either side at a gap of two");
    expect(Abreast(0, 3, 2) == -2 && Abreast(1, 3, 2) == 0 && Abreast(2, 3, 2) == 2, "three are centred");
    expect(Abreast(0, 0, 2) == 0, "none is nowhere");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
