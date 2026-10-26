// Drives the production rules of src/combat/dc_item_power_math.h with the rows the generator emitted.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> [<cond> <arg> <skills;...> [<stackSeconds> <stackMax>]]
//   now <ms>                          -> the clock the conditions read (no output)
//   span <skill> <start> <end> <running> -> a channel span of the situation (no output)
//   hurt <ms>                         -> the player last took damage at <ms>
//   wears <owner> <since>             -> an item (d3_id) put on at <since> (the situation's wornSince)
//   value <owner> <skill> <stat> <v>  -> a worn item's stored number for a row (the situation's itemValues)
//   skillon <skill>                   -> a skill that is active now (the situation's `active`, for `skills_active`; no output)
//   clear                             -> an empty situation
//   player <stat> <n> (<set> <worn>)xn  -> the multiplier of a `player` `_pct` stat
//   count <n> (<set> <name>)xn        -> "set=worn;..." in set order
//   active <set> <pieces> <worn>      -> 0 or 1
//   range <d3Id> <stat> <poolMin> <poolMax> -> "min max" the roller uses
//   stats <d3Id>                      -> the number of stat rows the item rolls as presets
//   factor <skill> <stat> <n> (<set> <worn>)xn          -> the multiplier of a `_pct` skill stat
//   setto <skill> <stat> <base> <n> (<set> <worn>)xn    -> a `set to` skill stat
//   bleed <total> <baseTicks> <ticks>                   -> "sum min max" of the bleed's ticks
//   powers <d3Id> <top 0|1> <unit> [<stored key>...]  -> "key=value[min-max];..." the rows an item rolls once, each rolled at `unit` of its range
//   worn <skill> <stat> <n> (<d3Id> <m> (<key> <value>)xm)xn -> the values WornRolls gives for n worn items, ";" joined
#include "combat/dc_item_power_math.h"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::ItemPower;

static std::vector<std::string> Split(std::string const& line)
{
    std::vector<std::string> cells;
    std::stringstream stream(line);
    std::string cell;
    while (std::getline(stream, cell, '\t'))
        cells.push_back(cell);
    return cells;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<Row> rows;
    Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line);
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]), "", 0, {}};
            if (c.size() > 10)
            {
                row.cond = c[8];
                row.arg = std::stod(c[9]);
                std::stringstream skills(c[10]);
                std::string skill;
                while (std::getline(skills, skill, ';'))
                    row.condSkills.push_back(skill);
            }
            if (c.size() > 12)
            {
                row.stackSeconds = std::stod(c[11]);
                row.stackMax = static_cast<unsigned>(std::stoul(c[12]));
            }
            rows.push_back(row);
        }
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "span")
            sit.channels[c[1]] = {static_cast<std::uint32_t>(std::stoul(c[2])), static_cast<std::uint32_t>(std::stoul(c[3])), c[4] == "1"};
        else if (c[0] == "hurt")
        {
            sit.hurt = true;
            sit.lastHurt = static_cast<std::uint32_t>(std::stoul(c[1]));
        }
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "value")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "skillon")
            sit.active.insert(c[1]);
        else if (c[0] == "skillon")
            sit.active.insert(c[1]);
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "player")
        {
            std::map<std::string, unsigned> counts;
            for (std::size_t i = 0; i < std::stoul(c[2]); ++i)
                counts[c[3 + 2 * i]] = static_cast<unsigned>(std::stoul(c[4 + 2 * i]));
            std::printf("%g\n", PlayerFactor(rows, counts, c[1], sit));
        }
        else if (c[0] == "count")
        {
            std::vector<Piece> worn;
            for (std::size_t i = 0; i < std::stoul(c[1]); ++i)
                worn.push_back({c[2 + 2 * i], c[3 + 2 * i]});
            std::string out;
            for (auto const& [set, count] : CountSets(worn))
                out += set + "=" + std::to_string(count) + ";";
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "active")
            std::printf("%d\n", BonusActive(rows, c[1], static_cast<unsigned>(std::stoul(c[2])),
                                             static_cast<unsigned>(std::stoul(c[3]))) ? 1 : 0);
        else if (c[0] == "range")
        {
            double min = std::stod(c[3]), max = std::stod(c[4]);
            RollRange(rows, c[1], c[2], min, max);
            std::printf("%g %g\n", min, max);
        }
        else if (c[0] == "stats")
            std::printf("%zu\n", ItemStats(rows, c[1]).size());
        else if (c[0] == "factor" || c[0] == "setto")
        {
            bool const setTo = c[0] == "setto";
            std::size_t const at = setTo ? 4 : 3;
            std::map<std::string, unsigned> counts;
            for (std::size_t i = 0; i < std::stoul(c[at]); ++i)
                counts[c[at + 1 + 2 * i]] = static_cast<unsigned>(std::stoul(c[at + 2 + 2 * i]));
            std::printf("%g\n", setTo ? SkillSetTo(rows, counts, c[1], c[2], std::stod(c[3]), sit) : SkillFactor(rows, counts, c[1], c[2], sit));
        }
        else if (c[0] == "powers")
        {
            double const unit = std::stod(c[3]);
            // the production roll draws in the range and snaps a whole range to whole numbers (Items RollValue); here `unit` is the draw
            auto roll = [&](double low, double high)
            {
                double const drawn = low + unit * (high - low);
                return low == std::floor(low) && high == std::floor(high) ? std::floor(drawn + 0.5) : drawn;
            };
            std::string out;
            char text[160];
            std::vector<Stored> have;
            for (std::size_t i = 4; i < c.size(); ++i)
                have.push_back({c[i], 0});
            for (Rolled const& r : RollPowers(rows, c[1], c[2] == "1", roll, have))
            {
                std::snprintf(text, sizeof text, "%s=%g[%g-%g];", r.key.c_str(), r.value, r.min, r.max);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "worn")
        {
            std::map<std::uint64_t, std::vector<Value>> items;
            std::size_t at = 4;
            for (std::size_t item = 0; item < std::stoul(c[3]); ++item)
            {
                std::string const d3Id = c[at];
                std::size_t const count = std::stoul(c[at + 1]);
                std::vector<Stored> stored;
                for (std::size_t i = 0; i < count; ++i)
                    stored.push_back({c[at + 2 + 2 * i], std::stod(c[at + 3 + 2 * i])});
                at += 2 + 2 * count;
                items[item] = WornValues(rows, d3Id, stored);
            }
            std::string out;
            char text[64];
            for (double v : WornRolls(items, c[1], c[2]))
            {
                std::snprintf(text, sizeof text, "%g;", v);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "bleed")
        {
            double const total = std::stod(c[1]);
            unsigned const base = static_cast<unsigned>(std::stoul(c[2])), ticks = static_cast<unsigned>(std::stoul(c[3]));
            double sum = 0, low = 1e300, high = 0;
            for (unsigned tick = 1; tick <= ticks; ++tick)
            {
                double const one = BleedTick(total, base, tick);
                sum += one;
                low = one < low ? one : low;
                high = one > high ? one : high;
            }
            std::printf("%g %g %g\n", sum, low, high);
        }
    }
    return 0;
}
