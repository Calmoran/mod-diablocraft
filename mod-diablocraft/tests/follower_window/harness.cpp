// The Follower window's records (src/items/dc_follower_window.h) and the sheet summary they and the player's inventory
// share (src/stats/dc_sheet_summary.h), compiled with no core and driven with sheets built here. No arguments.
//
// 1. SheetSummaryOf equals the formula SheetSummary(Player*) computed before it was split out (copied below as
// Reference,
//    taking the same sheet and the same three inputs), for 2000 seeded sheets: the player's numbers did not move.
// 2. A follower's Damage and Toughness follow its gear: each stat a piece of gear can give moves the right number.
// 3. The text shapes of a Details row, the order and the width of every record, the usable-slot rule.
#include "../../src/items/dc_follower_window.h"

#include <cmath>
#include <cstdio>
#include <random>
#include <string>

using namespace DC;
namespace W = DC::Items::FollowerGear::Window;
namespace G = DC::Items::FollowerGear;

static int failures = 0;
static void Check(bool ok, std::string const& what)
{
    if (!ok)
    {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", what.c_str());
    }
}

static bool Near(double a, double b)
{
    return std::fabs(a - b) <= 1e-9 * std::max(1.0, std::fabs(b));
}

// SheetSummary(Player*) as it was before the split: the average hit, main stat and damage buckets come in as arguments
// in place of the Player calls; every other line is the original.
static DC::Stats::Summary Reference(StatSheet const& sheet, double averageHit, Stat mainStat, double multiplier)
{
    DC::Stats::Summary out;
    double average = averageHit;
    average += sheet[Stat::WeaponFlatDamage] + sheet[Stat::WeaponFlatDamageDelta] / 2;
    double const critFactor = 1 + (sheet[Stat::CritChance] / 100) * (sheet[Stat::CritDamage] / 100);
    out.damage = average * (1 + sheet[mainStat] / 100) * critFactor * sheet.attacksPerSecond;
    out.damage *= multiplier;
    double resistances = (sheet.resistance[Index(Element::Arcane)] + sheet.resistance[Index(Element::Holy)]) / 2;
    for (Element element : {Element::Physical, Element::Fire, Element::Cold, Element::Lightning, Element::Poison})
        resistances += sheet.resistance[Index(element)];
    double const average_resist = resistances / 6;
    double const resistFactor = 1 / (1 + average_resist / (5.0 * sheet.level));
    double const specific = 1 - sheet[Stat::SpecificReduction] / 100;
    double elementFactor =
        1 -
        (sheet.elementReduction[Index(Element::Arcane)] + sheet.elementReduction[Index(Element::Holy)]) / 2 / 100 / 6;
    for (Element element : {Element::Physical, Element::Fire, Element::Cold, Element::Lightning, Element::Poison})
        elementFactor *= 1 - sheet.elementReduction[Index(element)] / 100 / 6;
    elementFactor *= 1 - sheet[Stat::EliteReduction] / 100 / 2;
    double const defenseFactor = (1 - sheet.armorDR) * resistFactor * (1 - sheet.classDR) * specific * elementFactor;
    out.toughness = defenseFactor > 0 ? sheet.maxLife / defenseFactor : 0;
    double const healing =
        sheet[Stat::LifeRegen] + sheet[Stat::LifePerHit] * sheet.attacksPerSecond + sheet[Stat::LifePerKill] * 0.16;
    out.recovery = sheet.maxLife > 0 ? healing * (out.toughness / sheet.maxLife) : 0;
    out.ready = true;
    return out;
}

static StatSheet BaseSheet()
{
    StatSheet sheet;
    sheet.level = 70;
    sheet.maxLife = 100000;
    sheet.attacksPerSecond = 1.2;
    sheet.values[Index(Stat::CritChance)] = 5;
    sheet.values[Index(Stat::CritDamage)] = 50;
    sheet.values[Index(Stat::Strength)] = 1000;
    for (double& resistance : sheet.resistance)
        resistance = 100;
    return sheet;
}

static DC::Stats::Summary Of(StatSheet const& sheet, Stat mainStat = Stat::Strength, double averageHit = 100)
{
    DC::Stats::SummaryInputs in;
    in.averageHit = averageHit;
    in.mainStat = mainStat;
    return DC::Stats::SheetSummaryOf(sheet, in);
}

