// The real dc_corpses_math.h: which deaths leave a corpse, the cap, the lifetime and the nearest-first take. Nothing is
// typed in from a sheet: the cap and the lifetime are the caller's, here small numbers that make each rule visible.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "combat/dc_corpses_math.h"

#include <cstdio>
#include <initializer_list>

using namespace DC::Combat::Corpses;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

static Spot At(float x, float y, std::uint32_t entry = 0, float z = 0, std::uint64_t body = 0)
{
    Spot spot;
    spot.x = x;
    spot.y = y;
    spot.z = z;
    spot.entry = entry;
    spot.body = body;
    return spot;
}

static bool Is(std::vector<Spot> const& spots, std::initializer_list<std::uint64_t> bodies)
{
    if (spots.size() != bodies.size())
        return false;
    std::size_t i = 0;
    for (std::uint64_t body : bodies)
        if (spots[i++].body != body)
            return false;
    return true;
}

int main()
{
    // Which deaths leave a corpse: a monster does; a player and a player's own pet, guardian or charmed unit do not.
    Victim monster;
    monster.creature = true;
    expect(Leaves(monster), "a monster leaves a corpse");
    Victim player;
    expect(!Leaves(player), "a player leaves none");
    Victim pet = monster;
    pet.controlledByPlayer = true;
    expect(!Leaves(pet), "a player's pet leaves none");

    std::uint64_t const life = 1000;

    // A corpse is kept and counted at the edge of its reach, not past it; the ground distance ignores height.
    {
        Pile pile;
        expect(pile.Leave(At(10, 0), 0, 5, life), "a corpse is kept");
        expect(pile.Size() == 1, "one corpse lies", double(pile.Size()), 1);
        expect(pile.Count(0, 0, 10, 0, life) == 1, "the edge of the reach counts");
        expect(pile.Count(0, 0, 9.99f, 0, life) == 0, "past the reach does not");
        Pile flyer;
        flyer.Leave(At(0, 0, 0, 40), 0, 5, life);
        expect(flyer.Count(0, 0, 1, 0, life) == 1, "a corpse high above the ground is in reach");
    }

    // The cap: the sixth corpse of a cap of five pushes the oldest out; a cap of nothing keeps none.
    {
        Pile pile;
        for (int i = 0; i < 5; ++i)
            pile.Leave(At(float(i), 0, 100 + i), std::uint64_t(i), 5, life);
        expect(pile.Size() == 5, "a full pile holds the cap", double(pile.Size()), 5);
        expect(pile.Leave(At(5, 0, 105), 5, 5, life), "a corpse past the cap is still kept");
        expect(pile.Size() == 5, "past the cap the pile stays at the cap", double(pile.Size()), 5);
        auto taken = pile.Take(0, 0, 100, 10, 5, life);
        expect(taken.size() == 5 && taken.front().entry == 101 && taken.back().entry == 105, "the oldest corpse went",
               taken.size() ? taken.front().entry : 0, 101);
        Pile none;
        expect(!none.Leave(At(0, 0), 0, 0, life), "a cap of nothing keeps no corpse");
        expect(none.Size() == 0, "and the pile is empty");
        Pile lowered;
        for (int i = 0; i < 4; ++i)
            lowered.Leave(At(float(i), 0), 0, 9, life);
        lowered.Leave(At(9, 0), 0, 2, life);
        expect(lowered.Size() == 2, "a cap lowered since trims the pile", double(lowered.Size()), 2);
    }

    // The lifetime: a corpse is there until it has lain for the lifetime, then gone; a lifetime of nothing keeps none.
    {
        Pile pile;
        pile.Leave(At(0, 0), 100, 5, life);
        expect(pile.Count(0, 0, 5, 100 + life - 1, life) == 1, "a corpse lasts to the last millisecond");
        expect(pile.Count(0, 0, 5, 100 + life, life) == 0, "a corpse is gone at its lifetime");
        expect(pile.Size() == 0, "and is out of the pile");
        Pile none;
        expect(!none.Leave(At(0, 0), 0, 5, 0), "a lifetime of nothing keeps no corpse");
        Pile old;
        old.Leave(At(0, 0), 0, 5, life);
        old.Leave(At(1, 0), life, 5, life);
        expect(old.Size() == 1, "a new corpse clears the expired ones", double(old.Size()), 1);
        Pile early;
        early.Leave(At(0, 0), 500, 5, life);
        expect(early.Count(0, 0, 5, 400, life) == 1, "a clock behind the corpse does not expire it");
    }

    // The take: nearest first, the older of a tie first, up to the maximum, out of the pile.
    {
        Pile pile;
        pile.Leave(At(8, 0, 1), 0, 9, life);
        pile.Leave(At(3, 0, 2), 1, 9, life);
        pile.Leave(At(0, 5, 3), 2, 9, life);  // 5 away
        pile.Leave(At(0, -3, 4), 3, 9, life); // 3 away, newer than entry 2
        pile.Leave(At(60, 0, 5), 4, 9, life);
        auto taken = pile.Take(0, 0, 20, 3, 10, life);
        expect(taken.size() == 3, "up to the maximum is taken", double(taken.size()), 3);
        expect(taken.size() == 3 && taken[0].entry == 2 && taken[1].entry == 4 && taken[2].entry == 3,
               "nearest first, the older of a tie first", taken.size() ? taken[0].entry : 0, 2);
        expect(pile.Size() == 2, "what was taken is out of the pile", double(pile.Size()), 2);
        expect(pile.Count(0, 0, 100, 10, life) == 2, "the rest is still there");
        auto rest = pile.Take(0, 0, 20, 10, 10, life);
        expect(rest.size() == 1 && rest[0].entry == 1, "the far corpse past the radius stays", rest.size(), 1);
        expect(pile.Take(0, 0, 20, 0, 10, life).empty(), "a maximum of nothing takes nothing");
        expect(pile.Take(0, 0, 100, 10, 10, life).size() == 1 && pile.Size() == 0, "a wider reach takes the last one");
        expect(pile.Take(0, 0, 100, 10, 10, life).empty(), "an empty pile takes nothing");
    }

    // The taken corpse is measured from the centre given, not from the owner.
    {
        Pile pile;
        pile.Leave(At(100, 100, 7), 0, 9, life);
        expect(pile.Count(0, 0, 11, 0, life) == 0, "a corpse far from the caster is out of its reach");
        expect(pile.Count(95, 100, 11, 0, life) == 1, "and in reach of a target area beside it");
    }

    // A corpse that is a dead body: the pile holds the body's guid, and a corpse that leaves without being taken hands its
    // body back, once, so the production half removes the body with it.
    {
        Pile pile;
        pile.Leave(At(0, 0, 1, 0, 11), 0, 2, life);
        pile.Leave(At(1, 0, 1, 0, 12), 1, 2, life);
        expect(pile.Released().empty(), "nothing has left the pile yet");
        pile.Leave(At(2, 0, 1, 0, 13), 2, 2, life);
        expect(Is(pile.Released(), {11}), "the cap pushed out the oldest, and its body is handed back");
        expect(pile.Released().empty(), "and handed back once");
        expect(pile.Size() == 2 && pile.Holds(12) && pile.Holds(13) && !pile.Holds(11), "the pile holds the other two bodies");
    }
    {
        Pile pile;
        pile.Leave(At(0, 0, 1, 0, 21), 100, 5, life);
        pile.Leave(At(1, 0, 1, 0, 22), 600, 5, life);
        expect(pile.Count(0, 0, 5, 100 + life, life) == 1, "the first corpse expired");
        expect(Is(pile.Released(), {21}), "the expired corpse hands back its body");
        pile.Sweep(600 + life, life);
        expect(pile.Size() == 0 && Is(pile.Released(), {22}), "a sweep expires the rest with no one asking");
    }
    {
        Pile pile;
        pile.Leave(At(0, 0, 1, 0, 31), 0, 5, life);
        pile.Leave(At(1, 0, 1, 0, 32), 1, 5, life);
        expect(!pile.Leave(At(2, 0, 1, 0, 33), 2, 0, life), "a cap lowered to nothing keeps none");
        expect(Is(pile.Released(), {31, 32}), "and the two lying hand back their bodies, not the one refused");
    }
    {
        Pile pile;
        pile.Leave(At(0, 0, 1, 0, 41), 0, 5, life);
        auto taken = pile.Take(0, 0, 10, 5, 1, life);
        expect(Is(taken, {41}), "a take hands the spot with its body to the caller");
        expect(pile.Released().empty(), "a taken corpse is not also released");
    }
    {
        Pile pile;
        pile.Leave(At(0, 0, 1, 0, 51), 0, 9, life);
        pile.Leave(At(1, 0, 1, 0, 52), 1, 9, life);
        pile.Leave(At(2, 0, 7), 2, 9, life); // a corpse a skill made: no body
        pile.Prune([](Spot const&) { return true; });
        expect(pile.Size() == 1 && !pile.Holds(0), "every body is gone: its claims go, the corpse with no body stays");
        expect(pile.Released().empty(), "a claim on a body that is gone is not handed back");
        Pile some;
        some.Leave(At(0, 0, 1, 0, 61), 0, 9, life);
        some.Leave(At(1, 0, 1, 0, 62), 1, 9, life);
        some.Leave(At(2, 0, 7), 2, 9, life); // a corpse a skill made: no body
        some.Prune([](Spot const& spot) { return spot.body == 61; });
        expect(some.Size() == 2 && some.Holds(62) && !some.Holds(61), "only the claim whose body is gone is dropped");
        auto bodies = some.Bodies();
        expect(bodies.size() == 1 && bodies[0] == 62, "the bodies held are listed");
    }

    // Used at will: the window is open until its end; a count finds at least the phantoms; a take is topped up to them.
    expect(AtWillNow(99, 100) && !AtWillNow(100, 100) && !AtWillNow(500, 100) && !AtWillNow(0, 0), "the window ends at its moment");
    expect(CountAtWill(3, false, 10) == 3, "without the window the real count stands");
    expect(CountAtWill(3, true, 10) == 10 && CountAtWill(0, true, 10) == 10, "with it a count finds the phantoms");
    expect(CountAtWill(14, true, 10) == 14, "and never fewer than the real corpses");
    expect(PhantomsFor(2, 5, true, 10) == 3, "a take of five that found two is topped up by three", PhantomsFor(2, 5, true, 10), 3);
    expect(PhantomsFor(2, 20, true, 10) == 8, "and is held to the phantoms", PhantomsFor(2, 20, true, 10), 8);
    expect(PhantomsFor(7, 5, true, 10) == 0 && PhantomsFor(10, 20, true, 10) == 0, "a take that found enough is not topped up");
    expect(PhantomsFor(2, 5, false, 10) == 0 && PhantomsFor(0, 5, true, 0) == 0, "no window or no phantoms, no corpse made");

    // A corpse a skill makes: the body is of the creature the skill names, else the stand-in.
    expect(BodyEntry(900152, 900153) == 900152 && BodyEntry(0, 900153) == 900153 && BodyEntry(0, 0) == 0, "a skill-made corpse's body is the creature the skill names, else the stand-in, never a dead monster's entry");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
