// Spectral Blade: Barrier Blades' shield on a cast, Flame Blades' stacking Fire bonus and Ice Blades' chill and freeze.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::SpectralBlade
{
    // A cast has begun: Barrier Blades' shield.
    void Begin(Player* player, std::uint32_t spellId);
    // A Flame Blades hit: one more stack of the Fire bonus, each with its own clock.
    void FlameBlade(Player* player, uint32 id);
    // Takes the stacks that ran out off the buff; called every update.
    void SyncFlameBlades(Player* player);
    // An Ice Blades hit: the freeze of an enemy chilled before it, then the chill.
    void IceBlades(Player* player, Unit* target, uint32 id);
    // Adds the Fire bonus of the Flame Blades stacks the Wizard wears.
    void FlameBladesBonus(Player* player, double& bonus);
} // namespace DC::Combat::Wizard::SpectralBlade
