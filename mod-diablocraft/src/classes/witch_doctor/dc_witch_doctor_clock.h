#pragma once
// The clock the Witch Doctor's timed loops run on, header-only so the harnesses of the skills that use it compile this exact code: a
// clock that has run so long is given more, and says how many whole intervals fell due; what a timed effect has left and returns a tick.

#include <algorithm>

namespace DC::Combat::WitchDoctor
{
    // A clock that has run `clock` ms and is given `diff` more: how many whole `interval`s are due, the rest left in `clock`. No interval, none
    // due; never more than `cap` at once.
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

    // The seconds a timed effect has left after a tick of `tickSeconds`; it does not go below nothing.
    inline double Left(double leftSeconds, double tickSeconds)
    {
        return std::max(0.0, leftSeconds - std::max(0.0, tickSeconds));
    }

    // What an effect returns in one tick of `tickSeconds` when it returns `perSecond` a second.
    inline double PerTick(double perSecond, double tickSeconds)
    {
        return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;
    }
} // namespace DC::Combat::WitchDoctor
