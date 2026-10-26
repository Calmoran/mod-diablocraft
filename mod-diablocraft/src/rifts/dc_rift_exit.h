/*
 * World of DiabloCraft - the exit portal and the next floor (rift floors Part F2,
 * docs/proposals/rift-floors.md 4.3, 4.4, 6.1, 6.2, 6.8, 6.12).
 *
 * The decisions with no core in them: which spot the exit stands on, which floor a click leads to and when it refuses,
 * which maps a new floor may roll, where the obelisk portal leads once floor 1 is gone, and the SQL of `.dc floor
 * exit`. No server types, so tests/rift_exit/harness.cpp compiles this very file; dc_rift_exit.cpp and dc_rifts.cpp are
 * the glue.
 *
 * Internal to the rifts folder.
 */

#ifndef DC_RIFT_EXIT_H
#define DC_RIFT_EXIT_H

#include "dc_rift_touchup.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace DC::Rifts::Exit
{
    // The exit portals wear the obelisk entrance's looks (6.12, rift_portals.csv), each on a template of its own so a
    // click runs the exit's code, and the template's name is "Floor N" for the floor the exit leads to (
    // the client reads the name from the template, so each floor led to has its own set). Look entry 910030 wearing the
    // exit to floor 2 is entry 910070, and so on through the 17 looks; floor 3 adds EXIT_FLOOR_STRIDE (generate_rifts.py
    // writes the templates from the same sheet and the rift_max_floors tunable; the test reads both). Constants:
    // identities, not game numbers. EXIT_LOOK_BLOCK is the thousand the entrance looks sit in (910030 to 910046).
    inline constexpr std::uint32_t EXIT_ENTRY_OFFSET = 40;
    inline constexpr std::uint32_t EXIT_FLOOR_STRIDE = 1000;
    inline constexpr std::uint32_t EXIT_LOOK_BLOCK = 910000;

    // The entry of the exit that wears `lookEntry` and leads to floor `leadsTo` (2 or more; the exit of floor 1 leads to 2).
    inline std::uint32_t ExitEntry(std::uint32_t lookEntry, unsigned leadsTo)
    {
        return lookEntry + EXIT_ENTRY_OFFSET + EXIT_FLOOR_STRIDE * (leadsTo > 2 ? leadsTo - 2 : 0);
    }

    // The look an exit entry wears; 0 when the entry is not in the exit blocks.
    inline std::uint32_t LookOf(std::uint32_t exitEntry)
    {
        if (exitEntry < EXIT_LOOK_BLOCK + EXIT_ENTRY_OFFSET)
            return 0;
        std::uint32_t const inBlock = (exitEntry - EXIT_LOOK_BLOCK) % EXIT_FLOOR_STRIDE;
        return inBlock >= EXIT_ENTRY_OFFSET ? EXIT_LOOK_BLOCK + inBlock - EXIT_ENTRY_OFFSET : 0;
    }

    struct Spot
    {
        double x = 0, y = 0, z = 0, o = 0;
    };

    // 6.2: where this dungeon's exit was placed by hand; where none was, the survey's far point.
    inline std::optional<Spot> ChooseSpot(std::optional<Spot> alex, std::optional<Spot> survey)
    {
        return alex ? alex : survey;
    }

    // What a click on an exit does not do, said to the player. None: go on.
    enum class Refusal
    {
        None,
        Closed,    // the run has closed
        Guardian,  // the Guardian has spawned: no new floor opens (4.3 item 6)
        LastFloor, // the run has opened as many floors as it may (6.1)
        NoMap,     // every map the pool has was used by this run (4.3 item 2)
    };

    // A click on the exit of a floor that has no floor after it standing. `highest` is the highest floor number the run
    // has had, `cap` is rift_max_floors, `maps` how many pool maps the run has not used.
    inline Refusal MayOpenNext(std::string const& state, std::uint32_t guardianInstance, unsigned highest, unsigned cap,
                               std::size_t maps)
    {
        if (state == "closed")
            return Refusal::Closed;
        if (guardianInstance || state == "guardian" || state == "complete")
            return Refusal::Guardian;
        if (highest >= cap)
            return Refusal::LastFloor;
        if (!maps)
            return Refusal::NoMap;
        return Refusal::None;
    }

    inline char const* Say(Refusal why)
    {
        switch (why)
        {
            case Refusal::Closed:
                return "That rift has closed.";
            case Refusal::Guardian:
                return "The Rift Guardian has appeared: no new floor opens.";
            case Refusal::LastFloor:
                return "This is the last floor of the rift.";
            case Refusal::NoMap:
                return "The rift has no floor left to open.";
            default:
                return "";
        }
    }

    // The floor a click leads to when one stands: the lowest number above this floor's (floors unload one by one, so
    // the next number may be gone). 0 when none stands. `standing` is in no order.
    inline unsigned NextStanding(std::vector<unsigned> standing, unsigned current)
    {
        unsigned next = 0;
        for (unsigned number : standing)
            if (number > current && (!next || number < next))
                next = number;
        return next;
    }

    // Where the obelisk portal leads (6.8): floor 1; when floor 1 has unloaded, the lowest floor still standing. 0:
    // none.
    inline unsigned ObeliskFloor(std::vector<unsigned> const& standing)
    {
        unsigned lowest = 0;
        for (unsigned number : standing)
            if (!lowest || number < lowest)
                lowest = number;
        return lowest;
    }

    // The pool rows (by index) whose map the run has not used: a run never uses one map twice, because the core keeps
    // one bind per map (4.3 item 2). Scarlet Monastery's Graveyard and Library share map 189.
    inline std::vector<std::size_t> EligibleMaps(std::vector<std::uint32_t> const& poolMaps,
                                                 std::set<std::uint32_t> const& used)
    {
        std::vector<std::size_t> out;
        for (std::size_t i = 0; i < poolMaps.size(); ++i)
            if (!used.count(poolMaps[i]))
                out.push_back(i);
        return out;
    }

    // `.dc floor exit here`: the dungeon's spot is where he stands, replacing an older one.
    inline std::string PlaceSql(std::string const& dungeon, Spot const& at)
    {
        return "REPLACE INTO `dc_rift_exit_spot` (`dungeon`, `x`, `y`, `z`, `o`) VALUES (" + TouchUp::Quote(dungeon) +
               ", " + TouchUp::Number(at.x) + ", " + TouchUp::Number(at.y) + ", " + TouchUp::Number(at.z) + ", " +
               TouchUp::Number(at.o) + ")";
    }

    // `.dc floor exit clear`: his spot goes; the survey's stays (dc_rift_exit_point is never edited here).
    inline std::string ClearSql(std::string const& dungeon)
    {
        return "DELETE FROM `dc_rift_exit_spot` WHERE `dungeon` = " + TouchUp::Quote(dungeon);
    }
} // namespace DC::Rifts::Exit

#endif // DC_RIFT_EXIT_H
