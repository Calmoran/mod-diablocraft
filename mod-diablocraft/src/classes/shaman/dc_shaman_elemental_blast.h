#pragma once
// Elemental Blast's rules that need no core type, header-only so tests/shaman_elemental_blast compiles this exact code:
// which rune is which, the order Prismatic Cycle moves the Attunement in, what Elemental Echo adds for each element,
// who the Elemental Mastery buff helps, the share Unstable Elements splashes and when Primal Wellspring refunds. The
// production half is dc_shaman_elemental_blast.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::ElementalBlast
{
    enum class Rune
    {
        None,
        PrismaticCycle,   // the Attunement moves on after the blast
        ElementalEcho,    // adds an effect of the Attunement's element
        UnstableElements, // splashes a share of the damage around the target
        ElementalMastery, // the buff gives damage of the Attunement's element instead of critical hit chance
        PrimalWellspring  // refunds Maelstrom for a kill or an elite
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Prismatic Cycle")
            return Rune::PrismaticCycle;
        if (name == "Elemental Echo")
            return Rune::ElementalEcho;
        if (name == "Unstable Elements")
            return Rune::UnstableElements;
        if (name == "Elemental Mastery")
            return Rune::ElementalMastery;
        if (name == "Primal Wellspring")
            return Rune::PrimalWellspring;
        return Rune::None;
    }

    // Prismatic Cycle: "the next element in the order Fire -> Lightning -> Cold -> Physical -> Fire", the elements
    // named as the engine names them. Nothing for another name.
    inline std::optional<std::string_view> NextElement(std::string_view element)
    {
        if (element == "fire")
            return "lightning";
        if (element == "lightning")
            return "cold";
        if (element == "cold")
            return "physical";
        if (element == "physical")
            return "fire";
        return std::nullopt;
    }

    // What Elemental Echo adds, by the Attunement.
    enum class Echo
    {
        Burn,
        Arc,
        Freeze,
        Knock
    };

    inline std::optional<Echo> EchoOf(std::string_view element)
    {
        if (element == "fire")
            return Echo::Burn;
        if (element == "lightning")
            return Echo::Arc;
        if (element == "cold")
            return Echo::Freeze;
        if (element == "physical")
            return Echo::Knock;
        return std::nullopt;
    }

    // The critical hit chance the Elemental Mastery buff gives: every rune's but Elemental Mastery's, which gives
    // damage instead.
    inline double CritBonus(Rune rune, double pct)
    {
        return rune == Rune::ElementalMastery || pct <= 0 ? 0.0 : pct;
    }

    // The damage the Elemental Mastery rune's buff gives a hit of the element of the Attunement; none for another
    // element.
    inline double DamageBonus(Rune rune, bool sameElement, double pct)
    {
        return rune == Rune::ElementalMastery && sameElement && pct > 0 ? pct : 0.0;
    }

    // Unstable Elements: "deals {damage_share_pct} of its damage to all enemies within {radius_yards} yards": the
    // weapon damage percent of the splash.
    inline double SplashPct(double hitPct, double sharePct)
    {
        return hitPct > 0 && sharePct > 0 ? hitPct * sharePct / 100.0 : 0.0;
    }

    // Primal Wellspring: "Refunds {gain_resource} Maelstrom if Elemental Blast kills its target or hits an elite".
    inline double Refund(bool killed, bool elite, double gain)
    {
        return (killed || elite) && gain > 0 ? gain : 0.0;
    }

    // The element a hit deals: the one the class names for it through the element seam (the blast and Primal Shock deal the Shaman's
    // Attunement whatever their record's school is), else the record's own school. Both as the engine names an element.
    inline std::string_view DealtElement(char const* seam, char const* record)
    {
        return seam && *seam ? std::string_view(seam) : std::string_view(record);
    }

    // Whether a buff that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_elemental_blast.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of an Elemental Blast record deals: the skill's, for every record.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The element a hit of the skill deals: the Shaman's Attunement. nullptr for any other spell.
    char const* Element(Player* player, std::uint32_t spellId);
    // A cast of `spellId` resolved: the Elemental Mastery buff, and Prismatic Cycle's move of the Attunement.
    void Cast(Player* player, std::uint32_t spellId);
    // A hit of the skill landed on `target`: Elemental Echo, Unstable Elements, Primal Wellspring.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The hit of `spellId` being computed: the Elemental Mastery rune's damage.
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::ElementalBlast
