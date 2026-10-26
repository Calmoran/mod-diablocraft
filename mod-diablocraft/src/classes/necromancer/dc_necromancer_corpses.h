#pragma once
// The Necromancer's side of the corpses: a kill by a Necromancer, its minions or its party leaves a corpse for each
// Necromancer of the party. The record, its cap, its lifetime and what takes it are shared (combat/dc_corpses.h); this
// file only says whose kills leave one and for whom.

namespace DC::Combat::Necromancer::KillCorpses
{
    // The kill hook (Combat::Necromancer::RegisterScripts).
    void RegisterScripts();
} // namespace DC::Combat::Necromancer::KillCorpses
