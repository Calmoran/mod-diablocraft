#include "../../../src/common/dc_common.h"

#include <cmath>
#include <map>
#include "../../../src/common/dc_numeric_data.h"
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include "../../../src/stats/dc_movement_math.h"

// Isolated source-shaped fixtures stand in for WORLD snapshots; production
// dc_numeric_data.cpp is deliberately not linked into these pure math tests.
namespace DC::NumericData
{
std::map<std::string, double> rules{
    {"crit_chance_pct", 5}, {"crit_damage_pct", 50}, {"attack_speed_cap", 5},
    {"movement_cap_pct", 25}, {"magic_find_cap_pct", 300}, {"gold_find_cap_pct", 300},
    {"xp_penalty_level", 70}, {"xp_divisor", 10}, {"all_res_per_int", 0.1},
    {"class_dr_pct", 30}, {"armor_level_coefficient", 50}, {"resistance_level_coefficient", 5}};
double Rule(char const* name) { return rules.at(name); }
unsigned MaximumLevel() { return 70; }
double BaseFury(unsigned) { return 100; }
BlockTuning Block() { return {75, 100, 1}; }
}

using namespace DC;
void Check(bool ok, char const* message) { if (!ok) throw std::runtime_error(message); }
void Near(double actual, double expected) { Check(std::abs(actual - expected) < 1e-8, "Unexpected formula result"); }
template<typename F> void Reject(F operation)
{
    bool rejected = false;
    try { operation(); } catch (std::invalid_argument const&) { rejected = true; }
    Check(rejected, "Invalid input was not rejected");
}

