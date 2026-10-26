#pragma once
// Fan of Knives' rules that need no core type, header-only so tests/demon_hunter_fan_of_knives compiles this exact
// code: which rune is which and which enemies Assassin's Knives throws at. The production half is
// dc_demon_hunter_fan_of_knives.cpp.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::FanOfKnives
{
    enum class Rune
    {
        None,
        KnivesExpert,     // no cooldown, 30 Hatred, Fire
        AssassinsKnives,  // long-range knives at more enemies
        FanOfDaggers,     // knockback and a stun, Fire
        PinpointAccuracy, // a longer cooldown and far more damage, Lightning
        BladedArmor       // armor for a while, Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Knives Expert")
            return Rune::KnivesExpert;
        if (name == "Assassin's Knives")
            return Rune::AssassinsKnives;
        if (name == "Fan of Daggers")
            return Rune::FanOfDaggers;
        if (name == "Pinpoint Accuracy")
            return Rune::PinpointAccuracy;
        if (name == "Bladed Armor")
            return Rune::BladedArmor;
        return Rune::None;
    }

    // "Also throw long-range knives that deal {damage_pct} weapon damage to {target_count} additional enemies": of the
    // enemies within `searchYards` of the Demon Hunter (`distances`, one for each), the ones the fan did not reach
    // (farther than `fanYards`), nearest first, at most `most` of them. The positions in `distances` come back.
    inline std::vector<std::size_t> ExtraTargets(std::vector<double> const& distances, double fanYards,
                                                 double searchYards, unsigned most)
    {
        std::vector<std::size_t> picked;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] > fanYards && distances[i] <= searchYards)
                picked.push_back(i);
        std::stable_sort(picked.begin(), picked.end(),
                         [&distances](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (picked.size() > most)
            picked.resize(most);
        return picked;
    }

    // The production half (dc_demon_hunter_fan_of_knives.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The fan hit `target`: the slow every rune carries and Fan of Daggers' knockback and stun.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The cast resolved: Assassin's Knives' extra throws and Bladed Armor's armor.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::DemonHunter::FanOfKnives
