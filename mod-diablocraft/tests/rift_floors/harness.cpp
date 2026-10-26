// Rift floors Part F1 (diablocraft-p8m7). Compiles the production Rift (dc_rifts.h), the production run book
// (dc_rift_floors.h) and the six public calls cut out of dc_rifts.cpp (included below from the generated file), against
// small doubles for the core's Map, Player and Creature, and drives a run that holds two floors.
#include "dc_rifts.h"
#include "dc_rift_floors.h"

#include <cassert>
#include <cstdio>
#include <mutex>
#include <string>
#include <vector>

struct Map
{
    unsigned id = 0, instance = 0;
    bool dungeon = true;
    bool IsDungeon() const { return dungeon; }
    unsigned GetInstanceId() const { return instance; }
    unsigned GetId() const { return id; }
};
struct Player
{
    Map* map = nullptr;
    Map* GetMap() const { return map; }
};
struct Creature
{
    Map* map = nullptr;
    Map* GetMap() const { return map; }
};
class WorldLocation
{
public:
    WorldLocation() = default;
    WorldLocation(unsigned m, float px, float py, float pz, float po) : map(m), x(px), y(py), z(pz), o(po) {}
    unsigned map = 0;
    float x = 0, y = 0, z = 0, o = 0;
};

namespace DC::Rifts
{
    struct Dungeon
    {
        std::uint32_t dungeonId = 0, mapId = 0;
        float x = 0, y = 0, z = 0, o = 0;
    };
    std::mutex dataMutex, riftMutex;
    std::vector<Dungeon> pool;
    LiveRuns<Rift> live;

    // the six public calls, as dc_rifts.cpp defines them
#include "calls.inc"
} // namespace DC::Rifts

using namespace DC::Rifts;

static Rift run(std::uint64_t id, std::uint32_t instance, std::uint32_t map, std::uint32_t dungeon, char const* mode = "nr")
{
    Rift rift;
    rift.id = id;
    rift.instanceId = instance;
    rift.mapId = map;
    rift.dungeonId = dungeon;
    rift.tier = 3;
    rift.players = 2;
    rift.mode = mode;
    rift.grRank = std::string(mode) == "gr" ? 17 : 0;
    return rift;
}

