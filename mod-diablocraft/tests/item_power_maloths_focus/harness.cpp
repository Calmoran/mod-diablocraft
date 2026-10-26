// Drives Maloth's Focus's rules (diablocraft-kxdwe, N-FEAR) of src/combat/dc_item_power_math.h with the rows the generator emitted: the `tick` clock that fires
// the `fear_enemies` effect once its cooldown is up (ItemPower::Fire, including a stamp set ahead of now), the stock hold the effect puts (ControlSpell), and the
// two stamps the executor sets (DelayedStamp after a proc that feared someone, RetryStamp after one that found nobody). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear | now <ms>
//   stamp <ms>                  -> the fear row's last proc is at <ms> (a stamp ahead of now is an extra wait)
//   fire <event> <skill>        -> the effects that fired as "stat:number;..." or "none"
//   spell <stat>                -> ControlSpell
//   delay <now> <deltaSeconds> <unit>   -> DelayedStamp
//   retry <now> <icdSeconds> <retrySeconds>   -> RetryStamp
//   ahead <now> <last>          -> StampAhead: 1 or 0
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
        else if (c[0] == "stamp")
        {
            for (auto const& row : rows)
                if (row.stat == "fear_enemies")
                    sit.fired[ItemPower::FireKey(row)] = static_cast<std::uint32_t>(std::stoul(c[1]));
        }
        else if (c[0] == "spell")
            std::printf("%u\n", ItemPower::ControlSpell(c[1]));
        else if (c[0] == "delay")
            std::printf("%u\n", ItemPower::DelayedStamp(static_cast<std::uint32_t>(std::stoul(c[1])), std::stod(c[2]), std::stod(c[3])));
        else if (c[0] == "ahead")
            std::printf("%d\n", ItemPower::StampAhead(static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2]))) ? 1 : 0);
        else if (c[0] == "retry")
            std::printf("%u\n", ItemPower::RetryStamp(static_cast<std::uint32_t>(std::stoul(c[1])), std::stod(c[2]), std::stod(c[3])));
    }
    return 0;
}