static void PlayerNumbersDidNotMove()
{
    std::mt19937_64 engine(20261023);
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    unsigned compared = 0;
    for (unsigned run = 0; run < 2000; ++run)
    {
        StatSheet sheet;
        sheet.level = 1 + unsigned(unit(engine) * 69);
        sheet.maxLife = 500 + unit(engine) * 2000000;
        sheet.armorDR = unit(engine) * 0.75;
        sheet.classDR = unit(engine) < 0.5 ? 0.3 : 0.0;
        sheet.attacksPerSecond = 0.5 + unit(engine) * 2.5;
        for (double& v : sheet.values)
            v = unit(engine) * 400;
        for (unsigned element = 0; element < ElementCount; ++element)
        {
            sheet.resistance[element] = unit(engine) * 900;
            sheet.elementReduction[element] = unit(engine) * 30;
        }
        double const averageHit = 1 + unit(engine) * 3000;
        double const multiplier = 1 + unit(engine) * 3;
        Stat const main = Stat(unsigned(unit(engine) * 3));
        DC::Stats::SummaryInputs in;
        in.averageHit = averageHit;
        in.mainStat = main;
        in.multiplier = multiplier;
        DC::Stats::Summary const now = DC::Stats::SheetSummaryOf(sheet, in);
        DC::Stats::Summary const then = Reference(sheet, averageHit, main, multiplier);
        Check(Near(now.damage, then.damage) && Near(now.toughness, then.toughness) &&
                  Near(now.recovery, then.recovery) && now.ready,
              "run " + std::to_string(run) + ": the summary moved");
        ++compared;
    }
    std::printf("compared %u sheets\n", compared);
}

static void GearMovesTheRightNumber()
{
    StatSheet const bare = BaseSheet();
    DC::Stats::Summary const base = Of(bare);
    Check(base.damage > 0 && base.toughness > base.damage * 0 && base.toughness >= bare.maxLife,
          "a bare sheet has numbers");

    auto moved = [&](char const* what, auto change, bool damage, bool toughness)
    {
        StatSheet sheet = BaseSheet();
        change(sheet);
        DC::Stats::Summary const summary = Of(sheet);
        Check((summary.damage > base.damage) == damage, std::string(what) + ": damage");
        Check((summary.toughness > base.toughness) == toughness, std::string(what) + ": toughness");
        if (!damage)
            Check(Near(summary.damage, base.damage), std::string(what) + ": damage unmoved");
        if (!toughness)
            Check(Near(summary.toughness, base.toughness), std::string(what) + ": toughness unmoved");
    };
    moved("main stat", [](StatSheet& s) { s.values[Index(Stat::Strength)] += 500; }, true, false);
    moved("another stat", [](StatSheet& s) { s.values[Index(Stat::Dexterity)] += 500; }, false, false);
    moved("attacks per second", [](StatSheet& s) { s.attacksPerSecond += 0.3; }, true, false);
    moved("crit chance", [](StatSheet& s) { s.values[Index(Stat::CritChance)] += 10; }, true, false);
    moved("crit damage", [](StatSheet& s) { s.values[Index(Stat::CritDamage)] += 50; }, true, false);
    moved("flat damage", [](StatSheet& s) { s.values[Index(Stat::WeaponFlatDamage)] += 200; }, true, false);
    moved("flat damage range", [](StatSheet& s) { s.values[Index(Stat::WeaponFlatDamageDelta)] += 200; }, true, false);
    moved("life", [](StatSheet& s) { s.maxLife += 50000; }, false, true);
    moved("armor", [](StatSheet& s) { s.armorDR += 0.2; }, false, true);
    moved(
        "resistance",
        [](StatSheet& s)
        {
            for (double& r : s.resistance)
                r += 200;
        },
        false, true);
    // Only the weapon, through the inputs: a heavier weapon is more damage and no more toughness.
    DC::Stats::Summary const heavier = Of(bare, Stat::Strength, 400);
    Check(heavier.damage > base.damage && Near(heavier.toughness, base.toughness), "a heavier weapon");
    // The main stat it multiplies by is the follower's own: Dexterity gear moves a Dexterity follower.
    StatSheet dexterity = BaseSheet();
    dexterity.values[Index(Stat::Strength)] = 0;
    dexterity.values[Index(Stat::Dexterity)] = 1000;
    Check(Near(Of(dexterity, Stat::Dexterity).damage, base.damage), "the main stat is read from the owner's stat");
    Check(Of(dexterity, Stat::Strength).damage < base.damage, "a Strength reading of a Dexterity sheet differs");
    // No attacks and no Life are zero numbers, not a failure.
    StatSheet empty;
    Check(Of(empty).damage == 0 && Of(empty).toughness == 0, "an empty sheet");
}

