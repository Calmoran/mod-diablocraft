#pragma once
// The Witch Doctor's passives that change how long a skill's effect or cooldown lasts: Tribal Rites and Creeping Death.
// The rules that need no core type are dc_witch_doctor_passive_rules.h; the numbers are witch_doctor_passive_values.csv
// (Creeping Death's one is the power file's, a tunable), read through each passive's record.
class Player;

namespace DC::Combat::WitchDoctor::Passive::Skills
{
    // Creeping Death: the seconds a debuff of `baseSeconds` lasts for `player` ("last almost forever": the power file's
    // 120 seconds while the passive is on). Piranhas' amplified damage asks it; Haunt and Locust Swarm will when they
    // are built.
    double Lasting(Player* player, double baseSeconds);
    // The cast hook for Tribal Rites; at startup.
    void Register();
} // namespace DC::Combat::WitchDoctor::Passive::Skills
