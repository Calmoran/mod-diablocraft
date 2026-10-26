/*
 * World of DiabloCraft - rift progress and the Greater Rift timer.
 *
 * The decisions with no core in them: what a kill is worth to the bar, what an orb is worth, which death
 * drops a pack's orbs, where the orbs of a pack lie, who may pick one up, and whether a Guardian kill beat the clock. The
 * hooks that read creatures, players and the live run are dc_gr_progress.cpp; this file is what the
 * test compiles. Internal to the rifts folder.
 */

#ifndef DC_GR_PROGRESS_H
#define DC_GR_PROGRESS_H

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Rifts::Gr
{
    // The bar is counted in hundredths of a D3 progress point (monster-spawning.md 3.9.4): the quest holds
    // 65,000 for the 650 points that fill it, which is inside the core's 16-bit quest counter, and warpath's
    // points have two decimals at most. A number that is negative, not a number or past the counter's reach
    // is nothing, never a loss of progress or a wrap.
    inline unsigned Hundredths(double points)
    {
        if (!(points > 0.0) || !std::isfinite(points))
            return 0;
        double const units = std::floor(points * 100.0 + 0.5);
        return units >= 4.0e9 ? 4000000000u : static_cast<unsigned>(units);
    }

    // What one kill adds: its monster's own points where the sheet has a row, else the default
    // (rifts/monster_progress_default_points, D3's median 1.0). A pack member, an elite and a normal monster
    // are all the same here: each gives its own monster's points (3.9.4).
    inline unsigned KillHundredths(bool hasRow, unsigned rowHundredths, unsigned defaultHundredths)
    {
        return hasRow ? rowHundredths : defaultHundredths;
    }

    // The bar after `units` more: capped at the whole bar (the quest's count), no wrap on a big sum.
    inline unsigned Filled(unsigned progress, unsigned units, unsigned requiredUnits)
    {
        return static_cast<unsigned>(std::min<std::uint64_t>(requiredUnits, static_cast<std::uint64_t>(progress) + units));
    }

    // One pack's head count, shared by its leader and every member, so the answer to "was that the
    // last of the pack?" never goes through the leader's corpse (it may be gone from the map by the
    // time the last member falls). A lone monster is a pack of one. A pack drops its orbs once.
    struct PackLife
    {
        unsigned living = 1;     // the creature that made it
        bool dropped = false;

        void Joined() { ++living; }
        // The pack's one drop: true the first time it is asked, never again.
        bool Drop()
        {
            if (dropped)
                return false;
            dropped = true;
            return true;
        }
        // One member died. True for the death that empties the pack, the first time only.
        bool Died()
        {
            if (living)
                --living;
            return !living && Drop();
        }
    };

    // Does this death drop its pack's orbs? Every death counts the head (Died), so the answer never depends on
    // whether it is asked. A pack drops when its last member falls, in both rift kinds (D3's
    // trigger for a Nephalem rare, the rare itself with its minions alive, is not followed).
    inline bool OrbsFall(PackLife& life)
    {
        return life.Died();
    }

    // The orbs one kind of pack drops in one mode: how many, and how much of the bar each is worth
    // (rifts.csv gr_orb_* and nr_orb_*). Counts that are negative or not a number are none.
    struct Orbs
    {
        unsigned count = 0, hundredths = 0;
    };
    inline Orbs OrbsFor(bool rare, double championCount, double rareCount, double points)
    {
        double const count = std::floor((rare ? rareCount : championCount) + 0.5);
        return {count > 0.0 && std::isfinite(count) ? (count >= 4.0e9 ? 4000000000u : static_cast<unsigned>(count)) : 0u,
                Hundredths(points)};
    }

    // The bar stops paying out once it is full or the run has left "open" (the Guardian is up).
    inline bool OrbsWanted(bool runOpen, unsigned progress, unsigned requiredUnits)
    {
        return runOpen && progress < requiredUnits;
    }

    // Where orb `index` of `count` lies: evenly round the body, `spread` yards out.
    struct Spot
    {
        float x = 0, y = 0;
    };
    inline Spot OrbSpot(unsigned index, unsigned count, float centreX, float centreY, float spread)
    {
        double const angle = count ? static_cast<double>(index) / count * 2.0 * 3.14159265358979323846 : 0.0;
        return {static_cast<float>(centreX + spread * std::cos(angle)),
                static_cast<float>(centreY + spread * std::sin(angle))};
    }

    // A player picks an orb up by walking within `radius` yards of it, edge included. A radius that
    // is not a positive number picks nothing up.
    inline bool WithinPickup(double distance, double radius)
    {
        return radius > 0.0 && std::isfinite(radius) && distance <= radius;
    }

    // 09-rifts 7.4: only a Guardian killed BEFORE 0:00 beats the rift. `now` and `deadline` are unix
    // seconds; a kill in the very second the clock reaches 0 is late.
    inline bool InTime(std::int64_t now, std::int64_t deadline)
    {
        return now < deadline;
    }

    // Whole seconds left on the clock, 0 once it has run out.
    inline unsigned TimeLeft(std::int64_t now, std::int64_t deadline)
    {
        return now < deadline ? static_cast<unsigned>(std::min<std::int64_t>(deadline - now, 4000000000ll)) : 0u;
    }

    // dc_rift.outcome for a Greater Rift, in the column's own words (rifts_0005): `success` is a
    // Guardian killed in time (beaten), `expired` is a run that lost its clock (failed).
    inline char const* OutcomeName(bool beaten)
    {
        return beaten ? "success" : "expired";
    }

    // The clock runs out on a run that has no result yet: it is failed from that second, whether or
    // not its Guardian ever dies. A run that already has a result keeps it.
    inline bool ExpiryDue(bool resultPending, std::int64_t now, std::int64_t deadline)
    {
        return resultPending && deadline > 0 && !InTime(now, deadline);
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_PROGRESS_H
