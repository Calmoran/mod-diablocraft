// Pylons and shrines P3 (diablocraft-7h5tr): the objects' entries and the click's share and one use, through the real
// src/combat/dc_pylon_math.h (Spend, Reaches, KindOfObject, IsPylonObject); scripts/tests/rifts/test_pylon_objects.py builds and
// drives it.
//   "spend <kind> <radius> <spent> <member>..."  one click; a member is floor:yards:gives (1 on the clicker's floor,
//                                                yards from the clicker, 1 when Give succeeds). Prints "none" for a
//                                                spent object, else "<given> <spent after> <who got it, 0/1 each>"
//   "object <entry>"                             prints "<kind index or -1> <is a pylon object>"
#include "../../src/combat/dc_pylon_math.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::Pylons;

namespace
{
    struct Member
    {
        bool floor;
        double yards;
        bool gives;
        bool got = false;
    };
} // namespace

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::string line;
    while (std::getline(in, line))
    {
        std::istringstream words(line);
        std::string verb;
        words >> verb;
        if (verb == "spend")
        {
            std::string name, cell;
            double radius;
            int spentBefore;
            words >> name >> radius >> spentBefore;
            std::vector<Member> members;
            while (words >> cell)
            {
                Member m{};
                int floor, gives;
                std::sscanf(cell.c_str(), "%d:%lf:%d", &floor, &m.yards, &gives);
                m.floor = floor;
                m.gives = gives;
                members.push_back(m);
            }
            std::vector<Member*> pointers;
            for (Member& m : members)
                pointers.push_back(&m);
            bool spent = spentBefore;
            auto const given = Spend(
                spent, *Parse(name), radius, pointers, [](Member* m) { return m->floor; },
                [](Member* m)
                {
                    if (!m->floor)
                        throw 1; // the distance is never asked of a member on another map
                    return m->yards;
                },
                [](Member* m) { return m->got = m->gives; });
            if (!given)
            {
                std::printf("none\n");
                continue;
            }
            std::printf("%u %d", *given, spent ? 1 : 0);
            for (Member const& m : members)
                std::printf(" %d", m.got ? 1 : 0);
            std::printf("\n");
        }
        else if (verb == "object")
        {
            unsigned long entry;
            words >> entry;
            auto const kind = KindOfObject(static_cast<std::uint32_t>(entry));
            std::printf("%d %d\n", kind ? static_cast<int>(*kind) : -1,
                        IsPylonObject(static_cast<std::uint32_t>(entry)) ? 1 : 0);
        }
    }
    return 0;
}
