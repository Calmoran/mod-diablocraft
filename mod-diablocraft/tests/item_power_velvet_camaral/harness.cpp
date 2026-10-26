// Drives Velvet Camaral's jump count (diablocraft-9l8ka): the `jump_count_factor` rule of dc_item_power_math.h (SkillSetTo) with the rows the generator
// emitted, times Electrocute's own jumps (dc_wizard_chain.h JumpCount), walked over a line of enemies (Walk), as Wizard::Jumps composes them. Input, tab
// separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear
//   jumps <rune> <targetCount>            -> the enemies the bolt jumps to after the first
//   reach <rune> <targetCount> <enemies>  -> how many of `enemies` in a row 1 yd apart the bolt hits, the first included (jump range 15 yd)
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
    auto jumps = [&](std::string const& rune, double count)
    {
        // Wizard::Jumps: Chain::JumpCount x unsigned(ItemPowers::SkillSetTo(player, "Electrocute", "jump_count_factor", 1))
        return Wizard::Chain::JumpCount(rune, count) * unsigned(ItemPower::SkillSetTo(rows, none, "Electrocute", "jump_count_factor", 1, sit));
    };
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
        else if (c[0] == "jumps")
            std::printf("%u\n", jumps(c[1], std::stod(c[2])));
        else if (c[0] == "reach")
        {
            int const enemies = std::stoi(c[3]);
            auto near = [&](int on)
            {
                std::vector<int> out;
                for (int i = 0; i < enemies; ++i)
                    if (std::abs(i - on) <= 15)
                        out.push_back(i);
                return out;
            };
            auto distance = [](int a, int b) { return double(std::abs(a - b)); };
            std::printf("%zu\n", 1 + Wizard::Chain::Walk(0, jumps(c[1], std::stod(c[2])), false, near, distance).size());
        }
    }
    return 0;
}
