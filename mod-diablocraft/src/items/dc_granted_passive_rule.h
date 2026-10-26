/*
 * World of DiabloCraft - a class passive an item grants (Hellfire Amulet).
 *
 * Pure functions only, so tests/granted_passive/harness.cpp compiles this exact header. Which classes and
 * passives exist is data (dc_class_passive); no class or passive is named here.
 *
 * The amulet carries base_items.csv's `extra_passive` preset. The roller takes a class passive for it once,
 * from the roll's class (the crafter's own, or the class a drop rolled for), out of that class's FULL passive
 * list, whatever the player has chosen (the player can change their passives, so a passive
 * is never excluded or re-rolled because it is picked). It is stored as a dc_item_affix row of kind 'passive'
 * (affix_id the passive's name) and read back while the item is worn and unbroken. Passives::Has answers for
 * the chosen passives OR the granted ones, so a copy of a chosen passive adds nothing.
 */

#ifndef DC_GRANTED_PASSIVE_RULE_H
#define DC_GRANTED_PASSIVE_RULE_H

#include <algorithm>
#include <cstddef>
#include <string>
#include <vector>

namespace DC::GrantedPassive
{
    inline constexpr char const* Preset = "extra_passive";
    inline constexpr char const* Kind = "passive";

    // A legendary base that lists the preset rolls a passive. The ethereal weapons list it too and are
    // not part of this rule (they stay as they are).
    inline bool Rolls(std::vector<std::string> const& presets, std::string const& rarity)
    {
        return rarity == "legendary" && std::find(presets.begin(), presets.end(), Preset) != presets.end();
    }

    // Uniform over the class's whole list; pick is uniform in [0, 1). Empty when the class has none.
    inline std::string Pick(std::vector<std::string> const& classPassives, double pick)
    {
        if (classPassives.empty())
            return std::string();
        std::size_t index = static_cast<std::size_t>(std::clamp(pick, 0.0, 1.0) * classPassives.size());
        return classPassives[std::min(index, classPassives.size() - 1)];
    }

    // The passive an item's stored rows grant while it is worn: the row of kind 'passive' (the first, if a
    // damaged item somehow holds two). Rows are anything with .kind and .affixId (Items::Affix). A broken
    // item is not worn as far as Items::Apply is concerned, so it grants nothing there.
    template<typename Rows>
    std::string Granted(Rows const& rows)
    {
        for (auto const& row : rows)
            if (row.kind == Kind)
                return row.affixId;
        return std::string();
    }

    // What Passives::Has searches: the chosen passives, then each granted one not already there.
    inline std::vector<std::string> Merge(std::vector<std::string> chosen, std::vector<std::string> const& granted)
    {
        for (std::string const& name : granted)
            if (!name.empty() && std::find(chosen.begin(), chosen.end(), name) == chosen.end())
                chosen.push_back(name);
        return chosen;
    }
} // namespace DC::GrantedPassive

#endif // DC_GRANTED_PASSIVE_RULE_H
