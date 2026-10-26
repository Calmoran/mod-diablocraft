// Drives Myken's Ball of Hate (diablocraft-3j0cg): the `jump_rehit` rule of dc_item_power_math.h (SkillSetTo, base 0) with the rows the generator
// emitted turns on Electrocute's `mayRehit` (dc_wizard_chain.h Next and Walk), with Velvet Camaral's `jump_count_factor` on the jumps, as Wizard::Jumps
// composes them. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear
//   walk <rune> <targetCount> <x,x,..>  -> the enemies the bolt hits in order (indexes into the line of positions, yards), the first (0) included;
//                                         jump range 15 yd
#include "combat/dc_item_power_math.h"
#include "wizard/dc_wizard_chain.h"

#include <cmath>
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
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "walk")
        {
            std::vector<double> at;
            for (std::string const& x : Split(c[3], ','))
                at.push_back(std::stod(x));
            // Wizard::Jumps: the jumps times the hat's factor; mayRehit while a `jump_rehit` source is worn
            unsigned const jumps = Wizard::Chain::JumpCount(c[1], std::stod(c[2])) *
                                   unsigned(ItemPower::SkillSetTo(rows, none, "Electrocute", "jump_count_factor", 1, sit));
            bool const mayRehit = ItemPower::SkillSetTo(rows, none, "Electrocute", "jump_rehit", 0, sit) > 0;
            auto near = [&](int on)
            {
                std::vector<int> out;
                for (int i = 0; i < int(at.size()); ++i)
                    if (std::abs(at[i] - at[on]) <= 15)
                        out.push_back(i);
                return out;
            };
            auto distance = [&](int a, int b) { return std::abs(at[a] - at[b]); };
            std::string out = "0";
            for (int i : Wizard::Chain::Walk(0, jumps, mayRehit, near, distance))
                out += " " + std::to_string(i);
            std::printf("%s\n", out.c_str());
        }
    }
    return 0;
}
