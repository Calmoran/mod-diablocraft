// Drives Rabid Strike's rules (diablocraft-6d1jb): the item row through dc_item_power_math.h (SkillSetTo, the reader Epiphany::Dash asks) and the
// copy's rules in classes/monk/dc_monk_epiphany.h (Mimics, MimicTarget, MimicFactor), with the rows the generator emitted. Input, tab separated,
// one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | value <owner> <skill> <stat> <roll> | clear
//   copy <cost> -> the copy's damage multiplier for a dash of a skill costing <cost> Spirit, 0 when no copy
//   pick <primary> <distance>... -> the copy's enemy (an index), -1 when none
#include "combat/dc_item_power_math.h"
#include "classes/monk/dc_monk_epiphany.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::ItemPower;
namespace E = DC::Combat::Monk::Epiphany;

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
        else if (c[0] == "value")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "copy")
        {
            double const pct = SkillSetTo(rows, none, "Epiphany", "mimic_damage_pct", 0, sit);
            std::printf("%.10g\n", E::Mimics(pct, std::stod(c[1])) ? E::MimicFactor(pct) : 0.0);
        }
        else if (c[0] == "pick")
        {
            std::vector<double> distances;
            for (std::size_t i = 2; i < c.size(); ++i)
                distances.push_back(std::stod(c[i]));
            std::printf("%d\n", E::MimicTarget(distances, std::stoi(c[1])));
        }
    }
    return 0;
}
