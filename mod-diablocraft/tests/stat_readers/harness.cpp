// diablocraft-1t1yx: the readers of the class-resource and monster-type affix stats. The real src/stats/dc_stat_readers.h,
// src/stats/dc_resource_pulse.h (RateFor over the generated resource rows) and src/common/dc_common.cpp (Calculate, the
// sheet save), no core. scripts/tests/combat/test_stat_readers.py builds and runs it; any failed check exits 1.
#include "common/dc_common.h"
#include "common/dc_numeric_data.h"
#include "stats/dc_resource_pulse.h"
#include "stats/dc_stat_readers.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <sstream>
#include <string>
#include <vector>

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
    unsigned MaximumLevel() { return 70; }
    double BaseFury(unsigned) { return 100; }
    BlockTuning Block() { return {75, 100, 1}; }
} // namespace DC::NumericData

using namespace DC;
namespace R = DC::Stats::Readers;

namespace
{
    int failures = 0;
    void Check(bool ok, char const* what)
    {
        if (!ok)
        {
            std::printf("FAIL: %s\n", what);
            ++failures;
        }
    }
    bool Near(double a, double b) { return std::fabs(a - b) < 1e-9; }

    Resources::Data::Row const* RowOf(char const* key)
    {
        for (auto const& row : Resources::Data::Rows)
            if (!std::strcmp(row.key, key))
                return &row;
        return nullptr;
    }
} // namespace

