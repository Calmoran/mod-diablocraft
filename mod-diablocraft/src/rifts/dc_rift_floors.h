/*
 * World of DiabloCraft - the live runs and their floors (rift floors Part F1, docs/proposals/rift-floors.md 4.2).
 *
 * A RUN is one rift from the obelisk to the Keeper's close: one quest, one bar, one Guardian, one clock. A FLOOR is one
 * instance of it. Today every run has one floor; the next floors (Part F2) are added with AddFloor and nothing else in
 * the book changes.
 *
 * The book keeps each run once, keyed by its id (dc_rift.id), and an index from instance id to run and floor. The run
 * it holds is the run's own row: its instanceId, mapId and dungeonId stay floor 1's, as the table's do. A lookup by
 * instance (View) hands back a copy "seen from" that floor, with the floor's own instance, map and dungeon and its
 * number, so code that means "this map" keeps working on every floor while code that means "the run" reads `id`.
 *
 * Header-only and templated over the run type so that the harness in tests/rift_floors compiles the production book
 * with the production Rift (dc_rifts.h). Needs of Run: id, instanceId, mapId, dungeonId, floor.
 *
 * No locking here: every caller holds riftMutex (dc_rifts_internal.h).
 */

#ifndef DC_RIFT_FLOORS_H
#define DC_RIFT_FLOORS_H

#include <algorithm>
#include <cstdint>
#include <set>
#include <unordered_map>
#include <vector>

namespace DC::Rifts
{
    struct Floor
    {
        std::uint64_t runId = 0;
        unsigned number = 0; // 1 is where the run starts
        std::uint32_t instanceId = 0, mapId = 0, dungeonId = 0;
    };

    template<class Run>
    class LiveRuns
    {
    public:
        // A run begins: it is stored as it is, and its own instance, map and dungeon are floor 1.
        Run& Start(Run const& run)
        {
            Entry& entry = runs[run.id];
            entry.run = run;
            entry.run.floor = 1;
            entry.highest = 1;
            entry.used = {run.mapId};
            entry.floors.assign(1, Floor{run.id, 1, run.instanceId, run.mapId, run.dungeonId});
            byInstance[run.instanceId] = run.id;
            return entry.run;
        }

        // The run's own row (floor 1's identity), null when the run is not live.
        Run* Find(std::uint64_t runId)
        {
            auto found = runs.find(runId);
            return found == runs.end() ? nullptr : &found->second.run;
        }
        Run const* Find(std::uint64_t runId) const
        {
            auto found = runs.find(runId);
            return found == runs.end() ? nullptr : &found->second.run;
        }

        // The floor that is instance `instanceId` of map `mapId` (0: any map). The map is a guard: the core reuses
        // instance ids, and an id that now names another map is not this run's.
        Floor const* FloorAt(std::uint32_t instanceId, std::uint32_t mapId) const
        {
            auto at = byInstance.find(instanceId);
            if (at == byInstance.end())
                return nullptr;
            auto run = runs.find(at->second);
            if (run == runs.end())
                return nullptr;
            for (Floor const& floor : run->second.floors)
                if (floor.instanceId == instanceId && (!mapId || floor.mapId == mapId))
                    return &floor;
            return nullptr;
        }

        // The run as seen from one floor: a copy whose instance, map, dungeon and floor are that floor's.
        static Run Seen(Run const& run, Floor const& floor)
        {
            Run view = run;
            view.instanceId = floor.instanceId;
            view.mapId = floor.mapId;
            view.dungeonId = floor.dungeonId;
            view.floor = floor.number;
            return view;
        }

        // The run seen from the floor that is instance `instanceId` of map `mapId` (0: any map). False when no live
        // run has such a floor.
        bool View(std::uint32_t instanceId, std::uint32_t mapId, Run& out) const
        {
            Floor const* floor = FloorAt(instanceId, mapId);
            if (!floor)
                return false;
            out = Seen(runs.at(floor->runId).run, *floor);
            return true;
        }

        // The run's own row from the floor that is instance `instanceId` of map `mapId`; null when there is none.
        Run* FindByInstance(std::uint32_t instanceId, std::uint32_t mapId)
        {
            Floor const* floor = FloorAt(instanceId, mapId);
            return floor ? Find(floor->runId) : nullptr;
        }

