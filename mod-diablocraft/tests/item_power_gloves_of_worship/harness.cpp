// Drives Gloves of Worship's rule (diablocraft-4y1jn, N-PYLONDUR) of src/combat/dc_item_power_math.h with the rows the generator emitted: the seconds a shrine
// effect lasts, the shrine's own or the worn `shrine_seconds` row's when that is more (ItemPower::PlayerSetTo). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear
//   shrine <ownSeconds>   -> PlayerSetTo of "shrine_seconds" over the shrine's own seconds
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
        else if (c[0] == "shrine")
            std::printf("%.10g\n", ItemPower::PlayerSetTo(rows, none, "shrine_seconds", std::stod(c[1]), sit));
    }
    return 0;
}
