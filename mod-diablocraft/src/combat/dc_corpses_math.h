#pragma once
// The rules of the corpses a kill leaves, with no core type, so tests/corpses compiles this exact code: which deaths
// leave one, how many a player keeps and for how long, and which of them a skill takes first. A corpse is the dead
// monster's own stock body where it fell: the record here is the player's claim on that body (its guid), and the body goes
// when the last claim on it is spent, expires or is pushed out. A corpse a skill makes gets a stock dead body of its own, made where
// it lies. A corpse gives no progress and no loot of its own. The production half is dc_corpses.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>

namespace DC::Combat::Corpses
{
    // Where a corpse lies and what stood there (a creature entry; 0 for a corpse a skill made on purpose), and the guid
    // of the dead body it is (0 when there is none: a corpse a skill made).
    struct Spot
    {
        float x = 0, y = 0, z = 0;
        std::uint32_t entry = 0;
        std::uint64_t body = 0;
    };

    struct Corpse
    {
        Spot spot;
        std::uint64_t leftAtMs = 0;
    };

    // The creature whose stock body a skill-made corpse is: the one the skill names (inert by its own template), else the
    // stand-in (the combat tunable skill_corpse_body_entry). Never the entry of a monster that died.
    inline std::uint32_t BodyEntry(std::uint32_t skillBody, std::uint32_t standIn)
    {
        return skillBody ? skillBody : standIn;
    }

    // What a death is, to the rule of leaving a corpse.
    struct Victim
    {
        bool creature = false; // a monster; a player never leaves one
        bool controlledByPlayer =
            false; // a pet, guardian, totem or charmed unit: the skills that mean to leave one say so
    };

    inline bool Leaves(Victim const& victim)
    {
        return victim.creature && !victim.controlledByPlayer;
    }

    // The distance along the ground: the radii of the skills (11 yards, 60 yards) are circles on the floor, so the
    // height a flyer died at does not push its corpse out of reach.
    inline double GroundDistance(Spot const& spot, float x, float y)
    {
        return std::hypot(double(spot.x) - x, double(spot.y) - y);
    }

