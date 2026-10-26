// The Wizard's passives that need code of their own; most are sheet numbers read where the skills use them.
#pragma once
#include "dc_wizard_internal.h"

namespace DC::Combat::Wizard::Passive
{
    // A cast has begun: Prodigy's Arcane Power on a Signature spell.
    void Prodigy(Player* player, std::uint32_t spellId);
    // A cast has begun: Arcane Dynamo's Flash of Insight, and the empowering of the next listed skill. Called with the module lock held.
    void ArcaneDynamo(Player* player, Shared::State& state, std::uint32_t spellId);
    // A cast has begun: Illusionist's movement speed after Mirror Image, Slow Time or Teleport. Called with the module lock held.
    void IllusionistBegin(Player* player, Shared::State& state, std::uint32_t spellId);
    // Unstable Anomaly: fatal damage becomes a shield; true when it did, with `damage` zero. Called with the module lock held.
    bool UnstableAnomaly(Player* victim, Shared::State& state, uint64 now, std::uint32_t& damage);
    // Illusionist: too much damage in the window takes the cooldowns of Mirror Image, Slow Time and Teleport. Called with the module lock held.
    void Illusionist(Player* victim, Shared::State& state, uint64 now, double maxLife, std::uint32_t damage);
    // Evocation's cooldown reduction is on while the passive is slotted.
    void Evocation(Player* player);
    // Galvanizing Ward's shield after a time without damage; `now` is the update's time.
    void GalvanizingWard(Player* player, uint64 now);
    // Dominance: a kill is a stack of the shield.
    void Dominance(Player* player);
} // namespace DC::Combat::Wizard::Passive
