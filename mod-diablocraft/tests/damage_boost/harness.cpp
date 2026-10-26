// Drives the timed damage boost's rules (src/combat/dc_damage_boost_math.h) as the production header has them. Input,
// tab separated, one command a line:
//   given <pct> <nowMs> <seconds>          -> "pct=P until=U": the boost that is given
//   live <pct> <untilMs> <nowMs>           -> 1 when the boost stands at now, else 0
//   mult <pct> <untilMs> <nowMs>           -> the multiplier a hit is given
#include "combat/dc_damage_boost_math.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::DamageBoost;

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
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "given")
        {
            Held const held = Given(std::stod(c[1]), std::stoull(c[2]), std::stod(c[3]));
            std::printf("pct=%.10g until=%llu\n", held.pct, static_cast<unsigned long long>(held.until));
        }
        else if (c[0] == "live")
            std::printf("%d\n", Live(Held{std::stod(c[1]), std::stoull(c[2])}, std::stoull(c[3])) ? 1 : 0);
        else if (c[0] == "mult")
            std::printf("%.10g\n", Multiplier(Held{std::stod(c[1]), std::stoull(c[2])}, std::stoull(c[3])));
    }
    return 0;
}
