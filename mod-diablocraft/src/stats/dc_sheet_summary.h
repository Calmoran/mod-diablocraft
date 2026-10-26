#ifndef DC_SHEET_SUMMARY_H
#define DC_SHEET_SUMMARY_H

// The three values D3's inventory screen shows above the DETAILS button, computed from a sheet. The player's sheet and a
// follower's share this one formula (formulas and citations in docs/research/sheet-summary.md). It includes no core
// header, so scripts/tests/stats/ compiles it against the sheets it is given.

#include "../combat/dc_weapon_flat.h"
#include "../common/dc_common.h"

namespace DC::Stats
{
    // Display only - nothing in combat reads them - but they are stat maths, so they are computed here and never in Lua
    // (00 §5, 12-ui §2).
    struct Summary
    {
        bool ready = false;
        double damage = 0;    // sheet DPS, sheet-summary §2
        double toughness = 0; // effective health pool, §3
        double recovery = 0;  // toughness restored per second, §4 (patch 2.1.0)
    };

    // What the sheet itself does not hold: the weapon the owner swings, the stat that owner multiplies damage by, and
    // the owner's own damage buckets.
    struct SummaryInputs
    {
        // The average weapon hit before the sheet's flat damage (both hands averaged for a dual wielder; the 1-2 of a
        // bare hand when none is held).
        double averageHit = 1.5;
        Stat mainStat = Stat::Strength;
        // (1 + the owner's damage bonus / 100) times its damage factor; 1 for an owner with neither (a follower).
        double multiplier = 1;
    };

    inline Summary SheetSummaryOf(StatSheet const& sheet, SummaryInputs const& in)
    {
        Summary out;

        // Damage, sheet-summary §2.2 and §6.1: the average weapon hit times the
        // primary attribute, the crit factor and the sheet's attacks per second.
        // Elemental %, elite % and skill % are deliberately absent - §2.2F lists
        // all three as off-sheet in D3 as well.
        //
        // One documented deviation: D3 takes the harmonic mean of both weapons'
        // attack rates while dual wielding (§2.3E). Our engine has one APS,
        // built from the main hand in RefreshWeapon, and combat swings at
        // that rate, so the sheet uses it too. A sheet that disagreed with the
        // repeat interval is the bug this whole number exists to avoid.
        double const average = in.averageHit + DC::Combat::FlatDamageAverage(sheet);
        double const critFactor = 1 + (sheet[Stat::CritChance] / 100) * (sheet[Stat::CritDamage] / 100);
        out.damage = average * (1 + sheet[in.mainStat] / 100) * critFactor * sheet.attacksPerSecond;
        out.damage *= in.multiplier;

        // Toughness, sheet-summary §3.2. resavg is D3's mean resistance over its
        // six elements; our sheet carries Arcane and Holy apart, and D3's sheet
        // shows them as one "Arcane/Holy" row, so they average into one term.
        double resistances = (sheet.resistance[Index(Element::Arcane)] + sheet.resistance[Index(Element::Holy)]) / 2;
        for (Element element : {Element::Physical, Element::Fire, Element::Cold, Element::Lightning, Element::Poison})
            resistances += sheet.resistance[Index(element)];
        double const average_resist = resistances / 6;
        double const resistFactor = 1 / (1 + average_resist / (5.0 * sheet.level));
        // Class DR and the specific-reduction bucket are D3Planner's dmgred
        // (§5 gap table, "class 30% innate"), and D3's own sheet Toughness
        // includes them. These are the same factors Calculate folds into
        // damageTaken[], taken apart here only because Toughness wants the
        // average resistance rather than one element's.
        double const specific = 1 - sheet[Stat::SpecificReduction] / 100;
        // An element's own damage reduction (Stat::ElementReduction) counts for
        // that element's sixth of incoming damage, as D3Planner's defavg weighs
        // colddef (stats_full.js:607); Arcane and Holy share D3's one sixth.
        double elementFactor = 1 - (sheet.elementReduction[Index(Element::Arcane)] +
                                    sheet.elementReduction[Index(Element::Holy)]) / 2 / 100 / 6;
        for (Element element : {Element::Physical, Element::Fire, Element::Cold, Element::Lightning, Element::Poison})
            elementFactor *= 1 - sheet.elementReduction[Index(element)] / 100 / 6;
        // Elite Damage Reduction counts at half, D3Planner's defense_factor (stats_full.js:616, edef / 2).
        elementFactor *= 1 - sheet[Stat::EliteReduction] / 100 / 2;
        double const defenseFactor = (1 - sheet.armorDR) * resistFactor * (1 - sheet.classDR) * specific * elementFactor;
        out.toughness = defenseFactor > 0 ? sheet.maxLife / defenseFactor : 0;

        // Recovery, sheet-summary §4.2: patch 2.1.0 replaced Healing with
        // Healing x Toughness / Life. Health Globe
        // Healing Bonus and % Life Regeneration are not stats we roll (§5), so
        // their terms are absent rather than filled with a guess.
        double const healing =
            sheet[Stat::LifeRegen] + sheet[Stat::LifePerHit] * sheet.attacksPerSecond + sheet[Stat::LifePerKill] * 0.16;
        out.recovery = sheet.maxLife > 0 ? healing * (out.toughness / sheet.maxLife) : 0;
        out.ready = true;
        return out;
    }
} // namespace DC::Stats

#endif
