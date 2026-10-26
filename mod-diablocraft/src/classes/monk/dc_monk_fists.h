#pragma once
// Fists of Thunder's rules that need no core type, header-only so
// tests/monk_fists compiles this exact code. The three-hit combo, the window that keeps it alive, the
// share each enemy of the third hit gets and the cone "in front of you".
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk
{
    // One counter per skill, shared by all its runes (docs/research/monk/fists-of-thunder-rules.md section 4).
    // d3planner simulator monk.js:7-23 (GenSequence): a punch inside the window of the last one is the next
    // stage; the third punch, or a window that ran out, starts the combo again at stage 1.
    struct Combo
    {
        unsigned count = 0;          // punches of the running combo already thrown (0, 1 or 2)
        std::uint64_t expires = 0;   // ms: after this the combo is over

        // One punch at `now`; `windowMs` keeps the combo alive after it. Returns the stage of this punch, 1 to 3.
        unsigned Advance(std::uint64_t now, std::uint64_t windowMs)
        {
            if (now > expires)
                count = 0;
            unsigned const stage = count + 1;
            if (stage < 3)
            {
                count = stage;
                expires = now + windowMs;
            }
            else
                count = 0;
            return stage;
        }
    };

    // ceil(frames / attacks per second) frames of `fps`, in ms (monk.js:12: Math.ceil(72 / aps) at 60 frames a second).
    inline std::uint64_t ComboWindowMs(double frames, double fps, double attacksPerSecond)
    {
        if (frames <= 0 || fps <= 0 || attacksPerSecond <= 0)
            return 0;
        return static_cast<std::uint64_t>(std::ceil(frames / attacksPerSecond) / fps * 1000.0 + 0.5);
    }

    // "dealing {damage_pct} weapon damage ... split between all enemies in front of you": the total is shared.
    inline double SplitPct(double totalPct, unsigned enemies)
    {
        return enemies ? totalPct / enemies : 0.0;
    }
} // namespace DC::Combat::Monk
