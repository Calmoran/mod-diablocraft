// Frost Nova: the freeze, Bone Chill's and Deep Freeze's marks, the mist Frozen Mist leaves and Shatter's second nova.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::FrostNova
{
    // The cast has resolved over `targets`: the freeze and the marks of the runes, or the mist's place.
    void Cast(Player* player, uint32 id, std::vector<Unit*> const& targets);
    // One tick of Frozen Mist, `seconds` being the period.
    void MistTick(Player* player, uint32 id, double seconds);
    // A frozen enemy was killed: Shatter's chance to release another nova from the bar.
    void Shatter(Player* player, Unit* killed);
} // namespace DC::Combat::Wizard::FrostNova
