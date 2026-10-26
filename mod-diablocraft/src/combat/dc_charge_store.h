#pragma once
// A skill that stores charges ("you gain a charge every N seconds and can store up to M"), for any class: the rule that needs no core
// type, header-only so the harness of the skills that use it compiles this exact code. One charge recharges at a time, its period
// fixed when it starts, and the next starts as it lands. Kept lazily: the count catches up whenever it is read, so no tick is needed; while
// the count is 0 the cooldown on the skill's record holds the button, and it ends exactly when the next charge lands.
#include <algorithm>
#include <cstdint>

namespace DC::Combat
{
    struct ChargeStore
    {
        unsigned count = 0;
        bool known = false;     // a player starts full
        std::uint64_t next = 0; // ms the charge recharging now lands; 0 when none is
        std::uint64_t period = 0;

        // The count at `now` for a cap of `cap`; `periodMs` starts a recharge when one is owed and none is running.
        unsigned Refill(std::uint64_t now, unsigned cap, std::uint64_t periodMs)
        {
            if (!known)
            {
                count = cap;
                known = true;
            }
            while (next && now >= next && count < cap)
            {
                ++count;
                next = count < cap && period ? next + period : 0;
            }
            if (count >= cap)
            {
                count = cap;
                next = 0;
            }
            else if (!next)
            {
                period = periodMs;
                next = now + periodMs;
            }
            return count;
        }

        // A cast spends one charge. Returns the milliseconds the button must wait: 0 while a charge is left, else until the next lands.
        std::uint64_t Spend(std::uint64_t now, unsigned cap, std::uint64_t periodMs)
        {
            Refill(now, cap, periodMs);
            if (count)
                --count;
            Refill(now, cap, periodMs);
            return count ? 0 : next - now;
        }

        // The recharge under way is shortened by `ms` (a corpse consumed); one that would land by then lands now. Returns the wait as Spend does.
        std::uint64_t Shorten(std::uint64_t now, unsigned cap, std::uint64_t periodMs, std::uint64_t ms)
        {
            Refill(now, cap, periodMs);
            if (next)
                next = next > now + ms ? next - ms : now;
            Refill(now, cap, periodMs);
            return count ? 0 : next - now;
        }
    };
} // namespace DC::Combat
