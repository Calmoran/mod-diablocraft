#pragma once
// The Monk's Mantras share one rule, "Only one Mantra may be active at a time", and so one state (with a
// state in each Mantra's file, a Healing cast never turned Salvation off). Header-only so
// tests/monk_mantras compiles this exact code. Session-only, per Monk guid; keyed by the Mantra's base spell id (the
// skill's own row, which its runes share).
//
// Nothing cast yet leaves every slotted Mantra in force: a Monk's slotted Mantra has its passive from the moment it is
// on the bar (login included), the cast only picks which one holds when two are slotted and opens the activation's
// boost window.
#include <cstdint>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Monk::Mantras
{
    struct State
    {
        std::uint32_t active = 0;
        std::uint64_t boostUntil = 0;
    };

    namespace detail
    {
        inline std::mutex mutex;
        inline std::unordered_map<std::uint64_t, State> states;
    } // namespace detail

    // The Monk cast `mantra`: it becomes the one in force and its boost window runs `boostMs` from `now`; the Mantra
    // cast before it is off.
    inline void Cast(std::uint64_t monk, std::uint32_t mantra, std::uint64_t now, std::uint64_t boostMs)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        detail::states[monk] = {mantra, now + boostMs};
    }

    // Whether `mantra`'s passive is on for the Monk: none cast yet, or it is the one cast last.
    inline bool On(std::uint64_t monk, std::uint32_t mantra)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        auto const found = detail::states.find(monk);
        return found == detail::states.end() || found->second.active == mantra;
    }

    // Whether `mantra`'s activation window is open at `now`.
    inline bool Boosted(std::uint64_t monk, std::uint32_t mantra, std::uint64_t now)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        auto const found = detail::states.find(monk);
        return found != detail::states.end() && found->second.active == mantra && now < found->second.boostUntil;
    }

    // The Monk left (logout): the next login starts with nothing cast.
    inline void Forget(std::uint64_t monk)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        detail::states.erase(monk);
    }

    // The id a Monk's Mantra puts on an ally's stat contribution. Two Monks' auras on one ally are two contributions:
    // keyed by the rune alone, the second Monk's pulse replaced the first's and its release took both off.
    inline std::uint64_t Key(std::uint64_t monk, std::uint64_t id)
    {
        return (monk << 32) | (id & 0xFFFFFFFFull);
    }
} // namespace DC::Combat::Monk::Mantras
