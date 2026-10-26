// Drives the first-hit, enemy-stack and skill-buff rules of dc_item_power_math.h (Fire's `first_hit_on_target`, FirstHit, MarksFirstHits, ControlSpell, EnemyPress / EnemyConnect, PerStackFactor,
// SkillFactor and StackedFactor; Madawc's Sorrow, Saffron Wrap, Fragment of Destiny) with the rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | stored <owner> <skill> <stat> <value> | clear
//   fire <event> <skill> <firstHit 0|1> <chance roll: 1 passes, 0 fails>  -> the fired stat:value list, "-" for none
//   marks -> MarksFirstHits     first <creature> <player> -> FirstHit on that creature's set     control <stat> -> ControlSpell
//   press <now> <seconds> | connect <enemies> <most> <now> | riding -> the EnemyStack: "riding carried carriedAt"     reset -> a new stack
//   perstack <skill> <stat> <stacks> -> PerStackFactor     skillfactor <skill> <stat> -> SkillFactor     stacked <owner> <stacks> <stat> <sign> <skill> -> StackedFactor
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <set>
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
    std::map<std::string, std::set<std::uint64_t>> creatures;
    Situation sit;
    EnemyStack stack;
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
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "fire")
        {
            Situation copy = sit;
            copy.firstHit = c[3] == "1";
            bool const passes = c[4] == "1";
            auto fired = Fire(rows, none, copy, c[1], c[2], 1.0, [passes](double) { return passes; });
            if (fired.empty())
                std::printf("-\n");
            else
            {
                std::string out;
                for (auto const& one : fired)
                    out += (out.empty() ? "" : ",") + one.stat + ":" + std::to_string(static_cast<int>(one.value));
                std::printf("%s\n", out.c_str());
            }
        }
        else if (c[0] == "marks")
            std::printf("%d\n", MarksFirstHits(rows, none, sit) ? 1 : 0);
        else if (c[0] == "first")
            std::printf("%d\n", FirstHit(creatures[c[1]], std::stoull(c[2])) ? 1 : 0);
        else if (c[0] == "control")
            std::printf("%u\n", ControlSpell(c[1]));
        else if (c[0] == "reset")
            stack = EnemyStack{};
        else if (c[0] == "press")
            stack = EnemyPress(stack, static_cast<std::uint32_t>(std::stoul(c[1])), std::stod(c[2]));
        else if (c[0] == "connect")
            stack = EnemyConnect(stack, static_cast<unsigned>(std::stoul(c[1])), static_cast<unsigned>(std::stoul(c[2])), static_cast<std::uint32_t>(std::stoul(c[3])));
        else if (c[0] == "riding")
            std::printf("%u %u %u\n", stack.riding, stack.carried, stack.carriedAt);
        else if (c[0] == "perstack")
            std::printf("%.10g\n", PerStackFactor(rows, none, c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "skillfactor")
            std::printf("%.10g\n", SkillFactor(rows, none, c[1], c[2], sit));
        else if (c[0] == "stacked")
            std::printf("%.10g\n", StackedFactor(rows, none, {{c[1], static_cast<unsigned>(std::stoul(c[2]))}}, c[3], std::stod(c[4]), sit, c[5]));
    }
    return 0;
}