int main()
{
    pool = {{4, 33, 1, 2, 3, 0.5f}, {7, 34, 10, 20, 30, 1.5f}, {9, 35, 100, 200, 300, 2.5f}};

    // ---- the book: a run, its floors, the index ----
    live.Start(run(5, 11, 33, 4, "gr"));
    assert(live.Find(5) && live.Find(5)->floor == 1 && live.FloorCount(5) == 1 && live.Size() == 1);
    assert(live.FloorAt(11, 33) && live.FloorAt(11, 0) && !live.FloorAt(11, 34));    // the map is a guard: ids are reused
    assert(!live.FloorAt(12, 0) && live.AddFloor(99, 12, 34, 7) == 0);              // an unknown run takes no floor
    assert(live.AddFloor(5, 12, 34, 7) == 2 && live.FloorCount(5) == 2);
    Rift two;
    assert(live.View(12, 34, two));
    assert(two.id == 5 && two.instanceId == 12 && two.mapId == 34 && two.dungeonId == 7 && two.floor == 2);
    assert(two.tier == 3 && two.mode == "gr" && two.grRank == 17);                  // the rest of the run is the run's
    assert(live.Find(5)->instanceId == 11 && live.Find(5)->mapId == 33 && live.Find(5)->floor == 1);   // its own row stays floor 1's
    assert(!live.View(12, 33, two) && !live.View(13, 0, two));
    auto views = live.Views(5);
    assert(views.size() == 2 && views[0].instanceId == 11 && views[0].floor == 1 && views[1].instanceId == 12 && views[1].floor == 2);
    assert(live.FindByInstance(12, 34) == live.Find(5) && live.FindByInstance(12, 33) == nullptr);

    // ---- a write-back from a copy seen from floor 2 moves the run's state and not its row ----
    two.progress = 400;
    two.state = "guardian";
    two.guardianInstance = 12;
    live.Store(two);
    assert(live.Find(5)->progress == 400 && live.Find(5)->state == "guardian" && live.Find(5)->guardianInstance == 12);
    assert(live.Find(5)->instanceId == 11 && live.Find(5)->mapId == 33 && live.Find(5)->dungeonId == 4 && live.Find(5)->floor == 1);
    live.Find(5)->state = "open";

    // ---- the six public calls answer for both floors ----
    Map oneMap{33, 11}, twoMap{34, 12}, hub{0, 0, false}, stale{99, 11};
    Player onOne{&oneMap}, onTwo{&twoMap}, inHub{&hub}, onStale{&stale};
    Rift seen;
    assert(Current(&onOne, seen) && seen.id == 5 && seen.instanceId == 11 && seen.floor == 1);
    assert(Current(&onTwo, seen) && seen.id == 5 && seen.instanceId == 12 && seen.mapId == 34 && seen.floor == 2);
    assert(!Current(&inHub, seen));
    assert(IsLiveInstance(33, 11) && IsLiveInstance(34, 12));
    assert(!IsLiveInstance(34, 11) && !IsLiveInstance(33, 12) && !IsLiveInstance(33, 13));   // wrong map or unknown instance
    unsigned tier = 0, players = 0;
    assert(ScalingContext(&oneMap, tier, players) && tier == 3 && players == 2);
    tier = players = 0;
    assert(ScalingContext(&twoMap, tier, players) && tier == 3 && players == 2);
    assert(!ScalingContext(&hub, tier, players) && !ScalingContext(&stale, tier, players));  // an id reused on another map is no floor
    assert(GreaterRiftLevel(&oneMap) == 17 && GreaterRiftLevel(&twoMap) == 17 && GreaterRiftLevel(&hub) == 0 && GreaterRiftLevel(&stale) == 0);
    Creature onFloorTwo{&twoMap}, inTheHub{&hub};
    tier = 0;
    assert(InRift(&onFloorTwo, tier) && tier == 3 && !InRift(&inTheHub, tier) && !InRift(nullptr, tier));
    WorldLocation entry;
    assert(EntryPosition(&onOne, entry) && entry.map == 33 && entry.x == 1 && entry.o == 0.5f);        // floor 1's dungeon
    assert(EntryPosition(&onTwo, entry) && entry.map == 34 && entry.x == 10 && entry.o == 1.5f);       // floor 2's own arrival point
    assert(!EntryPosition(&inHub, entry));

    // a Nephalem run answers the level as 0 on every floor
    live.Start(run(6, 21, 35, 9, "nr"));
    live.AddFloor(6, 22, 36, 9);
    Map nrOne{35, 21}, nrTwo{36, 22};
    assert(GreaterRiftLevel(&nrOne) == 0 && GreaterRiftLevel(&nrTwo) == 0);

    // ---- a closed run still answers the scaling context (until its maps are gone) and no longer the rest ----
    live.Find(6)->state = "closed";
    assert(ScalingContext(&nrTwo, tier, players) && !IsLiveInstance(36, 22));
    Player onNrTwo{&nrTwo};
    assert(!Current(&onNrTwo, seen));
    live.Find(6)->state = "open";

    // ---- one floor's map is destroyed: that floor leaves, the run stays ----
    using Gone = LiveRuns<Rift>::Gone;
    assert(live.Remove(11, 34) == Gone::Unknown && live.FloorCount(5) == 2);       // the wrong map: not this run's floor
    assert(live.Remove(77, 0) == Gone::Unknown);
    assert(live.Remove(11, 33) == Gone::Floor);
    assert(live.Find(5) && live.FloorCount(5) == 1 && !live.FloorAt(11, 33));
    assert(Current(&onTwo, seen) && seen.floor == 2 && IsLiveInstance(34, 12) && !IsLiveInstance(33, 11));
    assert(ScalingContext(&twoMap, tier, players) && !ScalingContext(&oneMap, tier, players));
    assert(live.Find(5)->instanceId == 11);                                          // the row keeps the floor it began on
    // a floor added after another was lost is numbered above every number the run has had
    assert(live.AddFloor(5, 13, 35, 9) == 3);
    // the instance id is reused by a new run on another map: the new run owns it, the old one cannot take it back
    live.Start(run(8, 11, 40, 4));
    assert(live.FloorAt(11, 40) && live.FloorAt(11, 40)->runId == 8 && !live.FloorAt(11, 33));
    // and the last floor takes the run with it
    assert(live.Remove(12, 34) == Gone::Floor && live.Remove(13, 35) == Gone::TheRun);
    assert(!live.Find(5) && !live.FloorAt(12, 0) && !live.FloorAt(13, 0));
    assert(!Current(&onTwo, seen) && !IsLiveInstance(34, 12) && !ScalingContext(&twoMap, tier, players));
    assert(live.Find(8) && live.FloorAt(11, 40));                                   // the other runs are untouched
    assert(live.IndexSize() == 3);                                                  // run 6's two floors and run 8's one: nothing left behind

    unsigned runs = 0;
    live.Each([&](Rift const&) { ++runs; });
    assert(runs == live.Size() && runs == 2);
    live.Clear();
    assert(live.Size() == 0 && live.IndexSize() == 0 && !live.FloorAt(11, 0));

    std::puts("rift floors harness: ok");
    return 0;
}