    // Corpse skills used at will (a class's window in which no corpse is needed): the corpses a request is met with. A request
    // for a count finds at least `phantoms` while the window is open; a take that found fewer than it asked for, up to `phantoms`,
    // is topped up with corpses made on the spot.
    inline bool AtWillNow(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    inline std::size_t CountAtWill(std::size_t real, bool atWill, std::size_t phantoms)
    {
        return atWill ? std::max(real, phantoms) : real;
    }

    inline std::size_t PhantomsFor(std::size_t taken, std::size_t max, bool atWill, std::size_t phantoms)
    {
        std::size_t const wanted = std::min(max, phantoms);
        return atWill && wanted > taken ? wanted - taken : 0;
    }

    // One player's corpses, oldest first. A cap or a lifetime of nothing keeps no corpse at all, so a number nobody has
    // chosen yet leaves none rather than a corpse that never ends.
    class Pile
    {
    public:
        // The corpse is kept unless the cap or the lifetime is nothing; past the cap the oldest corpse goes. True when
        // kept.
        bool Leave(Spot const& at, std::uint64_t nowMs, std::size_t cap, std::uint64_t lifetimeMs)
        {
            Expire(nowMs, lifetimeMs);
            if (cap == 0 || lifetimeMs == 0)
            {
                Release(corpses_.begin(), corpses_.end());
                corpses_.clear();
                return false;
            }
            corpses_.push_back({at, nowMs});
            if (corpses_.size() > cap)
            {
                auto const pushedOut = corpses_.begin() + std::ptrdiff_t(corpses_.size() - cap);
                Release(corpses_.begin(), pushedOut);
                corpses_.erase(corpses_.begin(), pushedOut);
            }
            return true;
        }

        // Expires what has lain for the lifetime; the production half calls it on a timer so a body does not outlast its
        // corpse.
        void Sweep(std::uint64_t nowMs, std::uint64_t lifetimeMs)
        {
            Expire(nowMs, lifetimeMs);
        }

        // Drops every corpse `gone` says has no body any more (the body decayed or was taken by something else).
        // They are not released: there is no body left to remove.
        template <class Gone>
        void Prune(Gone gone)
        {
            corpses_.erase(std::remove_if(corpses_.begin(), corpses_.end(), [&](Corpse const& corpse)
                                          { return corpse.spot.body != 0 && gone(corpse.spot); }),
                           corpses_.end());
        }

        // The corpses that left the pile without being taken (expired, pushed out by the cap, kept none) since this was
        // last asked, each once: the claims whose bodies the production half removes.
        std::vector<Spot> Released()
        {
            std::vector<Spot> out;
            out.swap(released_);
            return out;
        }

        // Every body the pile holds a claim on.
        std::vector<std::uint64_t> Bodies() const
        {
            std::vector<std::uint64_t> out;
            for (Corpse const& corpse : corpses_)
                if (corpse.spot.body != 0)
                    out.push_back(corpse.spot.body);
            return out;
        }

        bool Holds(std::uint64_t body) const
        {
            return body != 0 && std::any_of(corpses_.begin(), corpses_.end(),
                                            [&](Corpse const& corpse) { return corpse.spot.body == body; });
        }

        // How many corpses lie within `radius` yards of (x, y), counting the edge.
        std::size_t Count(float x, float y, float radius, std::uint64_t nowMs, std::uint64_t lifetimeMs)
        {
            Expire(nowMs, lifetimeMs);
            return std::size_t(std::count_if(corpses_.begin(), corpses_.end(), [&](Corpse const& corpse)
                                             { return GroundDistance(corpse.spot, x, y) <= radius; }));
        }

        // Up to `max` corpses within `radius` yards of (x, y), nearest first (the older of two at one distance), taken
        // out of the pile.
        std::vector<Spot> Take(float x, float y, float radius, std::size_t max, std::uint64_t nowMs,
                               std::uint64_t lifetimeMs)
        {
            Expire(nowMs, lifetimeMs);
            std::vector<std::size_t> near;
            for (std::size_t i = 0; i < corpses_.size(); ++i)
                if (GroundDistance(corpses_[i].spot, x, y) <= radius)
                    near.push_back(i);
            std::stable_sort(near.begin(), near.end(),
                             [&](std::size_t a, std::size_t b) {
                                 return GroundDistance(corpses_[a].spot, x, y) < GroundDistance(corpses_[b].spot, x, y);
                             });
            if (near.size() > max)
                near.resize(max);
            std::vector<Spot> taken;
            for (std::size_t i : near)
                taken.push_back(corpses_[i].spot);
            std::sort(near.begin(), near.end(), std::greater<std::size_t>());
            for (std::size_t i : near)
                corpses_.erase(corpses_.begin() + std::ptrdiff_t(i));
            return taken;
        }

        std::size_t Size() const
        {
            return corpses_.size();
        }

    private:
        // A corpse is gone once it has lain for the lifetime.
        void Expire(std::uint64_t nowMs, std::uint64_t lifetimeMs)
        {
            auto const expired = [&](Corpse const& corpse)
            { return nowMs >= corpse.leftAtMs && nowMs - corpse.leftAtMs >= lifetimeMs; };
            for (Corpse const& corpse : corpses_)
                if (expired(corpse))
                    released_.push_back(corpse.spot);
            corpses_.erase(std::remove_if(corpses_.begin(), corpses_.end(), expired), corpses_.end());
        }

        template <class Iterator>
        void Release(Iterator first, Iterator last)
        {
            for (; first != last; ++first)
                released_.push_back(first->spot);
        }

        std::vector<Corpse> corpses_;
        std::vector<Spot> released_;
    };
} // namespace DC::Combat::Corpses
