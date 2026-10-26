// Drives The Butcher's Sickle's rules (diablocraft-v052u, N-PULLFX) of src/combat/dc_item_power_math.h and dc_proc_math.h with the rows the generator emitted: the
// `hit` event that fires the `pull_enemy` effect with the item's rolled chance (ItemPower::Fire), whether a drag may happen at all (DragReady: reach and cooldown) and
// whether the chance falls once the hit's proc coefficient has scaled it (Proc::Rolls). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | rolled <owner> <skill> <stat> <value> | clear | now <ms>
//   fire <event> <skill>      -> the effects that fired as "stat:number;..." or "none"
//   ready <distance> <yards> <now> <dragged 0|1> <last> <cooldownSeconds>   -> DragReady: 1 or 0
//   damage <minimum> <delta> <unit>   -> DragDamage
//   chance <chancePct> <coefficient or -> <draw>   -> Proc::Rolls: 1 when the chance (scaled by the coefficient) falls on the draw, else 0
#include "combat/dc_item_power_math.h"
#include "combat/dc_item_proc_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <optional>
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
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "fire")
        {
            auto fired = ItemPower::Fire(rows, none, sit, c[1], c.size() > 2 ? c[2] : "", 1.0, [](double) { return true; });
            std::string out;
            for (auto const& one : fired)
            {
                char number[64];
                std::snprintf(number, sizeof number, "%.10g", one.value);
                out += (out.empty() ? "" : ";") + one.stat + ":" + number;
            }
            std::printf("%s\n", out.empty() ? "none" : out.c_str());
        }
        else if (c[0] == "rolled")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "ready")
            std::printf("%d\n", ItemPower::DragReady(std::stod(c[1]), std::stod(c[2]), static_cast<std::uint32_t>(std::stoul(c[3])), c[4] == "1",
                                                      static_cast<std::uint32_t>(std::stoul(c[5])), std::stod(c[6])) ? 1 : 0);
        else if (c[0] == "damage")
            std::printf("%.10g\n", ItemPower::DragDamage(std::stod(c[1]), std::stod(c[2]), std::stod(c[3])));
        else if (c[0] == "chance")
        {
            double const draw = std::stod(c[3]);
            std::optional<double> coefficient;
            if (c[2] != "-")
                coefficient = std::stod(c[2]);
            std::printf("%d\n", Proc::Rolls(coefficient, std::stod(c[1]), [draw](float pct) { return draw < pct; }) ? 1 : 0);
        }
    }
    return 0;
}
