// Pylons and shrines P1 (diablocraft-plgq2): the buffs through the module's own sheet. Compiled with the real
// src/common/dc_common.cpp (Calculate), src/combat/dc_pylon_math.h (Settle, PowerFactor, Active) and
// src/paragon/dc_paragon_math.h (AwardXP, Enlightened); scripts/tests/rifts/test_pylon_buffs.py builds and drives it.
//   "row <name> <value>"            a tunable row, as dc_tunables would answer it
//   "wear <bits> <alive>"            the kinds whose record the player wears (bit i is Kind i) and whether they live:
//                                    Reconcile's step. Prints whether the cost/cooldown auras must be rebuilt, then
//                                    AttackSpeed CDR RCR SpecificReduction MovementSpeed MagicFind GoldFind
//   "login"                          the next wear is the first after a login (the sheet as saved, nothing known)
//   "power <worn> <alive>"           step 8's product with Power's factor from its row
//   "xp <base> <gear pct> <flat> <worn> <alive>"  SheetAward's own-kill path: AwardXP, then Enlightened from its row
#include "../../src/common/dc_common.h"
#include "../../src/common/dc_numeric_data.h"
#include "../../src/combat/dc_pylon_math.h"
#include "../../src/paragon/dc_paragon_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <string>

namespace DC::NumericData
{
    double Rule(char const* name)
    {
        static std::map<std::string, double> const rules{
            {"crit_chance_pct", 5},          {"crit_damage_pct", 50},
            {"attack_speed_cap", 5},         {"movement_cap_pct", 25},
            {"magic_find_cap_pct", 300},     {"gold_find_cap_pct", 300},
            {"xp_penalty_level", 70},        {"xp_divisor", 10},
            {"all_res_per_int", 0.1},        {"class_dr_pct", 30},
            {"armor_level_coefficient", 50}, {"resistance_level_coefficient", 5}};
        return rules.at(name);
    }
    unsigned MaximumLevel()
    {
        return 70;
    }
    double BaseFury(unsigned)
    {
        return 100;
    }
    BlockTuning Block()
    {
        return {75, 100, 1};
    }
} // namespace DC::NumericData

using namespace DC;
using namespace DC::Combat::Pylons;
using namespace DC::Paragon;

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::map<std::string, double> rows;
    auto get = [&rows](std::string const& name) { return rows.at(name); };
    auto record = [](Kind kind) { return std::uint64_t(83500 + static_cast<unsigned>(kind)); };
    CharacterStats character;
    BaseStats base;
    base.level = 60;
    base.strength = 100;
    base.vitality = 100;
    base.baseArmor = base.strength;
    base.baseLife = 1000;
    base.lifePerVitality = 10;
    base.maxFury = 100;
    unsigned before = 0;
    bool known = false;
    std::string word;
    while (in >> word)
    {
        if (word == "row")
        {
            std::string name;
            double value;
            in >> name >> value;
            rows[name] = value;
        }
        else if (word == "login")
            known = false;
        else if (word == "wear")
        {
            unsigned bits;
            int alive;
            in >> bits >> alive;
            unsigned now = 0;
            for (unsigned i = 0; i < KindCount; ++i)
                if (Active(alive != 0, (bits >> i) & 1u))
                    now |= 1u << i;
            bool const modifiers = Settle(
                known, before, now, record, get, [&character](Stat stat, std::uint64_t id)
                { RemoveContribution(character, Source::Temporary, stat, id); },
                [&character](Contribution const& c) { SetContribution(character, c); });
            before = now;
            known = true;
            StatSheet const sheet = Calculate(base, character.contributions);
            std::printf("%d %.6f %.6f %.6f %.6f %.6f %.6f %.6f\n", modifiers ? 1 : 0, sheet[Stat::AttackSpeed],
                        sheet[Stat::CooldownReduction], sheet[Stat::ResourceCostReduction],
                        sheet[Stat::SpecificReduction], sheet[Stat::MovementSpeed], sheet[Stat::MagicFind],
                        sheet[Stat::GoldFind]);
        }
        else if (word == "power")
        {
            int worn, alive;
            in >> worn >> alive;
            Combat::Factors factors;
            PowerFactor(Active(alive != 0, worn != 0), get(Row(Kind::Power, "damage_pct")), factors);
            std::printf("%.6f\n", Combat::Product(factors));
        }
        else if (word == "xp")
        {
            unsigned long long amount, flat;
            double gear;
            int worn, alive;
            in >> amount >> gear >> flat >> worn >> alive;
            XP paid = AwardXP(amount, Hundredths(gear), flat);
            if (Active(alive != 0, worn != 0))
                paid = Enlightened(paid, Hundredths(get(Row(Kind::Enlightened, "xp_pct"))));
            std::printf("%llu\n", static_cast<unsigned long long>(paid));
        }
        else
            return 3;
    }
    return 0;
}
