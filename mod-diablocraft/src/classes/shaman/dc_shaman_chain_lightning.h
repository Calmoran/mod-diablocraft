#pragma once
// Chain Lightning's rules that need no core type, header-only so tests/shaman_chain_lightning compiles this exact code:
// which rune is which, which records the skill hands the loader the hit of, the walk of the jumps, what a Chain Frost
// jump deals, the Life a Chain Heal gives and when a Thunderhead refunds. The production half is
// dc_shaman_chain_lightning.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::ChainLightning
{
    enum class Rune
    {
        None,
        ForkedLightning, // jumps to more enemies, Lightning
        ChainLava,       // the enemies hit also burn, Fire
        ChainFrost,      // each jump chills and deals more than the one before, Cold
        ChainHeal,       // each enemy hit heals the Shaman, Cold
        Thunderhead      // refunds Maelstrom when it hits a crowd, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Forked Lightning")
            return Rune::ForkedLightning;
        if (name == "Chain Lava")
            return Rune::ChainLava;
        if (name == "Chain Frost")
            return Rune::ChainFrost;
        if (name == "Chain Heal")
            return Rune::ChainHeal;
        if (name == "Thunderhead")
            return Rune::Thunderhead;
        return Rune::None;
    }

    // Whether the cast's own hit is the skill's number although the plain loader rule would read another: Chain Lava
    // states a `damage_pct` of its own that is its burn, beside a duration the loader reads as a damage that waits. The
    // bolt still hits for the skill's.
    inline bool HitIsSkills(Rune rune)
    {
        return rune == Rune::ChainLava;
    }

    // The enemies the bolt hits, first to last: `first`, then up to `jumps` more, each the nearest enemy to the one
    // before that it has not hit yet. `near(on)` lists the enemies within the jump radius of `on` and `distance(a, b)`
    // measures; an enemy on its own ends the walk.
    template<class Enemy, class Near, class Distance>
    std::vector<Enemy> Walk(Enemy first, unsigned jumps, Near near, Distance distance)
    {
        std::vector<Enemy> hit{first};
        Enemy on = first;
        for (unsigned jump = 0; jump < jumps; ++jump)
        {
            std::optional<Enemy> best;
            for (Enemy const& candidate : near(on))
            {
                if (std::find(hit.begin(), hit.end(), candidate) != hit.end())
                    continue;
                if (!best || distance(on, candidate) < distance(on, *best))
                    best = candidate;
            }
            if (!best)
                break;
            hit.push_back(*best);
            on = *best;
        }
        return hit;
    }

    // Chain Frost: the weapon damage percent of jump number `jump` (1 for the first jump), each `bonusPct` percent more
    // than the one before it. The bolt's own hit is jump 0.
    inline double JumpPct(double basePct, double bonusPct, unsigned jump)
    {
        return basePct * std::pow(1.0 + (bonusPct > 0 ? bonusPct : 0.0) / 100.0, double(jump));
    }

    // Chain Heal: "Each enemy hit heals you for {heal_pct} of your maximum Life".
    inline double HealAmount(double maxLife, double pct)
    {
        return maxLife > 0 && pct > 0 ? maxLife * pct / 100.0 : 0.0;
    }

    // Thunderhead: "When Chain Lightning hits {nearby_enemy_count} or more enemies, it refunds {gain_resource}
    // Maelstrom".
    inline double Refund(unsigned enemies, double needed, double gain)
    {
        return needed > 0 && gain > 0 && double(enemies) >= needed ? gain : 0.0;
    }

    // The production half (dc_shaman_chain_lightning.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of a Chain Lightning record deals when the plain loader rule would
    // read the wrong one.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The bolt landed on `target`: the jumps and what each rune adds to the enemies hit.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::Shaman::ChainLightning
