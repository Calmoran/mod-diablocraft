#pragma once
// The Witch Doctor's passive that is about the pets and needs code of its own: Fierce Loyalty's speed. What Zombie Handler, Midnight
// Feast and Fierce Loyalty's extra dogs and Fetish Sycophants' Fetishes give the pets is the pets' piece's (dc_witch_doctor_pets.cpp),
// which reads those passives' sheets itself. The rules that need no core type are dc_witch_doctor_passive_rules.h.

namespace DC::Combat::WitchDoctor::Passive::Pets
{
    // The update script that keeps Fierce Loyalty's speed; at startup.
    void Register();
} // namespace DC::Combat::WitchDoctor::Passive::Pets
