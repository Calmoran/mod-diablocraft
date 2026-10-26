// The bonus the next Arcane or Lightning spell takes: Wave of Force's Arcane Attunement and Arcane Orb's Spark.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::NextSpellBonus
{
    // A cast has resolved over `targets`: it spends the bonus of its school, and the two runes set theirs anew. Called with the module lock held.
    void Cast(Shared::State& state, uint32 id, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Wizard::NextSpellBonus
