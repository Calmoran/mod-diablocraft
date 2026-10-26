// Drives DC::LegendaryGem::Scaled - the production function, compiled from
// src/common/dc_legendary_gem.h - with the numbers the generator emitted.
// Line: "<label> <base> <per_rank> <max_rank|none> <rank>". Prints "<label> <value>".
#include "dc_legendary_gem.h"

#include <cstdio>
#include <fstream>
#include <optional>
#include <string>

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::string label, max;
    double base, per;
    unsigned rank;
    while (in >> label >> base >> per >> max >> rank)
    {
        std::optional<uint32_t> cap;
        if (max != "none")
            cap = std::stoul(max);
        std::printf("%s %.12g\n", label.c_str(), DC::LegendaryGem::Scaled(base, per, cap, rank));
    }
    return 0;
}
