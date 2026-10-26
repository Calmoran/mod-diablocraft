/*
 * World of DiabloCraft - the spawner's picks (monster spawning S2, docs/proposals/monster-spawning.md 3.2 to 3.4, 3.8,
 * 3.9.2).
 *
 * What stands on a floor, decided and nothing else: the monster set, the anchors picked in each area, what stands at
 * each (a cluster, or a solo), the elite packs, the body cap. No summon, no map, no database: the module's glue
 * (dc_rift_spawner.cpp) fills the sheets from the world database and summons what the plan says, and
 * tests/rift_spawn compiles this header as it stands and feeds it the generated sheets.
 *
 * Every roll comes from one stream seeded by the run's seed and the floor number (Rng), taken in a fixed order, so a
 * floor can be replayed exactly from its seed (`.dc rift picks` prints it). A roll is always taken even when its answer
 * is already known (the solo share on a set with no solo monster), so the stream does not shift with the sheets.
 *
 * Header-only and std-only on purpose. A patrol (Part S5, 3.6) is a patrol-size cluster at a picked anchor that has a route: the
 * plan says which route and who is in it, and the glue walks the leader along the route's path. Wander is the glue's (S7).
 */

#ifndef DC_RIFT_SPAWN_H
#define DC_RIFT_SPAWN_H

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <initializer_list>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace DC::Rifts::Spawn
{
    // The four recipe roles (3.3) and the three cluster sizes. Identities of the plan's model, not tunables.
    enum Role : unsigned
    {
        Melee,
        Ranged,
        Caster,
        Big,
        RoleCount
    };
    // The three sizes an area's tag allows; a patrol's recipe is the fourth row of the recipe sheet, not a size an area can hold
    // (Patrol shares SizeCount's value on purpose: loops over SizeCount stay the three cluster sizes).
    enum Size : unsigned
    {
        Small,
        Medium,
        Large,
        SizeCount,
        Patrol = SizeCount
    };
    enum class Kind
    {
        Cluster,
        Solo,
        Patrol
    };
    enum class Elite
    {
        None,
        Champion,
        Rare
    };

    // The roster's role word by its first word, "summoner" counted as caster (3.3). False for a word that is none of
    // them.
    inline bool RoleOf(std::string word, Role& role)
    {
        word = word.substr(0, word.find_first_of("/ ,;"));
        std::transform(word.begin(), word.end(), word.begin(), [](unsigned char c) { return std::tolower(c); });
        if (word == "melee")
            role = Melee;
        else if (word == "ranged")
            role = Ranged;
        else if (word == "caster" || word == "summoner")
            role = Caster;
        else if (word == "big")
            role = Big;
        else
            return false;
        return true;
    }

    // One seeded stream (splitmix64): the same on every platform, which the standard distributions are not.
    class Rng
    {
    public:
        Rng(std::uint64_t seed, std::uint64_t floor)
            : _state(Mix(seed ^ Mix(floor + 0x9E3779B97F4A7C15ull)))
        {
        }
        std::uint64_t Next()
        {
            _state += 0x9E3779B97F4A7C15ull;
            return Mix(_state);
        }
        unsigned Below(unsigned n)
        {
            return n ? static_cast<unsigned>(Next() % n) : 0;
        }
        unsigned Between(unsigned lo, unsigned hi)
        {
            return hi <= lo ? lo : lo + Below(hi - lo + 1);
        }
        double Real()
        {
            return static_cast<double>(Next() >> 11) / 9007199254740992.0;
        }
        // The index picked by weight among the positive ones; weights that are all zero pick none (-1).
        int Weighted(std::vector<double> const& weights)
        {
            double total = 0;
            for (double w : weights)
                total += w > 0 ? w : 0;
            if (total <= 0)
                return -1;
            double at = Real() * total;
            int last = -1;
            for (std::size_t i = 0; i < weights.size(); ++i)
            {
                if (weights[i] <= 0)
                    continue;
                last = static_cast<int>(i);
                if (at < weights[i])
                    return last;
                at -= weights[i];
            }
            return last;
        }
        template<class T>
        void Shuffle(std::vector<T>& list)
        {
            for (std::size_t i = list.size(); i > 1; --i)
                std::swap(list[i - 1], list[Below(static_cast<unsigned>(i))]);
        }

    private:
        static std::uint64_t Mix(std::uint64_t z)
        {
            z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
            z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
            return z ^ (z >> 31);
        }
        std::uint64_t _state;
    };

    // --- the sheets (monster_sets.csv, cluster_recipes.csv, monster_spawn.csv, area_defaults.csv, rift_areas.csv,
    // rift_anchors.csv) ---

    struct Monster
    {
        std::string name, family;
        std::uint32_t entry = 0;
        Role role = Melee;
        bool solo = false;
        double wanderYards = 0;
    };
    struct SetFamily
    {
        std::string family;
        double weight = 1;
        bool clusterable = false; // the generator's word: the family has a melee or ranged member in the set
    };
    struct MonsterSet
    {
        unsigned id = 0;
        std::string name;
        double weight = 1;
        bool nephalem = true, greater = true;
        std::vector<unsigned> members; // indices into Sheets::monsters; only monsters that have a creature row
        std::vector<SetFamily> families;
    };
    struct Range
    {
        unsigned lo = 0, hi = 0;
    };
    struct Recipe
    {
        Range bodies, role[RoleCount];
    };
    struct AreaDefault
    {
        Range anchors;
        bool size[SizeCount] = {false, false, false};
    };
    struct Sheets
    {
        std::vector<Monster> monsters;
        std::vector<MonsterSet> sets;
        std::map<std::pair<unsigned, std::string>, Recipe> recipes; // (size, family); family "" is the size's own row
        AreaDefault defaults[3];                                    // S, M, L
    };

    struct Anchor
    {
        unsigned id = 0, area = 0;
        float x = 0, y = 0, z = 0, o = 0;
        bool hasWalk = false;
        double entryWalk = 0; // walking yards from the dungeon's entry point
    };
    struct Area
    {
        unsigned id = 0;
        char tag = 'S';
        bool hasDensity = false;
        Range density;
        bool nospawn = false;
    };
    // A route a patrol can walk (dc_rift_route): a stock waypoint_data path id, tied by the survey (or by a recording) to
    // the anchor nearest its first point. x, y, z is that first point, where the patrol's leader is put.
    struct Route
    {
        std::uint32_t path = 0;
        unsigned anchor = 0;
        float x = 0, y = 0, z = 0;
    };
    struct Survey
    {
        std::string name;
        std::vector<Area> areas;
        std::vector<Anchor> anchors;
        std::vector<Route> routes;
    };

    // The floor's knobs: rifts.csv rows (elite_chance_pct and its neighbours) and the pack sizes the elite code uses. A
    // blank placeholder arrives as 0: no body cap, nothing cleared at the entry.
    struct Knobs
    {
        double elitePct = 0, championPct = 50, soloPct = 0, patrolPct = 0, radiusSmallYards = 5, entryClearYards = 0, minSpacingYards = 0;
        unsigned eliteMin = 0, eliteMax = 0, bodyCap = 0;
        // What an elite pack brings, for the body count: a champion pack is championPack bodies; a rare is itself and at
        // most rareMinionsMax minions, times hordeMultiplier when it rolls Horde (the affix is rolled inside SpawnElitePack,
        // so the plan counts the most a rare can bring).
        unsigned championPack = 3, rareMinionsMax = 4, hordeMultiplier = 1;
    };

    inline int TagIndex(char tag)
    {
        return tag == 'S' ? 0 : tag == 'M' ? 1 : tag == 'L' ? 2 : -1;
    }

    // --- the picks
    // --------------------------------------------------------------------------------------------------------------

    // A monster set is usable when its mode switch is on and it can put something on the ground: a family that
    // clusters, or a solo.
    inline std::vector<unsigned> SoloPool(Sheets const& sheets, MonsterSet const& set)
    {
        std::vector<unsigned> pool;
        for (unsigned index : set.members)
        {
            Monster const& monster = sheets.monsters[index];
            bool clusters = false;
            for (SetFamily const& family : set.families)
                if (family.family == monster.family)
                    clusters = family.clusterable && family.weight > 0;
            if (monster.solo || !clusters)
                pool.push_back(index);
        }
        return pool;
    }
    inline bool CanCluster(MonsterSet const& set)
    {
        for (SetFamily const& family : set.families)
            if (family.clusterable && family.weight > 0)
                return true;
        return false;
    }
    inline bool Usable(Sheets const& sheets, MonsterSet const& set, bool greater)
    {
        return set.weight > 0 && (greater ? set.greater : set.nephalem) &&
               (CanCluster(set) || !SoloPool(sheets, set).empty());
    }

    // A floor's set, by weight among the usable ones, never the set of the floor before (rift floors 6.5). When that
    // set is the only usable one it is used again rather than leaving the floor empty. -1: no set is usable.
    inline int PickSet(Sheets const& sheets, bool greater, unsigned previousId, Rng& rng)
    {
        std::vector<double> weights(sheets.sets.size(), 0.0);
        bool other = false;
        for (std::size_t i = 0; i < sheets.sets.size(); ++i)
            if (Usable(sheets, sheets.sets[i], greater) && sheets.sets[i].id != previousId)
            {
                weights[i] = sheets.sets[i].weight;
                other = true;
            }
        if (!other)
            for (std::size_t i = 0; i < sheets.sets.size(); ++i)
                if (Usable(sheets, sheets.sets[i], greater))
                    weights[i] = sheets.sets[i].weight;
        return rng.Weighted(weights);
    }

    inline Recipe const* RecipeFor(Sheets const& sheets, Size size, std::string const& family)
    {
        auto found = sheets.recipes.find({size, family});
        if (found == sheets.recipes.end())
            found = sheets.recipes.find({size, std::string()});
        return found == sheets.recipes.end() ? nullptr : &found->second;
    }

    // 3.3 "Filling a cluster": a count per role rolled in its range; a role the family has no member for in this set
    // goes to the first role it does have (the stand-in table); melee is the filler that brings the total inside the
    // body range; each body is a random member of its role. A solo monster is never picked. Empty when the family has
    // nothing to fill it with or no recipe exists.
    inline std::vector<unsigned> BuildCluster(Sheets const& sheets, MonsterSet const& set, std::string const& family,
                                              Size size, Rng& rng)
    {
        Recipe const* recipe = RecipeFor(sheets, size, family);
        std::vector<unsigned> pool[RoleCount];
        for (unsigned index : set.members)
            if (sheets.monsters[index].family == family && !sheets.monsters[index].solo)
                pool[sheets.monsters[index].role].push_back(index);
        if (!recipe)
            return {};
        unsigned count[RoleCount];
        for (unsigned role = 0; role < RoleCount; ++role)
            count[role] = rng.Between(recipe->role[role].lo, recipe->role[role].hi);
        static unsigned const standIns[RoleCount][3] = {
            {Ranged, Big, Caster}, {Caster, Melee, Big}, {Ranged, Melee, Big}, {Melee, Ranged, Caster}};
        for (unsigned role = 0; role < RoleCount; ++role)
            if (pool[role].empty() && count[role])
                for (unsigned standIn : standIns[role])
                    if (!pool[standIn].empty())
                    {
                        count[standIn] += count[role];
                        count[role] = 0;
                        break;
                    }
        unsigned filler = RoleCount;
        for (unsigned role : {Melee, Ranged, Big, Caster})
            if (filler == RoleCount && !pool[role].empty())
                filler = role;
        if (filler == RoleCount)
            return {};
        auto total = [&] { return count[Melee] + count[Ranged] + count[Caster] + count[Big]; };
        while (total() < recipe->bodies.lo)
            ++count[filler];
        for (unsigned role : std::initializer_list<unsigned>{filler, Caster, Big, Ranged, Melee})
            while (total() > recipe->bodies.hi && count[role])
                --count[role];
        std::vector<unsigned> bodies;
        for (unsigned role = 0; role < RoleCount; ++role)
            for (unsigned i = 0; i < count[role]; ++i)
                bodies.push_back(pool[role].empty()
                                     ? pool[filler][rng.Below(static_cast<unsigned>(pool[filler].size()))]
                                     : pool[role][rng.Below(static_cast<unsigned>(pool[role].size()))]);
        rng.Shuffle(bodies);
        return bodies;
    }

    // 3.3 "Placing a cluster": the members' offsets from the anchor, random points within radius = small radius x
    // sqrt(bodies / 4) (uniform over the disc), never two on one spot: a point closer than `minSpacingYards` to one already
    // placed (or equal to it, whatever the spacing) is drawn again. The glue puts each on reachable ground.
    struct Spot
    {
        float dx = 0, dy = 0;
    };
    inline std::vector<Spot> SpotsFor(unsigned bodies, double radiusSmallYards, double minSpacingYards, Rng& rng)
    {
        std::vector<Spot> spots;
        double const radius = radiusSmallYards * std::sqrt(bodies / 4.0);
        // A safeguard, not a game number: a spacing the disc cannot hold ends with the last draw kept, as a cluster that
        // is too crowded for the sheet's spacing is still a cluster.
        constexpr unsigned DRAWS = 64;
        for (unsigned i = 0; i < bodies; ++i)
        {
            Spot spot;
            for (unsigned draw = 0; draw < DRAWS; ++draw)
            {
                double const r = radius * std::sqrt(rng.Real()), angle = rng.Real() * 6.283185307179586;
                spot = {static_cast<float>(r * std::cos(angle)), static_cast<float>(r * std::sin(angle))};
                bool free = true;
                for (Spot const& other : spots)
                {
                    double const gap = std::hypot(spot.dx - other.dx, spot.dy - other.dy);
                    free = free && gap > 0.0 && gap >= minSpacingYards;
                }
                if (free)
                    break;
            }
            spots.push_back(spot);
        }
        return spots;
    }

    struct Placement
    {
        unsigned anchor = 0; // Anchor::id
        std::uint32_t route = 0; // Kind::Patrol: the waypoint_data path the leader (monsters[0]) walks
        Kind kind = Kind::Cluster;
        Size size = Small;
        std::string family;
        std::vector<unsigned> monsters; // indices into Sheets::monsters; one for a solo
        std::vector<Spot> spots;        // one per monster
        Elite elite = Elite::None;
        unsigned leader = 0; // the monster the elite pack is made of
    };
    struct FloorPlan
    {
        int set = -1;
        std::vector<Placement> placements;
        unsigned clusters = 0, solos = 0, elitePacks = 0, bodies = 0, cutByCap = 0;
        unsigned patrols = 0; // of the clusters, the ones that walk a route
    };

    // Bodies a placement puts on the floor: a cluster or solo as placed, an elite pack as the elite code builds it, a rare at its most
    // (its minions at the top of their range, doubled by Horde).
    inline unsigned BodiesOf(Placement const& placement, Knobs const& knobs)
    {
        return placement.elite == Elite::Champion ? knobs.championPack
               : placement.elite == Elite::Rare   ? 1 + knobs.rareMinionsMax * std::max(1u, knobs.hordeMultiplier)
                                                  : static_cast<unsigned>(placement.monsters.size());
    }

    // 3.8 steps 2 to 7 for one floor of one dungeon, with the set already chosen. `rng` is the floor's stream (PickSet
    // drew from it first).
    inline FloorPlan PlanFloor(Sheets const& sheets, int setIndex, Survey const& dungeon, Knobs const& knobs, Rng& rng)
    {
        FloorPlan plan;
        plan.set = setIndex;
        if (setIndex < 0 || setIndex >= static_cast<int>(sheets.sets.size()))
            return plan;
        MonsterSet const& set = sheets.sets[setIndex];
        std::vector<unsigned> const solos = SoloPool(sheets, set);
        std::vector<double> familyWeights;
        for (SetFamily const& family : set.families)
            familyWeights.push_back(family.clusterable ? family.weight : 0.0);

        // 2. The areas: k anchors of each, none twice. Nothing at the door: no anchor within the entry clearance (an
        // unknown walk stays).
        struct Picked
        {
            Anchor const* anchor;
            char tag;
        };
        std::vector<Picked> picked;
        for (Area const& area : dungeon.areas)
        {
            if (area.nospawn || TagIndex(area.tag) < 0)
                continue;
            std::vector<Anchor const*> open;
            for (Anchor const& anchor : dungeon.anchors)
                if (anchor.area == area.id && !(anchor.hasWalk && anchor.entryWalk < knobs.entryClearYards))
                    open.push_back(&anchor);
            Range const density = area.hasDensity ? area.density : sheets.defaults[TagIndex(area.tag)].anchors;
            unsigned const k =
                std::min<unsigned>(rng.Between(density.lo, density.hi), static_cast<unsigned>(open.size()));
            rng.Shuffle(open);
            for (unsigned i = 0; i < k; ++i)
                picked.push_back({open[i], area.tag});
        }

        // 3 and 4. What stands at each picked anchor: a patrol by the patrol share when a route is tied to the anchor (3.6; no route
        // is made where the dungeon has none), else a solo by the solo share when the set has one, else a cluster. Both rolls are
        // always taken.
        for (std::size_t at = 0; at < picked.size(); ++at)
        {
            std::vector<Route const*> routes;
            for (Route const& route : dungeon.routes)
                if (route.anchor == picked[at].anchor->id)
                    routes.push_back(&route);
            bool const walks = rng.Real() * 100.0 < knobs.patrolPct && !routes.empty();
            bool const solo = rng.Real() * 100.0 < knobs.soloPct && !solos.empty();
            Placement placement;
            placement.anchor = picked[at].anchor->id;
            if (walks)
                placement.route = routes[rng.Below(static_cast<unsigned>(routes.size()))]->path;
            if (solo && !walks)
            {
                placement.kind = Kind::Solo;
                placement.monsters = {solos[rng.Below(static_cast<unsigned>(solos.size()))]};
                placement.family = sheets.monsters[placement.monsters[0]].family;
                placement.spots = {Spot{}};
            }
            else
            {
                AreaDefault const& rule = sheets.defaults[TagIndex(picked[at].tag)];
                std::vector<Size> sizes;
                for (unsigned size = 0; size < SizeCount; ++size)
                    if (rule.size[size])
                        sizes.push_back(static_cast<Size>(size));
                int const family = rng.Weighted(familyWeights);
                if ((sizes.empty() && !walks) || family < 0)
                    continue;
                placement.kind = walks ? Kind::Patrol : Kind::Cluster;
                placement.size = walks ? Patrol : sizes[rng.Below(static_cast<unsigned>(sizes.size()))];
                placement.family = set.families[family].family;
                placement.monsters = BuildCluster(sheets, set, placement.family, placement.size, rng);
                if (placement.monsters.empty())
                    continue;
                placement.spots =
                    SpotsFor(static_cast<unsigned>(placement.monsters.size()), knobs.radiusSmallYards, knobs.minSpacingYards, rng);
            }
            plan.placements.push_back(std::move(placement));
        }

        // 5. Elite packs (3.9.2): every cluster and patrol rolls the chance; the floor's minimum and maximum hold the count. A
        // cluster or patrol that turns elite is replaced by a champion or rare pack of one of its own monsters (a patrol's pack
        // walks the route). Solos never roll.
        std::vector<std::size_t> hits, misses;
        for (std::size_t i = 0; i < plan.placements.size(); ++i)
            if (plan.placements[i].kind != Kind::Solo)
                (rng.Real() * 100.0 < knobs.elitePct ? hits : misses).push_back(i);
        unsigned const high = knobs.eliteMax, low = std::min(knobs.eliteMin, high);
        rng.Shuffle(hits);
        rng.Shuffle(misses);
        while (hits.size() > high)
            hits.pop_back();
        while (hits.size() < low && !misses.empty())
        {
            hits.push_back(misses.back());
            misses.pop_back();
        }
        for (std::size_t index : hits)
        {
            Placement& placement = plan.placements[index];
            placement.elite = rng.Real() * 100.0 < knobs.championPct ? Elite::Champion : Elite::Rare;
            placement.leader = placement.monsters[rng.Below(static_cast<unsigned>(placement.monsters.size()))];
        }

        // 7. The cap, after the elite pass, because a pack is more bodies than the cluster it replaced: a floor stops adding
        // bodies at the cap, and the placements left after that are not placed.
        if (knobs.bodyCap)
        {
            unsigned total = 0;
            std::size_t keep = 0;
            for (; keep < plan.placements.size(); ++keep)
            {
                unsigned const bodies = BodiesOf(plan.placements[keep], knobs);
                if (total + bodies > knobs.bodyCap)
                    break;
                total += bodies;
            }
            plan.cutByCap = static_cast<unsigned>(plan.placements.size() - keep);
            plan.placements.resize(keep);
        }

        // The floor's body count: a cluster as placed, an elite pack as the elite code builds it (a rare's minions at their most).
        for (Placement const& placement : plan.placements)
        {
            plan.clusters += placement.kind != Kind::Solo;
            plan.patrols += placement.kind == Kind::Patrol;
            plan.solos += placement.kind == Kind::Solo;
            plan.elitePacks += placement.elite != Elite::None;
            plan.bodies += BodiesOf(placement, knobs);
        }
        return plan;
    }
} // namespace DC::Rifts::Spawn

#endif // DC_RIFT_SPAWN_H
