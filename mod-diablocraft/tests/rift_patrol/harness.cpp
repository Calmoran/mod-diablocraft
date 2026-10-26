// Drives the production recording rules (src/rifts/dc_rift_patrol.h), one command per line on stdin, answers on stdout. No game code.
//   record <step> <dungeon, the rest of the line>   starts a walk on map 1
//   map <id>                                the map the player is on from now on (starts at 1)
//   add <x> <y> <z>                         a sample (the sampler's call)
//   finish <x> <y> <z>                      where he stopped
//   onmap <id>                              ONMAP 0|1: is the walk on that map
//   show                                    POINTS n, one P x y z per point, USABLE 0|1
//   nearest <x> <y> <z> <id:x:y:z> ...      NEAREST <index> <id>
//   next <highest>                          NEXT <id>
//   sql <anchor> <path>                     the statements for the walk so far, one per line
#include "dc_rift_patrol.h"

#include <iostream>
#include <memory>
#include <sstream>

using namespace DC::Rifts::Patrol;

int main()
{
    std::unique_ptr<Recording> walk;
    std::uint32_t here = 1;
    std::string line;
    while (std::getline(std::cin, line))
    {
        std::istringstream in(line);
        std::string word;
        in >> word;
        if (word == "record")
        {
            std::string dungeon;
            double step;
            in >> step;
            std::getline(in >> std::ws, dungeon);
            here = 1;
            walk = std::make_unique<Recording>(dungeon, step, here);
        }
        else if (word == "map")
            in >> here;
        else if (word == "onmap")
        {
            std::uint32_t id;
            in >> id;
            std::printf("ONMAP\t%d\n", walk->OnMap(id) ? 1 : 0);
        }
        else if (word == "add" || word == "finish")
        {
            Point p;
            in >> p.x >> p.y >> p.z;
            if (word == "add")
                walk->Add(here, p);
            else
                walk->Finish(here, p);
        }
        else if (word == "show")
        {
            std::printf("POINTS\t%zu\n", walk->Points().size());
            for (Point const& p : walk->Points())
                std::printf("P\t%.4f\t%.4f\t%.4f\n", p.x, p.y, p.z);
            std::printf("USABLE\t%d\n", walk->Usable() ? 1 : 0);
        }
        else if (word == "nearest")
        {
            Point p;
            in >> p.x >> p.y >> p.z;
            std::vector<DC::Rifts::Spawn::Anchor> anchors;
            std::string token;
            while (in >> token)
            {
                DC::Rifts::Spawn::Anchor a;
                char colon;
                std::istringstream cell(token);
                cell >> a.id >> colon >> a.x >> colon >> a.y >> colon >> a.z;
                anchors.push_back(a);
            }
            int const at = NearestAnchor(anchors, p);
            std::printf("NEAREST\t%d\t%u\n", at, at < 0 ? 0u : anchors[at].id);
        }
        else if (word == "next")
        {
            std::uint64_t highest;
            in >> highest;
            std::printf("NEXT\t%u\n", NextPathId(static_cast<std::uint32_t>(highest)));
        }
        else if (word == "sql")
        {
            unsigned anchor;
            std::uint32_t path;
            in >> anchor >> path;
            for (std::string const& statement : Statements(walk->Dungeon(), path, anchor, walk->Points()))
                std::printf("SQL\t%s\n", statement.c_str());
        }
    }
    return 0;
}
