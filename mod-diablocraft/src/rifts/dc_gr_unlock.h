/*
 * World of DiabloCraft - Greater Rift unlocks.
 *
 * The decisions with no core in them: how many levels a time left unlocks, and what one beaten
 * run does to a character's three numbers. The store that holds them is dc_gr_level.cpp, the run
 * that grants them dc_gr_progress.cpp; this file is what the test compiles. Internal to the
 * rifts folder.
 */

#ifndef DC_GR_UNLOCK_H
#define DC_GR_UNLOCK_H

#include <algorithm>

namespace DC::Rifts::Gr
{
    // The rows of the unlock chart: `minSeconds[i]` is the whole seconds a kill must still have left
    // for the bonus `i + 1` (greater_rifts.csv keystone_upgrade_rule: 4:30 or less +1 ... 12:01 or
    // more +10; rifts.csv gr_unlock_plus_N_min_seconds_left). The bonus is the highest row the time
    // left reaches, 0 when it reaches none (rows are tried in order, so the last one reached wins).
    inline unsigned UnlockBonus(unsigned secondsLeft, unsigned const* minSeconds, unsigned rows)
    {
        unsigned bonus = 0;
        for (unsigned i = 0; i < rows; ++i)
            if (secondsLeft >= minSeconds[i])
                bonus = i + 1;
        return bonus;
    }

    // One character's Greater Rift numbers: the highest level it may open, the highest it has beaten
    // in time (0 none) and the highest it has beaten alone (0 none; Torment VII to XVI read this).
    struct Reach
    {
        unsigned unlocked = 1, beaten = 0, beatenSolo = 0;
    };

    // What an in-time kill of `level` does: the character may open the beaten level plus the bonus,
    // never fewer than it could and never above `cap`; `beaten` rises to the level; `beatenSolo`
    // rises only when the run was solo. Nothing ever falls, so a repeat of the same call changes
    // nothing. A failed run does not reach this function at all.
    inline Reach Beat(Reach reach, unsigned level, unsigned bonus, bool solo, unsigned cap)
    {
        level = std::min(level, cap);
        reach.unlocked = std::max(reach.unlocked, std::min(cap, level + bonus));
        reach.beaten = std::max(reach.beaten, level);
        if (solo)
            reach.beatenSolo = std::max(reach.beatenSolo, level);
        return reach;
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_UNLOCK_H
