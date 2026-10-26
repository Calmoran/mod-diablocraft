/*
 * World of DiabloCraft - Electrocute's jumps: the rules, with no core dependency, so
 * scripts/tests/classes/test_wizard_electrocute_jumps.py compiles this exact header and drives it. The walk itself is
 * Wizard::Jumps (dc_wizard_electrocute.cpp).
 */

#ifndef DC_WIZARD_CHAIN_H
#define DC_WIZARD_CHAIN_H

#include <cstddef>
#include <string_view>
#include <vector>

namespace DC::Combat::Wizard::Chain
{
    // How many enemies the bolt jumps to after the first. The skill's sheet number is the additional enemies ("hitting
    // up to {target_count} additional enemies", wizard_skills.csv; Power/Wizard_Electrocute.pow SF_13 'Base: Num of
    // Targets' 3, the first and 2); Chain Lightning's is the most enemies electrocuted ("Increase the maximum number of
    // enemies that can be electrocuted to {target_count}", wizard_runes.csv; SF_9 'B: Max Number of Targets' 10, the
    // first and 9). Lightning Blast's streaks pierce and Arc Lightning is a cone: neither jumps (wizard_runes.csv).
    inline unsigned JumpCount(std::string_view rune, double targetCount)
    {
        if (rune == "Lightning Blast" || rune == "Arc Lightning" || targetCount < 1)
            return 0;
        return unsigned(rune == "Chain Lightning" ? targetCount - 1 : targetCount);
    }

    // One enemy in jump range of the enemy the bolt is on: how far from it, whether the bolt has hit it already and
    // whether it is that enemy.
    struct Candidate
    {
        double distance = 0;
        bool hit = false;
        bool current = false;
    };

    // The next jump: the nearest candidate the bolt has not hit; with `mayRehit` (Myken's Ball of Hate, "Electrocute can
    // chain to enemies already hit") the nearest one already hit, never the one it is on, only when no fresh enemy is in
    // reach. -1 when none is left.
    inline int Next(std::vector<Candidate> const& candidates, bool mayRehit)
    {
        int fresh = -1, again = -1;
        for (std::size_t i = 0; i < candidates.size(); ++i)
        {
            Candidate const& c = candidates[i];
            if (c.current)
                continue;
            int& best = c.hit ? again : fresh;
            if (best < 0 || c.distance < candidates[best].distance)
                best = int(i);
        }
        return fresh >= 0 ? fresh : (mayRehit ? again : -1);
    }

    // The walk: from `first`, `jumps` times or until none is left, to Next of the enemies `near(on)` names within jump
    // range of the one it is on (`distance(a, b)` apart). The enemies jumped to, in order; `first` is not among them.
    template<class Unit, class Near, class Distance>
    std::vector<Unit> Walk(Unit first, unsigned jumps, bool mayRehit, Near near, Distance distance)
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
                candidates.push_back({distance(on, unit), seen, unit == on});
            }
            int const next = Next(candidates, mayRehit);
            if (next < 0)
                break;
            on = around[std::size_t(next)];
            hit.push_back(on);
            out.push_back(on);
        }
        return out;
    }
} // namespace DC::Combat::Wizard::Chain

#endif
