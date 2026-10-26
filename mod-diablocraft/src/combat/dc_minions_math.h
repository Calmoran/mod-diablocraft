#pragma once
// The rules of a class's minions that need no core type, header-only so tests/minions compiles this exact code: how
// many of a group may stand, when a keeper raises the next one, when a minion's time is up, when a minion that dies
// after so many hits is dead, what a commanded minion's blow is worth, and how a skill's damage is cut into blows. The
// production half is dc_minions.cpp. No class is named here: a class defines its kinds and the numbers they run on.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::Minions
{
    // A new minion of a group that already has `alive` of `cap`: whether it may be raised, and whether the oldest of
    // the group goes to make room. A cap of 0 is no cap.
    struct Admission
    {
        bool raise = false;
        bool dismissOldest = false;
    };

    inline Admission Admit(unsigned alive, unsigned cap)
    {
        if (cap == 0 || alive < cap)
            return {true, false};
        return {true, true};
    }

    // A keeper holds `wanted` minions of a group, raising one at a time: it raises when fewer stand than wanted and its
    // own clock has run (`nextAt`, the earliest moment the next may be raised).
    inline bool KeeperDue(std::uint64_t now, std::uint64_t nextAt, unsigned alive, unsigned wanted)
    {
        return alive < wanted && now >= nextAt;
    }

    // When a keeper may next raise, after raising at `now` (one every `intervalMs`) or after a minion of the group was
    // lost at `now` (none before `returnMs`), never earlier than it already was.
    inline std::uint64_t NextAfterRaise(std::uint64_t now, std::uint64_t intervalMs)
    {
        return now + intervalMs;
    }

    inline std::uint64_t NextAfterLoss(std::uint64_t now, std::uint64_t nextAt, std::uint64_t returnMs)
    {
        return std::max(nextAt, now + returnMs);
    }

    // A minion born at `bornAt` with `lifeMs` to live (0: it stays) is over at this moment.
    inline bool Expired(std::uint64_t now, std::uint64_t bornAt, std::uint64_t lifeMs)
    {
        return lifeMs > 0 && now >= bornAt + lifeMs;
    }

    // A minion that "dies after {hits} hits" (0: it has its own Life): the count of hits taken so far, and whether this
    // one is the last.
    struct HitLimit
    {
        unsigned taken = 0;

        bool Take(unsigned limit)
        {
            ++taken;
            return limit > 0 && taken >= limit;
        }
    };

    // A commanded minion's blow: the skill's `bonusPct` more damage against the target it was ordered at, and the plain
    // damage against any other. `commanded` is whether the target is the commanded one and the order still stands.
    inline double BlowPct(double damagePct, bool commanded, double bonusPct)
    {
        return commanded && bonusPct > 0 ? damagePct * (1.0 + bonusPct / 100.0) : damagePct;
    }

    // A group's blow with a timed boost on it (a rune that feeds the minion): `boostPct` percent more while the boost stands.
    inline double BoostedPct(double damagePct, double boostPct)
    {
        return boostPct > 0 ? damagePct * (1.0 + boostPct / 100.0) : damagePct;
    }

    // A commanded minion's blow rate: the minion's attacks per second, `speedPct` percent faster while it attacks the target
    // it was ordered at (a rune that sends the commanded into a frenzy), and the plain rate against any other.
    // The time a minion waits between swings, in ms: the kind's own (`swingMs`, a power that fixes its attack's cooldown) when it states one, else one
    // over the attacks per second of the owner. Nothing to wait for with no rate and no swing time (the minion does not attack).
    inline double SwingMs(double attacksPerSecond, double swingMs)
    {
        return swingMs > 0 ? swingMs : (attacksPerSecond > 0 ? 1000.0 / attacksPerSecond : 0.0);
    }

    inline double CommandedRate(double attacksPerSecond, bool commanded, double speedPct)
    {
        return commanded && speedPct > 0 ? attacksPerSecond * (1.0 + speedPct / 100.0) : attacksPerSecond;
    }

    // A skill that deals {damage_pct} "over N attacks": the share of one attack. At least one attack.
    inline double PerHit(double totalPct, unsigned hits)
    {
        return totalPct / std::max(1u, hits);
    }

    // A minion follows its owner, except one whose kind stands where it was raised.
    inline bool Follows(bool staysPut)
    {
        return !staysPut;
    }

    // A copy of the owner that has `lifePct` percent of its maximum Life (Simulacrum), never less than 1.
    inline std::uint32_t CopyLife(std::uint32_t ownerMaxLife, double lifePct)
    {
        double const life = ownerMaxLife * std::max(0.0, lifePct) / 100.0;
        return std::uint32_t(std::max(1.0, life));
    }
} // namespace DC::Combat::Minions
