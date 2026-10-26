// Drives the Companion's rules (src/classes/demon_hunter/dc_demon_hunter_companion_math.h) as the production header has
// them. Input, tab separated, one command a line:
//   rune <name>                                   -> the form's number (0 raven, 1 spider, 2 boar, 3 wolf, 4 bat, 5
//   ferret) pets <name>                                   -> how many pets the form has entry <name> -> the creature
//   entry that wears the form life <name> <formsPct> <boarPct>              -> the pet's Life share cone <name> -> 1
//   when the form's attack reaches a cone angle <a> <b>                                 -> the smallest angle between
//   two headings, radians incone <heading> <centre> <distance> <yards> <degrees>   -> 1 when the point is in the cone
//   party <distance> <yards>                      -> 1 when a member is in range
//   regen <table> <share>                         -> the boar's regeneration a second
//   millis <seconds>                              -> whole milliseconds
#include "classes/demon_hunter/dc_demon_hunter_companion_math.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::DemonHunter::Companion;

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
        std::string const name = c.size() > 1 ? c[1] : "";
        if (c[0] == "rune")
            std::printf("%d\n", static_cast<int>(RuneOf(name)));
        else if (c[0] == "pets")
            std::printf("%u\n", Pets(RuneOf(name)));
        else if (c[0] == "entry")
            std::printf("%u\n", EntryOf(RuneOf(name)));
        else if (c[0] == "life")
            std::printf("%.10g\n", LifePct(RuneOf(name), std::stod(c[2]), std::stod(c[3])));
        else if (c[0] == "cone")
            std::printf("%d\n", HasCone(RuneOf(name)) ? 1 : 0);
        else if (c[0] == "angle")
            std::printf("%.10g\n", AngleBetween(std::stod(c[1]), std::stod(c[2])));
        else if (c[0] == "incone")
            std::printf(
                "%d\n",
                InCone(std::stod(c[1]), std::stod(c[2]), std::stod(c[3]), std::stod(c[4]), std::stod(c[5])) ? 1 : 0);
        else if (c[0] == "party")
            std::printf("%d\n", InPartyRange(std::stod(c[1]), std::stod(c[2])) ? 1 : 0);
        else if (c[0] == "regen")
            std::printf("%.10g\n", RegenPerSecond(std::stod(c[1]), std::stod(c[2])));
        else if (c[0] == "millis")
            std::printf("%u\n", Millis(std::stod(c[1])));
    }
    return 0;
}
