// The Familiar: the companion the skill summons, the attack it makes when the Wizard casts, and Ancient Guardian.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Familiar
{
    // The Wizard's Familiar if it is up and alive.
    Creature* FamiliarOf(Player* player);
    // Summons the Familiar, replacing the one already up.
    void SummonFamiliar(Player* player);
    // A cast has begun: the Familiar attacks, at most once every attack_frames_count of attack speed. Called with the module lock held.
    void Begin(Player* player, Shared::State& state, std::uint32_t spellId, Unit* explicitTarget);
    // Ancient Guardian: whether the Familiar takes the attack about to land on `victim` (and `damage` goes to zero).
    // Called with the module lock held.
    bool Guardian(Player* victim, Shared::State& state, uint64 now, std::uint32_t& damage);
    void RegisterScripts();
} // namespace DC::Combat::Wizard::Familiar
