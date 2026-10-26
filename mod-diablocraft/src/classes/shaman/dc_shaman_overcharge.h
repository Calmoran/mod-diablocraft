#pragma once
// The Shaman's Overcharge: Maelstrom generated at the maximum is banked, every `perStack` points of overflow is one
// stack up to a cap, the stacks last `ms` and the whole time restarts when a stack is gained, and the next Secondary
// skill spends every stack for a damage bonus per stack. The rule needs no core type, header-only so the harness in
// tests/shaman_overcharge compiles this exact code. The state and the wiring are dc_shaman_overcharge.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Shaman::Overcharge
{
    // One Shaman's banked overflow. `carry` is the part of a stack the overflow has not yet filled; it lives as long as a
    // stack would, from the last overflow.
    struct Bank
    {
        unsigned stacks = 0;
        double carry = 0;
        std::uint64_t until = 0;      // ms: the stacks are gone from this moment on
        std::uint64_t carryUntil = 0; // ms: the carry is gone from this moment on
    };

    // The most stacks: the base, or what the Storm Surge passive raises it to.
    inline unsigned Cap(unsigned base, bool stormSurge, unsigned stormSurgeMax)
    {
        return stormSurge ? std::max(base, stormSurgeMax) : base;
    }

    inline bool Over(Bank const& bank, std::uint64_t now)
    {
        return bank.stacks == 0 || bank.until <= now;
    }

    // The stacks held now, never above `cap` (a cap that fell with its passive takes the extra).
    inline unsigned Held(Bank const& bank, std::uint64_t now, unsigned cap)
    {
        return Over(bank, now) ? 0 : std::min(bank.stacks, cap);
    }

    // `overflow` points of Maelstrom that did not fit. Returns the stacks held after. A new stack restarts the time of all
    // of them; the points toward the next one wait for the next overflow. At the cap nothing more is banked.
    inline unsigned Add(Bank& bank, std::uint64_t now, double overflow, double perStack, unsigned cap, std::uint64_t ms)
    {
        if (bank.until <= now)
            bank.stacks = 0;
        if (bank.carryUntil <= now)
            bank.carry = 0;
        if (overflow <= 0 || perStack <= 0)
            return Held(bank, now, cap);
        bank.carry += overflow;
        // The sum of tenths the pulse adds up is no exact binary fraction: 10 points arrive as 9.999..., so the whole
        // stack gets the tolerance a whole unit gets in the resource pulse.
        auto const gained = unsigned(std::floor(bank.carry / perStack + 1e-9));
        if (gained > 0)
        {
            bank.carry -= gained * perStack;
            if (bank.carry < 0)
                bank.carry = 0;
            bank.stacks = std::min(bank.stacks + gained, cap);
            bank.until = now + ms;
        }
        if (bank.stacks >= cap)
            bank.carry = 0;
        bank.carryUntil = now + ms;
        return Held(bank, now, cap);
    }

    // The next Secondary skill spends every stack: how many it had, and none are left.
    inline unsigned Take(Bank& bank, std::uint64_t now, unsigned cap)
    {
        unsigned const held = Held(bank, now, cap);
        bank.stacks = 0;
        bank.until = 0;
        return held;
    }

    // "+15% damage per stack": the percent a cast that spent `stacks` deals more.
    inline double DamagePct(unsigned stacks, double perStackPct)
    {
        return stacks * perStackPct;
    }

    // The seconds left on the stacks, 0 when there are none.
    inline double SecondsLeft(Bank const& bank, std::uint64_t now)
    {
        return Over(bank, now) ? 0.0 : double(bank.until - now) / 1000.0;
    }
} // namespace DC::Combat::Shaman::Overcharge
