// Drives Ranslor's Folly's rules (diablocraft-5kkgd, N-LESSER) of src/combat/dc_item_power_math.h with the rows the generator emitted: which enemies are lesser
// (ItemPower::IsLesser), whether the twister's pull takes one enemy now (ItemPower::LesserPull: lesser, in reach, off the per-target clock) and the numbers the
// worn rows give the twister (ItemPower::SkillSetTo of each pull stat, the highest source). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear
//   setto <skill> <stat> <base>   -> SkillSetTo
//   lesser <monster 0|1> <elite 0|1> <boss 0|1>   -> IsLesser: 1 or 0
//   pull <lesser 0|1> <distance> <yards> <now> <pulled 0|1> <last> <cooldownSeconds>   -> LesserPull: 1 or 0
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
        else if (c[0] == "setto")
            std::printf("%.10g\n", ItemPower::SkillSetTo(rows, none, c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "lesser")
            std::printf("%d\n", ItemPower::IsLesser(c[1] == "1", c[2] == "1", c[3] == "1") ? 1 : 0);
        else if (c[0] == "pull")
            std::printf("%d\n", ItemPower::LesserPull(c[1] == "1", std::stod(c[2]), std::stod(c[3]), static_cast<std::uint32_t>(std::stoul(c[4])), c[5] == "1",
                                                      static_cast<std::uint32_t>(std::stoul(c[6])), std::stod(c[7]))
                                    ? 1
                                    : 0);
    }
    return 0;
}
