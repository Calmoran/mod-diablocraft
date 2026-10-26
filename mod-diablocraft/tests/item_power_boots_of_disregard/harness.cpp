// Drives the stood-still rules of dc_item_power_math.h (StillSince, StillStacks through Stacks / Holds / PlayerSum, Boots of Disregard) with the rows the generator
// emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> <ms> | now <ms> | still <tracked 0|1> <since ms> | clear
//   sum <stat> -> PlayerSum of the player rows of that stat     holds <row index> -> Holds
//   since <moving 0|1> <tracked 0|1> <since> <now> -> StillSince
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::ItemPower;

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
    std::vector<Row> rows;
    std::map<std::string, unsigned> const none;
    Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]), c[8], std::stod(c[9]),
                    Split(c[10], ';'), std::stod(c[11]), static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = Split(c[14], ';');
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "still")
        {
            sit.stillTracked = c[1] == "1";
            sit.stillSince = static_cast<std::uint32_t>(std::stoul(c[2]));
        }
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "sum")
            std::printf("%.10g\n", PlayerSum(rows, none, c[1], sit));
        else if (c[0] == "holds")
            std::printf("%d\n", std::stoul(c[1]) < rows.size() && Holds(rows[std::stoul(c[1])], sit) ? 1 : 0);
        else if (c[0] == "since")
            std::printf("%u\n", StillSince(c[1] == "1", c[2] == "1", static_cast<std::uint32_t>(std::stoul(c[3])), static_cast<std::uint32_t>(std::stoul(c[4]))));
    }
    return 0;
}
