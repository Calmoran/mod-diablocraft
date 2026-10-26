#pragma once
// Spirit Link's rules that need no core type, header-only so tests/shaman_spirit_link compiles this exact code: which
// rune is which, which enemies a cast links, what share of a hit the others take, how far a death extends the link, and
// how the link's own damage ticks. The production half is dc_shaman_spirit_link.cpp, called from dc_shaman.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::SpiritLink
{
    enum class Rune
    {
        None,
        AncestralChains, // links more enemies in a wider circle
        SearingLink,     // Fire; the linked enemies burn
        FrozenLink,      // Cold; the linked enemies are chilled, and frozen when one of them dies
        ThunderLink,     // Lightning; a larger share
        SpiritHarvest    // each linked enemy that dies pays Maelstrom and extends the link
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Ancestral Chains")
            return Rune::AncestralChains;
        if (name == "Searing Link")
            return Rune::SearingLink;
        if (name == "Frozen Link")
            return Rune::FrozenLink;
        if (name == "Thunder Link")
            return Rune::ThunderLink;
        if (name == "Spirit Harvest")
            return Rune::SpiritHarvest;
        return Rune::None;
    }

    // The enemies a cast links: the target first, then the nearest to it, `cap` in all. `distances[i]` is enemy i's
    // yards from the target (the target is among them at 0). Returns the indices, nearest first.
    inline std::vector<std::size_t> Members(std::vector<double> const& distances, std::size_t cap)
    {
        std::vector<std::size_t> order(distances.size());
        std::iota(order.begin(), order.end(), std::size_t(0));
        std::stable_sort(order.begin(), order.end(),
                         [&](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (order.size() > cap)
            order.resize(cap);
        return order;
    }

    // "{damage_share_pct}% of the damage you deal to one linked enemy is also dealt to every other linked enemy. Elites
    // and bosses ... receive only half of the shared damage": what one other enemy takes of a hit of `damage`.
    // `elitePct` is the share an elite or a boss gets of it.
    inline double Shared(double damage, double sharePct, bool elite, double elitePct)
    {
        if (damage <= 0 || sharePct <= 0)
            return 0.0;
        return damage * sharePct / 100.0 * (elite ? elitePct / 100.0 : 1.0);
    }

    // The share a rune gives: Thunder Link's own, else the skill's.
    inline double ShareOf(Rune rune, double skill, double thunder)
    {
        return rune == Rune::ThunderLink ? thunder : skill;
    }

    // Whether a hit is shared at all: not an echo of a share (they are proc-free single copies, never copied again),
    // and not the link's own damage (it would feed on itself).
    inline bool Shares(bool echoing, bool linksOwnDamage)
    {
        return !echoing && !linksOwnDamage;
    }

    // "extends the link by {extend} second (up to {cap} extra seconds)": the extra seconds after one more death.
    inline double Extended(double extra, double perDeath, double cap)
    {
        return std::min(cap, extra + perDeath);
    }

    // The link's own damage "N% weapon damage per second" in ticks of `tickSeconds`: the percent of one tick.
    inline double TickPct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct * tickSeconds;
    }

    // Whether the link's damage ticks as a burn (Searing Link) or as an aura pulse.
    inline double TickSeconds(Rune rune, double aura, double burn)
    {
        return rune == Rune::SearingLink ? burn : aura;
    }

    // The production half (dc_shaman_spirit_link.cpp).
    bool Is(std::uint32_t spellId);
    // The cast has no hit of its own; the link's damage ticks.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets` (the target first): the link is made.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // `target` took `damage` of school `school` from the Shaman's hit of `spellId` (Combat::DealHit): the other linked
    // enemies take their share.
    void Dealt(Player* player, Unit* target, std::uint32_t spellId, unsigned school, bool critical, double damage);
    // The link's deaths and its end; called from the class's upkeep.
    void Upkeep(Player* player);
    void Forget(Player* player);
} // namespace DC::Combat::Shaman::SpiritLink
