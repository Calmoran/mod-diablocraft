// Seismic Slam: the heal of Strength from Earth, the Rumble zone and the chill of Permafrost.
#pragma once
#include "dc_barbarian_internal.h"

namespace DC::Combat::Abilities::SeismicSlam
{
    using Shared::Row;
    using Shared::State;

    // The cast: Strength from Earth's heal, Rumble's zone on the enemies the slam hit.
    void OnCast(Player* p, uint32 id, Row const* r, std::vector<Unit*> const& targets, Position const* center, double extraDamage, State& s);
    // A hit of the skill landed on `target`: Permafrost's chill.
    void OnHit(Player* p, Unit* target, Row const* r);
    // Whether the rune keeps the sheet's damage.
    bool KeepsSheetDamage(std::string const& skill, std::string const& rune);
    // Whether the rune spends the whole pool at the cast.
    bool SpendsEveryPoint(std::string const& skill, std::string const& rune);
    // A cast begins with `fury` in the pool and `cost` about to be taken: Rumble turns the rest into damage.
    void OnBegin(std::string const& skill, std::string const& rune, uint32 id, double fury, double cost, double& extraDamage);
} // namespace DC::Combat::Abilities::SeismicSlam
