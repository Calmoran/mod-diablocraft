// Pylons and shrines Part P4 (diablocraft-0x640). Compiles the production decisions of dc_rift_pylon.h and drives them: the
// spots a floor may roll, the Nephalem plan (replay, caps, minimums, kinds by class and weight, the rate), the Greater Rift's
// chance, its limits and its per-spot roll, the fates of a buff when the player leaves the run or a Greater Rift starts, and the
// SQL of `.dc pylon spot`. argv[1] (optional): `add<TAB>dungeon<TAB>id x y z o`, `move<TAB>...` and `remove<TAB>dungeon<TAB>id`
// lines; the SQL of each is printed.
#include "dc_rift_pylon.h"

#include <cassert>
#include <cstdio>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Rifts;
using namespace DC::Rifts::Pylons;

static std::vector<Spot> Spots(unsigned n)
{
    std::vector<Spot> out;
    for (unsigned i = 1; i <= n; ++i)
        out.push_back(Spot{i, i, double(i), 0, 0, 0, 100.0 * i});
    return out;
}

static std::vector<Kind> Kinds(double fortune)
{
    std::vector<Kind> out;
    for (char const* p : {"power", "conduit", "channeling", "shield", "speed"})
        out.push_back(Kind{p, true, 1});
    for (char const* s : {"blessed", "empowered", "enlightened", "fleeting", "frenzied"})
        out.push_back(Kind{s, false, 1});
    out.push_back(Kind{"fortune", false, fortune});
    return out;
}

static std::vector<Placed> Plan(std::uint64_t seed, unsigned floor, std::vector<Spot> const& spots, std::vector<Kind> const& kinds,
                                NephalemKnobs const& knobs)
{
    Spawn::Rng rng = StreamOf(seed, floor);
    return PlanNephalem(spots, kinds, knobs, rng);
}

static std::string Show(std::vector<Placed> const& plan)
{
    std::ostringstream out;
    for (Placed const& p : plan)
        out << p.spot << ':' << p.kind << ' ';
    return out.str();
}

