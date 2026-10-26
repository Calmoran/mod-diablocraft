#pragma once
// What the Witch Doctor's passive files share: a passive's record, whether the Witch Doctor has it on and its sheet
// numbers (witch_doctor_passive_values.csv, the passive's name is its skill), read through its record. The class's tunables are
// dc_witch_doctor_common.h's Tune.
#include "dc_witch_doctor_common.h"
#include "../dc_classes.h"
#include "../dc_resources.h"
#include "../../combat/dc_passives.h"
#include "../../combat/dc_spell_numbers.h"
#include "../../combat/dc_spell_shells.h"

#include <cstdint>
#include <string_view>

namespace DC::Combat::WitchDoctor::Passive
{
    inline std::uint32_t Id(std::string_view name)
    {
        for (auto const& passive : Shells::Passives)
            if (name == passive.name)
                return passive.id;
        return 0;
    }

    inline bool IsWitchDoctor(Player const* player)
    {
        return player && Classes::ClassIdOf(player) == Resources::Mana.classId;
    }

    // A passive is on when it sits in one of the Witch Doctor's passive slots, or a worn item grants it.
    inline bool On(Player* player, char const* name)
    {
        return IsWitchDoctor(player) && Combat::Passives::Has(player, name);
    }

    inline double Num(char const* name, char const* token, char const* qualifier = "")
    {
        return Numbers::Num(Id(name), token, qualifier);
    }
} // namespace DC::Combat::WitchDoctor::Passive
