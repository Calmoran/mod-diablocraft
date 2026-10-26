#pragma once
// The Witch Doctor's passives that keep the Witch Doctor alive: Zombie Handler's Life, Spirit Vessel, Swampland Attunement and Grave Injustice. The rules that
// need no core type are dc_witch_doctor_passive_rules.h; the numbers are witch_doctor_passive_values.csv, read through
// each passive's record.
class Unit;

namespace DC::Combat::WitchDoctor::Passive::Survival
{
    // The damage `victim` takes after Spirit Vessel (Combat's Mitigate, beside the Necromancer's Reduce).
    double Reduce(Unit* victim, double damage);
    // The update script that keeps the sheet's Life percent; at startup.
    void Register();
} // namespace DC::Combat::WitchDoctor::Passive::Survival