        // The run seen from each of its floors, in floor order: one per floor still standing.
        std::vector<Run> Views(std::uint64_t runId) const
        {
            std::vector<Run> out;
            auto found = runs.find(runId);
            if (found != runs.end())
                for (Floor const& floor : found->second.floors)
                    out.push_back(Seen(found->second.run, floor));
            return out;
        }

        std::vector<Floor> Floors(std::uint64_t runId) const
        {
            auto found = runs.find(runId);
            return found == runs.end() ? std::vector<Floor>() : found->second.floors;
        }

        // A later floor of a live run. Returns its number, 0 when the run is not live. The number is one above the
        // highest the run has had, so a number is never given twice even after a floor is gone.
        unsigned AddFloor(std::uint64_t runId, std::uint32_t instanceId, std::uint32_t mapId, std::uint32_t dungeonId)
        {
            auto found = runs.find(runId);
            if (found == runs.end())
                return 0;
            Entry& entry = found->second;
            unsigned const number = ++entry.highest;
            entry.floors.push_back(Floor{runId, number, instanceId, mapId, dungeonId});
            entry.used.insert(mapId);
            byInstance[instanceId] = runId;
            return number;
        }

        // A write-back of the run's own state from a copy. The identity (instance, map, dungeon, floor 1) is kept: a
        // copy seen from another floor must not move the run's row to that floor.
        void Store(Run const& copy)
        {
            Run* run = Find(copy.id);
            if (!run)
                return;
            std::uint32_t const instanceId = run->instanceId, mapId = run->mapId, dungeonId = run->dungeonId;
            *run = copy;
            run->instanceId = instanceId;
            run->mapId = mapId;
            run->dungeonId = dungeonId;
            run->floor = 1;
        }

        // What a destroyed map took with it.
        enum class Gone
        {
            Unknown, // no live run has such a floor (the map was not a rift's)
            Floor,   // the floor is dropped; the run has others standing and goes on
            TheRun,  // that was the run's last floor: the run is dropped too
        };

        // A floor's map is gone. Only that floor leaves the book, unless it was the run's last.
        Gone Remove(std::uint32_t instanceId, std::uint32_t mapId)
        {
            Floor const* floor = FloorAt(instanceId, mapId);
            if (!floor)
                return Gone::Unknown;
            std::uint64_t const runId = floor->runId;
            Entry& entry = runs.at(runId);
            Floor const gone = *floor; // the erase below invalidates `floor`
            entry.floors.erase(std::remove_if(entry.floors.begin(), entry.floors.end(),
                                              [&](Floor const& f) { return f.instanceId == gone.instanceId; }),
                               entry.floors.end());
            Unindex(gone);
            if (!entry.floors.empty())
                return Gone::Floor;
            runs.erase(runId);
            return Gone::TheRun;
        }

        // The highest floor number the run has had, standing or not: what the floor cap counts (rift floors 6.1).
        unsigned Highest(std::uint64_t runId) const
        {
            auto found = runs.find(runId);
            return found == runs.end() ? 0 : found->second.highest;
        }

        // Every map the run has had a floor on, standing or not: a run never uses one map twice (4.3).
        std::set<std::uint32_t> UsedMaps(std::uint64_t runId) const
        {
            auto found = runs.find(runId);
            return found == runs.end() ? std::set<std::uint32_t>() : found->second.used;
        }

        std::size_t FloorCount(std::uint64_t runId) const
        {
            auto found = runs.find(runId);
            return found == runs.end() ? 0 : found->second.floors.size();
        }

        // Every live run's own row, in no order.
        template<class Visit>
        void Each(Visit&& visit) const
        {
            for (auto const& [id, entry] : runs)
                visit(entry.run);
        }

        void Clear()
        {
            runs.clear();
            byInstance.clear();
        }

        std::size_t Size() const
        {
            return runs.size();
        }

        // Instances indexed: one per floor standing, or the index leaks an entry for every map ever made.
        std::size_t IndexSize() const
        {
            return byInstance.size();
        }

    private:
        struct Entry
        {
            Run run;
            std::vector<Floor> floors;
            unsigned highest = 1;
            std::set<std::uint32_t> used;
        };

        void Unindex(Floor const& floor)
        {
            auto at = byInstance.find(floor.instanceId);
            if (at != byInstance.end() && at->second == floor.runId)
                byInstance.erase(at);
        }

        std::unordered_map<std::uint64_t, Entry> runs;
        std::unordered_map<std::uint32_t, std::uint64_t> byInstance;
    };
} // namespace DC::Rifts

#endif // DC_RIFT_FLOORS_H
