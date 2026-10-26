// Drives the ground devices' rules (src/combat/dc_ground_device_math.h) as the production header has them. Input, tab
// separated, one command a line:
//   spec <mode proximity|command|periodic> <radius> <armMs> <lifetimeMs> <intervalMs> <most>   the device's numbers;
//   the state is cleared clear the state is cleared step <diffMs> <enemyNear 0|1> <lookEveryMs>   -> "fires=N gone=0|1
//   asked=K": one Advance; K is how many times the enemy test was asked overflow <placed> <most> -> how many of the
//   oldest give way armed                                          -> 1 when the device is armed now detonable -> 1
//   when the device can be detonated now due <clock> <diff> <interval> <cap>            -> "due=N clock=C": Due on a
//   clock
#include "combat/dc_ground_device_math.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::GroundDevice;

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
    Spec spec;
    State state;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "spec")
        {
            spec = Spec{};
            spec.mode = c[1] == "command" ? Mode::Command : c[1] == "periodic" ? Mode::Periodic : Mode::Proximity;
            spec.radiusYards = std::stod(c[2]);
            spec.armMs = std::stod(c[3]);
            spec.lifetimeMs = std::stod(c[4]);
            spec.intervalMs = std::stod(c[5]);
            spec.most = static_cast<std::size_t>(std::stoul(c[6]));
            state = State{};
        }
        else if (c[0] == "clear")
            state = State{};
        else if (c[0] == "step")
        {
            unsigned asked = 0;
            bool const near = c[2] == "1";
            Outcome const out = Advance(state, spec, std::stod(c[1]), std::stod(c[3]),
                                        [&]
                                        {
                                            ++asked;
                                            return near;
                                        });
            std::printf("fires=%u gone=%d asked=%u\n", out.fires, out.gone ? 1 : 0, asked);
        }
        else if (c[0] == "overflow")
            std::printf("%zu\n", Overflow(static_cast<std::size_t>(std::stoul(c[1])),
                                          static_cast<std::size_t>(std::stoul(c[2]))));
        else if (c[0] == "armed")
            std::printf("%d\n", Armed(state, spec) ? 1 : 0);
        else if (c[0] == "detonable")
            std::printf("%d\n", Detonable(state, spec) ? 1 : 0);
        else if (c[0] == "due")
        {
            double clock = std::stod(c[1]);
            unsigned const due = Due(clock, std::stod(c[2]), std::stod(c[3]), static_cast<unsigned>(std::stoul(c[4])));
            std::printf("due=%u clock=%.10g\n", due, clock);
        }
    }
    return 0;
}
