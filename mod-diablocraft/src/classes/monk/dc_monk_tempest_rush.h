#pragma once
// Tempest Rush's rules that need no core type, header-only so tests/monk_tempest_rush
// compiles this exact code. The skill is a channel (Power/Monk_TempestRush.pow): it drains its Spirit cost every second
// in ticks and deals its weapon damage every second in ticks. Until the Monk has its own
// channel records, the module runs the channel itself from the instant cast, and the cast's own cost is the first
// second of it; this file's rules are the ones that move over to the channel loop unchanged.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <unordered_set>

namespace DC::Combat::Monk
{
    // A per-second number spread over ticks of `tickSeconds` (damage: 390% a second, cost: 30 Spirit a second).
    inline double PerTick(double perSecond, double tickSeconds)
    {
        return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;
    }

    // The seconds the press already paid: the instant cast costs one second of the channel, so ticks before `until` are
    // free.
    struct Prepaid
    {
        std::uint64_t until = 0;

        void Press(std::uint64_t now, std::uint64_t ms)
        {
            until = now + ms;
        }

        bool Covers(std::uint64_t now) const
        {
            return now < until;
        }
    };

    // Flurry: one stack for each attack period the channel has run, up to the cap (pow SF_34 'Weapon Damage Per Attack
    // Period', SF_36 'Max Stacks'); the explosion when it ends deals the stacks' share.
    inline unsigned FlurryStacks(double elapsedSeconds, double attacksPerSecond, unsigned cap)
    {
        if (elapsedSeconds <= 0 || attacksPerSecond <= 0)
            return 0;
        return unsigned(std::min<double>(cap, std::floor(elapsedSeconds * attacksPerSecond)));
    }

    // Bluster knocks each enemy back once for the whole channel: First is true the first time a guid is seen.
    struct Seen
    {
        std::unordered_set<std::uint64_t> guids;

        bool First(std::uint64_t guid)
        {
            return guids.insert(guid).second;
        }
    };
} // namespace DC::Combat::Monk
