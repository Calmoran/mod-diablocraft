// Drives ChestOpen::Openings of src/combat/dc_chest_open_math.h (diablocraft-69lxx, N-CHEST): when a chest's loot state change is an opening.
// Input, tab separated, one command a line:
//   state <map> <instance> <guid> <activated|other>   -> the chest's loot state changed: prints 1 when that is an opening, else 0
//   forget <map> <instance> <guid>                    -> the chest left the world
//   held                                              -> prints how many chests the tracker holds as activated
#include "combat/dc_chest_open_math.h"

#include <cstdio>
#include <fstream>
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
    ChestOpen::Openings openings;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "state" || c[0] == "forget")
        {
            ChestOpen::Key const key{static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2])), std::stoull(c[3])};
            if (c[0] == "forget")
                openings.Forget(key);
            else
                std::printf("%d\n", openings.Changed(key, c[4] == "activated") ? 1 : 0);
        }
        else if (c[0] == "held")
            std::printf("%zu\n", openings.Held());
    }
    return 0;
}
