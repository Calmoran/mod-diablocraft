// Drives dc_ground_missile_math.h (the production header) with the cases the test builds from the generated spell
// records. Input, tab separated, one command a line:
//   path <speed> <channeled 0|1> <aimsAtAUnit 0|1> -> "cast", "impact" or "arrival"
//   arrival <distance> <speed> -> the missile's flight in milliseconds
#include "combat/dc_ground_missile_math.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::GroundMissile;

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
        if (c[0] == "path")
        {
            Path const path = PathOf(std::stod(c[1]), c[2] == "1", c[3] == "1");
            std::printf("%s\n", path == Path::AtCast ? "cast" : path == Path::OnImpact ? "impact" : "arrival");
        }
        else if (c[0] == "arrival")
            std::printf("%u\n", ArrivalMs(std::stod(c[1]), std::stod(c[2])));
    }
    return 0;
}
