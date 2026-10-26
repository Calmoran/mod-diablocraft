// Drives the Tal Rasha's Elements rules of src/combat/dc_item_power_math.h (diablocraft-fkcp2) with the rows the generator emitted.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | count <set> <n> | reset | clear
//   fire <event> <skill> -> "stat=value@on;..." of the effect rows ItemPower::Fire fires (the draw is 0: every chance falls)
//   factor <stat>         -> ItemPower::PlayerFactor with the window as it is now
//   attack <element> <seconds> <fullAt> <extendSeconds> <maxSeconds> -> WindowAttack at `now`
//   window                -> "open remainingMs extendedMs stacks"
//   touch <resist|immune> <element> <ms> -> Touch at `now`: 1 when the buff was off before
//   on <resist|immune>    -> CountOn at `now`
//   drops <element> <onBar 0|1> | setmeteor <element> | rune <element>
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <fstream>
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
    std::map<std::string, unsigned> counts;
    Situation sit;
    ElementState state;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        sit.elementWindow = WindowOn(state, sit.now);
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
        else if (c[0] == "count")
            counts[c[1]] = static_cast<unsigned>(std::stoul(c[2]));
        else if (c[0] == "reset")
            state = ElementState{};
        else if (c[0] == "clear")
        {
            sit = Situation{};
            counts.clear();
            state = ElementState{};
        }
        else if (c[0] == "fire")
        {
            std::string out;
            for (Fired const& f : Fire(rows, counts, sit, c[1], c.size() > 2 ? c[2] : "", 1.0, [](double pct) { return 0.0 < pct; }))
            {
                char text[160];
                std::snprintf(text, sizeof text, "%s=%g@%s;", f.stat.c_str(), f.value, f.on.c_str());
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "factor")
            std::printf("%g\n", PlayerFactor(rows, counts, c[1], sit));
        else if (c[0] == "attack")
            WindowAttack(state, c[1], sit.now, std::stod(c[2]), static_cast<unsigned>(std::stoul(c[3])), std::stod(c[4]), std::stod(c[5]));
        else if (c[0] == "window")
            std::printf("%d %d %u %zu\n", WindowOn(state, sit.now) ? 1 : 0, WindowOn(state, sit.now) ? static_cast<int>(state.windowUntil - sit.now) : 0,
                        state.extendedMs, state.stacks.size());
        else if (c[0] == "touch")
        {
            auto& ends = c[1] == "resist" ? state.resistUntil : state.immuneUntil;
            std::printf("%d\n", Touch(ends, c[2], sit.now, static_cast<std::uint32_t>(std::stoul(c[3]))) ? 1 : 0);
        }
        else if (c[0] == "on")
            std::printf("%u\n", CountOn(c[1] == "resist" ? state.resistUntil : state.immuneUntil, sit.now));
        else if (c[0] == "drops")
            std::printf("%d\n", MeteorDrops(state, c[1], c[2] == "1") ? 1 : 0);
        else if (c[0] == "setmeteor")
            state.lastMeteor = c[1];
        else if (c[0] == "rune")
            std::printf("[%s]\n", MeteorRune(c[1]).c_str());
    }
    return 0;
}
