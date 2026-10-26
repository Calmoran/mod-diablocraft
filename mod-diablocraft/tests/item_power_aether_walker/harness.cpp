// Drives Aether Walker's rules (diablocraft-iv3xg, N-CD and N-COST) of src/combat/dc_item_power_math.h and dc_cost_math.h with the rows the generator emitted: the
// multiplier on Teleport's cooldown (ItemPower::CooldownFactor), the points of cost the worn rows put on a skill (ItemPower::SkillSum of `cost_add_resource`) and the
// whole units of the class resource the flat aura carries (CostMath::FlatAmount over the registry's scale). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear
//   cooldown <skill>      -> CooldownFactor
//   added <skill>         -> the points of cost the `cost_add_resource` rows that are on add up to
//   flat <points> <scale> -> CostMath::FlatAmount
//   arcane                -> the Wizard's Arcane Power scale in the resource registry
#include "classes/dc_resource_data.h"
#include "combat/dc_cost_math.h"
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat;

static std::vector<std::string> Split(std::string const& text, char by)
{
    std::vector<std::string> cells;
    std::stringstream stream(text);
    std::string cell;
    while (std::getline(stream, cell, by))
        cells.push_back(cell);
    return cells;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<ItemPower::Row> rows;
    std::map<std::string, unsigned> const none;
    ItemPower::Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            ItemPower::Row row{c[1],
                               static_cast<unsigned>(std::stoul(c[2])),
                               c[3],
                               c[4],
                               c[5],
                               std::stod(c[6]),
                               std::stod(c[7]),
                               c[8],
                               std::stod(c[9]),
                               Split(c[10], ';'),
                               std::stod(c[11]),
                               static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = Split(c[14], ';');
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = 0;
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "cooldown")
            std::printf("%.10g\n", ItemPower::CooldownFactor(rows, none, c.size() > 1 ? c[1] : "", sit));
        else if (c[0] == "added")
            std::printf("%.10g\n", ItemPower::SkillSum(rows, none, c.size() > 1 ? c[1] : "", "cost_add_resource", sit));
        else if (c[0] == "flat")
            std::printf("%d\n", CostMath::FlatAmount(std::stod(c[1]), std::stod(c[2])));
        else if (c[0] == "arcane")
            std::printf("%.10g\n", DC::Resources::Data::Find("Wizard", "arcane_power")->scale);
    }
    return 0;
}
