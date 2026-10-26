// The Shaman's totems on the core's four native totem slots (fire, earth, water, air): the entry points the class
// dispatch and the totem skills call.
#pragma once

#include <cstdint>
#include <unordered_set>

class Creature;
class Player;

namespace DC::Combat::Shaman::Totems
{
    // What a totem keeps between its updates: two clocks (a skill's bolt and its second pulse), a count of its bolts
    // and the enemies it has met.
    struct State
    {
        std::uint32_t clock[2] = {0, 0};
        unsigned bolts = 0;
        bool placed = false; // the totem's placing has been told to its skill
        std::unordered_set<std::uint64_t> seen;
    };

    // A cast of `spellId` began and was paid (Shaman::Casting): a skill of the Totems category sets its totem down at
    // the Shaman's feet.
    void Cast(Player* player, std::uint32_t spellId);
    // The totem standing in `slot` (FireSlot to AirSlot), null for none.
    Creature* Totem(Player const* player, unsigned slot);
    // The record the totem standing in `slot` (FireSlot to AirSlot) was cast from, 0 for none. Skills that act while
    // their totem stands ask it.
    std::uint32_t Standing(Player const* player, unsigned slot);
    // Takes every totem the player has away (logout, a change of floor).
    void Away(Player* player);
    void RegisterScripts();
} // namespace DC::Combat::Shaman::Totems
