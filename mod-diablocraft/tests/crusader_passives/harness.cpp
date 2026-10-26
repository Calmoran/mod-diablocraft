// The real dc_crusader_passives.h. The numbers come from argv (read from the sheets by test_crusader_passives.py); nothing else
// is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_passives.h"

#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Crusader::Passive;

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
    // argv: Heavenly Strength's reduction, Fanaticism's attack speed, Righteousness' extra Wrath, Insurmountable's Wrath, Fervor's
    // cooldown reduction, the attack speed cap, Indestructible's seconds and cooldown seconds, Holy Cause's heal percent,
    // Wrathful's Life per point, Lord Commander's Steed Charge and Bombardment percent, Long Arm's seconds, Renewal's Life, Finery's
    // percent per gem, Towering Shield's cooldown percent, a Law's seconds
    if (argc < 18)
        return 2;
    double const reduction = std::atof(argv[1]), fanatic = std::atof(argv[2]), extra = std::atof(argv[3]),
                 gain = std::atof(argv[4]), cooldown = std::atof(argv[5]), cap = std::atof(argv[6]),
                 saveSeconds = std::atof(argv[7]), saveCooldownSeconds = std::atof(argv[8]), holyPct = std::atof(argv[9]),
                 perPoint = std::atof(argv[10]), steedPct = std::atof(argv[11]), bombardPct = std::atof(argv[12]),
                 longArm = std::atof(argv[13]), renewal = std::atof(argv[14]), perGem = std::atof(argv[15]),
                 towerPct = std::atof(argv[16]), lawSeconds = std::atof(argv[17]);
    std::uint64_t const saveMs = std::uint64_t(saveSeconds * 1000), saveCooldownMs = std::uint64_t(saveCooldownSeconds * 1000);

    // The grips.
    Wield none, one, two, oneShield, twoShield, shieldOnly;
    one.oneHand = true;
    two.twoHand = true;
    oneShield.oneHand = oneShield.shield = true;
    twoShield.twoHand = twoShield.shield = true;
    shieldOnly.shield = true;

    // Fervor: only with a one-handed weapon, shield or not.
    expect(FervorOn(one) && FervorOn(oneShield), "a one-handed weapon turns Fervor on");
    expect(!FervorOn(none) && !FervorOn(two) && !FervorOn(twoShield) && !FervorOn(shieldOnly), "no other grip does");

    // Heavenly Strength: the reduction is the price of a two-handed weapon with a shield, and only of that.
    expect(HeavenlyStrengthPct(twoShield, reduction) == reduction, "a two-handed weapon and a shield pay the reduction",
           HeavenlyStrengthPct(twoShield, reduction), reduction);
    expect(HeavenlyStrengthPct(two, reduction) == 0 && HeavenlyStrengthPct(oneShield, reduction) == 0 &&
               HeavenlyStrengthPct(one, reduction) == 0 && HeavenlyStrengthPct(shieldOnly, reduction) == 0 &&
               HeavenlyStrengthPct(none, reduction) == 0,
           "no other grip pays it");
    expect(HeavenlyStrengthPct(twoShield, 0) == 0 && HeavenlyStrengthPct(twoShield, -5) == 0, "no number, no reduction");

    // Heavenly Strength's grip: a Crusader with the passive, and nobody else.
    expect(HeavenlyStrengthGrip(true, true), "a Crusader with the passive may hold the grip");
    expect(!HeavenlyStrengthGrip(true, false), "a Crusader without the passive may not");
    expect(!HeavenlyStrengthGrip(false, true) && !HeavenlyStrengthGrip(false, false), "another class may not, passive or not");
    // Unpicked: the shield goes when a two-hander and a shield are both worn and the grip is not allowed, never otherwise.
    expect(GripBroken(twoShield, false), "unpicked with a two-hander and a shield, the grip is broken");
    expect(!GripBroken(twoShield, true), "picked, the grip stands");
    expect(!GripBroken(oneShield, false) && !GripBroken(two, false) && !GripBroken(shieldOnly, false) && !GripBroken(none, false),
           "no other wield is a broken grip");

    // Vigilant: every element but Physical.
    bool others = true;
    for (unsigned e = 0; e < DC::ElementCount; ++e)
        others = others && (VigilantReduces(DC::Element(e)) == (DC::Element(e) != DC::Element::Physical));
    expect(others, "Vigilant reduces every element but Physical");

    // Fanaticism: the four skills the sheet names, nothing else.
    expect(FanaticismSkill("Punish") && FanaticismSkill("Slash") && FanaticismSkill("Smite") && FanaticismSkill("Justice"),
           "the four named skills");
    expect(!FanaticismSkill("Shield Bash") && !FanaticismSkill("Blessed Hammer") && !FanaticismSkill("") && !FanaticismSkill("punish"),
           "no other skill");
    // Its share joins the sum the speed was built from: 2.0 attacks a second with 20% in it, 15% more.
    expect(FanaticismAps(2.0, 20, fanatic, cap) > 2.0, "the speed rises");
    double const sum = 2.0 * (1 + (20 + fanatic) / 100) / (1 + 20.0 / 100);
    expect(FanaticismAps(2.0, 20, fanatic, 100) == sum, "by the sum rule", FanaticismAps(2.0, 20, fanatic, 100), sum);
    expect(FanaticismAps(2.0, 20, fanatic, 2.1) == 2.1, "held to the attack speed cap");
    expect(FanaticismAps(2.0, 20, fanatic, 1.0) == 2.0, "never below what it was");
    expect(FanaticismAps(0, 20, fanatic, cap) == 0 && FanaticismAps(2.0, 20, 0, cap) == 2.0 && FanaticismAps(2.0, -100, fanatic, cap) == 2.0,
           "no speed, no share, or a sheet at its floor: unchanged");

    // Righteousness and Insurmountable pay their Wrath.
    expect(RighteousnessWrath(true, extra) == extra && RighteousnessWrath(false, extra) == 0 && RighteousnessWrath(true, 0) == 0,
           "Righteousness pays its extra for a primary only");
    expect(InsurmountableWrath(gain) == gain && InsurmountableWrath(0) == 0 && InsurmountableWrath(-1) == 0, "a block pays the sheet's Wrath");

    // Fervor's cooldown reduction as the sheet takes it.
    expect(CooldownContribution(cooldown) == cooldown && CooldownContribution(250) == 100 && CooldownContribution(-5) == 0,
           "held to 0 through 100");

    // The bits are distinct.
    expect((FervorBit | VigilantBit | RighteousnessBit | DivineFortressBit | HoldGroundBit | IronMaidenBit | FineryBit) == 127,
           "seven separate bits");

    // Indestructible: a fatal hit saves once, the save lasts its seconds, and the next waits out the cooldown.
    Fatal fatal;
    expect(!fatal.Active(1000), "no save, nothing active");
    expect(!fatal.Save(1000, 99, 100, saveCooldownMs, saveMs), "a hit that leaves Life saves nothing");
    expect(fatal.Save(1000, 100, 100, saveCooldownMs, saveMs), "a hit that takes all the Life saves");
    expect(fatal.Active(1000) && fatal.Active(1000 + saveMs - 1) && !fatal.Active(1000 + saveMs), "for exactly its seconds");
    expect(!fatal.Save(1000 + saveMs, 500, 100, saveCooldownMs, saveMs), "not again inside the cooldown");
    expect(!fatal.Save(1000 + saveCooldownMs - 1, 500, 100, saveCooldownMs, saveMs), "to the last millisecond of it");
    expect(fatal.Save(1000 + saveCooldownMs, 500, 100, saveCooldownMs, saveMs), "and again once it has run");
    expect(saveCooldownMs > saveMs, "the cooldown outlasts the save", double(saveCooldownMs), double(saveMs));
    Fatal never;
    expect(!never.Save(1000, 500, 100, saveCooldownMs, 0), "a save of no time is no save");

    // Holy Cause: a Holy hit heals its share of the Life; any other hit nothing.
    expect(HolyCauseHeal(true, 1000, holyPct) == 1000 * holyPct / 100, "a Holy hit heals the share", HolyCauseHeal(true, 1000, holyPct),
           1000 * holyPct / 100);
    expect(HolyCauseHeal(false, 1000, holyPct) == 0 && HolyCauseHeal(true, 0, holyPct) == 0 && HolyCauseHeal(true, 1000, 0) == 0,
           "no other hit, no Life, no share heals");

    // Wrathful: Life for every point of Wrath spent.
    expect(WrathfulHeal(perPoint, 30) == perPoint * 30 && WrathfulHeal(perPoint, 0) == 0 && WrathfulHeal(0, 30) == 0 &&
               WrathfulHeal(perPoint, -3) == 0,
           "Wrathful heals per point spent and nothing for none");

    // Divine Fortress: the Armor percent is the Block Chance, never below nothing.
    expect(DivineFortressPct(30) == 30 && DivineFortressPct(0) == 0 && DivineFortressPct(-5) == 0, "Armor percent equal to the Block Chance");

    // Lord Commander: the two skills it names take their own percent, no other skill any; a cut is a share of what is left.
    expect(LordCommanderQualifier("Steed Charge") == "steed_charge" && LordCommanderQualifier("Bombardment") == "bombardment",
           "the two skills and their sheet qualifiers");
    expect(LordCommanderQualifier("Provoke").empty() && LordCommanderQualifier("").empty() && LordCommanderQualifier("steed charge").empty(),
           "no other skill");
    expect(steedPct != bombardPct, "the two shares differ on the sheet", steedPct, bombardPct);
    expect(CooldownCut(20000, steedPct) == std::uint32_t(20000 * steedPct / 100), "the cut is the share of what is left",
           double(CooldownCut(20000, steedPct)), 20000 * steedPct / 100);
    expect(CooldownCut(20000, 100) == 20000 && CooldownCut(20000, 250) == 20000 && CooldownCut(20000, -5) == 0 && CooldownCut(0, 50) == 0,
           "never more than is left, never negative");
    expect(LordCommanderDamage("Phalanx") && !LordCommanderDamage("Punish") && !LordCommanderDamage(""), "its damage bonus is Phalanx's alone");

    // Hold Your Ground: no dodge at all.
    expect(DodgeFactor(true) == 0.0 && DodgeFactor(false) == 1.0, "no dodge with the passive, the same without");

    // Long Arm of the Law: a Law's active time grows by the seconds; no time stays none, no passive adds nothing.
    expect(LongArm(lawSeconds, longArm) == lawSeconds + longArm, "the active effect lasts the seconds longer", LongArm(lawSeconds, longArm),
           lawSeconds + longArm);
    expect(LongArm(0, longArm) == 0 && LongArm(lawSeconds, 0) == lawSeconds && LongArm(lawSeconds, -2) == lawSeconds,
           "no time stays none; no passive, no change");

    // Renewal: the sheet's Life on a block, nothing for no number.
    expect(RenewalHeal(renewal) == renewal && RenewalHeal(0) == 0 && RenewalHeal(-1) == 0, "a block heals the sheet's Life");

    // Finery: the percent per gem times the gems, none without any.
    expect(FineryPct(perGem, 10) == perGem * 10 && FineryPct(perGem, 0) == 0 && FineryPct(0, 10) == 0 && FineryPct(-1, 10) == 0,
           "the percent per gem times the gems", FineryPct(perGem, 10), perGem * 10);

    // Blunt and Towering Shield name their skills and no others.
    expect(BluntSkill("Justice") && BluntSkill("Blessed Hammer") && !BluntSkill("Blessed Shield") && !BluntSkill("Punish") && !BluntSkill(""),
           "Blunt: Justice and Blessed Hammer");
    expect(ToweringDamageSkill("Punish") && ToweringDamageSkill("Shield Bash") && ToweringDamageSkill("Blessed Shield") &&
               !ToweringDamageSkill("Shield Glare") && !ToweringDamageSkill("Justice") && !ToweringDamageSkill(""),
           "Towering Shield's damage: Punish, Shield Bash and Blessed Shield");
    expect(ToweringCooldownSkill("Shield Glare") && !ToweringCooldownSkill("Shield Bash") && !ToweringCooldownSkill(""),
           "Towering Shield's cooldown: Shield Glare alone");
    expect(towerPct > 0 && CooldownCut(10000, towerPct) == std::uint32_t(10000 * towerPct / 100), "its share of the cooldown left",
           double(CooldownCut(10000, towerPct)), 10000 * towerPct / 100);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
