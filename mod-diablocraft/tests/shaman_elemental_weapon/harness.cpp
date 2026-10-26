// The real dc_shaman_elemental_weapon.h, no core. Every number comes from argv (test_shaman_elemental_weapon.py reads the
// sheet): the base imbue's damage bonus and Maelstrom, a rune's passive and activated bonus, Windfury's two counts, Rockbiter's
// two Armor numbers, Windfury's attack speed, Maelstrom Weapon's count and Maelstrom. Prints "cases=N failures=M" and exits 0,
// or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_elemental_weapon.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::ElementalWeapon;
using DC::Combat::Shaman::Attunement::Element;

static int failures = 0;
static int cases = 0;

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
    if (argc < 13)
        return 2;
    double const basePassive = std::atof(argv[1]), baseActive = std::atof(argv[2]), basePct = std::atof(argv[3]),
                 runePassive = std::atof(argv[4]), runeActive = std::atof(argv[5]);
    unsigned const windfuryPassive = unsigned(std::atof(argv[6])), windfuryActive = unsigned(std::atof(argv[7])),
                   weaponEvery = unsigned(std::atof(argv[11]));
    double const armorPassive = std::atof(argv[8]), armorActive = std::atof(argv[9]), speed = std::atof(argv[10]),
                 weaponPct = std::atof(argv[12]);
    Element const elements[] = {Element::Fire, Element::Cold, Element::Physical, Element::Lightning};

    // The imbue a record gives.
    expect(RuneOf("") == Rune::Base && RuneOf("Flametongue") == Rune::Flametongue && RuneOf("Frostbrand") == Rune::Frostbrand &&
               RuneOf("Windfury") == Rune::Windfury && RuneOf("Rockbiter") == Rune::Rockbiter &&
               RuneOf("Maelstrom Weapon") == Rune::MaelstromWeapon,
           "each imbue by its name");
    expect(RuneOf("Chain Frost") == Rune::Off, "a stranger is no imbue");

    // The element a hit deals: the seam's name wins over the record's school, and none leaves the record's.
    expect(DealtElement("fire", Element::Cold) == Element::Fire && DealtElement("cold", Element::Fire) == Element::Cold &&
               DealtElement("lightning", Element::Fire) == Element::Lightning &&
               DealtElement("physical", Element::Fire) == Element::Physical,
           "the seam names the dealt element");
    expect(DealtElement(nullptr, Element::Cold) == Element::Cold && DealtElement("", Element::Fire) == Element::Fire &&
               DealtElement("plasma", Element::Physical) == Element::Physical,
           "and none or a stranger leaves the record's school");

    // Which skills an imbue boosts: the base every one, a rune its own element, Maelstrom Weapon none.
    for (Element element : elements)
    {
        expect(Boosts(Rune::Base, element), "the base imbue boosts every element");
        expect(!Boosts(Rune::MaelstromWeapon, element) && !Boosts(Rune::Off, element), "Maelstrom Weapon and none boost nothing");
    }
    for (Element element : elements)
    {
        expect(Boosts(Rune::Flametongue, element) == (element == Element::Fire), "Flametongue boosts Fire only");
        expect(Boosts(Rune::Frostbrand, element) == (element == Element::Cold), "Frostbrand boosts Cold only");
        expect(Boosts(Rune::Windfury, element) == (element == Element::Lightning), "Windfury boosts Lightning only");
        expect(Boosts(Rune::Rockbiter, element) == (element == Element::Physical), "Rockbiter boosts Physical only");
    }

    // The bonuses: the passive's always, the activation's on top only while activated.
    Bonus bonus = DamageBonus(Rune::Base, Element::Cold, false, basePassive, baseActive);
    expect(bonus.passivePct == basePassive && bonus.activePct == 0, "the base passive alone", bonus.passivePct, basePassive);
    bonus = DamageBonus(Rune::Base, Element::Cold, true, basePassive, baseActive);
    expect(bonus.passivePct == basePassive && bonus.activePct == baseActive, "and activated, with the activation's on top",
           bonus.activePct, baseActive);
    bonus = DamageBonus(Rune::Flametongue, Element::Fire, true, runePassive, runeActive);
    expect(bonus.passivePct == runePassive && bonus.activePct == runeActive, "Flametongue's Fire hit", bonus.activePct, runeActive);
    bonus = DamageBonus(Rune::Flametongue, Element::Cold, true, runePassive, runeActive);
    expect(bonus.passivePct == 0 && bonus.activePct == 0, "and not a Cold hit");
    bonus = DamageBonus(Rune::Off, Element::Fire, true, runePassive, runeActive);
    expect(bonus.passivePct == 0 && bonus.activePct == 0, "no imbue, no bonus");

    // What rides on a hit.
    for (bool active : {false, true})
    {
        Effect e = EffectOf(Rune::Flametongue, Element::Fire, active);
        expect(e.burn && !e.chill && !e.freeze && !e.echo, "Flametongue burns a Fire hit");
        e = EffectOf(Rune::Flametongue, Element::Cold, active);
        expect(!e.burn && !e.chill && !e.freeze && !e.echo, "and no other");
        e = EffectOf(Rune::Frostbrand, Element::Cold, active);
        expect(e.chill && e.freeze == active && !e.burn && !e.echo, "Frostbrand chills a Cold hit and freezes it only activated");
        e = EffectOf(Rune::Frostbrand, Element::Fire, active);
        expect(!e.chill && !e.freeze, "and not a Fire one");
        e = EffectOf(Rune::Windfury, Element::Lightning, active);
        expect(e.echo && !e.burn && !e.chill, "Windfury counts a Lightning hit");
        e = EffectOf(Rune::Windfury, Element::Physical, active);
        expect(!e.echo, "and not a Physical one");
        for (Rune rune : {Rune::Off, Rune::Base, Rune::Rockbiter, Rune::MaelstromWeapon})
            for (Element element : elements)
            {
                e = EffectOf(rune, element, active);
                expect(!e.burn && !e.chill && !e.freeze && !e.echo, "the other imbues ride on no hit");
            }
    }

    // Every Nth: Windfury's hits (more often activated) and Maelstrom Weapon's casts.
    unsigned count = 0, fired = 0;
    for (unsigned hit = 1; hit <= windfuryPassive * 4; ++hit)
        fired += Reached(count, windfuryPassive);
    expect(fired == 4 && count == 0, "every passive-count'th hit strikes again", fired, 4);
    count = 0;
    fired = 0;
    for (unsigned hit = 1; hit <= windfuryActive * 6; ++hit)
        fired += Reached(count, windfuryActive);
    expect(fired == 6, "and more often activated", fired, 6);
    expect(windfuryActive < windfuryPassive, "the activation strikes more often");
    count = 0;
    bool early = false;
    for (unsigned hit = 1; hit < weaponEvery; ++hit)
        early = early || Reached(count, weaponEvery);
    expect(!early && Reached(count, weaponEvery), "the free cast comes on the count, not before", weaponEvery, 0);
    count = 0;
    expect(!Reached(count, 0) && count == 0, "no count, never");

    // The Maelstrom: the base imbue on every generating skill, Maelstrom Weapon activated on a Primary only.
    expect(GenerationPct(Rune::Base, false, false, basePct) == basePct && GenerationPct(Rune::Base, true, true, basePct) == basePct,
           "the base imbue pays more on every skill, active or not", GenerationPct(Rune::Base, false, false, basePct), basePct);
    expect(GenerationPct(Rune::MaelstromWeapon, true, true, weaponPct) == weaponPct, "Maelstrom Weapon activated pays on a Primary");
    expect(GenerationPct(Rune::MaelstromWeapon, false, true, weaponPct) == 0, "not before the activation");
    expect(GenerationPct(Rune::MaelstromWeapon, true, false, weaponPct) == 0, "and not on another skill");
    for (Rune rune : {Rune::Off, Rune::Flametongue, Rune::Frostbrand, Rune::Windfury, Rune::Rockbiter})
        expect(GenerationPct(rune, true, true, weaponPct) == 0, "no other imbue pays more Maelstrom");

    // The sheet.
    Sheet sheet = SheetOf(Rune::Rockbiter, false, armorPassive, armorActive, speed);
    expect(sheet.armorPct == armorPassive && sheet.attackSpeedPct == 0, "Rockbiter's passive Armor", sheet.armorPct, armorPassive);
    sheet = SheetOf(Rune::Rockbiter, true, armorPassive, armorActive, speed);
    expect(sheet.armorPct == armorPassive + armorActive, "and its activation on top", sheet.armorPct, armorPassive + armorActive);
    sheet = SheetOf(Rune::Windfury, false, armorPassive, armorActive, speed);
    expect(sheet.armorPct == 0 && sheet.attackSpeedPct == 0, "Windfury's speed only activated");
    sheet = SheetOf(Rune::Windfury, true, armorPassive, armorActive, speed);
    expect(sheet.attackSpeedPct == speed && sheet.armorPct == 0, "and then the sheet's speed", sheet.attackSpeedPct, speed);
    for (Rune rune : {Rune::Off, Rune::Base, Rune::Flametongue, Rune::Frostbrand, Rune::MaelstromWeapon})
    {
        sheet = SheetOf(rune, true, armorPassive, armorActive, speed);
        expect(sheet.armorPct == 0 && sheet.attackSpeedPct == 0, "no other imbue touches the sheet");
    }

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
