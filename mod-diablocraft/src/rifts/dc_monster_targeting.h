#ifndef DC_MONSTER_TARGETING_H
#define DC_MONSTER_TARGETING_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

// Literal audit (docs/research/literal-audit-claude.md): the numbers below are
// constants, not tunables - recorded here, nothing else changes.
// Constant (-1.0, 1.0): clamp on the targeting jitter roll; Bounds on a random, not a value.

namespace DC::Rifts::Targeting
{
    // Every numeric field is a tunable loaded from dc_monster_targeting.
    // No balancing defaults live in C++; missing/invalid profiles are an error.
    struct Profile
    {
        double lockSeconds, jitterPercent, recencyWeight, proximityWeight, reachabilityWeight;
        double recencyWindowSeconds, recencyMaxYards, candidateMaxYards;
        double unreachablePenalty, switchMargin;
    };

    inline bool Valid(Profile const& p)
    {
        for (double value :
             {p.lockSeconds, p.jitterPercent, p.recencyWeight, p.proximityWeight, p.reachabilityWeight,
              p.recencyWindowSeconds, p.recencyMaxYards, p.candidateMaxYards, p.unreachablePenalty, p.switchMargin})
            if (!std::isfinite(value) || value < 0)
                return false;
        return p.lockSeconds > 0 && p.recencyWindowSeconds > 0 && p.candidateMaxYards > 0 && p.jitterPercent < 100 &&
               p.recencyMaxYards <= p.candidateMaxYards &&
               std::isfinite(p.recencyWeight + p.proximityWeight + p.reachabilityWeight + p.unreachablePenalty +
                             p.switchMargin) &&
               std::isfinite(p.lockSeconds * (1.0 + p.jitterPercent / 100.0));
    }

    struct Candidate
    {
        std::uint64_t guid;
        double distance;
        bool reachable;
        // Infinity means this player has never damaged this monster.
        double secondsSinceHit = std::numeric_limits<double>::infinity();
        // Straight distance / complete route length; long detours score lower.
        double routeEfficiency = 1.0;
    };

    inline double Score(Candidate const& c, Profile const& p)
    {
        double recency = c.distance <= p.recencyMaxYards
                             ? std::clamp(1.0 - c.secondsSinceHit / p.recencyWindowSeconds, 0.0, 1.0)
                             : 0.0;
        double proximity = std::clamp(1.0 - c.distance / p.candidateMaxYards, 0.0, 1.0);
        return p.recencyWeight * recency + p.proximityWeight * proximity +
               (c.reachable ? p.reachabilityWeight * c.routeEfficiency : -p.unreachablePenalty);
    }

    class Policy
    {
    public:
        std::uint64_t Current() const
        {
            return _current;
        }
        double Remaining(double now) const
        {
            return std::max(0.0, _until - now);
        }
        bool Taunted() const
        {
            return _taunted;
        }
        void Clear()
        {
            _current = 0;
            _until = 0;
            _taunted = false;
        }
        void ReleaseTaunt(double now)
        {
            if (_taunted)
            {
                _taunted = false;
                _until = now;
            }
        }

        // Hit range/path gating also protects the immediate-lock path. Otherwise
        // the scored release could be bypassed with alternating distant pokes.
        bool Hit(Candidate const& attacker, double now, Profile const& p, double jitter)
        {
            if (_taunted || Remaining(now) > 0 || !attacker.reachable || attacker.distance > p.recencyMaxYards)
                return false;
            Commit(attacker.guid, now, p, jitter);
            return true;
        }

        std::uint64_t Choose(std::vector<Candidate> const& candidates, double now, Profile const& p, double jitter,
                             std::uint64_t taunt = 0)
        {
            if (taunt)
            {
                _current = taunt;
                _taunted = true;
                return _current; // Native aura lifetime is the override duration.
            }
            ReleaseTaunt(now); // No extra normal lock after aura expiry.
            Candidate const* current = nullptr;
            for (auto const& c : candidates)
                if (c.guid == _current)
                    current = &c;
            if (current && Remaining(now) > 0)
                return _current;

            Candidate const* best = nullptr;
            double bestScore = -std::numeric_limits<double>::infinity();
            for (auto const& c : candidates)
            {
                // Penalise in diagnostics AND never commit to an unreachable
                // player. With no reachable player, park without resetting Life.
                double score = Score(c, p);
                if (!c.reachable)
                    continue;
                if (score > bestScore || (score == bestScore && best && c.guid < best->guid))
                {
                    best = &c;
                    bestScore = score;
                }
            }
            if (!best)
            {
                Clear();
                return 0;
            }
            if (current && current->reachable && best->guid != current->guid &&
                !(bestScore > Score(*current, p) + p.switchMargin))
                best = current;
            Commit(best->guid, now, p, jitter);
            return _current;
        }

    private:
        void Commit(std::uint64_t guid, double now, Profile const& p, double jitter)
        {
            _current = guid;
            _until = now + p.lockSeconds * (1.0 + std::clamp(jitter, -1.0, 1.0) * p.jitterPercent / 100.0);
        }
        std::uint64_t _current = 0;
        double _until = 0;
        bool _taunted = false;
    };
} // namespace DC::Rifts::Targeting
#endif
