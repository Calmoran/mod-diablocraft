// Drives DC::Combat::Proc::Rolls - the production function, compiled from
// src/combat/dc_proc_math.h - with the coefficient each line hands it.
// Line: "<label> <coefficient|none>". Prints "<label> <hits> <rolls>".
// The roll is the core's roll_chance_f: a percent wins when it is above a
// uniform draw in [0, 100).
#include "dc_proc_math.h"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <optional>
#include <random>
#include <string>

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::mt19937_64 engine(20260929);
    std::uniform_real_distribution<double> draw(0.0, 100.0);
    auto roll = [&](float pct) { return pct > float(draw(engine)); };
    constexpr int rolls = 200000;
    std::string label, value;
    while (in >> label >> value)
    {
        std::optional<double> coefficient;
        if (value != "none")
            coefficient = std::stod(value);
        int hits = 0;
        for (int i = 0; i < rolls; ++i)
            hits += DC::Combat::Proc::Rolls(coefficient, roll) ? 1 : 0;
        std::printf("%s %d %d\n", label.c_str(), hits, rolls);
    }
    return 0;
}
