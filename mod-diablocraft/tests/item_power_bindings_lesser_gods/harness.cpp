// Drives Bindings of the Lesser Gods' rules with the rows the generator emitted: the mark's factor (MarkFactor in
// dc_item_power_math.h) and the split bonus (`mark_split_factor`, read with SkillSetTo, base 1).
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear
//   split -> the split factor with what is worn: SkillSetTo(Mystic Ally, mark_split_factor, 1)
//   mark <pct> <split> -> MarkFactor(pct, split)
//   hit <pct> <split 0|1> -> what ComputeHit gets: MarkFactor(pct, the split factor when the hit is a split one, else 1)
//   seconds <owner> -> the mark's seconds: the stack_seconds of the owner's mark_enemy row (0 with none)
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
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "split")
            std::printf("%.10g\n", SkillSetTo(rows, none, "Mystic Ally", "mark_split_factor", 1, sit));
        else if (c[0] == "mark")
            std::printf("%.10g\n", MarkFactor(std::stod(c[1]), std::stod(c[2])));
        else if (c[0] == "hit")
        {
            double const times = c[2] == "1" ? SkillSetTo(rows, none, "Mystic Ally", "mark_split_factor", 1, sit) : 1.0;
            std::printf("%.10g\n", MarkFactor(std::stod(c[1]), times));
        }
        else if (c[0] == "seconds")
        {
            double seconds = 0;
            for (Row const& row : rows)
                if (row.owner == c[1] && row.kind == "effect" && row.stat == "mark_enemy")
                    seconds = row.stackSeconds;
            std::printf("%.10g\n", seconds);
        }
    }
    return 0;
}