int main(int argc, char** argv)
{
    try
    {
        Check(argc == 2, "Pass the base CSV path");
        std::ifstream input(argv[1]);
        Check(input.good(), "Cannot read base CSV");
        std::string line;
        std::getline(input, line);
        unsigned count = 0;
        BaseStats seventy;
        while (std::getline(input, line))
        {
            std::istringstream row(line);
            std::array<double, 10> cells{};
            for (double& value : cells) { std::string cell; Check(bool(std::getline(row, cell, ',')), "Malformed CSV row"); value = std::stod(cell); }
            BaseStats base{static_cast<unsigned>(cells[0]), cells[1], cells[2], cells[3], cells[4], cells[5], cells[6], cells[8], cells[9]};
            auto sheet = Calculate(base, {});
            Near(sheet.maxLife, cells[7]); Near(sheet[Stat::Armor], cells[8]);
            Near(sheet[Stat::CritChance], 5); Near(sheet[Stat::CritDamage], 50);
            Near(sheet[Stat::AllResistance], cells[3] / 10);
            Near(sheet.armorDR, cells[8] / (cells[8] + 50 * cells[0]));
            for (unsigned element = 0; element < ElementCount; ++element)
                Near(sheet.damageTaken[element], (1 - sheet.armorDR) * (1 - sheet.resistanceDR[element]) * 0.7);
            Check(Serialize(DeserializeSheet(Serialize(sheet))) == Serialize(sheet), "Sheet persistence changed values");
            if (base.level == 70) seventy = base;
            ++count;
        }
        Check(count == 70, "Expected 70 base CSV records");
        NumericData::rules["crit_chance_pct"] = 7;
        NumericData::rules["movement_cap_pct"] = 18;
        Near(Calculate(seventy, {})[Stat::CritChance], 7);
        NumericData::rules["crit_chance_pct"] = 5;
        NumericData::rules["movement_cap_pct"] = 25;
        auto naked = Calculate(seventy, {});
        Near(naked[Stat::Strength], 217); Near(naked[Stat::Vitality], 147);
        Near(naked.maxLife, 15016); Near(naked[Stat::Armor], 294);

        CharacterStats state;
        auto add = [&](Source source, Stat stat, std::uint64_t id, double value, Bucket bucket = Bucket::Flat, Element element = Element::Physical)
            { SetContribution(state, {source, stat, id, value, bucket, element}); };
        add(Source::Items, Stat::Strength, 1, 50);
        add(Source::Items, Stat::Strength, 1, 100); // Replace, not accumulate.
        add(Source::Passives, Stat::Strength, 1, 20, Bucket::Percent);
        add(Source::Items, Stat::Armor, 1, 100);
        add(Source::Passives, Stat::Armor, 1, 25, Bucket::Percent);
        add(Source::Paragon, Stat::LifePercent, 1, 25);
        add(Source::Items, Stat::CooldownReduction, 1, 10);
        add(Source::Items, Stat::CooldownReduction, 2, 20);
        add(Source::Items, Stat::ResourceCostReduction, 1, 10);
        add(Source::Passives, Stat::ResourceCostReduction, 1, 20);
        add(Source::Items, Stat::MovementSpeed, 1, 12);
        add(Source::Paragon, Stat::MovementSpeed, 1, 25);
        add(Source::Passives, Stat::MovementSpeed, 1, 10);
        add(Source::Items, Stat::MovementSpeed, 2, 15, Bucket::Uncapped);
        add(Source::Items, Stat::SingleResistance, 1, 10, Bucket::Flat, Element::Fire);
        add(Source::Items, Stat::ElementalDamage, 1, 20, Bucket::Flat, Element::Fire);
        add(Source::Temporary, Stat::SpecificReduction, 1, 50);
        add(Source::Passives, Stat::SpecificReduction, 1, 50);
        add(Source::Items, Stat::WeaponAPS, 1, 1.4);
        add(Source::Items, Stat::AttackSpeed, 1, 10, Bucket::WeaponLocal);
        add(Source::Passives, Stat::AttackSpeed, 1, 15);
        add(Source::Gems, Stat::XPBonus, 1, 50);
        add(Source::Items, Stat::XPBonus, 1, 100, Bucket::FlatXP);
        add(Source::Items, Stat::MagicFind, 1, 400);
        add(Source::Items, Stat::GoldFind, 1, 400);
        add(Source::Passives, Stat::MaxFury, 1, 20);
        auto s = Calculate(seventy, state.contributions);
        Near(s[Stat::Strength], 380.4); Near(s[Stat::Armor], (380.4 + 77 + 100) * 1.25);
        Near(s.maxLife, 18770); Near(s[Stat::CooldownReduction], 28); Near(s[Stat::ResourceCostReduction], 28);
        Near(s[Stat::MovementSpeed], 50); Near(s[Stat::SpecificReduction], 75);
        Near(s.resistance[Index(Element::Fire)], 17.7); Near(s.resistance[Index(Element::Cold)], 7.7);
        Near(s.elementalDamage[Index(Element::Fire)], 20); Near(s.elementalDamage[Index(Element::Cold)], 0);
        Near(s.attacksPerSecond, 1.4 * 1.10 * 1.15); Near(s[Stat::XPBonus], 5); Near(s.flatXP, 100);
        Near(s[Stat::MagicFind], 300); Near(s[Stat::GoldFind], 300); Near(s[Stat::MaxFury], 120);
        Near(s.damageTaken[0], (1 - s.armorDR) * (1 - s.resistanceDR[0]) * 0.7 * 0.25);
        auto restored = DeserializeContributions(Serialize(state.contributions));
        Check(Serialize(Calculate(seventy, restored)) == Serialize(s), "Contributions did not survive relog serialization");
        // Prior saves end their stat array before the two appended gem inputs.
        std::istringstream serialized(Serialize(s));
        std::vector<std::string> tokens;std::string token;
        while(serialized>>token)tokens.push_back(token);
        tokens[0]="1";
        // Versions 5 and 6 appended the offhand's own attacks per second and
        // its own weapon IAS after flatXP; a version-1 save has neither those
        // nor the two gem inputs, so the forged string drops both appended
        // scalars and then the appended stats.
        tokens.erase(tokens.begin()+8,tokens.begin()+10);
        tokens.erase(tokens.begin()+8+Index(Stat::EliteDamage),tokens.begin()+8+StatCount);
        // Version 7 appended the element reductions after the four element arrays.
        tokens.resize(tokens.size()-ElementCount);
        std::ostringstream legacy;for(auto const& t:tokens)legacy<<t<<' ';
        auto oldSheet=DeserializeSheet(legacy.str());
        Check(Serialize(oldSheet)==Serialize(s),"Version-1 sheet lost values on upgrade");
        Near(oldSheet[Stat::EliteDamage],0);Near(oldSheet[Stat::WeaponFlatDamage],0);
        auto gemSheet=s;gemSheet.values[Index(Stat::EliteDamage)]=20;gemSheet.values[Index(Stat::WeaponFlatDamage)]=270;
        Check(Serialize(DeserializeSheet(Serialize(gemSheet)))==Serialize(gemSheet),"Gem inputs did not persist");
        // Flat weapon damage is a minimum and a delta; a version-8 save ends its stat array before the delta.
        {
            auto flat=s;flat.values[Index(Stat::WeaponFlatDamage)]=88;flat.values[Index(Stat::WeaponFlatDamageDelta)]=80;
            auto kept=DeserializeSheet(Serialize(flat));
            Near(kept[Stat::WeaponFlatDamage],88);Near(kept[Stat::WeaponFlatDamageDelta],80);
            std::istringstream saved(Serialize(flat));std::vector<std::string> parts;std::string part;
            while(saved>>part)parts.push_back(part);
            // Version 10 appended the class-resource and monster-type affixes after the delta: a version-9 save ends its
            // stat array before them, a version-8 save before the delta too.
            auto v9parts=parts;
            v9parts[0]="9";v9parts.erase(v9parts.begin()+10+Index(Stat::ResourceOnCrit),v9parts.begin()+10+StatCount);
            std::ostringstream v9;for(auto const& t:v9parts)v9<<t<<' ';
            auto fromV9=DeserializeSheet(v9.str());
            Near(fromV9[Stat::WeaponFlatDamageDelta],80);Near(fromV9[Stat::ResourceOnCrit],0);Near(fromV9[Stat::DamageVsHuman],0);
            parts[0]="8";parts.erase(parts.begin()+10+Index(Stat::WeaponFlatDamageDelta),parts.begin()+10+StatCount);
            std::ostringstream v8;for(auto const& t:parts)v8<<t<<' ';
            auto upgraded=DeserializeSheet(v8.str());
            Near(upgraded[Stat::WeaponFlatDamage],88);Near(upgraded[Stat::WeaponFlatDamageDelta],0);
            Near(upgraded[Stat::EliteReduction],flat[Stat::EliteReduction]);
            // The stats a version-10 save carries come back as saved.
            auto affixes=s;affixes.values[Index(Stat::ResourceOnCrit)]=3;affixes.values[Index(Stat::DamageVsHuman)]=20;
            auto kept10=DeserializeSheet(Serialize(affixes));
            Near(kept10[Stat::ResourceOnCrit],3);Near(kept10[Stat::DamageVsHuman],20);
            // Version 11 appended the Shaman's Maelstrom generation lines: a version-10 save ends its stat array before them.
            auto maelstrom=s;maelstrom.values[Index(Stat::MaelstromGeneration)]=7;maelstrom.values[Index(Stat::PrimaryMaelstrom)]=2;
            auto kept11=DeserializeSheet(Serialize(maelstrom));
            Near(kept11[Stat::MaelstromGeneration],7);Near(kept11[Stat::PrimaryMaelstrom],2);
            std::istringstream saved11(Serialize(maelstrom));std::vector<std::string> parts11;std::string part11;
            while(saved11>>part11)parts11.push_back(part11);
            parts11[0]="10";parts11.erase(parts11.begin()+10+Index(Stat::MaelstromGeneration),parts11.begin()+10+StatCount);
            std::ostringstream v10;for(auto const& t:parts11)v10<<t<<' ';
            auto fromV10=DeserializeSheet(v10.str());
            Near(fromV10[Stat::DamageVsHuman],maelstrom[Stat::DamageVsHuman]);Near(fromV10[Stat::MaelstromGeneration],0);Near(fromV10[Stat::PrimaryMaelstrom],0);
            // Version 12 appended the second resource's gear maximum: a version-11 save ends its stat array before it.
            auto second=s;second.values[Index(Stat::MaxSecond)]=9;second.values[Index(Stat::PrimaryMaelstrom)]=2;
            Near(DeserializeSheet(Serialize(second))[Stat::MaxSecond],9);
            std::istringstream saved12(Serialize(second));std::vector<std::string> parts12;std::string part12;
            while(saved12>>part12)parts12.push_back(part12);
            parts12[0]="11";parts12.erase(parts12.begin()+10+Index(Stat::MaxSecond),parts12.begin()+10+StatCount);
            std::ostringstream v11;for(auto const& t:parts12)v11<<t<<' ';
            auto fromV11=DeserializeSheet(v11.str());
            Near(fromV11[Stat::PrimaryMaelstrom],2);Near(fromV11[Stat::MaxSecond],0);
        }
        // Block (docs/research/block.md). One legendary shield: base chance 10-20
        // clamped to the base cap, +11% on top, a Block Amount range stored as a
        // minimum plus a delta, and a %-Block Amount affix scaling both ends.
        {
            std::vector<Contribution> shield;
            auto put = [&](Stat stat, std::uint64_t id, double value, Bucket bucket = Bucket::Flat)
            { shield.push_back({Source::Items, stat, id, value, bucket, Element::Physical}); };
            put(Stat::BaseBlockChance, 1, 17);
            put(Stat::BlockChance, 2, 11);
            put(Stat::BlockAmountMin, 3, 18000);
            put(Stat::BlockAmountMax, 4, 23000); // the reference's delta, not the max
            auto blocked = Calculate(seventy, shield);
            Near(blocked[Stat::BlockChance], 28);
            Near(blocked[Stat::BlockAmountMin], 18000);
            Near(blocked[Stat::BlockAmountMax], 41000);
            // Both caps are tunables, so a tuned pair has to move the answer.
            Near(Calculate(seventy, shield, {12, 100, 1})[Stat::BlockChance], 23);
            Near(Calculate(seventy, shield, {75, 20, 1})[Stat::BlockChance], 20);
            put(Stat::BlockAmountMin, 5, 50, Bucket::Percent);
            put(Stat::BlockAmountMax, 6, 50, Bucket::Percent);
            Near(Calculate(seventy, shield)[Stat::BlockAmountMax], 61500);
            // ...and turning the %-amount model off leaves the flat range alone.
            Near(Calculate(seventy, shield, {75, 100, 0})[Stat::BlockAmountMax], 41000);
            Check(Serialize(DeserializeSheet(Serialize(blocked))) == Serialize(blocked),
                  "Block stats did not survive persistence");
        }
        {
            // Derived: the combat module measures what the player's
            // SPELLMOD_COST auras charge and the sheet shows that instead of
            // the product of its own Resource Cost Reduction contributions,
            // which a whole-percent aura cannot match (decisions.md,
            // 2026-09-20). Gear 33.4 is paid as 33, and the sheet says 33.
            CharacterStats paying;
            SetContribution(paying, {Source::Items, Stat::ResourceCostReduction, 1, 33.4});
            Near(Calculate(seventy, paying.contributions)[Stat::ResourceCostReduction], 33.4);
            SetContribution(paying, {Source::Temporary, Stat::ResourceCostReduction, 2, 33,
                                     Bucket::Derived});
            Near(Calculate(seventy, paying.contributions)[Stat::ResourceCostReduction], 33);
            // Step 6 gives Cooldown Reduction the same treatment, for the
            // same reason: the cooldown is the core's now and the gear
            // reduction is a whole-percent SPELLMOD_COOLDOWN aura.
            CharacterStats waiting;
            SetContribution(waiting, {Source::Items, Stat::CooldownReduction, 1, 33.4});
            Near(Calculate(seventy, waiting.contributions)[Stat::CooldownReduction], 33.4);
            SetContribution(waiting, {Source::Temporary, Stat::CooldownReduction, 2, 33,
                                      Bucket::Derived});
            Near(Calculate(seventy, waiting.contributions)[Stat::CooldownReduction], 33);
            // the two are measured apart: one derived number does not become
            // the other's
            CharacterStats both;
            SetContribution(both, {Source::Items, Stat::ResourceCostReduction, 1, 20});
            SetContribution(both, {Source::Items, Stat::CooldownReduction, 1, 40});
            SetContribution(both, {Source::Temporary, Stat::ResourceCostReduction, 2, 17,
                                   Bucket::Derived});
            SetContribution(both, {Source::Temporary, Stat::CooldownReduction, 2, 38,
                                   Bucket::Derived});
            auto measured = Calculate(seventy, both.contributions);
            Near(measured[Stat::ResourceCostReduction], 17);
            Near(measured[Stat::CooldownReduction], 38);
            // and it is only for those two stats
            Reject([&] { Validate({Source::Temporary, Stat::AttackSpeed, 2, 33,
                                   Bucket::Derived}); });
            Reject([&] { Validate({Source::Temporary, Stat::SpecificReduction, 2, 33,
                                   Bucket::Derived}); });
        }
        {
            // A speed per hand: D3 runs its weapon calculation once for each
            // (stats_full.js:673-675), and the Whirlwind channel swings them
            // alternately. The offhand shares the sheet's IAS - the
            // dual-wield 15 % is inside it - and is zero with nothing in that
            // hand. Version 5 of a saved sheet carries it.
            CharacterStats hands;
            SetContribution(hands, {Source::Items, Stat::WeaponAPS, 1, 1.0});
            SetContribution(hands, {Source::Items, Stat::OffhandWeaponAPS, 1, 1.25});
            SetContribution(hands, {Source::Items, Stat::AttackSpeed, 1, 12});
            auto twoHanded = Calculate(seventy, hands.contributions);
            Near(twoHanded.attacksPerSecond, 1.0 * 1.12);
            Near(twoHanded.offhandAttacksPerSecond, 1.25 * 1.12);
            Check(Serialize(DeserializeSheet(Serialize(twoHanded))) == Serialize(twoHanded),
                  "The offhand speed did not survive persistence");

            // A weapon's own attack-speed affix belongs to its own hand
            // (stats_full.js:331 reads it off that weapon), so an offhand
            // affix must leave the main hand alone and the other way about.
            SetContribution(hands, {Source::Items, Stat::OffhandWeaponIAS, 2, 40, Bucket::WeaponLocal});
            auto handed = Calculate(seventy, hands.contributions);
            Near(handed.attacksPerSecond, twoHanded.attacksPerSecond);
            Near(handed.offhandAttacksPerSecond, 1.25 * 1.40 * 1.12);
            SetContribution(hands, {Source::Items, Stat::AttackSpeed, 3, 25, Bucket::WeaponLocal});
            auto both = Calculate(seventy, hands.contributions);
            Near(both.attacksPerSecond, 1.0 * 1.25 * 1.12);
            Near(both.offhandAttacksPerSecond, handed.offhandAttacksPerSecond);
            Check(Serialize(DeserializeSheet(Serialize(both))) == Serialize(both),
                  "The per-hand weapon IAS did not survive persistence");
            // the weapon leaves that hand: its affix leaves with it
            RemoveContribution(hands, Source::Items, Stat::OffhandWeaponIAS, 2);
            Near(Calculate(seventy, hands.contributions).offhandAttacksPerSecond, 1.25 * 1.12);
            Near(Calculate(seventy, hands.contributions).attacksPerSecond, both.attacksPerSecond);
            // and moving it to the other hand moves the affix, not a copy
            SetContribution(hands, {Source::Items, Stat::OffhandWeaponIAS, 3, 25, Bucket::WeaponLocal});
            RemoveContribution(hands, Source::Items, Stat::AttackSpeed, 3);
            auto swapped = Calculate(seventy, hands.contributions);
            Near(swapped.attacksPerSecond, 1.0 * 1.12);
            Near(swapped.offhandAttacksPerSecond, 1.25 * 1.25 * 1.12);
            RemoveContribution(hands, Source::Items, Stat::OffhandWeaponIAS, 3);
            RemoveContribution(hands, Source::Items, Stat::OffhandWeaponAPS, 1);
            Near(Calculate(seventy, hands.contributions).offhandAttacksPerSecond, 0);
            Reject([&] { Validate({Source::Items, Stat::CritChance, 1, 5, Bucket::WeaponLocal}); });
        }
        RemoveContribution(state, Source::Items, Stat::Strength, 1);
        Near(Calculate(seventy, state.contributions)[Stat::Strength], 217 * 1.2);
        Reject([&] { add(Source::Base, Stat::Strength, 1, 5); });
        Reject([&] { add(Source::Items, Stat::CooldownReduction, 3, 101); });
        Reject([&] { add(Source::Items, Stat::Strength, 9, std::numeric_limits<double>::infinity()); });
        Reject([&] { add(Source::Items, Stat::Strength, 9, 5, Bucket::WeaponLocal); });
        Reject([&] { DeserializeSheet("1 70 broken"); });
        Reject([&] { DeserializeContributions("1 1 1 0 1 5 0 0 garbage"); });
        add(Source::Items, Stat::Vitality, 99, 1e12);
        Reject([&] { Calculate(seventy, state.contributions); });
        {
            // Issue #54: the sheet's Movement Speed reaching the player.
            //
            // The sheet half first, through the real engine: the capped gear
            // and paragon share is clamped to movement_cap_pct (25) and the
            // skill bonuses are uncapped, and it is the TOTAL that is published
            // as one aura - the core keeps the largest MOD_INCREASE_SPEED and
            // not the sum, so one aura is the whole of it.
            CharacterStats movement;
            auto give = [&](Source source, unsigned id, double value, Bucket bucket)
            { SetContribution(movement, {source, Stat::MovementSpeed, id, value, bucket}); };
            give(Source::Items, 1, 12, Bucket::Flat);
            give(Source::Paragon, 2, 20, Bucket::Flat);      // 32 asked, 25 is the cap
            Near(Calculate(seventy, movement.contributions)[Stat::MovementSpeed], 25);
            Check(Stats::MovementAuraAmount(Calculate(seventy, movement.contributions)[Stat::MovementSpeed]) == 25,
                  "the capped share is not what is published");
            give(Source::Temporary, 3, 30, Bucket::Uncapped);  // Sprint, on top of the cap
            Near(Calculate(seventy, movement.contributions)[Stat::MovementSpeed], 55);
            Check(Stats::MovementAuraAmount(Calculate(seventy, movement.contributions)[Stat::MovementSpeed]) == 55,
                  "a skill bonus does not reach the aura");
            // A character with nothing asks for no aura at all.
            Check(Stats::MovementAuraAmount(Calculate(seventy, {})[Stat::MovementSpeed]) == 0, "an empty sheet casts an aura");
            Check(Stats::MovementAuraAmount(-5) == 0, "a negative sheet reached an increase aura");
            // The rounding, both ways, and the worst case it can be out by.
            Check(Stats::MovementAuraAmount(24.4) == 24, "24.4% did not round down");
            Check(Stats::MovementAuraAmount(24.5) == 25, "24.5% did not round up");
            Check(Stats::MovementAuraAmount(0.4) == 0, "under half a percent asked for an aura");
            // And the slows the affixes cast beside it: a rate of normal speed
            // as a percentage change, so the core can combine the two.
            Check(Stats::SlowAuraAmount(0.4) == -60, "a 0.4 rate is not -60%");
            Check(Stats::SlowAuraAmount(0.75) == -25, "a 0.75 rate is not -25%");
            Check(Stats::SlowAuraAmount(1.0) == 0, "an unchanged rate cast a slow");
            Check(Stats::SlowAuraAmount(1.5) == 0, "a speed-up was cast as a slow");
            Check(Stats::SlowAuraAmount(0.994) == -1, "0.994 did not round to -1%");
            Check(Stats::SlowAuraAmount(0.996) == 0, "0.996 did not round to nothing");
        }
        std::cout << "PASS: 70 CSV levels, level-70 targets, contribution buckets, caps, block, persistence, invalid inputs, and #54 movement publishing\n";
        std::cout << "#54 worst-case rounding: an aura amount is whole percent, so the published Movement Speed "
                     "is at most 0.5% away from the sheet's, and an affix slow at most 0.5% away from its tuned "
                     "rate. Nothing else rounds: the sheet's own cap is applied before either.\n";
    }
    catch (std::exception const& error) { std::cerr << error.what() << '\n'; return 1; }
}
