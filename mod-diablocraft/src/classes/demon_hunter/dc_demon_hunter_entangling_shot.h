#pragma once
// Entangling Shot's rules that need no core type, header-only so tests/demon_hunter_entangling_shot compiles this exact
// code: which rune is which and which enemies a shot entangles, given the ones already entangled. The production half is
// dc_demon_hunter_entangling_shot.cpp.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::EntanglingShot
{
    enum class Rune
    {
        None,
        HeavyBurden,     // a longer slow and Cold
        ChainGang,       // more enemies entangled
        ShockCollar,     // the entangled take Lightning over time
        JusticeIsServed, // more Hatred (paid by the class's Connected) and Fire
        BountyHunter     // a stronger slow
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Heavy Burden")
            return Rune::HeavyBurden;
        if (name == "Chain Gang")
            return Rune::ChainGang;
        if (name == "Shock Collar")
            return Rune::ShockCollar;
        if (name == "Justice is Served")
            return Rune::JusticeIsServed;
        if (name == "Bounty Hunter")
            return Rune::BountyHunter;
        return Rune::None;
    }

    // An enemy entangled until a game time (milliseconds).
    struct Tie
    {
        std::uint64_t enemy;
        std::uint64_t untilMs;
    };

    // "entangles up to {target_count} enemies ... When Entangling Shot hits an enemy, the Slow effect on all entangled
    // enemies is refreshed": the enemies a shot at `primary` entangles at game time `nowMs`, `held` being the ties the
    // Demon Hunter's last shot left and `nearest` the other enemies around the primary, nearest first. The primary is always
    // entangled; when it is one of the enemies still entangled, those stay (and are all refreshed) and any room left up
    // to `count` is filled from the nearest, else the nearest alone fill it.
    inline std::vector<std::uint64_t> Entangled(std::vector<Tie> const& held, std::uint64_t nowMs, std::uint64_t primary,
                                                std::vector<std::uint64_t> const& nearest, std::size_t count)
    {
        std::vector<std::uint64_t> group;
        if (!count)
            return group;
        group.push_back(primary);
        auto const has = [&group](std::uint64_t enemy) { return std::find(group.begin(), group.end(), enemy) != group.end(); };
        bool const linked = std::any_of(held.begin(), held.end(),
                                        [&](Tie const& tie) { return tie.enemy == primary && tie.untilMs > nowMs; });
        if (linked)
            for (Tie const& tie : held)
                if (tie.untilMs > nowMs && group.size() < count && !has(tie.enemy))
                    group.push_back(tie.enemy);
        for (std::uint64_t enemy : nearest)
            if (group.size() < count && !has(enemy))
                group.push_back(enemy);
        return group;
    }

    // Of the enemies a shot reaches, the ones the engine's own hit is left to: only the enemy thrown at. The record carries
    // the entangle count in the core's chain slot, and the core chains to that many more enemies; D3 hurts the one hit and
    // entangles the rest, which the entangle below does itself.
    inline bool LeftToEngine(bool isTheEnemyShotAt)
    {
        return isTheEnemyShotAt;
    }

    // The production half (dc_demon_hunter_entangling_shot.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The shot's own hit, which every rune inherits (Shock Collar's 80% is the damage over time's, not the shot's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // A shot reached `target`, `aimed` being the enemy it was shot at (Combat's Impact, before the hit): true for an enemy the
    // core chained it to, which takes the entangle and no hit.
    bool Impact(Player* player, Unit* target, Unit* aimed, std::uint32_t spellId);
    // The shot landed on `target`: the entangle, the slow and Shock Collar's damage over time.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter::EntanglingShot
