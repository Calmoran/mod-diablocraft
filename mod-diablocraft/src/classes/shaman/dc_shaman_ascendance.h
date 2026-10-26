#pragma once
// Ascendance's rules that need no core type, header-only so tests/shaman_ascendance compiles this exact code: which
// rune is which, which element a rune empowers and what the damage bonus of a hit is, the bolt a Primary cast fires,
// how far Maelstrom spent extends the buff and the extra jumps of Chain Lightning. The production half is
// dc_shaman_ascendance.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::Ascendance
{
    enum class Rune
    {
        None,
        FlameAscendance,  // Fire skills deal more, and Lava Burst is free
        StormAscendance,  // Lightning skills deal more, and Chain Lightning jumps more
        WaterAscendance,  // Cold skills deal more, and the Shaman heals
        EarthAscendance,  // Physical skills deal more, and the Shaman takes less damage
        EternalAscendance // Maelstrom spent extends the buff
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Flame Ascendance")
            return Rune::FlameAscendance;
        if (name == "Storm Ascendance")
            return Rune::StormAscendance;
        if (name == "Water Ascendance")
            return Rune::WaterAscendance;
        if (name == "Earth Ascendance")
            return Rune::EarthAscendance;
        if (name == "Eternal Ascendance")
            return Rune::EternalAscendance;
        return Rune::None;
    }

    // The element a rune empowers, as the engine names an element; empty for the base and Eternal Ascendance, which
    // empower none.
    inline std::string_view ElementOfRune(Rune rune)
    {
        switch (rune)
        {
            case Rune::FlameAscendance:
                return "fire";
            case Rune::StormAscendance:
                return "lightning";
            case Rune::WaterAscendance:
                return "cold";
            case Rune::EarthAscendance:
                return "physical";
            default:
                return {};
        }
    }

    // "Damage dealt increases by {damage_bonus_pct}. Each rune picks an element and empowers it": the percent more a
    // hit of `element` deals under `rune`: the rune's own number for the element it picked, the skill's for every other
    // hit. `runePct` is 0 for a rune that states none.
    inline double Bonus(Rune rune, std::string_view element, double basePct, double runePct)
    {
        std::string_view const empowered = ElementOfRune(rune);
        return !empowered.empty() && empowered == element && runePct > 0 ? runePct : (basePct > 0 ? basePct : 0.0);
    }

    // "each Primary skill cast also fires an elemental bolt at {target_count} more enemies for {damage_share_pct} of
    // its damage": the weapon damage percent of a bolt of a Primary whose hit is `hitPct`.
    inline double BoltPct(double hitPct, double sharePct)
    {
        return hitPct > 0 && sharePct > 0 ? hitPct * sharePct / 100.0 : 0.0;
    }

    // Whether a cast of a skill of `category` fires bolts while Ascendance stands.
    inline bool Fires(std::string_view category, bool up)
    {
        return up && category == "Primary";
    }

    // Eternal Ascendance: "Every {per_trigger_resource} Maelstrom you spend extends Ascendance by {extend} second, up
    // to {cap} extra seconds": the milliseconds the `spent` more Maelstrom add, given the `carried` already counted
    // toward the next step (kept in `remainder`) and the `extendedMs` already added.
    struct Extension
    {
        std::uint64_t addMs = 0;
        double remainder = 0;
    };

    inline Extension Extend(Rune rune, double carried, double spent, std::uint64_t extendedMs, double perTrigger,
                            double extendSeconds, double capSeconds)
    {
        Extension out;
        out.remainder = carried;
        if (rune != Rune::EternalAscendance || spent <= 0 || perTrigger <= 0 || extendSeconds <= 0 || capSeconds <= 0)
            return out;
        double total = carried + spent;
        auto const cap = std::uint64_t(capSeconds * 1000.0), step = std::uint64_t(extendSeconds * 1000.0);
        while (total >= perTrigger)
        {
            total -= perTrigger;
            if (extendedMs + out.addMs < cap)
                out.addMs += std::min(step, cap - extendedMs - out.addMs);
        }
        out.remainder = total;
        return out;
    }

    // Storm Ascendance: the jumps Chain Lightning gets in all: "jumps {target_count} extra times".
    inline unsigned ExtraJumps(Rune rune, double targetCount)
    {
        return rune == Rune::StormAscendance && targetCount > 0 ? unsigned(targetCount) : 0u;
    }

    // Whether a buff that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_ascendance.cpp), called from dc_shaman.cpp and the Chain Lightning file.
    bool Is(std::uint32_t spellId);
    // A cast of `spellId` is about to be paid (the Casting seam): Eternal Ascendance counts a Secondary's Maelstrom.
    void Casting(Player* player, std::uint32_t spellId);
    // A cast of `spellId` resolved on `targets`: Ascendance starts, a Primary fires its bolts.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // The hit of `spellId` being computed: the damage bonus.
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
    // The jumps Chain Lightning gets more now (Storm Ascendance).
    unsigned ExtraChainJumps(Player* player);
} // namespace DC::Combat::Shaman::Ascendance
