// Drives the exact-damage rules of src/combat/dc_exact_damage.h as the production header has them. Input, tab separated, one command a line:
//   exact <amount>          -> ExactDamage(amount) as a decimal whole number
//   boosted <amount> <mult> -> Boosted(amount, mult), "%.10g"
#include "combat/dc_exact_damage.h"

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
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "exact")
            std::printf("%llu\n", static_cast<unsigned long long>(ExactDamage(std::stod(c[1]))));
        else if (c[0] == "boosted")
            std::printf("%.10g\n", Boosted(std::stod(c[1]), std::stod(c[2])));
    }
    return 0;
}