static void Shapes()
{
    Check(W::Int(3762.4) == "3,762", "int " + W::Int(3762.4));
    Check(W::Int(3762.5) == "3,763", "int rounds");
    Check(W::Int(0) == "0", "int zero");
    Check(W::Int(1234567) == "1,234,567", "int groups");
    Check(W::Int(999.4) == "999", "int under a thousand");
    Check(W::Num(1.2) == "1.20", "num " + W::Num(1.2));
    Check(W::Num(1234.567) == "1,234.57", "num groups");
    Check(W::Num(0.004) == "0.00", "num rounds down");
    Check(W::Pct(40) == "40.00%", "pct " + W::Pct(40));
    Check(W::Pct(0) == "0.00%", "pct zero");
    Check(W::Pct(-0.001) == "0.00%", "no negative zero");
    Check(W::Pct(-5) == "-5.00%", "pct negative");
    Check(W::Pct(99.999) == "100.00%", "pct carries");
    Check(W::Whole(1234.6) == "1235", "whole " + W::Whole(1234.6));
    Check(W::Whole(-3) == "0", "whole never negative");
}

static void RecordsAreTheContractsAndFit()
{
    W::View view;
    view.follower = 2;
    view.hired = true;
    view.hub = false;
    view.level = 61;
    view.sheet = BaseSheet();
    view.sheet.values[Index(Stat::Dexterity)] = 12345;
    view.sheet.values[Index(Stat::BlockAmountMin)] = 100;
    view.sheet.values[Index(Stat::BlockAmountMax)] = 2500;
    view.sheet.armorDR = 0.4;
    view.sheet.resistance[Index(Element::Arcane)] = 100;
    view.sheet.resistance[Index(Element::Holy)] = 201;
    view.sheet.resistance[Index(Element::Fire)] = 7;
    view.mainStat = Stat::Dexterity;
    view.summary = Of(view.sheet, Stat::Dexterity);
    view.slots[unsigned(G::Slot::Head)] = {1234, 98765, true};
    view.slots[unsigned(G::Slot::OffHand)] = {0, 0, false};
    view.tiers = {{5, "heal"}, {10, ""}, {15, "crippling-shot"}, {20, ""}};
    view.allSkills = true;

    auto const records = W::Records(view);
    Check(records.front() == W::Record({"W", "2", "1", "0", "61"}), "W");
    Check(records[1][0] == "A" && records[1].size() == 7 && records[1][1] == "1000" && records[1][2] == "12345", "A");
    Check(records[1][5] == std::to_string(std::llround(view.summary.damage)), "A damage is the summary's");
    Check(records[1][6] == std::to_string(std::llround(view.summary.toughness)), "A toughness is the summary's");
    Check(records.back() == W::Record({"E"}), "E last");
    unsigned d = 0, g = 0, k = 0;
    std::string group;
    char last = 'W';
    for (auto const& record : records)
    {
        Check(!record.empty(), "empty record");
        char const kind = record[0][0];
        if (kind == 'D')
        {
            ++d;
            Check(record.size() == 4, "D has group, label, value");
            Check(record[1] == "offense" || record[1] == "defense" || record[1] == "life" || record[1] == "adventure",
                  "D group " + record[1]);
        }
        if (kind == 'G')
            ++g;
        if (kind == 'K')
            ++k;
        // W A D G K E, each kind after the one before it.
        Check(std::string("WADGKE").find(kind) >= std::string("WADGKE").find(last), std::string("order ") + kind);
        last = kind;
        std::size_t width = std::string("DCFOLLOWER").size() + 1;
        for (std::size_t i = 0; i < record.size(); ++i)
            width += record[i].size() + (i ? 1 : 0);
        Check(width <= 255, "a record is under the wire cap");
        for (auto const& field : record)
            Check(field.find('|') == std::string::npos && field.find('\t') == std::string::npos,
                  "separator in a field");
    }
    Check(d == 22, "22 Details rows, got " + std::to_string(d));
    Check(g == 14 && k == 4, "14 slots and 4 tiers");
    Check(records[2][2] == "Damage Increased by Dexterity" && records[2][3] == "12,345.00%",
          "main stat row: " + records[2][3]);
    // The Details rows in order and their values.
    auto const rows = W::Details(view);
    auto row = [&](std::string const& label) -> std::string
    {
        for (auto const& r : rows)
            if (r[1] == label)
                return r[2];
        return "missing";
    };
    Check(row("Block Amount") == "100-2,500", "block amount " + row("Block Amount"));
    Check(row("Damage Reduction") == "40.00%", "damage reduction " + row("Damage Reduction"));
    Check(row("Dodge Chance") == "0.00%" && row("Life Steal") == "0.00%", "the two stats no sheet has");
    Check(row("Attacks per Second") == "1.20", "aps");
    Check(row("Arcane/Holy Resistance") == "151", "arcane/holy is the mean " + row("Arcane/Holy Resistance"));
    Check(row("Fire Resistance") == "7" && row("Physical Resistance") == "100", "the single elements");
    Check(row("Maximum Life") == "100,000", "life");
    // The labels, for the contract check in the test that runs this.
    for (auto const& r : rows)
        std::printf("DETAIL %s|%s\n", r[0].c_str(), r[1].c_str());
    // G rows: slot order, empty and usable.
    unsigned index = 0;
    for (auto const& record : records)
        if (record[0] == "G")
        {
            Check(record[1] == std::string(G::SlotKeys[index]), "G slot order");
            ++index;
        }
    Check(records[2 + d + 1 + 0][1] == "head" && records[2 + d + 1][2] == "1234" && records[2 + d + 1][3] == "98765",
          "G head");
    // K rows.
    Check(records[2 + d + g][0] == "K" && records[2 + d + g] == W::Record({"K", "1", "5", "heal", "1"}), "K 1");
    Check(records[2 + d + g + 2] == W::Record({"K", "3", "15", "crippling-shot", "1"}), "K 3 keeps the hyphen");
    Check(records[2 + d + g + 3] == W::Record({"K", "4", "20", "", "1"}), "K 4");
    view.allSkills = false;
    Check(W::Records(view)[2 + d + g] == W::Record({"K", "1", "5", "heal", "0"}), "K without all skills");
    // The three main stats name themselves.
    view.mainStat = Stat::Intelligence;
    Check(W::Records(view)[2][2] == "Damage Increased by Intelligence", "intelligence label");
    view.mainStat = Stat::Strength;
    Check(W::Records(view)[2][2] == "Damage Increased by Strength", "strength label");
}

