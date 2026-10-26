// Drives Hack's rules (diablocraft-fhpm9, N-THDEAL) of src/combat/dc_item_power_math.h with the rows the generator
// emitted: which hit fires the row (ItemPower::Fire) and the share of the Thorns damage it applies (ThornsShare).
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> wears <owner> | rolled <owner> <skill> <stat> <value> | clear hit <skill>
//   <scale> <thorns> -> for each effect row a hit of `skill` (proc coefficient `scale`) fires: "<stat>=<Thorns damage
//   applied>;" share <thorns> <pct>         -> ThornsShare on its own
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
        else if (c[0] == "rolled")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "hit")
        {
            double const thorns = std::stod(c[3]);
            std::string out;
            char text[96];
            for (ItemPower::Fired const& f :
                 ItemPower::Fire(rows, {}, sit, "hit", c[1], std::stod(c[2]), [](double) { return false; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(),
                              f.stat == "thorns_on_attack_pct" ? ItemPower::ThornsShare(thorns, f.value) : f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "share")
            std::printf("%g\n", ItemPower::ThornsShare(std::stod(c[1]), std::stod(c[2])));
    }
    return 0;
}
