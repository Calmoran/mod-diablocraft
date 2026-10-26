#pragma once
// The Crusader's Laws share one rule, "Only one Law may be active at a time", and so one state (a state in each Law's
// file would let a Hope cast leave Valor on). The rules that need no core type are here, header-only, so
// tests/crusader_laws compiles this exact code; the mechanism that runs a Law's aura is dc_crusader_laws.cpp.
// Session-only, per Crusader guid; keyed by the Law's base spell id (the skill's own row, which its runes share).
//
// Nothing cast yet leaves every slotted Law in force: a Law's passive is on from the moment it is on the bar (login
// included); the cast only picks which one holds when two are slotted and opens the activation's window.
#include "../../common/dc_common.h"

#include <algorithm>
#include <cstdint>
#include <mutex>
#include <string_view>
#include <unordered_map>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::Laws
{
    struct State
    {
        std::uint32_t active = 0;
        std::uint64_t boostUntil = 0;
        std::uint64_t extendedMs = 0; // time Answered Prayer's kills have added to this window
    };

    namespace detail
    {
        inline std::mutex mutex;
        inline std::unordered_map<std::uint64_t, State> states;
    } // namespace detail

    // The Crusader cast `law`: it becomes the one in force and its window runs `boostMs` from `now`; the Law cast
    // before it is off, and the time kills added to that window is forgotten.
    inline void Cast(std::uint64_t crusader, std::uint32_t law, std::uint64_t now, std::uint64_t boostMs)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        detail::states[crusader] = {law, now + boostMs, 0};
    }

    // Whether `law`'s passive is on for the Crusader: none cast yet, or it is the one cast last.
    inline bool On(std::uint64_t crusader, std::uint32_t law)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        auto const found = detail::states.find(crusader);
        return found == detail::states.end() || found->second.active == law;
    }

    // Whether `law`'s window is open at `now`.
    inline bool Boosted(std::uint64_t crusader, std::uint32_t law, std::uint64_t now)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        auto const found = detail::states.find(crusader);
        return found != detail::states.end() && found->second.active == law && now < found->second.boostUntil;
    }

    // When `law`'s window ends, 0 when it is not the Law in force.
    inline std::uint64_t BoostEnd(std::uint64_t crusader, std::uint32_t law)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        auto const found = detail::states.find(crusader);
        return found != detail::states.end() && found->second.active == law ? found->second.boostUntil : 0;
    }

    // An enemy died while `law`'s window was open: it grows by `perKillMs`, and the time added to one window never
    // passes `maxExtraMs`. Returns the milliseconds added (0 when the window is closed, is another Law's or is at its
    // cap).
    inline std::uint64_t Extend(std::uint64_t crusader, std::uint32_t law, std::uint64_t now, std::uint64_t perKillMs,
                                std::uint64_t maxExtraMs)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        auto found = detail::states.find(crusader);
        if (found == detail::states.end() || found->second.active != law || now >= found->second.boostUntil)
            return 0;
        State& state = found->second;
        std::uint64_t const room = maxExtraMs > state.extendedMs ? maxExtraMs - state.extendedMs : 0;
        std::uint64_t const added = std::min(perKillMs, room);
        state.extendedMs += added;
        state.boostUntil += added;
        return added;
    }

    // The Crusader left (logout): the next login starts with nothing cast.
    inline void Forget(std::uint64_t crusader)
    {
        std::lock_guard<std::mutex> guard(detail::mutex);
        detail::states.erase(crusader);
    }

    // The id a Law puts on an ally's stat contribution. Two Crusaders' auras on one ally are two contributions: keyed
    // by the skill alone, the second Crusader's pulse would replace the first's and its end would take both off.
    inline std::uint64_t Key(std::uint64_t crusader, std::uint64_t id)
    {
        return (crusader << 32) | (id & 0xFFFFFFFFull);
    }

    // What a holder's number is: the Law's active number while its window is open, its passive number otherwise. The
    // sheet states them as two separate numbers ("Active: ... granting you and your allies 15% ... Passive: ... 8%")
    // and the Law is in one form or the other, so the active replaces the passive and does not add to it.
    inline double Number(bool boosted, double passive, double active)
    {
        return boosted ? active : passive;
    }

    // The milliseconds a stat given by one pulse lasts: the pulse period and a small grace, so the next pulse renews it
    // before it lapses and a stopped Law's numbers are gone within a pulse.
    inline std::uint64_t HoldMs(double periodSeconds, double graceSeconds)
    {
        return std::uint64_t((std::max(0.0, periodSeconds) + std::max(0.0, graceSeconds)) * 1000.0 + 0.5);
    }

    // ---- the mechanism (dc_crusader_laws.cpp) ---------------------------------------------------------------------

    // One Law to the mechanism: its skill's name in the sheets, one pulse of its aura (`boosted` says the window is
    // open), and what the press itself does to the targets the cast resolved. `killed` is called when the Crusader
    // kills an enemy (null for a Law that has no kill rule). `spent` is called when the Crusader casts a skill that costs
    // Wrath, with the points it costs (null for a Law that has no spending rule).
    struct Flavour
    {
        std::string_view skill;
        void (*pulse)(Player* owner, std::uint32_t slotted, bool boosted);
        void (*activate)(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
        void (*killed)(Player* player);
        void (*spent)(Player* player, double wrath) = nullptr;
        // The sheet token that states how long the empowered window lasts: most Laws say duration_seconds, Hope states its
        // time as its shield's.
        std::string_view window = "duration_seconds";
    };

    // Adds a Law to the always-on hook (once, at startup).
    void Add(Flavour const& flavour);
    // The always-on hook: a PlayerScript that, at login and then once a second, starts the pulse of each Law a Crusader
    // has on its skill bar, so a passive needs no press and a Law slotted later starts without one. Also the kill hook.
    void RegisterScripts();
    // The press: this Law is now the one in force, its window opens, the activation runs, and the pulse starts if none
    // runs.
    void Press(Flavour const& flavour, Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);

    std::uint64_t Now();
    // `seconds` of a Law's active effect with the Crusader's Long Arm of the Law added (the passive, dc_crusader_passives.h).
    double ActiveSeconds(Player* player, double seconds);
    // The seconds between two pulses (the tunable, or the code's default while it is blank).
    double PulseSeconds();
    // The milliseconds a number one pulse gives lasts (the pulse period and its grace): given until `Now() +
    // PulseHoldMs()`.
    std::uint64_t PulseHoldMs();
    // The skill's own spell id (its runes share the numbers and the state).
    std::uint32_t BaseId(std::string_view skill);
    // The skill or rune of the Law on one of the Crusader's skill buttons; 0 when none is.
    std::uint32_t Slotted(Player* player, std::string_view skill);
    // The Crusader and its group within the skill's radius, the Crusader first.
    std::vector<Player*> InAura(Player* owner, std::string_view skill);
    // `stat` of `target` is `value` until `untilMs` (a later call renews it, or changes the number); when no call
    // renews it by then, it comes off. `id` names the contribution. Only the sheet is touched, and the client is told
    // on a change.
    // `element` is the element an ElementReduction number is for: give each element its own id.
    void Hold(Player* target, Stat stat, Bucket bucket, std::uint64_t id, double value, std::uint64_t untilMs,
              Element element = Element::Physical);
} // namespace DC::Combat::Crusader::Laws