int main()
{
    BaseStats base;
    base.level = 60;
    base.strength = 100;
    base.vitality = 100;
    base.baseArmor = base.strength;
    base.baseLife = 1000;
    base.lifePerVitality = 10;
    base.maxFury = 100;
    // Each stat is a flat sum over its sources, and a distinct number, so a reader that reads its neighbour is caught.
    std::vector<Contribution> gear{
        {Source::Items, Stat::ResourceOnCrit, 1, 3},  {Source::Gems, Stat::ResourceOnCrit, 2, 2},
        {Source::Items, Stat::LifePerFury, 3, 12},    {Source::Items, Stat::SpiritRegen, 4, 2.5},
        {Source::Items, Stat::ManaRegen, 5, 7},       {Source::Items, Stat::DamageVsBeast, 6, 20},
        {Source::Items, Stat::DamageVsDemon, 7, 35},  {Source::Items, Stat::DamageVsUndead, 8, 50},
        {Source::Gems, Stat::DamageVsUndead, 9, 10},  {Source::Items, Stat::DamageVsHuman, 10, 15}};
    StatSheet const sheet = Calculate(base, gear);
    StatSheet const bare = Calculate(base, {});
    Check(Near(sheet[Stat::ResourceOnCrit], 5) && Near(sheet[Stat::LifePerFury], 12) && Near(sheet[Stat::SpiritRegen], 2.5) &&
              Near(sheet[Stat::ManaRegen], 7) && Near(sheet[Stat::DamageVsBeast], 20) && Near(sheet[Stat::DamageVsDemon], 35) &&
              Near(sheet[Stat::DamageVsUndead], 60) && Near(sheet[Stat::DamageVsHuman], 15),
          "the sheet sums each stat over its sources");

    // Life per Fury Spent: N for each point spent.
    Check(Near(R::LifeForFurySpent(sheet, 30), 360), "30 Fury spent at 12 Life per Fury is 360 Life");
    Check(R::LifeForFurySpent(sheet, 0) == 0 && R::LifeForFurySpent(sheet, -5) == 0, "no Fury spent pays nothing");
    Check(R::LifeForFurySpent(bare, 30) == 0, "no Life per Fury on the sheet pays nothing");

    // Arcane Power on Critical Hit: 5 x the skill's proc coefficient, the part under a point carried.
    double carry = 0;
    Check(R::CritResource(sheet, 0.4, carry) == 2 && Near(carry, 0), "5 x 0.4 coefficient pays 2");
    carry = 0;
    Check(R::CritResource(sheet, 0.5, carry) == 2 && Near(carry, 0.5), "5 x 0.5 pays 2 and carries 0.5");
    Check(R::CritResource(sheet, 0.5, carry) == 3 && Near(carry, 0), "the carried half joins the next crit: 3");
    carry = 0;
    unsigned paid = 0;
    for (int i = 0; i < 8; ++i)
        paid += R::CritResource(sheet, 0.25, carry); // 1.25 a crit: 8 crits pay 10 whole
    Check(paid == 10 && Near(carry, 0), "eight crits at 1.25 each pay ten, none lost to the rounding");
    carry = 0.75;
    Check(R::CritResource(bare, 1.0, carry) == 0 && carry == 0.75, "no Arcane Power on Critical Hit pays nothing and leaves the carry");
    StatSheet negative = bare;
    negative.values[Index(Stat::ResourceOnCrit)] = -3;
    carry = 0;
    Check(R::CritResource(negative, 1.0, carry) == 0 && carry == 0, "a negative sheet value pays nothing");
    carry = 0;
    Check(R::CritResource(sheet, std::nullopt, carry) == 0 && carry == 0, "a skill with no stated coefficient pays nothing");
    Check(R::CritResource(sheet, 0.0, carry) == 0 && carry == 0, "a zero coefficient pays nothing");

    // Damage to a creature type: the step 6 factor, each kind from its own stat.
    Check(Near(R::MonsterTypeFactor(sheet, R::MonsterKind::Beast), 1.2), "Beasts take +20%");
    Check(Near(R::MonsterTypeFactor(sheet, R::MonsterKind::Demon), 1.35), "Demons take +35%");
    Check(Near(R::MonsterTypeFactor(sheet, R::MonsterKind::Undead), 1.6), "Undead take +60% (two sources add)");
    Check(Near(R::MonsterTypeFactor(sheet, R::MonsterKind::Human), 1.15), "Humans take +15%");
    Check(Near(R::MonsterTypeFactor(sheet, R::MonsterKind::Other), 1.0), "any other creature takes none");
    Check(Near(R::MonsterTypeFactor(bare, R::MonsterKind::Beast), 1.0), "a bare sheet changes nothing");

    // Resource regeneration: the points a second go to the resource they name, through the pulse's rate.
    Resources::Data::Row const* spirit = RowOf("spirit");
    Resources::Data::Row const* fury = RowOf("fury");
    Resources::Data::Row const* arcane = RowOf("arcane_power");
    Check(spirit && fury && arcane, "the resource rows are there");
    if (spirit && fury && arcane)
    {
        Check(Near(R::RegenPerSecond(sheet, "spirit"), 2.5) && Near(R::RegenPerSecond(sheet, "mana"), 7),
              "Spirit reads SpiritRegen and Mana reads ManaRegen");
        Check(R::RegenPerSecond(sheet, "fury") == 0 && R::RegenPerSecond(sheet, "arcane_power") == 0 &&
                  R::RegenPerSecond(sheet, "hatred") == 0 && R::RegenPerSecond(sheet, "") == 0,
              "a resource no affix regenerates gets none");
        Check(R::RegenPerSecond(bare, "spirit") == 0, "a bare sheet adds none");
        Stats::Pulse::Inputs in;
        in.row = spirit;
        double const own = Stats::Pulse::RateFor(in).regenPerSecond;
        in.sheetPerSecond = R::RegenPerSecond(sheet, spirit->key);
        double const with = Stats::Pulse::RateFor(in).regenPerSecond;
        Check(Near(with - own, 2.5 * spirit->scale), "the pulse pays 2.5 Spirit a second, scaled to the slot's units");
        // Every live row is one unit a point, so a row at ten a point shows the sheet's share is scaled with the rate.
        Resources::Data::Row tens = *spirit;
        tens.scale = 10;
        in.row = &tens;
        Check(Near(Stats::Pulse::RateFor(in).regenPerSecond, (tens.regenPerSecond + 2.5) * 10),
              "at ten units a point the sheet's 2.5 a second is 25 units");
        // The Witch Doctor's Mana has no row yet (the class is not built): a stub row of the same shape shows the reader
        // would pay it the moment the row exists.
        Resources::Data::Row stubMana = *spirit;
        stubMana.key = "mana";
        stubMana.regenPerSecond = 50;
        stubMana.scale = 1;
        in.row = &stubMana;
        in.sheetPerSecond = R::RegenPerSecond(sheet, stubMana.key);
        Check(Near(Stats::Pulse::RateFor(in).regenPerSecond, 57), "a Mana row regenerating 50 gains 7 from ManaRegen");
        in.row = fury;
        in.sheetPerSecond = R::RegenPerSecond(sheet, fury->key);
        Check(Near(Stats::Pulse::RateFor(in).regenPerSecond, fury->regenPerSecond * fury->scale), "Fury's rate does not move");
    }

    // The sheet save keeps all eight.
    std::string const saved = Serialize(sheet);
    StatSheet const back = DeserializeSheet(saved);
    Check(Serialize(back) == saved && Near(back[Stat::ResourceOnCrit], 5) && Near(back[Stat::LifePerFury], 12) &&
              Near(back[Stat::SpiritRegen], 2.5) && Near(back[Stat::ManaRegen], 7) && Near(back[Stat::DamageVsBeast], 20) &&
              Near(back[Stat::DamageVsDemon], 35) && Near(back[Stat::DamageVsUndead], 60) && Near(back[Stat::DamageVsHuman], 15),
          "the eight stats survive a save");

    if (failures)
        return 1;
    std::printf("PASS\n");
    return 0;
}
