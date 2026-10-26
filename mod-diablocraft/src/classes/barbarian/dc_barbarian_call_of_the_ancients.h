#pragma once
#include <cstdint>
class Player;
class Unit;
namespace DC::Classes::Ancients
{
    // Entries 900100-900102 are Talic, Korlic and Madawc (creature_template, ScriptName dc_ancient).
    constexpr std::uint32_t FirstEntry = 900100, Count = 3;
    constexpr bool IsAncientEntry(std::uint32_t entry)
    {
        return entry >= FirstEntry && entry < FirstEntry + Count;
    }
    // Creature::AI() is whatever the last AIM_Initialize installed, and a script hook (the rift
    // one) can replace it. ScriptedAI keeps its own `me`, so a static_cast to our AI on a
    // different AI reads a field that is not there. Never static_cast an AI; use this.
    template <class Target, class Base>
    Target* AiAs(Base* ai)
    {
        return dynamic_cast<Target*>(ai);
    }
    // The Ancients are the owner's companions. They fight what the owner fights
    // and otherwise follow him; they never pick a fight of their own. The owner's current attack
    // target comes first; his selection counts only while he is in combat, so merely clicking a
    // monster does not send them off. None means: follow the owner.
    enum class Pick { None, Victim, Selected };
    constexpr Pick PickTarget(bool victimValid, bool ownerInCombat, bool selectedValid)
    {
        if (victimValid)
            return Pick::Victim;
        if (ownerInCombat && selectedValid)
            return Pick::Selected;
        return Pick::None;
    }
    // Each Ancient keeps its own spot beside the owner (radians, 0 = in front, pi/2 = beside).
    constexpr float FollowAngle(std::uint32_t index)
    {
        return 1.5707963f + (float(index) - 1.0f) * 0.9f;
    }
    void RegisterScripts();
    void Summon(Player*, std::uint32_t);
    // Whether the player's Ancients are alive (Call of the Ancients is active).
    bool Active(Player const*);
    void Spent(Player*, double);
    void Redirect(Player*, std::uint32_t&);
    void HealAll(Player*, std::uint32_t, double);
} // namespace DC::Classes::Ancients
