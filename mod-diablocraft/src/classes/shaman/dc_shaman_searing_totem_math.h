#pragma once
// The rules of the Searing Totem's runes with no core include, so tests/shaman_searing_totem compiles them alone:
// Searing Flames' stacks and what they add, Frostflame's every-Nth freeze, Stoneclaw's damage taken and Capacitor's
// chain. dc_shaman_searing_totem.cpp is the player and creature side around them.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace DC::Combat::Shaman::Searing
{
    // The stacks of Searing Flames on one enemy and when they end.
    struct Flames
    {
        unsigned stacks = 0;
        std::uint64_t untilMs = 0;
    };

    inline std::uint64_t Millis(double seconds)
    {
        return seconds > 0 ? std::uint64_t(std::llround(seconds * 1000.0)) : 0;
    }

    // A bolt hits: one more stack, up to `most`, and the end of every stack moves to `seconds` from now. Stacks that
    // had ended start again at one.
    inline Flames Stack(Flames flames, std::uint64_t nowMs, unsigned most, double seconds)
    {
        if (flames.untilMs <= nowMs)
            flames.stacks = 0;
        flames.stacks = std::min(flames.stacks + 1, most);
        flames.untilMs = nowMs + Millis(seconds);
        return flames;
    }

    // The stacks on the enemy now.
    inline unsigned Live(Flames const& flames, std::uint64_t nowMs)
    {
        return flames.untilMs > nowMs ? flames.stacks : 0;
    }

    // "Each stack makes the target take N% more damage from your Fire skills": the percent more the stacks give.
    inline double MorePct(unsigned stacks, double perStackPct)
    {
        return perStackPct > 0 ? stacks * perStackPct : 0.0;
    }

    // Frostflame: "Every Nth bolt Freezes". Counts a bolt; true on the Nth, which starts the count again. No count, no
    // freeze.
    inline bool Freezes(unsigned& bolts, unsigned every)
    {
        if (!every)
        {
            bolts = 0;
            return false;
        }
        if (++bolts < every)
            return false;
        bolts = 0;
        return true;
    }

    // Stoneclaw: the factor on the damage the Shaman takes while the totem stands.
    inline double TakenFactorOf(double reductionPct)
    {
        return 1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0;
    }

    // Capacitor's chain: one enemy within reach of the one the bolt is on, how far from it and whether the bolt has
    // been on it.
    struct Candidate
    {
        double distance = 0;
        bool hit = false;
    };

    // The next enemy the bolt goes to: the nearest it has not been on. -1 when none is left.
    inline int Next(std::vector<Candidate> const& candidates)
    {
        int best = -1;
        for (std::size_t i = 0; i < candidates.size(); ++i)
            if (!candidates[i].hit && (best < 0 || candidates[i].distance < candidates[std::size_t(best)].distance))
                best = int(i);
        return best;
    }

    // The walk: from `first`, `jumps` times or until none is left, to Next of the enemies `near(on)` names within reach
    // of the one it is on
    // (`distance(a, b)` apart). The enemies jumped to, in order; `first` is not among them.
    template<class Unit, class Near, class Distance>
    std::vector<Unit> Walk(Unit first, unsigned jumps, Near near, Distance distance)
    {
        std::vector<Unit> out, hit{first};
        Unit on = first;
        while (out.size() < jumps)
        {
            std::vector<Unit> const around = near(on);
            std::vector<Candidate> candidates;
            for (Unit const& unit : around)
            {
                bool seen = false;
                for (Unit const& done : hit)
                    seen = seen || done == unit;
                candidates.push_back({distance(on, unit), seen});
            }
            int const next = Next(candidates);
            if (next < 0)
                break;
            on = around[std::size_t(next)];
            hit.push_back(on);
            out.push_back(on);
        }
        return out;
    }
} // namespace DC::Combat::Shaman::Searing
