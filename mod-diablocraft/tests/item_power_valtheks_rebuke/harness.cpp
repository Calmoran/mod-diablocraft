// Drives Valthek's Rebuke (diablocraft-057cl): the `straight_path` row through dc_item_power_math.h's SkillSetTo (base 0), which turns Energy Twister's
// turn limit to 0 in EnergyTwister::Start, then dc_twister_math.h's Path with that limit; and the `damage_increase_pct` row through SkillFactor (the
// hit's legendary term). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | value <owner> <skill> <stat> <roll> | clear
//   factor <skill> <stat>   -> SkillFactor
//   path <turnLimit> <speed> <life> <turnSeconds> <rolls,..>   -> the waypoints "x y x y .." of Start's path from (0,0) heading 0, the turn limit
//                              being 0 while a `straight_path` source is worn and <turnLimit> (the tunable) otherwise, as Start composes it
#include "combat/dc_item_power_math.h"
#include "wizard/dc_twister_math.h"

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
            ItemPower::Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]), c[8], std::stod(c[9]),
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
            sit = ItemPower::Situation{};
        else if (c[0] == "factor")
            std::printf("%.10g\n", ItemPower::SkillFactor(rows, none, c[1], c[2], sit));
        else if (c[0] == "path")
        {
            // EnergyTwister::Start: straight when a `straight_path` source is worn, else the tunable's limit
            bool const straight = ItemPower::SkillSetTo(rows, none, "Energy Twister", "straight_path", 0, sit) > 0;
            double const limit = straight ? 0 : std::stod(c[1]);
            std::vector<double> rolls;
            if (c.size() > 5 && !c[5].empty())
                for (std::string const& r : Split(c[5], ','))
                    rolls.push_back(std::stod(r));
            auto path = Wizard::Twister::Path({0, 0}, 0.0, std::stod(c[2]), std::stod(c[3]), std::stod(c[4]), limit, rolls);
            std::string out;
            for (auto const& p : path)
            {
                char buf[64];
                std::snprintf(buf, sizeof buf, "%.4f %.4f ", p.x, p.y);
                out += buf;
            }
            std::printf("%s\n", out.c_str());
        }
    }
    return 0;
}
