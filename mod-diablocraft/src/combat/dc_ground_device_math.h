#pragma once
// The rules of a ground device that need no core type, header-only so tests/ground_device compiles this exact code: how many of a
// kind may stand, when a device is armed, when it fires and when it is gone. The production half is dc_ground_device.cpp. No class
// or skill is named here: a skill fills a Spec from its sheet and says how its device fires.
#include <algorithm>
#include <cmath>
#include <cstddef>

namespace DC::Combat::GroundDevice
{
    // How a device is fired once it is armed.
    //   Proximity: the first time an enemy stands within the radius it fires once and is gone.
    //   Command:   it stays dormant until it is detonated from outside (Detonate), and is gone when it has fired.
    //   Periodic:  every interval, while an enemy stands within the radius, it fires; it goes only when its life is over.
    enum class Mode
    {
        Proximity,
        Command,
        Periodic
    };

    struct Spec
    {
        Mode mode = Mode::Proximity;
        double radiusYards = 0;   // the distance an enemy must be within (Proximity, Periodic); the area a firing reaches
        double armMs = 0;         // it fires nothing before it has stood this long
        double lifetimeMs = 0;    // it is gone this long after it was placed (0: it stands until it fires or its owner leaves)
        double intervalMs = 0;    // Periodic: the time between firings
        std::size_t most = 0;     // the most of its kind one owner has standing at once (0: no limit)
    };

    struct State
    {
        double age = 0;        // ms since it was placed
        double sinceCheck = 0; // ms since the last look for an enemy (Proximity)
        double sinceShot = 0;  // ms the next firing has been waited for (Periodic)
    };

    struct Outcome
    {
        unsigned fires = 0; // how many times it fired this step
        bool gone = false;  // it is to be taken away
    };

    // Laying one more when `placed` of the kind stand with room for `most`: how many of the oldest give way so that no more than `most` stand.
    // No limit stated, none give way.
    inline std::size_t Overflow(std::size_t placed, std::size_t most)
    {
        return most > 0 && placed >= most ? placed - most + 1 : 0;
    }

    inline bool Armed(State const& state, Spec const& spec)
    {
        return state.age >= spec.armMs;
    }

    // A clock that has run `clock` ms and is given `diff` more: how many whole `interval`s are due, the rest left in `clock`. No interval, none
    // due and the clock cleared; never more than `cap` at once.
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

    // One step of a device that has been given `diff` ms. `lookEveryMs` is how often a Proximity device looks for an enemy. `enemyNear` is asked
    // only when the answer decides something (a device not yet armed, or one with nothing due, never asks) and says whether an enemy stands
    // within the radius. A Command device never fires here. The device is gone when its life is over, after it has had this step's firings, and
    // after a Proximity device has fired.
    template <class Near>
    inline Outcome Advance(State& state, Spec const& spec, double diff, double lookEveryMs, Near&& enemyNear)
    {
        Outcome out;
        state.age += diff;
        bool const armed = Armed(state, spec);
        if (spec.mode == Mode::Proximity)
        {
            unsigned const looks = Due(state.sinceCheck, diff, lookEveryMs);
            if (armed && looks && enemyNear())
            {
                out.fires = 1;
                out.gone = true;
            }
        }
        else if (spec.mode == Mode::Periodic)
        {
            if (!armed || spec.intervalMs <= 0)
                state.sinceShot = 0;
            else
            {
                state.sinceShot += diff;
                if (state.sinceShot >= spec.intervalMs && enemyNear())
                {
                    out.fires = std::min(40u, static_cast<unsigned>(state.sinceShot / spec.intervalMs));
                    state.sinceShot -= out.fires * spec.intervalMs;
                    if (state.sinceShot >= spec.intervalMs)
                        state.sinceShot = 0; // a backlog past the cap is dropped, not paid out later
                }
                else if (state.sinceShot >= spec.intervalMs)
                    state.sinceShot = spec.intervalMs; // ready, and waiting for an enemy: the first shot comes the moment one stands there
            }
        }
        if (spec.lifetimeMs > 0 && state.age >= spec.lifetimeMs)
            out.gone = true;
        return out;
    }

    // Whether a dormant device can be detonated now: a Command device that is armed.
    inline bool Detonable(State const& state, Spec const& spec)
    {
        return spec.mode == Mode::Command && Armed(state, spec);
    }
} // namespace DC::Combat::GroundDevice