int main(int argc, char** argv)
{
    // 6.6: the entry clearance drops a spot whose walk is known and short; an unknown walk (the designer's) stays; 0 clears nothing.
    {
        std::vector<Spot> spots = {Spot{3, 0, 0, 0, 0, 0, 90}, Spot{1, 0, 0, 0, 0, 0, 10}, Spot{2, 0, 0, 0, 0, 0, -1}};
        assert(Usable(spots, 0).size() == 3);
        std::vector<Spot> kept = Usable(spots, 50);
        assert(kept.size() == 2 && kept[0].id == 2 && kept[1].id == 3); // id order, the short walk gone, the unknown kept
        assert(Usable(spots, 100).size() == 1 && Usable(spots, 100)[0].id == 2);
        assert(Usable({Spot{4, 0, 0, 0, 0, 0, 50}}, 50).size() == 1); // a walk equal to the clearance stays
    }

    std::vector<Spot> const spots = Spots(15);
    NephalemKnobs const knobs{5, 13, 0, 2, 0, 5};

    // A replayed seed places the same kinds at the same spots; another seed, another floor, or a changed sheet moves them.
    {
        std::string const a = Show(Plan(77, 1, spots, Kinds(0), knobs));
        assert(a == Show(Plan(77, 1, spots, Kinds(0), knobs)));
        unsigned different = 0;
        for (std::uint64_t seed = 1; seed <= 40; ++seed)
            different += Show(Plan(seed, 1, spots, Kinds(0), knobs)) != Show(Plan(seed + 1000, 1, spots, Kinds(0), knobs));
        assert(different > 30);
        unsigned floorsDiffer = 0;
        for (unsigned floor = 1; floor <= 20; ++floor)
            floorsDiffer += Show(Plan(77, floor, spots, Kinds(0), knobs)) != a;
        assert(floorsDiffer > 14);
    }

    // The plan's stream is not the spawner's: the same seed and floor give different first draws.
    assert(StreamOf(5, 1).Next() != Spawn::Rng(5, 1).Next());

    // Caps and minimums, on every seed: never more than the caps, never fewer than the minimums when the floor has room; one object
    // a spot; a pylon spot gets a pylon kind and a shrine spot a shrine kind.
    {
        NephalemKnobs all{100, 0, 0, 2, 0, 5};      // every spot rolls a pylon, at most 2 stand
        NephalemKnobs shrines{0, 100, 0, 2, 0, 5};  // every spot rolls a shrine, at most 5 stand
        NephalemKnobs topUp{0, 0, 2, 2, 3, 5};      // nothing rolls, 2 pylons and 3 shrines are the minimum
        NephalemKnobs mixed{60, 60, 0, 4, 0, 6};
        for (std::uint64_t seed = 1; seed <= 300; ++seed)
        {
            std::vector<Kind> const kinds = Kinds(1);
            auto count = [&](std::vector<Placed> const& plan, bool pylon)
            {
                unsigned n = 0;
                for (Placed const& p : plan)
                    n += kinds[p.kind].pylon == pylon;
                return n;
            };
            std::vector<Placed> const a = Plan(seed, 1, spots, kinds, all);
            assert(count(a, true) == 2 && count(a, false) == 0);
            std::vector<Placed> const b = Plan(seed, 1, spots, kinds, shrines);
            assert(count(b, false) == 5 && count(b, true) == 0);
            std::vector<Placed> const c = Plan(seed, 1, spots, kinds, topUp);
            assert(count(c, true) == 2 && count(c, false) == 3);
            std::vector<Placed> const d = Plan(seed, 2, spots, kinds, mixed);
            assert(count(d, true) <= 4 && count(d, false) <= 6);
            for (std::vector<Placed> const* plan : {&a, &b, &c, &d})
            {
                std::set<std::size_t> used;
                for (Placed const& p : *plan)
                    assert(used.insert(p.spot).second && p.spot < spots.size());
            }
        }
        // Fewer spots than the minimum: all of them are used and no more.
        assert(Plan(1, 1, Spots(2), Kinds(1), NephalemKnobs{0, 0, 5, 9, 0, 0}).size() == 2);
        // No spots, no objects.
        assert(Plan(1, 1, {}, Kinds(1), NephalemKnobs{100, 100, 3, 3, 3, 3}).empty());
    }

    // Kinds: Fortune's weight is the designer's; at 0 (blank) no Fortune Shrine ever stands, above 0 it does; the rest are even.
    {
        NephalemKnobs shrines{0, 100, 0, 15, 0, 15};
        unsigned fortuneAtZero = 0, fortuneAtOne = 0;
        std::vector<unsigned> seen(11, 0);
        for (std::uint64_t seed = 1; seed <= 400; ++seed)
        {
            for (Placed const& p : Plan(seed, 1, spots, Kinds(0), shrines))
                fortuneAtZero += p.kind == 10;
            for (Placed const& p : Plan(seed, 1, spots, Kinds(1), shrines))
            {
                fortuneAtOne += p.kind == 10;
                ++seen[p.kind];
            }
        }
        assert(fortuneAtZero == 0 && fortuneAtOne > 500);
        for (unsigned k = 5; k <= 10; ++k)
            assert(seen[k] > 800 && seen[k] < 1200); // 6000 shrines over 6 even kinds: about 1000 each
        for (unsigned k = 0; k < 5; ++k)
            assert(seen[k] == 0);
        // A class with no kind places none.
        std::vector<Kind> pylonsOnly = Kinds(1);
        pylonsOnly.resize(5);
        assert(Plan(1, 1, spots, pylonsOnly, NephalemKnobs{0, 100, 0, 0, 0, 15}).empty());
    }

    // The rate: 5% and 13% over 15 spots is 0.75 pylons and 1.95 shrines a floor; measured over many seeds.
    {
        double pylons = 0, shrineCount = 0;
        unsigned const floors = 4000;
        std::vector<Kind> const kinds = Kinds(1);
        for (std::uint64_t seed = 1; seed <= floors; ++seed)
            for (Placed const& p : Plan(seed, 1, spots, kinds, knobs))
                (kinds[p.kind].pylon ? pylons : shrineCount) += 1;
        assert(std::abs(pylons / floors - 0.75) < 0.1 && std::abs(shrineCount / floors - 1.95) < 0.2);
    }

    // The Greater Rift's chance: base after the last pylon, a straight line to 100 at the full share since then.
    {
        GreaterKnobs g; // 1, 50, 75, 4
        assert(GreaterChancePct(0, 0, g) == 1);
        assert(std::abs(GreaterChancePct(25, 0, g) - 50.5) < 1e-9);
        assert(GreaterChancePct(50, 0, g) == 100 && GreaterChancePct(80, 0, g) == 100);
        assert(GreaterChancePct(40, 30, g) == 1 + 99.0 * 10 / 50); // 10% since the last pylon, which stood at 30%
        assert(GreaterChancePct(30, 40, g) == 1);                   // never below the base
        g.fullAtPct = 0;
        assert(GreaterChancePct(0, 0, g) == 100);
    }

    // The limits: the Guardian ends the rolling (its state, or its instance), four a run is the most, a closed run rolls nothing.
    {
        GreaterKnobs g;
        RunHad had;
        assert(MayRoll("open", 0, had, g) == NoRoll::None);
        assert(MayRoll("guardian", 0, had, g) == NoRoll::Guardian && MayRoll("complete", 0, had, g) == NoRoll::Guardian);
        assert(MayRoll("closed", 0, had, g) == NoRoll::Guardian && MayRoll("open", 9, had, g) == NoRoll::Guardian);
        had.count = 3;
        assert(MayRoll("open", 0, had, g) == NoRoll::None);
        had.count = 4;
        assert(MayRoll("open", 0, had, g) == NoRoll::Full);
        g.maxPerRun = 2;
        had.count = 2;
        assert(MayRoll("open", 0, had, g) == NoRoll::Full);
        assert(MayRoll("guardian", 0, had, g) == NoRoll::Guardian); // the Guardian is the first answer
    }

    // A run never holds a shrine, never a kind twice, never a fifth pylon (and never a sixth, when the cap is raised past the kinds).
    {
        GreaterKnobs g;
        std::vector<Kind> const kinds = Kinds(1);
        for (std::uint64_t seed = 1; seed <= 200; ++seed)
        {
            RunHad had;
            unsigned spot = 0;
            while (MayRoll("open", 0, had, g) == NoRoll::None && spot < 60)
            {
                int const pick = RollGreater(seed, 1, ++spot, 100, kinds, had);
                assert(pick >= 0 && kinds[pick].pylon);
                assert(std::find(had.kinds.begin(), had.kinds.end(), kinds[pick].name) == had.kinds.end());
                had.kinds.push_back(kinds[pick].name);
                ++had.count;
            }
            assert(had.count == 4 && had.kinds.size() == 4);
            assert(spot == 4);
        }
        // With the cap at 9 the five pylon kinds run out: a sixth never rolls.
        RunHad had;
        for (unsigned i = 0; i < 5; ++i)
        {
            int const pick = RollGreater(1, 1, 10 + i, 100, kinds, had);
            assert(pick >= 0);
            had.kinds.push_back(kinds[pick].name);
        }
        assert(RollGreater(1, 1, 99, 100, kinds, had) == -1);
        // Chance 0 never stands; chance 100 always does; a replay gives the same answer; the kind does not depend on the chance.
        RunHad none;
        unsigned stood = 0;
        for (unsigned spotId = 1; spotId <= 400; ++spotId)
        {
            assert(RollGreater(7, 2, spotId, 0, kinds, none) == -1);
            assert(RollGreater(7, 2, spotId, 100, kinds, none) >= 0);
            assert(RollGreater(7, 2, spotId, 30, kinds, none) == RollGreater(7, 2, spotId, 30, kinds, none));
            int const at30 = RollGreater(7, 2, spotId, 30, kinds, none);
            stood += at30 >= 0;
            if (at30 >= 0)
                assert(at30 == RollGreater(7, 2, spotId, 100, kinds, none));
        }
        assert(stood > 90 && stood < 150); // 30% of 400
        // Another floor of the run rolls its spots on a stream of its own.
        unsigned same = 0;
        for (unsigned spotId = 1; spotId <= 100; ++spotId)
            same += RollGreater(7, 1, spotId, 100, kinds, none) == RollGreater(7, 2, spotId, 100, kinds, none);
        assert(same < 60);
    }

    // Ruling 2026-10-11 (decisions 1551ce0e): no two placed objects nearer than pylon_min_spacing_yd, both rift kinds.
    {
        std::vector<Spot> line; // 15 spots 10 yards apart
        for (unsigned i = 1; i <= 15; ++i)
            line.push_back(Spot{i, i, 10.0 * i, 0, 0, 0, 100.0 * i});
        auto spaced = [&](std::vector<Placed> const& plan, double yards)
        {
            for (Placed const& a : plan)
                for (Placed const& b : plan)
                    if (a.spot != b.spot && Distance(line[a.spot], line[b.spot]) < yards)
                        return false;
            return true;
        };
        std::vector<Kind> const kinds = Kinds(1);
        unsigned crowdedWithout = 0;
        for (std::uint64_t seed = 1; seed <= 300; ++seed)
        {
            // Nephalem, at the roll: every hit nearer than 60 yards to an earlier one is skipped.
            assert(spaced(Plan(seed, 1, line, kinds, NephalemKnobs{40, 40, 0, 99, 0, 99, 60}), 60));
            crowdedWithout += !spaced(Plan(seed, 1, line, kinds, NephalemKnobs{40, 40, 0, 99, 0, 99, 0}), 60);
            // and at the top-up: a minimum the spacing cannot meet stops short (150 yards hold 3 at 60 apart).
            std::vector<Placed> const top = Plan(seed, 1, line, kinds, NephalemKnobs{0, 0, 3, 9, 3, 9, 60});
            assert(spaced(top, 60) && top.size() <= 3 && !top.empty());
        }
        assert(crowdedWithout > 250); // 0 keeps nothing apart: the check above has teeth
        // Exactly the minimum apart is not crowded.
        std::vector<Spot> const two = {Spot{1, 1, 0, 0, 0}, Spot{2, 2, 60, 0, 0}};
        assert(Plan(3, 1, two, kinds, NephalemKnobs{100, 0, 0, 9, 0, 9, 60}).size() == 2);
        assert(Plan(3, 1, two, kinds, NephalemKnobs{100, 0, 0, 9, 0, 9, 60.5}).size() == 1);

        // Greater Rift: a hit near a placed object is dropped and nothing is stored (the chance keeps rising); away from it, it stands.
        GreaterKnobs g;
        g.minSpacing = 60;
        std::vector<Spot> placed = {Spot{1, 0, 0, 0, 0}};
        Spot const near{2, 0, 30, 0, 0}, far{3, 0, 200, 0, 0};
        RunHad had;
        had.shareAtLast = 10;
        assert(ApproachGreater(5, 1, near, 60, g, kinds, placed, had) == -1);
        assert(had.count == 0 && had.kinds.empty() && had.shareAtLast == 10);
        assert(GreaterChancePct(60, had.shareAtLast, g) == 100); // still the chance since the last pylon, not reset
        int const stood = ApproachGreater(5, 1, far, 60, g, kinds, placed, had);
        assert(stood >= 0 && kinds[stood].pylon && had.count == 1 && had.kinds.size() == 1 && had.shareAtLast == 60);
        // Without the minimum, the near spot stands; a miss (chance 0, the base after the last pylon) stores nothing either.
        g.minSpacing = 0;
        RunHad open;
        assert(ApproachGreater(5, 1, near, 60, g, kinds, placed, open) >= 0 && open.count == 1);
        GreaterKnobs never;
        never.baseChancePct = 0;
        never.fullAtPct = 1e9;
        RunHad none;
        assert(ApproachGreater(5, 1, far, 0, never, kinds, placed, none) == -1 && none.count == 0);
    }

    // The approach: within the radius, inclusive, in three dimensions.
    {
        Spot const s{1, 0, 100, 100, 10, 0, 5};
        assert(Within(s, 100, 175, 10, 75) && !Within(s, 100, 175.1, 10, 75) && !Within(s, 100, 100, 85.1, 75) && Within(s, 100, 100, 10, 0));
    }

    // 6.11: a pylon buff ends when the player leaves the run (Speed keeps all but its knock-up); a shrine buff outlasts that and a
    // Greater Rift clears it; a pylon buff is not touched when a Greater Rift starts (it ended on the way out of the last run).
    // Arriving on a map: off the rift floors is leaving the run, a Greater Rift floor ends the shrines, another floor nothing.
    assert(Leaving(false, false) == Leaves::LeftRun && Leaving(false, true) == Leaves::LeftRun);
    assert(Leaving(true, true) == Leaves::GreaterRift && !Leaving(true, false));
    {
        // The plan's tests: a pylon buff crosses a floor and ends in town, keeping Speed's speed; a shrine buff lasts through
        // town and is gone in a new Greater Rift; a pylon buff crosses a Greater Rift's floors.
        auto fate = [](bool pylon, bool speed, bool onFloor, bool greater)
        {
            std::optional<Leaves> const when = Leaving(onFloor, greater);
            return when ? FateOf(pylon, speed, *when) : Fate::Keeps;
        };
        assert(fate(true, false, true, false) == Fate::Keeps && fate(true, false, false, false) == Fate::Ends);
        assert(fate(true, true, false, false) == Fate::EndsKnockOnly);
        assert(fate(false, false, false, false) == Fate::Keeps && fate(false, false, true, true) == Fate::Ends);
        assert(fate(true, false, true, true) == Fate::Keeps);
    }
    assert(FateOf(true, false, Leaves::LeftRun) == Fate::Ends);
    assert(FateOf(true, true, Leaves::LeftRun) == Fate::EndsKnockOnly);
    assert(FateOf(false, false, Leaves::LeftRun) == Fate::Keeps);
    assert(FateOf(false, false, Leaves::GreaterRift) == Fate::Ends);
    assert(FateOf(true, false, Leaves::GreaterRift) == Fate::Keeps && FateOf(true, true, Leaves::GreaterRift) == Fate::Keeps);

    // `.dc pylon spot`: the nearest spot within NEAR_YARDS (a move or a removal), the next number, and the SQL.
    {
        std::vector<Spot> rows = {Spot{4, 1, 0, 0, 0}, Spot{9, 2, 10, 0, 0}, Spot{2, 3, 40, 0, 0}};
        assert(NextSpotId(rows) == 10 && NextSpotId({}) == 1);
        assert(NearestSpot(rows, 8, 0, 0) == 1 && NearestSpot(rows, 1, 0, 0) == 0 && NearestSpot(rows, 25, 0, 0) == -1);
        assert(NearestSpot(rows, 40, 0, NEAR_YARDS) == 2 && NearestSpot(rows, 40, 0, NEAR_YARDS + 0.1) == -1);
        assert(NearestSpot({}, 0, 0, 0) == -1);
    }
    if (argc >= 2)
    {
        std::ifstream in(argv[1]);
        std::string line;
        while (std::getline(in, line))
        {
            std::istringstream fields(line);
            std::string verb, dungeon;
            std::getline(fields, verb, '\t');
            std::getline(fields, dungeon, '\t');
            if (verb == "remove")
            {
                unsigned id;
                fields >> id;
                std::printf("%s\n", RemoveSql(dungeon, id).c_str());
                continue;
            }
            unsigned id;
            Spot at;
            fields >> id >> at.x >> at.y >> at.z >> at.o;
            std::printf("%s\n", (verb == "add" ? AddSql(dungeon, id, at) : MoveSql(dungeon, id, at)).c_str());
        }
    }
    std::puts("rift pylon harness: ok");
    return 0;
}
