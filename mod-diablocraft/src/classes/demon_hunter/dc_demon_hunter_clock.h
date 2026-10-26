#pragma once
// The clock the Demon Hunter's timed loops run on, header-only so the harnesses of the skills that use it compile this exact
// code: a clock that has run so long is given more, and says how many whole intervals fell due.

namespace DC::Combat::DemonHunter
{
    // A clock that has run `clock` ms and is given `diff` more: how many whole `interval`s are due, the rest left in `clock`. No
    // interval, none due; never more than `cap` at once.
    inline unsigned Due(double& clock, double diff, double interval, unsigned cap = 40)
    {
        clock += diff;
        if (interval <= 0)
        {
            clock = 0;
            return 0;
        }
        unsigned due = 0;
        while (clock >= interval && due < cap)
        {
            clock -= interval;
            ++due;
        }
        if (clock >= interval)
            clock = 0;
        return due;
    }
} // namespace DC::Combat::DemonHunter
