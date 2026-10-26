// Drives Harrington Waistguard's rules (diablocraft-ikpbp, N-CHEST) of src/combat/dc_item_power_math.h with the rows
// the generator emitted: the `chest` event (ItemPower::Fire) that starts the row's `triggered` window and the damage
// multiplier the window gives (PlayerFactor). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> now <ms> | wears <owner> | rolled <owner> <skill> <stat> <value> | clear
//   event <name>   -> ItemPower::Fire for that event (skill blank): "<n> fired" where n is the number of rows that
//   fired dealt          -> PlayerFactor(damage_dealt_pct) now
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
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = 0;
        else if (c[0] == "rolled")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "event")
            ItemPower::Fire(rows, none, sit, c[1], "", 1.0, [](double) { return true; });
        else if (c[0] == "dealt")
            std::printf("%.10g\n", ItemPower::PlayerFactor(rows, none, "damage_dealt_pct", sit));
    }
    return 0;
}
