// Energy Twister: the base skill and its travelling runes wander forward from the aim point; Storm Chaser's Lightning Charges are
// stored by the rune's cast and released by the next Signature spell.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::EnergyTwister
{
    // A cast has begun: a Signature spell releases the stored charges as a bolt. Called with the module lock held.
    void Begin(Player* player, Shared::State& state, std::uint32_t spellId, Unit* explicitTarget);
    // A cast has resolved: the rune grants one charge, up to the sheet's most. Called with the module lock held.
    void Cast(Shared::State& state, uint32 id);
    // The base skill and every rune but Wicked Wind (which spins in place on the stationary ground) travel.
    bool Wanders(uint32 id);
    // The twister that stays: Wicked Wind's, on the generic ground at `center`, pulls (Ranslor's Folly) as a wandering one does, from the cast point, for the ground's life.
    void Stay(Player* player, uint32 id, Position const& center);
    // The twister appears at `center` and wanders forward for its life. Takes the module lock itself.
    void Start(Player* player, uint32 id, Position const& center);
} // namespace DC::Combat::Wizard::EnergyTwister
