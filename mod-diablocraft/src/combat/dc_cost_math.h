/*
 * World of DiabloCraft - the arithmetic a Fury cost still needs in the module.
 *
 * The spell record carries the cost and the core charges it, with
 * every reduction a SPELLMOD_COST aura, so the reduction arithmetic is
 * Player::ApplySpellMod's and none of it is copied here. What is left is the
 * unit conversion between the sheets' Fury and the record's Rage, the whole
 * percent a spell modifier can carry, and D3's Whirlwind channel model - the
 * one cost no stock field can hold.
 *
 * It is a header with no core dependency so the offline harness in
 * tests/cost_math can compile the real thing and measure what these
 * conversions cost in precision (scripts/tests/combat/test_cost_math.py).
 */

#ifndef DC_COST_MATH_H
#define DC_COST_MATH_H

#include "../classes/dc_resource_data.h"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::CostMath
{
    // Fury is stored at the class resource registry's scale (Rage units per
    // point, dc_resource_data.h), which is how every record's ManaCost was
    // written and how the client prints it.
    inline constexpr double RagePerFury = Resources::Data::Find("Barbarian", "fury")->scale;

    inline std::int32_t Rage(double fury)
    {
        return std::int32_t(std::llround(fury * RagePerFury));
    }

    inline double Fury(std::int32_t rage)
    {
        return std::max(0, rage) / RagePerFury;
    }

    // What a debit actually removes. The pool is integer Rage, so a Fury
    // amount is rounded to a tenth on its way in or out of it
    // (dc_combat.cpp's ChangeFury) - the module's channel tick charges this,
    // not the unrounded number, and scripts/tests/combat/test_cost_math.py measures it.
    inline double Charged(double fury)
    {
        return Fury(Rage(fury));
    }

    // A spell modifier carries whole percent, and a reduction is negative.
    // Rounding to the nearest is an accepted deviation of at most half a
    // percent of a cost.
    inline std::int32_t ModifierAmount(double percent)
    {
        return -std::int32_t(std::lround(std::clamp(percent, 0.0, 100.0)));
    }

    // N-COST (Aether Walker): a cost put on a skill that has none, `points` of the class resource at its registry `scale`, in whole units. A spell
    // modifier's flat amount is added to the record's cost (the core floors the total at 0), so it is positive.
    inline std::int32_t FlatAmount(double points, double scale)
    {
        return std::int32_t(std::llround(std::max(0.0, points) * std::max(0.0, scale)));
    }

    // A probe cost, in Rage units, large enough that the integer the core
    // hands back carries a reduction to a hundredth of a percent.
    inline constexpr std::int32_t COST_PROBE = 10000;

    // The same for a cooldown, in milliseconds. It is large for the same
    // reason and for one more: the core reduces a cooldown to a whole
    // millisecond, so a 30 second cooldown at 33 % measures 33.0033 and not
    // 33. The sheet is showing the modifiers, not one skill's rounding, so it
    // asks about a duration long enough that the millisecond does not show.
    inline constexpr std::int32_t COOLDOWN_PROBE = 1000000;

    inline double Factor(std::int32_t probed)
    {
        return std::clamp(double(probed) / COST_PROBE, 0.0, 1.0);
    }

    // D3's Whirlwind channel, out of d3planner simulator/barbarian.js:377-384
    // (`cost: function(rune) { var speed = Sim.stats.info[Sim.curweapon ||
    // "mainhand"].speed; return 7 / speed + 3; }`, with `channeling: 40`) and
    // cast.js:136-147 (`cost *= channeling / 60`), which is what
    // docs/research/d3-cost-cooldown-math.md reproduces:
    //
    //     cost = speedTerm / weapon_speed + flatTerm     Fury per SECOND
    //     cost *= channeling / 60                        one tick's share
    //
    // so the rate is what a reduction applies to, and the tick takes the
    // fraction of a second it covers. Both terms and both frame counts are
    // values-sheet rows; nothing here invents a number.
    inline double ChannelRate(double speedTerm, double flatTerm, double attacksPerSecond)
    {
        return attacksPerSecond > 0 ? speedTerm / attacksPerSecond + flatTerm : 0.0;
    }

    // The scaling of one tick's cost: the fraction of a second the tick's own
    // frame count covers, `cost *= channeling / 60`. It is the simulator's
    // scaling and stays the unrounded frame count, not the rounded interval
    // the tick is scheduled at.
    inline double CostScaleSeconds(double frames, double framesPerSecond)
    {
        return framesPerSecond > 0 ? frames / framesPerSecond : 0.0;
    }

    // The cadence, which is a different number. d3planner's simulator, read
    // at simulator/cast.js:504 and :508:
    //
    //     var rate = Math.floor(speed / info.speed);
    //     data.buff.params.tickrate = Math.floor(data.speed / info.speed);
    //
    // where that `speed` argument is the skill's `channeling` frame count
    // (cast.js:473, barbarian.js:401) and `info.speed` is attacks per second
    // (cast.js:438-440). So the tick is floor(frames / attacks) frames away:
    // 40 at one attack a second, 26 at 1.5. The second line is the same sum
    // run again on every tick, which is why the module reads the interval
    // fresh rather than caching it. (cast.js:491-495 states the identical
    // formula as Sim.channelDelay, which nothing calls; the live path is the
    // two lines above.)
    inline double ScheduleFrames(double frames, double attacksPerSecond)
    {
        return attacksPerSecond > 0 ? std::floor(frames / attacksPerSecond) : 0.0;
    }

    inline double ScheduleSeconds(double frames, double attacksPerSecond, double framesPerSecond)
    {
        return framesPerSecond > 0 ? ScheduleFrames(frames, attacksPerSecond) / framesPerSecond : 0.0;
    }

    // --- the Wizard's channels -------------
    // The third named module-paid exception, in Whirlwind's shape,
    // after d3planner's simulator at the
    // pin (d07RiV/d3planner@898918b). The cadence is ScheduleSeconds above.

    // One tick's cost in resource points: the percentage reduction first,
    // then channeling / 60 - the sheet's frame count, not the rounded
    // interval (simulator/cast.js:136-147). No attack-speed term, unlike
    // Whirlwind's.
    inline double ChannelTickCost(double cost, double reductionFactor, double frames, double framesPerSecond)
    {
        return cost * reductionFactor * CostScaleSeconds(frames, framesPerSecond);
    }

    // The per-second percentage after `elapsedSeconds` of channel: base plus
    // one ramp step per whole second, never past the sheet's max
    // (wizard.js:170, :276, :337 add min(bonus, 2) steps, which is the max
    // row for every one of the three).
    inline double ChannelRamp(double base, double ramp, double max, double elapsedSeconds)
    {
        return std::min(base + std::floor(elapsedSeconds) * ramp, max);
    }

    // What one tick carries of that per-second percentage. Ray of Frost and
    // Disintegrate scale by aps x tick frames / 60 (wizard.js:174, :338);
    // Arcane Torrent scales by channeling / 60 (wizard.js:323-325).
    inline double ChannelTickShare(double perSecond, double frames, double framesPerSecond, double attacksPerSecond,
                                   bool byChannelFrames)
    {
        if (framesPerSecond <= 0)
            return 0.0;
        if (byChannelFrames)
            return perSecond * frames / framesPerSecond;
        return perSecond * attacksPerSecond * ScheduleFrames(frames, attacksPerSecond) / framesPerSecond;
    }

    // Mana is whole points: a tick due `due` points (with what earlier ticks
    // left owing) takes the whole part and carries the fraction. Not paid -
    // the channel ends - when the pool is short of the whole amount due.
    struct Debit
    {
        bool paid = false;
        std::int32_t whole = 0;
        double owed = 0;
    };
    inline Debit PayWhole(double pool, double due)
    {
        Debit out;
        if (pool + 0.0001 < due)
            return out;
        out.paid = true;
        out.whole = std::int32_t(std::floor(due + 0.0001));
        out.owed = std::max(0.0, due - out.whole);
        return out;
    }
}

#endif // DC_COST_MATH_H
