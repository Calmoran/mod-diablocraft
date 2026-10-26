// Drives the Vitality-to-Thorns rule of dc_item_power_math.h (ThornsOfVitality through PlayerSum, Heart of Iron) with the rows the generator emitted. Input, tab separated,
// one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | stored <owner> <stat> <value> | clear
//   thorns <vitality> -> ThornsOfVitality over the rows and the worn items
//   best <row index> -> Best (the number a Primal Ancient stores)
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
            sit.wornSince[c[1]] = 0;
        else if (c[0] == "stored")
            sit.itemValues[c[1]].push_back({"", c[2], std::stod(c[3]), c[1]});
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "thorns")
            std::printf("%.10g\n", ThornsOfVitality(rows, none, std::stod(c[1]), sit));
        else if (c[0] == "best")
            std::printf("%.10g\n", std::stoul(c[1]) < rows.size() ? Best(rows[std::stoul(c[1])]) : -1.0);
    }
    return 0;
}
