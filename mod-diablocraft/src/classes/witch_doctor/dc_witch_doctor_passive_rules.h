#pragma once
// The rules of the Witch Doctor's passives of the second and third group that need no core type, header-only so
// tests/witch_doctor_passive_rules compiles this exact code: what Pierce the Veil costs, when Spirit Vessel saves and
// when it may again, how many Rush of Essence streams
// are running, what Vision Quest adds, and the rest of the third group's numbers. The production halves are the files
// named for what they do (dc_witch_doctor_damage_passives.cpp and its neighbours).
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

namespace DC::Combat::WitchDoctor::Passive::Rules
{
    // Pierce the Veil: "your Mana costs are increased by {cost_increase_pct}": the Mana a cast of `cost` pays on top of
    // it.
    inline double ExtraCost(double cost, double pct)
    {
        return cost > 0 && pct > 0 ? cost * pct / 100.0 : 0.0;
    }

    // Whether a name is in a list of skills the passive's tooltip names.
    template<class List>
    inline bool Listed(List const& list, std::string_view name)
    {
        return std::find(list.begin(), list.end(), name) != list.end();
    }

    // Spirit Vessel: "When you receive fatal damage": a blow of `damage` that is at least the `health` left.
    inline bool Fatal(double damage, double health)
    {
        return health > 0 && damage >= health;
    }

    // "This effect may occur once every {internal_cooldown_seconds} seconds": the last time it did (none before), now,
    // and the cooldown, all in milliseconds.
    inline bool Ready(std::optional<std::uint64_t> lastMs, std::uint64_t nowMs, std::uint64_t cooldownMs)
    {
        return !lastMs || nowMs >= *lastMs + cooldownMs;
    }

    // Whether a window that began at `startMs` and lasts `lastsMs` is still open at `nowMs`.
    inline bool Open(std::uint64_t startMs, std::uint64_t nowMs, std::uint64_t lastsMs)
    {
        return nowMs < startMs + lastsMs;
    }

    // Rush of Essence: the streams still running at `nowMs` (each ends at its own time) and the points a second they
    // pay: each is `gain` Mana over `seconds`.
    inline unsigned Running(std::vector<std::uint64_t> const& ends, std::uint64_t nowMs)
    {
        return unsigned(std::count_if(ends.begin(), ends.end(), [nowMs](std::uint64_t end) { return end > nowMs; }));
    }

    inline void Prune(std::vector<std::uint64_t>& ends, std::uint64_t nowMs)
    {
        ends.erase(std::remove_if(ends.begin(), ends.end(), [nowMs](std::uint64_t end) { return end <= nowMs; }),
                   ends.end());
    }

    inline double PerSecond(double gain, double seconds)
    {
        return seconds > 0 ? gain / seconds : 0.0;
    }

    // Vision Quest: "Mana regeneration is increased by {regen_pct}": that share of the class's own points a second.
    inline double RegenBonus(double classRegenPerSecond, double pct)
    {
        return classRegenPerSecond > 0 && pct > 0 ? classRegenPerSecond * pct / 100.0 : 0.0;
    }

    // Tribal Rites: "Reduce the cooldowns ... by {cooldown_reduction_pct}": the milliseconds taken off a cooldown that has `leftMs` to run.
    inline std::uint32_t CooldownCut(std::uint32_t leftMs, double pct)
    {
        return std::uint32_t(leftMs * std::clamp(pct, 0.0, 100.0) / 100.0);
    }

    // Grave Injustice: "reduce the cooldown of all of your skills by {cooldown_reduction_seconds} second": the milliseconds left of a
    // cooldown that has `leftMs` to run, taking off `seconds`, never below nothing.
    inline std::uint32_t CooledBy(std::uint32_t leftMs, double seconds)
    {
        std::uint32_t const cut = std::uint32_t(std::max(0.0, seconds) * 1000.0 + 0.5);
        return leftMs > cut ? leftMs - cut : 0u;
    }

    // Grave Injustice: "Gain {heal_pct} of your maximum Life and Mana": that share of `maximum`.
    inline double Share(double maximum, double pct)
    {
        return maximum > 0 && pct > 0 ? maximum * pct / 100.0 : 0.0;
    }

    // Creeping Death: a debuff of `baseSeconds` lasts the passive's seconds instead while the passive is on.
    inline double Lasting(bool on, double baseSeconds, double passiveSeconds)
    {
        return on ? std::max(baseSeconds, passiveSeconds) : baseSeconds;
    }

    // Whether something `distance` yards off is within `radius` yards, widened by `extra` (a gold pickup radius, a combat reach).
    inline bool Near(double distance, double radius, double extra)
    {
        return distance <= radius + std::max(0.0, extra);
    }

    // Swampland Attunement: "{resistance_points} ... Resistance for every enemy within {radius_yards} yards": the points a level gives for
    // each enemy, for the enemies there are (counting no more than `most`).
    inline double ResistPoints(unsigned level, double perLevel, unsigned enemies, unsigned most)
    {
        return level * perLevel * std::min(enemies, most);
    }

    // Fierce Loyalty: the movement speed percent: none without a pet out, the base one with a pet, the out-of-combat one while a pet is
    // not in combat.
    inline double FierceSpeed(bool petOut, bool petIdle, double base, double outOfCombat)
    {
        return !petOut ? 0.0 : petIdle ? outOfCombat : base;
    }
} // namespace DC::Combat::WitchDoctor::Passive::Rules
