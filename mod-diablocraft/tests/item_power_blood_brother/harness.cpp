// Drives the Blood Brother rules (diablocraft-jxvsn, N-BLOCK) of src/combat/dc_item_power_math.h (the `block` event that fires the row, the block chance and
// the blocked-damage cut as player stats) and src/combat/dc_item_block_math.h (the chance, the cut hit and the attack the bonus is spent on) with the rows the
// generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | clear                           -> the clock; an empty situation (no output)
//   wears <owner> [<roll>]                     -> the item put on, its ranged rows at the stored roll when given (no roll: none stored) (no output)
//   bag <owner>                                -> the item only known, not worn (no output)
//   fire <event>                               -> "stat=value;..." of the effect rows ItemPower::Fire fires
//   bonus                                      -> PlayerSum of block_chance_pct over the worn items
//   cut                                        -> CutFactor of blocked_damage_cut_pct over the worn items
//   chance <sheet> <bonus> <cap>               -> ItemBlock::Chance
//   blocked <damage> <flat> <cutFactor>        -> ItemBlock::Blocked
//   factor <armed> <spentPct> <spentSkill> <skill> -> ItemBlock::NextAttackFactor
//   connect <armed> <spentPct> <spentSkill> <skill> -> ItemBlock::Connect: "pct|skill" of what the cast carries
//   press <spentPct> <spentSkill>              -> ItemBlock::Press: "pct|skill"
//   arm <armed> <pct>                          -> ItemBlock::Arm
#include "combat/dc_item_block_math.h"
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

// An empty last cell is no cell to getline: a skill that is the empty string reads as one.
static std::string Cell(std::vector<std::string> const& cells, std::size_t at)
{
    return at < cells.size() ? cells[at] : std::string();
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
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
        {
            std::vector<ItemPower::Stored> stored;
            if (c.size() > 2)
                for (ItemPower::Row const& row : rows)
                    if (row.owner == c[1] && ItemPower::Rolls(row))
                        stored.push_back({ItemPower::RollKey(row), std::stod(c[2])});
            sit.wornSince[c[1]] = 0;
            sit.itemValues[c[1]] = ItemPower::WornValues(rows, c[1], stored);
        }
        else if (c[0] == "bag")
            sit.itemValues[c[1]] = ItemPower::WornValues(rows, c[1], {});
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "fire")
        {
            std::string out;
            char text[96];
            for (ItemPower::Fired const& f : ItemPower::Fire(rows, std::map<std::string, unsigned>{}, sit, c[1], "", 1.0, [](double) { return true; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "bonus")
            std::printf("%.10g\n", ItemPower::PlayerSum(rows, std::map<std::string, unsigned>{}, "block_chance_pct", sit));
        else if (c[0] == "cut")
            std::printf("%.10g\n", ItemPower::CutFactor(rows, std::map<std::string, unsigned>{}, "blocked_damage_cut_pct", sit));
        else if (c[0] == "chance")
            std::printf("%.10g\n", ItemBlock::Chance(std::stod(c[1]), std::stod(c[2]), std::stod(c[3])));
        else if (c[0] == "blocked")
            std::printf("%.10g\n", ItemBlock::Blocked(std::stod(c[1]), std::stod(c[2]), std::stod(c[3])));
        else if (c[0] == "factor")
            std::printf("%.10g\n", ItemBlock::NextAttackFactor(std::stod(c[1]), ItemBlock::Spent{std::stod(c[2]), Cell(c, 3)}, Cell(c, 4)));
        else if (c[0] == "connect")
        {
            ItemBlock::Spent const spent = ItemBlock::Connect(std::stod(c[1]), ItemBlock::Spent{std::stod(c[2]), Cell(c, 3)}, Cell(c, 4));
            std::printf("%.10g|%s\n", spent.pct, spent.skill.c_str());
        }
        else if (c[0] == "press")
        {
            ItemBlock::Spent const spent = ItemBlock::Press(ItemBlock::Spent{std::stod(c[1]), Cell(c, 2)});
            std::printf("%.10g|%s\n", spent.pct, spent.skill.c_str());
        }
        else if (c[0] == "arm")
            std::printf("%.10g\n", ItemBlock::Arm(std::stod(c[1]), std::stod(c[2])));
    }
    return 0;
}
