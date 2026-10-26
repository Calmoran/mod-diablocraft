// Rift floors Part F2 (diablocraft-m36x). Compiles the production decisions of the exit portal (dc_rift_exit.h) and the
// production run book (dc_rift_floors.h) and drives them: the spot an exit stands on, the refusals, the floor a click leads
// to, the maps a new floor may roll, where the obelisk portal leads once floor 1 has unloaded, the SQL of `.dc floor exit`.
// argv[1]: a file with the pool's map ids, one per dungeon row, in rift_dungeons.csv order (the test reads the sheet).
// argv[2] (optional): `place<TAB>dungeon<TAB>x y z o` and `clear<TAB>dungeon` lines; the SQL for each is printed.
#include "dc_rift_exit.h"
#include "dc_rift_floors.h"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <set>
#include <string>
#include <vector>

using namespace DC::Rifts;

struct Run
{
    std::uint64_t id = 0;
    std::uint32_t instanceId = 0, mapId = 0, dungeonId = 0;
    unsigned floor = 1;
};

int main(int argc, char** argv)
{
    assert(argc >= 2);
    std::vector<std::uint32_t> maps;
    {
        std::ifstream in(argv[1]);
        std::uint32_t map;
        while (in >> map)
            maps.push_back(map);
    }
    assert(maps.size() == 30);

    // 6.2: his spot beats the survey's; the survey's stands where he placed none; none at all is none.
    {
        Exit::Spot alex{1, 2, 3, 4}, survey{5, 6, 7, 8};
        assert(Exit::ChooseSpot(alex, survey)->x == 1);
        assert(Exit::ChooseSpot(std::nullopt, survey)->x == 5);
        assert(Exit::ChooseSpot(alex, std::nullopt)->x == 1);
        assert(!Exit::ChooseSpot(std::nullopt, std::nullopt));
    }

    // The exit's template is the look's entry plus the offset, plus a block per floor led to after the second, and back.
    assert(Exit::ExitEntry(910030, 2) == 910070 && Exit::LookOf(910070) == 910030);
    assert(Exit::ExitEntry(910030, 3) == 911070 && Exit::ExitEntry(910046, 10) == 918086);
    for (unsigned floor = 2; floor <= 10; ++floor)
        for (std::uint32_t look = 910030; look <= 910046; ++look)
            assert(Exit::LookOf(Exit::ExitEntry(look, floor)) == look);
    assert(Exit::LookOf(5) == 0 && Exit::LookOf(911039) == 0);

    // The refusals, and their order: a closed run first, then the Guardian, then the cap, then no map left.
    {
        using R = Exit::Refusal;
        assert(Exit::MayOpenNext("open", 0, 1, 10, 5) == R::None);
        assert(Exit::MayOpenNext("open", 0, 9, 10, 5) == R::None);     // floor 10 is the last one allowed
        assert(Exit::MayOpenNext("open", 0, 10, 10, 5) == R::LastFloor); // floor 11 is not
        assert(Exit::MayOpenNext("open", 0, 1, 1, 5) == R::LastFloor);
        assert(Exit::MayOpenNext("open", 0, 1, 0, 5) == R::LastFloor);   // a cap nobody set opens nothing
        assert(Exit::MayOpenNext("open", 0, 1, 10, 0) == R::NoMap);
        assert(Exit::MayOpenNext("guardian", 0, 1, 10, 5) == R::Guardian);
        assert(Exit::MayOpenNext("complete", 0, 1, 10, 5) == R::Guardian);
        assert(Exit::MayOpenNext("open", 7, 1, 10, 5) == R::Guardian);   // the Guardian's floor is recorded
        assert(Exit::MayOpenNext("closed", 0, 1, 10, 5) == R::Closed);
        assert(Exit::MayOpenNext("closed", 7, 99, 10, 0) == R::Closed);
        assert(Exit::MayOpenNext("guardian", 7, 99, 10, 0) == R::Guardian);
        assert(Exit::MayOpenNext("open", 0, 10, 10, 0) == R::LastFloor);
        for (R why : {R::Closed, R::Guardian, R::LastFloor, R::NoMap})
            assert(*Exit::Say(why));
        assert(!*Exit::Say(R::None));
    }

    // The floor a click leads to: the lowest number above this floor's that stands.
    {
        assert(Exit::NextStanding({1, 2, 3}, 1) == 2);
        assert(Exit::NextStanding({3, 1, 2}, 1) == 2);   // no order assumed
        assert(Exit::NextStanding({1, 3}, 1) == 3);      // floor 2 unloaded
        assert(Exit::NextStanding({1, 2}, 2) == 0);      // nothing after the last
        assert(Exit::NextStanding({1, 2, 3}, 3) == 0);
        assert(Exit::NextStanding({2, 3}, 1) == 2);
        assert(Exit::NextStanding({}, 1) == 0);
    }

    // The obelisk portal: floor 1; else the lowest floor still standing; else none.
    {
        assert(Exit::ObeliskFloor({1, 2, 3}) == 1);
        assert(Exit::ObeliskFloor({3, 2}) == 2);
        assert(Exit::ObeliskFloor({4}) == 4);
        assert(Exit::ObeliskFloor({}) == 0);
    }

    // The maps a new floor may roll: a run never uses a map twice. Scarlet Monastery's two rows share map 189.
    {
        std::set<std::uint32_t> distinct(maps.begin(), maps.end());
        assert(distinct.size() == 29);
        assert(Exit::EligibleMaps(maps, {}).size() == 30);
        std::set<std::uint32_t> used{189};
        std::vector<std::size_t> eligible = Exit::EligibleMaps(maps, used);
        assert(eligible.size() == 28);                   // both rows of map 189 are out
        for (std::size_t i : eligible)
            assert(maps[i] != 189);
        // A whole run: always take the first eligible row, as a roll that happens to; it ends after 29 floors, no map twice.
        LiveRuns<Run> live;
        Run run;
        run.id = 1, run.instanceId = 100, run.mapId = maps[0], run.dungeonId = 1;
        live.Start(run);
        unsigned floors = 1;
        for (;;)
        {
            std::vector<std::size_t> pick = Exit::EligibleMaps(maps, live.UsedMaps(1));
            if (Exit::MayOpenNext("open", 0, live.Highest(1), 99, pick.size()) != Exit::Refusal::None)
            {
                assert(Exit::MayOpenNext("open", 0, live.Highest(1), 99, pick.size()) == Exit::Refusal::NoMap);
                break;
            }
            unsigned const number = live.AddFloor(1, 100 + floors, maps[pick.back()], pick.back() + 1);
            assert(number == ++floors);
        }
        assert(floors == 29 && live.UsedMaps(1).size() == 29 && live.Highest(1) == 29);
    }

    // The book: the highest floor and the used maps outlive an unloaded floor (the cap and the no-repeat rule count them).
    {
        LiveRuns<Run> live;
        Run run;
        run.id = 7, run.instanceId = 10, run.mapId = 33, run.dungeonId = 1;
        live.Start(run);
        assert(live.Highest(7) == 1 && live.UsedMaps(7) == std::set<std::uint32_t>{33});
        assert(live.AddFloor(7, 11, 34, 2) == 2 && live.AddFloor(7, 12, 36, 3) == 3);
        assert(live.Highest(7) == 3 && live.UsedMaps(7).size() == 3);
        live.Remove(12, 36);                              // the third floor unloads
        assert(live.FloorCount(7) == 2);
        assert(live.Highest(7) == 3);                     // still counts for the cap
        assert(live.UsedMaps(7).count(36) == 1);          // and its map is still not rolled again
        assert(live.AddFloor(7, 13, 43, 4) == 4);
        assert(live.Highest(99) == 0 && live.UsedMaps(99).empty());
    }

    // The SQL of `.dc floor exit`, for the commands in argv[2] (the test runs it on a scratch schema): an apostrophe in a
    // dungeon name does not end the string.
    if (argc > 2)
    {
        std::ifstream in(argv[2]);
        std::string kind, name;
        while (std::getline(in, kind, '\t'))
        {
            std::getline(in, name, kind == "place" ? '\t' : '\n');
            if (kind == "place")
            {
                Exit::Spot at;
                in >> at.x >> at.y >> at.z >> at.o;
                in.ignore();
                std::printf("%s\n", Exit::PlaceSql(name, at).c_str());
            }
            else
                std::printf("%s\n", Exit::ClearSql(name).c_str());
        }
    }
    std::puts("rift exit harness: ok");
    return 0;
}
