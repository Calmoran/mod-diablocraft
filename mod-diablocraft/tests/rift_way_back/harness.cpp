// Rift floors Part F4 (diablocraft-o69g). Compiles the production decision of the way back (dc_rift_way_back.h) and drives it:
// where a dungeon's way-out trigger leads a player in a live rift floor, and when it refuses.
// `harness name` prints the scripts' names (the test reads it against generate_rift_way_back.py).
#include "dc_rift_way_back.h"

#include <cassert>
#include <cstdio>
#include <cstring>

using namespace DC::Rifts::WayBack;

int main(int argc, char** argv)
{
    if (argc > 1 && !std::strcmp(argv[1], "name"))
    {
        std::puts(SCRIPT_NAME);
        std::puts(NONE_SCRIPT_NAME);
        return 0;
    }
    std::vector<unsigned> const all{1, 2, 3};

    // A member of a Nephalem Rift goes up a floor; from floor 1 to the hub.
    assert(Choose(3, true, true, false, "open", all).way == Way::Up && Choose(3, true, true, false, "open", all).floor == 2);
    assert(Choose(2, true, true, false, "open", all).floor == 1);
    assert(Choose(1, true, true, false, "open", all).way == Way::Hub);
    // The floor above has unloaded: the hub, not the floor below that.
    assert(Choose(3, true, true, false, "open", {1, 3}).way == Way::Hub);
    assert(Choose(2, true, true, false, "open", {2}).way == Way::Hub);
    // The Guardian's states do not matter in a Nephalem Rift.
    for (char const* state : {"open", "guardian", "complete"})
        assert(Choose(1, true, true, false, state, all).way == Way::Hub);

    // A Greater Rift: up is never shut; the hub is shut until the Guardian is dead, floor 1 or an unloaded floor above.
    assert(Choose(3, true, true, true, "open", all).way == Way::Up);
    assert(Choose(2, true, true, true, "guardian", all).way == Way::Up);
    assert(Choose(1, true, true, true, "open", all).way == Way::Shut);
    assert(Choose(1, true, true, true, "guardian", all).way == Way::Shut);
    assert(Choose(1, true, true, true, "complete", all).way == Way::Hub);
    assert(Choose(3, true, true, true, "open", {1, 3}).way == Way::Shut);
    assert(Choose(3, true, true, true, "complete", {1, 3}).way == Way::Hub);

    // A closed run lets everybody out; the run is going anyway.
    assert(Choose(1, true, true, true, "closed", all).way == Way::Hub);
    assert(Choose(3, true, true, false, "closed", all).way == Way::Hub);
    // A player who is not a member of the run just leaves, a Greater Rift's floor 1 included.
    assert(Choose(1, true, false, true, "open", all).way == Way::Hub);
    assert(Choose(3, true, false, false, "open", all).way == Way::Hub);
    // The dead use nothing, whatever they are.
    for (bool member : {true, false})
        for (bool greater : {true, false})
            for (unsigned floor : {1u, 3u})
                assert(Choose(floor, false, member, greater, "complete", all).way == Way::Dead);

    for (Choice choice : {Choice{Way::Up, 2}, Choice{Way::Hub, 0}, Choice{Way::Shut, 0}, Choice{Way::Dead, 0}})
        assert(!Say(choice).empty());
    assert(Say(Choice{Way::Up, 2}).find('2') != std::string::npos);
    std::puts("rift way back harness: ok");
    return 0;
}
