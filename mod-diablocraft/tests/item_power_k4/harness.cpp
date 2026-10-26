// Drives the K4 rules of src/combat/dc_item_power_math.h (GrantsRune, SkillLowest, SkillSetTo, SkillFactor, Fire of the `hit` event and its
// `apply_skill` effect, Ticks and the bleed stacks) with the rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | wears <owner> <since> | value <owner> <skill> <stat> <v> | channel <skill> <start> <end> <running 0|1> | clear
//   rune <skill> <rune> <n> (<set> <worn>)xn            -> 1 when the rune is given, else 0
//   lowest <skill> <stat> <base> <n> (<set> <worn>)xn   -> SkillLowest;  setto <skill> <stat> <base> <n> ... -> SkillSetTo;  factor <skill> <stat> <n> ...
//   fire <event> <skill> <scale> <draw> <n> (<set> <worn>)xn -> "stat(skill)=value;..." of the effect rows that fired
//   ticks <seconds>                                      -> Ticks
//   stacks clear | stacks add <total> <base> <length> <pay> <start> <cap> | stacks tick <n> | stacks end | stacks count | stacks starts
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

static std::map<std::string, unsigned> Counts(std::vector<std::string> const& c, std::size_t at)
{
    std::map<std::string, unsigned> counts;
    for (std::size_t i = 0; i < std::stoul(c[at]); ++i)
        counts[c[at + 1 + 2 * i]] = static_cast<unsigned>(std::stoul(c[at + 2 + 2 * i]));
    return counts;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<Row> rows;
    Situation sit;
    std::vector<BleedStack> stacks;
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
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "value")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "channel")
            sit.channels[c[1]] = {static_cast<std::uint32_t>(std::stoul(c[2])), static_cast<std::uint32_t>(std::stoul(c[3])), c[4] == "1"};
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "rune")
            std::printf("%d\n", GrantsRune(rows, Counts(c, 3), c[1], c[2], sit) ? 1 : 0);
        else if (c[0] == "lowest")
            std::printf("%g\n", SkillLowest(rows, Counts(c, 4), c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "setto")
            std::printf("%g\n", SkillSetTo(rows, Counts(c, 4), c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "factor")
            std::printf("%g\n", SkillFactor(rows, Counts(c, 3), c[1], c[2], sit));
        else if (c[0] == "fire")
        {
            double const draw = std::stod(c[4]);
            std::string out;
            char text[128];
            for (Fired const& f : Fire(rows, Counts(c, 5), sit, c[1], c[2], std::stod(c[3]), [&](double pct) { return draw < pct; }))
            {
                std::snprintf(text, sizeof text, "%s(%s)=%g;", f.stat.c_str(), f.skill.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "ticks")
            std::printf("%u\n", Ticks(std::stod(c[1])));
        else if (c[0] == "stacks")
        {
            if (c[1] == "clear")
                stacks.clear();
            else if (c[1] == "add")
                AddStack(stacks,
                         {std::stod(c[2]), static_cast<unsigned>(std::stoul(c[3])), static_cast<unsigned>(std::stoul(c[4])),
                          static_cast<unsigned>(std::stoul(c[5])), static_cast<unsigned>(std::stoul(c[6]))},
                         static_cast<unsigned>(std::stoul(c[7])));
            else if (c[1] == "tick")
                std::printf("%g\n", BleedDamage(stacks, static_cast<unsigned>(std::stoul(c[2]))));
            else if (c[1] == "end")
                std::printf("%u\n", BleedEnd(stacks));
            else if (c[1] == "count")
                std::printf("%zu\n", stacks.size());
            else if (c[1] == "starts")
            {
                std::string out;
                for (BleedStack const& s : stacks)
                    out += std::to_string(s.start) + ";";
                std::printf("%s\n", out.c_str());
            }
        }
    }
    return 0;
}
