#pragma once
// Immunity to control impairing effects, for a time a skill or a power gives: the core's own spell immunity lists (the mechanics a
// player counts as control, and the aura types that put them on), kept under a key so two givers never take each other's away. The key
// is the giver's own (0 is Invigorating Gemstone's, 1 the item powers', a rune's its own spell id). The one list of those mechanics is here: the gem
// powers, Temple of Protection and Bone Armor's Limited Immunity all give it through Set, and Bane of the Trapped asks Impaired.
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::ControlImmunity
{
    // Puts the immunity under `key` on the player or takes it off; going on strips what is already on them.
    void Set(Player* player, std::uint32_t key, bool on);
    // The narrower immunity Tremor Totem gives: Fear, Charm and Stun alone, under the same kind of key.
    void SetFearCharmStun(Player* player, std::uint32_t key, bool on);
    // Takes every control impairing aura off the player, and leaves no immunity behind (a skill that "removes all control effects").
    void Strip(Player* player);
    // Whether the unit carries an aura of one of those mechanics (a stun, a root, a fear, a slow ...).
    bool Impaired(Unit const* unit);
    // Whether it carries one of them that is not a slow (the snare): Krysbin's Sentence triples its bonus against these.
    bool ImpairedBesidesSlow(Unit const* unit);
} // namespace DC::Combat::ControlImmunity
