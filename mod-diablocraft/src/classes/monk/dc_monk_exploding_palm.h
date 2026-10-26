#pragma once
// Exploding Palm's rules that need no core type, header-only so
// tests/monk_exploding_palm compiles this exact code: the marks an enemy carries and who they belong to, the stamps of
// the damage-over-time runs, the ticks of a total spread over its seconds.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <utility>
#include <vector>

namespace DC::Combat::Monk::ExplodingPalm
{
    // The ticks that fit `seconds` at `perSecond` ticks a second, and each one's share of a total. No rate or no
    // seconds, no ticks.
    inline unsigned Ticks(double seconds, double perSecond)
    {
        return seconds > 0 && perSecond > 0 ? static_cast<unsigned>(std::floor(seconds * perSecond + 1e-9)) : 0u;
    }

    inline double TickPct(double totalPct, unsigned ticks)
    {
        return ticks ? totalPct / ticks : 0.0;
    }

    // "If the enemy dies while bleeding": the enemies a Monk's palm is on, for as long as the palm lasts. A new palm on
    // the same enemy by the same Monk starts over; another Monk's is its own.
    struct Mark
    {
        std::uint64_t caster = 0;
        std::uint32_t spellId = 0;
    };

    class Marks
    {
    public:
        void Set(std::uint64_t caster, std::uint64_t enemy, std::uint32_t spellId, std::uint64_t untilMs)
        {
            marks_[{enemy, caster}] = {spellId, untilMs};
        }

        // Whether the palm of `spellId` by `caster` is still on `enemy` at `now`.
        bool Live(std::uint64_t caster, std::uint64_t enemy, std::uint32_t spellId, std::uint64_t now) const
        {
            auto const found = marks_.find({enemy, caster});
            return found != marks_.end() && found->second.spellId == spellId && now < found->second.untilMs;
        }

        // The enemy has died: every palm on it that still lasts, once. The ones that ran out are dropped silently.
        std::vector<Mark> Take(std::uint64_t enemy, std::uint64_t now)
        {
            std::vector<Mark> live;
            for (auto at = marks_.lower_bound({enemy, 0}); at != marks_.end() && at->first.first == enemy;)
            {
                if (now < at->second.untilMs)
                    live.push_back({at->first.second, at->second.spellId});
                at = marks_.erase(at);
            }
            return live;
        }

        // Palms that ran out, for the enemies that left without dying.
        void Prune(std::uint64_t now)
        {
            for (auto at = marks_.begin(); at != marks_.end();)
                at = now < at->second.untilMs ? std::next(at) : marks_.erase(at);
        }

        std::size_t Size() const
        {
            return marks_.size();
        }

    private:
        struct Value
        {
            std::uint32_t spellId = 0;
            std::uint64_t untilMs = 0;
        };
        std::map<std::pair<std::uint64_t, std::uint64_t>, Value> marks_;
    };

    // The damage-over-time runs, one per Monk, enemy and kind: a new run starts over, and the ticks of the old one find
    // their stamp gone and stop.
    class Runs
    {
    public:
        std::uint64_t Start(std::uint64_t caster, std::uint64_t enemy, unsigned kind)
        {
            return stamps_[{{caster, enemy}, kind}] = ++last_;
        }

        bool Live(std::uint64_t caster, std::uint64_t enemy, unsigned kind, std::uint64_t stamp) const
        {
            auto const found = stamps_.find({{caster, enemy}, kind});
            return found != stamps_.end() && found->second == stamp;
        }

        void End(std::uint64_t caster, std::uint64_t enemy, unsigned kind, std::uint64_t stamp)
        {
            auto const found = stamps_.find({{caster, enemy}, kind});
            if (found != stamps_.end() && found->second == stamp)
                stamps_.erase(found);
        }

    private:
        std::map<std::pair<std::pair<std::uint64_t, std::uint64_t>, unsigned>, std::uint64_t> stamps_;
        std::uint64_t last_ = 0;
    };

    // Shocking Grasp: "arcs up to {radius_yards} yards to another target": the nearest of the candidates' squared
    // distances within the radius, or none.
    inline int Nearest(std::vector<double> const& distancesSquared, double radius)
    {
        int best = -1;
        for (std::size_t i = 0; i < distancesSquared.size(); ++i)
            if (distancesSquared[i] <= radius * radius && (best < 0 || distancesSquared[i] < distancesSquared[best]))
                best = int(i);
        return best;
    }
} // namespace DC::Combat::Monk::ExplodingPalm