static void UsableSlots()
{
    std::vector<G::Kind> kinds;
    auto add = [&](unsigned follower, G::Slot slot) { kinds.push_back({follower, slot, "x", "y"}); };
    for (unsigned slot = 1; slot < G::SlotCount; ++slot)
        add(1, G::Slot(slot));
    for (unsigned slot = 1; slot < G::SlotCount - 1; ++slot)
        add(2, G::Slot(slot)); // no off-hand
    G::Held none, twoHander;
    twoHander.twoHanded = true;
    Check(G::SlotUsable(1, G::Slot::Relic, kinds, none), "the relic slot is always usable");
    Check(G::SlotUsable(1, G::Slot::OffHand, kinds, none), "a follower with off-hand kinds uses the off-hand");
    Check(!G::SlotUsable(2, G::Slot::OffHand, kinds, none), "a follower with no off-hand kind cannot");
    Check(!G::SlotUsable(1, G::Slot::OffHand, kinds, twoHander), "beside a two-hander the off-hand is dimmed");
    Check(G::SlotUsable(1, G::Slot::MainHand, kinds, twoHander), "a two-hander leaves the main hand usable");
    Check(G::SlotUsable(2, G::Slot::Head, kinds, none), "head");
    Check(!G::SlotUsable(3, G::Slot::Head, kinds, none), "a follower with no rows has no slot");
}

static void HireIsTheNpcs()
{
    // The window's hire request is refused with the way to hire; every other request the window makes goes through.
    std::string_view const hire = W::Refusal("hire");
    Check(!hire.empty(), "the window's hire request is refused");
    Check(hire.find("Talk to") != std::string_view::npos && hire.find("hub") != std::string_view::npos,
          "the refusal says to talk to the follower in the hub");
    for (std::string_view verb : {"open", "equip", "unequip", "dismiss", "skill"})
        Check(W::Refusal(verb).empty(), "the window keeps " + std::string(verb));
    Check(W::Refusal("hirex").empty() && W::Refusal("").empty(), "only the exact verb is the hire request");
}

int main()
{
    PlayerNumbersDidNotMove();
    GearMovesTheRightNumber();
    Shapes();
    RecordsAreTheContractsAndFit();
    UsableSlots();
    HireIsTheNpcs();
    if (failures)
    {
        std::fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    std::printf("follower window OK\n");
    return 0;
}
