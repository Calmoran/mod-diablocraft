// Drives the production dc_gr_urshi.h (where she stands) and dc_gr_complete.h (the line at the Guardian's death, in the record it travels in). Input, tab separated, one command a line:
//   angles <base>                                   -> the eight directions tried, space separated
//   facing <fromX> <fromY> <toX> <toY> <fallback>    -> FacingAngle
//   fits <wanted> <got> <climb> <los 0|1> <share> <maxClimb> -> SpotFits, 1 or 0
//   line <seconds left>                              -> the record's fields (Text::Fields of CompleteParts), joined by '|'
#include "rifts/dc_gr_complete.h"
#include "rifts/dc_gr_urshi.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Rifts::Gr;

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
        if (c[0] == "angles")
        {
            for (double angle : SpawnAngles(std::stod(c[1])))
                std::printf("%.9f ", angle);
            std::printf("\n");
        }
        else if (c[0] == "facing")
            std::printf("%.9f\n", FacingAngle(std::stod(c[1]), std::stod(c[2]), std::stod(c[3]), std::stod(c[4]), std::stod(c[5])));
        else if (c[0] == "fits")
            std::printf("%d\n", SpotFits(std::stod(c[1]), std::stod(c[2]), std::stod(c[3]), c[4] == "1", std::stod(c[5]), std::stod(c[6])) ? 1 : 0);
        else if (c[0] == "line")
        {
            std::string joined;
            for (std::string const& field : DC::Rifts::Text::Fields(DC::Rifts::Text::GreaterRiftComplete, CompleteParts(static_cast<unsigned>(std::stoul(c[1])))))
                joined += (joined.empty() ? "" : "|") + field;
            std::printf("%s\n", joined.c_str());
        }
    }
    return 0;
}
