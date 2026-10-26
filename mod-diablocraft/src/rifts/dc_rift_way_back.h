/*
 * World of DiabloCraft - the way back out of a rift floor (rift floors Part F4,
 * docs/proposals/rift-floors.md 4.5, 6.7).
 *
 * The decision with no core in it: where a dungeon's own way-out trigger leads a player standing in a live rift floor,
 * and when it refuses. No server types, so tests/rift_way_back/harness.cpp compiles this very file; dc_rift_exit.cpp is
 * the glue.
 *
 * Internal to the rifts folder.
 */

#ifndef DC_RIFT_WAY_BACK_H
#define DC_RIFT_WAY_BACK_H

#include <algorithm>
#include <string>
#include <vector>

namespace DC::Rifts::WayBack
{
    // The name the module's area trigger script registers; rifts_0022 binds each way-out trigger to it
    // (generate_rift_way_back.py, which test_rift_way_back.py reads against this one).
    inline constexpr char const* SCRIPT_NAME = "dc_rift_way_back";
    // A way-out trigger switched off in rifts (data/d3/rift_way_none.csv): in a live rift floor it does
    // nothing; anywhere else the stock teleport runs.
    inline constexpr char const* NONE_SCRIPT_NAME = "dc_rift_way_none";

    enum class Way
    {
        Up,   // to the exit portal of the floor above
        Hub,  // out of the rift, to the hub
        Shut, // a Greater Rift before its Guardian is dead: leaving would fail the member (09-rifts 7.9.2 item 7)
        Dead, // a ghost does not use it: the revive choices are the way out of death
    };

    struct Choice
    {
        Way way = Way::Hub;
        unsigned floor = 0; // Up: the floor number led to
    };

    // `floor` is the number of the floor the player stands on, `standing` the numbers of the run's floors that still
    // stand (floors unload one by one), `member` whether they are enrolled in this run, `greater` whether the run is a
    // Greater Rift, `state` the run's state (open | guardian | complete | closed).
    // Up a floor is not leaving the rift, so it is never shut; every way that ends in the hub is, in a Greater Rift
    // whose Guardian is not dead (4.5). A floor above that has unloaded leads to the hub (4.5), so that case is shut
    // there too. A player who is not a member of the run, and any player once the run has closed, simply leaves.
    inline Choice Choose(unsigned floor, bool alive, bool member, bool greater, std::string const& state,
                         std::vector<unsigned> const& standing)
    {
        if (!alive)
            return {Way::Dead, 0};
        bool const closed = state == "closed";
        if (member && !closed && floor > 1 && std::find(standing.begin(), standing.end(), floor - 1) != standing.end())
            return {Way::Up, floor - 1};
        if (member && greater && !closed && state != "complete")
            return {Way::Shut, 0};
        return {Way::Hub, 0};
    }

    inline std::string Say(Choice choice)
    {
        switch (choice.way)
        {
            case Way::Up:
                return "Back up to floor " + std::to_string(choice.floor) + ".";
            case Way::Hub:
                return "Leaving the rift. Returning you to the hub.";
            case Way::Shut:
                return "The Rift Guardian is not dead: leaving a Greater Rift now would fail you. Use a town portal to "
                       "leave on purpose.";
            default:
                return "Revive first: the way back is for the living.";
        }
    }
} // namespace DC::Rifts::WayBack

#endif // DC_RIFT_WAY_BACK_H
