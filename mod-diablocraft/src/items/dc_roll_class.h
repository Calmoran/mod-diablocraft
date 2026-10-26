/*
 * World of DiabloCraft - the class an item rolls for (loot roll class,
 * skill-affix class, Mystic class policy).
 *
 * Pure functions only, so scripts/tests/loot/roll_class_tests.cpp compiles this
 * exact header against the generated data. Classes are class_key strings from
 * dc_class_map ("barbarian", "wizard"): which classes exist is data, and no class
 * is named here.
 */

#ifndef DC_ROLL_CLASS_H
#define DC_ROLL_CLASS_H

#include <algorithm>
#include <cstddef>
#include <sstream>
#include <string>
#include <vector>

namespace DC::RollClass
{
    // Which dc_base_item rows may ever drop, from any source (05 section 3 pool rules). Only the
    // latest pool version drops; a Blacksmith-crafted set never drops;
    // and an Ethereal never drops at all.
    // Every drop source - kills, chests, the rift guardian,
    // the first-kill legendary - picks its base through the one pool this builds, so this is the
    // only place that has to say so. Items already in bags are not touched. A Horadric Cache
    // legendary (cacheOnly: in dc_bounties_cache_legendary) comes only from the cache.
    inline bool InDropPool(std::string const& rarity, std::string const& poolVersion, std::string const& craftOnly,
                           std::string const& cacheOnly)
    {
        if (cacheOnly == "yes")
            return false;
        return poolVersion == "yes" && craftOnly != "yes" && rarity != "ethereal";
    }

    // Rule 1. The looter's class (100 - offClassPct)% of the time, otherwise one of
    // the OTHER playable classes, uniformly. roll and pick are uniform in [0, 1).
    // With no other playable class there is nobody else to roll for.
    inline std::string Pick(std::string const& looter, std::vector<std::string> const& playable, double offClassPct,
                            double roll, double pick)
    {
        std::vector<std::string> others;
        for (std::string const& key : playable)
            if (!key.empty() && key != looter && std::find(others.begin(), others.end(), key) == others.end())
                others.push_back(key);
        if (others.empty() || roll * 100.0 >= offClassPct)
            return looter;
        std::size_t index = static_cast<std::size_t>(std::clamp(pick, 0.0, 1.0) * others.size());
        return others[std::min(index, others.size() - 1)];
    }

    // usable_by is the D3Planner ';' list of classes that may equip the type.
    inline bool Lists(std::string const& usableBy, std::string const& key)
    {
        std::istringstream input(usableBy);
        std::string token;
        while (std::getline(input, token, ';'))
            if (token == key)
                return true;
        return false;
    }

    // Rule 2. A base may drop for a roll class when that class can use the type and
    // the item is nobody's or that class's own. Class-only items therefore drop on an
    // off-class roll too; AllowableClass stops the wrong class wearing them, never
    // looting them.
    inline bool Eligible(std::string const& usableBy, std::string const& designated, std::string const& rollClass)
    {
        return !rollClass.empty() && (usableBy.empty() || Lists(usableBy, rollClass)) &&
               (designated.empty() || designated == rollClass);
    }

    // Rule 2, for a set piece. A class set
    // (Armor of Akkhan, Bones of Rathma...) belongs to one class in the source, but its
    // generic pieces (Helm, Boots) name no class in usable_by or designated_class, so the
    // rule above offered them to every roll class. set_class is that source class, and it
    // is the DROP class only: AllowableClass keeps reading usable_by and designated_class,
    // so who may wear a piece does not change. A class-only item's own designation wins.
    inline std::string DropClass(std::string const& designated, std::string const& setClass)
    {
        return designated.empty() ? setClass : designated;
    }

    inline bool DropEligible(std::string const& usableBy, std::string const& designated, std::string const& setClass,
                             std::string const& rollClass)
    {
        return Eligible(usableBy, DropClass(designated, setClass), rollClass);
    }

    // Rule 3. The one class an item's main stat and every skill affix belong to: a
    // class-only item's own class, otherwise the class it rolled for.
    inline std::string AffixClass(std::string const& designated, std::string const& rollClass)
    {
        return designated.empty() ? rollClass : designated;
    }

    // Rule 5. The Mystic: on an ordinary item the re-rolling character's class
    // decides the new main stat and skill affix; a class-only item keeps its own.
    // This is Torment's own class policy, not D3
    // behaviour the research found.
    inline std::string MysticClass(std::string const& designated, std::string const& rerollerClass)
    {
        return AffixClass(designated, rerollerClass);
    }

    // Rule 4. The class an unidentified shell rolls for at identify: the one stored
    // at the drop. A row written before roll classes were stored has none, and falls
    // back to the looter it dropped for - never to whoever identifies it.
    inline std::string ShellClass(std::string const& stored, std::string const& ownerClass)
    {
        return stored.empty() ? ownerClass : stored;
    }

    // Rule 3 for skill affixes: the choices of one slot group that belong to the
    // given class (dc_skill_affix.class_id, the catalogue's class id).
    template<typename Choice>
    std::vector<Choice> ChoicesFor(std::vector<Choice> const& group, unsigned classId)
    {
        std::vector<Choice> out;
        for (Choice const& choice : group)
            if (classId && choice.classId == classId)
                out.push_back(choice);
        return out;
    }
} // namespace DC::RollClass

#endif // DC_ROLL_CLASS_H
