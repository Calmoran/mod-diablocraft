#ifndef DC_REQUEST_GAP_H
#define DC_REQUEST_GAP_H
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <unordered_map>

// security.md G1: a short per-player gap between two requests of one kind, for the
// handlers that wait on a database commit on the world thread (DCSLOT, DCPASSIVE,
// Paragon allocate/deallocate). One helper, so a handler that later moves to another
// mechanism (the custom NPC research) keeps the same rule. A request inside the gap is
// refused and does NOT extend the wait: only an admitted request stamps the clock.
// The window bridge (dc_bridge.h) needs a burst as well as a gap, so its
// per-player token bucket lives here too: one header, one clock, one tunable clamp.
namespace DC::Gap
{
// True when the previous admitted request is still inside the gap. A gap of 0 is off.
inline bool Cooling(std::uint64_t nowMs, bool hasLast, std::uint64_t lastMs, std::uint64_t gapMs)
{
    return hasLast && nowMs >= lastMs && nowMs - lastMs < gapMs;
}

inline std::uint64_t NowMs()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// A tunable row is a double; a negative or non-finite row must not wrap into a huge gap.
inline std::uint64_t GapFromTunable(double milliseconds)
{
    return milliseconds > 0.0 && milliseconds < 3600000.0 ? static_cast<std::uint64_t>(milliseconds) : 0;
}

// One instance per handler. Thread-safe: map threads call it for their own players.
class PerPlayer
{
public:
    bool Admit(std::uint64_t player, std::uint64_t nowMs, std::uint64_t gapMs)
    {
        if (!gapMs)
            return true;
        std::lock_guard<std::mutex> lock(mutex_);
        auto found = last_.find(player);
        if (found != last_.end() && Cooling(nowMs, true, found->second, gapMs))
            return false;
        // An entry older than the gap says nothing, so the table stays about the size of
        // the players who acted in the last gap.
        if (last_.size() >= 256)
            for (auto it = last_.begin(); it != last_.end();)
                it = (nowMs >= it->second && nowMs - it->second >= gapMs) ? last_.erase(it) : std::next(it);
        last_[player] = nowMs;
        return true;
    }

private:
    std::mutex mutex_;
    std::unordered_map<std::uint64_t, std::uint64_t> last_;
};

// A tunable row is a double; the bucket reads two. A row nobody set (0), a negative or a
// non-finite one gives 0, and 0 here means "refuse": a bucket that is not configured must
// not become an open door. The ceilings only stop a typo (1e9) from meaning "no limit".
inline std::uint32_t BurstFromTunable(double burst)
{
    return std::isfinite(burst) && burst >= 1.0 && burst <= 1000.0 ? static_cast<std::uint32_t>(burst) : 0;
}

inline double RateFromTunable(double perSecond)
{
    return std::isfinite(perSecond) && perSecond > 0.0 && perSecond <= 1000.0 ? perSecond : 0.0;
}

// Token bucket, one per prefix. A player starts full (a window's first clicks are never held),
// each admitted request costs one token, tokens come back at `perSecond` up to `burst`. A
// refused request costs nothing and does not delay the refill. burst 0 or rate 0 refuses
// everything (see above). Thread-safe.
class PerPlayerBucket
{
public:
    bool Admit(std::uint64_t player, std::uint64_t nowMs, std::uint32_t burst, double perSecond)
    {
        if (!burst || perSecond <= 0.0)
            return false;
        std::lock_guard<std::mutex> lock(mutex_);
        auto found = state_.find(player);
        if (found == state_.end())
        {
            // A table that only holds players who spent tokens recently stays small: a full
            // bucket says nothing and is dropped.
            if (state_.size() >= 256)
                for (auto it = state_.begin(); it != state_.end();)
                    it = Refilled(it->second, nowMs, burst, perSecond) >= burst ? state_.erase(it) : std::next(it);
            found = state_.emplace(player, State{static_cast<double>(burst), nowMs}).first;
        }
        // Only an admitted request writes: a refusal leaves the clock alone, so hammering cannot
        // delay the refill (and the float sum is one product, not many small ones).
        State& state = found->second;
        double tokens = Refilled(state, nowMs, burst, perSecond);
        if (tokens < 1.0)
            return false;
        state.tokens = tokens - 1.0;
        state.lastMs = std::max(state.lastMs, nowMs);
        return true;
    }

private:
    struct State
    {
        double tokens;
        std::uint64_t lastMs;
    };
    static double Refilled(State const& state, std::uint64_t nowMs, std::uint32_t burst, double perSecond)
    {
        double elapsed = nowMs > state.lastMs ? static_cast<double>(nowMs - state.lastMs) : 0.0;
        return std::min(static_cast<double>(burst), state.tokens + elapsed * perSecond / 1000.0);
    }
    std::mutex mutex_;
    std::unordered_map<std::uint64_t, State> state_;
};
}

#endif
